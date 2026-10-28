"""Serialize automatic account lookups in zone/favorite order across stores."""
import asyncio
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
