"""Local meal routines and presence-based pantry consumption, without backfilling."""
import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta
import logging
import math
import re
from uuid import uuid4

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .catalog import CatalogError
from .const import DOMAIN

_LOGGER=logging.getLogger(__name__)
ID=re.compile(r"[a-zA-Z0-9_-]{1,64}")
PERSON=re.compile(r"person\.[a-z0-9_]+")


def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):raise CatalogError("El identificador de la rutina o comida no es válido.")
    return value


def normalize_rules(data):
    from .stock import quantity_value
    if not isinstance(data,list) or len(data)>100:raise CatalogError("Puedes seleccionar hasta 100 comidas por producto.")
    result=[];seen=set()
    for raw in data:
        if not isinstance(raw,dict) or set(raw)-{'person_amounts'}!={'routine_id','meal_id','amount'}:raise CatalogError("El consumo por comidas no es válido.")
        key=(identifier(raw['routine_id']),identifier(raw['meal_id']))
        if key in seen:raise CatalogError("Una comida no puede seleccionarse dos veces para el mismo producto.")
        seen.add(key);people=raw.get('person_amounts',{})
        if not isinstance(people,dict) or len(people)>30 or any(not isinstance(p,str) or not PERSON.fullmatch(p) for p in people):raise CatalogError("Las cantidades por persona no son válidas.")
        result.append({'routine_id':key[0],'meal_id':key[1],'amount':quantity_value(raw['amount'],positive=True),
                       'person_amounts':{p:quantity_value(n) for p,n in people.items()}})
    return result


