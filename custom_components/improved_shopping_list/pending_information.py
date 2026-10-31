"""Explicit, resumable refresh of URLs belonging to incomplete catalog products."""
import asyncio
from asyncio import sleep
from copy import deepcopy
import math
import time
from urllib.parse import urlsplit

import aiohttp
from homeassistant.core import callback
from homeassistant.helpers.storage import Store

from .catalog import CatalogError, FIELDS
from .const import DOMAIN
from .product_references import gtin, UNITS
from .receipt_quantities import weight_format
from .store_links import HOSTS, normalize_link

INTERVAL=20


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def price(value):
    if not isinstance(value,dict) or value.get("currency")!="EUR":return False
    try:return value.get("price") not in (None,"") and not isinstance(value["price"],bool) and math.isfinite(float(value["price"])) and float(value["price"])>=0
    except (TypeError,ValueError):return False


def pending(product,offers=()):
    """Same product-level criterion as the panel: every active option is incomplete."""
    refs=[r for r in product.get("commercial_references",[]) if r.get("active") is not False]
    for ref in refs or [{}]:
        measure=ref.get("measure_price",{})
        has_price=price(ref.get("last_price")) or price(measure) and float(measure["price"])>0 and number(measure.get("quantity")) and measure["quantity"]>0 and measure.get("unit") in UNITS
        if not ref.get("store"):has_price=has_price or price(product)
        for offer in offers:
            if has_price:break
            if offer.get("catalog_product_id")!=product["id"] or not price(offer) or not ref.get("store") or offer.get("store")!=ref["store"]:continue
            code,other=gtin(ref.get("ean")),gtin(offer.get("ean"))
            if code and other and code!=other:continue
            has_price=bool(ref.get("id") and offer.get("commercial_reference_id")==ref["id"] or code and other and code==other or offer.get("reference_id") and offer["reference_id"] in (ref.get("reference_id"),ref.get("ticket_reference_id")) or not any(offer.get(k) for k in ("commercial_reference_id","reference_id","ean")) and len([r for r in refs if r.get("store")==ref["store"]])==1)
        quantity,unit=ref.get("content_quantity"),ref.get("content_unit")
        has_content=weight_format(ref) or number(quantity) and 0<quantity<=1000000 and (unit!="uds" or float(quantity).is_integer()) and unit in UNITS
        if has_price and has_content:return False
    return True


def url_store(url):
    return next((store for store,hosts in HOSTS.items() if urlsplit(url).hostname in hosts),"")


def merge_result(product,job,data):
    """Apply a manual retrieval to a fresh snapshot, without erasing concurrent edits."""
    refs=product["commercial_references"]
    original=next((r for r in refs if r["id"]==job["reference_id"] and r.get("active") is not False and r.get("url")==job["url"]),None)
    if not original:return False
    target=original
    different=bool(gtin(original.get("ean")) and gtin(data.get("ean")) and gtin(original["ean"])!=gtin(data["ean"]))
    if different:
        target=next((r for r in refs if r is not original and r.get("store")==data["store"] and gtin(r.get("ean"))==gtin(data["ean"]) and (r.get("reference_id")==data["reference_id"] or r.get("url")==data["url"])),None)
        if target and target.get("active") is False:return False
        if target is None:target={"store":data["store"],"ean":data["ean"]};refs.append(target)
        original["url"]="";original["reference_id"]=""
    old_store=original.get("store")
    old_link=product.get("store_links",{}).get(old_store)
    if different or target.get("store")!=data["store"]:
        if (old_link.get("url") if isinstance(old_link,dict) else old_link)==job["url"]:product["store_links"].pop(old_store,None)
        if not different:
            for key in ("id","last_price","measure_price","ticket_reference_id"):target.pop(key,None)
    target.update(store=data["store"],url=data["url"],reference_id=data["reference_id"],active=True)
    for field in ("name","brand","ean","nutriscore","image_url","pack_count"):
        if data.get(field) not in (None,""):target[field]=deepcopy(data[field])
    if not target.get("content_confirmed") and data.get("content_quantity") and data.get("content_unit"):
        target.update(content_quantity=data["content_quantity"],content_unit=data["content_unit"],content_confirmed=True)
    if data.get("price") is not None and data.get("currency")=="EUR":
        target["last_price"]={"price":data["price"],"currency":"EUR","checked_at":data.get("checked_at",int(time.time()))}
    if data.get("measure_price"):target["measure_price"]=deepcopy(data["measure_price"])
    for other in refs:
        if other is target or other.get("active") is False or not gtin(target.get("ean")) or gtin(other.get("ean"))!=gtin(target["ean"]):continue
        for field in ("brand","pack_count"):
            if not other.get(field) and target.get(field):other[field]=deepcopy(target[field])
        if not other.get("content_quantity") and target.get("content_quantity") and target.get("content_unit"):
            other.update(content_quantity=target["content_quantity"],content_unit=target["content_unit"],content_confirmed=True)
    product.setdefault("store_links",{}).setdefault(data["store"],data["url"])
    if not product.get("image_url") and data.get("image_url"):product["image_url"]=data["image_url"]
    return True


