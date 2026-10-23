"""Serialize automatic account lookups in zone/favorite order across stores."""
import asyncio
from homeassistant.util import dt as dt_util
from .catalog import CatalogError


class TicketAccounts:
    def __init__(self,accounts,activity):
        self.accounts,self.activity=accounts,activity
        self.purchase_detection=None
        self._lock=asyncio.Lock()

    def note_completion(self):
        for account in self.accounts.values():account.note_completion()

    async def async_check(self):
        if self._lock.locked():return
        async with self._lock:
            now=dt_util.now();detection=self.purchase_detection
            detected_today=bool(detection and detection.pending_for_today)
            sources={}
            for store,account in self.accounts.items():
                await account._save_options()
                if account.automatic_due(now,detected_today):
                    sources[store]=lambda account=account:account.async_automatic_ticket(now,detected_today)
            if detection and detection.enabled:
                await detection.async_search_ticket_sources(sources)
                return
            order=detection.ticket_search_order(sources) if detection else sorted(sources)
            for store in order:
                try:
                    if await sources[store]():break
                except (CatalogError,OSError,TimeoutError) as err:
                    self.activity.record("stores.account",store.upper()+": no se pudo recuperar el ticket automáticamente",
                        source="automatic",diagnostics={"store":store,**getattr(err,"diagnostics",{})})
