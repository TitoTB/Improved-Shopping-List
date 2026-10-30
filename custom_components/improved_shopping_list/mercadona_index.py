"""Local EAN index of the complete public Mercadona snapshot; no user uploads."""
import asyncio
import json
import math
import re
import time

from aiohttp import ClientError, ClientTimeout
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .ean_links import DAY
from .product_references import gtin
from .ean_common import validate as validate_common, observed_at

URL="https://raw.githubusercontent.com/TitoTB/Improved-Shopping-List/data/catalogs/mercadona-index.json"
INITIAL_URL="https://raw.githubusercontent.com/TitoTB/Improved-Shopping-List/main/data/mercadona-index.json"
MAX_BYTES=4*1024*1024


def validate_index(value):
    if not isinstance(value,dict) or value.get("schema_version")!=1:
        raise ValueError("El índice público de Mercadona no tiene un formato válido.")
    products=value.get("products")
    if not isinstance(products,dict) or not 1<=len(products)<=20000:
        raise ValueError("El índice público de Mercadona no contiene productos válidos.")
    revision=value.get("source_revision")
    if not isinstance(revision,str) or not re.fullmatch(r"[a-f0-9]{40}",revision):
        raise ValueError("La revisión del índice público de Mercadona no es válida.")
    for ean,identifier in products.items():
        if not gtin(ean) or gtin(ean)!=ean or not isinstance(identifier,str) or not re.fullmatch(r"[0-9]{1,12}",identifier):
            raise ValueError("El índice público de Mercadona contiene una referencia no válida.")
    result={"schema_version":1,"source_revision":revision,"products":dict(products),"common_schema_version":0,"common":{}}
    common_version=value.get("common_schema_version",0)
    if type(common_version) is not int or common_version not in (0,1):raise ValueError("Invalid common EAN schema")
    if common_version==1:
        common=value.get("common")
        if not isinstance(common,dict) or set(common)-set(products):raise ValueError("Invalid common EAN entries")
        date=value.get("source_updated_at")
        observed_at(date)
        result.update(common_schema_version=1,source_updated_at=date,common={ean:validate_common(row) for ean,row in common.items()})
    return result


def parse_index(raw):
    if len(raw)>MAX_BYTES:raise ValueError("El índice público de Mercadona supera el tamaño permitido.")
    return validate_index(json.loads(raw))


class MercadonaIndex:
    def __init__(self,hass):
        self.hass=hass
        self._store=Store(hass,1,f"{DOMAIN}.mercadona_index")
        self._data={"index":None,"checked_at":0,"next_attempt":0,"etag":"","url":""}
        self._lock=asyncio.Lock()
        self.error=""

    @property
    def products(self):
        return self._data["index"]["products"] if self._data["index"] else {}

    @property
    def status(self):
        return {"entries":len(self.products),"revision":(self._data["index"] or {}).get("source_revision",""),
            "checked_at":self._data["checked_at"],"cached_fallback":bool(self.error and self.products),
            "common_entries":len((self._data["index"] or {}).get("common",{}))}

    @property
    def has_common_data(self):
        return (self._data["index"] or {}).get("common_schema_version")==1

    def common_data(self,codes):
        index=self._data["index"] or {}
        result={}
        for code in codes:
            row=index.get("common",{}).get(code)
            if row is not None:
                result[code]={**row,"source":{"store":"mercadona","url":f"https://tienda.mercadona.es/product/{self.products[code]}",
                    "revision":index["source_revision"],"observed_at":observed_at(index["source_updated_at"])}}
        return result

    async def async_load(self):
        saved=await self._store.async_load()
        if not isinstance(saved,dict):return
        try:
            index=validate_index(saved.get("index"))
            checked=saved.get("checked_at",0)
            next_attempt=saved.get("next_attempt",0)
            if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=time.time()+DAY for v in (checked,next_attempt)):
                raise ValueError("Invalid index cache time")
            etag=saved.get("etag","")
            if not isinstance(etag,str) or len(etag)>256 or any(ord(c)<32 for c in etag):raise ValueError("Invalid ETag")
            self._data.update(index=index,checked_at=checked,next_attempt=next_attempt,etag=etag,
                url=saved.get("url") if saved.get("url") in (URL,INITIAL_URL) else "")
            if not index["common_schema_version"]:self._data.update(checked_at=0,next_attempt=0,etag="")
        except (ValueError,TypeError):pass

    async def async_refresh(self):
        async with self._lock:
            now=time.time()
            if now<max(self._data["checked_at"]+DAY,self._data["next_attempt"]):return
            self._data["next_attempt"]=now+3600
            try:
                session=async_get_clientsession(self.hass)
                for url in (URL,INITIAL_URL):
                    headers={"If-None-Match":self._data["etag"]} if self._data["url"]==url and self._data["etag"] else {}
                    async with session.get(url,headers=headers,allow_redirects=False,timeout=ClientTimeout(total=30)) as response:
                        if response.status==404 and url==URL:continue
                        if response.status==304 and self.products:
                            self._data.update(checked_at=now,next_attempt=0)
                        elif response.status==200:
                            raw=bytearray()
                            async for chunk in response.content.iter_chunked(65536):
                                raw.extend(chunk)
                                if len(raw)>MAX_BYTES:raise ValueError("El índice público de Mercadona supera el tamaño permitido.")
                            index=await self.hass.async_add_executor_job(parse_index,bytes(raw))
                            etag=response.headers.get("ETag","")
                            if len(etag)>256 or any(ord(c)<32 for c in etag):etag=""
                            self._data.update(index=index,checked_at=now,next_attempt=0,etag=etag,url=url)
                        else:raise ValueError(f"Índice público de Mercadona: GitHub HTTP {response.status}.")
                        self.error=""
                        break
            except (ClientError,TimeoutError,OSError,ValueError) as err:
                self.error=str(err)[:500]
            await self._store.async_save(self._data)
