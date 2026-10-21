"""Anonymous postal coverage and exact product/center price selection."""

from copy import deepcopy
import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.regional_stores import async_resolve_areas, coverage_areas
from custom_components.improved_shopping_list.stores import StoreError
from custom_components.improved_shopping_list.price_sources import PriceSources, PriceError, consum_offer, sirena_offer, sirena_product
from custom_components.improved_shopping_list.store_links import normalize_link

CONSUM_AREA = [{"shippingAreas":[{"shippingZoneId":"301D", "deliveryTypeId":"D", "enabled":True,
    "zone":{"id":301, "name":"Centro 301", "address":{"city":"Cullera"}}}]}]
SIRENA_AREAS = [{"id":"v2.example", "sellers":[{"id":"lasirena259"},{"id":"lasirena102"}]}]
CONSUM_CONFIG = {"postal_code":"46409", "area_id":"301D", "zone":"301"}
SIRENA_CONFIG = {"postal_code":"28024", "area_id":"lasirena259"}
CONSUM_PRODUCT = {"code":"7394260", "ean":"8410199023094", "productData":{"name":"Patatas", "temporaryOutOfStock":False},
    "priceData":{"prices":[{"id":"PRICE", "value":{"centAmount":2.45, "centUnitAmount":14.41}}],"unitPriceUnitType":"1 Kg"}}
SIRENA_PRODUCT = [{"productId":"655", "productName":"Salmón", "items":[{"itemId":"700", "ean":"8414532006553"}]}]
SIRENA_PRICE = {"postalCode":"28024", "country":"ESP", "items":[{"id":"700", "seller":"lasirena259",
    "quantity":1, "availability":"available", "sellingPrice":1699}]}


@pytest.mark.parametrize(("store","url","data","count"), [
    ("consum","https://tienda.consum.es/api/rest/V1.0/shipping/area?shippingMethod=D&zipCode=46409",CONSUM_AREA,1),
    ("lasirena","https://www.lasirena.es/es/api/checkout/pub/regions?country=ESP&postalCode=46409&sc=1",SIRENA_AREAS,2)])
async def test_public_coverage(hass, aioclient_mock, store, url, data, count):
    aioclient_mock.get(url,json=data)
    result = await async_resolve_areas(hass,store,"46409")
    assert result["postal_code"] == "46409" and len(result["areas"]) == count


@pytest.mark.parametrize("postal",["", "00000", "53000", "４６４０９", "46409&x=1"])
async def test_invalid_postal_never_fetches(hass, aioclient_mock, postal):
    with pytest.raises(StoreError):
        await async_resolve_areas(hass,"consum",postal)
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(("status","body"),[(200,"[]"),(200,"{}"),(200,"not json"),(200,"x"*262145),(403,"blocked"),(302,"redirect")])
async def test_coverage_errors_are_not_saved_or_defaulted(hass, aioclient_mock, status, body):
    aioclient_mock.get("https://tienda.consum.es/api/rest/V1.0/shipping/area?shippingMethod=D&zipCode=46409",status=status,text=body)
    with pytest.raises(StoreError):
        await async_resolve_areas(hass,"consum","46409")


def test_filters_disabled_or_inconsistent_coverage():
    data=deepcopy(CONSUM_AREA)
    data[0]["shippingAreas"][0]["zone"]["id"]=302
    assert coverage_areas("consum",data)==[]
    data=deepcopy(CONSUM_AREA);data[0]["shippingAreas"][0]["enabled"]=False
    assert coverage_areas("consum",data)==[]
    assert coverage_areas("lasirena",[{"sellers":[{"id":"../bad"}]}])==[]


async def test_selected_area_must_belong_to_postal_and_toggle_is_local(hass,monkeypatch):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"},options={"unrelated":True})
    entry.add_to_hass(hass);settings=ListSettings(hass);settings.attach(entry);hass.data[DOMAIN]={"active":True}
    resolver=AsyncMock(return_value={"areas":coverage_areas("consum",CONSUM_AREA)})
    monkeypatch.setattr("custom_components.improved_shopping_list.list_settings.async_resolve_areas",resolver)
    with pytest.raises(StoreError):await settings.async_update_regional("consum",True,"46409","999D",True)
    assert not settings.snapshot["stores"]["consum"]["enabled"]
    await settings.async_update_regional("consum",True,"46409","301D",True)
    assert settings.snapshot["stores"]["consum"]["zone"]=="301"
    assert settings.snapshot["favorite_store"]=="consum"
    resolver.reset_mock()
    await settings.async_update_regional("consum",False)
    await settings.async_update_regional("consum",True)
    resolver.assert_not_awaited()
    assert entry.options["unrelated"] is True
    previous=deepcopy(settings.snapshot)
    resolver.side_effect=StoreError("Sin cobertura")
    with pytest.raises(StoreError):await settings.async_update_regional("consum",True,"28024","301D",True)
    assert settings.snapshot==previous


@pytest.mark.parametrize(("store","url","identifier"),[
    ("consum","https://tienda.consum.es/es/p/patatas-fritas/7394260?tracking=1","7394260"),
    ("lasirena","https://www.lasirena.es/es/lomos-de-salmon-655/p","655")])
def test_official_links_and_ids(store,url,identifier):
    assert normalize_link(store,url)["id"]==identifier
    assert "?" not in normalize_link(store,url)["url"]
    assert normalize_link(store,identifier)["id"]==identifier
    with pytest.raises(ValueError):normalize_link(store,url.replace("https://","https://evil.example/"))
    with pytest.raises(ValueError):normalize_link(store,{"id":"999", "url":url})