class PendingInformationRefresh:
    def __init__(self,hass,catalog,lookup,prices,activity):
        self.hass,self.catalog,self.lookup,self.prices,self.activity=hass,catalog,lookup,prices,activity
        self._store=Store(hass,1,f"{DOMAIN}.pending_information_refresh")
        self._queue=[];self._next=0;self._cooldowns={};self._task=None;self._active=False;self._listeners=set();self._lock=asyncio.Lock()
        self._state={"running":False,"phase":"idle","total":0,"processed":0,"updated":0,"skipped":0,"current":"","errors":[],"products":[],"updated_products":[]}

    async def async_load(self):
        saved=await self._store.async_load()
        if not isinstance(saved,dict):return
        queue=saved.get("queue",[]);state=saved.get("state",{})
        if not isinstance(queue,list) or len(queue)>20000 or not isinstance(state,dict):return
        try:
            for job in queue:
                if not isinstance(job,dict) or any(not isinstance(job.get(k),str) for k in ("product_id","reference_id","url")):return
                normalize_link(url_store(job["url"]),job["url"])
            done=state.get("processed",0)
            if type(done) is not int or not 0<=done<=len(queue):return
            if any(type(state.get(key,0)) is not int or state.get(key,0)<0 for key in ("updated","skipped")):return
            if any(not isinstance(state.get(key,[]),list) or any(not isinstance(value,str) for value in state.get(key,[])) for key in ("products","updated_products")):return
            if not isinstance(state.get("errors",[]),list) or any(not isinstance(error,dict) for error in state.get("errors",[])):return
            self._queue=queue;self._state.update({k:v for k,v in state.items() if k in self._state})
            self._state["total"]=len(queue)
            cooldowns=saved.get("cooldowns",{})
            self._cooldowns={key:value for key,value in (cooldowns if isinstance(cooldowns,dict) else {}).items() if key in HOSTS and number(value) and time.time()<value<=time.time()+86400}
            value=saved.get("next",0)
            if number(value) and 0<=value<=time.time()+86400:self._next=value
        except (ValueError,TypeError):return

    async def _save(self):
        await self._store.async_save({"queue":deepcopy(self._queue),"state":deepcopy(self._state),"next":self._next,"cooldowns":deepcopy(self._cooldowns)})

    @property
    def snapshot(self):return deepcopy(self._state)

    @callback
    def subscribe(self,listener):
        self._listeners.add(listener)
        return lambda:self._listeners.discard(listener)

    def _notify(self):
        for listener in tuple(self._listeners):listener()

    @callback
    def start(self):
        self._active=True
        if self._state["phase"] in ("running","waiting","preparing","paused") and self._state["processed"]<len(self._queue):self._launch()

    def _launch(self):
        if self._active and (not self._task or self._task.done()):self._task=self.hass.async_create_background_task(self._run(),"Shopping pending-information URL refresh")

    async def async_start(self):
        async with self._lock:
            if self._task and not self._task.done():return self.snapshot
            queue=[];products=[]
            for product in self.catalog.products:
                if not pending(product,self.prices.prices_for(product)):continue
                jobs=[];seen=set()
                for ref in product.get("commercial_references",[]):
                    if ref.get("active") is False or not ref.get("url") or ref["url"] in seen:continue
                    try:normalize_link(url_store(ref["url"]),ref["url"])
                    except (ValueError,TypeError):continue
                    seen.add(ref["url"]);jobs.append({"product_id":product["id"],"reference_id":ref["id"],"url":ref["url"]})
                if jobs:products.append(product["id"]);queue.extend(jobs)
            if len(queue)>20000:raise ValueError("Hay demasiadas alternativas para revisar de una vez.")
            self._queue=queue
            self._state.update(running=True,phase="preparing",total=len(queue),processed=0,updated=0,skipped=0,current="",errors=[],products=products,updated_products=[])
            await self._save();self._notify();self._launch()
            return self.snapshot

    async def _before_request(self):
        self._state["phase"]="waiting";self._notify()
        await sleep(max(0,self._next-time.time()))
        if not self._active:raise asyncio.CancelledError
        await self.lookup._before_request()
        self._next=time.time()+INTERVAL
        self.lookup._next=max(self.lookup._next,time.monotonic()+INTERVAL)
        await self._save()
        self._state["phase"]="running";self._notify()

    async def _apply(self,job,data):
        for _ in range(3):
            current=next((p for p in self.catalog.products if p["id"]==job["product_id"]),None)
            if not current:return False
            candidate={k:deepcopy(v) for k,v in current.items() if k in FIELDS}
            if not merge_result(candidate,job,data) or candidate=={k:v for k,v in current.items() if k in FIELDS}:return False
            try:await self.catalog.async_save_product(candidate);return True
            except CatalogError as err:
                if getattr(err,"code","")!="conflict":raise
        raise ValueError("El producto ha cambiado durante la recuperación. Revisa su ficha.")

    async def _run(self):
        self._state["running"]=True;blocked={store for store,until in self._cooldowns.items() if until>time.time()}
        reported={url_store(error.get("url","")) for error in self._state["errors"]}
        try:
            while self._active and self._state["processed"]<len(self._queue):
                job=self._queue[self._state["processed"]]
                current=next((p for p in self.catalog.products if p["id"]==job["product_id"]),None)
                ref=next((r for r in (current or {}).get("commercial_references",[]) if r["id"]==job["reference_id"] and r.get("active") is not False and r.get("url")==job["url"]),None)
                self._state.update(current=(current or {}).get("name",""),phase="running");self._notify()
                store=url_store(job["url"])
                try:
                    if not ref or store in blocked:
                        self._state["skipped"]+=1
                        if ref and store not in reported:
                            self._state["errors"].append({"product":current["name"],"url":job["url"],"message":"La tienda está en pausa de reintento. Se conservan los datos anteriores."})
                            reported.add(store)
                    else:
                        data=await self.lookup.retrieve(job["url"],before_request=self._before_request,force=True)
                        if await self._apply(job,data):
                            self._state["updated"]+=1
                            if job["product_id"] not in self._state["updated_products"]:self._state["updated_products"].append(job["product_id"])
                except (ValueError,OSError,TimeoutError,aiohttp.ClientError) as err:
                    diagnostics=deepcopy(getattr(err,"diagnostics",{}))
                    if diagnostics.get("http_status") in (403,429,503) or diagnostics.get("retry_seconds",0) or diagnostics.get("response_class") in ("rate_limited","access_denied"):
                        blocked.add(store);reported.add(store)
                        wait=diagnostics.get("retry_seconds",900)
                        self._cooldowns[store]=time.time()+min(86400,max(900,wait if number(wait) else 900))
                    if len(self._state["errors"])<200:self._state["errors"].append({"product":(current or {}).get("name",""),"url":job["url"],"message":str(err)[:500],"diagnostics":diagnostics})
                self._state["processed"]+=1;await self._save();self._notify()
            self._state.update(running=False,phase="finished",current="")
            await self._save();self._notify()
            if self.activity:self.activity.record("stores.catalog","Recuperación de información pendiente finalizada",source="user",diagnostics=self.snapshot)
        except asyncio.CancelledError:
            self._state.update(running=False,phase="paused",current="")
            await self._save();self._notify();raise
        except (ValueError,OSError,TimeoutError) as err:
            self._state.update(running=False,phase="error",current="")
            self._state["errors"].append({"message":str(err)[:500]});self._notify()

    async def async_stop(self):
        self._active=False
        if self._task and not self._task.done():self._task.cancel();await asyncio.gather(self._task,return_exceptions=True)