def normalize_routine(data,current=None):
    if not isinstance(data,dict) or set(data)-{'id','revision','minimum_minutes'}!={'name','persons','enabled','meals'}:raise CatalogError("La rutina no es válida.")
    name=data['name'];people=data['persons'];meals=data['meals']
    if not isinstance(name,str) or not name.strip() or len(name)>100 or any(ord(c)<32 for c in name):raise CatalogError("Indica un nombre de rutina válido.")
    if not isinstance(people,list) or not 1<=len(people)<=30 or any(not isinstance(p,str) or not PERSON.fullmatch(p) for p in people):raise CatalogError("Selecciona al menos una persona de Home Assistant.")
    if type(data['enabled']) is not bool:raise CatalogError("Selecciona si la rutina está activada.")
    if 'minimum_minutes' in data and (type(data['minimum_minutes']) is not int or not 0<=data['minimum_minutes']<=240):raise CatalogError("La configuración anterior de la rutina no es válida.")
    if not isinstance(meals,list) or not 1<=len(meals)<=20:raise CatalogError("Añade entre 1 y 20 comidas a la rutina.")
    rows=[];seen=set()
    for raw in meals:
        if not isinstance(raw,dict) or set(raw) not in ({'id','name','time','days','enabled'},{'id','name','start_time','end_time','days','enabled'}):raise CatalogError("La comida no es válida.")
        mid=identifier(raw['id']);label=raw['name'];days=raw['days']
        if mid in seen:raise CatalogError("Hay comidas con el mismo identificador.")
        seen.add(mid)
        if not isinstance(label,str) or not label.strip() or len(label)>80 or any(ord(c)<32 for c in label):raise CatalogError("Indica el nombre de cada comida.")
        start=raw.get('start_time',raw.get('time'));end=raw.get('end_time')
        if not isinstance(start,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',start):raise CatalogError("Indica una hora de inicio válida para cada comida.")
        if 'time' in raw:
            previous=next((m for m in (current or {}).get('meals',[]) if m['id']==mid),{})
            # An older open editor must not erase a window when saving other fields.
            if previous.get('start_time')==start:end=previous['end_time']
            else:
                hour,minute=map(int,start.split(':'));end=f'{(hour+1)%24:02d}:{minute:02d}'
        if not isinstance(end,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',end) or start==end:raise CatalogError("Indica una hora final distinta del inicio para cada comida.")
        if not isinstance(days,list) or not days or any(type(d) is not int or not 0<=d<=6 for d in days) or type(raw['enabled']) is not bool:raise CatalogError("Selecciona los días de cada comida.")
        rows.append({'id':mid,'name':label.strip(),'start_time':start,'end_time':end,'days':sorted(set(days)),'enabled':raw['enabled']})
    return {'id':current['id'] if current else str(uuid4()),'revision':(current or {}).get('revision',0)+1,
            'name':name.strip(),'persons':list(dict.fromkeys(people)),'enabled':data['enabled'],'meals':rows,
            'updated_at':dt_util.utcnow().timestamp()}


class MealRoutines:
    def __init__(self,hass,stock,activity):
        self.hass=hass;self.stock=stock;self.activity=activity
        self._store=Store(hass,1,f'{DOMAIN}.meal_routines');self._routines={};self._listeners=set()
        self._lock=asyncio.Lock();self._check_lock=asyncio.Lock();self._active=False;self._stops=[];self._task=None;self._presence={}

    async def async_load(self):
        data=await self._store.async_load()
        if data is not None:
            if not isinstance(data,dict) or not isinstance(data.get('routines'),dict):raise CatalogError("No se han podido leer las rutinas.")
            if len(data['routines'])>100:raise CatalogError("El archivo de rutinas no es válido.")
            normalized={}
            for key,row in data['routines'].items():
                identifier(key)
                if not isinstance(row,dict) or row.get('id')!=key or type(row.get('revision')) is not int or row['revision']<1 or type(row.get('updated_at')) not in (int,float) or not math.isfinite(row['updated_at']):raise CatalogError("El archivo de rutinas no es válido.")
                normalized[key]={**normalize_routine({k:v for k,v in row.items() if k!='updated_at'},row),'id':row['id'],'revision':row['revision'],'updated_at':row['updated_at']}
            if normalized!=data['routines']:await self._store.async_save({'routines':normalized})
            self._routines=normalized

    @property
    def snapshot(self):return {'routines':deepcopy(sorted(self._routines.values(),key=lambda r:r['name'].casefold()))}

    @callback
    def subscribe(self,listener):
        self._listeners.add(listener)
        return lambda:self._listeners.discard(listener)

    async def async_save(self,data):
        async with self._lock:
            if not isinstance(data,dict):raise CatalogError("La rutina no es válida.")
            if 'id' in data:identifier(data['id'])
            current=self._routines.get(data.get('id')) if isinstance(data,dict) else None
            if isinstance(data,dict) and data.get('id') and (not current or type(data.get('revision')) is not int or data['revision']!=current['revision']):raise CatalogError("La rutina ha cambiado. Vuelve a abrirla.",'conflict')
            if not current and len(self._routines)>=100:raise CatalogError("Se ha alcanzado el máximo de 100 rutinas.")
            row=normalize_routine(data,current);rows={**self._routines,row['id']:row}
            await self._store.async_save({'routines':rows});self._routines=rows
        self._seed_presence();self._queue()
        for listener in tuple(self._listeners):listener()
        if self.activity:self.activity.record('stock.routine.saved',f'Rutina guardada: {row["name"]}',source='manual')
        return deepcopy(row)

    async def async_delete(self,routine_id,revision):
        async with self._lock:
            current=self._routines.get(routine_id)
            if not current or type(revision) is not int or revision!=current['revision']:raise CatalogError("La rutina ha cambiado. Vuelve a abrirla.",'conflict')
            rows={key:value for key,value in self._routines.items() if key!=routine_id}
            await self._store.async_save({'routines':rows});self._routines=rows
        for listener in tuple(self._listeners):listener()

    def _seed_presence(self):
        for routine in self._routines.values():
            for person in routine['persons']:
                if person not in self._presence and (state:=self.hass.states.get(person)):
                    self._presence[person]=deque([(state.last_changed.timestamp(),state.state)],maxlen=256)

    @callback
    def _state_changed(self,event):
        person=event.data.get('entity_id','')
        if person not in self._presence and not any(person in r['persons'] for r in self._routines.values()):return
        history=self._presence.setdefault(person,deque(maxlen=256));old=event.data.get('old_state');new=event.data.get('new_state')
        if not history and old:history.append((old.last_changed.timestamp(),old.state))
        if new and (not old or old.state!=new.state):
            history.append((new.last_changed.timestamp(),new.state));self._queue()
        elif not new:
            history.append((dt_util.utcnow().timestamp(),'unavailable'));self._queue()

    def _home_between(self,person,start,end):
        self._seed_presence()
        history=list(self._presence.get(person,()))
        for index,(stamp,state) in enumerate(history):
            stop=history[index+1][0] if index+1<len(history) else end
            if state=='home' and stamp<end and stop>start:
                return max(stamp,start)
        return None

    @callback
    def start(self):
        if self._active:return
        self._active=True;self._started_at=dt_util.utcnow().timestamp();self._presence={};self._seed_presence()
        self._stops=[async_track_time_interval(self.hass,self._queue,timedelta(seconds=30)),self.hass.bus.async_listen('state_changed',self._state_changed),self.stock.subscribe(self._queue)]
        self._queue()

    @callback
    def _queue(self,*_args):
        if not self._active:return
        self._dirty=True
        if not self._task or self._task.done():self._task=self.hass.async_create_background_task(self._drain(),'Shopping meal routines')

    async def _drain(self):
        try:
            while self._active and self._dirty:
                self._dirty=False
                await self.async_check()
        except Exception:_LOGGER.exception('Could not evaluate meal windows')

    async def async_check(self):
        async with self._check_lock:
            if not self._active:return
            now=dt_util.now();stamp=now.timestamp()
            for item in self.stock.snapshot['items']:
                if item.get('mode')!='meals' or not item.get('configured') or not self.stock.recurrence_ready(item):continue
                events=[]
                for rule in item.get('meal_rules',[]):
                    routine=self._routines.get(rule['routine_id'])
                    if not routine or not routine['enabled']:continue
                    meal=next((m for m in routine['meals'] if m['id']==rule['meal_id']),None)
                    if not meal or not meal['enabled']:continue
                    for day in (now.date(),now.date()-timedelta(days=1)):
                        if day.weekday() not in meal['days']:continue
                        start=datetime.combine(day,datetime.strptime(meal['start_time'],'%H:%M').time(),tzinfo=now.tzinfo)
                        end=datetime.combine(day,datetime.strptime(meal['end_time'],'%H:%M').time(),tzinfo=now.tzinfo)
                        if end<=start:end+=timedelta(days=1)
                        if stamp<start.timestamp() or stamp>=end.timestamp()+90:continue
                        observed_start=max(start.timestamp(),self._started_at,routine['updated_at'],item.get('meal_config_at',0))
                        observed_end=min(end.timestamp(),stamp+0.000001)
                        if observed_start>=observed_end:continue
                        for person in routine['persons']:
                            at=self._home_between(person,observed_start,observed_end)
                            amount=rule.get('person_amounts',{}).get(person,rule['amount'])
                            if at is not None and amount>0:
                                events.append({'key':'|'.join([item['id'],routine['id'],meal['id'],person,day.isoformat()]),
                                    'at':at,'person':person,'meal':meal['name'],'routine':routine['name'],'amount':amount,
                                    'window_start':start.isoformat(),'window_end':end.isoformat()})

                if events:
                    try:await self.stock.async_meals(item['id'],item['config_revision'],events)
                    except (OSError,CatalogError):_LOGGER.exception('Could not persist meal consumption for %s',item['name'])

    async def async_stop(self):
        self._active=False
        for stop in self._stops:stop()
        self._stops=[]
        if self._task and not self._task.done():
            self._task.cancel();await asyncio.gather(self._task,return_exceptions=True)
        self._task=None;self._presence={}
