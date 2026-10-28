"""Shared history catch-up for account checks, without extra ticket downloads."""
import asyncio
from contextlib import asynccontextmanager
import json


@asynccontextmanager
async def account_purchase_check(fetch_page, *, pagination_error, page_limit=100):
    """Yield recent purchases, then import remaining summary pages.

    fetch_page must import summaries idempotently, regardless of the optional
    initial-history setting. Retrieve the current ticket before advancing pages:
    some providers use short-lived references. Never download older tickets here.
    """
    first = await fetch_page(None)
    cancelled = False
    try:
        yield first
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        if not cancelled:
            cursor, seen = first.get("next_cursor"), set()
            for _ in range(page_limit - 1):
                if cursor is None:
                    break
                marker = json.dumps(cursor, sort_keys=True)
                if marker in seen:
                    raise pagination_error()
                seen.add(marker)
                await asyncio.sleep(1)
                page = await fetch_page(cursor)
                cursor = page.get("next_cursor")
