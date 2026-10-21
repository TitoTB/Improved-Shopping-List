"""Durable daily pending-list price queue; all UI reads use the last known cache."""

import asyncio
from copy import deepcopy
from datetime import timedelta
import logging
import time

import aiohttp
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .catalog import normalized_name
from .const import DOMAIN
from .price_sources import PriceError, PriceSources
from .store_links import STORES, normalize_link

INTERVAL = 300
_LOGGER = logging.getLogger(__name__)


class PriceManager:
    def __init__(self, hass, catalog, settings, activity):
        self.hass, self.catalog, self.settings, self.activity = hass, catalog, settings, activity
        self.sources = PriceSources(hass)
        self._store = Store(hass, 1, f"{DOMAIN}.prices")
        self._data = {"offers":{}, "attempts":{}, "pending":[], "day":"", "next_request":0,
            "errors":{}, "blocked_day":{}, "blocked_until":{}, "legacy_ean":{}, "total":0, "processed":0,
            "partial":False, "prepare_retry_at":0}
        self._active = False
        self._lock = asyncio.Lock()
        self._task = None
        self._stops, self._listeners = [], set()
        self._configuration = None

    async def async_load(self):
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not all(isinstance(data.get(key), dict) for key in ("offers", "attempts")) or not isinstance(data.get("pending"), list):
                raise ValueError("No se pudo leer la cola de precios guardada.")
            self._data.update(data)
            # Remove the retired provider from durable work without touching other prices.
            migrated = False
            for name in ("offers", "attempts", "legacy_ean"):
                previous = self._data[name]
                self._data[name] = {key:value for key,value in previous.items() if not key.startswith("lidl:")}
                migrated |= self._data[name] != previous
            for name in ("errors", "blocked_day", "blocked_until"):
                if "lidl" in self._data[name]:
                    del self._data[name]["lidl"]
                    migrated = True
            previous = self._data["pending"]
            self._data["pending"] = [job for job in previous if job.get("store") != "lidl"]
            removed = len(previous)-len(self._data["pending"])
            if removed:
                self._data["processed"] += removed
                migrated = True
            if migrated:
                await self._save()
            return
        # Migrate prices locally. Neither of these legacy services is started.
        legacy = await Store(self.hass, 1, f"{DOMAIN}.store_products").async_load()
        for key, entry in (legacy or {}).get("offers", {}).items():
            offer = entry.get("offer") or {}
            if offer.get("store_product_id"):
                try:
                    link = normalize_link("mercadona", str(offer["store_product_id"]))
                except ValueError:
                    continue
                scope = key.split(":", 1)[0]
                price = {**offer, "store":"mercadona", "reference_id":link["id"], "url":link["url"],
                    "checked_at":entry.get("checked_at", 0), "scope":scope}
                self._data["offers"][self.key("mercadona", link, scope)] = price
                if offer.get("ean"):
                    self._data["legacy_ean"]["mercadona:"+str(offer["ean"]).zfill(14)] = price
        feed = await Store(self.hass, 1, f"{DOMAIN}.carrefour").async_load()
        for key, item in (feed or {}).get("products", {}).items():
            self._data["legacy_ean"]["carrefour:"+key] = {**item, "store":"carrefour", "store_name":item.get("name", ""),
                "url":item.get("affiliate_url", ""), "checked_at":(feed or {}).get("checked_at", 0), "source":"legacy_feed"}
        await self._save()

    async def _save(self):
        await self._store.async_save(deepcopy(self._data))

    def scope(self, store):
        config = self.settings.snapshot["stores"].get(store, {})
        if store in ("consum", "lasirena"):
            return f"{config['postal_code']}:{config['area_id']}" if config.get("postal_code") and config.get("area_id") else ""
        return config.get("warehouse", "") if store == "mercadona" else config.get("region_id", "") if store == "alcampo" else config.get("sale_point", "005290")

    @staticmethod
    def key(store, link, scope):
        return f"{store}:{scope}:{link['id']}"

    def links_for_product(self, product):
        links = {store:deepcopy(link) for store,link in product.get("store_links", {}).items() if store in STORES}
        # Preserve exact EAN associations already discovered by the former service.
        if "store_links" not in product and "mercadona" not in links:
            for code in [product.get("barcode", ""), *product.get("barcodes", [])]:
                old = self._data["legacy_ean"].get("mercadona:"+code.zfill(14))
                if code and old and old.get("scope") == self.scope("mercadona"):
                    links["mercadona"] = normalize_link("mercadona", str(old["reference_id"]))
                    break
        return links

    def prices_for(self, product):
        prices = []
        links = self.links_for_product(product)
        for store, link in links.items():
            price = self._data["offers"].get(self.key(store, link, self.scope(store)))
            if price:
                prices.append({**deepcopy(price), "catalog_product_id":product.get("id"), "name":product.get("name", ""),
                    "error":self._data["errors"].get(store, "")})
        for store in STORES:
            if store in links:
                continue
            for code in [product.get("barcode", ""), *product.get("barcodes", [])]:
                price = self._data["legacy_ean"].get(store+":"+code.zfill(14)) if code else None
                if price and (store != "mercadona" or price.get("scope") == self.scope(store)):
                    prices.append({**deepcopy(price), "catalog_product_id":product.get("id"), "name":product.get("name", ""),
                        "error":self._data["errors"].get(store, "")})
                    break
        return prices

    def snapshot(self, store=None):
        settings = self.settings.snapshot
        products = [price for product in self.catalog.products for price in self.prices_for(product)
                    if (store is None or price["store"] == store)]
        pending = self._data["pending"]
        return {"products":products, "nightly":True, "update_time":settings.get("price_update_time", "01:00"),
            "sale_point":self.scope(store) if store == "carrefour" else None,
            "enabled":bool(settings["stores"].get(store, {}).get("enabled")) if store else True,
            "warehouse":self.scope(store) if store else "", "error":self._data["errors"].get(store, "") if store else "",
            "remaining":len(pending), "processed":self._data["processed"], "total":self._data["total"],
            "next_request":self._data["next_request"] if pending else None, "retry_at":0,
            "automatic_refresh_blocked":False, "running":bool(pending), "not_found":0}

    @property
    def progress(self):
        running = bool(self._data["pending"])
        remaining = len(self._data["pending"]) + sum(1 for job in self._data["pending"]
            if job.get("store") == "lasirena" and not job.get("reserved"))
        return {"running":running, "total":self._data["total"], "processed":self._data["processed"],
            "errors":deepcopy(self._data["errors"]),
            "last_updated":max((offer.get("checked_at", 0) for offer in self._data["offers"].values()), default=0),
            "started_at":self._data.get("started_at", time.time()), "phase":"waiting" if running else "processed",
            "estimated_seconds":max(0, self._data["next_request"]-time.time())+max(0, remaining-1)*INTERVAL if running else 0}

    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._stops = [async_track_time_interval(self.hass, self._queue, timedelta(minutes=1))]
        self._queue()

    @callback
    def _queue(self, *_args):
        if self._active and (not self._task or self._task.done()):
            self._task = self.hass.async_create_background_task(self._run_tick(), "Shopping prices queue")

    async def _run_tick(self):
        try:
            await self.async_tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Could not advance nightly shopping price queue")

    async def async_stop(self):
        self._active = False
        for stop in self._stops:
            stop()
        self._stops = []
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def pending_names(self):
        names = set()
        failures = []
        for entity in self.settings.snapshot["entities"]:
            state = self.hass.states.get(entity)
            if not state or state.state in ("unknown", "unavailable"):
                failures.append(entity)
                continue
            try:
                response = await self.hass.services.async_call("todo", "get_items", {"entity_id":entity,
                    "status":["needs_action"]}, blocking=True, return_response=True)
                items = response[entity]["items"]
                if not isinstance(items, list):
                    raise ValueError("Invalid todo response")
                names.update(normalized_name(item["summary"]) for item in items
                    if item.get("status") == "needs_action" and isinstance(item.get("summary"), str))
            except Exception:
                failures.append(entity)
        return names, failures

    async def _prepare(self, day):
        if not any(self.settings.snapshot["stores"].get(store, {}).get("enabled") for store in STORES):
            return
        names, failures = await self.pending_names()
        jobs = {}
        for job in self._data["pending"]:
            if (job.get("manual") or failures and self._data["day"] == day) and self._linked_job(job):
                jobs[self.key(job["store"],job["link"],job["scope"])] = job
        for product in self.catalog.products:
            if normalized_name(product["name"]) not in names:
                continue
            for store, link in self.links_for_product(product).items():
                if self.settings.snapshot["stores"].get(store, {}).get("enabled"):
                    scope = self.scope(store)
                    key = self.key(store, link, scope)
                    if self._data["attempts"].get(key) != day:
                        jobs.setdefault(key, {"store":store, "link":link, "scope":scope})
        pending = sorted(jobs.values(), key=lambda job:self._data["offers"].get(self.key(job["store"], job["link"], job["scope"]), {}).get("checked_at", 0))
        processed = self._data["processed"] if self._data["day"] == day else 0
        self._data.update(day=day, pending=pending, total=processed+len(pending), processed=processed,
            started_at=self._data.get("started_at", time.time()) if processed else time.time(),
            partial=bool(failures), prepare_retry_at=time.time()+INTERVAL)
        await self._save()
        self.activity.record("stores.queue", "Revisión nocturna de precios preparada", source="automatic",
            diagnostics={"references":len(pending), "interval_seconds":INTERVAL, "unavailable_lists":failures})
        self._notify()

    async def async_refresh_store(self, store):
        """Queue a deliberate manual run without bypassing durable HTTP pacing."""
        async with self._lock:
            if not self._active or not self.hass.data.get(DOMAIN, {}).get("active"):
                raise ValueError("La integración no está disponible.")
            if not self.settings.snapshot["stores"].get(store, {}).get("enabled"):
                raise ValueError("Habilita la tienda antes de actualizar sus precios.")
            if store in ("mercadona", "consum", "lasirena") and not self.scope(store):
                raise ValueError(f"Configura el código postal de {STORES[store]} antes de actualizar.")
            if time.time() < self._data["blocked_until"].get(store, 0):
                raise ValueError("La tienda ha indicado una pausa. Espera antes de volver a actualizar.")
            active = [job for job in self._data["pending"] if job["store"] == store and not job.get("blocked")]
            if active:
                return {**self.snapshot(store), "queued":len(active)}
            blocked = [job for job in self._data["pending"] if job["store"] == store and job.get("blocked")]
            for job in blocked:
                self._data["pending"].remove(job)
                self._data["processed"] += 1
            names, failures = await self.pending_names()
            if failures:
                raise ValueError("No se pudieron leer todas las listas. Comprueba su disponibilidad y vuelve a intentarlo.")
            jobs = {}
            for product in self.catalog.products:
                link = self.links_for_product(product).get(store)
                if link and normalized_name(product["name"]) in names:
                    scope = self.scope(store)
                    key = self.key(store, link, scope)
                    jobs[key] = {"store":store, "link":link, "scope":scope, "manual":True}
            existing = {self.key(job["store"],job["link"],job["scope"]):job for job in self._data["pending"]}
            added = 0
            for key, job in jobs.items():
                # Repeated clicks cannot restart an active run or replay reserved requests.
                if key not in existing:
                    self._data["pending"].append(job)
                    added += 1
            if not self._data["pending"]:
                return {**self.snapshot(store), "queued":0}
            if len(self._data["pending"]) == added:
                self._data.update(total=added, processed=0, started_at=time.time())
            else:
                self._data["total"] += added
            await self._save()
            self.activity.record("stores.queue", f"{STORES[store]}: actualización manual solicitada", source="manual",
                diagnostics={"references":len(jobs), "added":added, "interval_seconds":INTERVAL})
            self._notify()
        self._queue()
        return {**self.snapshot(store), "queued":len(jobs)}

    def _current_job(self, job, names):
        return (self._linked_job(job) and any(
                normalized_name(product["name"]) in names and self.links_for_product(product).get(job["store"]) == job["link"]
                for product in self.catalog.products))

    def _linked_job(self, job):
        return (self._active and self.hass.data.get(DOMAIN, {}).get("active")
            and self.settings.snapshot["stores"].get(job["store"], {}).get("enabled")
            and self.scope(job["store"]) == job["scope"] and any(
                self.links_for_product(product).get(job["store"]) == job["link"]
                for product in self.catalog.products))

    async def _reserve_request(self):
        delay = max(0, self._data["next_request"]-time.time())
        if delay:
            await asyncio.sleep(delay)
        entry, generation, configuration, job = self._configuration
        if (not self._active or self.settings.entry is not entry or self.settings._generation != generation
            or self.settings.snapshot["stores"].get(job["store"]) != configuration):
            raise PriceError("La configuración ha cambiado; consulta cancelada.", response_class="configuration_changed")
        names, failures = await self.pending_names()
        if not self._current_job(job, names):
            raise PriceError("No se pudo confirmar la lista; consulta aplazada." if failures else "El producto ya no está pendiente; consulta omitida.",
                response_class="list_unavailable" if failures else "no_longer_pending")
        self._data["attempts"][self.key(job["store"],job["link"],job["scope"])] = dt_util.now().date().isoformat()
        job["reserved"] = True
        self._data["next_request"] = time.time()+INTERVAL
        await self._save()  # Persist request reservation before touching the retailer.
        self._notify()
        self.activity.record("stores.request", f"{STORES[job['store']]}: consulta de precio iniciada",
            source="manual" if job.get("manual") else "automatic", store=STORES[job["store"]],
            diagnostics={"reference_id":job["link"]["id"], "scope":job["scope"],
                "provider":"carrefour_json" if job["store"] == "carrefour" else job["store"]})

    async def async_tick(self):
        async with self._lock:
            if not self._active or not self.hass.data.get(DOMAIN, {}).get("active"):
                return
            now = dt_util.now()
            day = now.date().isoformat()
            hour, minute = map(int, self.settings.snapshot.get("price_update_time", "01:00").split(":"))
            elapsed = now.hour*60+now.minute-hour*60-minute
            if (self._data["day"] != day or self._data["partial"] and time.time() >= self._data["prepare_retry_at"]) and 0 <= elapsed < 60:
                await self._prepare(day)
            if not self._data["pending"] or time.time() < self._data["next_request"]:
                return
            names, failures = await self.pending_names()
            deferred = 0
            while self._data["pending"] and deferred < len(self._data["pending"]):
                job = self._data["pending"][0]
                store = job["store"]
                key = self.key(store, job["link"], job["scope"])
                if failures and self._linked_job(job) and not self._current_job(job, names):
                    self._data["pending"].append(self._data["pending"].pop(0))
                    deferred += 1
                    continue
                if (not self._current_job(job, names) or job.get("reserved") or job.get("blocked")
                    or not job.get("manual") and (self._data["attempts"].get(key) == day or self._data["blocked_day"].get(store) == day)
                    or time.time() < self._data["blocked_until"].get(store, 0)):
                    self._data["pending"].pop(0)
                    self._data["processed"] += 1
                    await self._save()
                    self._notify()
                    continue
                entry, generation = self.settings.entry, self.settings._generation
                configuration = deepcopy(self.settings.snapshot["stores"][store])
                source = "manual" if job.get("manual") else "automatic"
                self._configuration = (entry, generation, configuration, job)
                try:
                    result = await self.sources.fetch(store, job["link"], configuration, self._reserve_request)
                    if (self.settings.entry is not entry or self.settings._generation != generation
                        or self.settings.snapshot["stores"].get(store) != configuration or not self._linked_job(job)):
                        result = "discarded"
                    if isinstance(result, dict):
                        self._data["offers"][key] = {**result, "checked_at":time.time(), "scope":job["scope"]}
                        self._data["errors"].pop(store, None)
                        self.activity.record("stores.price", f"{STORES[store]}: precio actualizado", source=source,
                            diagnostics={"reference_id":job["link"]["id"], "price":result["price"], "currency":result["currency"]})
                    elif result is None:
                        self.activity.record("stores.not_found", f"{STORES[store]}: referencia no disponible; se conserva el último precio", source=source,
                            diagnostics={"reference_id":job["link"]["id"], "response_class":"not_found"})
                except (PriceError, aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, TypeError) as err:
                    diagnostics = getattr(err, "diagnostics", {"response_class":"invalid_response"})
                    if diagnostics.get("response_class") == "list_unavailable":
                        await self._save()
                        return
                    if diagnostics.get("response_class") in ("configuration_changed", "no_longer_pending"):
                        self._data["pending"].pop(0)
                        self._data["processed"] += 1
                        await self._save()
                        self._notify()
                        return
                    self._data["errors"][store] = str(err) if isinstance(err, PriceError) else f"{STORES[store]}: no se pudo consultar. Se conserva el último precio."
                    if diagnostics.get("http_status") in (403, 429):
                        self._data["blocked_day"][store] = day
                        self._data["blocked_until"][store] = time.time()+diagnostics.get("retry_seconds", 0)
                        for queued in self._data["pending"]:
                            if queued["store"] == store:
                                queued["blocked"] = True
                    self.activity.record("stores.error", self._data["errors"][store], source=source, store=STORES[store],
                        diagnostics={**diagnostics, "reference_id":job["link"]["id"], "next_attempt":"next_daily_run"})
                finally:
                    self._configuration = None
                self._data["pending"].pop(0)
                self._data["processed"] += 1
                await self._save()
                self._notify()
                return  # At most one product per tick; redirects share the same 5-minute reservation.


class StorePriceView:
    """Compatibility adapter: opening or refreshing a popup is a cache-only read."""
    def __init__(self, manager, store):
        self.manager, self.store = manager, store

    def snapshot(self):
        return self.manager.snapshot(self.store)

    @property
    def progress(self):
        return {**self.manager.progress, "warehouse":self.manager.scope(self.store)}

    def subscribe(self, callback):
        return self.manager.subscribe(callback)

    async def async_refresh(self, force=False):
        return self.snapshot()
