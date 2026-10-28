"""Provider-independent catch-up; runnable without a Home Assistant runtime."""
import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, call, patch

SPEC = importlib.util.spec_from_file_location("account_history", Path(__file__).parents[1] / "custom_components/improved_shopping_list/account_history.py")
history = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history)


class AccountHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_pages_import_after_current_ticket_without_downloading_older_tickets(self):
        fetch = AsyncMock(side_effect=[{"purchases":["today"], "next_cursor":{"page":2}},
            {"purchases":["older"], "next_cursor":{"page":3}}, {"purchases":[], "next_cursor":None}])
        with patch.object(history.asyncio, "sleep", new_callable=AsyncMock) as pause:
            async with history.account_purchase_check(fetch, pagination_error=lambda:ValueError("repeated")) as first:
                self.assertEqual(first["purchases"], ["today"])
                fetch.assert_awaited_once_with(None)
            self.assertEqual(fetch.await_args_list, [call(None),call({"page":2}),call({"page":3})])
            self.assertEqual(pause.await_count, 2)

    async def test_ticket_failure_still_imports_remaining_summaries(self):
        fetch = AsyncMock(side_effect=[{"next_cursor":{"page":2}}, {"next_cursor":None}])
        with patch.object(history.asyncio, "sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(ValueError, "ticket failed"):
                async with history.account_purchase_check(fetch, pagination_error=lambda:ValueError("repeated")):
                    raise ValueError("ticket failed")
        self.assertEqual(fetch.await_count, 2)

    async def test_repeated_cursor_stops_additional_requests(self):
        fetch = AsyncMock(return_value={"next_cursor":{"page":2}})
        with patch.object(history.asyncio, "sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(ValueError,"repeated"):
                async with history.account_purchase_check(fetch, pagination_error=lambda:ValueError("repeated")):
                    pass
        self.assertEqual(fetch.await_count, 2)

    async def test_cancelled_ticket_does_not_request_more_pages(self):
        fetch = AsyncMock(return_value={"next_cursor":{"page":2}})
        with self.assertRaises(asyncio.CancelledError):
            async with history.account_purchase_check(fetch, pagination_error=lambda:ValueError("repeated")):
                raise asyncio.CancelledError
        fetch.assert_awaited_once_with(None)

    async def test_bounded_history_and_single_page(self):
        for cursor, limit, expected in [(None,100,1),({"page":2},1,1)]:
            fetch = AsyncMock(return_value={"next_cursor":cursor})
            async with history.account_purchase_check(fetch, pagination_error=lambda:ValueError("repeated"),page_limit=limit):
                pass
            self.assertEqual(fetch.await_count, expected)


if __name__ == "__main__":
    unittest.main()
