"""Store-independent public EAN facts, cached locally and never uploading data."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json
import math
import re
import time

from aiohttp import ClientError,ClientTimeout
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later,async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .ean_common import validate,observed_at
from .ean_links import product_eans,DAY
from .product_references import gtin

URL='https://raw.githubusercontent.com/TitoTB/Improved-Shopping-List/data/catalogs/ean-common.json'
INITIAL_URL='https://raw.githubusercontent.com/TitoTB/Improved-Shopping-List/main/data/ean-common.json'
MAX_BYTES=8*1024*1024


def validate_index(data):
    if not isinstance(data,dict) or type(data.get('schema_version')) is not int or data['schema_version']!=1 or not re.fullmatch(r'[a-f0-9]{40}',str(data.get('revision',''))):raise ValueError('Invalid common EAN index')
    observed_at(data.get('updated_at'))
    products=data.get('products')
    if not isinstance(products,dict) or not 1<=len(products)<=100000:raise ValueError('Invalid common EAN entries')
    clean={}
    for code,row in products.items():
        if gtin(code)!=code or not code or not isinstance(row,dict):raise ValueError('Invalid common EAN record')
        origins=row.get('origins',[])
        if not isinstance(origins,list) or len(origins)>50 or any(not isinstance(s,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',s) for s in origins):raise ValueError('Invalid common EAN origins')
        clean[code]=validate({key:value for key,value in row.items() if key!='origins'})
    return {'schema_version':1,'revision':data['revision'],'updated_at':data['updated_at'],'products':clean}


def parse_index(raw):
    if len(raw)>MAX_BYTES:raise ValueError('Common EAN index is too large')
    return validate_index(json.loads(raw))


class CommonEANIndex:
    def __init__(self,hass,catalog):
        self.hass,self.catalog=hass,catalog
        self._store=Store(hass,1,f'{DOMAIN}.ean_common_index');self._data={'index':None,'checked_at':0,'next_attempt':0,'etag':'','url':''}
        self._lock=asyncio.Lock();self._active=False;self._dirty=False;self._task=self._timer=None;self._stops=[];self.error=''

    async def async_load(self):
        try:saved=await self._store.async_load()
        except (OSError,HomeAssistantError):return
        if not isinstance(saved,dict):return
        try:
            index=validate_index(saved.get('index'))
            for key in ('checked_at','next_attempt'):
                if type(saved.get(key)) not in (int,float) or not math.isfinite(saved[key]) or not 0<=saved[key]<=time.time()+DAY:raise ValueError('Invalid cache date')
            etag=saved.get('etag','')
            if not isinstance(etag,str) or len(etag)>256 or any(ord(c)<32 for c in etag):raise ValueError('Invalid cache ETag')
            self._data.update(index=index,checked_at=saved['checked_at'],next_attempt=saved['next_attempt'],etag=etag,url=saved.get('url') if saved.get('url') in (URL,INITIAL_URL) else '')
        except (ValueError,TypeError):pass

    def entries(self,codes):
        index=self._data['index']
        if not index:return {}
        provenance={'store':'community','url':INITIAL_URL,'revision':index['revision'],'observed_at':observed_at(index['updated_at'])}
        return {code:{**deepcopy(index['products'][code]),'source':dict(provenance)} for code in codes if code in index['products']}

    async def async_refresh(self):
        async with self._lock:
            now=time.time()
            if now<max(self._data['checked_at']+DAY,self._data['next_attempt']):return
            self._data['next_attempt']=now+DAY
            try:
                for url in (URL,INITIAL_URL):
                    headers={'If-None-Match':self._data['etag']} if self._data['url']==url and self._data['etag'] else {}
                    async with async_get_clientsession(self.hass).get(url,headers=headers,allow_redirects=False,timeout=ClientTimeout(total=25)) as response:
                        if response.status==404 and url==URL:continue
                        if response.status==304 and self._data['index']:
                            self._data.update(checked_at=now,next_attempt=0)
                        elif response.status==200:
                            raw=bytearray()
                            async for chunk in response.content.iter_chunked(65536):
                                raw.extend(chunk)
                                if len(raw)>MAX_BYTES:raise ValueError('Common EAN index is too large')
                            index=await self.hass.async_add_executor_job(parse_index,bytes(raw))
                            etag=response.headers.get('ETag','')
                            if len(etag)>256 or any(ord(c)<32 for c in etag):etag=''
                            self._data.update(index=index,checked_at=now,next_attempt=0,etag=etag,url=url)
                        else:raise ValueError(f'Common EAN index: GitHub HTTP {response.status}')
                        self.error='';break
            except (ClientError,TimeoutError,OSError,ValueError) as err:self.error=str(err)[:500]
            try:await self._store.async_save(self._data)
            except (OSError,HomeAssistantError) as err:self.error=str(err)[:500]

    async def async_hint(self,code):
        code=gtin(code)
        if not code:return {}
        await self.async_refresh()
        return {key:value for key,value in self.entries({code}).get(code,{}).items() if key!='source'}

    def start(self):
        if self._active:return
        self._active=True;self._stops=[self.catalog.subscribe(self._queue),async_track_time_interval(self.hass,self._queue,timedelta(hours=1))];self._queue()

    @callback
    def _queue(self,*_args):
        if not self._active:return
        self._dirty=True
        if self._timer is None and (self._task is None or self._task.done()):self._timer=async_call_later(self.hass,1,self._launch)

    @callback
    def _launch(self,*_args):
        self._timer=None
        if self._active:self._task=self.hass.async_create_background_task(self._drain(),'Shopping common EAN dictionary')

    async def _drain(self):
        while self._active and self._dirty:
            self._dirty=False
            codes={code for product in self.catalog.products for code in product_eans(product)}
            if codes:
                await self.async_refresh()
                try:await self.catalog.async_apply_common_ean_data(self.entries(codes))
                except (ValueError,OSError,HomeAssistantError) as err:self.error=str(err)[:500]

    async def async_stop(self):
        self._active=False
        if self._timer:self._timer();self._timer=None
        for stop in self._stops:stop()
        self._stops=[]
        if self._task and not self._task.done():self._task.cancel();await asyncio.gather(self._task,return_exceptions=True)
