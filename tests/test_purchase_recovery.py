"""Manual recovery: explicit account/day, scoped selections and atomic detection replacement."""
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
        self.detected={"id":"detected","detected_purchase":True,"store":"unknown","purchased_at":now,"needs_details":True,"total":None,"completed_products":[{"name":"Pan"}],"shoppers":["person.one"]}
        self.summary={"id":"saved","store":"carrefour","purchased_at":now,"summary_only":True,"account_key":"private-ref","total":5.22,"ticket_available":True}
        stock=SimpleNamespace(receipts={"history":{"detected":deepcopy(self.detected),"saved":deepcopy(self.summary)},"purchases":{}})
        self.receipts=ReceiptManager(None,stock,None,None)
        self.receipts.settings=SimpleNamespace(snapshot={"purchase_detection":{"shops":[{"id":"local","name":"Mi Carrefour","account":"carrefour","image_url":"/local/store.png","color":"#2388dc"}]}})
        self.account=SimpleNamespace(status=Mock(return_value={"connected":True}),async_sync_history=AsyncMock(),async_preview_saved=AsyncMock(side_effect=self.preview),_options={"auto_ticket":False,"history_enabled":False,"ticket_day":"already-tried"})
        self.accounts=TicketAccounts({"carrefour":self.account},SimpleNamespace(record=Mock()))

    async def preview(self, owner, identifier):
        receipt={"id":"ticket","store":"carrefour","purchased_at":self.summary["purchased_at"],"total":5.22,"lines":[]}
        self.receipts._drafts["draft"]={"owner":owner,"expires":time.time()+600,"receipt":deepcopy(receipt)}
        return {"token":"draft","receipt":receipt}

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

    async def test_manual_preview_does_not_commit_and_confirmation_replaces_detection(self):
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","shop:local")
        draft=await self.accounts.async_preview_manual(self.receipts,"admin",result["recovery_token"],"saved")
        self.assertEqual(self.receipts.stock.receipts["history"]["detected"],self.detected)
        history=deepcopy(self.receipts.stock.receipts["history"])
        receipt=deepcopy(draft["receipt"])
        self.receipts._apply_manual_detection(self.receipts._draft("draft","admin"),receipt,history)
        self.assertNotIn("detected",history)
        self.assertEqual(receipt["detection_id"],"detected")
        self.assertEqual(receipt["shop_name"],"Mi Carrefour")
        self.assertEqual(receipt["shoppers"],["person.one"])

    async def test_owner_expiry_and_unoffered_ticket_are_rejected(self):
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        token=result["recovery_token"]
        for owner,identifier in [("other-admin","saved"),("admin","unoffered")]:
            with self.assertRaises(CatalogError):await self.accounts.async_preview_manual(self.receipts,owner,token,identifier)
        self.accounts._recoveries[token]["until"]=0
        with self.assertRaises(CatalogError):await self.accounts.async_preview_manual(self.receipts,"admin",token,"saved")
        self.account.async_preview_saved.assert_not_awaited()

    async def test_changed_detection_is_not_overwritten_at_confirmation(self):
        result=await self.accounts.async_search_manual(self.receipts,"admin","detected","carrefour")
        draft=await self.accounts.async_preview_manual(self.receipts,"admin",result["recovery_token"],"saved")
        history=deepcopy(self.receipts.stock.receipts["history"]);history["detected"]["total"]=8
        with self.assertRaises(CatalogError):self.receipts._apply_manual_detection(self.receipts._draft("draft","admin"),draft["receipt"],history)
        self.assertIn("detected",history)

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
