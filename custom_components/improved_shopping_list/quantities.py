"""Private per-list UID purchase quantities, independent of todo descriptions."""

import asyncio
from copy import deepcopy
from decimal import Decimal

from homeassistant.exceptions import HomeAssistantError

from homeassistant.components.todo import DATA_COMPONENT
from homeassistant.core import callback
from homeassistant.helpers.storage import Store

from .catalog import CatalogError, normalized_name
from .const import DOMAIN
from .quantity_values import normalize_purchase, positive_quantity, purchase_defaults


RECIPE_CONFIRM_DELAYS = (1, 4, 6)
RECIPE_CONFIRM_TIMEOUT = 30


class ListQuantities:
    def __init__(self, hass, catalog, settings, activity):
        self.hass, self.catalog, self.settings, self.activity = hass, catalog, settings, activity
        self._store = Store(hass, 1, f"{DOMAIN}.list_quantities")
        self._entries, self._listeners, self._lists, self._stops = {}, set(), {}, []
        self._active, self._dirty = False, False
        self._lock = asyncio.Lock()
        self._task = None

    async def async_load(self):
        saved = await self._store.async_load()
        if saved is not None:
            if not isinstance(saved, dict) or not isinstance(saved.get("entries"), dict):
                raise ValueError("No se han podido leer las cantidades de compra.")
            try:
                for entity, items in saved["entries"].items():
                    if not isinstance(entity, str) or not entity.startswith("todo.") or not isinstance(items, dict):
                        raise ValueError
                    for uid, record in items.items():
                        if not isinstance(uid, str) or not uid or not isinstance(record, dict):
                            raise ValueError
                        normalize_purchase({"purchase_unit": record["unit"], "unit_quantity": record["quantity"], "quantity_step": record["step"]})
            except (ValueError, TypeError, KeyError) as err:
                raise ValueError("No se han podido leer las cantidades de compra.") from err
            self._entries = saved["entries"]

    @property
    def snapshot(self):
        return {"entries": {entity: deepcopy(items) for entity, items in self._entries.items()
            if entity in self.settings.snapshot["entities"]}}

    @callback
    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    def value(self, entity_id, item, product=None):
        if product is None:
            product = next((p for p in self.catalog.products
                if normalized_name(p["name"]) == normalized_name(item.get("summary") or "")), None)
        defaults = purchase_defaults(product)
        record = self._entries.get(entity_id, {}).get(str(item.get("uid")))
        if record and product and record["unit"] != defaults["purchase_unit"]:
            record = None  # A changed product unit must not reinterpret an old quantity.
        return {"quantity": record["quantity"] if record else defaults["unit_quantity"],
            "unit": defaults["purchase_unit"] if product or not record else record["unit"],
            "step": defaults["quantity_step"] if product or not record else record.get("step", 1),
            "unit_quantity": defaults["unit_quantity"]}

    async def async_adjust(self, entity_id, uid, direction):
        async with self._lock:
            if not self._active or entity_id not in self.settings.snapshot["entities"]:
                raise CatalogError("Selecciona una lista de la compra añadida a la integración.")
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                raise CatalogError("La lista no está disponible.")
            if type(direction) is not int or direction not in (-1, 1):
                raise CatalogError("El ajuste debe aumentar o disminuir un paso.")
            result = await self.hass.services.async_call("todo", "get_items", {"entity_id": entity_id},
                blocking=True, return_response=True)
            if not self._active or entity_id not in self.settings.snapshot["entities"]:
                raise CatalogError("La lista ya no está disponible en la integración.")
            items = result.get(entity_id, {}).get("items") if isinstance(result, dict) else None
            item = next((item for item in items if str(item.get("uid")) == uid), None) if isinstance(items, list) else None
            if item is None:
                raise CatalogError("El producto ya no está en la lista. Actualiza la vista.", "not_found")
            value = self.value(entity_id, item)
            try:
                quantity = positive_quantity(round(value["quantity"] + direction * value["step"], 3))
            except ValueError as err:
                raise CatalogError(str(err)) from err
            entries = deepcopy(self._entries)
            entries.setdefault(entity_id, {})[uid] = {"quantity": quantity, "unit": value["unit"], "step": value["step"]}
            await self._store.async_save({"entries": entries})
            self._entries = entries
            self._notify()
            self.activity.record("list.quantity", f"Cantidad de compra: {item.get('summary', '')} · {quantity} {value['unit']}",
                source="manual", product=item.get("summary", ""), list_entity=entity_id,
                diagnostics={"quantity": quantity, "unit": value["unit"]})
            return self.snapshot

    async def async_add_recipe(self, recipe_id, revision, entity_id, operation_lock):
        """Add physical ingredient quantities, serializing with readers and quantity edits."""
        applied, confirmations = [], []
        stage = "validate"
        async with operation_lock, self._lock:
            recipe = next((item for item in self.catalog.recipes if item["id"] == recipe_id), None)
            if not recipe or recipe["revision"] != revision:
                raise CatalogError("La receta ha cambiado o ya no existe. Vuelve a abrirla.", "conflict")
            products = {product["id"]: product for product in self.catalog.products}
            for ingredient in recipe["ingredients"]:
                product = products.get(ingredient["product_id"])
                if product is None or purchase_defaults(product)["purchase_unit"] != ingredient["unit"]:
                    raise CatalogError("Hay ingredientes eliminados o con unidades distintas. Revisa la receta antes de añadirla.")
            async def read_items():
                state = self.hass.states.get(entity_id)
                if not self._active or entity_id not in self.settings.snapshot["entities"] or state is None or state.state in ("unknown", "unavailable"):
                    raise CatalogError("La lista de la compra no está disponible.")
                response = await self.hass.services.async_call("todo", "get_items", {"entity_id": entity_id}, blocking=True, return_response=True)
                items = response.get(entity_id, {}).get("items") if isinstance(response, dict) else None
                if not self._active or entity_id not in self.settings.snapshot["entities"] or not isinstance(items, list):
                    raise CatalogError("No se ha podido comprobar el contenido de la lista.")
                return items

            async def confirm_item(product):
                """Re-read after a write; never repeat an unconfirmed provider mutation."""
                confirmation = {"product_id": product["id"], "name": product["name"],
                                "reads": 0, "refreshes": 0, "confirmed": False}
                confirmations.append(confirmation)
                try:
                    async with asyncio.timeout(RECIPE_CONFIRM_TIMEOUT):
                        for delay in (0, *RECIPE_CONFIRM_DELAYS):
                            if delay:
                                await asyncio.sleep(delay)
                                # get_items only reads HA's cached list. Ask the native entity
                                # to refresh, respecting its provider/coordinator throttling.
                                await read_items()  # Recheck availability before refreshing.
                                component = self.hass.data.get(DATA_COMPONENT)
                                entity = component.get_entity(entity_id) if component else None
                                if entity is not None:
                                    confirmation["refreshes"] += 1
                                    await entity.async_update_ha_state(force_refresh=True)
                            items = await read_items()
                            confirmation["reads"] += 1
                            matches = [item for item in items if item.get("status") != "completed"
                                       and normalized_name(item.get("summary", "")) == normalized_name(product["name"])]
                            item = next((item for item in matches if item.get("uid")), None)
                            if item:
                                confirmation["confirmed"] = True
                                return item
                except TimeoutError:
                    confirmation["timed_out"] = True
                raise CatalogError(f"No se ha podido confirmar «{product['name']}» en la lista tras esperar al proveedor. "
                                   "Revisa los ingredientes y sus cantidades antes de volver a añadir la receta.")

            try:
                for ingredient in recipe["ingredients"]:
                    product = products[ingredient["product_id"]]
                    current = next((p for p in self.catalog.products if p["id"] == product["id"]), None)
                    if current is None or current["name"] != product["name"] or purchase_defaults(current)["purchase_unit"] != ingredient["unit"]:
                        raise CatalogError("Ha cambiado un ingrediente. Revisa la receta antes de continuar.")
                    stage = "read"
                    items = await read_items()
                    matches = [item for item in items if normalized_name(item.get("summary", "")) == normalized_name(product["name"])]
                    pending = next((item for item in matches if item.get("status") != "completed"), None)
                    amount = ingredient["quantity"]
                    if pending:
                        if not pending.get("uid"):
                            stage = "confirm"
                            pending = await confirm_item(product)
                        amount = positive_quantity(float(Decimal(str(self.value(entity_id, pending, product)["quantity"])) + Decimal(str(amount))))
                        item = pending
                    else:
                        completed = next((item for item in matches if item.get("uid")), None)
                        features = int(self.hass.states.get(entity_id).attributes.get("supported_features", 0))
                        stage = "write"
                        if completed and features & 4:
                            await self.hass.services.async_call("todo", "update_item", {"entity_id": entity_id, "item": completed["uid"], "status": "needs_action"}, blocking=True)
                        elif completed:
                            raise CatalogError("La lista no permite recuperar un ingrediente comprado sin duplicarlo.")
                        elif features & 1:
                            await self.hass.services.async_call("todo", "add_item", {"entity_id": entity_id, "item": product["name"]}, blocking=True)
                        else:
                            raise CatalogError("La lista no permite añadir ingredientes.")
                        stage = "confirm"
                        item = await confirm_item(product)
                    stage = "save_quantity"
                    entries = deepcopy(self._entries)
                    entries.setdefault(entity_id, {})[str(item["uid"])] = {"quantity": amount, "unit": ingredient["unit"], "step": purchase_defaults(product)["quantity_step"]}
                    try:
                        await self._store.async_save({"entries": entries})
                    except (OSError, HomeAssistantError) as err:
                        raise CatalogError("El ingrediente está en la lista, pero no se ha podido guardar su cantidad. Compruébala antes de reintentar.") from err
                    self._entries = entries
                    self._notify()
                    applied.append({"product_id": product["id"], "name": product["name"], "quantity": amount, "unit": ingredient["unit"]})
            except (CatalogError, HomeAssistantError, OSError, ValueError) as err:
                error = str(err)
                self.activity.record("list.recipe", f"Receta incompleta: {recipe['name']}", source="manual", list_entity=entity_id,
                                     diagnostics={"ingredients": applied, "error": error, "failed_product": product["name"],
                                                  "failed_product_id": product["id"], "stage": stage,
                                                  "confirmations": confirmations})
                return {"applied": applied, "error": error}
            self.activity.record("list.recipe", f"Receta añadida: {recipe['name']}", source="manual", list_entity=entity_id,
                                 diagnostics={"ingredients": applied, "confirmations": confirmations})
            return {"applied": applied, "error": ""}

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._stops = [self.settings.subscribe(self._changed), self.catalog.subscribe(self._changed),
            self.hass.bus.async_listen("state_changed", self._state_changed)]
        self._changed()

    @callback
    def _state_changed(self, event):
        if event.data.get("entity_id") in self.settings.snapshot["entities"]:
            self._changed()

    @callback
    def _changed(self, *_args):
        if not self._active:
            return
        component = self.hass.data.get(DATA_COMPONENT)
        wanted = set(self.settings.snapshot["entities"])
        for entity_id in tuple(self._lists):
            entity = component.get_entity(entity_id) if component else None
            if entity_id not in wanted or entity is not self._lists[entity_id][0]:
                self._lists.pop(entity_id)[1]()
        if component:
            for entity_id in wanted - self._lists.keys():
                entity = component.get_entity(entity_id)
                if entity is not None:
                    self._lists[entity_id] = (entity, entity.async_subscribe_updates(self._changed))
        self._dirty = True
        if not self._task or self._task.done():
            self._task = self.hass.async_create_background_task(self._clean(), "Shopping list quantity cleanup")

    async def _clean(self):
        while self._active and self._dirty:
            self._dirty = False
            async with self._lock:
                entries = deepcopy(self._entries)
                products = {normalized_name(product["name"]): product for product in self.catalog.products}
                for entity_id, (entity, _) in self._lists.items():
                    state = self.hass.states.get(entity_id)
                    if entity.todo_items is None or not state or state.state in ("unknown", "unavailable"):
                        continue
                    current = {str(item.uid): item for item in entity.todo_items if item.uid}
                    records = entries.get(entity_id, {})
                    for uid in tuple(records):
                        product = products.get(normalized_name(current[uid].summary or "")) if uid in current else None
                        if uid not in current or product and records[uid]["unit"] != purchase_defaults(product)["purchase_unit"]:
                            del records[uid]
                    if not records:
                        entries.pop(entity_id, None)
                if entries != self._entries:
                    await self._store.async_save({"entries": entries})
                    self._entries = entries
                self._notify()

    async def async_stop(self):
        self._active = False
        for stop in self._stops:
            stop()
        self._stops = []
        for _, stop in self._lists.values():
            stop()
        self._lists.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
