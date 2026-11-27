"""Security primitives: secret loading, bcrypt auth, Fernet encryption, CSRF, rate limiting, and SSRF protection."""

from __future__ import annotations

import base64
import collections
import hashlib
import hmac
import http.cookiejar
import ipaddress
import logging
import os
import secrets
import socket
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

import bcrypt
import requests
import requests.adapters
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("concert_tracker.security")

# TODO(security): Integrate OAuth 2.0 / OpenID Connect providers for federated login when deployed multi-user.
# TODO(security): Add WebAuthn / TOTP multi-factor authentication (MFA) option for internet-exposed deployments.
# TODO(security): Add k-anonymity leaked-password check (e.g., HaveIBeenPwned range API) during registration.


def load_master_secret(data_dir: Path) -> bytes:
    """Multi-tiered secret resolution without hardcoded defaults.

    Order:
    1. CONCERT_TRACKER_SECRET_KEY environment variable (required when CONCERT_TRACKER_ENV=production).
    2. Local restricted file data/.secret_key (0600) outside static web root for persistent local vaults.
    3. Cryptographically random ephemeral key with warning.
    """
    env_secret = os.getenv("CONCERT_TRACKER_SECRET_KEY", "").strip()
    if env_secret:
        if len(env_secret) < 32:
            raise RuntimeError("CONCERT_TRACKER_SECRET_KEY must be at least 32 characters long.")
        return env_secret.encode("utf-8")

    if os.getenv("CONCERT_TRACKER_ENV", "").lower() == "production":
        # Fail closed in production if KMS/environment secret is absent.
        raise RuntimeError(
            "CONCERT_TRACKER_SECRET_KEY must be set in production (use KMS or secret manager; never store prod secrets on disk)."
        )

    secret_file = data_dir / ".secret_key"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        if secret_file.exists():
            raw = secret_file.read_text(encoding="utf-8").strip()
            if len(raw) >= 64:
                return raw.encode("utf-8")
        generated = secrets.token_hex(32)
        fd = os.open(str(secret_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(generated)
        logger.warning(
            "Generated local instance secret in %s (0600). Set CONCERT_TRACKER_SECRET_KEY for multi-instance deployments.",
            secret_file,
        )
        return generated.encode("utf-8")
    except OSError:
        logger.warning("Generating ephemeral in-memory secret. Instance-isolated; sessions will reset on restart!")
        return secrets.token_hex(32).encode("utf-8")


class SecretBox:
    """Encrypts and decrypts notification credentials at rest using Fernet."""

    def __init__(self, master_secret: bytes) -> None:
        digest = hashlib.sha256(b"concert-tracker-fernet-v1:" + master_secret).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        clean = (plaintext or "").strip()
        if not clean:
            return ""
        return self._fernet.encrypt(clean.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            logger.error("Failed to decrypt stored credential; secret key may have rotated.")
            return ""


def mask_secret(value: str) -> str:
    """Masks sensitive strings (webhook URLs, tokens, emails) for safe UI display."""
    clean = (value or "").strip()
    if not clean:
        return ""
    if "@" in clean and not clean.startswith("http"):
        local, _, domain = clean.partition("@")
        prefix = local[:1] if local else "*"
        return f"{prefix}***@{domain}"
    if len(clean) <= 8:
        return "••••••••"
    return f"••••••••{clean[-4:]}"


def validate_password_strength(password: str) -> str | None:
    """Validates password length (8..128) while allowing all Unicode and special characters."""
    if not isinstance(password, str):
        return "Password must be a string."
    if len(password) < 8:
        return "Password must be at least 8 characters long (12+ recommended)."
    if len(password) > 128:
        return "Password must not exceed 128 characters."
    if password.strip() == "":
        return "Password cannot consist solely of whitespace."
    return None


def hash_password(password: str) -> str:
    """Hashes a password using bcrypt with a unique per-user salt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Verifies a candidate password against its bcrypt hash."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def hash_session_token(raw_token: str) -> str:
    """Hashes session tokens before storing in SQLite so DB snapshots never expose raw session IDs."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_csrf_token(expected: str, provided: str) -> bool:
    """Constant-time comparison for Synchronizer CSRF tokens."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)


class SlidingWindowRateLimiter:
    """Thread-safe in-memory rate limiter with automatic empty-bucket eviction."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, collections.deque[float]] = {}
        self._ops = 0

    @property
    def tracked_key_count(self) -> int:
        with self._lock:
            return len(self._hits)

    def prune(self, max_idle_seconds: float = 600.0) -> int:
        now = time.monotonic()
        cutoff = now - max_idle_seconds
        removed = 0
        with self._lock:
            stale_keys = [k for k, dq in self._hits.items() if not dq or dq[-1] <= cutoff]
            for k in stale_keys:
                del self._hits[k]
                removed += 1
        return removed

    def allow(self, key: str, limit: int, window_seconds: float) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            self._ops += 1
            if self._ops % 256 == 0 and len(self._hits) > 128:
                idle_cutoff = now - max(window_seconds * 2.0, 300.0)
                for stale_k in [k for k, q in self._hits.items() if not q or q[-1] <= idle_cutoff]:
                    del self._hits[stale_k]

            dq = self._hits.get(key)
            if dq is not None:
                while dq and dq[0] <= cutoff:
                    dq.popleft()
                if not dq:
                    del self._hits[key]
                    dq = None

            if dq is not None and len(dq) >= limit:
                retry_after = max(1, int(window_seconds - (now - dq[0])))
                return False, retry_after

            if dq is None:
                dq = collections.deque()
                self._hits[key] = dq
            dq.append(now)
            return True, 0


def _is_disallowed_ip(ip_str: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_str)
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_outbound_https_url(url: str) -> str:
    """Validates an outbound URL against SSRF: enforces HTTPS and blocks private/internal IPs."""
    parsed = urllib.parse.urlsplit((url or "").strip())
    if parsed.scheme != "https":
        raise ValueError("Outbound URLs must use https://.")
    if not parsed.hostname:
        raise ValueError("Outbound URL is missing a valid hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in outbound URLs are not permitted.")

    port = parsed.port or 443
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname: {parsed.hostname}") from exc

    if not infos:
        raise ValueError(f"No DNS records found for hostname: {parsed.hostname}")

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        if _is_disallowed_ip(ip_str):
            raise ValueError("Outbound requests to private, loopback, or internal network addresses are blocked.")

    return urllib.parse.urlunsplit(parsed)


_HTTP_SESSION_LOCK = threading.Lock()
_POOLED_HTTP_SESSION: requests.Session | None = None


def _get_pooled_http_session() -> requests.Session:
    """Returns a connection-pooled HTTPS session with cookie persistence disabled."""
    global _POOLED_HTTP_SESSION
    with _HTTP_SESSION_LOCK:
        if _POOLED_HTTP_SESSION is None:
            sess = requests.Session()
            sess.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
            adapter = requests.adapters.HTTPAdapter(pool_connections=12, pool_maxsize=16, max_retries=0)
            sess.mount("https://", adapter)
            _POOLED_HTTP_SESSION = sess
        return _POOLED_HTTP_SESSION


def safe_https_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    data: dict[str, Any] | None = None,
    timeout: float = 6.0,
    max_redirects: int = 2,
) -> requests.Response:
    """Performs an HTTPS request with SSRF DNS validation on initial URL and every redirect hop."""
    method_upper = method.upper()
    if method_upper not in ("GET", "POST"):
        raise ValueError("Only GET and POST outbound methods are allowed.")

    current_url = validate_outbound_https_url(url)
    req_headers = {"User-Agent": "LiveEchoConcertTracker/2.1"}
    if headers:
        req_headers.update(headers)

    session = _get_pooled_http_session()
    for _ in range(max_redirects + 1):
        resp = session.request(
            method_upper,
            current_url,
            headers=req_headers,
            params=params,
            json=json_body,
            data=data,
            timeout=timeout,
            allow_redirects=False,
        )
        params = None  # Only attach query params on the initial hop
        if resp.is_redirect and resp.headers.get("Location"):
            next_url = urllib.parse.urljoin(current_url, resp.headers["Location"])
            current_url = validate_outbound_https_url(next_url)
            method_upper = "GET"
            json_body = None
            data = None
            continue
        return resp

    raise ValueError("Too many redirects on outbound HTTPS request.")
