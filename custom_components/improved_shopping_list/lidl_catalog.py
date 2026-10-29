"""Bounded, anonymous Lidl IAN discovery for explicitly reviewed receipts."""
from asyncio import Lock, sleep
from copy import deepcopy
from html.parser import HTMLParser
import json
import re
import time
from urllib.parse import urlencode

from aiohttp import ClientError, ClientTimeout
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .ean_links import DAY
from .option_lookup import metadata
from .price_sources import PriceError
from .product_references import gtin
from .store_links import normalize_link

INTERVAL=20
MAX_BYTES=10*1024*1024
PAGES=(
    "https://www.lidl.es/c/ofertas-semanales/a10089449",
    "https://www.lidl.es/c/store/ofertas-proxima-semana/a10088432/",
    "https://www.lidl.es/c/frescos-frutas-y-verduras/s10089404",
    "https://www.lidl.es/c/bajadas-fruta-y-verdura/a10105984",
)


def ian(value):
    return (value.lstrip("0") or "0") if isinstance(value,str) and re.fullmatch(r"[0-9]{1,16}",value) else ""


def product_data(product):
    if not isinstance(product,dict):
        raise ValueError("Ficha de Lidl no válida.")
    link=normalize_link("lidl","https://www.lidl.es"+product.get("canonicalPath", ""))
    if str(product.get("erpNumber"))!=link["id"]:
        raise ValueError("Lidl no ha confirmado la referencia web.")
    values=product.get("ians",[])
    if not isinstance(values,list) or len(values)>100:raise ValueError("Códigos IAN no válidos.")
    codes={ian(code) for code in values if ian(code)}
    if not codes:
        raise ValueError("Lidl no ha devuelto códigos IAN.")
    packs=[]; future=[]
    def pack(price,target):
        value=price.get("packaging",{}).get("text") if isinstance(price,dict) and isinstance(price.get("packaging"),dict) else None
        if isinstance(value,str) and 0<len(value)<=160:
            target.append(value)
    pack(product.get("price"),packs)
    regions=product.get("regionsPrices") or {}
    if not isinstance(regions,dict):raise ValueError("Regiones de Lidl no válidas.")
    for region in regions.values():
        if not isinstance(region,dict):continue
        pack(region.get("currentPrice"),packs)
        for item in region.get("futurePrices",[]) if isinstance(region.get("futurePrices",[]),list) else []:
            if isinstance(item,dict):pack(item.get("price"),future)
    choices=set(packs or future)
    size=next(iter(choices)) if len(choices)==1 else ""
    name=product.get("fullTitle") or product.get("title") or ""
    result=metadata({"name":name,"brand":product.get("brand", ""),"size":size})
    # No guessed quantities from a title when packaging is absent or ambiguous.
    if not size:
        result.pop("content_quantity",None);result.pop("content_unit",None)
    result.pop("image_url",None)
    code=next((product.get(key) for key in ("gtin13","gtin14","ean") if gtin(product.get(key))),"")
    result.update(store="lidl",url=link["url"],web_reference_id=link["id"],ians=sorted(codes),checked_at=time.time(),
                  format_provisional=bool(not packs and future),packaging=size)
    if code:result["ean"]=code
    return result


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__();self.products=[]
    def handle_starttag(self,tag,attrs):
        raw=dict(attrs).get("data-grid-data")
        if raw and len(raw)<=MAX_BYTES:
            try:self.collect(json.loads(raw))
            except (ValueError,RecursionError):pass
    def collect(self,value,depth=0):
        if depth>15 or len(self.products)>=5000:return
        if isinstance(value,list):
            for child in value:self.collect(child,depth+1)
        elif isinstance(value,dict):
            if value.get("ians") and value.get("canonicalPath"):
                try:self.products.append(product_data(value))
                except (ValueError,TypeError,AttributeError):pass
            else:
                for child in value.values():self.collect(child,depth+1)


def parse_listing(raw):
    parser=ListingParser();parser.feed(raw.decode("utf-8",errors="replace"));return parser.products


