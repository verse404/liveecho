"""SQLite database layer with 100% parameterized queries, schema migrations, and strict per-user ownership isolation."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.security import SecretBox, hash_session_token, mask_secret
from app.turso_http import TransportFn, TursoHttpConnection, normalize_turso_pipeline_url

logger = logging.getLogger("concert_tracker.db")

SESSION_TTL_SECONDS = 7 * 24 * 3600
INACTIVITY_TTL_SECONDS = 24 * 3600

# TODO(security): SQLite runs in-process over restricted local file permissions (0600); if migrated to a
# networked RDBMS (PostgreSQL/MySQL), enforce mTLS connections and least-privilege non-admin DB roles.


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    preferred_region TEXT NOT NULL DEFAULT 'all',
    preferred_cities_json TEXT NOT NULL DEFAULT '[]',
    home_city TEXT NOT NULL DEFAULT '上海',
    calendar_token TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    genre TEXT NOT NULL DEFAULT '',
    region_origin TEXT NOT NULL DEFAULT '',
    apple_music_url TEXT NOT NULL DEFAULT '',
    auto_discover INTEGER NOT NULL DEFAULT 1,
    custom_rss_url TEXT NOT NULL DEFAULT '',
    last_checked_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS uploaded_posters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    poster_uuid TEXT NOT NULL UNIQUE,
    stored_filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    image_blob BLOB,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS concerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    artist_id INTEGER REFERENCES artists(id) ON DELETE SET NULL,
    artist_name TEXT NOT NULL,
    title TEXT NOT NULL,
    city TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'other',
    venue TEXT NOT NULL DEFAULT '',
    show_time TEXT NOT NULL,
    price_text TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '大麦',
    ticket_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'upcoming_drop',
    seat_note TEXT NOT NULL DEFAULT '',
    checklist_want INTEGER NOT NULL DEFAULT 0,
    checklist_realname INTEGER NOT NULL DEFAULT 0,
    checklist_alarm INTEGER NOT NULL DEFAULT 0,
    hotel_booked INTEGER NOT NULL DEFAULT 0,
    rail_booked INTEGER NOT NULL DEFAULT 0,
    event_kind TEXT NOT NULL DEFAULT 'concert',
    festival_name TEXT NOT NULL DEFAULT '',
    lineup_json TEXT NOT NULL DEFAULT '[]',
    approval_doc_no TEXT NOT NULL DEFAULT '',
    approval_source TEXT NOT NULL DEFAULT '',
    poster_uuid TEXT NOT NULL DEFAULT '',
    actual_paid_yuan INTEGER NOT NULL DEFAULT 0,
    venue_rating INTEGER NOT NULL DEFAULT 0,
    seat_view_note TEXT NOT NULL DEFAULT '',
    setlist_note TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    external_key TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_concerts_user_show ON concerts(user_id, show_time);
CREATE INDEX IF NOT EXISTS idx_concerts_user_ext ON concerts(user_id, external_key);

CREATE TABLE IF NOT EXISTS ticket_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concert_id INTEGER NOT NULL REFERENCES concerts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    round_label TEXT NOT NULL,
    sale_time TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT '',
    booking_url TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rounds_user_sale ON ticket_rounds(user_id, sale_time);

CREATE TABLE IF NOT EXISTS refund_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concert_id INTEGER NOT NULL REFERENCES concerts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tier_label TEXT NOT NULL,
    cutoff_time TEXT NOT NULL,
    fee_percent INTEGER NOT NULL DEFAULT 0,
    expect_return_drop INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refunds_user_cutoff ON refund_tiers(user_id, cutoff_time);

CREATE TABLE IF NOT EXISTS notification_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    browser_enabled INTEGER NOT NULL DEFAULT 1,
    bark_url_enc TEXT NOT NULL DEFAULT '',
    serverchan_key_enc TEXT NOT NULL DEFAULT '',
    telegram_bot_token_enc TEXT NOT NULL DEFAULT '',
    telegram_chat_id TEXT NOT NULL DEFAULT '',
    webhook_url_enc TEXT NOT NULL DEFAULT '',
    smtp_host TEXT NOT NULL DEFAULT '',
    smtp_port INTEGER NOT NULL DEFAULT 587,
    smtp_user TEXT NOT NULL DEFAULT '',
    smtp_pass_enc TEXT NOT NULL DEFAULT '',
    notify_email TEXT NOT NULL DEFAULT '',
    vision_api_key_enc TEXT NOT NULL DEFAULT '',
    lead_minutes_json TEXT NOT NULL DEFAULT '[60, 15, 5]',
    show_lead_hours_json TEXT NOT NULL DEFAULT '[24, 3]',
    enable_12306_reminders INTEGER NOT NULL DEFAULT 1,
    enable_return_sniper INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reminder_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    channel TEXT NOT NULL,
    sent_at INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(user_id, event_key, channel)
);
"""

