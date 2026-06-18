from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


BLOCKED_PORTS = {22, 23, 25, 53, 110, 143, 3306, 5432, 6379, 8000, 8080, 9090, 27017}
ALLOWED_PORTS = {443}
SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "bearer",
    "key",
    "password",
    "secret",
    "token",
}


class UnsafeURL(ValueError):
    """Raised when a user-supplied URL is not safe for public relay checks."""


@dataclass(frozen=True)
class SafeURL:
    normalized: str
    public: str
    url_hash: str
    hostname: str


def stable_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def mask_secret(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return f"{text[:2]}...{text[-2:]}"
    return f"{text[:4]}...{text[-4:]}"


def fingerprint_secret(value: str | None) -> str:
    text = (value or "").strip()
    return stable_hash(text) if text else ""


def _is_blocked_hostname(hostname: str) -> bool:
    lower = hostname.lower().strip(".")
    if lower in {"localhost", "localhost.localdomain"}:
        return True
    if lower.endswith(".localhost"):
        return True
    return False


def _is_blocked_ip(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def normalize_public_https_url(raw_url: str, *, allow_path: bool = True) -> SafeURL:
    text = (raw_url or "").strip()
    if not text:
        raise UnsafeURL("URL is required.")
    if "://" not in text:
        text = f"https://{text}"

    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    if scheme != "https":
        raise UnsafeURL("Only HTTPS URLs are allowed.")
    if not parsed.hostname:
        raise UnsafeURL("URL host is required.")

    hostname = parsed.hostname.lower().strip(".")
    if _is_blocked_hostname(hostname) or _is_blocked_ip(hostname):
        raise UnsafeURL("Target host is not allowed.")

    port = parsed.port
    if port is not None and (port not in ALLOWED_PORTS or port in BLOCKED_PORTS):
        raise UnsafeURL("Target port is not allowed.")

    path = parsed.path or ""
    if not allow_path:
        path = ""
    if path and not path.startswith("/"):
        path = f"/{path}"

    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    for key, _ in query_pairs:
        if key.strip().lower() in SENSITIVE_QUERY_KEYS:
            raise UnsafeURL("Sensitive credentials are not allowed in URL query parameters.")

    normalized_query = urlencode(sorted(query_pairs))
    netloc = hostname if port in (None, 443) else f"{hostname}:{port}"
    normalized = urlunsplit((scheme, netloc, path or "", normalized_query, ""))
    public = urlunsplit((scheme, netloc, path or "", "", ""))
    return SafeURL(
        normalized=normalized,
        public=public,
        url_hash=stable_hash(normalized),
        hostname=hostname,
    )


def redact_url_for_public(raw_url: str) -> str:
    return normalize_public_https_url(raw_url, allow_path=True).public
