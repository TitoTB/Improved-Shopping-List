"""DIA manual reference bindings with durable, spread public price refreshes."""

import asyncio
import time

from .alcampo import AlcampoManager
from .catalog import CatalogError
from .store_links import normalize_link
from .store_location import reference_location


class DiaPriceManager(AlcampoManager):
    """Reuse Alcampo's schedule and backoff, without discovery or account login."""

    provider = "dia"
    provider_name = "DIA"

    async def async_load(self):
        await super().async_load()
        self._data["search_enabled"] = False

    @property
    def snapshot(self):
        return {key: value for key, value in super().snapshot.items() if key != "search_enabled"}

    async def async_options(self, options):
        if (not isinstance(options, dict) or set(options) != {"refresh_enabled", "days"}
                or type(options["refresh_enabled"]) is not bool
                or type(options["days"]) is not int or not 1 <= options["days"] <= 3650):
            raise CatalogError("Indica un periodo de DIA entre 1 y 3650 días.")
        # Do not make the popup wait for a five-minute reservation to finish.
        # Closing the client also prevents a late executor response reusing it.
        if self._task and not self._task.done():
            self._task.cancel()
            self.sources.close()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return await super().async_options({**options, "search_enabled": False})

    async def _before_request(self, *, manual=False):
        # DIA can need a postal initialization and a price request. Pace both,
        # including the first request after restoring an in-progress session.
        delay = max(self._data["next_request"], self._data["retry_at"]) - time.time()
        if delay > 0:
            await asyncio.sleep(delay)
        if not self._data["refresh_enabled"]:
            raise asyncio.CancelledError
        await super()._before_request(manual=manual)

    async def _fetch(self, identifier):
        return await self.sources.fetch("dia", normalize_link("dia", identifier),
            reference_location("dia"), self._before_request)