MIGRATION_COLUMNS: list[tuple[str, str, str]] = [
    ("users", "home_city", "TEXT NOT NULL DEFAULT '上海'"),
    ("uploaded_posters", "image_blob", "BLOB"),
    ("concerts", "hotel_booked", "INTEGER NOT NULL DEFAULT 0"),
    ("concerts", "rail_booked", "INTEGER NOT NULL DEFAULT 0"),
    ("concerts", "event_kind", "TEXT NOT NULL DEFAULT 'concert'"),
    ("concerts", "festival_name", "TEXT NOT NULL DEFAULT ''"),
    ("concerts", "lineup_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("concerts", "approval_doc_no", "TEXT NOT NULL DEFAULT ''"),
    ("concerts", "approval_source", "TEXT NOT NULL DEFAULT ''"),
    ("concerts", "poster_uuid", "TEXT NOT NULL DEFAULT ''"),
    ("concerts", "actual_paid_yuan", "INTEGER NOT NULL DEFAULT 0"),
    ("concerts", "venue_rating", "INTEGER NOT NULL DEFAULT 0"),
    ("concerts", "seat_view_note", "TEXT NOT NULL DEFAULT ''"),
    ("concerts", "setlist_note", "TEXT NOT NULL DEFAULT ''"),
    ("notification_settings", "vision_api_key_enc", "TEXT NOT NULL DEFAULT ''"),
    ("notification_settings", "enable_12306_reminders", "INTEGER NOT NULL DEFAULT 1"),
    ("notification_settings", "enable_return_sniper", "INTEGER NOT NULL DEFAULT 1"),
]


class Database:
    """Thread-safe local SQLite / remote Turso (libSQL) repository enforcing user_id ownership on all queries."""

    def __init__(
        self,
        db_path: Path,
        secret_box: SecretBox,
        *,
        turso_url: str | None = None,
        turso_auth_token: str | None = None,
        turso_transport_fn: TransportFn | None = None,
    ) -> None:
        self.db_path = db_path
        self.secret_box = secret_box
        self._lock = threading.RLock()

        raw_turso_url = (turso_url if turso_url is not None else os.getenv("TURSO_DATABASE_URL", "")).strip()
        raw_turso_token = (
            turso_auth_token if turso_auth_token is not None else os.getenv("TURSO_AUTH_TOKEN", "")
        ).strip()
        self._turso_transport_fn = turso_transport_fn

        if raw_turso_url:
            if not raw_turso_token:
                # Fail closed: never silently drop to ephemeral local SQLite when cloud DB was configured.
                raise RuntimeError("TURSO_DATABASE_URL is set, but TURSO_AUTH_TOKEN is missing.")
            self._turso_pipeline_url = normalize_turso_pipeline_url(
                raw_turso_url,
                validate_dns=(turso_transport_fn is None),
            )
            self._turso_auth_token = raw_turso_token
            self.backend_mode = "turso"
            logger.info("Database backend initialized in cloud Turso (libSQL over HTTPS) mode.")
        else:
            self._turso_pipeline_url = ""
            self._turso_auth_token = ""
            self.backend_mode = "sqlite"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _connect(self) -> sqlite3.Connection | TursoHttpConnection:
        if self.backend_mode == "turso":
            return TursoHttpConnection(
                self._turso_pipeline_url,
                self._turso_auth_token,
                transport_fn=self._turso_transport_fn,
            )
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(SCHEMA_SQL)
                cols_cache: dict[str, set[str]] = {}
                for table, col, col_def in MIGRATION_COLUMNS:
                    if table not in cols_cache:
                        cols_cache[table] = {
                            r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
                        }
                    if col not in cols_cache[table]:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
                        cols_cache[table].add(col)
                conn.commit()
            finally:
                conn.close()
            if self.backend_mode == "sqlite":
                try:
                    os.chmod(self.db_path, 0o600)
                except OSError:
                    pass

    # ---------------- Auth & Users ----------------

    def count_users(self) -> int:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
            return int(row["cnt"]) if row else 0

    def create_user(
        self,
        username: str,
        password_hash: str,
        preferred_region: str = "all",
        preferred_cities: list[str] | None = None,
        home_city: str = "上海",
    ) -> int:
        now = int(time.time())
        cal_token = secrets.token_urlsafe(32)
        cities_json = json.dumps(preferred_cities or [], ensure_ascii=False)
        with self._lock, contextlib.closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, preferred_region, preferred_cities_json, home_city, calendar_token, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (username, password_hash, preferred_region, cities_json, home_city or "上海", cal_token, now),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO notification_settings (user_id, updated_at) VALUES (?, ?)",
                (user_id, now),
            )
            conn.commit()
            return user_id

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, preferred_region, preferred_cities_json, home_city, calendar_token FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, username, preferred_region, preferred_cities_json, home_city, calendar_token FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["preferred_cities"] = json.loads(d.pop("preferred_cities_json", "[]"))
            return d

    def get_user_by_calendar_token(self, token: str) -> dict[str, Any] | None:
        if not token or len(token) < 20:
            return None
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, username, preferred_region, preferred_cities_json, home_city FROM users WHERE calendar_token = ?",
                (token,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["preferred_cities"] = json.loads(d.pop("preferred_cities_json", "[]"))
            return d

    def rotate_calendar_token(self, user_id: int) -> str:
        new_token = secrets.token_urlsafe(32)
        with self._lock, contextlib.closing(self._connect()) as conn:
            conn.execute(
                "UPDATE users SET calendar_token = ? WHERE id = ?",
                (new_token, user_id),
            )
            conn.commit()
        return new_token

    def update_user_preferences(
        self,
        user_id: int,
        preferred_region: str,
        preferred_cities: list[str],
        home_city: str | None = None,
    ) -> None:
        cities_json = json.dumps(preferred_cities, ensure_ascii=False)
        with self._lock, contextlib.closing(self._connect()) as conn:
            if home_city is not None:
                conn.execute(
                    "UPDATE users SET preferred_region = ?, preferred_cities_json = ?, home_city = ? WHERE id = ?",
                    (preferred_region, cities_json, home_city, user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET preferred_region = ?, preferred_cities_json = ? WHERE id = ?",
                    (preferred_region, cities_json, user_id),
                )
            conn.commit()

    # ---------------- Sessions ----------------

    def create_session(self, user_id: int) -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_session_token(raw_token)
        csrf_token = secrets.token_urlsafe(32)
        now = int(time.time())
        expires_at = now + SESSION_TTL_SECONDS
        with self._lock, contextlib.closing(self._connect()) as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            conn.execute(
                """
                INSERT INTO sessions (token_hash, user_id, csrf_token, created_at, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token_hash, user_id, csrf_token, now, expires_at, now),
            )
            conn.commit()
        return raw_token, csrf_token

    def validate_session(self, raw_token: str) -> dict[str, Any] | None:
        if not raw_token:
            return None
        token_hash = hash_session_token(raw_token)
        now = int(time.time())
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT s.user_id, s.csrf_token, s.expires_at, s.last_seen_at,
                       u.username, u.preferred_region, u.preferred_cities_json, u.home_city, u.calendar_token
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] <= now or (now - row["last_seen_at"]) > INACTIVITY_TTL_SECONDS:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                conn.commit()
                return None
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
                (now, token_hash),
            )
            conn.commit()
            return {
                "user_id": int(row["user_id"]),
                "username": row["username"],
                "csrf_token": row["csrf_token"],
                "preferred_region": row["preferred_region"],
                "preferred_cities": json.loads(row["preferred_cities_json"] or "[]"),
                "home_city": row["home_city"] or "上海",
                "calendar_token": row["calendar_token"],
            }

    def invalidate_all_user_sessions(self, user_id: int) -> None:
        with self._lock, contextlib.closing(self._connect()) as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()

    # ---------------- Uploaded Posters ----------------

    def record_uploaded_poster(
        self,
        user_id: int,
        poster_uuid: str,
        stored_filename: str,
        original_name: str,
        width: int,
        height: int,
        image_blob: bytes | None = None,
    ) -> None:
        now = int(time.time())
        with self._lock, contextlib.closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO uploaded_posters (
                    user_id, poster_uuid, stored_filename, original_name, width, height, image_blob, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, poster_uuid, stored_filename, original_name, width, height, image_blob, now),
            )
            conn.commit()

    def get_uploaded_poster(self, user_id: int, poster_uuid: str) -> dict[str, Any] | None:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT poster_uuid, stored_filename, original_name, width, height
                FROM uploaded_posters
                WHERE user_id = ? AND poster_uuid = ?
                """,
                (user_id, poster_uuid),
            ).fetchone()
            return dict(row) if row else None

    def get_uploaded_poster_bytes(self, user_id: int, poster_uuid: str) -> bytes | None:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT image_blob
                FROM uploaded_posters
                WHERE user_id = ? AND poster_uuid = ?
                """,
                (user_id, poster_uuid),
            ).fetchone()
            if not row or row["image_blob"] is None:
                return None
            return bytes(row["image_blob"])

    # ---------------- Artists ----------------

    def list_artists(self, user_id: int) -> list[dict[str, Any]]:
        with self._lock, contextlib.closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, name, aliases_json, genre, region_origin, apple_music_url,
                       auto_discover, custom_rss_url, last_checked_at, created_at
                FROM artists
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["aliases"] = json.loads(d.pop("aliases_json", "[]"))
                d["auto_discover"] = bool(d["auto_discover"])
                result.append(d)
            return result

    def list_all_auto_discover_artists(self) -> list[dict[str, Any]]:
        with self._lock, contextlib.closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, name, aliases_json, custom_rss_url, last_checked_at
                FROM artists
                WHERE auto_discover = 1
                """
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["aliases"] = json.loads(d.pop("aliases_json", "[]"))
                out.append(d)
            return out

    def upsert_artist(
        self,
        user_id: int,
        name: str,
        aliases: list[str] | None = None,
        genre: str = "",
        region_origin: str = "",
        apple_music_url: str = "",
        auto_discover: bool = True,
        custom_rss_url: str = "",
    ) -> int:
        now = int(time.time())
        aliases_json = json.dumps(aliases or [], ensure_ascii=False)
        with self._lock, contextlib.closing(self._connect()) as conn:
            existing = conn.execute(
                "SELECT id FROM artists WHERE user_id = ? AND name = ?",
                (user_id, name),
            ).fetchone()
            if existing:
                artist_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE artists
                    SET aliases_json = ?, genre = ?, region_origin = ?, apple_music_url = ?,
                        auto_discover = ?, custom_rss_url = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        aliases_json,
                        genre,
                        region_origin,
                        apple_music_url,
                        1 if auto_discover else 0,
                        custom_rss_url,
                        artist_id,
                        user_id,
                    ),
                )
                conn.commit()
                return artist_id

            cur = conn.execute(
                """
                INSERT INTO artists (user_id, name, aliases_json, genre, region_origin,
                                     apple_music_url, auto_discover, custom_rss_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    name,
                    aliases_json,
                    genre,
                    region_origin,
                    apple_music_url,
                    1 if auto_discover else 0,
                    custom_rss_url,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def mark_artist_checked(self, user_id: int, artist_id: int) -> None:
        now = int(time.time())
        with self._lock, contextlib.closing(self._connect()) as conn:
            conn.execute(
                "UPDATE artists SET last_checked_at = ? WHERE id = ? AND user_id = ?",
                (now, artist_id, user_id),
            )
            conn.commit()

    def delete_artist(self, user_id: int, artist_id: int) -> bool:
        with self._lock, contextlib.closing(self._connect()) as conn:
            cur = conn.execute(
                "DELETE FROM artists WHERE id = ? AND user_id = ?",
                (artist_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    # ---------------- Concerts, Ticket Rounds & Refund Tiers ----------------

    def _hydrate_concert_row(
        self,
        row: sqlite3.Row,
        rounds_map: dict[int, list[dict[str, Any]]],
        refunds_map: dict[int, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        cd = dict(row)
        cid = int(cd["id"])
        for bool_col in ("checklist_want", "checklist_realname", "checklist_alarm", "hotel_booked", "rail_booked"):
            cd[bool_col] = bool(cd.get(bool_col))
        try:
            cd["lineup"] = json.loads(cd.pop("lineup_json", "[]") or "[]")
        except json.JSONDecodeError:
            cd["lineup"] = []
        cd["ticket_rounds"] = rounds_map.get(cid, [])
        cd["refund_tiers"] = refunds_map.get(cid, [])
        return cd

    def list_concerts(self, user_id: int) -> list[dict[str, Any]]:
        with self._lock, contextlib.closing(self._connect()) as conn:
            c_rows = conn.execute(
                "SELECT * FROM concerts WHERE user_id = ? ORDER BY show_time ASC, id ASC",
                (user_id,),
            ).fetchall()
            r_rows = conn.execute(
                """
                SELECT id, concert_id, round_label, sale_time, platform, booking_url
                FROM ticket_rounds
                WHERE user_id = ?
                ORDER BY sale_time ASC, id ASC
                """,
                (user_id,),
            ).fetchall()
            f_rows = conn.execute(
                """
                SELECT id, concert_id, tier_label, cutoff_time, fee_percent, expect_return_drop
                FROM refund_tiers
                WHERE user_id = ?
                ORDER BY cutoff_time ASC, id ASC
                """,
                (user_id,),
            ).fetchall()

            rounds_by_c: dict[int, list[dict[str, Any]]] = {}
            for rr in r_rows:
                rd = dict(rr)
                rounds_by_c.setdefault(int(rd["concert_id"]), []).append(rd)

            refunds_by_c: dict[int, list[dict[str, Any]]] = {}
            for fr in f_rows:
                fd = dict(fr)
                fd["expect_return_drop"] = bool(fd["expect_return_drop"])
                refunds_by_c.setdefault(int(fd["concert_id"]), []).append(fd)

            return [self._hydrate_concert_row(cr, rounds_by_c, refunds_by_c) for cr in c_rows]

    def get_concert(self, user_id: int, concert_id: int) -> dict[str, Any] | None:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM concerts WHERE id = ? AND user_id = ?",
                (concert_id, user_id),
            ).fetchone()
            if not row:
                return None
            r_rows = conn.execute(
                """
                SELECT id, concert_id, round_label, sale_time, platform, booking_url
                FROM ticket_rounds
                WHERE concert_id = ? AND user_id = ?
                ORDER BY sale_time ASC
                """,
                (concert_id, user_id),
            ).fetchall()
            f_rows = conn.execute(
                """
                SELECT id, concert_id, tier_label, cutoff_time, fee_percent, expect_return_drop
                FROM refund_tiers
                WHERE concert_id = ? AND user_id = ?
                ORDER BY cutoff_time ASC
                """,
                (concert_id, user_id),
            ).fetchall()
            refund_list = []
            for fr in f_rows:
                fd = dict(fr)
                fd["expect_return_drop"] = bool(fd["expect_return_drop"])
                refund_list.append(fd)
            return self._hydrate_concert_row(
                row,
                {concert_id: [dict(r) for r in r_rows]},
                {concert_id: refund_list},
            )

    def _insert_child_schedules(
        self, conn: sqlite3.Connection, user_id: int, concert_id: int, payload: dict[str, Any], now: int
    ) -> None:
        for tr in payload.get("ticket_rounds") or []:
            sale_time = (tr.get("sale_time") or "").strip()
            if not sale_time:
                continue
            conn.execute(
                """
                INSERT INTO ticket_rounds (concert_id, user_id, round_label, sale_time, platform, booking_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    concert_id,
                    user_id,
                    (tr.get("round_label") or "一开").strip(),
                    sale_time,
                    (tr.get("platform") or payload.get("platform") or "大麦").strip(),
                    (tr.get("booking_url") or payload.get("ticket_url") or "").strip(),
                    now,
                ),
            )
        for rf in payload.get("refund_tiers") or []:
            cutoff = (rf.get("cutoff_time") or "").strip()
            if not cutoff:
                continue
            conn.execute(
                """
                INSERT INTO refund_tiers (concert_id, user_id, tier_label, cutoff_time, fee_percent, expect_return_drop, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    concert_id,
                    user_id,
                    (rf.get("tier_label") or "无条件退截止").strip(),
                    cutoff,
                    max(0, min(100, int(rf.get("fee_percent") or 0))),
                    1 if rf.get("expect_return_drop", True) else 0,
                    now,
                ),
            )

    def create_concert(self, user_id: int, payload: dict[str, Any]) -> int:
        now = int(time.time())
        ext_key = (payload.get("external_key") or "").strip()
        with self._lock, contextlib.closing(self._connect()) as conn:
            if ext_key:
                dup = conn.execute(
                    "SELECT id FROM concerts WHERE user_id = ? AND external_key = ?",
                    (user_id, ext_key),
                ).fetchone()
                if dup:
                    return int(dup["id"])

            artist_id = payload.get("artist_id")
            artist_name = (payload.get("artist_name") or "").strip()
            clean_title = payload.get("title", "").strip()
            clean_city = payload.get("city", "").strip()
            clean_show_time = payload.get("show_time", "").strip()

            if not ext_key and not payload.get("allow_duplicate"):
                nat_dup = conn.execute(
                    """
                    SELECT id FROM concerts
                    WHERE user_id = ? AND artist_name = ? AND city = ? AND show_time = ? AND title = ?
                    """,
                    (user_id, artist_name, clean_city, clean_show_time, clean_title),
                ).fetchone()
                if nat_dup:
                    return int(nat_dup["id"])

            if not artist_id and artist_name:
                arow = conn.execute(
                    "SELECT id FROM artists WHERE user_id = ? AND name = ?",
                    (user_id, artist_name),
                ).fetchone()
                if arow:
                    artist_id = int(arow["id"])

            lineup_json = json.dumps(payload.get("lineup") or [], ensure_ascii=False)
            cur = conn.execute(
                """
                INSERT INTO concerts (
                    user_id, artist_id, artist_name, title, city, region, venue, show_time,
                    price_text, platform, ticket_url, status, seat_note,
                    checklist_want, checklist_realname, checklist_alarm,
                    hotel_booked, rail_booked, event_kind, festival_name, lineup_json,
                    approval_doc_no, approval_source, poster_uuid,
                    actual_paid_yuan, venue_rating, seat_view_note, setlist_note,
                    source_type, external_key, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    artist_id,
                    artist_name,
                    payload.get("title", "").strip(),
                    payload.get("city", "").strip(),
                    payload.get("region", "other").strip(),
                    payload.get("venue", "").strip(),
                    payload.get("show_time", "").strip(),
                    payload.get("price_text", "").strip(),
                    payload.get("platform", "大麦").strip(),
                    payload.get("ticket_url", "").strip(),
                    payload.get("status", "upcoming_drop").strip(),
                    payload.get("seat_note", "").strip(),
                    1 if payload.get("checklist_want") else 0,
                    1 if payload.get("checklist_realname") else 0,
                    1 if payload.get("checklist_alarm") else 0,
                    1 if payload.get("hotel_booked") else 0,
                    1 if payload.get("rail_booked") else 0,
                    payload.get("event_kind", "concert").strip(),
                    payload.get("festival_name", "").strip(),
                    lineup_json,
                    payload.get("approval_doc_no", "").strip(),
                    payload.get("approval_source", "").strip(),
                    payload.get("poster_uuid", "").strip(),
                    max(0, int(payload.get("actual_paid_yuan") or 0)),
                    max(0, min(5, int(payload.get("venue_rating") or 0))),
                    payload.get("seat_view_note", "").strip(),
                    payload.get("setlist_note", "").strip(),
                    payload.get("source_type", "manual").strip(),
                    ext_key,
                    payload.get("notes", "").strip(),
                    now,
                    now,
                ),
            )
            concert_id = int(cur.lastrowid)
            self._insert_child_schedules(conn, user_id, concert_id, payload, now)
            conn.commit()
            return concert_id

    def update_concert(self, user_id: int, concert_id: int, payload: dict[str, Any]) -> bool:
        now = int(time.time())
        with self._lock, contextlib.closing(self._connect()) as conn:
            existing = conn.execute(
                "SELECT id FROM concerts WHERE id = ? AND user_id = ?",
                (concert_id, user_id),
            ).fetchone()
            if not existing:
                return False

            lineup_json = json.dumps(payload.get("lineup") or [], ensure_ascii=False)
            conn.execute(
                """
                UPDATE concerts
                SET artist_name = ?, title = ?, city = ?, region = ?, venue = ?, show_time = ?,
                    price_text = ?, platform = ?, ticket_url = ?, status = ?, seat_note = ?,
                    checklist_want = ?, checklist_realname = ?, checklist_alarm = ?,
                    hotel_booked = ?, rail_booked = ?, event_kind = ?, festival_name = ?, lineup_json = ?,
                    approval_doc_no = ?, approval_source = ?, poster_uuid = ?,
                    actual_paid_yuan = ?, venue_rating = ?, seat_view_note = ?, setlist_note = ?,
                    notes = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    payload.get("artist_name", "").strip(),
                    payload.get("title", "").strip(),
                    payload.get("city", "").strip(),
                    payload.get("region", "other").strip(),
                    payload.get("venue", "").strip(),
                    payload.get("show_time", "").strip(),
                    payload.get("price_text", "").strip(),
                    payload.get("platform", "大麦").strip(),
                    payload.get("ticket_url", "").strip(),
                    payload.get("status", "upcoming_drop").strip(),
                    payload.get("seat_note", "").strip(),
                    1 if payload.get("checklist_want") else 0,
                    1 if payload.get("checklist_realname") else 0,
                    1 if payload.get("checklist_alarm") else 0,
                    1 if payload.get("hotel_booked") else 0,
                    1 if payload.get("rail_booked") else 0,
                    payload.get("event_kind", "concert").strip(),
                    payload.get("festival_name", "").strip(),
                    lineup_json,
                    payload.get("approval_doc_no", "").strip(),
                    payload.get("approval_source", "").strip(),
                    payload.get("poster_uuid", "").strip(),
                    max(0, int(payload.get("actual_paid_yuan") or 0)),
                    max(0, min(5, int(payload.get("venue_rating") or 0))),
                    payload.get("seat_view_note", "").strip(),
                    payload.get("setlist_note", "").strip(),
                    payload.get("notes", "").strip(),
                    now,
                    concert_id,
                    user_id,
                ),
            )
            if "ticket_rounds" in payload and isinstance(payload["ticket_rounds"], list):
                conn.execute(
                    "DELETE FROM ticket_rounds WHERE concert_id = ? AND user_id = ?",
                    (concert_id, user_id),
                )
            if "refund_tiers" in payload and isinstance(payload["refund_tiers"], list):
                conn.execute(
                    "DELETE FROM refund_tiers WHERE concert_id = ? AND user_id = ?",
                    (concert_id, user_id),
                )
            self._insert_child_schedules(conn, user_id, concert_id, payload, now)
            conn.commit()
            return True

    def patch_concert_quick_state(self, user_id: int, concert_id: int, updates: dict[str, Any]) -> bool:
        now = int(time.time())
        allowed_cols = {
            "status",
            "checklist_want",
            "checklist_realname",
            "checklist_alarm",
            "hotel_booked",
            "rail_booked",
            "seat_note",
            "actual_paid_yuan",
            "venue_rating",
            "seat_view_note",
            "setlist_note",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_cols and v is not None}
        if not filtered:
            return False

        # Column names come strictly from the hardcoded allowed_cols allow-list above; values use ? parameters.
        set_fragments = [f"{col} = ?" for col in filtered] + ["updated_at = ?"]
        params: list[Any] = []
        for col, val in filtered.items():
            if col in ("checklist_want", "checklist_realname", "checklist_alarm", "hotel_booked", "rail_booked"):
                params.append(1 if val else 0)
            elif col in ("actual_paid_yuan", "venue_rating"):
                params.append(int(val))
            else:
                params.append(str(val))
        params.extend([now, concert_id, user_id])

        with self._lock, contextlib.closing(self._connect()) as conn:
            cur = conn.execute(
                f"UPDATE concerts SET {', '.join(set_fragments)} WHERE id = ? AND user_id = ?",
                tuple(params),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_concert(self, user_id: int, concert_id: int, uploads_dir: Path | None = None) -> bool:
        orphan_filename = ""
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT poster_uuid FROM concerts WHERE id = ? AND user_id = ?",
                (concert_id, user_id),
            ).fetchone()
            if not row:
                return False
            poster_uuid = (row["poster_uuid"] or "").strip()
            cur = conn.execute(
                "DELETE FROM concerts WHERE id = ? AND user_id = ?",
                (concert_id, user_id),
            )
            if poster_uuid:
                still_used = conn.execute(
                    "SELECT 1 FROM concerts WHERE user_id = ? AND poster_uuid = ?",
                    (user_id, poster_uuid),
                ).fetchone()
                if not still_used:
                    prec = conn.execute(
                        "SELECT stored_filename FROM uploaded_posters WHERE user_id = ? AND poster_uuid = ?",
                        (user_id, poster_uuid),
                    ).fetchone()
                    if prec:
                        orphan_filename = prec["stored_filename"]
                        conn.execute(
                            "DELETE FROM uploaded_posters WHERE user_id = ? AND poster_uuid = ?",
                            (user_id, poster_uuid),
                        )
            conn.commit()
            deleted = cur.rowcount > 0

        if deleted and orphan_filename and uploads_dir is not None:
            self._safe_unlink_upload(uploads_dir, orphan_filename)
        return deleted

    @staticmethod
    def _safe_unlink_upload(uploads_dir: Path, stored_filename: str) -> None:
        safe_name = os.path.basename(stored_filename or "")
        if not safe_name:
            return
        base_resolved = uploads_dir.resolve()
        candidate = (base_resolved / safe_name).resolve()
        if str(candidate).startswith(str(base_resolved) + os.sep) and candidate.is_file():
            try:
                candidate.unlink()
            except OSError:
                pass

    def run_maintenance(self, uploads_dir: Path | None = None) -> dict[str, int]:
        """Cleans expired sessions, old reminder logs (>60d), and unreferenced poster files (>24h)."""
        now = int(time.time())
        idle_cutoff = now - INACTIVITY_TTL_SECONDS
        log_cutoff = now - 60 * 86400
        poster_cutoff = now - 24 * 3600
        orphan_files: list[str] = []

        with self._lock, contextlib.closing(self._connect()) as conn:
            s_cur = conn.execute(
                "DELETE FROM sessions WHERE expires_at <= ? OR last_seen_at < ?",
                (now, idle_cutoff),
            )
            r_cur = conn.execute(
                "DELETE FROM reminder_logs WHERE sent_at < ?",
                (log_cutoff,),
            )
            orphan_rows = conn.execute(
                """
                SELECT id, stored_filename FROM uploaded_posters
                WHERE created_at < ?
                  AND poster_uuid NOT IN (SELECT poster_uuid FROM concerts WHERE poster_uuid != '')
                """,
                (poster_cutoff,),
            ).fetchall()
            for orow in orphan_rows:
                orphan_files.append(orow["stored_filename"])
                conn.execute("DELETE FROM uploaded_posters WHERE id = ?", (int(orow["id"]),))
            conn.commit()

        if uploads_dir is not None:
            for fname in orphan_files:
                self._safe_unlink_upload(uploads_dir, fname)

        return {
            "sessions_pruned": s_cur.rowcount,
            "logs_pruned": r_cur.rowcount,
            "posters_pruned": len(orphan_files),
        }

    def export_user_vault(self, user_id: int) -> dict[str, Any]:
        """Exports portable, non-sensitive user concert & artist vault JSON (never exports password hashes or API secrets)."""
        user = self.get_user_by_id(user_id) or {}
        artists = self.list_artists(user_id)
        concerts = self.list_concerts(user_id)

        clean_artists = [
            {
                "name": a["name"],
                "aliases": a.get("aliases") or [],
                "genre": a.get("genre") or "",
                "region_origin": a.get("region_origin") or "",
                "apple_music_url": a.get("apple_music_url") or "",
                "auto_discover": bool(a.get("auto_discover", True)),
                "custom_rss_url": a.get("custom_rss_url") or "",
            }
            for a in artists
        ]
        clean_concerts = []
        for c in concerts:
            clean_concerts.append(
                {
                    "artist_name": c["artist_name"],
                    "title": c["title"],
                    "city": c["city"],
                    "region": c["region"],
                    "venue": c["venue"],
                    "show_time": c["show_time"],
                    "price_text": c["price_text"],
                    "platform": c["platform"],
                    "ticket_url": c["ticket_url"],
                    "status": c["status"],
                    "seat_note": c["seat_note"],
                    "checklist_want": c["checklist_want"],
                    "checklist_realname": c["checklist_realname"],
                    "checklist_alarm": c["checklist_alarm"],
                    "hotel_booked": c["hotel_booked"],
                    "rail_booked": c["rail_booked"],
                    "event_kind": c["event_kind"],
                    "festival_name": c["festival_name"],
                    "lineup": c.get("lineup") or [],
                    "approval_doc_no": c["approval_doc_no"],
                    "approval_source": c["approval_source"],
                    "actual_paid_yuan": c["actual_paid_yuan"],
                    "venue_rating": c["venue_rating"],
                    "seat_view_note": c["seat_view_note"],
                    "setlist_note": c["setlist_note"],
                    "source_type": c["source_type"],
                    "notes": c["notes"],
                    "ticket_rounds": [
                        {
                            "round_label": tr["round_label"],
                            "sale_time": tr["sale_time"],
                            "platform": tr["platform"],
                            "booking_url": tr["booking_url"],
                        }
                        for tr in (c.get("ticket_rounds") or [])
                    ],
                    "refund_tiers": [
                        {
                            "tier_label": rf["tier_label"],
                            "cutoff_time": rf["cutoff_time"],
                            "fee_percent": rf["fee_percent"],
                            "expect_return_drop": rf["expect_return_drop"],
                        }
                        for rf in (c.get("refund_tiers") or [])
                    ],
                }
            )
        return {
            "app": "LiveEcho",
            "schema_version": 2,
            "exported_at": int(time.time()),
            "preferences": {
                "preferred_region": user.get("preferred_region", "all"),
                "preferred_cities": user.get("preferred_cities") or [],
                "home_city": user.get("home_city", "上海"),
            },
            "artists": clean_artists,
            "concerts": clean_concerts,
        }

    # ---------------- Notification & Vision Settings ----------------

    def get_notification_settings_masked(self, user_id: int) -> dict[str, Any]:
        raw = self.get_notification_settings_decrypted(user_id)
        return {
            "browser_enabled": raw["browser_enabled"],
            "bark_configured": bool(raw["bark_url"]),
            "bark_url_masked": mask_secret(raw["bark_url"]),
            "serverchan_configured": bool(raw["serverchan_key"]),
            "serverchan_key_masked": mask_secret(raw["serverchan_key"]),
            "telegram_configured": bool(raw["telegram_bot_token"] and raw["telegram_chat_id"]),
            "telegram_bot_token_masked": mask_secret(raw["telegram_bot_token"]),
            "telegram_chat_id": raw["telegram_chat_id"],
            "webhook_configured": bool(raw["webhook_url"]),
            "webhook_url_masked": mask_secret(raw["webhook_url"]),
            "smtp_configured": bool(raw["smtp_host"] and raw["notify_email"]),
            "smtp_host": raw["smtp_host"],
            "smtp_port": raw["smtp_port"],
            "smtp_user_masked": mask_secret(raw["smtp_user"]),
            "smtp_pass_configured": bool(raw["smtp_pass"]),
            "notify_email_masked": mask_secret(raw["notify_email"]),
            "vision_api_configured": bool(raw["vision_api_key"]),
            "vision_api_key_masked": mask_secret(raw["vision_api_key"]),
            "lead_minutes": raw["lead_minutes"],
            "show_lead_hours": raw["show_lead_hours"],
            "enable_12306_reminders": raw["enable_12306_reminders"],
            "enable_return_sniper": raw["enable_return_sniper"],
        }

    def get_notification_settings_decrypted(self, user_id: int) -> dict[str, Any]:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM notification_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return {
                    "user_id": user_id,
                    "browser_enabled": True,
                    "bark_url": "",
                    "serverchan_key": "",
                    "telegram_bot_token": "",
                    "telegram_chat_id": "",
                    "webhook_url": "",
                    "smtp_host": "",
                    "smtp_port": 587,
                    "smtp_user": "",
                    "smtp_pass": "",
                    "notify_email": "",
                    "vision_api_key": "",
                    "lead_minutes": [60, 15, 5],
                    "show_lead_hours": [24, 3],
                    "enable_12306_reminders": True,
                    "enable_return_sniper": True,
                }
            return {
                "user_id": user_id,
                "browser_enabled": bool(row["browser_enabled"]),
                "bark_url": self.secret_box.decrypt(row["bark_url_enc"]),
                "serverchan_key": self.secret_box.decrypt(row["serverchan_key_enc"]),
                "telegram_bot_token": self.secret_box.decrypt(row["telegram_bot_token_enc"]),
                "telegram_chat_id": row["telegram_chat_id"],
                "webhook_url": self.secret_box.decrypt(row["webhook_url_enc"]),
                "smtp_host": row["smtp_host"],
                "smtp_port": int(row["smtp_port"] or 587),
                "smtp_user": row["smtp_user"],
                "smtp_pass": self.secret_box.decrypt(row["smtp_pass_enc"]),
                "notify_email": row["notify_email"],
                "vision_api_key": self.secret_box.decrypt(row["vision_api_key_enc"]),
                "lead_minutes": json.loads(row["lead_minutes_json"] or "[60, 15, 5]"),
                "show_lead_hours": json.loads(row["show_lead_hours_json"] or "[24, 3]"),
                "enable_12306_reminders": bool(row["enable_12306_reminders"]),
                "enable_return_sniper": bool(row["enable_return_sniper"]),
            }

    def update_notification_settings(self, user_id: int, payload: dict[str, Any]) -> None:
        current = self.get_notification_settings_decrypted(user_id)
        now = int(time.time())

        def resolve_secret(field_name: str, clear_flag: str) -> str:
            if payload.get(clear_flag):
                return ""
            val = (payload.get(field_name) or "").strip()
            return val if val else current[field_name]

        bark_url = resolve_secret("bark_url", "clear_bark")
        serverchan_key = resolve_secret("serverchan_key", "clear_serverchan")
        telegram_token = resolve_secret("telegram_bot_token", "clear_telegram")
        webhook_url = resolve_secret("webhook_url", "clear_webhook")
        smtp_pass = resolve_secret("smtp_pass", "clear_smtp_pass")
        vision_key = resolve_secret("vision_api_key", "clear_vision_key")

        telegram_chat_id = (
            ""
            if payload.get("clear_telegram")
            else (payload.get("telegram_chat_id") if "telegram_chat_id" in payload else current["telegram_chat_id"])
        ).strip()
        smtp_host = (payload.get("smtp_host") if "smtp_host" in payload else current["smtp_host"]).strip()
        smtp_port = int(payload.get("smtp_port") or current["smtp_port"] or 587)
        smtp_user = (payload.get("smtp_user") if "smtp_user" in payload else current["smtp_user"]).strip()
        notify_email = (payload.get("notify_email") if "notify_email" in payload else current["notify_email"]).strip()
        browser_enabled = bool(payload.get("browser_enabled", current["browser_enabled"]))
        enable_12306 = bool(payload.get("enable_12306_reminders", current["enable_12306_reminders"]))
        enable_sniper = bool(payload.get("enable_return_sniper", current["enable_return_sniper"]))

        lead_minutes = payload.get("lead_minutes", current["lead_minutes"])
        lead_minutes = sorted({max(1, min(10080, int(x))) for x in lead_minutes}, reverse=True)[:5] or [60, 15, 5]

        show_lead_hours = payload.get("show_lead_hours", current["show_lead_hours"])
        show_lead_hours = sorted({max(1, min(168, int(x))) for x in show_lead_hours}, reverse=True)[:4] or [24, 3]

        with self._lock, contextlib.closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO notification_settings (
                    user_id, browser_enabled, bark_url_enc, serverchan_key_enc,
                    telegram_bot_token_enc, telegram_chat_id, webhook_url_enc,
                    smtp_host, smtp_port, smtp_user, smtp_pass_enc, notify_email,
                    vision_api_key_enc, lead_minutes_json, show_lead_hours_json,
                    enable_12306_reminders, enable_return_sniper, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    browser_enabled = excluded.browser_enabled,
                    bark_url_enc = excluded.bark_url_enc,
                    serverchan_key_enc = excluded.serverchan_key_enc,
                    telegram_bot_token_enc = excluded.telegram_bot_token_enc,
                    telegram_chat_id = excluded.telegram_chat_id,
                    webhook_url_enc = excluded.webhook_url_enc,
                    smtp_host = excluded.smtp_host,
                    smtp_port = excluded.smtp_port,
                    smtp_user = excluded.smtp_user,
                    smtp_pass_enc = excluded.smtp_pass_enc,
                    notify_email = excluded.notify_email,
                    vision_api_key_enc = excluded.vision_api_key_enc,
                    lead_minutes_json = excluded.lead_minutes_json,
                    show_lead_hours_json = excluded.show_lead_hours_json,
                    enable_12306_reminders = excluded.enable_12306_reminders,
                    enable_return_sniper = excluded.enable_return_sniper,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    1 if browser_enabled else 0,
                    self.secret_box.encrypt(bark_url),
                    self.secret_box.encrypt(serverchan_key),
                    self.secret_box.encrypt(telegram_token),
                    telegram_chat_id,
                    self.secret_box.encrypt(webhook_url),
                    smtp_host,
                    smtp_port,
                    smtp_user,
                    self.secret_box.encrypt(smtp_pass),
                    notify_email,
                    self.secret_box.encrypt(vision_key),
                    json.dumps(lead_minutes),
                    json.dumps(show_lead_hours),
                    1 if enable_12306 else 0,
                    1 if enable_sniper else 0,
                    now,
                ),
            )
            conn.commit()

    def list_all_users_for_scheduler(self) -> list[int]:
        with self._lock, contextlib.closing(self._connect()) as conn:
            rows = conn.execute("SELECT id FROM users").fetchall()
            return [int(r["id"]) for r in rows]

    def has_reminder_been_sent(self, user_id: int, event_key: str, channel: str) -> bool:
        with self._lock, contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM reminder_logs WHERE user_id = ? AND event_key = ? AND channel = ?",
                (user_id, event_key, channel),
            ).fetchone()
            return row is not None

    def record_reminder_sent(self, user_id: int, event_key: str, channel: str, status: str = "sent") -> None:
        now = int(time.time())
        with self._lock, contextlib.closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO reminder_logs (user_id, event_key, channel, sent_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, event_key, channel, now, status),
            )
            conn.commit()
