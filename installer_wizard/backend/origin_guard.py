import ipaddress
import json
import logging
import os
import socket
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urlsplit

log = logging.getLogger("nuxiva.security.origin_guard")

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOOPBACK_NAMES = frozenset({"localhost", "nuxiva.local", "nuxiva", "testserver"})

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers") or ():
        if key == name:
            return value.decode("latin-1")
    if name == b"host":
        for key, value in scope.get("headers") or ():
            if key == b":authority":
                return value.decode("latin-1")
    return ""


def _hostname(authority: str) -> str:
    if not authority:
        return ""
    if "://" in authority:
        return (urlsplit(authority).hostname or "").lower()
    return (urlsplit(f"//{authority}").hostname or "").lower()


def _origin_hostname(origin: str) -> str:
    if not origin or origin == "null":
        return ""
    return (urlsplit(origin).hostname or "").lower()


def _is_ip(name: str) -> bool:
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def _machine_names() -> frozenset[str]:
    host = socket.gethostname().strip().lower()
    return frozenset({host, f"{host}.local"} if host else ())


def _clean_host(h: str) -> str:
    h = h.strip().lower()
    if not h:
        return ""
    if h == "*" or h.startswith("*."):
        return h
    return _hostname(h) or h


class OriginGuard:

    def __init__(self, app, extra_hosts: Iterable[str] = ()) -> None:
        self.app = app
        cleaned_extra = {_clean_host(h) for h in extra_hosts if h and _clean_host(h)}
        self.trusted = set(LOOPBACK_NAMES | _machine_names() | cleaned_extra)
        allow_all_env = os.environ.get("NUXIVA_ALLOW_ALL_HOSTS", "").lower() in ("1", "true", "yes", "on")
        is_docker = os.environ.get("NUXIVA_CONTAINER", "").lower() in ("1", "true", "yes", "on")
        if not is_docker:
            try:
                import machine
                is_docker = bool(machine.is_container())
            except Exception:
                pass
        if allow_all_env or (is_docker and not cleaned_extra):
            self.trusted.add("*")

    def host_allowed(self, host: str) -> bool:
        if not host:
            return False
        if "*" in self.trusted:
            return True
        if host in self.trusted or _is_ip(host) or host.endswith(".local"):
            return True
        for t in self.trusted:
            if t.startswith("*.") and (host == t[2:] or host.endswith(t[1:])):
                return True
        return False

    def verdict(self, scope: Scope) -> str:
        if scope.get("type") != "http":
            return ""
        host = _hostname(_header(scope, b"host"))
        if host and not self.host_allowed(host):
            return "untrusted_host"
        raw_fwd = _header(scope, b"x-forwarded-host")
        forwarded_host = _hostname(raw_fwd.split(",")[0].strip()) if raw_fwd else ""
        if forwarded_host and not self.host_allowed(forwarded_host):
            return "untrusted_host"
        if scope.get("method", "GET").upper() not in UNSAFE:
            return ""
        fetch_site = _header(scope, b"sec-fetch-site").lower()
        if fetch_site == "cross-site":
            return "cross_site"
        origin = _header(scope, b"origin")
        if origin:
            orig_host = _origin_hostname(origin)
            effective_hosts = {h for h in (host, forwarded_host) if h}
            if orig_host not in effective_hosts and not (
                self.host_allowed(orig_host) and any(self.host_allowed(h) for h in effective_hosts)
            ):
                return "foreign_origin"
        return ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        reason = self.verdict(scope)
        if not reason:
            await self.app(scope, receive, send)
            return
        host = _hostname(_header(scope, b"host"))
        raw_fwd = _header(scope, b"x-forwarded-host")
        origin = _header(scope, b"origin")
        log.warning(
            "🔴 [ORIGIN GUARD] Rifiutata richiesta HTTP per host non autorizzato (%s):\n"
            "🔴   Host: %r | X-Forwarded-Host: %r | Origin: %r\n"
            "🔴   Trusted hosts: %r\n"
            "🔴   Aggiungi il tuo dominio in NUXIVA_ALLOWED_HOSTS (es. NUXIVA_ALLOWED_HOSTS=%s) nello stack Portainer.",
            reason,
            host,
            raw_fwd,
            origin,
            sorted(list(self.trusted)),
            host or raw_fwd or "jar.ghome.it",
        )
        body = json.dumps({"detail": "Richiesta rifiutata per sicurezza", "code": f"security.{reason}"}).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
