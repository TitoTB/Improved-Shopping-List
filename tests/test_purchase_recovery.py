"""Manual recovery: explicit account/day, scoped selections and atomic detection replacement."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock

from homeassistant.util import dt as dt_util
from custom_components.improved_shopping_list.catalog import CatalogError
from custom_components.improved_shopping_list.receipts import ReceiptManager
from custom_components.improved_shopping_list.ticket_accounts import TicketAccounts


class PurchaseRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        now=dt_util.now().isoformat()
        self.detected={"id":"detected","detected_purchase":True,"store":"unknown","purchased_at":now,"needs_details":True,"summary_only":True,"total":None,"completed_products":[{"name":"Pan"}],"shoppers":["person.one"]}
        self.summary={"id":"saved","store":"carrefour","purchased_at":now,"summary_only":True,"account_key":"private-ref","total":5.22,"ticket_available":True}
        stock=SimpleNamespace(receipts={"history":{"detected":deepcopy(self.detected),"saved":deepcopy(self.summary)},"purchases":{}})
        stock._lock=asyncio.Lock();stock._items={}
        async def persist(items, *, receipts):
            stock._items=items;stock.receipts=receipts
        stock._persist=AsyncMock(side_effect=persist)
        self.receipts=ReceiptManager(None,stock,None,None)
        self.receipts.settings=SimpleNamespace(snapshot={"purchase_detection":{"shops":[{"id":"local","name":"Mi Carrefour","account":"carrefour","image_url":"/local/store.png","color":"#2388dc"}]}})
        self.account=SimpleNamespace(status=Mock(return_value={"connected":True}),async_sync_history=AsyncMock(),async_preview_saved=AsyncMock(side_effect=self.preview),_options={"auto_ticket":False,"history_enabled":False,"ticket_day":"already-tried"})
        self.accounts=TicketAccounts({"carrefour":self.account},SimpleNamespace(record=Mock()))

    async def preview(self, owner, identifier):
        receipt={"id":"ticket","store":"carrefour","purchased_at":self.summary["purchased_at"],"total":5.22,"lines":[],"digest":"digest","account_key":"private-ref"}
        self.receipts._drafts["draft"]={"owner":owner,"expires":time.time()+600,"receipt":deepcopy(receipt)}
        return {"token":"draft","receipt":receipt}

    def test_snapshot_exposes_only_connected_and_enabled_ticket_accounts(self):
        self.receipts.settings.snapshot['stores'] = {
            'carrefour': {'enabled': True}, 'lidl': {'enabled': False},
            'offline': {'enabled': True}}
        connected = SimpleNamespace(status=Mock(return_value={'connected': True}))
        offline = SimpleNamespace(status=Mock(return_value={'connected': False}))
        self.receipts.ticket_accounts = SimpleNamespace(accounts={
            'carrefour': connected, 'lidl': connected, 'offline': offline, 'unset': connected})
        self.assertEqual(self.receipts.snapshot['ticket_accounts'], {
            'carrefour': True, 'lidl': False, 'offline': False, 'unset': False})
        self.receipts.settings.snapshot['stores']['carrefour']['enabled'] = False
        self.assertFalse(self.receipts.snapshot['ticket_accounts']['carrefour'])

    async def test_forced_search_ignores_auto_options_and_filters_account_day(self):
        rows=self.receipts.stock.receipts["history"]
        rows["other-day"]={**self.summary,"id":"other-day","purchased_at":(dt_util.now()-timedelta(days=1)).isoformat()}
        rows["other-store"]={**self.summary,"id":"other-store","store":"lidl"}
        rows["unavailable"]={**self.summary,"id":"unavailable","ticket_available":False}
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        self.assertEqual([p["id"] for p in result["purchases"]],["saved"])
        self.account.async_sync_history.assert_awaited_once_with("admin")
        self.assertEqual(self.account._options["ticket_day"],"already-tried")
        self.assertEqual(rows["detected"],self.detected)

    async def test_recovery_replaces_detection_immediately_and_saves_pending_ticket(self):
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","shop:local")
        recovered=await self.accounts.async_preview_manual(self.receipts,"admin",result["recovery_token"],"saved")
        receipt=recovered["receipt"]
        self.assertEqual(list(self.receipts.stock.receipts["history"]),["ticket"])
        self.assertTrue(receipt["pending_review"])
        self.assertEqual(receipt["detection_id"],"detected")
        self.assertEqual(receipt["shop_name"],"Mi Carrefour")
        self.assertEqual(receipt["shoppers"],["person.one"])
        self.assertEqual(self.receipts.stock._items,{})
        self.assertNotIn("draft",self.receipts._drafts)
        with self.assertRaises(CatalogError):
            await self.accounts.async_preview_manual(self.receipts,"admin",result["recovery_token"],"saved")

    async def test_owner_expiry_and_unoffered_ticket_are_rejected(self):
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        token=result["recovery_token"]
        for owner,identifier in [("other-admin","saved"),("admin","unoffered")]:
            with self.assertRaises(CatalogError):await self.accounts.async_preview_manual(self.receipts,owner,token,identifier)
        self.accounts._recoveries[token]["until"]=0
        with self.assertRaises(CatalogError):await self.accounts.async_preview_manual(self.receipts,"admin",token,"saved")
        self.account.async_preview_saved.assert_not_awaited()

    async def test_changed_detection_is_not_overwritten_during_download(self):
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        async def changed(owner,identifier):
            draft=await self.preview(owner,identifier)
            self.receipts.stock.receipts["history"]["detected"]["total"]=8
            return draft
        self.account.async_preview_saved.side_effect=changed
        with self.assertRaises(CatalogError):
            await self.accounts.async_preview_manual(self.receipts,"admin",result["recovery_token"],"saved")
        self.assertEqual(self.receipts.stock.receipts["history"]["detected"]["total"],8)
        self.receipts.stock._persist.assert_not_awaited()
        self.assertNotIn("draft",self.receipts._drafts)

    async def test_save_failure_keeps_unknown_purchase_and_allows_retry(self):
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        self.receipts.stock._persist.side_effect=OSError("storage unavailable")
        with self.assertRaises(OSError):
            await self.accounts.async_preview_manual(self.receipts,"admin",result["recovery_token"],"saved")
        self.assertEqual(self.receipts.stock.receipts["history"]["detected"],self.detected)
        self.assertIn(result["recovery_token"],self.accounts._recoveries)
        self.assertNotIn("draft",self.receipts._drafts)

    async def test_unlinked_disconnected_or_missing_detection_never_contacts_provider(self):
        for identifier,store in [("missing","carrefour"),("detected","other")]:
            with self.assertRaises(CatalogError):await self.accounts.async_search_manual(self.receipts,"admin",identifier,store)
        self.account.status.return_value={"connected":False}
        with self.assertRaises(CatalogError):await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        self.account.async_sync_history.assert_not_awaited()

    async def test_empty_results_and_wrong_detail_leave_detection_untouched(self):
        self.receipts.stock.receipts["history"].pop("saved")
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        self.assertEqual(result["purchases"],[])
        self.receipts.stock.receipts["history"]["saved"]=deepcopy(self.summary)
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        async def wrong(owner,identifier):
            draft=await self.preview(owner,identifier);draft["receipt"]["purchased_at"]=(dt_util.now()-timedelta(days=1)).isoformat();return draft
        self.account.async_preview_saved.side_effect=wrong
        with self.assertRaises(CatalogError):await self.accounts.async_preview_manual(self.receipts,"admin",result["recovery_token"],"saved")
        self.assertNotIn("draft",self.receipts._drafts)
        self.assertEqual(self.receipts.stock.receipts["history"]["detected"],self.detected)

    async def test_automatic_association_uses_ticket_not_completed_product_overlap(self):
        receipt={**self.summary,"pending_review":True,"lines":[{"description":"Producto extra","count":2,"amount":5.22}]}
        self.assertTrue(self.receipts._detection_matches(self.detected,receipt))
        self.assertFalse(self.receipts._detection_matches(self.detected,{**receipt,"pending_review":False}))
        self.assertFalse(self.receipts._detection_matches(self.detected,{**receipt,"purchased_at":(dt_util.now()-timedelta(days=1)).isoformat()}))
        self.assertFalse(self.receipts._detection_matches({**self.detected,"account":"lidl"},receipt))
