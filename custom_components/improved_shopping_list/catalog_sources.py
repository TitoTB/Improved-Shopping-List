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

INTERVAL = 300


class CatalogSources:
    def __init__(self, hass, catalog, links, lookup, activity):
        self.hass, self.catalog, self.links, self.lookup, self.activity = hass, catalog, links, lookup, activity
        self._store = Store(hass,1,f"{DOMAIN}.catalog_sources")
        self._data = {"enabled":False,"attempts":{},"next_request":0,"retry_at":0}
        self._status = {"running":False,"phase":"idle","total":0,"processed":0,"updated":0,"errors":[],"current":""}
        self._active = False
        self._task = self._timer = self._unsubscribe = None
        self._listeners = set()

    async def async_load(self):
        saved = await self._store.async_load()
        if isinstance(saved,dict):
            self._data["enabled"] = saved.get("enabled") is True
            self._data["attempts"] = {key:value for key,value in saved.get("attempts",{}).items()
                                      if isinstance(key,str) and isinstance(value,dict) and type(value.get("at")) in (int,float)}
            for key in ("next_request","retry_at"):
                value = saved.get(key,0)
                if type(value) in (int,float) and 0 <= value <= time.time()+DAY:
                    self._data[key] = value
        self._gate()

    def _gate(self):
        if self._data["enabled"]:
            self.links.enabled_stores.add("alcampo")
        else:
            self.links.enabled_stores.discard("alcampo")

    @property
    def snapshot(self):
        return {**deepcopy(self._status),"enabled":self._data["enabled"],"next_request":self._data["next_request"],
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
        if type(enabled) is not bool:
            raise ValueError("Selecciona un estado válido para el catálogo de Alcampo.")
        if enabled != self._data["enabled"]:
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
            self._task = self.hass.async_create_background_task(self.async_run(),"Shopping Alcampo catalog completion")

    async def _before_request(self):
        delay = self._data["next_request"]-time.time()
        if delay > 0:
            self._status["phase"] = "waiting"; self._notify()
            await sleep(delay)
        if not self._active or not self._data["enabled"]:
            raise asyncio.CancelledError
        await self.lookup._before_request()  # Shared spacing with manual option lookups.
        self._data["next_request"] = time.time()+INTERVAL
        await self._store.async_save(deepcopy(self._data))
        self._status["phase"] = "querying"; self._notify()

    def _pending(self, links):
        result = []
        for key,link in links.items():
            code = key.rsplit(":",1)[-1]
            products = [p for p in self.catalog.products if code in product_eans(p) and any(
                ref["store"] == "alcampo" and gtin(ref.get("ean")) == code and ref.get("active",True)
                and ref.get("url") == link["url"] for ref in p.get("commercial_references",[]))]
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
        self._status.update(running=True,phase="preparing",errors=[],current="")
        self._notify()
        try:
            if not any(product_eans(product) for product in self.catalog.products):
                self._status.update(phase="finished",total=0,processed=0,updated=0)
                return
            links = await self.links.async_store_links("alcampo")
            if not links and self.links.error:
                raise ValueError("No se ha podido consultar el diccionario: "+self.links.error)
            if not self._active or not self._data["enabled"]:
                return
            await self.catalog.async_apply_ean_links(links)
            pending = self._pending(links)
            self._status.update(total=len(pending),processed=0,updated=0)
            self._notify()
            for identity,code,link,name in pending:
                if not self._active or not self._data["enabled"]:
                    break
                self._status.update(current=name,phase="querying"); self._notify()
                success = False
                try:
                    data = await self.lookup.retrieve(link["url"],"alcampo",code,before_request=self._before_request)
                    if not self._active or not self._data["enabled"]:
                        break
                    if data.get("store") != "alcampo" or data.get("reference_id") != link["id"]:
                        raise PriceError("La respuesta no corresponde a esta ficha de Alcampo.")
                    if data.get("ean") and gtin(data["ean"]) != code:
                        raise PriceError("El EAN de Alcampo no coincide con el producto.")
                    changed = await self.catalog.async_complete_store_option("alcampo",code,link,data)
                    self._status["updated"] += changed
                    success = data.get("price") is not None
                    if not success:
                        self._status["errors"].append({"product":name,"ean":code,"message":"La ficha no ha devuelto un precio; se conservan los datos anteriores."})
                except (ValueError,OSError,TimeoutError) as err:
                    self._status["errors"].append({"product":name,"ean":code,"message":str(err)[:500]})
                    blocked = max(0,self.lookup._blocked_until.get("alcampo",0)-time.monotonic())
                    if blocked:
                        self._data["retry_at"] = time.time()+blocked
                self._data["attempts"][identity] = {"at":time.time(),"success":success}
                self._status["processed"] += 1
                await self._store.async_save(deepcopy(self._data)); self._notify()
                if self._data["retry_at"] > time.time():
                    break
            self._status.update(running=False,phase="paused" if self._data["retry_at"]>time.time() else "finished",current="")
            if pending and self.activity:
                self.activity.record("stores.catalog","Alcampo: revisión del catálogo finalizada",source="automatic",
                                     diagnostics=deepcopy(self._status))
        except (ValueError,OSError,TimeoutError) as err:
            self._status.update(running=False,phase="error",errors=[{"message":str(err)[:500]}])
        finally:
            self._status["running"] = False
            self._notify()
            if self._active and self._data["enabled"]:
                self._timer = async_call_later(self.hass,max(3600,self._data["retry_at"]-time.time()),self._launch)
