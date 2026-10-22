"""Durable daily pending-list price queue; all UI reads use the last known cache."""

import asyncio
from copy import deepcopy
from datetime import date, timedelta
import logging
import re
from uuid import uuid4
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
from .regional_stores import valid_area
from .community_data import price_fingerprint

INTERVAL = 300
_LOGGER = logging.getLogger(__name__)


class PriceManager:
    def __init__(self, hass, catalog, settings, activity):
        self.hass, self.catalog, self.settings, self.activity = hass, catalog, settings, activity
        self.sources = PriceSources(hass)
        self._store = Store(hass, 1, f"{DOMAIN}.prices")
        self._data = {"offers":{}, "attempts":{}, "pending":[], "day":"", "next_request":0,
            "errors":{}, "blocked_day":{}, "blocked_until":{}, "legacy_ean":{}, "total":0, "processed":0,
            "partial":False, "prepare_retry_at":0, "batch":None, "offer_history":{}}
        self._active = False
        self._lock = asyncio.Lock()
        self._task = None
        self._stops, self._listeners = [], set()
        self._configuration = None
        self._preparing = 0

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

    def _begin_batch(self, source):
        batch = self._data.get("batch")
        if batch and batch.get("finished_at") is not None and not batch.get("logged"):
            raise OSError("El resumen de la revisión anterior está pendiente de guardar en Logs.")
        if not batch or batch.get("finished_at") is not None:
            batch = {"id":str(uuid4()), "source":source, "started_at":time.time(),
                "finished_at":None, "events":[], "stores":{}}
            self._data["batch"] = batch
            self._data["errors"] = {}
            if not self._data["pending"]:
                self._data.update(total=0,processed=0,started_at=batch["started_at"])
        elif source == "manual":
            batch["source"] = "manual"
        return batch

    @staticmethod
    def _error_message(store, message):
        name = STORES[store]
        return name+": "+re.sub(r"^(?:"+re.escape(name)+r"(?::\s*|\s+))+", "",str(message),flags=re.I)

    def _record(self, kind, message, *, source="automatic", store=None, diagnostics=None):
        batch = self._begin_batch(source)
        diagnostics = deepcopy(diagnostics or {})
        key = next((key for key,name in STORES.items() if store in (key,name)
            or str(message).lower().startswith(name.lower()+":")),None)
        if key is None and store is None:
            key = next((key for key,name in STORES.items() if str(message).lower().startswith(name.lower())),None)
        if key:
            configuration = self.settings.snapshot["stores"].get(key,{})
            batch["stores"][key] = {"name":STORES[key],"postal_code":configuration.get("postal_code",""),
                "reference_postal_code":configuration.get("postal_code",""),"scope":self.scope(key)}
        batch["events"].append({"kind":kind,"source":source,"time":time.time(),"store":key,"message":str(message),"diagnostics":diagnostics})

    async def _save(self):
        batch = self._data.get("batch")
        finished = bool(batch and batch.get("finished_at") is None and not self._data["pending"] and not self._preparing)
        if finished:
            batch["finished_at"] = time.time()
        try:
            await self._store.async_save(deepcopy(self._data))
        except BaseException:
            if finished:
                batch["finished_at"] = None
            raise
        if batch and batch.get("finished_at") is not None and not batch.get("logged"):
            counts = {"updated":0,"not_found":0,"errors":0,"skipped":0,"http_requests":0}
            mapping = {"stores.price":"updated","stores.not_found":"not_found","stores.error":"errors",
                "stores.skipped":"skipped","stores.request":"http_requests"}
            for event in batch["events"]:
                counter = mapping.get(event["kind"])
                if counter:
                    counts[counter] += 1
            stores = deepcopy(batch["stores"])
            for store in stores:
                stores[store]["totals"] = {key:sum(1 for event in batch["events"] if event["store"] == store
                    and mapping.get(event["kind"]) == key) for key in counts}
            logged = await self.activity.async_record_durable("stores.summary",
                f'Actualización de precios finalizada: {counts["updated"]} actualizados · {counts["not_found"]} sin resultado · {counts["errors"]} incidencias',
                entry_id=f'price-batch:{batch["id"]}',source=batch["source"],diagnostics={"batch_id":batch["id"],"started_at":batch["started_at"],
                    "finished_at":batch["finished_at"],"elapsed_seconds":round(batch["finished_at"]-batch["started_at"],2),
                    "interval_seconds":INTERVAL, "totals":counts,"stores":stores,"events":deepcopy(batch["events"])})
            if logged:
                batch["logged"] = True
                try:
                    await self._store.async_save(deepcopy(self._data))
                except BaseException:
                    batch["logged"] = False
                    raise

    def scope(self, store):
        config = self.settings.snapshot["stores"].get(store, {})
        if store in ("consum", "lasirena", "eroski", "dia"):
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
        if not self.prices_enabled:
            return []
        prices = []
        links = self.links_for_product(product)
        for store, link in links.items():
            price = self._data["offers"].get(self.key(store, link, self.scope(store)))
            community = getattr(self, "community", None)
            if community and (not price or price.get("checked_at", 0) < time.time()-86400):
                price = community.price(store, link) or price
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
        receipts = getattr(self,"receipts",None)
        for price in receipts.offers_for(product) if receipts else []:
            previous = next((p for p in prices if p["store"] == price["store"]),None)
            if previous is None or price["checked_at"] > previous.get("checked_at",0):
                prices = [p for p in prices if p["store"] != price["store"]]
                prices.append(price)
        return prices

    async def async_apply_revocations(self, revoked):
        """Withdraw only community observations; never touch directly fetched prices."""
        keys = set(revoked)
        if not keys:
            return
        async with self._lock:
            changed = False
            for key, price in list(self._data["offers"].items()):
                if price.get("source") != "community" or price_fingerprint(price) not in keys:
                    continue
                history = self._data["offer_history"].get(key, [])
                previous = next((old for old in reversed(history) if old.get("source") != "community" or price_fingerprint(old) not in keys), None)
                if previous:
                    self._data["offers"][key] = deepcopy(previous)
                else:
                    del self._data["offers"][key]
                changed = True
            if changed:
                await self._store.async_save(deepcopy(self._data))
                self._notify()

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
        running = bool(self._data["pending"] or self._preparing)
        batch = self._data.get("batch") or {}
        remaining = sum(max(0, job.get("expected_requests", self.sources.expected_requests(job.get("store"),
            self.settings.snapshot["stores"].get(job.get("store"), {})))
            - job.get("request_count", 0)) for job in self._data["pending"] if not job.get("blocked"))
        return {"running":running, "total":self._data["total"], "processed":self._data["processed"],
            "errors":deepcopy(self._data["errors"]),
            "batch_id":batch.get("id"),"finished_at":batch.get("finished_at"),
            "log_pending":batch.get("finished_at") is not None and not batch.get("logged",False),
            "last_updated":max((offer.get("checked_at", 0) for offer in self._data["offers"].values()), default=0),
            "started_at":self._data.get("started_at", time.time()), "phase":"preparing" if self._preparing else "waiting" if running else "processed",
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
        if hasattr(self.settings,"subscribe"):
            self._stops.append(self.settings.subscribe(self._settings_changed))
        self._queue()

    @property
    def prices_enabled(self):
        return self.settings.snapshot.get("price_updates_enabled",True)

    @callback
    def _settings_changed(self):
        self._notify()
        self._queue()

    def _schedule_due(self, now):
        _, scheduled=self._schedule_window(now)
        try:
            return (scheduled-date.fromisoformat(self._data["day"])).days >= self.settings.snapshot.get("price_update_days",1)
        except ValueError:
            return True

    def _schedule_window(self, now):
        hour, minute=map(int,self.settings.snapshot.get("price_update_time","01:00").split(":"))
        elapsed=(now.hour*60+now.minute-hour*60-minute)%1440
        return elapsed,(now-timedelta(minutes=elapsed)).date()

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
        self.sources.close()

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
        if not self.prices_enabled:
            return
        if not any(self.settings.snapshot["stores"].get(store, {}).get("enabled") for store in STORES):
            return
        self._begin_batch("automatic")
        names, failures = await self.pending_names()
        unavailable = set()
        if failures:
            self._record("stores.error","No se pudieron comprobar algunas listas",source="automatic",
                diagnostics={"response_class":"list_unavailable","entities":failures})
        stores = {store for product in self.catalog.products if normalized_name(product["name"]) in names
            for store in self.links_for_product(product)
            if self.settings.snapshot["stores"].get(store, {}).get("enabled")}
        for store in sorted(stores):
            try:
                await self._ensure_location(store)
            except ValueError as err:
                unavailable.add(store)
                self._data["errors"][store] = self._error_message(store,err)
                self._record("stores.error", self._data["errors"][store], source="automatic",
                    store=STORES[store], diagnostics={"response_class":"location_unavailable",**getattr(err,"diagnostics",{})})
        jobs = {}
        for job in self._data["pending"]:
            if (job.get("manual") or failures and self._data["day"] == day) and self._linked_job(job):
                jobs[self.key(job["store"],job["link"],job["scope"])] = job
        for product in self.catalog.products:
            if normalized_name(product["name"]) not in names:
                continue
            for store, link in self.links_for_product(product).items():
                if store not in unavailable and self.settings.snapshot["stores"].get(store, {}).get("enabled"):
                    scope = self.scope(store)
                    key = self.key(store, link, scope)
                    if self._data["attempts"].get(key) != day:
                        jobs.setdefault(key, {"store":store, "link":link, "scope":scope})
        pending = sorted(jobs.values(), key=lambda job:self._data["offers"].get(self.key(job["store"], job["link"], job["scope"]), {}).get("checked_at", 0))
        processed = self._data["processed"] if self._data["day"] == day else 0
        self._data.update(day=day, pending=pending, total=processed+len(pending), processed=processed,
            started_at=self._data.get("started_at", time.time()) if processed else time.time(),
            partial=bool(failures), prepare_retry_at=time.time()+INTERVAL)
        self._record("stores.queue", "Revisión nocturna de precios preparada", source="automatic",
            diagnostics={"references":len(pending), "interval_seconds":INTERVAL, "unavailable_lists":failures})
        await self._save()
        self._notify()

    async def _ensure_location(self, store):
        if store not in ("mercadona", "consum", "lasirena", "eroski", "dia"):
            return
        config = self.settings.snapshot["stores"].get(store, {})
        ready = bool(self.scope(store))
        if store != "mercadona":
            ready = ready and valid_area(store, config.get("area_id"))
            if store == "consum":
                ready = ready and config.get("zone") == config["area_id"][:-1]
            elif store == "eroski":
                ready = ready and bool(config.get("zone"))
        if not ready or config.get("location_error"):
            config = await self.settings.async_ensure_store_location(store)
        if config.get("location_error"):
            raise PriceError(self._error_message(store,config["location_error"]),
                **{"response_class":"location_unavailable",**config.get("location_diagnostics",{})})
        if not self.scope(store):
            raise ValueError(f"No se ha podido resolver la ubicación de {STORES[store]}.")

    async def async_refresh_store(self, store):
        if not self.prices_enabled:
            raise ValueError("Activa la actualización de precios en Ajustes → Tiendas.")
        try:
            return await self._queue_store(store)
        except (ValueError,OSError) as err:
            async with self._lock:
                if self._active and self.hass.data.get(DOMAIN,{}).get("active"):
                    if (self._data.get("batch") or {}).get("finished_at") is not None and not self._data["batch"].get("logged"):
                        raise
                    self._begin_batch("manual")
                    message = self._error_message(store,err)
                    self._data["errors"][store] = message
                    self._record("stores.error",message,source="manual",store=STORES[store],
                        diagnostics={**getattr(err,"diagnostics",{}),"stage":"preparation"})
                    await self._save();self._notify()
            raise

    async def async_refresh_all(self):
        """Prepare one manual batch, including stores whose preparation fails."""
        if not self.prices_enabled:
            raise ValueError("Activa la actualización de precios en Ajustes → Tiendas.")
        if not self._active or not self.hass.data.get(DOMAIN,{}).get("active"):
            raise ValueError("La integración no está disponible.")
        if self._data["pending"] or self._preparing:
            return self._resume_result()
        community = getattr(self, "community", None)
        if community:
            await community.async_prepare_prices()
        stores = [store for store in STORES if self.settings.snapshot["stores"].get(store,{}).get("enabled")]
        errors,queued = [],0
        async with self._lock:
            if self._data["pending"] or self._preparing:
                return self._resume_result()
            await self._save()
            self._begin_batch("manual")
            self._preparing += 1
        try:
            for store in stores:
                try:
                    result = await self.async_refresh_store(store)
                    queued += result.get("queued",0)
                except (ValueError,OSError) as err:
                    errors.append({"store":store,"error":self._error_message(store,err)})
        finally:
            async with self._lock:
                self._preparing -= 1
                await self._save();self._notify()
        self._queue()
        return {"queued":queued,"errors":errors}

    def _resume_result(self):
        """A reload or another client observes the same run, including an in-flight request."""
        return {"resumed":True, "queued":len(self._data["pending"]),
            "errors":[{"store":store,"error":error} for store,error in self._data["errors"].items()],
            "progress":self.progress}

    async def _queue_store(self, store):
        """Queue a deliberate manual run without bypassing durable HTTP pacing."""
        async with self._lock:
            if not self.prices_enabled:
                raise ValueError("La actualización de precios está desactivada.")
            if not self._active or not self.hass.data.get(DOMAIN, {}).get("active"):
                raise ValueError("La integración no está disponible.")
            if (self._data.get("batch") or {}).get("finished_at") is not None and not self._data["batch"].get("logged"):
                await self._save()
            if not self.settings.snapshot["stores"].get(store, {}).get("enabled"):
                raise ValueError("Habilita la tienda antes de actualizar sus precios.")
            active = [job for job in self._data["pending"] if job["store"] == store and not job.get("blocked")]
            if active:
                return {**self.snapshot(store), "queued":len(active)}
            names, failures = await self.pending_names()
            if failures:
                raise ValueError("No se pudieron leer todas las listas. Comprueba su disponibilidad y vuelve a intentarlo.")
            candidates = [self.links_for_product(product)[store] for product in self.catalog.products
                if normalized_name(product["name"]) in names and store in self.links_for_product(product)]
            if not candidates:
                return {**self.snapshot(store), "queued":0}
            if time.time() < self._data["blocked_until"].get(store, 0):
                raise ValueError("La tienda ha indicado una pausa. Espera antes de volver a actualizar.")
            self._begin_batch("manual")
            await self._ensure_location(store)
            self._data["errors"].pop(store,None)
            blocked = [job for job in self._data["pending"] if job["store"] == store and job.get("blocked")]
            for job in blocked:
                self._data["pending"].remove(job)
                self._data["processed"] += 1
            scope = self.scope(store)
            jobs = {self.key(store,link,scope):{"store":store,"link":link,"scope":scope,"manual":True} for link in candidates}
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
            self._record("stores.queue", f"{STORES[store]}: actualización manual solicitada", source="manual", store=STORES[store],
                diagnostics={"references":len(jobs), "added":added, "interval_seconds":INTERVAL})
            await self._save()
            self._notify()
        self._queue()
        return {**self.snapshot(store), "queued":len(jobs)}

    def _current_job(self, job, names):
        return (self._linked_job(job) and any(
                normalized_name(product["name"]) in names and self.links_for_product(product).get(job["store"]) == job["link"]
                for product in self.catalog.products))

    def _linked_job(self, job):
        return (self.prices_enabled and self._active and self.hass.data.get(DOMAIN, {}).get("active")
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
        job["request_count"] = job.get("request_count", 0) + 1
        self._data["next_request"] = time.time()+INTERVAL
        self._record("stores.request", f"{STORES[job['store']]}: consulta de precio iniciada",
            source="manual" if job.get("manual") else "automatic", store=STORES[job["store"]],
            diagnostics={"reference_id":job["link"]["id"], "scope":job["scope"],
                "provider":"carrefour_json" if job["store"] == "carrefour" else job["store"]})

        await self._save()  # Persist request reservation and diagnostics before the HTTP request.
        self._notify()

    async def async_tick(self):
        if not self.prices_enabled:
            async with self._lock:
                if self._data["pending"] or self._data["partial"]:
                    self._data["processed"]+=len(self._data["pending"])
                    self._data.update(pending=[],partial=False)
                    await self._save()
                    self._notify()
            return
        community = getattr(self, "community", None)
        if community and self._active:
            current = dt_util.now()
            elapsed,_=self._schedule_window(current)
            if self._schedule_due(current) and elapsed < 60:
                await community.async_prepare_prices()
        async with self._lock:
            if not self._active or not self.hass.data.get(DOMAIN, {}).get("active") or self._preparing:
                return
            if (self._data.get("batch") or {}).get("finished_at") is not None and not self._data["batch"].get("logged"):
                await self._save()
                self._notify()
            now = dt_util.now()
            day = now.date().isoformat()
            elapsed,scheduled=self._schedule_window(now)
            scheduled_day=scheduled.isoformat()
            if (self._schedule_due(now) or self._data["day"] == scheduled_day and self._data["partial"] and time.time() >= self._data["prepare_retry_at"]) and elapsed < 60:
                await self._prepare(scheduled_day)
            if not self._data["pending"]:
                if self._data.get("batch") and not self._data["batch"].get("logged"):
                    await self._save()
                    self._notify()
                return
            if time.time() < self._data["next_request"]:
                first = self._data["pending"][0]
                community = getattr(self, "community", None)
                if not community or not community.price(first["store"], first["link"]):
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
                    self._record("stores.skipped",f"{STORES[store]}: referencia omitida",source="manual" if job.get("manual") else "automatic",store=STORES[store],
                        diagnostics={"reference_id":job["link"]["id"],"blocked":bool(job.get("blocked")),"reserved":bool(job.get("reserved"))})
                    self._data["pending"].pop(0)
                    self._data["processed"] += 1
                    await self._save()
                    self._notify()
                    continue
                entry, generation = self.settings.entry, self.settings._generation
                configuration = deepcopy(self.settings.snapshot["stores"][store])
                job["expected_requests"] = self.sources.expected_requests(store, configuration)
                source = "manual" if job.get("manual") else "automatic"
                self._configuration = (entry, generation, configuration, job)
                try:
                    community = getattr(self, "community", None)
                    shared_price = community.price(store, job["link"]) if community else None
                    local_price = self._data["offers"].get(key)
                    fresh_local = local_price if community and local_price and local_price.get("checked_at", 0) >= time.time()-86400 else None
                    result = shared_price or fresh_local
                    if result is None:
                        result = await self.sources.fetch(store, job["link"], configuration, self._reserve_request)
                    if (self.settings.entry is not entry or self.settings._generation != generation
                        or self.settings.snapshot["stores"].get(store) != configuration or not self._linked_job(job)):
                        result = "discarded"
                    if isinstance(result, dict):
                        previous = self._data["offers"].get(key)
                        if previous and price_fingerprint(previous) != price_fingerprint(result):
                            history = self._data["offer_history"].setdefault(key, [])
                            history.append(deepcopy(previous))
                            self._data["offer_history"][key] = history[-5:]
                        self._data["offers"][key] = {**result, "checked_at":result.get("checked_at", time.time()), "scope":job["scope"]}
                        self._data["errors"].pop(store, None)
                        self._record("stores.price", f"{STORES[store]}: precio actualizado", source=source,
                            diagnostics={"reference_id":job["link"]["id"], "price":result["price"], "currency":result["currency"]})
                    elif result is None:
                        self._record("stores.not_found", f"{STORES[store]}: referencia no disponible; se conserva el último precio", source=source,
                            diagnostics={"reference_id":job["link"]["id"], "response_class":"not_found"})
                    elif result == "discarded":
                        self._record("stores.skipped",f"{STORES[store]}: respuesta descartada por cambio de configuración",source=source,
                            store=STORES[store],diagnostics={"reference_id":job["link"]["id"],"response_class":"configuration_changed"})
                except (PriceError, aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, TypeError) as err:
                    diagnostics = getattr(err, "diagnostics", {"response_class":"invalid_response"})
                    if diagnostics.get("response_class") == "list_unavailable":
                        await self._save()
                        return
                    if diagnostics.get("response_class") in ("configuration_changed", "no_longer_pending"):
                        self._record("stores.skipped",str(err),source=source,store=STORES[store],diagnostics=diagnostics)
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
                    self._record("stores.error", self._data["errors"][store], source=source, store=STORES[store],
                        diagnostics={**diagnostics, "reference_id":job["link"]["id"], "next_attempt":"next_daily_run"})
                finally:
                    self._configuration = None
                self._data["pending"].pop(0)
                self._data["processed"] += 1
                for blocked in list(self._data["pending"]):
                    if blocked.get("blocked"):
                        self._record("stores.skipped",f"{STORES[blocked['store']]}: referencia omitida por rechazo de la tienda",
                            source="manual" if blocked.get("manual") else "automatic",store=STORES[blocked["store"]],
                            diagnostics={"reference_id":blocked["link"]["id"],"response_class":"store_blocked","blocked":True})
                        self._data["pending"].remove(blocked)
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
