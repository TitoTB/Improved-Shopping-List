"""Private receipt previews and atomic stock/history confirmation."""

import asyncio
import base64
import binascii
from copy import deepcopy
from difflib import SequenceMatcher
import time
from uuid import uuid4

from homeassistant.util import dt as dt_util

from .catalog import CatalogError, normalized_name
from .receipt_parser import MAX_PDF_BYTES, extract_receipt
from .stock import DAY, DEFAULT_CONFIG, quantity_value


def converted_quantity(line, unit):
    if unit == "uds":
        return line["count"]
    scales = {"g":("mass",1), "kg":("mass",1000), "ml":("volume",1), "cl":("volume",10), "l":("volume",1000)}
    source, target = scales.get(line["pack_unit"]), scales.get(unit)
    if source and target and source[0] == target[0] and line["pack_quantity"]:
        return round(line["count"] * line["pack_quantity"] * source[1] / target[1], 3)
    return None


class ReceiptManager:
    def __init__(self, hass, stock, automation, prices):
        self.hass, self.stock, self.automation, self.prices = hass, stock, automation, prices
        self._drafts = {}
        self._parse_lock = asyncio.Lock()

    @property
    def snapshot(self):
        return {"receipts":sorted(deepcopy(list(self.stock.receipts["history"].values())),
            key=lambda receipt:receipt["purchased_at"], reverse=True)}

    def _check_duplicate(self, receipt):
        if any(old["id"] == receipt["id"] or old["digest"] == receipt["digest"] for old in self.stock.receipts["history"].values()):
            raise CatalogError("Este ticket ya se ha importado. Puedes consultarlo en Últimas compras.", "duplicate")

    def _draft(self, token, owner):
        draft = self._drafts.get(token)
        if not draft or draft["owner"] != owner or draft["expires"] <= time.time():
            raise CatalogError("La revisión ha caducado. Vuelve a subir el ticket.", "expired")
        return draft

    def _choices(self, store):
        choices = []
        for product in self.stock.catalog.products:
            stock = self.stock.item_for(product)
            offers = self.prices.prices_for(product) if hasattr(self.prices,"prices_for") else []
            price = next((offer for offer in offers if offer["store"] == store),None)
            choices.append({"id":product["id"],"name":product["name"],"unit":stock["unit"] if stock else "uds",
                "stock_id":stock["id"] if stock else "","revision":stock["revision"] if stock else 0,
                "price":price.get("price") if price else None,"price_date":price.get("checked_at",0) if price else 0})
        return choices

    async def async_options(self, token, owner):
        draft = self._draft(token,owner)
        await self.automation.async_check()
        draft["products"] = self._choices(draft["receipt"]["store"])
        purchases = [p for p in self.stock.receipts["purchases"].values() if not p.get("receipt_id") and p.get("at",0)>time.time()-30*DAY]
        return {"products":deepcopy(draft["products"]),"purchases":deepcopy(purchases)}

    def _links(self, receipt, selections):
        if not isinstance(selections,list) or len(selections) != len(receipt["lines"]):
            raise CatalogError("Revisa todas las vinculaciones del ticket.")
        seen, products, result = set(), set(), []
        for selection in selections:
            if not isinstance(selection,dict) or set(selection) != {"id","product_id"} or any(not isinstance(value,str) or len(value)>200 for value in selection.values()):
                raise CatalogError("Las vinculaciones no son válidas.")
            line = next((line for line in receipt["lines"] if line["id"] == selection["id"]),None)
            if not line or line["id"] in seen:
                raise CatalogError("Las vinculaciones no son válidas.")
            seen.add(line["id"])
            product = next((p for p in self.stock.catalog.products if p["id"] == selection["product_id"]),None)
            if selection["product_id"] and not product:
                raise CatalogError("Un producto del catálogo ha cambiado. Revisa su vinculación.","conflict")
            if product:
                if product["id"] in products:
                    raise CatalogError("Dos líneas del mismo ticket no pueden vincularse al mismo producto del catálogo.")
                products.add(product["id"])
            result.append((line,product))
        return result

    @staticmethod
    def _remember_alias(data, store, line, product):
        key = store+":"+normalized_name(line["description"])
        if data["aliases"].get(key,{}).get("product_id") != product["id"]:
            data["aliases"][key] = {"product_id":product["id"],"per_unit":None,"unit":""}

    async def async_link(self, token, owner, selections):
        draft = self._draft(token,owner)
        async with self.stock._lock:
            linked = self._links(draft["receipt"],selections)
            data = deepcopy(self.stock.receipts)
            for line,product in linked:
                if product:
                    self._remember_alias(data,draft["receipt"]["store"],line,product)
            await self.stock._persist(deepcopy(self.stock._items),receipts=data)
        return await self.async_options(token,owner)

    async def async_preview(self, encoded, owner):
        if len(encoded) > (MAX_PDF_BYTES + 2) // 3 * 4:
            raise CatalogError("Sube un PDF de hasta 2 MB.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as err:
            raise CatalogError("El archivo no es un PDF válido.") from err
        if self._parse_lock.locked():
            raise CatalogError("Ya se está leyendo un ticket. Espera a que termine.")
        async with self._parse_lock:
            receipt = await self.hass.async_add_executor_job(extract_receipt, content)
        self._check_duplicate(receipt)
        await self.automation.async_check()
        choices = self._choices(receipt["store"])
        used = set()
        for line in receipt["lines"]:
            alias = self.stock.receipts["aliases"].get(receipt["store"]+":"+normalized_name(line["description"]))
            product = next((p for p in choices if alias and p["id"] == alias["product_id"]),None)
            if not product:
                alias = None
            exact = next((p for p in choices if normalized_name(p["name"]) == normalized_name(line["description"])),None)
            ranked = sorted(choices,key=lambda p:SequenceMatcher(None,normalized_name(p["name"]),normalized_name(line["description"])).ratio(),reverse=True)
            product = product or exact or (ranked[0] if ranked and SequenceMatcher(None,normalized_name(ranked[0]["name"]),normalized_name(line["description"])).ratio() >= .45 else None)
            if product and product["id"] in used:
                product = alias = exact = None
            if product:
                used.add(product["id"])
            line.update(product_id=product["id"] if product else "", matched=bool(alias or exact), quantity=None,
                unit=product["unit"] if product else "uds", stock_id=product["stock_id"] if product else "")
            if product:
                line["quantity"] = (round(alias["per_unit"] * line["count"],3) if alias and alias.get("per_unit") is not None and alias["unit"] == product["unit"]
                    else converted_quantity(line,product["unit"]))
            line["replenish"] = bool(line["matched"] and line["stock_id"] and line["quantity"] is not None)
        token = str(uuid4())
        self._drafts = {key:value for key,value in self._drafts.items() if value["expires"] > time.time()}
        if len(self._drafts) >= 10:
            raise CatalogError("Hay demasiados tickets pendientes de revisar. Espera unos minutos.")
        purchases = [p for p in self.stock.receipts["purchases"].values() if not p.get("receipt_id") and p.get("at",0) > time.time()-30*DAY]
        self._drafts[token] = {"owner":owner, "expires":time.time()+1800, "receipt":deepcopy(receipt), "products":choices}
        return {"token":token, "receipt":receipt, "products":choices, "purchases":deepcopy(purchases)}

    def discard(self, token, owner):
        if self._drafts.get(token,{}).get("owner") == owner:
            self._drafts.pop(token,None)

    async def async_confirm(self, token, owner, selections, update_prices):
        draft = self._draft(token,owner)
        if type(update_prices) is not bool or not isinstance(selections,list) or len(selections) != len(draft["receipt"]["lines"]):
            raise CatalogError("Revisa las líneas del ticket antes de confirmar.")
        await self.automation.async_check()
        # Keep a todo completion from racing the receipt's stock adjustment.
        async with self.automation._lock:
            async with self.stock._lock:
                receipt = deepcopy(draft["receipt"])
                self._check_duplicate(receipt)
                data, items = deepcopy(self.stock.receipts), deepcopy(self.stock._items)
                if len(data["history"]) >= 1000:
                    raise CatalogError("El historial ha alcanzado los 1000 tickets.")
                groups = {}
                date = dt_util.parse_datetime(receipt["purchased_at"])
                purchased_at = dt_util.as_utc(date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).timestamp()
                if purchased_at > time.time()+DAY:
                    raise CatalogError("La fecha del ticket está en el futuro.")
                seen = set()
                if any(not isinstance(selection,dict) for selection in selections):
                    raise CatalogError("Las líneas seleccionadas no son válidas.")
                self._links(receipt,[{key:selection.get(key) for key in ("id","product_id")} for selection in selections])
                for selection in selections:
                    if set(selection)-{"save_price","unit"} != {"id","product_id","replenish","quantity","purchase_id"}:
                        raise CatalogError("Las líneas seleccionadas no son válidas.")
                    if any(not isinstance(selection[key],str) or len(selection[key]) > 200 for key in ("id","product_id","purchase_id")):
                        raise CatalogError("Las líneas seleccionadas no son válidas.")
                    line = next((line for line in receipt["lines"] if line["id"] == selection["id"]),None)
                    if line is None or line["id"] in seen or type(selection["replenish"]) is not bool:
                        raise CatalogError("Las líneas seleccionadas no son válidas.")
                    seen.add(line["id"])
                    product = next((p for p in self.stock.catalog.products if p["id"] == selection["product_id"]),None)
                    save_price = selection.get("save_price",update_prices)
                    if type(save_price) is not bool:
                        raise CatalogError("La selección de precios no es válida.")
                    line.update(product_id=product["id"] if product else "", product_name=product["name"] if product else "",
                        replenished=False, quantity=None, unit="", price_saved=bool(update_prices and save_price and product))
                    if selection["product_id"] and not product:
                        raise CatalogError("Un producto del catálogo ha cambiado. Vuelve a subir el ticket.", "conflict")
                    if selection["replenish"]:
                        stock = self.stock.item_for(product) if product else None
                        expected = next((p for p in draft["products"] if product and p["id"] == product["id"]),None)
                        if not expected or stock and stock["revision"] != expected["revision"] or not stock and expected["stock_id"]:
                            raise CatalogError("El stock ha cambiado. Vuelve a subir el ticket para revisar las cantidades.", "conflict")
                        quantity = quantity_value(selection["quantity"],positive=True)
                        if not stock:
                            unit = selection.get("unit","uds")
                            if not isinstance(unit,str) or not unit.strip() or len(unit.strip())>32 or any(ord(char)<32 for char in unit):
                                raise CatalogError("Indica una unidad de hasta 32 caracteres.")
                            stock = {**deepcopy(DEFAULT_CONFIG),"id":str(uuid4()),"name":product["name"],"catalog_product_id":product["id"],
                                "quantity":0,"revision":0,"unit":unit.strip(),"refill_quantity":quantity,"configured":True,"config_revision":1}
                            items[stock["id"]] = deepcopy(stock)
                        group = groups.setdefault(stock["id"],{"stock":stock, "quantity":0, "purchase_id":selection["purchase_id"]})
                        if group["purchase_id"] != selection["purchase_id"]:
                            raise CatalogError("Las líneas del mismo producto deben corresponder a la misma reposición.")
                        group["quantity"] = quantity_value(round(group["quantity"]+quantity,3),positive=True)
                        line.update(replenished=True, quantity=quantity, unit=stock["unit"])
                        data["aliases"][receipt["store"]+":"+normalized_name(line["description"])] = {
                            "product_id":product["id"], "per_unit":quantity/line["count"], "unit":stock["unit"]}
                    elif product:
                        self._remember_alias(data,receipt["store"],line,product)
                for item_id, group in groups.items():
                    if any(event[0] == item_id and event[2] == "purchase" for event in getattr(self.automation,"_events",())):
                        raise CatalogError("Se acaba de registrar una compra de este producto. Vuelve a subir el ticket para conciliarla.", "conflict")
                    item, quantity = items[item_id], group["quantity"]
                    previous = data["purchases"].get(group["purchase_id"]) if group["purchase_id"] else None
                    if group["purchase_id"] and (not previous or previous["item_id"] != item_id or previous.get("receipt_id") or previous.get("unit") != item["unit"]):
                        raise CatalogError("La reposición seleccionada ya se ha conciliado o ha cambiado.", "conflict")
                    delta = quantity - (previous["quantity"] if previous else 0)
                    item["quantity"] = quantity_value(round(item["quantity"]+delta,3))
                    item["revision"] += 1
                    if item["mode"] == "perishable" and (not previous or abs(previous["at"]-purchased_at) < 2*DAY):
                        # An old receipt must not restart a newer batch's shelf life.
                        if not item.get("expires_at") or purchased_at+item["days"]*DAY >= item["expires_at"]-2*DAY:
                            item.update(expires_at=purchased_at+item["days"]*DAY, expired=False)
                    if previous:
                        previous.update(quantity=quantity,receipt_id=receipt["id"])
                    else:
                        purchase_id = "receipt:"+receipt["id"]+":"+item_id
                        data["purchases"][purchase_id] = {"id":purchase_id,"at":purchased_at,"item_id":item_id,
                            "quantity":quantity,"unit":item["unit"],"receipt_id":receipt["id"],"list_entity":"","uid":""}
                        # Cover one exact pending list entry so its later purchase isn't added again.
                        candidates = [(entity,uid) for entity, entries in self.automation._snapshots.items() for uid,entry in entries.items()
                            if entry.get("status") == "needs_action" and normalized_name(entry.get("summary","")) == normalized_name(group["stock"]["name"])]
                        target = item.get("list_entity") or self.automation.settings.snapshot["primary_entity"]
                        candidates.sort(key=lambda pair:pair[0] != target)
                        if candidates:
                            key = ":".join(candidates[0])
                            if key in data["coverage"]:
                                raise CatalogError("Ya hay una compra importada para este producto pendiente. Marca la compra en la lista antes de importar otra.", "conflict")
                            data["coverage"][key] = {"quantity":quantity,"receipt_id":receipt["id"],"item_id":item_id,"unit":item["unit"]}
                receipt.update(imported_at=time.time(),prices_enabled=update_prices)
                data["history"][receipt["id"]] = receipt
                await self.stock._persist(items,receipts=data)
                self._drafts.pop(token,None)
        self.prices._notify()
        if self.stock.activity:
            self.stock.activity.record("stock.receipt",f'Ticket de {receipt["store_name"]} importado: {receipt["total"]:.2f} €',
                source="manual",diagnostics={"receipt_id":receipt["id"],"products":len(receipt["lines"]),"replenished":len(groups)})
        return deepcopy(receipt)

    def offers_for(self, product):
        offers = {}
        for receipt in self.stock.receipts["history"].values():
            for line in receipt["lines"]:
                if line.get("price_saved") and line.get("product_id") == product["id"]:
                    date = dt_util.parse_datetime(receipt["purchased_at"])
                    at = dt_util.as_utc(date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).timestamp()
                    if receipt["store"] not in offers or offers[receipt["store"]]["checked_at"] < at:
                        link = product.get("store_links",{}).get(receipt["store"],{})
                        offers[receipt["store"]] = {"store":receipt["store"],"store_name":receipt["store_name"],"name":product["name"],
                            "catalog_product_id":product["id"],"price":line["unit_price"],"currency":receipt["currency"],
                            "checked_at":at,"source":"receipt","reference_id":link.get("id",""),"url":link.get("url","")}
        return list(offers.values())
