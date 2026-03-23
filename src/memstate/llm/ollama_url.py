"""Validate and normalize Ollama base URLs (client overrides)."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse, urlunparse

from memstate.config import Settings


def _format_netloc(host: str, port: int, username: str | None, password: str | None) -> str:
    userinfo = ""
    if username is not None:
        userinfo = username
        if password is not None:
            userinfo += ":" + password
        userinfo += "@"
    try:
        ip = ipaddress.ip_address(host)
        hostpart = f"[{host}]" if isinstance(ip, ipaddress.IPv6Address) else host
    except ValueError:
        hostpart = host
    return f"{userinfo}{hostpart}:{port}"


def normalize_ollama_base_url(url: str) -> str:
    """Strip trailing slash; default HTTP port to 11434 (Ollama) when omitted."""
    raw = url.strip().rstrip("/")
    p = urlparse(raw)
    if p.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not p.hostname:
        raise ValueError("URL must include a host")
    host = p.hostname
    port = p.port
    if port is None:
        port = 443 if p.scheme == "https" else 11434
    netloc = _format_netloc(host, port, p.username, p.password)
    return urlunparse((p.scheme, netloc, p.path or "", "", "", "")).rstrip("/")


def _host_allowed(host: str, settings: Settings) -> bool:
    if settings.ollama_allow_remote:
        return True
    h = host.lower()
    if h in ("localhost", "127.0.0.1", "::1", "host.docker.internal"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return False


def validate_client_ollama_url(url: str, settings: Settings) -> str:
    """Normalize URL from client; reject disallowed hosts unless ollama_allow_remote."""
    norm = normalize_ollama_base_url(url)
    p = urlparse(norm)
    assert p.hostname is not None
    if not _host_allowed(p.hostname, settings):
        raise ValueError(
            "Ollama host not allowed (use localhost, 127.0.0.1, private LAN IP, "
            "or host.docker.internal; or set MEMSTATE_OLLAMA_ALLOW_REMOTE=1)"
        )
    return norm
