"""Private receipt previews and atomic stock/history confirmation."""

import asyncio
import base64
import binascii
from copy import deepcopy
from difflib import SequenceMatcher
from hashlib import sha256
import time
import math
from uuid import uuid4

from homeassistant.util import dt as dt_util

from .catalog import CatalogError, normalized_name, product_codes
from .receipt_parser import MAX_PDF_BYTES, extract_receipt, extract_carrefour_account_ticket
from .dia_receipts import extract_dia_account_ticket, reference_id
from .lidl_receipts import extract_lidl_ticket
from .stock import DAY, DEFAULT_CONFIG, quantity_value, materialized_stock
from .store_links import STORES
from .quantity_values import purchase_defaults
from .product_references import content, format_observation, reference_key, matching_reference, inferred_content
from .receipt_quantities import purchase_quantity, price_from_option, estimated_quantity, weight_format, weight_purchase, receipt_catalog_price, lookup_paused, measure_price, stock_quantity
from .receipt_estimates import ReceiptEstimates, estimate_key


def converted_quantity(line, unit):
    purchased, purchased_unit=purchase_quantity(line)
    if purchased is not None:
        from .receipt_quantities import SCALES
        source,target=SCALES.get(purchased_unit),SCALES.get(unit)
        if source and target and source[0]==target[0]:
            return round(purchased*source[1]/target[1],3)
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
        self._quantity_cache=ReceiptEstimates(hass)

    @property
    def snapshot(self):
        return {"receipts":sorted(deepcopy(list(self.stock.receipts["history"].values())),
            key=lambda receipt:receipt["purchased_at"], reverse=True),
            "ticket_accounts":{store:bool(account.status("").get("connected") and getattr(self,"settings",None) and self.settings.snapshot.get("stores",{}).get(store,{}).get("enabled")) for store,account in self.ticket_accounts.accounts.items()} if getattr(self,"ticket_accounts",None) else {},
            "shops":deepcopy(getattr(self,'settings',None).snapshot['purchase_detection'].get('shops',[])) if getattr(self,'settings',None) else [],
            "persons":list(self.settings.snapshot['purchase_detection'].get('persons',[])) if getattr(self,'settings',None) else []}

    @staticmethod
    def _account_key(reference, store="carrefour"):
        return sha256((store+":"+reference).encode()).hexdigest()

    @staticmethod
    def _same_purchase(first, second):
        if (type(first.get("total")) not in (int, float) or type(second.get("total")) not in (int, float)
                or first.get("store") != second.get("store") or abs(first["total"]-second["total"]) > .01):
            return False
        dates = [dt_util.parse_datetime(item["purchased_at"]) for item in (first, second)]
        if not all(dates):
            return False
        # The printed ticket can omit seconds. Require the same local minute.
        local = [dt_util.as_local(value if value.tzinfo else value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)) for value in dates]
        return local[0].replace(second=0,microsecond=0)==local[1].replace(second=0,microsecond=0)

    def _summary_match(self, receipt, history=None):
        history = self.stock.receipts["history"] if history is None else history
        candidates = [old for old in history.values() if old.get("summary_only") and
            ((receipt.get("account_key") and old.get("account_key")==receipt["account_key"]) or
             (not receipt.get("account_key") and self._same_purchase(old,receipt)))]
        return candidates[0] if len(candidates)==1 else None

    async def async_import_carrefour_purchases(self, purchases):
        return await self.async_import_account_purchases(purchases,"carrefour")

    async def async_import_account_purchases(self, purchases, store):
        """Store account summaries only: never replenish stock or generate prices."""
        if store not in ("carrefour","dia","lidl"):
            raise CatalogError("La tienda no admite tickets de cuenta.")
        added = 0
        async with self.stock._lock:
            data = deepcopy(self.stock.receipts)
            for purchase in purchases:
                key = self._account_key(purchase["purchaseId"],store)
                when = dt_util.parse_datetime(purchase["purchaseDate"])
                if when.tzinfo is None:
                    when = when.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                receipt = {"id":store+"-account:"+key,"digest":store+"-account:"+key,"account_key":key,
                    "summary_only":True,"store":store,"store_name":STORES[store],
                    "purchased_at":dt_util.as_local(when).isoformat(),"currency":"EUR","total":purchase["amount"],
                    "article_count":purchase.get("article_count"),"lines":[],"imported_at":time.time(),
                    "ticket_available":purchase.get("ticket_available", True)}
                existing = next((old for old in data["history"].values() if old.get("account_key")==key),None)
                if existing and (not existing.get("summary_only") or existing.get("pending_review")):
                    continue
                if not existing:
                    matches = [old for old in data["history"].values() if not old.get("summary_only") and not old.get("account_key") and self._same_purchase(old,receipt)]
                    if len(matches)==1:
                        matches[0]["account_key"]=key
                        continue
                    if len(data["history"]) >= 1000:
                        continue
                    added += 1
                if existing:
                    receipt["imported_at"] = existing["imported_at"]
                    if receipt["article_count"] is None:
                        receipt["article_count"] = existing.get("article_count")
                data["history"][receipt["id"]] = receipt
            if data != self.stock.receipts:
                await self.stock._persist(deepcopy(self.stock._items),receipts=data)
        return added

    @staticmethod
    def _purchase_day(receipt):
        date = dt_util.parse_datetime(receipt.get("purchased_at", ""))
        if not date:
            return None
        return dt_util.as_local(date if date.tzinfo else date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).date()

    def _detection_matches(self, detected, receipt):
        day = self._purchase_day(detected)
        if day is None or day != self._purchase_day(receipt) or receipt.get("detected_purchase"):
            return False
        if detected.get('account') and detected.get('account') != receipt.get('store'):
            return False
        if not detected.get("needs_details") and (detected["store"] != receipt["store"] and not (detected.get('shop_id') and not detected.get('account')) or
                abs(detected["total"]-receipt["total"]) > .01):
            return False
        # A history summary alone must not stop the connector before it retrieves
        # the ticket. Its contents need not overlap the list that triggered us.
        return not receipt.get("summary_only") or bool(receipt.get("pending_review"))


    async def async_reconcile_detected_purchases(self):
        """Replace a detection with one compatible ticket; completed list items are only a trigger."""
        reconciled = []
        async with self.stock._lock:
            data = deepcopy(self.stock.receipts)
            for detected in list(data["history"].values()):
                if not detected.get("detected_purchase"):
                    continue
                candidates = [receipt for receipt in data["history"].values()
                    if not receipt.get("detection_id") and self._detection_matches(detected,receipt)]
                if len(candidates) == 1:
                    candidate = candidates[0]
                    if detected.get('purchase_group') and sum(self._detection_matches(other,candidate) for other in data['history'].values() if other.get('detected_purchase')) != 1:
                        continue
                    candidate["detection_id"] = detected["id"]
                    for key in ('shop_id','zone_id','shop_name','shop_image','shop_color','shoppers','purchase_group','completed_products'):
                        if key in detected:candidate[key]=deepcopy(detected[key])
                    data["history"].pop(detected["id"])
                    reconciled.append(detected["id"])
            if reconciled:
                await self.stock._persist(deepcopy(self.stock._items),receipts=data)
        if reconciled and getattr(self.stock,"activity",None):
            self.stock.activity.record("purchase.detected.matched", "Compra detectada vinculada a su ticket", source="automatic")
        return reconciled

    async def async_save_purchase_group(self, day, groups, products):
        """Upsert physical-store detections without duplicating allocated products."""
        async with self.stock._lock:
            data = deepcopy(self.stock.receipts)
            history = data['history']
            wanted = {group['id'] for group in groups}
            claimed = {p['key'] for receipt in history.values() if receipt.get('purchase_group')==day
                and (receipt.get('allocation_confirmed') or not receipt.get('detected_purchase') or receipt.get('shop_id') and receipt['id'] not in wanted)
                for p in receipt.get('completed_products',[]) if p.get('key')}
            for identifier,receipt in list(history.items()):
                if identifier=='detected:'+day and receipt.get('purchase_group')==day and receipt.get('detected_purchase') and receipt.get('needs_details') and not receipt.get('allocation_confirmed') and identifier not in wanted:
                    history.pop(identifier)
            for group in groups:
                identifier, shop = group['id'], group['shop']
                if identifier in data.get('coverage',{}).get('dismissed_detections',[]):continue
                if any(r.get('detection_id')==identifier for r in history.values()):continue
                previous = history.get(identifier)
                if shop is None and not any(p.get('key') not in claimed for p in group['products']) and any(g['shop'] for g in groups):
                    if previous and previous.get('needs_details') and not previous.get('allocation_confirmed'):history.pop(identifier)
                    continue
                if previous and (not previous.get('needs_details') or previous.get('allocation_confirmed')):continue
                if not previous and len(history)>=1000:raise CatalogError('El historial ha alcanzado las 1000 compras.')
                store = (shop['account'] or 'shop:'+shop['id']) if shop else 'unknown'
                history[identifier] = {**(previous or {}),'id':identifier,'digest':identifier,'detected_purchase':True,
                    'needs_details':True,'summary_only':True,'store':store,'store_name':shop['name'] if shop else 'Tienda desconocida',
                    'shop_id':shop['id'] if shop else '', 'shop_name':shop['name'] if shop else '',
                    'zone_id':shop.get('zone_id','') if shop else '',
                    'shop_image':shop['image_url'] if shop else '', 'shop_color':shop['color'] if shop else '#64748b',
                    'account':shop['account'] if shop else '', 'shoppers':group['shoppers'],'purchase_group':day,
                    'purchased_at':group['purchased_at'],'currency':'EUR','total':None,'lines':[],
                    'completed_products':[deepcopy(p) for p in group['products'] if p.get('key') not in claimed],
                    'candidate_products':[deepcopy(p) for p in products if p.get('key') not in claimed],
                    'article_count':len([p for p in group['products'] if p.get('key') not in claimed]),
                    'allocation_pending':len(groups)>1,'imported_at':(previous or {}).get('imported_at',time.time())}
            if data != self.stock.receipts:await self.stock._persist(deepcopy(self.stock._items),receipts=data)

    async def async_save_detected_purchase(self, identifier, purchased_at, products, *, zone_stores=None):
        """Save a detection summary only; stock changes require a reviewed receipt."""
        async with self.stock._lock:
            data = deepcopy(self.stock.receipts)
            previous = data["history"].get(identifier)
            if previous and not previous.get("detected_purchase"):
                return None
            if not previous and len(data["history"]) >= 1000:
                raise CatalogError("El historial ha alcanzado las 1000 compras.")
            receipt = previous or {"id":identifier,"digest":identifier,"detected_purchase":True,
                "needs_details":True,"summary_only":True,"store":"unknown","store_name":"Tienda desconocida",
                "purchased_at":purchased_at,"currency":"EUR","total":None,"lines":[],"imported_at":time.time()}
            receipt.update(completed_products=deepcopy(products),article_count=len(products))
            if receipt.get("needs_details") and zone_stores is not None:
                candidates = [store for store in dict.fromkeys(zone_stores) if store in STORES]
                receipt["zone_candidates"] = candidates
                receipt["provisional_store"] = len(candidates) == 1
                receipt["store"] = candidates[0] if len(candidates) == 1 else "unknown"
                receipt["store_name"] = STORES[candidates[0]] if len(candidates) == 1 else "Tienda desconocida"
            data["history"][identifier] = receipt
            if data != self.stock.receipts:
                await self.stock._persist(deepcopy(self.stock._items),receipts=data)
            return deepcopy(receipt)

    async def async_complete_detected_purchase(self, identifier, store, total, store_name="", product_keys=None, shoppers=None):
        places = getattr(self,'settings',None).snapshot['purchase_detection'].get('shops',[]) if getattr(self,'settings',None) else []
        shop = next((p for p in places if store=='shop:'+p['id']),None)
        if (store not in {*STORES,"other"} and shop is None or type(total) not in (int,float) or
                not math.isfinite(total) or not 0 <= total <= 1000000 or abs(total-round(total,2)) > .000001):
            raise CatalogError("Selecciona una tienda e indica un importe válido con hasta dos decimales.")
        if shop:
            store_name=shop['name'];store=shop['account'] or 'shop:'+shop['id']
        elif store == "other":
            if not isinstance(store_name,str) or not 1 <= len(store_name.strip()) <= 100:
                raise CatalogError("Indica el nombre de la tienda.")
            store_name = store_name.strip()
            store = "other:"+sha256(normalized_name(store_name).encode()).hexdigest()[:16]
        else:
            store_name = STORES[store]
        async with self.stock._lock:
            data = deepcopy(self.stock.receipts)
            receipt = data["history"].get(identifier)
            if not receipt or not receipt.get("detected_purchase"):
                raise CatalogError("Esta compra detectada ya no está pendiente o se ha sustituido por un ticket.","conflict")
            if shop:
                receipt.update(shop_id=shop['id'],shop_name=shop['name'],shop_image=shop['image_url'],shop_color=shop['color'],account=shop['account'])
            elif receipt.get('shop_id'):
                for key in ('shop_id','zone_id','shop_name','shop_image','shop_color','account'):receipt.pop(key,None)
            if shoppers is not None:
                allowed = set(getattr(self,'settings',None).snapshot['purchase_detection'].get('persons',[])) if getattr(self,'settings',None) else set()
                allowed.update(receipt.get('shoppers',[]))
                if not isinstance(shoppers,list) or any(person not in allowed for person in shoppers):raise CatalogError('Selecciona compradores válidos.')
                receipt['shoppers']=list(dict.fromkeys(shoppers))
            if product_keys is not None:
                candidates={p['key']:p for p in receipt.get('candidate_products',[]) if p.get('key')}
                if not isinstance(product_keys,list) or len(product_keys)!=len(set(product_keys)) or any(key not in candidates for key in product_keys):raise CatalogError('La selección de productos ha cambiado. Vuelve a abrir la compra.')
                claimed={p['key'] for r in data['history'].values() if r['id']!=identifier and r.get('purchase_group')==receipt.get('purchase_group') and r.get('allocation_confirmed') for p in r.get('completed_products',[]) if p.get('key')}
                if claimed.intersection(product_keys):raise CatalogError('Algún producto ya está asignado a otra compra.')
                receipt.update(completed_products=[deepcopy(candidates[key]) for key in product_keys],article_count=len(product_keys),allocation_confirmed=True,allocation_pending=False)
                for r in data['history'].values():
                    if r['id']!=identifier and r.get('purchase_group')==receipt.get('purchase_group') and r.get('detected_purchase') and not r.get('allocation_confirmed'):
                        r['completed_products']=[p for p in r.get('completed_products',[]) if p.get('key') not in product_keys]
                        r['candidate_products']=[p for p in r.get('candidate_products',[]) if p.get('key') not in product_keys]
                        r['article_count']=len(r['completed_products'])
            receipt.update(store=store,store_name=store_name,total=round(total,2),needs_details=False,provisional_store=False)
            # This is explicit user confirmation, not an automatic product inference.
            matches = [other for other in data["history"].values() if not other.get("detected_purchase") and
                other.get("store")==store and type(other.get("total")) in (int,float) and
                abs(other["total"]-receipt["total"]) <= .01 and self._purchase_day(other)==self._purchase_day(receipt)]
            if len(matches)==1 and not matches[0].get("detection_id"):
                matches[0]["detection_id"]=identifier
                for key in ('shop_id','zone_id','shop_name','shop_image','shop_color','shoppers','purchase_group','completed_products'):
                    if key in receipt:matches[0][key]=deepcopy(receipt[key])
                data["history"].pop(identifier)
                receipt=matches[0]
            await self.stock._persist(deepcopy(self.stock._items),receipts=data)
        if getattr(self.stock,"activity",None):
            self.stock.activity.record("purchase.detected.updated","Compra detectada: tienda e importe guardados",source="manual")
        return deepcopy(receipt)

    async def async_discard_detected_purchase(self, identifier):
        async with self.stock._lock:
            data = deepcopy(self.stock.receipts)
            receipt = data["history"].get(identifier)
            if not receipt or not receipt.get("detected_purchase"):
                raise CatalogError("Esta compra detectada ya no está disponible.","conflict")
            data["history"].pop(identifier)
            if receipt.get('purchase_group'):
                data.setdefault('coverage',{}).setdefault('dismissed_detections',[]).append(identifier)
                data['coverage']['dismissed_detections']=data['coverage']['dismissed_detections'][-1000:]
            await self.stock._persist(deepcopy(self.stock._items),receipts=data)
        return {"removed":True}

    def account_ticket_available(self, reference, store="carrefour"):
        key=self._account_key(reference,store)
        return any(old.get("account_key")==key and (old.get("pending_review") or not old.get("summary_only")) for old in self.stock.receipts["history"].values())

    async def async_archive_account_ticket(self, token, owner):
        draft=self._draft(token,owner)
        async with self.stock._lock:
            receipt=deepcopy(draft["receipt"])
            self._check_duplicate(receipt)
            data=deepcopy(self.stock.receipts)
            previous=self._summary_match(receipt,data["history"])
            if previous:
                for key in ("detection_id","shop_id","zone_id","shop_name","shop_image","shop_color","shoppers","purchase_group","completed_products"):
                    if key in previous:receipt[key]=deepcopy(previous[key])
                data["history"].pop(previous["id"])
            self._apply_manual_detection(draft,receipt,data["history"])
            if len(data["history"])>=1000:
                raise CatalogError("El historial ha alcanzado los 1000 tickets.")
            receipt.update(summary_only=True,pending_review=True,imported_at=time.time())
            data["history"][receipt["id"]]=receipt
            await self.stock._persist(deepcopy(self.stock._items),receipts=data)
            self._drafts.pop(token,None)
        return deepcopy(receipt)

    async def async_review_saved(self, identifier, owner):
        saved=self.stock.receipts["history"].get(identifier)
        if not saved:
            raise CatalogError("El ticket pendiente ya no está disponible.")
        if not saved.get("summary_only"):
            receipt=deepcopy(saved)
            account=getattr(self,"lidl_account",None)
            warning=""
            if receipt.get("store")=="lidl" and receipt.get("account_key") and account and account.status(owner).get("connected"):
                try:
                    fresh=await account.async_reprocess_receipt(saved)
                    unused=list(fresh["lines"])
                    for line in receipt["lines"]:
                        match=next((row for row in unused if row.get("reference_id")==line.get("reference_id") and row["description"]==line["description"] and abs(row["amount"]-line["amount"])<.001 and row["count"]==line["count"]),None)
                        if not match:
                            raise CatalogError("El detalle actualizado no coincide con las líneas guardadas.")
                        unused.remove(match)
                        if match.get("ticket_measure_price"):
                            for key in ("purchased_quantity","purchased_unit","quantity_estimated","ticket_measure_price","pack_quantity","pack_unit"):
                                line[key]=deepcopy(match[key])
                    if unused:
                        raise CatalogError("El detalle actualizado contiene otras líneas.")
                except (CatalogError,OSError,TimeoutError) as err:
                    receipt=deepcopy(saved)
                    warning="No se ha podido recuperar el detalle original de Lidl; se muestran los datos guardados. "+str(err)
            choices=self._choices(receipt["store"])
            for line in receipt["lines"]:
                product=next((product for product in choices if product["id"]==line.get("product_id")),None)
                quantity,unit=inferred_content(line)
                if quantity is not None:
                    line["pack_quantity"],line["pack_unit"]=content(quantity,unit)
                line.update(product_id=product["id"] if product else "",matched=bool(product),replenish=False)
            self._drafts={key:value for key,value in self._drafts.items() if value["expires"]>time.time()}
            if len(self._drafts)>=10:
                raise CatalogError("Hay demasiados tickets pendientes de revisar. Espera unos minutos.")
            token=str(uuid4())
            self._drafts[token]={"owner":owner,"expires":time.time()+1800,"receipt":receipt,"products":choices,"reprocess_original":deepcopy(saved)}
            return {"token":token,"receipt":deepcopy(receipt),"products":choices,"purchases":[],"reprocess":True,"warning":warning}
        if not saved.get("pending_review"):
            raise CatalogError("El ticket pendiente ya no está disponible.")
        receipt=deepcopy(saved)
        for key in ("summary_only","pending_review","imported_at"):
            receipt.pop(key,None)
        return await self._prepare_preview(receipt,owner)

    async def async_reprocess(self, token, owner, selections):
        draft=self._draft(token,owner)
        original=draft.get("reprocess_original")
        if original is None:
            raise CatalogError("Abre un ticket ya revisado para reprocesar sus datos.")
        async with self.stock._lock:
            data=deepcopy(self.stock.receipts)
            if data["history"].get(original["id"])!=original:
                raise CatalogError("La compra ha cambiado. Vuelve a abrir el ticket.","conflict")
            receipt=deepcopy(original)
            if not isinstance(selections,list) or len(selections)!=len(receipt["lines"]):
                raise CatalogError("Revisa todos los contenidos del ticket.")
            # Review the refreshed draft, while the original remains the conflict baseline.
            receipt=deepcopy(draft["receipt"])
            seen=set();references=[]
            prices_enabled=self.automation.settings.snapshot.get("price_updates_enabled",True)
            date=dt_util.parse_datetime(receipt["purchased_at"])
            price_at=dt_util.as_utc(date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE) if date.tzinfo is None else date).timestamp() if date else None
            for selection in selections:
                if not isinstance(selection,dict) or set(selection)-{"manual_measure_price"} not in ({"id","pack_quantity","pack_unit"},{"id","product_id","pack_quantity","pack_unit"}):
                    raise CatalogError("Los datos del envase no son válidos.")
                line=next((line for line in receipt["lines"] if line["id"]==selection["id"]),None)
                if not line or line["id"] in seen:
                    raise CatalogError("Los datos del envase no son válidos.")
                seen.add(line["id"])
                try:
                    quantity,unit=content(selection["pack_quantity"],selection["pack_unit"],allow_partial=True)
                except ValueError as err:
                    raise CatalogError(str(err)) from err
                product_id=selection.get("product_id",line.get("product_id",""))
                if not isinstance(product_id,str):
                    raise CatalogError("La vinculación no es válida.")
                if line.get("product_id") and any(p["id"]==line["product_id"] for p in self.stock.catalog.products) and product_id!=line["product_id"]:
                    raise CatalogError("Conserva la vinculación original al reprocesar este ticket.")
                product=next((product for product in self.stock.catalog.products if product["id"]==product_id),None)
                if product_id and not product:
                    raise CatalogError("El producto vinculado ya no existe.","conflict")
                if product:
                    line.update(product_id=product_id,matched=True)
                    self._remember_alias(data,receipt["store"],line,product)
                self._apply_lidl_metadata(draft,line,product)
                reference=matching_reference(product,receipt["store"],line) if product else None
                if reference and reference.get("active") is False:
                    continue
                self._apply_manual_measure_price(selection,line,reference,prices_enabled)
                if product:
                    if quantity is not None or unit:
                        line.update(pack_quantity=quantity,pack_unit=unit,format_confirmed=quantity is not None or unit in ("g","kg"))
                    price=receipt_catalog_price(line,reference)
                    save_price=prices_enabled and receipt.get("currency")=="EUR" and price_at and type(price) in (int,float) and math.isfinite(price) and 0<=price<=1000000
                    reference_line=deepcopy(line)
                    line["price_saved"]=bool(save_price)
                    reference_line["price_saved"]=bool(save_price)
                    if save_price:
                        line["price_saved"]=True
                        reference_line["price_saved"]=True
                        reference_line["last_price"]={"price":price,"currency":"EUR","checked_at":line.get("manual_measure_price",{}).get("checked_at",price_at)}
                        if reference_line.get("ticket_measure_price"):
                            reference_line["ticket_measure_price"].setdefault("checked_at",price_at)
                            reference_line["ticket_measure_price"].setdefault("source","ticket")
                    references.append((product["id"],receipt["store"],reference_line,quantity is not None))
            await self.stock.catalog.async_bind_receipt_eans([(line["product_id"],line.get("ean","")) for line in receipt["lines"] if line.get("product_id")],references=references)
            data["history"][receipt["id"]]=receipt
            await self.stock._persist(deepcopy(self.stock._items),receipts=data)
            self._drafts.pop(token,None)
        self.prices._notify()
        if self.stock.activity:
            self.stock.activity.record("stock.receipt_reprocessed",f'Datos del ticket de {receipt["store_name"]} reprocesados',source="manual",diagnostics={"receipt_id":receipt["id"],"options":len(references)})
        return deepcopy(receipt)

    async def async_lidl_metadata(self,token,owner,line_id,product_id):
        draft=self._draft(token,owner)
        line=next((row for row in draft["receipt"]["lines"] if row["id"]==line_id),None)
        product=next((p for p in self.stock.catalog.products if p["id"]==product_id),None)
        bound=draft.get("quantity_products",{}).get(line_id) or (line.get("product_id") if line and line.get("matched") is not False else None)
        if draft["receipt"]["store"]!="lidl" or not line or not product or bound!=product_id:
            raise CatalogError("Vincula primero esta línea de Lidl con un producto del catálogo.")
        ref=matching_reference(product,"lidl",line)
        if ref and ref.get("active") is False:
            return {"reason":"Esta alternativa está desvinculada."}
        cached=draft.get("lidl_metadata",{}).get(line_id)
        if cached and cached["product_id"]==product_id:return deepcopy(cached["data"])
        try:
            data=await self.lidl_catalog.resolve(line.get("reference_id",""),line.get("ean") or (ref or {}).get("ean",""),(ref or {}).get("url",""))
        except (ValueError,OSError,TimeoutError) as err:
            data={"reason":str(err)[:500]}
        self._draft(token,owner)  # Discarded/expired previews cannot receive results.
        draft.setdefault("lidl_metadata",{})[line_id]={"product_id":product_id,"data":deepcopy(data)}
        return deepcopy(data)

    @staticmethod
    def _apply_lidl_metadata(draft,line,product):
        candidate=draft.get("lidl_metadata",{}).get(line["id"],{})
        data=candidate.get("data",{})
        if draft["receipt"]["store"]!="lidl" or not product or candidate.get("product_id")!=product["id"] or not data.get("url"):
            return False
        line.update(url=data["url"],ticket_reference_id=line["reference_id"],web_reference_id=data["web_reference_id"])
        for key in ("name","brand"):
            if data.get(key):line[key]=data[key]
        if data.get("ean") and not line.get("ean"):line["ean"]=data["ean"]
        return True

    def _check_duplicate(self, receipt):
        if any(not old.get("summary_only") and (old["id"] == receipt["id"] or old["digest"] == receipt["digest"] or
                (receipt.get("account_key") and old.get("account_key")==receipt["account_key"])) for old in self.stock.receipts["history"].values()):
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
            defaults = purchase_defaults(product)
            offers = self.prices.prices_for(product) if hasattr(self.prices,"prices_for") else []
            price = next((offer for offer in offers if offer["store"] == store),None)
            choices.append({"id":product["id"],"name":product["name"],"image_url":product.get("image_url", ""),"icon":product.get("icon", ""),"barcodes":product_codes(product, "barcode"),"unit":stock["unit"] if stock else defaults["purchase_unit"],
                "refill_quantity":stock["refill_quantity"] if stock else defaults["unit_quantity"],
                "stock_id":stock["id"] if stock else "","revision":stock["revision"] if stock else 0,
                "commercial_references":deepcopy(product.get("commercial_references",[])),
                "reference_prices":deepcopy(offers),
                "price":price.get("price") if price else None,"price_date":price.get("checked_at",0) if price else 0})
        return choices

    async def async_options(self, token, owner):
        draft = self._draft(token,owner)
        await self.automation.async_check()
        draft["products"] = self._choices(draft["receipt"]["store"])
        purchases = [p for p in self.stock.receipts["purchases"].values() if not p.get("receipt_id") and p.get("at",0)>time.time()-30*DAY]
        return {"products":deepcopy(draft["products"]),"purchases":deepcopy(purchases)}

    async def async_estimate_quantity(self, token, owner, line_id, product_id):
        """One reviewed line per request, allowing the UI to display real progress."""
        draft=self._draft(token,owner)
        if "reprocess_original" in draft:
            raise CatalogError("El reprocesamiento no cambia las cantidades compradas.")
        line=next((line for line in draft["receipt"]["lines"] if line["id"]==line_id),None)
        if not line or draft.get("quantity_products",{}).get(line_id)!=product_id:
            raise CatalogError("Confirma primero la vinculación del producto.","conflict")
        draft["expires"]=time.time()+1800
        quantity,unit=purchase_quantity(line)
        if quantity is not None and not line.get("quantity_estimated"):
            return {"quantity":quantity,"unit":unit,"estimated":False}
        if draft["receipt"]["store"]!="carrefour":
            return {"quantity":None}
        product=next((p for p in self.stock.catalog.products if p["id"]==product_id),None)
        if not product:
            raise CatalogError("El producto ya no existe.","conflict")
        ref,rate=self._quantity_inputs(line,product)
        if not ref:
            return {"quantity":None,"reason":"No hay una única opción de Carrefour identificada."}
        cached=await self._quantity_cache.get(estimate_key(draft['receipt'],line,product_id,ref,rate))
        if cached:
            line.update(purchased_quantity=cached['quantity'],purchased_unit=cached['unit'],quantity_estimated=True)
            return cached
        if not rate and ref.get("url") and getattr(self,"option_lookup",None):
            if draft.get("quantity_search_paused"):
                return {"quantity":None,"search_paused":True,"reason":"Carrefour está en pausa. Se continúa con los datos disponibles."}
            try:
                data=await self.option_lookup.retrieve(ref["url"],"carrefour",ref.get("ean",""),measure=True)
            except ValueError as err:
                if lookup_paused(getattr(err,"diagnostics",{})):
                    draft["quantity_search_paused"]=True
                    return {"quantity":None,"search_paused":True,"reason":str(err)}
                return {"quantity":None,"reason":str(err)}
            self._draft(token,owner)
            if draft.get("quantity_products",{}).get(line_id)!=product_id:
                raise CatalogError("La vinculación ha cambiado.","conflict")
            rate=data.get("measure_price")
            if not rate and lookup_paused(data.get("retrieval_diagnostics",{})):
                draft["quantity_search_paused"]=True
                return {"quantity":None,"search_paused":True,"reason":"Carrefour está en pausa. Se continúa con los datos disponibles."}
        if not rate:
            return {"quantity":None,"reason":"No hay un precio por unidad de medida disponible."}
        if ref.get("measure_price")!=rate:
            await self.stock.catalog.async_save_measure_price(product_id,ref["id"],ref.get("url",""),rate)
        result=estimated_quantity(line,rate)
        if not result:
            return {"quantity":None}
        line.update(purchased_quantity=result["quantity"],purchased_unit=result["unit"],quantity_estimated=True)
        current=next((p for p in self.stock.catalog.products if p['id']==product_id),product)
        ref,rate=self._quantity_inputs(line,current)
        await self._quantity_cache.put(estimate_key(draft['receipt'],line,product_id,ref,rate),result)
        return result

    def _quantity_inputs(self,line,product):
        from .product_references import gtin
        refs=[ref for ref in product.get('commercial_references',[]) if ref['store']=='carrefour' and ref.get('active',True) and (ref.get('url') or ref.get('measure_price') or ref.get('last_price'))]
        if line.get('ean'):refs=[ref for ref in refs if gtin(ref.get('ean'))==gtin(line['ean'])]
        elif line.get('reference_id'):refs=[ref for ref in refs if ref.get('reference_id')==line['reference_id']]
        if len(refs)!=1:return None,None
        ref=refs[0];rate=price_from_option(ref)
        if not rate and hasattr(self.prices,'prices_for'):
            offers=[offer for offer in self.prices.prices_for(product) if offer.get('store')=='carrefour' and
                    (offer.get('commercial_reference_id')==ref['id'] or ref.get('reference_id') and offer.get('reference_id')==ref['reference_id']
                     or gtin(ref.get('ean')) and gtin(offer.get('ean'))==gtin(ref['ean']))]
            for offer in sorted(offers,key=lambda item:item.get('checked_at',0),reverse=True):
                rate=price_from_option({**ref,'last_price':{key:offer.get(key) for key in ('price','currency','checked_at')}})
                if rate:break
        return ref,rate

    @staticmethod
    def _apply_manual_measure_price(selection,line,reference,enabled):
        if "manual_measure_price" not in selection:return
        if not enabled or not weight_purchase(line,reference):
            raise CatalogError("Solo se puede editar el precio por kg de una compra al peso con los precios activados.")
        try:
            rate=measure_price({"price":selection["manual_measure_price"],"quantity":1,"unit":"kg","currency":"EUR","checked_at":time.time(),"source":"manual"})
        except ValueError as err:raise CatalogError(str(err)) from err
        line["manual_measure_price"]=rate

    def _links(self, receipt, selections):
        if not isinstance(selections,list) or len(selections) != len(receipt["lines"]):
            raise CatalogError("Revisa todas las vinculaciones del ticket.")
        seen, result = set(), []
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
            result.append((line,product))
        return result

    @staticmethod
    def _remember_alias(data, store, line, product):
        key = store+":"+normalized_name(line["description"])
        if data["aliases"].get(key,{}).get("product_id") != product["id"]:
            data["aliases"][key] = {"product_id":product["id"],"per_unit":None,"unit":""}
        if line.get("reference_id"):
            data["aliases"][key]["reference_id"] = line["reference_id"]

    async def async_link(self, token, owner, selections):
        draft = self._draft(token,owner)
        if "reprocess_original" in draft:
            raise CatalogError("Este ticket solo admite reprocesar los datos de sus envases.")
        async with self.stock._lock:
            linked = self._links(draft["receipt"],selections)
            for line,product in linked:
                if line.get("quantity_estimated") and draft.get("quantity_products",{}).get(line["id"])!=(product or {}).get("id"):
                    for field in ("purchased_quantity","purchased_unit","quantity_estimated"):
                        line.pop(field,None)
            data = deepcopy(self.stock.receipts)
            for line,product in linked:
                if product:
                    self._remember_alias(data,draft["receipt"]["store"],line,product)
            await self.stock.catalog.async_bind_receipt_eans([(product["id"], line.get("ean", "")) for line, product in linked if product],
                references=[(product["id"],draft["receipt"]["store"],line,False) for line,product in linked if product])
            await self.stock._persist(deepcopy(self.stock._items),receipts=data)
            draft["quantity_products"]={line["id"]:product["id"] for line,product in linked if product}
        options=await self.async_options(token,owner)
        if draft['receipt']['store']=='carrefour':
            estimates={}
            for line,product in linked:
                if not product or line.get('purchased_quantity') is not None and not line.get('quantity_estimated'):continue
                current=next((p for p in self.stock.catalog.products if p['id']==product['id']),None)
                if not current:continue
                ref,rate=self._quantity_inputs(line,current)
                cached=await self._quantity_cache.get(estimate_key(draft['receipt'],line,product['id'],ref,rate))
                if cached:
                    line.update(purchased_quantity=cached['quantity'],purchased_unit=cached['unit'],quantity_estimated=True)
                    estimates[line['id']]={**cached,'product_id':product['id']}
            if estimates:options['quantity_estimates']=estimates
        return options

    async def async_preview(self, encoded, owner, *, account_reference=None, expected_total=None, expected_purchased_at=None):
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
        if expected_total is not None and (type(expected_total) not in (int,float) or not math.isfinite(expected_total) or abs(receipt["total"]-expected_total)>.02):
            raise CatalogError("El importe del PDF no coincide con la compra de Carrefour seleccionada.","receipt_purchase_mismatch")
        if expected_purchased_at is not None and self._purchase_day(receipt)!=self._purchase_day({"purchased_at":expected_purchased_at}):
            raise CatalogError("La fecha del PDF no coincide con la compra de Carrefour seleccionada.","receipt_purchase_mismatch")
        if account_reference:
            receipt["account_key"] = self._account_key(account_reference)
        return await self._prepare_preview(receipt, owner)

    async def async_preview_carrefour_ticket(self, detail, reference, expected_total, owner):
        if self._parse_lock.locked():
            raise CatalogError("Ya se está leyendo un ticket. Espera a que termine.")
        async with self._parse_lock:
            receipt = await self.hass.async_add_executor_job(extract_carrefour_account_ticket, detail, reference, expected_total)
        receipt["account_key"] = self._account_key(reference)
        return await self._prepare_preview(receipt, owner)

    async def async_preview_dia_ticket(self, detail, params, expected_total, owner):
        if self._parse_lock.locked():
            raise CatalogError("Ya se está leyendo un ticket. Espera a que termine.")
        async with self._parse_lock:
            receipt = await self.hass.async_add_executor_job(extract_dia_account_ticket,detail,params,expected_total)
        receipt["account_key"] = self._account_key(reference_id(params),"dia")
        return await self._prepare_preview(receipt,owner)

    async def async_preview_lidl_ticket(self, detail, reference, expected_total, expected_date, owner):
        if self._parse_lock.locked():
            raise CatalogError("Ya se está leyendo un ticket. Espera a que termine.")
        async with self._parse_lock:
            receipt = await self.hass.async_add_executor_job(extract_lidl_ticket, detail, reference, expected_total, expected_date)
        receipt["account_key"] = self._account_key(reference, "lidl")
        return await self._prepare_preview(receipt, owner)

    async def _prepare_preview(self, receipt, owner):
        # Contents describe one scanned/sold EAN, never the number purchased.
        # Re-read multipacks before using a parser's simple weight match.
        for line in receipt["lines"]:
            if line.get("ticket_measure_price"):
                date=dt_util.parse_datetime(receipt["purchased_at"])
                if date:
                    line["ticket_measure_price"].setdefault("checked_at",dt_util.as_utc(date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE) if date.tzinfo is None else date).timestamp())
                    line["ticket_measure_price"].setdefault("source","ticket")
            quantity,unit=inferred_content(line)
            if quantity is not None:
                try:
                    line["pack_quantity"],line["pack_unit"]=content(quantity,unit)
                except ValueError:
                    pass
            bought,bought_unit=purchase_quantity(line)
            if bought is not None:
                line.update(purchased_quantity=bought,purchased_unit=bought_unit,quantity_estimated=False)
        summary = self._summary_match(receipt)
        if summary:
            receipt["account_key"] = summary["account_key"]
        self._check_duplicate(receipt)
        await self.automation.async_check()
        choices = self._choices(receipt["store"])
        for line in receipt["lines"]:
            eligible=[p for p in choices if not ((ref:=matching_reference(p,receipt["store"],line)) and ref.get("active") is False)]
            alias = self.stock.receipts["aliases"].get(receipt["store"]+":"+normalized_name(line["description"]))
            ean = line.get("ean", "")
            ean_product = next((p for p in eligible if ean and any(code.isascii() and code.isdigit() and code.zfill(14) == ean.zfill(14) for code in p["barcodes"])), None)
            product = ean_product or next((p for p in eligible if alias and p["id"] == alias["product_id"]),None)
            if ean_product and alias and alias["product_id"] != ean_product["id"]:
                alias = None
            if not product:
                alias = None
            exact = next((p for p in eligible if normalized_name(p["name"]) == normalized_name(line["description"])),None)
            ranked = sorted(eligible,key=lambda p:SequenceMatcher(None,normalized_name(p["name"]),normalized_name(line["description"])).ratio(),reverse=True)
            product = product or exact or (ranked[0] if ranked and SequenceMatcher(None,normalized_name(ranked[0]["name"]),normalized_name(line["description"])).ratio() >= .45 else None)
            line.update(product_id=product["id"] if product else "", matched=bool(ean_product or alias or exact), quantity=None,
                unit=product["unit"] if product else "uds", stock_id=product["stock_id"] if product else "")
            if product:
                from .receipt_quantities import SCALES
                purchased,purchased_unit=purchase_quantity(line)
                source,target=SCALES.get(purchased_unit),SCALES.get(product["unit"])
                recovered=converted_quantity(line,product["unit"]) if purchased is not None and source and target and source[0]==target[0] else None
                line["quantity"] = recovered if recovered is not None else product["refill_quantity"]
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

    def _apply_manual_detection(self, draft, receipt, history):
        manual=draft.get("manual_detection")
        if not manual:
            return
        expected=manual["snapshot"];detected=history.get(expected["id"])
        if detected!=expected or not detected.get("detected_purchase") or self._purchase_day(detected)!=self._purchase_day(receipt):
            raise CatalogError("La compra detectada ha cambiado o ya tiene un ticket. Vuelve a abrirla.","conflict")
        if receipt.get("detection_id") not in (None,detected["id"]):
            raise CatalogError("Este ticket ya está asignado a otra compra.","conflict")
        receipt["detection_id"]=detected["id"]
        for key in ("shoppers","purchase_group","completed_products"):
            if key in detected:receipt[key]=deepcopy(detected[key])
        if shop:=manual.get("shop"):
            receipt.update(shop_id=shop["id"],shop_name=shop["name"],shop_image=shop["image_url"],shop_color=shop["color"],account=shop["account"])
        history.pop(detected["id"])

    async def async_confirm(self, token, owner, selections, update_prices):
        if "reprocess_original" in self._draft(token,owner):
            raise CatalogError("Este ticket solo admite reprocesar los datos de sus envases.")
        draft = self._draft(token,owner)
        if type(update_prices) is not bool or not isinstance(selections,list) or len(selections) != len(draft["receipt"]["lines"]):
            raise CatalogError("Revisa las líneas del ticket antes de confirmar.")
        await self.automation.async_check()
        # Serialize the reorder guard and the receipt's stock adjustment.
        async with self.automation._lock:
            async with self.stock._lock:
                receipt = deepcopy(draft["receipt"])
                self._check_duplicate(receipt)
                data, items = deepcopy(self.stock.receipts), deepcopy(self.stock._items)
                summary = self._summary_match(receipt,data["history"])
                if summary:
                    for key in ("detection_id","shop_id","zone_id","shop_name","shop_image","shop_color","shoppers","purchase_group","completed_products"):
                        if key in summary:receipt[key]=deepcopy(summary[key])
                    data["history"].pop(summary["id"])
                self._apply_manual_detection(draft,receipt,data["history"])
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
                    if set(selection)-{"save_price","unit","pack_quantity","pack_unit","quantity_edited","manual_measure_price"} != {"id","product_id","replenish","quantity","purchase_id"}:
                        raise CatalogError("Las líneas seleccionadas no son válidas.")
                    if any(not isinstance(selection[key],str) or len(selection[key]) > 200 for key in ("id","product_id","purchase_id")):
                        raise CatalogError("Las líneas seleccionadas no son válidas.")
                    line = next((line for line in receipt["lines"] if line["id"] == selection["id"]),None)
                    if line is None or line["id"] in seen or type(selection["replenish"]) is not bool:
                        raise CatalogError("Las líneas seleccionadas no son válidas.")
                    seen.add(line["id"])
                    product = next((p for p in self.stock.catalog.products if p["id"] == selection["product_id"]),None)
                    self._apply_lidl_metadata(draft,line,product)
                    save_price = selection.get("save_price",update_prices)
                    if type(save_price) is not bool:
                        raise CatalogError("La selección de precios no es válida.")
                    reference=matching_reference(product,receipt["store"],line) if product else None
                    self._apply_manual_measure_price(selection,line,reference,bool(update_prices and save_price and product))
                    line.update(product_id=product["id"] if product else "", product_name=product["name"] if product else "",
                        replenished=False, quantity=None, unit="", price_saved=bool(update_prices and save_price and product and receipt_catalog_price(line,reference) is not None))
                    if selection["product_id"] and not product:
                        raise CatalogError("Un producto del catálogo ha cambiado. Vuelve a subir el ticket.", "conflict")
                    if "pack_quantity" in selection or "pack_unit" in selection:
                        try:
                            quantity,unit=content(selection.get("pack_quantity"),selection.get("pack_unit",""),allow_partial=True)
                        except ValueError as err:
                            raise CatalogError(str(err)) from err
                        line.update(pack_quantity=quantity,pack_unit=unit,format_confirmed=quantity is not None or unit in ("g","kg"))
                    if receipt_catalog_price(line,reference) is None:line["price_saved"]=False
                    if selection["replenish"]:
                        if line.get("quantity_estimated") and selection.get("quantity_edited") is True:
                            line.update(purchased_quantity=quantity_value(selection["quantity"],positive=True),purchased_unit=selection.get("unit",""),quantity_estimated=False)
                        stock = self.stock.item_for(product) if product else None
                        if not stock and product:stock=next((item for item in items.values() if item.get('catalog_product_id')==product['id']),None)
                        expected = next((p for p in draft["products"] if product and p["id"] == product["id"]),None)
                        if not expected or stock and stock["revision"] != expected["revision"] or not stock and expected["stock_id"]:
                            raise CatalogError("El stock ha cambiado. Vuelve a subir el ticket para revisar las cantidades.", "conflict")
                        quantity = quantity_value(selection["quantity"],positive=True)
                        unit=selection.get('unit',stock['unit'] if stock else 'uds')
                        if not isinstance(unit,str) or not unit.strip() or len(unit.strip())>32 or any(ord(char)<32 for char in unit):
                            raise CatalogError("Indica una unidad de hasta 32 caracteres.")
                        if not stock:
                            stock = {**deepcopy(DEFAULT_CONFIG),"id":str(uuid4()),"name":product["name"],"catalog_product_id":product["id"],
                                "quantity":0,"revision":0,"unit":unit.strip(),"refill_quantity":quantity,"configured":True,"config_revision":1}
                            items[stock["id"]] = deepcopy(stock)
                        converted=stock_quantity(quantity,unit,stock['unit'])
                        if converted is None:raise CatalogError(f'No se pueden sumar las cantidades de «{product["name"]}»: {unit} y {stock["unit"]}. Indica unidades compatibles.')
                        quantity=quantity_value(converted,positive=True)
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
                    items[item_id]=materialized_stock(items[item_id])
                    item, quantity = items[item_id], group["quantity"]
                    data["coverage"].pop("awaiting:"+item_id,None)
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
                receipt.update(imported_at=time.time(),prices_enabled=update_prices)
                data["history"][receipt["id"]] = receipt
                await self.stock.catalog.async_bind_receipt_eans([(line["product_id"], line.get("ean", "")) for line in receipt["lines"] if line.get("product_id")],
                    references=[(line["product_id"],receipt["store"],line,line.get("format_confirmed",False)) for line in receipt["lines"] if line.get("product_id")])
                await self.stock._persist(items,receipts=data)
                self._drafts.pop(token,None)
        self.prices._notify()
        if self.stock.activity:
            self.stock.activity.record("stock.receipt",f'Ticket de {receipt["store_name"]} importado: {receipt["total"]:.2f} €',
                source="manual",diagnostics={"receipt_id":receipt["id"],"products":len(receipt["lines"]),"replenished":len(groups)})
        return deepcopy(receipt)

    def offers_for(self, product):
        if not product.get("id"):
            return []
        offers = {}
        for receipt in self.stock.receipts["history"].values():
            for line in receipt["lines"]:
                if line.get("price_saved") and line.get("product_id") == product["id"]:
                    reference=matching_reference(product,receipt["store"],line)
                    price=receipt_catalog_price(line,reference)
                    if price is None:continue
                    date = dt_util.parse_datetime(receipt["purchased_at"])
                    at = dt_util.as_utc(date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)).timestamp()
                    at=line.get("manual_measure_price",{}).get("checked_at",at)
                    key=(receipt["store"],reference_key(receipt["store"],line))
                    if key not in offers or offers[key]["checked_at"] < at:
                        link = product.get("store_links",{}).get(receipt["store"],{})
                        details=format_observation(product,receipt["store"],line)
                        if weight_purchase(line,reference):details.update(pack_quantity=1,pack_unit="kg",format_pending=False)
                        if details.get("reference_excluded"):
                            continue
                        offers[key] = {"store":receipt["store"],"store_name":receipt["store_name"],"name":line["description"],
                            "catalog_product_id":product["id"],"price":price,"currency":receipt["currency"],
                            "checked_at":at,"source":"receipt","reference_id":line.get("reference_id","") or link.get("id"),"url":link.get("url",""),
                            **{key:details.get(key) for key in ("ean","pack_quantity","pack_unit","commercial_reference_id","format_pending")}}
        return list(offers.values())