async def test_consum_decimal_euros_and_paced_anonymous_source(hass, aioclient_mock):
    aioclient_mock.get("https://tienda.consum.es/api/rest/V1.0/catalog/product/code/7394260?showRecommendations=false",json=CONSUM_PRODUCT)
    gate=AsyncMock()
    result=await PriceSources(hass).fetch("consum",normalize_link("consum","7394260"),CONSUM_CONFIG,gate)
    assert result["price"]=="2.45" and result["reference_price"]=="14.41" and result["ean"]=="8410199023094"
    gate.assert_awaited_once()
    with pytest.raises(PriceError):consum_offer({**CONSUM_PRODUCT,"code":"wrong"},normalize_link("consum","7394260"))


async def test_sirena_uses_real_sku_and_selected_center_with_gate_for_each_request(hass,aioclient_mock):
    aioclient_mock.get("https://www.lasirena.es/api/catalog_system/pub/products/search?fq=productId%3A655",json=SIRENA_PRODUCT)
    aioclient_mock.get("https://www.lasirena.es/_v/public/middleware/client/vtex/simulationCart/700/lasirena259/28024",json=SIRENA_PRICE)
    gate=AsyncMock()
    result=await PriceSources(hass).fetch("lasirena",normalize_link("lasirena","655"),SIRENA_CONFIG,gate)
    assert result["price"]=="16.99" and result["ean"]=="8414532006553" and gate.await_count==2
    assert len(aioclient_mock.mock_calls)==2


@pytest.mark.parametrize(("field","value"),[("id","wrong"),("seller","lasirena102"),("quantity",2),("sellingPrice",-1),("sellingPrice","1699")])
def test_sirena_rejects_wrong_product_center_or_price(field,value):
    data=deepcopy(SIRENA_PRICE);data["items"][0][field]=value
    with pytest.raises(PriceError):sirena_offer(data,SIRENA_PRODUCT[0],SIRENA_PRODUCT[0]["items"][0],SIRENA_CONFIG)


def test_unavailable_products_do_not_replace_price_with_zero():
    data=deepcopy(SIRENA_PRICE);data["items"][0].update(availability="cannotBeDelivered",sellingPrice=0)
    assert sirena_offer(data,SIRENA_PRODUCT[0],SIRENA_PRODUCT[0]["items"][0],SIRENA_CONFIG) is None
    assert sirena_product([],normalize_link("lasirena","655")) is None
    data=deepcopy(SIRENA_PRODUCT);data[0]["items"].append({"itemId":"701"})
    with pytest.raises(PriceError):sirena_product(data,normalize_link("lasirena","655"))


async def test_regional_ws_requires_admin(hass,hass_ws_client,hass_read_only_user,aioclient_mock):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id="http://test.local")
    client=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await client.send_json({"id":1,"type":f"{DOMAIN}/settings/resolve_store","store":"consum","postal_code":"46409"})
    assert (await client.receive_json())["error"]["code"]=="unauthorized"
    assert aioclient_mock.call_count==0


async def test_regional_ws_resolve_save_and_cached_read(hass,hass_ws_client,aioclient_mock):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"});entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    aioclient_mock.get("https://tienda.consum.es/api/rest/V1.0/shipping/area?shippingMethod=D&zipCode=46409",json=CONSUM_AREA)
    client=await hass_ws_client(hass)
    await client.send_json({"id":1,"type":f"{DOMAIN}/settings/resolve_store","store":"consum","postal_code":"46409"})
    assert (await client.receive_json())["result"]["areas"][0]["id"]=="301D"
    await client.send_json({"id":2,"type":f"{DOMAIN}/settings/store","store":"consum","enabled":False,
        "postal_code":"46409","area_id":"301D","verify":True})
    result=await client.receive_json()
    assert result["success"] and result["result"]["stores"]["consum"]["zone"]=="301"
    count=aioclient_mock.call_count
    await client.send_json({"id":3,"type":f"{DOMAIN}/catalog/store_prices","store":"consum"})
    assert (await client.receive_json())["result"]["products"]==[]
    assert aioclient_mock.call_count==count


async def test_late_postal_configuration_after_reload_is_discarded(hass,monkeypatch):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"});entry.add_to_hass(hass)
    settings=ListSettings(hass);settings.attach(entry);hass.data[DOMAIN]={"active":True}
    entered,resume=asyncio.Event(),asyncio.Event()
    async def resolve(*args):
        entered.set();await resume.wait()
        return {"areas":coverage_areas("consum",CONSUM_AREA)}
    monkeypatch.setattr("custom_components.improved_shopping_list.list_settings.async_resolve_areas",resolve)
    task=asyncio.create_task(settings.async_update_regional("consum",True,"46409","301D",True))
    await entered.wait();settings.detach();settings.attach(entry);resume.set()
    with pytest.raises(StoreError):await task
    assert not settings.snapshot["stores"]["consum"]["enabled"]


async def test_sirena_403_stops_before_simulation(hass,aioclient_mock):
    aioclient_mock.get("https://www.lasirena.es/api/catalog_system/pub/products/search?fq=productId%3A655",status=403)
    gate=AsyncMock()
    with pytest.raises(PriceError) as err:
        await PriceSources(hass).fetch("lasirena",normalize_link("lasirena","655"),SIRENA_CONFIG,gate)
    assert err.value.diagnostics["http_status"]==403
    gate.assert_awaited_once()
    assert aioclient_mock.call_count==1
