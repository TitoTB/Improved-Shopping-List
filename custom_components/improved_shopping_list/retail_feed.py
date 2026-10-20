"""Periodic credential-free Carrefour feed downloads from the public data branch."""

import asyncio
from datetime import datetime, timedelta
import json
import re
import time

import aiohttp
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .feed_protocol import apply_delta, check_descriptor, digest, gtin, read_snapshot, snapshot

ROOT = "https://raw.githubusercontent.com/TitoTB/Improved-Shopping-List/data/carrefour/"
INTERVAL = 24 * 3600


class RetailFeed:
    def __init__(self, hass, catalog, settings, activity):
        self.hass, self.catalog, self.settings, self.activity = hass, catalog, settings, activity
        self._store = Store(hass, 1, f"{DOMAIN}.carrefour")
        self._data = {"version": "", "products": {}, "checked_at": 0, "generated_at": "", "etag": ""}
        self.error = ""
        self._lock = asyncio.Lock()
        self._task = None
        self._stops = []
        self._retry_at = 0

    async def async_load(self):
        data = await self._store.async_load()
        if data:
            try:
                products = read_snapshot(snapshot(list(data["products"].values())))
                if digest(snapshot(list(products.values()))) != data["version"]:
                    raise ValueError("Invalid stored feed")
                self._data = {**data, "products": products}
            except (ValueError, KeyError, TypeError):
                self.error = "La copia guardada de Carrefour no es válida; se volverá a descargar."

    def enabled(self):
        return bool(self.settings.snapshot["stores"].get("carrefour", {}).get("enabled"))

    def snapshot(self):
        matches = {}
        if self.enabled():
            for product in self.catalog.products:
                for code in [product.get("barcode", ""), *product.get("barcodes", [])]:
                    try:
                        key = gtin(code)
                    except ValueError:
                        continue
                    if key in self._data["products"]:
                        matches[key] = dict(self._data["products"][key])
        return {"enabled": self.enabled(), "products": list(matches.values()), "version": self._data["version"],
            "checked_at": self._data["checked_at"], "generated_at": self._data["generated_at"], "error": self.error,
            "stale": bool(self._data["checked_at"] and time.time()-self._data["checked_at"] > 2*INTERVAL)}

    @callback
    def start(self):
        self._stops = [self.settings.subscribe(self._schedule),
            async_track_time_interval(self.hass, lambda now: self._schedule(), timedelta(seconds=INTERVAL))]
        self._schedule()

    @callback
    def _schedule(self):
        if self.enabled() and self.hass.data.get(DOMAIN, {}).get("active") and (not self._task or self._task.done()):
            self._task = self.hass.async_create_background_task(self.async_refresh(), "Improved Shopping List Carrefour")

    async def async_stop(self):
        for stop in self._stops:
            stop()
        self._stops = []
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _get(self, path, headers=None, missing_ok=False):
        if path != "manifest.json":
            if not re.fullmatch(r"(?:snapshots|deltas)/[a-f0-9]{64}\.json", path):
                raise ValueError("Ruta de catálogo no válida.")
        async with async_get_clientsession(self.hass).get(ROOT+path, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30), allow_redirects=False) as response:
            if response.status == 304:
                return None, response.headers.get("ETag", "")
            if response.status == 404 and missing_ok:
                raise FileNotFoundError("El catálogo de Carrefour todavía no se ha publicado.")
            if response.status != 200:
                raise ValueError(f"No se pudo descargar Carrefour (HTTP {response.status}).")
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                body.extend(chunk)
                if len(body) > (65536 if path == "manifest.json" else 16*1024*1024):
                    raise ValueError("El catálogo supera el tamaño permitido.")
            return bytes(body), response.headers.get("ETag", "")

    async def _content(self, reference):
        check_descriptor(reference)
        raw, _ = await self._get(reference["path"])
        if raw is None or len(raw) != reference["bytes"] or digest(raw) != reference["sha256"]:
            raise ValueError("La comprobación de integridad de Carrefour ha fallado.")
        return raw

    async def async_refresh(self, force=False):
        async with self._lock:
            if not self.enabled() or not self.hass.data.get(DOMAIN, {}).get("active"):
                return self.snapshot()
            if not force and time.time()-self._data["checked_at"] < INTERVAL:
                return self.snapshot()
            if not force and time.time() < self._retry_at:
                return self.snapshot()
            entry, generation = self.settings.entry, self.settings._generation
            try:
                raw, etag = await self._get("manifest.json", {"If-None-Match":self._data["etag"]} if self._data["etag"] else {}, missing_ok=True)
                data = dict(self._data)
                if raw is None and not data["version"]:
                    raise ValueError("Carrefour devolvió una caché que todavía no existe localmente.")
                if raw is not None:
                    manifest = json.loads(raw)
                    if (not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("store") != "carrefour"
                        or not isinstance(manifest.get("version"), str) or not re.fullmatch(r"[a-f0-9]{64}", manifest["version"])
                        or not isinstance(manifest.get("generated_at"), str) or len(manifest["generated_at"]) > 80):
                        raise ValueError("El manifiesto de Carrefour no es válido.")
                    if datetime.fromisoformat(manifest["generated_at"]).utcoffset() is None:
                        raise ValueError("La fecha del catálogo de Carrefour no es válida.")
                    if manifest["version"] != data["version"]:
                        products = None
                        delta = manifest.get("delta")
                        if isinstance(delta, dict) and delta.get("base_version") == data["version"]:
                            try:
                                ref = {key:delta[key] for key in ("path","sha256","bytes")}
                                products = apply_delta(data["products"], await self._content(ref), data["version"], manifest["version"])
                            except (ValueError, KeyError, TypeError):
                                products = None
                        if products is None:
                            snapshot_raw = await self._content(manifest["snapshot"])
                            products = read_snapshot(snapshot_raw)
                            if digest(snapshot(list(products.values()))) != manifest["version"]:
                                raise ValueError("La versión del catálogo de Carrefour no coincide.")
                        if len(products) != manifest.get("products_count"):
                            raise ValueError("El número de productos de Carrefour no coincide.")
                        data.update(products=products, version=manifest["version"])
                    data["generated_at"] = manifest["generated_at"]
                if not self.enabled() or self.settings.entry is not entry or self.settings._generation != generation or not self.hass.data.get(DOMAIN, {}).get("active"):
                    return self.snapshot()
                data.update(checked_at=time.time(), etag=etag or data["etag"])
                await self._store.async_save(data)
                self._data, self.error = data, ""
                self._retry_at = 0
                self.activity.record("stores.feed_updated", "Carrefour: catálogo comprobado", store="Carrefour",
                    diagnostics={"version":data["version"],"products":len(data["products"]),"checked_at":data["checked_at"]})
            except (ValueError, TypeError, KeyError, OSError, aiohttp.ClientError, asyncio.TimeoutError, HomeAssistantError) as err:
                self._retry_at = time.time()+300
                self.error = str(err) if isinstance(err, (ValueError, FileNotFoundError)) else "No se pudo actualizar Carrefour. Se conserva la copia anterior."
                self.activity.record("stores.error", self.error, store="Carrefour")
            return self.snapshot()
