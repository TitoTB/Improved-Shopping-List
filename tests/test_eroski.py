"""Eroski exact-center anonymous form flow and product identity checks."""

from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import aiohttp
import pytest
from yarl import URL

from custom_components.improved_shopping_list.eroski import EroskiClient, EroskiError, parse_page, pickup_areas, product_offer, ROOT, SLOT_PATH
from custom_components.improved_shopping_list.price_sources import PriceSources, PriceError
from custom_components.improved_shopping_list.regional_stores import async_resolve_areas
from custom_components.improved_shopping_list.store_links import normalize_link

AREA="f7e80707-fd7a-437c-b451-698301f2cf77"
CONFIG={"postal_code":"48001","area_id":AREA,"zone":"244"}
PRODUCT_URL=ROOT+"/es/productdetail/17528126-aceite-especial-para-freir/"
SELECTION=f'''<form id="slotForm" method="post" action="{ROOT}:443{SLOT_PATH}">
<input name="t:formdata" value="fresh-session-form"><input name="zipCode" value="48001"></form>
<li data-address-ref="{AREA}" data-shopref="244" data-currency="EUR" data-deliverymode="DRIVE_DELIVERY">
<span class="center_name">BIZKAIA - Eroski <b>Deusto</b></span></li>'''
PRODUCT=f'''<link rel="canonical" href="{PRODUCT_URL}"><h1 itemprop="description">Aceite <b>KOIPE</b></h1>
<meta itemprop="priceCurrency" content="EUR"><span itemprop="price" class="offer-now"> 3,29</span>'''


def test_data_parser_does_not_execute_markup_and_preserves_names():
    page=parse_page(SELECTION)
    assert pickup_areas(page)==[{"id":AREA,"zone":"244","name":"BIZKAIA - Eroski Deusto"}]
    assert page.forms["slotForm"]["fields"]["t:formdata"]=="fresh-session-form"
    result=product_offer(PRODUCT,normalize_link("eroski",PRODUCT_URL))
    assert result["price"]=="3.29" and result["store_name"]=="Aceite KOIPE" and result["currency"]=="EUR"


@pytest.mark.parametrize("value",["17528126",ROOT+"/es/productdetail/17528126/",PRODUCT_URL.replace("https:","http:"),
    PRODUCT_URL.replace("supermercado.eroski.es","evil.example"),PRODUCT_URL.replace("17528126-","../17528126-")])
def test_requires_official_complete_product_link(value):
    with pytest.raises(ValueError):normalize_link("eroski",value)


def test_product_path_keeps_canonical_trailing_slash():
    assert normalize_link("eroski",PRODUCT_URL.rstrip("/")+"?tracking=1")["url"]==PRODUCT_URL


@pytest.mark.parametrize("markup",[PRODUCT.replace("17528126-","999-"),PRODUCT.replace('content="EUR"','content="USD"'),
    PRODUCT.replace("3,29","0,00"),PRODUCT.replace("3,29","NaN"),PRODUCT+PRODUCT,
    '<html>Inicia sesión</html>'])
def test_invalid_or_ambiguous_prices_never_replace_cache(markup):
    with pytest.raises(EroskiError):product_offer(markup,normalize_link("eroski",PRODUCT_URL))


async def test_anonymous_flow_applies_center_reuses_session_and_paces_every_call(hass,monkeypatch):
    client=EroskiClient(hass)
    calls=[]
    async def request(path,gate,*,data=None):
        if gate:await gate()
        calls.append((path,data))
        if path=="/es/":return "<html></html>"
        if path.startswith("/es/login/delivery/?"):return SELECTION
        if path==SLOT_PATH:
            assert data=={"t:formdata":"fresh-session-form","zipCode":"48001","radiogroup":"offQuick","selectedAddressRef":AREA,"t:zoneid":"^"}
            client.session.cookie_jar.update_cookies({"supermarket.ali.shop":"244"},URL(ROOT))
            return '{"_tapestry":{"redirectURL":"https://supermercado.eroski.es"}}'
        assert path==urlsplit(PRODUCT_URL).path
        return PRODUCT
    monkeypatch.setattr(client,"request",request)
    # Test fixture may replace HA's cookie jar: preserve this client's isolated jar.
    original_start=client._start
    def start():
        original_start();client.session._cookie_jar=aiohttp.CookieJar()
    monkeypatch.setattr(client,"_start",start)
    gate=AsyncMock()
    try:
        assert (await client.fetch(normalize_link("eroski",PRODUCT_URL),CONFIG,gate))["price"]=="3.29"
        assert client._shop()=="244" and gate.await_count==4
        assert (await client.fetch(normalize_link("eroski",PRODUCT_URL),CONFIG,gate))["price"]=="3.29"
        assert gate.await_count==5 and len(calls)==5
    finally:client.close()
    assert client.session is None and client.context is None


async def test_no_fallback_when_selection_does_not_apply(hass,monkeypatch):
    client=EroskiClient(hass)
    async def request(path,gate,**kwargs):
        return '{"_tapestry":{"redirectURL":"https://supermercado.eroski.es"}}' if path==SLOT_PATH else SELECTION
    monkeypatch.setattr(client,"request",request)
    with pytest.raises(EroskiError):await client.fetch(normalize_link("eroski",PRODUCT_URL),CONFIG,AsyncMock())
    assert client.session is None


async def test_rejects_foreign_form_and_inconsistent_center(hass,monkeypatch):
    client=EroskiClient(hass)
    monkeypatch.setattr(client,"request",AsyncMock(return_value=SELECTION.replace(ROOT,"https://evil.example")))
    with pytest.raises(EroskiError):await client.fetch(normalize_link("eroski",PRODUCT_URL),CONFIG,AsyncMock())
    assert client.request.await_count==2  # Only home and center page, never submit a foreign action.
    assert client.session is None


async def test_coverage_reads_names_and_does_not_select_or_reserve(hass,aioclient_mock):
    aioclient_mock.get(ROOT+"/es/",text="home")
    aioclient_mock.get(ROOT+"/es/login/delivery/?zipCode=48001",text=SELECTION)
    result=await async_resolve_areas(hass,"eroski","48001")
    assert result["areas"][0]["zone"]=="244"
    assert [call[0] for call in aioclient_mock.mock_calls]==["GET","GET"]


async def test_403_is_diagnostic_and_closes_session(hass,aioclient_mock):
    aioclient_mock.get(ROOT+"/es/",status=403,headers={"Retry-After":"600"})
    source=PriceSources(hass);gate=AsyncMock()
    with pytest.raises(PriceError) as err:await source.fetch("eroski",normalize_link("eroski",PRODUCT_URL),CONFIG,gate)
    assert err.value.diagnostics["http_status"]==403 and err.value.diagnostics["retry_seconds"]==600
    gate.assert_awaited_once()
    assert source.eroski.session is None