class LidlCatalog:
    def __init__(self,hass,links,lookup,activity):
        self.hass,self.links,self.lookup,self.activity=hass,links,lookup,activity
        self._store=Store(hass,1,f"{DOMAIN}.lidl_catalog")
        self._data={"products":{},"checked_at":0,"next_request":0,"retry_at":0}
        self._lock=Lock();self._closed=False
    async def async_load(self):
        saved=await self._store.async_load()
        if not isinstance(saved,dict):return
        for key in ("checked_at","next_request","retry_at"):
            value=saved.get(key,0)
            if type(value) in (int,float) and 0<=value<=time.time()+DAY:self._data[key]=value
        products=saved.get("products",{})
        if not isinstance(products,dict):return
        for code,items in list(products.items())[:10000]:
            if ian(code)!=code or not isinstance(items,list):continue
            valid=[]
            for item in items[:10]:
                try:
                    link=normalize_link("lidl",item["url"])
                    if link["id"]==item["web_reference_id"] and code in item["ians"]:valid.append(item)
                except (ValueError,TypeError,KeyError):pass
            if valid:self._data["products"][code]=valid
    def close(self):self._closed=True
    async def _save(self):
        if not self._closed:await self._store.async_save(deepcopy(self._data))
    async def _request(self,url):
        if self._closed:raise ValueError("El catálogo de Lidl se está cerrando.")
        if self._data["retry_at"]>time.time():
            raise PriceError("Lidl está en pausa de reintento.",response_class="rate_limited")
        await sleep(max(0,self._data["next_request"]-time.time()))
        await self.lookup._before_request()
        if self._closed:raise ValueError("El catálogo de Lidl se está cerrando.")
        self._data["next_request"]=time.time()+INTERVAL;await self._save()
        async with async_get_clientsession(self.hass).get(url,headers={"Accept":"application/json,text/html","User-Agent":"Improved-Shopping-List"},timeout=ClientTimeout(total=25),allow_redirects=False) as response:
            if response.status!=200:
                if response.status in (403,429,503):
                    retry=response.headers.get("Retry-After","")
                    self._data["retry_at"]=time.time()+min(DAY,max(900,int(retry) if retry.isdigit() else 900));await self._save()
                raise PriceError(f"Lidl: consulta rechazada (HTTP {response.status}).",http_status=response.status,response_class="http_error")
            raw=bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw)>MAX_BYTES:raise ValueError("La respuesta de Lidl es demasiado grande.")
            return bytes(raw)
    def _remember(self,data):
        for code in data["ians"]:
            if code not in self._data["products"] and len(self._data["products"])>=10000:continue
            items=self._data["products"].setdefault(code,[])
            items[:]=[item for item in items if item["url"]!=data["url"]]
            if len(items)<10:items.append(deepcopy(data))
    async def _index(self):
        if self._data["checked_at"] and self._data["checked_at"]+DAY>time.time():return
        # Reserve the daily scan before network I/O, including unsuccessful scans.
        self._data["checked_at"]=time.time();await self._save()
        errors=[];count=0
        for url in PAGES:
            if self._closed:break
            try:
                rows=await self.hass.async_add_executor_job(parse_listing,await self._request(url));count+=1
                for data in rows:self._remember(data)
            except (ClientError,TimeoutError,OSError,ValueError) as err:
                errors.append({"url":url,"message":str(err)[:300],**getattr(err,"diagnostics",{})})
                if self._data["retry_at"]>time.time():break
        await self._save()
        if self.activity and not self._closed:
            self.activity.record("stores.lidl_catalog","Lidl: consulta de listados públicos finalizada",source="user",
                diagnostics={"pages":count,"ians":len(self._data["products"]),"interval_seconds":INTERVAL,"errors":errors})
    async def resolve(self,code,ean="",url=""):
        code=ian(code)
        if not code:return {"reason":"El ticket no contiene una referencia IAN válida."}
        async with self._lock:
            if self._closed:return {"reason":"El catálogo de Lidl se está cerrando."}
            cached=self._data["products"].get(code,[])
            if len(cached)==1 and (not url or url==cached[0]["url"]) and (not ean or not cached[0].get("ean") or gtin(ean)==gtin(cached[0]["ean"])):
                return {**deepcopy(cached[0]),"source":"cache"}
            # Explicit receipt review checks the EAN dictionary before Lidl HTTP.
            link=await self.links.async_find_link("lidl",ean) if gtin(ean) else None
            chosen=normalize_link("lidl",url) if url else link
            if chosen:
                via_dictionary=bool(link and chosen["url"]==link["url"])
                try:
                    raw=await self._request("https://www.lidl.es/p/api/gridboxes/ES/es?"+urlencode({"erpNumbers":chosen["id"]}))
                    rows=json.loads(raw)
                    matches=[product_data(p) for p in rows if isinstance(p,dict) and str(p.get("erpNumber"))==chosen["id"]] if isinstance(rows,list) else []
                    matches=[p for p in matches if (code in p["ians"] or via_dictionary and gtin(ean)) and (not p.get("ean") or not ean or gtin(p["ean"])==gtin(ean))]
                    if len(matches)==1:
                        data=matches[0]
                        # The dictionary can verify an EAN even if IAN was omitted.
                        if code not in data["ians"]:data["ians"].append(code)
                        self._remember(data);await self._save();return {**data,"source":"dictionary" if not url else "url"}
                except (ClientError,TimeoutError,OSError,ValueError) as err:
                    if self._data["retry_at"]>time.time():return {"reason":str(err)}
                if url:return {"reason":"La ficha vinculada no ha confirmado el IAN del ticket; se conserva la URL manual."}
            await self._index()
            cached=self._data["products"].get(code,[])
            if len(cached)==1 and (not ean or not cached[0].get("ean") or gtin(ean)==gtin(cached[0]["ean"])):
                return {**deepcopy(cached[0]),"source":"listing"}
            return {"reason":"Hay varias fichas para este IAN; vincula una URL manualmente." if cached else "No se ha encontrado una ficha pública con este IAN."}
