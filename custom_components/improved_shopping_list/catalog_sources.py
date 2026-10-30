"""Opt-in completion from verified EAN links, with durable request spacing."""
import asyncio
from asyncio import sleep
from copy import deepcopy
import time

from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .ean_links import product_eans, DAY
from .product_references import gtin
from .price_sources import PriceError

INTERVAL = 20


class CatalogSources:
    source_store = "alcampo"
    source_name = "Alcampo"
    def __init__(self, hass, catalog, links, lookup, activity):
        self.hass, self.catalog, self.links, self.lookup, self.activity = hass, catalog, links, lookup, activity
        self._store = Store(hass,1,f"{DOMAIN}.catalog_sources" if self.source_store=="alcampo" else f"{DOMAIN}.{self.source_store}_catalog")
        self._data = {"enabled":False,"show_store":False,"attempts":{},"next_request":0,"retry_at":0}
        self._status = {"running":False,"phase":"idle","total":0,"processed":0,"updated":0,"errors":[],"current":""}
        self._active = False
        self._task = self._timer = self._unsubscribe = None
        self._listeners = set()
        self._legacy_source_visibility = False
        self._config_lock=asyncio.Lock()
        self._data_lock=asyncio.Lock()

    async def async_load(self):
        saved = await self._store.async_load()
        if isinstance(saved,dict):
            self._legacy_source_visibility = "show_store" not in saved
            self._data["enabled"] = saved.get("enabled") is True
            self._data["show_store"] = saved.get("show_store") is True
            self._data["attempts"] = {key:value for key,value in saved.get("attempts",{}).items()
                                      if isinstance(key,str) and isinstance(value,dict) and type(value.get("at")) in (int,float)}
            for key in ("next_request","retry_at"):
                value = saved.get(key,0)
                if type(value) in (int,float) and 0 <= value <= time.time()+DAY:
                    self._data[key] = value
        self._gate()
        await self.catalog.async_source_visibility(self.source_store,self._data["show_store"],self._legacy_options())
        if self._legacy_source_visibility:
            await self._save_state()
            self._legacy_source_visibility=False
        await self._apply_cached_options()

    async def _save_state(self):
        async with self._data_lock:
            await self._store.async_save(deepcopy(self._data))

    def _cached_options(self):
        result={}
        for identity,saved in deepcopy(list(self._data["attempts"].items())):
            data=saved.get("data")
            if not saved.get("matched",saved.get("success")) or not isinstance(data,dict):continue
            code=gtin(data.get("ean") or identity.split(":",1)[0])
            url=data.get("url")
            if not url and self.links:
                url=self.links._data.get("links",{}).get(self.source_store+":"+code)
            try:
                from .store_links import normalize_link
                link=normalize_link(self.source_store,url)
            except ValueError:continue
            if not code or data.get("store",self.source_store)!=self.source_store or data.get("reference_id",link["id"])!=link["id"]:continue
            data.update(ean=data.get("ean") or code,url=link["url"],reference_id=link["id"],store=self.source_store)
            result[(code,link["id"])]=data
        return list(result.values())

    async def _apply_cached_options(self):
        changed=0
        for data in self._cached_options():
            try:
                changed+=await self.catalog.async_complete_store_option(self.source_store,data["ean"],data["url"],data,
                    create=True,show_store=self._data["show_store"],catalog_source=True)
            except ValueError as err:
                self._status["errors"].append({"ean":data["ean"],"message":str(err)[:500],"diagnostics":{"stage":"cached_option"}})
        return changed

    def _legacy_options(self):
        if not self._legacy_source_visibility:return set()
        pairs={(gtin(data.get("ean")),data.get("url")) for saved in self._data["attempts"].values()
            if isinstance(data:=saved.get("data"),dict) and gtin(data.get("ean")) and data.get("url")}
        if self.links:
            pairs.update((key.rsplit(":",1)[-1],link["url"]) for key,link in self.links._data.get("resolved",{}).items() if key.startswith(self.source_store+":"))
        return pairs

    async def async_set_show_store(self, show_store):
        async with self._config_lock:
            return await self._set_show_store(show_store)

    async def _set_show_store(self, show_store):
        if type(show_store) is not bool:raise ValueError("Selecciona un estado de visibilidad válido.")
        async with self._data_lock:
            updated={**self._data,"show_store":show_store}
            await self._store.async_save(deepcopy(updated))
            self._data=updated
        self._gate()
        await self.catalog.async_source_visibility(self.source_store,show_store,self._legacy_options())
        await self._apply_cached_options()
        self._queue();self._notify()
        return self.snapshot

    def _gate(self):
        if self._data["enabled"]:
            self.links.catalog_stores.add(self.source_store)
        else:
            self.links.catalog_stores.discard(self.source_store)
        if self._data["enabled"] and self._data["show_store"]:
            self.links.enabled_stores.add(self.source_store)
        else:
            self.links.enabled_stores.discard(self.source_store)

    @property
    def snapshot(self):
        return {**deepcopy(self._status),"enabled":self._data["enabled"],"show_store":self._data["show_store"],"next_request":self._data["next_request"],
                "retry_at":self._data["retry_at"],"interval_seconds":INTERVAL}

    @callback
    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda:self._listeners.discard(listener)

    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    def start(self):
        if self._active:
            return
        self._active = True
        self._unsubscribe = self.catalog.subscribe(self._queue)
        self._queue()

    async def async_stop(self):
        self._active = False
        if self._unsubscribe:
            self._unsubscribe(); self._unsubscribe = None
        await self._cancel()

    async def _cancel(self):
        if self._timer:
            self._timer(); self._timer = None
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task,return_exceptions=True)
        self._task = None
        self._status.update(running=False,phase="idle",current="")

    async def async_set_enabled(self, enabled):
        async with self._config_lock:
            return await self._set_enabled(enabled)

    async def _set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError(f"Selecciona un estado válido para el catálogo de {self.source_name}.")
        if enabled != self._data["enabled"]:
            async with self._data_lock:
                updated = {**self._data,"enabled":enabled}
                await self._store.async_save(deepcopy(updated))
                self._data = updated
            self._gate()
            if not enabled:
                await self._cancel()
            else:
                self._status.update(phase="preparing",total=0,processed=0,updated=0,errors=[])
                self._queue()
        self._notify()
        return self.snapshot

    @callback
    def _queue(self, *_args):
        if not self._active or not self._data["enabled"] or self._task and not self._task.done():
            return
        if self._timer:
            self._timer()
        self._timer = async_call_later(self.hass,max(1,self._data["retry_at"]-time.time()),self._launch)

    @callback
    def _launch(self, *_args):
        self._timer = None
        if self._active and self._data["enabled"] and (self._task is None or self._task.done()):
            self._task = self.hass.async_create_background_task(self.async_run(),f"Shopping {self.source_name} catalog completion")

    async def _before_request(self):
        delay = self._data["next_request"]-time.time()
        if delay > 0:
            self._status["phase"] = "waiting"; self._notify()
            await sleep(delay)
        if not self._active or not self._data["enabled"]:
            raise asyncio.CancelledError
        await self.lookup._before_request()  # Shared spacing with manual option lookups.
        self._data["next_request"] = time.time()+INTERVAL
        await self._save_state()
        self._status["phase"] = "querying"; self._notify()

    def _pending(self, links):
        result = []
        for key,link in links.items():
            code = key.rsplit(":",1)[-1]
            products = [p for p in self.catalog.products if code in product_eans(p)]
            if not products:
                continue
            identity = code+":"+link["id"]
            attempt = self._data["attempts"].get(identity,{})
            if attempt.get("success") or attempt.get("at",0)+DAY > time.time():
                continue
            result.append((identity,code,link,products[0]["name"]))
        return result

    async def async_run(self):
        if not self._active or not self._data["enabled"]:
            return
        if self._data["retry_at"]>time.time():
            self._status.update(phase="paused");self._notify();return
        if self._timer:
            self._timer(); self._timer = None
        self._status.update(running=True,phase="preparing",errors=[],current="")
        self._notify()
        try:
            if not any(product_eans(product) for product in self.catalog.products):
                self._status.update(phase="finished",total=0,processed=0,updated=0)
                return
            links = await self.links.async_store_links(self.source_store)
            if not links and self.links.error:
                raise ValueError("No se ha podido consultar el diccionario: "+self.links.error)
            if not self._active or not self._data["enabled"]:
                return
            if self._data["show_store"]:
                await self.catalog.async_apply_ean_links(links)
            reused = await self._apply_cached_options()
            pending = self._pending(links)
            self._status.update(total=len(pending),processed=0,updated=reused)
            self._notify()
            for identity,code,link,name in pending:
                if not self._active or not self._data["enabled"]:
                    break
                self._status.update(current=name,phase="querying"); self._notify()
                previous=self._data["attempts"].get(identity,{})
                previous_data=deepcopy(previous.get("data")) if previous.get("matched",previous.get("success")) else None
                success = False
                data = None
                matched = False
                try:
                    data = await self.lookup.retrieve(link["url"],self.source_store,code,before_request=self._before_request)
                    data.setdefault("checked_at",int(time.time()))
                    if not self._active or not self._data["enabled"]:
                        break
                    if data.get("store") != self.source_store or data.get("reference_id") != link["id"]:
                        raise PriceError(f"La respuesta no corresponde a esta ficha de {self.source_name}.")
                    if (self.source_store=="mercadona" or data.get("ean")) and gtin(data.get("ean", "")) != code:
                        raise PriceError(f"El EAN de {self.source_name} no coincide con el producto.")
                    data.setdefault("ean",code)
                    data.setdefault("url",link["url"])
                    matched = True
                    self._data["attempts"][identity]={"at":time.time(),"success":False,"matched":True,"data":deepcopy(data)}
                    await self._save_state()
                    changed = await self.catalog.async_complete_store_option(self.source_store,code,link,data,create=True,show_store=self._data["show_store"],catalog_source=True)
                    self._status["updated"] += changed
                    success = data.get("price") is not None
                    if not success:
                        self._status["errors"].append({"product":name,"ean":code,"message":"La ficha no ha devuelto un precio; se conservan los datos anteriores.",
                            "reference_id":link["id"],"url":link["url"],"diagnostics":deepcopy(data.get("retrieval_diagnostics",{}))})
                except (ValueError,OSError,TimeoutError) as err:
                    self._status["errors"].append({"product":name,"ean":code,"message":str(err)[:500],
                        "reference_id":link["id"],"url":link["url"],"error_type":type(err).__name__,
                        "diagnostics":deepcopy(getattr(err,"diagnostics",{}))})
                blocked = max(0,self.lookup._blocked_until.get(self.source_store,0)-time.monotonic())
                if blocked:
                    self._data["retry_at"] = time.time()+blocked
                retained=data if matched else previous_data
                self._data["attempts"][identity] = {"at":time.time(),"success":success,"matched":bool(retained),**({"data":deepcopy(retained)} if retained else {})}
                self._status["processed"] += 1
                await self._save_state(); self._notify()
                if self._data["retry_at"] > time.time():
                    break
            self._status.update(running=False,phase="paused" if self._data["retry_at"]>time.time() else "finished",current="")
            if pending and self.activity:
                self.activity.record("stores.catalog",f"{self.source_name}: revisión del catálogo {'pausada' if self._status['phase']=='paused' else 'finalizada'}",source="automatic",
                                     diagnostics={**deepcopy(self._status),"interval_seconds":INTERVAL,
                                                  "retry_at":self._data["retry_at"]})
        except (ValueError,OSError,TimeoutError) as err:
            self._status.update(running=False,phase="error",errors=[{"message":str(err)[:500]}])
        finally:
            self._status["running"] = False
            self._notify()
            if self._active and self._data["enabled"]:
                self._timer = async_call_later(self.hass,max(3600,self._data["retry_at"]-time.time()),self._launch)
