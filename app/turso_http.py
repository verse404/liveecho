"""Zero-dependency Turso (libSQL) Hrana v2 HTTP pipeline client with strict SSRF, TLS, and typed parameter binding."""

from __future__ import annotations

import base64
import logging
import sqlite3
import urllib.parse
from collections.abc import Callable, Sequence
from typing import Any

from app.security import safe_https_request, validate_outbound_https_url

logger = logging.getLogger("concert_tracker.turso")

# TODO(security): Turso's serverless /v2/pipeline API operates over HTTPS (TLS 1.2+) authenticated with a
# database-scoped JWT Bearer token (TURSO_AUTH_TOKEN) rather than raw TCP client-certificate mTLS. Always
# generate a database-scoped least-privilege token (`turso db tokens create <db-name>`) rather than an
# organization-wide admin token.

TransportFn = Callable[[str, str, dict[str, Any]], dict[str, Any]]


def normalize_turso_pipeline_url(raw_url: str, *, validate_dns: bool = True) -> str:
    """Normalizes libsql:// or https:// Turso URLs to https://<host>/v2/pipeline and rejects unsafe URLs."""
    cleaned = (raw_url or "").strip()
    if not cleaned:
        raise ValueError("TURSO_DATABASE_URL cannot be empty.")

    if cleaned.startswith("libsql://"):
        cleaned = "https://" + cleaned[len("libsql://") :]

    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme != "https":
        raise ValueError("TURSO_DATABASE_URL must use libsql:// or https://.")
    if not parsed.hostname:
        raise ValueError("TURSO_DATABASE_URL is missing a valid hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in TURSO_DATABASE_URL are forbidden; pass TURSO_AUTH_TOKEN via environment.")
    if parsed.query or parsed.fragment:
        raise ValueError("Query strings and fragments are forbidden in TURSO_DATABASE_URL.")

    netloc = parsed.hostname
    if parsed.port and parsed.port != 443:
        netloc = f"{parsed.hostname}:{parsed.port}"

    pipeline_url = urllib.parse.urlunsplit(("https", netloc, "/v2/pipeline", "", ""))
    if validate_dns:
        validate_outbound_https_url(pipeline_url)
    return pipeline_url


def encode_hrana_arg(value: Any) -> dict[str, Any]:
    """Encodes a Python parameter into a typed Hrana v2 argument object (prevents SQL injection by design)."""
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray, memoryview)):
        b64 = base64.b64encode(bytes(value)).decode("ascii")
        return {"type": "blob", "base64": b64}
    return {"type": "text", "value": str(value)}


def decode_hrana_cell(cell: dict[str, Any]) -> Any:
    """Decodes a typed Hrana v2 result cell back into native Python types."""
    ctype = cell.get("type")
    if ctype == "null" or ctype is None:
        return None
    if ctype == "integer":
        return int(cell["value"])
    if ctype == "float":
        return float(cell["value"])
    if ctype == "blob":
        return base64.b64decode(cell.get("base64") or "")
    return str(cell.get("value") or "")


def split_sql_script(script: str) -> list[str]:
    """Splits a multi-statement SQL schema script on top-level semicolons while respecting quoted literals."""
    statements: list[str] = []
    buf: list[str] = []
    in_single_quote = False
    i = 0
    n = len(script)

    while i < n:
        ch = script[i]
        if ch == "'" and not in_single_quote:
            in_single_quote = True
            buf.append(ch)
        elif ch == "'" and in_single_quote:
            buf.append(ch)
            if i + 1 < n and script[i + 1] == "'":
                buf.append("'")
                i += 1
            else:
                in_single_quote = False
        elif ch == "-" and not in_single_quote and i + 1 < n and script[i + 1] == "-":
            while i < n and script[i] != "\n":
                i += 1
            continue
        elif ch == ";" and not in_single_quote:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf.clear()
        else:
            buf.append(ch)
        i += 1

    trailing = "".join(buf).strip()
    if trailing:
        statements.append(trailing)
    return statements


class TursoRow(dict[str, Any]):
    """sqlite3.Row-compatible dictionary supporting both column-name (`row['id']`) and positional (`row[0]`) access."""

    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        super().__init__(zip(columns, values, strict=False))
        self._positional = tuple(values)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._positional[key]
        return super().__getitem__(key)


