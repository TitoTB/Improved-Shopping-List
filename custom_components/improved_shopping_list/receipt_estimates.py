"""Private, bounded cache of unconfirmed receipt quantity proposals."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import logging
import math
import time

from .const import DOMAIN

_LOGGER=logging.getLogger(__name__)
TTL=30*86400
LIMIT=2000


def estimate_key(receipt,line,product_id,reference,rate):
    if not reference or not rate:return None
    data={"receipt":{key:receipt.get(key) for key in ("store","id","digest","account_key","purchased_at","total","currency")},
          "line":{key:line.get(key) for key in ("id","description","ean","reference_id","count","amount","gross_amount","unit_price")},
          "product":product_id,"option":{key:reference.get(key) for key in ("store","ean","reference_id","url","sale_mode","content_quantity","content_unit","content_confirmed","pack_count")},
          "rate":{key:rate.get(key) for key in ("price","quantity","unit","currency")}}
    return sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def valid_entry(key,entry):
    if not isinstance(key,str) or len(key)!=64 or any(c not in '0123456789abcdef' for c in key) or not isinstance(entry,dict):return False
    result=entry.get('result');expires=entry.get('expires')
    return (type(expires) in (int,float) and math.isfinite(expires) and time.time()<expires<=time.time()+TTL+60
            and isinstance(result,dict) and type(result.get('quantity')) in (int,float)
            and math.isfinite(result['quantity']) and 0<result['quantity']<=1000000
            and result.get('unit') in ('kg','g','l','ml','cl','uds') and result.get('estimated') is True)


class ReceiptEstimates:
    def __init__(self,hass,*,store=None):
        self._errors=(OSError,ValueError)
        self._hass=hass;self._store=store;self._entries={};self._loaded=False;self._lock=asyncio.Lock()

    async def _load(self):
        if self._loaded:return
        if self._store is None:
            from homeassistant.helpers.storage import Store
            from homeassistant.exceptions import HomeAssistantError
            self._errors=(*self._errors,HomeAssistantError)
            self._store=Store(self._hass,1,f'{DOMAIN}.receipt_quantity_cache')
        try:
            data=await self._store.async_load()
            if isinstance(data,dict):self._entries={key:entry for key,entry in list(data.items())[-LIMIT:] if valid_entry(key,entry)}
        except self._errors:_LOGGER.warning('Could not load optional receipt quantity cache')
        self._loaded=True

    async def get(self,key):
        if not key:return None
        async with self._lock:
            await self._load();entry=self._entries.get(key)
            return deepcopy(entry['result']) if valid_entry(key,entry) else None

    async def put(self,key,result):
        if not key:return
        entry={'expires':time.time()+TTL,'result':{field:result[field] for field in ('quantity','unit','estimated')}}
        if not valid_entry(key,entry):return
        async with self._lock:
            await self._load()
            self._entries.pop(key,None);self._entries[key]=entry
            self._entries={key:value for key,value in list(self._entries.items())[-LIMIT:] if valid_entry(key,value)}
            try:await self._store.async_save(self._entries)
            except self._errors:_LOGGER.warning('Could not save optional receipt quantity cache')
