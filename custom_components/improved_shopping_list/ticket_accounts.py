"""Serialize automatic account lookups in zone/favorite order across stores."""
import asyncio
from copy import deepcopy
import time
from uuid import uuid4
from homeassistant.util import dt as dt_util
from homeassistant.helpers.storage import Store
from .const import DOMAIN
from .catalog import CatalogError


class TicketAccounts:
    def __init__(self,accounts,activity,hass=None):
        self.accounts,self.activity=accounts,activity
        self.purchase_detection=None
        self._lock=asyncio.Lock()
        self._store=Store(hass,1,f"{DOMAIN}.ticket_accounts",private=True) if hass else None
        self._resolved_day=""
        self._recoveries={}

    async def async_load(self):
        data=await self._store.async_load() if self._store else None
        if isinstance(data,dict) and isinstance(data.get("resolved_day"),str):self._resolved_day=data["resolved_day"]

    async def _resolved(self,now):
        self._resolved_day=now.date().isoformat()
        if self._store:await self._store.async_save({"resolved_day":self._resolved_day})

    def note_completion(self):
        for account in self.accounts.values():account.note_completion()

    async def async_check(self):
        if self._lock.locked():return
        async with self._lock:
            now=dt_util.now();detection=self.purchase_detection
            if self._resolved_day==now.date().isoformat() and not (detection and 'shops' in getattr(detection,'zone_config',{})):return
            detected_today=bool(detection and detection.pending_for_today)
            sources={}
            for store,account in self.accounts.items():
                await account._save_options()
                if account.automatic_due(now,detected_today):
                    sources[store]=lambda account=account:account.async_automatic_ticket(now,detected_today)
            if detection and detection.enabled:
                await detection.async_search_ticket_sources(sources)
                if detection._today_identified():await self._resolved(now)
                return
            order=detection.ticket_search_order(sources) if detection else sorted(sources)
            for store in order:
                try:
                    if await sources[store]():
                        await self._resolved(now)
                        break
                except (CatalogError,OSError,TimeoutError) as err:
                    self.activity.record("stores.account",store.upper()+": no se pudo recuperar el ticket automáticamente",
                        source="automatic",diagnostics={"store":store,**getattr(err,"diagnostics",{})})


    def _manual_target(self, receipts, owner, identifier, store):
        detected=receipts.stock.receipts["history"].get(identifier)
        if not detected or not detected.get("detected_purchase"):
            raise CatalogError("La compra detectada ya no está pendiente. Vuelve a abrir el historial.","conflict")
        shops=receipts.settings.snapshot["purchase_detection"].get("shops",[])
        shop=next((shop for shop in shops if store=="shop:"+shop["id"]),None)
        provider=shop.get("account") if shop else store
        account=self.accounts.get(provider)
        if account is None:
            raise CatalogError("Esta tienda no tiene una cuenta vinculada que permita recuperar tickets.")
        if not account.status(owner).get("connected"):
            raise CatalogError("Conecta primero la cuenta de la tienda en Ajustes → Tiendas.")
        day=receipts._purchase_day(detected)
        if day is None:
            raise CatalogError("La fecha de la compra detectada no es válida.")
        return account,provider,shop,detected,day

    async def async_search_manual(self, receipts, owner, identifier, store):
        """Explicit retry for the selected account and detection day, independent of daily gates."""
        account,provider,shop,detected,day=self._manual_target(receipts,owner,identifier,store)
        if self._lock.locked():
            raise CatalogError("Ya se está consultando una cuenta. Espera a que termine.")
        async with self._lock:
            await account.async_sync_history(owner)
            purchases=[{"id":row["id"],"purchased_at":row["purchased_at"],"amount":row["total"]}
                for row in receipts.stock.receipts["history"].values()
                if row.get("store")==provider and row.get("summary_only") and not row.get("detected_purchase")
                and row.get("account_key") and row.get("ticket_available",True)
                and receipts._purchase_day(row)==day and not row.get("detection_id")]
            purchases.sort(key=lambda row:row["purchased_at"],reverse=True)
            self._recoveries={key:value for key,value in self._recoveries.items() if value["until"]>time.time() and not (value["owner"]==owner and value["identifier"]==identifier)}
            if len(self._recoveries)>=20:
                raise CatalogError("Hay demasiadas recuperaciones abiertas. Cierra las anteriores o espera unos minutos.")
            token=str(uuid4())
            self._recoveries[token]={"owner":owner,"identifier":identifier,"store":store,"provider":provider,"day":day,
                "until":time.time()+600,"candidates":{row["id"] for row in purchases}}
            self.activity.record("stores.account","Recuperación manual de compra: historial consultado",source="manual",diagnostics={"store":provider,"purchases":len(purchases),"day":day.isoformat()})
            return {"recovery_token":token,"purchases":purchases}

    async def async_preview_manual(self, receipts, owner, token, purchase_id):
        session=self._recoveries.get(token)
        if not session or session["owner"]!=owner or session["until"]<=time.time() or purchase_id not in session["candidates"]:
            raise CatalogError("La búsqueda ha caducado o el ticket no pertenece a este intento. Vuelve a recuperar la compra.","expired")
        account,provider,shop,detected,day=self._manual_target(receipts,owner,session["identifier"],session["store"])
        detected,shop=deepcopy(detected),deepcopy(shop)
        if provider!=session["provider"] or day!=session["day"]:
            raise CatalogError("La tienda o la fecha han cambiado. Repite la búsqueda.","conflict")
        saved=receipts.stock.receipts["history"].get(purchase_id)
        if not saved or saved.get("store")!=provider or receipts._purchase_day(saved)!=day or saved.get("detection_id"):
            raise CatalogError("El ticket ya no está disponible para esta compra.","conflict")
        if self._lock.locked():
            raise CatalogError("Ya se está consultando una cuenta. Espera a que termine.")
        async with self._lock:
            draft=await receipts.async_review_saved(purchase_id,owner) if saved.get("pending_review") else await account.async_preview_saved(owner,purchase_id)
            if draft["receipt"]["store"]!=provider or receipts._purchase_day(draft["receipt"])!=day:
                receipts.discard(draft["token"],owner)
                raise CatalogError("El ticket recuperado no corresponde al día y la tienda seleccionados.","conflict")
            receipts._draft(draft["token"],owner)["manual_detection"]={"snapshot":deepcopy(detected),"shop":deepcopy(shop)}
            try:
                receipt=await receipts.async_archive_account_ticket(draft["token"],owner)
            except Exception:
                receipts.discard(draft["token"],owner)
                raise
            self._recoveries.pop(token,None)
            return {"receipt":receipt}
