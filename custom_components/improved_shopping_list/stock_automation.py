"""Observed usage, purchase replenishment and perishable pantry expiration."""

import asyncio
from collections import deque
from datetime import timedelta
import logging
import time
from uuid import uuid4

from homeassistant.components.todo import DATA_COMPONENT, serialize_todo_item
from homeassistant.core import Context, callback
from homeassistant.helpers.event import async_track_time_interval

from .catalog import normalized_name
from .stock import stock_needs_reorder

_LOGGER = logging.getLogger(__name__)


class StockAutomation:
    def __init__(self, hass, stock, settings, activity, operation_lock):
        self.hass, self.stock, self.settings, self.activity = hass, stock, settings, activity
        self._operation_lock = operation_lock
        self._active = False
        self._stops, self._lists, self._snapshots = [], {}, {}
        self._events = deque()
        self._retry_after = {}
        self._task = None
        self._lock = asyncio.Lock()

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._stops = [self.stock.subscribe(self._queue), self.settings.subscribe(self._settings_changed),
            self.hass.bus.async_listen("state_changed",self._state_changed),
            async_track_time_interval(self.hass,self._queue,timedelta(minutes=1))]
        self._settings_changed()

    @callback
    def _settings_changed(self):
        self._sync_lists()
        self._queue()

    @callback
    def _sync_lists(self):
        component = self.hass.data.get(DATA_COMPONENT)
        wanted = set(self.settings.snapshot["entities"])
        for entity_id in tuple(self._lists):
            entity = component.get_entity(entity_id) if component else None
            if entity_id not in wanted or entity is not self._lists[entity_id][0]:
                self._lists.pop(entity_id)[1]()
                self._snapshots.pop(entity_id,None)
        if component:
            for entity_id in wanted-self._lists.keys():
                entity = component.get_entity(entity_id)
                if entity is not None:
                    self._list_changed(entity_id,entity.todo_items)
                    self._lists[entity_id] = (entity,entity.async_subscribe_updates(
                        lambda items, key=entity_id:self._list_changed(key,items)))

    @callback
    def _list_changed(self, entity_id, items):
        if not self._active or items is None:
            return
        current = {str(item.uid):serialize_todo_item(item) for item in items if item.uid}
        previous = self._snapshots.get(entity_id)
        self._snapshots[entity_id] = current
        # Existing completed entries are a baseline, including on reconnect/restart.
        if previous is not None:
            for uid,item in current.items():
                if (previous.get(uid,{}).get("status") == "needs_action"
                    and item.get("status") == "completed"):
                    detection = getattr(self,"purchase_detection",None)
                    if detection and detection.enabled:
                        quantity = self.quantities.value(entity_id,item) if getattr(self,"quantities",None) else None
                        detection.note_completion(entity_id,item,quantity)
                    elif getattr(self,"carrefour_account",None):
                        self.carrefour_account.note_completion()
                    for stock in self.stock.snapshot["items"]:
                        if (stock.get("configured") or getattr(self, "quantities", None)) and normalized_name(stock["name"]) == normalized_name(item.get("summary", "")):
                            quantity = self.quantities.value(entity_id, item) if getattr(self, "quantities", None) else None
                            self._events.append((stock["id"],stock["config_revision"],"purchase",
                                {"id":str(uuid4()), "at":time.time(), "list_entity":entity_id, "uid":uid,
                                 **({"purchase_quantity": quantity["quantity"], "purchase_unit": quantity["unit"]} if quantity else {})}))
        self._queue()

    @callback
    def _state_changed(self, event):
        if not self._active:
            return
        entity_id = event.data.get("entity_id", "")
        if entity_id.startswith("todo."):
            self._sync_lists()
        old,new = event.data.get("old_state"),event.data.get("new_state")
        # Attribute updates, startup and availability restoration are not uses.
        if not old or not new or old.state in ("unknown","unavailable") or old.state == new.state:
            return
        for item in self.stock.snapshot["items"]:
            if (item.get("configured") and item.get("mode") == "usage" and item.get("usage_entity") == entity_id
                and item.get("usage_state") == new.state):
                self._events.append((item["id"],item["config_revision"],"usage"))
        if self._events:
            self._queue()

    @callback
    def _queue(self, *_args):
        if not self._active:
            return
        self._dirty = True
        if not self._task or self._task.done():
            self._task = self.hass.async_create_background_task(self._drain(),"Shopping stock automation")

    async def _drain(self):
        try:
            while self._active and self._dirty:
                self._dirty = False
                await self.async_check()
        except Exception:
            _LOGGER.exception("Could not process pantry automation")

    async def async_stop(self):
        self._active = False
        for stop in self._stops:
            stop()
        self._stops = []
        for _,stop in self._lists.values():
            stop()
        self._lists.clear();self._snapshots.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task,return_exceptions=True)
        self._task = None
        self._events.clear();self._retry_after.clear()

    def _error(self, key, item, err):
        self._retry_after[key] = time.time()+300
        self.activity.record("stock.error",f'{item["name"]}: no se pudo actualizar Stock',source="automatic",
            product=item["name"],error=str(err))

    async def async_check(self):
        async with self._lock:
            if not self._active:
                return
            self._sync_lists()
            for _ in range(len(self._events)):
                event = self._events.popleft()
                if not self._active:
                    return
                key = ("event",event[0])
                if self._retry_after.get(key,0)>time.time():
                    self._events.append(event);continue
                try:
                    await self.stock.async_automatic(*event)
                except Exception as err:
                    self._events.append(event)
                    item = next((i for i in self.stock.snapshot["items"] if i["id"]==event[0]),{"name":"Producto eliminado"})
                    self._error(key,item,err)
            for item in self.stock.snapshot["items"]:
                if not self._active:
                    return
                if not item.get("configured") or not self.stock.recurrence_ready(item):
                    continue
                key = ("reorder",item["id"])
                if self._retry_after.get(key,0)>time.time():
                    continue
                try:
                    if item.get("mode") == "perishable" and item.get("expires_at",0) and time.time()>=item["expires_at"]:
                        item = await self.stock.async_automatic(item["id"],item["config_revision"],"expire")
                    if item and self._needs_reorder(item):
                        async with self._operation_lock:
                            async with asyncio.timeout(30):
                                await self._add_or_restore(item)
                except Exception as err:
                    self._error(key,item,err)

    @staticmethod
    def _needs_reorder(item):
        return stock_needs_reorder(item, time.time())

    def _validate(self, item, target):
        current = next((i for i in self.stock.snapshot["items"] if i["id"] == item["id"]),None)
        if (not self._active or not current or current["revision"] != item["revision"] or not self.stock.recurrence_ready(current)
            or not self._needs_reorder(current) or current["name"] != item["name"]
            or target != (current.get("list_entity") or self.settings.snapshot["primary_entity"])
            or target not in self.settings.snapshot["entities"]):
            raise ValueError("El stock o la lista de reposición han cambiado.")
        state = self.hass.states.get(target)
        if state is None or state.state in ("unknown","unavailable"):
            raise ValueError("La lista de reposición no está disponible.")
        return state

    async def _add_or_restore(self, item):
        if any(event[0] == item["id"] and event[2] == "purchase" for event in self._events):
            return  # Process the observed purchase before deciding whether to reorder.
        target = item.get("list_entity") or self.settings.snapshot["primary_entity"]
        self._validate(item,target)
        response = await self.hass.services.async_call("todo","get_items",{"entity_id":target},blocking=True,return_response=True)
        if any(event[0] == item["id"] and event[2] == "purchase" for event in self._events):
            return
        state = self._validate(item,target)
        items = response.get(target,{}).get("items") if isinstance(response,dict) else None
        if not isinstance(items,list):
            raise ValueError("No se ha podido comprobar el contenido de la lista de reposición.")
        matches = [entry for entry in items if normalized_name(entry.get("summary", "")) == normalized_name(item["name"])]
        if any(entry.get("status") != "completed" for entry in matches):
            return
        completed = next((entry for entry in matches if entry.get("uid") and entry.get("status") == "completed"),None)
        features = int(state.attributes.get("supported_features",0))
        context = Context(parent_id=Context().id)
        if completed:
            if not features & 4:
                raise ValueError("La lista no permite recuperar el producto comprado sin duplicarlo.")
            await self.hass.services.async_call("todo","update_item",{"entity_id":target,"item":completed["uid"],"status":"needs_action"},blocking=True,context=context)
        elif matches:
            raise ValueError("La lista no devuelve un identificador válido para recuperar el producto.")
        elif features & 1:
            await self.hass.services.async_call("todo","add_item",{"entity_id":target,"item":item["name"]},blocking=True,context=context)
        else:
            raise ValueError("La lista no permite añadir productos.")
        self.activity.record("stock.reorder",f'Reposición automática: {item["name"]}',source="automatic",product=item["name"],list_entity=target)