class TursoCursor:
    """DB-API 2.0 compatible cursor returned by TursoHttpConnection."""

    def __init__(
        self,
        rows: list[TursoRow],
        rowcount: int = 0,
        lastrowid: int = 0,
    ) -> None:
        self._rows = rows
        self._idx = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self) -> TursoRow | None:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self) -> list[TursoRow]:
        if self._idx == 0:
            self._idx = len(self._rows)
            return list(self._rows)
        rem = self._rows[self._idx :]
        self._idx = len(self._rows)
        return rem


class TursoHttpConnection:
    """Stateless-per-pipeline HTTPS connection to Turso (libSQL) matching sqlite3.Connection's interface."""

    def __init__(
        self,
        pipeline_url: str,
        auth_token: str,
        *,
        transport_fn: TransportFn | None = None,
    ) -> None:
        self._pipeline_url = pipeline_url
        self._auth_token = auth_token
        self._transport_fn = transport_fn
        self._closed = False

    def _default_transport(self, url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = safe_https_request(
            "POST",
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_body=payload,
            timeout=12.0,
        )
        if resp.status_code in (401, 403):
            raise sqlite3.OperationalError("Turso authentication failed (HTTP 401/403). Check TURSO_AUTH_TOKEN.")
        if resp.status_code >= 400:
            raise sqlite3.OperationalError(f"Turso HTTP pipeline returned status {resp.status_code}.")
        try:
            data = resp.json()
        except ValueError as exc:
            raise sqlite3.OperationalError("Turso HTTP pipeline returned non-JSON response.") from exc
        if not isinstance(data, dict):
            raise sqlite3.OperationalError("Unexpected Turso pipeline envelope.")
        return data

    def _send_pipeline(self, requests_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed TursoHttpConnection.")
        payload = {"requests": requests_list}
        sender = self._transport_fn or self._default_transport
        envelope = sender(self._pipeline_url, self._auth_token, payload)
        results = envelope.get("results")
        if not isinstance(results, list):
            raise sqlite3.OperationalError("Turso response missing 'results' array.")

        for item in results:
            if item.get("type") == "error":
                err_obj = item.get("error") or {}
                code = str(err_obj.get("code") or "")
                msg = str(err_obj.get("message") or "Turso query execution error")
                if "CONSTRAINT" in code.upper() or "CONSTRAINT" in msg.upper():
                    raise sqlite3.IntegrityError(msg)
                raise sqlite3.OperationalError(msg)
        return results

    @staticmethod
    def _needs_fk_pragma(sql: str) -> bool:
        head = sql.lstrip()[:12].upper()
        return head.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))

    def execute(self, sql: str, params: Sequence[Any] = ()) -> TursoCursor:
        stmt_obj: dict[str, Any] = {"sql": sql}
        if params:
            stmt_obj["args"] = [encode_hrana_arg(p) for p in params]

        reqs: list[dict[str, Any]] = []
        if self._needs_fk_pragma(sql):
            reqs.append({"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = ON"}})
        reqs.append({"type": "execute", "stmt": stmt_obj})
        reqs.append({"type": "close"})

        results = self._send_pipeline(reqs)
        exec_idx = 1 if self._needs_fk_pragma(sql) else 0
        exec_res = ((results[exec_idx].get("response") or {}).get("result")) or {}

        cols = [str(c.get("name") or f"col_{i}") for i, c in enumerate(exec_res.get("cols") or [])]
        decoded_rows: list[TursoRow] = []
        for raw_row in exec_res.get("rows") or []:
            vals = [decode_hrana_cell(cell) for cell in raw_row]
            decoded_rows.append(TursoRow(cols, vals))

        raw_last_id = exec_res.get("last_insert_rowid")
        lastrowid = int(raw_last_id) if raw_last_id is not None and str(raw_last_id) != "" else 0
        rowcount = int(exec_res.get("affected_row_count") or 0)
        return TursoCursor(decoded_rows, rowcount=rowcount, lastrowid=lastrowid)

    def executescript(self, script: str) -> TursoCursor:
        statements = split_sql_script(script)
        if not statements:
            return TursoCursor([])
        reqs: list[dict[str, Any]] = [
            {"type": "execute", "stmt": {"sql": s}}
            for s in statements
            if not s.upper().startswith("PRAGMA JOURNAL_MODE")
        ]
        reqs.append({"type": "close"})
        self._send_pipeline(reqs)
        return TursoCursor([])

    def commit(self) -> None:
        """Statements sent with a trailing close request commit atomically on Turso."""

    def close(self) -> None:
        self._closed = True
