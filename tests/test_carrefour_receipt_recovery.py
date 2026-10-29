"""An inconsistent account breakdown may use an independently validated PDF."""
import asyncio
import base64
from datetime import timedelta
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock

from homeassistant.util import dt as dt_util
from custom_components.improved_shopping_list.catalog import CatalogError
from custom_components.improved_shopping_list.carrefour_account import CarrefourAccount, CarrefourAccountError
from custom_components.improved_shopping_list.receipt_parser import extract_carrefour_account_ticket
from custom_components.improved_shopping_list.receipts import ReceiptManager


class CarrefourReceiptRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.when=dt_util.now().isoformat()
        self.detail={"ticketId":"test-ticket","date":self.when,"header":{"netAmount":5,"numberItems":1,"numberLinesItems":1},"totalDiscount":-1,"items":[{"description":"PAN","numberUnits":1,"netAmount":7}],"private_customer":"DO_NOT_LOG"}
        self.receipt={"id":"pdf-ticket","total":5,"purchased_at":self.when,"store":"carrefour","lines":[]}
        executor=AsyncMock(return_value=self.receipt)
        self.receipts=ReceiptManager(SimpleNamespace(async_add_executor_job=executor),None,None,None)
        self.receipts._prepare_preview=AsyncMock(side_effect=lambda receipt,owner:{"token":"draft","receipt":receipt})
        async def parse(detail,reference,amount,owner):
            return extract_carrefour_account_ticket(detail,reference,amount)
        self.receipts.async_preview_carrefour_ticket=AsyncMock(side_effect=parse)
        self.account=CarrefourAccount.__new__(CarrefourAccount)
        self.account.receipts=self.receipts;self.account.activity=SimpleNamespace(record=Mock())
        self.account._lock=asyncio.Lock();self.account._headers=AsyncMock(return_value={})
        self.account._purchases={"key":{"id":"test-ticket","owner":"owner","expires":time.time()+600,"supported":True,"amount":5,"purchased_at":self.when}}
        self.account._http=AsyncMock(side_effect=[self.detail,b"%PDF-test"])

    async def test_inconsistent_detail_uses_verified_pdf_and_logs_only_numeric_totals(self):
        result=await self.account.async_preview("owner","key")
        self.assertEqual(result["receipt"]["total"],5)
        self.assertEqual(self.account._http.await_count,2)
        diag=self.account.activity.record.call_args.kwargs["diagnostics"]
        self.assertEqual(diag["detail_format_error"],"receipt_detail_amount")
        self.assertEqual(diag["items_subtotal"],7)
        self.assertEqual(diag["difference"],1)
        self.assertNotIn("DO_NOT_LOG",str(diag))

    async def test_pdf_with_different_amount_is_not_prepared(self):
        self.receipt["total"]=6
        with self.assertRaises(CarrefourAccountError) as error:
            await self.account.async_preview("owner","key")
        self.assertEqual(error.exception.diagnostics["pdf_error"],"receipt_purchase_mismatch")
        self.receipts._prepare_preview.assert_not_awaited()

    async def test_pdf_with_different_day_is_not_prepared(self):
        self.receipt["purchased_at"]=(dt_util.now()-timedelta(days=1)).isoformat()
        with self.assertRaises(CarrefourAccountError):await self.account.async_preview("owner","key")
        self.receipts._prepare_preview.assert_not_awaited()

    async def test_unavailable_pdf_preserves_breakdown_diagnostics(self):
        self.account._http.side_effect=[self.detail,CarrefourAccountError("Unavailable","pdf",status=500)]
        with self.assertRaises(CarrefourAccountError) as error:await self.account.async_preview("owner","key")
        self.assertEqual(error.exception.diagnostics["stage"],"ticket_pdf_fallback")
        self.assertEqual(error.exception.diagnostics["difference"],1)
        self.assertEqual(error.exception.diagnostics["http_status"],500)
        self.receipts._prepare_preview.assert_not_awaited()

    async def test_wrong_identity_and_duplicate_never_use_pdf(self):
        for code in ("duplicate","conflict","invalid"):
            self.receipts.async_preview_carrefour_ticket.side_effect=CatalogError("Invalid",code)
            self.account._http.reset_mock(side_effect=True)
            self.account._http.return_value=self.detail
            with self.assertRaises(CatalogError):await self.account.async_preview("owner","key")
            self.assertEqual(self.account._http.await_count,1)

    async def test_parser_still_rejects_the_inconsistent_detail(self):
        with self.assertRaises(CatalogError) as error:extract_carrefour_account_ticket(self.detail,"test-ticket",5)
        self.assertEqual(error.exception.code,"receipt_detail_amount")
        self.receipts._prepare_preview.assert_not_awaited()
