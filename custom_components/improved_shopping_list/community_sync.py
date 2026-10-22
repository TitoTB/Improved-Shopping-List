"""Opt-in GitHub device authorization and durable daily community exchange."""

import asyncio
from copy import deepcopy
import json
import time
from datetime import timedelta

from aiohttp import ClientError, ClientTimeout
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DOMAIN, VERSION
from .community_data import (APP_URL, CLIENT_ID, REPO, SCHEMA, REFERENCE_VERSION, DAY,
    MARKER, MAX_BYTES, ean, normalized, fingerprint, price_fingerprint, pack, validate_product, validate_dictionary, scope)

DATA_URL = f"https://raw.githubusercontent.com/{REPO}/data/community/products.json"
API = f"https://api.github.com/repos/{REPO}"


class CommunityError(ValueError):
    """A safe message that never embeds OAuth responses or credentials."""


class CommunitySync:
    def __init__(self, hass, catalog, icons, prices, lookup):
        self.hass, self.catalog, self.icons, self.prices, self.lookup = hass, catalog, icons, prices, lookup
        self._store = Store(hass, 1, f"{DOMAIN}.community_account", private=True)
        self._cache = Store(hass, 1, f"{DOMAIN}.community_products")
        self._data = {"sharing": False, "credentials": {}, "last_download": 0, "last_upload": 0,
                      "next_attempt": 0, "last_download_attempt":0, "next_upload_attempt": 0, "outbox": None, "account": ""}
        self.dictionary = {"schema": SCHEMA, "reference_version": REFERENCE_VERSION, "generated_at": 0, "products": []}
        self._active = False
        self._lock = asyncio.Lock()
        self._auth = None
        self._task = None
        self._upload_requested = False
        self._device = None
        self._listeners = set()
        self._stop = None
        self._error = ""
        self._generation = 0

    async def async_load(self):
        saved = await self._store.async_load()
        if isinstance(saved, dict):
            self._data.update({key:deepcopy(saved[key]) for key in self._data if key in saved})
        try:
            cached = await self._cache.async_load()
            if cached:
                self.dictionary = validate_dictionary(cached, time.time())
                await self.prices.async_apply_revocations(self.dictionary.get("revoked_prices", []))
        except (ValueError, TypeError, KeyError):
            pass

    @property
    def snapshot(self):
        # Never expose access/refresh tokens, device_code, outbox or private account identifiers.
        device = self._device or {}
        return {"sharing": self._data["sharing"], "connected": bool(self._data["credentials"].get("access_token")),
                "account": self._data["account"], "last_download": self._data["last_download"],
                "last_upload": self._data["last_upload"], "error": self._error,
                "running": bool(self._task and not self._task.done()), "app_url": APP_URL,
                "authorization": {"user_code": device["user_code"], "verification_uri": "https://github.com/login/device"}
                    if device else None}

    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    def start(self):
        if self._active:
            return
        self._active = True
        self._stop = async_track_time_interval(self.hass, self._queue, timedelta(minutes=15))
        # First periodic tick downloads data; setup itself never requires GitHub.

    def _queue(self, *_args, immediate_upload=False):
        if not self._active:
            return
        self._upload_requested |= immediate_upload
        if self._task is None or self._task.done():
            self._task = self.hass.async_create_background_task(self._sync_queued(), "Shopping community daily sync")

    async def _sync_queued(self):
        while self._active:
            immediate = self._upload_requested
            self._upload_requested = False
            await self.async_sync(immediate_upload=immediate)
            if not self._upload_requested:
                return

    async def async_stop(self):
        self._active = False
        self._upload_requested = False
        self._generation += 1
        if self._stop:
            self._stop(); self._stop = None
        for task in (self._auth, self._task):
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self._device = None

    async def _request(self, method, url, *, token=None, data=None, limit=MAX_BYTES):
        # URLs are fixed by this module; contributor URLs are never fetched here.
        headers = {"Accept": "application/json", "User-Agent": f"ImprovedShoppingList/{VERSION}"}
        if token:
            headers["Authorization"] = "Bearer "+token
        async with async_get_clientsession(self.hass).request(method, url, json=data,
                headers=headers, timeout=ClientTimeout(total=20), allow_redirects=False) as response:
            if response.status == 401:
                raise CommunityError("La autorización de GitHub ha caducado o ha sido revocada. Vuelve a conectar.")
            if response.status not in (200, 201):
                raise CommunityError(f"GitHub no ha permitido la operación (HTTP {response.status}).")
            raw = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                raw.extend(chunk)
                if len(raw) > limit:
                    raise CommunityError("La respuesta comunitaria supera el tamaño permitido.")
            try:
                return json.loads(raw)
            except (ValueError, TypeError) as err:
                raise CommunityError("GitHub ha devuelto una respuesta no válida.") from err

    async def async_sharing(self, enabled):
        if not enabled:
            self._generation += 1
            if self._auth and not self._auth.done():
                self._auth.cancel()
                await asyncio.gather(self._auth, return_exceptions=True)
            # Cancel an upload before forgetting credentials; public reading can resume next cycle.
            if self._task and not self._task.done():
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            self._device = None
            self._upload_requested = False
            self._data.update(sharing=False, credentials={}, account="", outbox=None)
            self._error = ""
            await self._store.async_save(self._data)
            self._notify()
            return self.snapshot
        if self._data["credentials"].get("access_token"):
            self._data["sharing"] = True
            await self._store.async_save(self._data)
            self._notify()
            self._queue(immediate_upload=True)
            return self.snapshot
        if self._auth and not self._auth.done():
            return self.snapshot
        response = await self._request("POST", "https://github.com/login/device/code",
            data={"client_id": CLIENT_ID, "scope": "offline_access"}, limit=8192)
        if (not isinstance(response.get("device_code"), str) or not isinstance(response.get("user_code"), str)
            or type(response.get("interval")) is not int or not 5 <= response["interval"] <= 60
            or type(response.get("expires_in")) is not int or not 1 <= response["expires_in"] <= 1800):
            raise CommunityError("No se ha podido iniciar la autorización de GitHub. Comprueba que Device Flow esté habilitado.")
        self._data["sharing"] = True
        await self._store.async_save(self._data)
        self._device = {key:response[key] for key in ("device_code", "user_code", "interval", "expires_in")}
        self._error = ""
        generation = self._generation
        self._auth = self.hass.async_create_background_task(self._authorize(generation), "Shopping GitHub authorization")
        self._notify()
        return self.snapshot

    async def _authorize(self, generation):
        device = self._device
        deadline = time.monotonic()+device["expires_in"]
        interval = device["interval"]
        try:
            while self._active and generation == self._generation and time.monotonic() < deadline:
                await asyncio.sleep(interval)
                response = await self._request("POST", "https://github.com/login/oauth/access_token", data={
                    "client_id": CLIENT_ID, "device_code": device["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}, limit=8192)
                if response.get("error") == "authorization_pending":
                    continue
                if response.get("error") == "slow_down":
                    interval += 5
                    continue
                credentials = self._credentials(response)
                user = await self._request("GET", "https://api.github.com/user", token=credentials["access_token"], limit=65536)
                if not isinstance(user.get("login"), str) or type(user.get("id")) is not int:
                    raise CommunityError("GitHub no ha confirmado la cuenta autorizada.")
                if generation != self._generation or not self._active:
                    return
                self._data.update(credentials=credentials, account=user["login"])
                await self._store.async_save(self._data)
                self._queue(immediate_upload=True)
                return
            raise CommunityError("El código de autorización ha caducado. Activa de nuevo Compartir mis datos.")
        except (CommunityError, ClientError, TimeoutError, ValueError, OSError):
            if generation == self._generation:
                self._error = "No se ha completado la autorización. Comprueba la app y vuelve a conectar con GitHub."
        finally:
            if generation == self._generation:
                self._device = None
                self._notify()

    def _credentials(self, response):
        token, refresh = response.get("access_token"), response.get("refresh_token")
        if not isinstance(token, str) or not token.startswith("ghu_") or not isinstance(refresh, str) or not refresh.startswith("ghr_"):
            raise CommunityError("GitHub no ha concedido la autorización esperada.")
        expires = response.get("expires_in")
        if type(expires) is not int or not 60 <= expires <= 86400:
            raise CommunityError("La caducidad de la autorización no es válida.")
        return {"access_token": token, "refresh_token": refresh, "expires_at": time.time()+expires}

    async def _access_token(self):
        credentials = self._data["credentials"]
        if credentials.get("expires_at", 0) <= time.time()+60:
            response = await self._request("POST", "https://github.com/login/oauth/access_token", data={
                "client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": credentials.get("refresh_token", "")}, limit=8192)
            credentials = self._credentials(response)
            self._data["credentials"] = credentials
            # Persist rotation before any subsequent upload uses it.
            await self._store.async_save(self._data)
        return credentials["access_token"]

    def find(self, product=None, *, code=None, query=None):
        codes = {ean(code)} if code else {ean(c) for c in [product.get("barcode", ""), *product.get("barcodes", [])]} if product else set()
        codes.discard("")
        links = (product or {}).get("store_links", {})
        matches = [item for item in self.dictionary["products"] if codes.intersection(item.get("eans", [])) or any(
            item.get("store_links", {}).get(store, {}).get("id") == link["id"] for store, link in links.items())]
        if not matches and query:
            matches = [item for item in self.dictionary["products"] if normalized(query) in
                (normalized(item.get("name", "")), normalized(item.get("name_en", "")))]
        return deepcopy(matches[0]) if len(matches) == 1 else None

    def product_hint(self, code):
        item = self.find(code=code)
        if not item or "name" not in item["confirmed_fields"]:
            return None
        result = {"status": "found", "name": item["name"], "common_name": item["name"], "source": "community"}
        if "nutriscore" in item["confirmed_fields"] and item["nutriscore"]:
            result["nutriscore"] = {"grade": item["nutriscore"], "checked_at": self.dictionary["generated_at"], "source": "community"}
        return result

    def price(self, store, link):
        if not self._prices_enabled:
            return None
        for item in self.dictionary["products"]:
            for price in item["prices"]:
                if (price["store"] == store and price["reference_id"] == link["id"] and price["checked_at"] >= time.time()-DAY
                    and price_fingerprint(price) not in self.dictionary.get("revoked_prices", [])):
                    return {**deepcopy(price), "store": store, "url": link["url"], "source": "community", "scope": scope(store)}
        return None

    async def async_prepare_prices(self):
        """A store batch first consumes the daily dictionary, without uploading yet."""
        if not self._prices_enabled or not self._download_due():
            return
        await self.async_sync(upload=False)

    @property
    def _prices_enabled(self):
        settings=getattr(self.prices,"settings",None)
        return settings.snapshot.get("price_updates_enabled",True) if settings else True

    @property
    def _period(self):
        settings=getattr(self.prices,"settings",None)
        return DAY*(settings.snapshot.get("price_update_days",1) if settings else 1)

    def _download_due(self):
        attempt=self._data.get("last_download_attempt") or max(0,self._data["next_attempt"]-DAY)
        return time.time() >= max(self._data["last_download"],attempt)+self._period

    def suggestions(self, query):
        matches = [item for item in self.dictionary["products"] if normalized(query) in
            (normalized(item.get("name", "")), normalized(item.get("name_en", "")))]
        unique = {}
        for item in matches:
            for icon in item["icons"]:
                previous = unique.get(icon["id"])
                if previous is None or icon["confirmations"] > previous["confirmations"]:
                    unique[icon["id"]] = icon
        return [{**icon, "id": "shared:"+icon["id"], "label": query, "collection": "Comunidad",
            "preview_url": f"https://api.iconify.design/{icon['id'].replace(':', '/')}.svg?height=96"}
            for icon in sorted(unique.values(), key=lambda i:(-i.get("selections", i["confirmations"]), -i["confirmations"], i["id"]))[:5]]

    async def async_import(self, identifier):
        identifier = identifier.removeprefix("shared:")
        if not any(icon["id"] == identifier for item in self.dictionary["products"] for icon in item["icons"]):
            raise CommunityError("El icono comunitario ya no está disponible.")
        asset = await self.icons.async_import(identifier)
        asset["community_origin"] = True
        assets = {**self.icons._assets, asset["url"]: asset}
        await self.icons._store.async_save({"assets": assets})
        self.icons._assets = assets
        return deepcopy(asset)

    def payload(self):
        products = []
        now = time.time()
        for product in self.catalog.products:
            borrowed = product.get("community_fields", {})
            def local(field, value):
                return borrowed.get(field) != fingerprint(value)
            links = {store:link for store,link in product.get("store_links", {}).items() if local("store_links."+store, link)}
            codes = sorted({ean(c) for c in [product.get("barcode", ""), *product.get("barcodes", [])] if ean(c)})
            item = {"name": product["name"], "name_en": product.get("name_en", ""),
                    "eans": codes, "store_links": links, "icons": [], "prices": [], "nutriscore": "",
                    "borrowed_fields": [field for field, digest in borrowed.items()
                        if field in ("name", "name_en") and digest == fingerprint(product.get(field, ""))]}
            asset = self.icons._assets.get(product.get("image_url", ""), {})
            if asset:
                item["icons"] = [asset["id"]] if ":" in asset.get("id", "") else []
                if asset.get("community_origin"):
                    item["borrowed_fields"].append("icons")
            for code in codes:
                hint = self.lookup.cached(code) or {}
                if hint.get("source") != "community":
                    item["nutriscore"] = (hint.get("nutriscore") or {}).get("grade", "")
                    if item["nutriscore"]:
                        break
            for price in (self.prices.prices_for(product) if self._prices_enabled else []):
                if (price.get("source") not in ("community", "receipt") and price.get("checked_at", 0) >= now-DAY
                    and price["store"] in product.get("store_links", {})):
                    # Include the reference needed to validate a fresh, independently fetched price.
                    item["store_links"][price["store"]] = product["store_links"][price["store"]]
                    if not local("store_links."+price["store"], product["store_links"][price["store"]]):
                        item["borrowed_fields"].append("store_links."+price["store"])
                    item["prices"].append({key:price[key] for key in ("store", "reference_id", "price", "currency", "checked_at")})
            try:
                products.append(validate_product(item, now))
            except (ValueError, TypeError):
                continue
        return {"schema": SCHEMA, "reference_version": REFERENCE_VERSION, "products": products}

    async def _upload(self):
        if not self._data["sharing"] or not self._data["credentials"] or time.time() < self._data["last_upload"]+DAY:
            return
        token = await self._access_token()
        outbox = self._data["outbox"]
        if not outbox:
            manifest, parts = pack(self.payload())
            outbox = {"manifest": manifest, "parts": parts, "issue": None, "sent": 0, "created_at": time.time()}
            self._data["outbox"] = outbox
            await self._store.async_save(self._data)
        if outbox["issue"] is None:
            # Recover an accepted POST whose response was lost before retrying.
            issues = await self._request("GET", API+"/issues?state=all&creator="+self._data["account"]+"&per_page=10", token=token)
            title = "[ISL community] "+outbox["manifest"]["digest"]
            existing = next((issue for issue in issues if issue.get("title") == title and issue.get("body", "").startswith(MARKER)), None)
            issue = existing or await self._request("POST", API+"/issues", token=token,
                data={"title": title, "body": MARKER+json.dumps(outbox["manifest"], separators=(",", ":"))})
            outbox["issue"] = int(issue["number"])
            await self._store.async_save(self._data)
        # Reconcile comments before retrying an ambiguous network/storage outcome.
        comments = await self._request("GET", API+f"/issues/{outbox['issue']}/comments?per_page=100", token=token)
        existing_parts = {comment.get("body", "") for comment in comments}
        for index in range(outbox["sent"], len(outbox["parts"])):
            body = MARKER+json.dumps({"digest": outbox["manifest"]["digest"], "part": index, "data": outbox["parts"][index]}, separators=(",", ":"))
            if body not in existing_parts:
                await self._request("POST", API+f"/issues/{outbox['issue']}/comments", token=token, data={"body": body})
            outbox["sent"] = index+1
            await self._store.async_save(self._data)
        self._data.update(last_upload=time.time(), outbox=None)
        await self._store.async_save(self._data)

    async def async_sync(self, *, upload=True, immediate_upload=False):
        async with self._lock:
            if not self._active:
                return
            # Consent sends the current catalog without waiting for a public download or store batch.
            download_due = not immediate_upload and self._download_due()
            upload_due = (upload and self._data["sharing"] and self._data["credentials"]
                and (immediate_upload or not self.prices._data["pending"] and not self.prices._preparing)
                and time.time() >= max(self._data["last_upload"]+self._period, self._data["next_upload_attempt"]))
            if not download_due and not upload_due:
                return
            self._error = ""
            try:
                if download_due:
                    self._data["last_download_attempt"] = time.time()
                    self._data["next_attempt"] = time.time()+self._period
                    await self._store.async_save(self._data)
                    data = validate_dictionary(await self._request("GET", DATA_URL, limit=16*1024*1024), time.time())
                    await self._cache.async_save(data)
                    self.dictionary = data
                    await self.prices.async_apply_revocations(data.get("revoked_prices", []))
                    self._data["last_download"] = time.time()
                    await self._store.async_save(self._data)
                    await self.catalog.async_apply_community(self)
                self.prices._notify()
                if upload_due:
                    # Multipart retries resume the same issue; they never create a second daily batch.
                    self._data["next_upload_attempt"] = time.time()+(900 if self._data["outbox"] else DAY)
                    await self._store.async_save(self._data)
                    await self._upload()
            except (ClientError, TimeoutError, OSError, ValueError, TypeError, KeyError):
                # Never log response bodies, token values, catalog payloads or OAuth parameters.
                self._error = "No se ha completado la sincronización comunitaria. Se conserva la información local; se reintentará en el próximo ciclo diario."
            finally:
                self._notify()
