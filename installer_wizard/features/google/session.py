import asyncio
import time

import httpx

from features.google.accounts import accounts
from features.google.app import oauth
from features.google.constants import log
from features.google.data import GoogleData
from features.google.errors import GoogleApiError, explain

RETRY_STATUS = {429, 500, 502, 503, 504}
RETRIES = 2
BACKOFF = 0.8
TIMEOUT = httpx.Timeout(15.0, connect=6.0)


class Session(GoogleData):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.access_token = ""
        self.expires_at = 0.0
        self.unread: int | None = None
        self.status = "collegato"
        self._refresh_lock = asyncio.Lock()

    @property
    def info(self) -> dict:
        return accounts.get(self.slug) or {}

    def granted(self) -> list[str]:
        return accounts.granted(self.info)

    def ready(self, service: str) -> bool:
        info = self.info
        return bool(info.get("refresh")) and not info.get("revoked") and service in accounts.granted(info)

    async def _access(self, force: bool = False) -> str:
        if not force and self.access_token and time.time() < self.expires_at:
            return self.access_token
        async with self._refresh_lock:
            if not force and self.access_token and time.time() < self.expires_at:
                return self.access_token
            refresh = self.info.get("refresh", "")
            if not refresh:
                raise GoogleApiError(401, "not_linked", "Account Google non collegato")
            try:
                body = await oauth.token({"grant_type": "refresh_token", "refresh_token": refresh})
            except ValueError as exc:
                if "ricollega" in str(exc):
                    accounts.put(self.slug, {"revoked": True})
                    self.status = "da ricollegare"
                raise
            self.access_token = body["access_token"]
            self.expires_at = time.time() + int(body.get("expires_in", 3600)) - 60
            changes: dict = {"revoked": False}
            returned = set(str(body.get("scope") or "").split())
            stored = set(self.info.get("scopes") or [])
            if returned - stored:
                changes["scopes"] = sorted(stored | returned)
            missing = stored - returned
            if returned and missing:
                log.info("Google (%s): il rinnovo non elenca %s, li verifico alla prima risposta dell'API", self.slug, ", ".join(sorted(missing)))
            accounts.put(self.slug, changes)
            return self.access_token

    async def verify_scopes(self) -> list[str]:
        token = await self._access()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": token})
        if r.status_code != 200:
            raise explain(r)
        scopes = sorted(set(str(r.json().get("scope") or "").split()))
        if scopes:
            accounts.put(self.slug, {"scopes": scopes})
        return scopes

    async def _call(self, method: str, url: str, **kw) -> dict:
        renewed = False
        attempt = 0
        while True:
            token = await self._access(force=renewed)
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kw)
            if r.status_code == 401 and not renewed:
                self.access_token, renewed = "", True
                continue
            if r.status_code in RETRY_STATUS and attempt < RETRIES:
                attempt += 1
                wait = _retry_after(r) or BACKOFF * (2 ** (attempt - 1))
                log.info("Google %s %s: %s, nuovo tentativo tra %.1fs", method, url.split("?")[0], r.status_code, wait)
                await asyncio.sleep(min(wait, 8.0))
                continue
            if r.status_code >= 400:
                error = explain(r)
                if error.reason == "scope_missing":
                    await self._recheck_scopes()
                raise error
            return r.json() if r.content else {}

    async def _recheck_scopes(self) -> None:
        try:
            before = set(accounts.granted(self.info))
            await self.verify_scopes()
            lost = before - set(accounts.granted(self.info))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Google (%s): permessi non verificati: %s", self.slug, exc)
            return
        if lost:
            log.warning("Google (%s): Google non concede più %s", self.slug, ", ".join(sorted(lost)))

    async def _get(self, url: str, **params) -> dict:
        return await self._call("GET", url, params=params or None)


def _retry_after(r: httpx.Response) -> float:
    try:
        return max(0.0, float(r.headers.get("retry-after", "")))
    except ValueError:
        return 0.0
