"""Pantry persistence, atomic quantities, catalog identity and admin API."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.catalog import Catalog, CatalogError
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.stock import StockManager


async def test_stock_normalization_concurrent_units_and_restart(hass):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({"name":"Seitán"})
    stock=StockManager(hass,catalog);await stock.async_load()
    await asyncio.gather(stock.async_add("seitan"),stock.async_add("SEITÁN"),stock.async_add(" Seitán "))
    assert len(stock.snapshot["items"])==1
    item=stock.snapshot["items"][0]
    assert item["name"]=="Seitán" and item["quantity"]==3 and item["catalog_product_id"]==product["id"]
    restored=StockManager(hass,catalog);await restored.async_load()
    assert restored.snapshot==stock.snapshot
    for _ in range(5):await restored.async_adjust(item["id"],-1)
    assert restored.snapshot["items"][0]["quantity"]==0
    with pytest.raises(CatalogError):await restored.async_adjust(item["id"],True)
    with pytest.raises(CatalogError):await restored.async_adjust(item["id"],-2)


async def test_stock_catalog_changes_and_failed_disk_do_not_lose_units(hass,monkeypatch):
    catalog=Catalog(hass);await catalog.async_load()
    stock=StockManager(hass,catalog);await stock.async_load()
    item=await stock.async_add("Arroz")
    product=await catalog.async_save_product({"name":"Arroz"})
    assert stock.snapshot["items"][0]["catalog_product_id"]==product["id"]
    await stock.async_add("arroz")
    renamed=await catalog.async_save_product({"id":product["id"],"revision":product["revision"],"name":"Arroz integral"})
    assert stock.snapshot["items"][0]["name"]=="Arroz integral"
    assert (await stock.async_add("ARROZ INTEGRAL"))["quantity"]==3
    before=deepcopy(stock.snapshot)
    monkeypatch.setattr(stock._store,"async_save",AsyncMock(side_effect=OSError("disk")))
    with pytest.raises(OSError):await stock.async_adjust(item["id"],1)
    assert stock.snapshot==before
    await catalog.async_delete_product(renamed["id"],renamed["revision"])
    assert stock.snapshot["items"][0]["quantity"]==3


async def test_stock_stale_delete_and_reader_guard(hass):
    catalog=Catalog(hass);await catalog.async_load()
    product=await catalog.async_save_product({"name":"Cacao"})
    stock=StockManager(hass,catalog);await stock.async_load()
    item=await stock.async_add("Cacao")
    await stock.async_adjust(item["id"],1)
    with pytest.raises(CatalogError,match="cambiado"):await stock.async_remove(item["id"],item["revision"])
    with pytest.raises(CatalogError,match="configuración"):await stock.async_change_product(product,1,guard=lambda:False)
    assert stock.snapshot["items"][0]["quantity"]==2
    await stock.async_remove(item["id"],stock.snapshot["items"][0]["revision"])
    assert stock.snapshot["items"]==[] and len(catalog.products)==1


async def test_stock_ws_pushes_permissions_and_unload(hass,hass_ws_client,hass_read_only_user):
    entry=MockConfigEntry(domain=DOMAIN,data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass);assert await hass.config_entries.async_setup(entry.entry_id)
    client=await hass_ws_client(hass)
    token=await hass.auth.async_create_refresh_token(hass_read_only_user,client_id="http://test.local")
    readonly=await hass_ws_client(hass,hass.auth.async_create_access_token(token))
    await readonly.send_json({"id":1,"type":f"{DOMAIN}/stock/subscribe"})
    assert (await readonly.receive_json())["success"] is True
    assert (await readonly.receive_json())["event"]=={"items":[]}
    await readonly.send_json({"id":2,"type":f"{DOMAIN}/stock/add","name":"Cacao"})
    assert (await readonly.receive_json())["error"]["code"]=="unauthorized"
    await readonly.send_json({"id":3,"type":f"{DOMAIN}/stock/save","item_id":"missing","revision":1,"config":{}})
    assert (await readonly.receive_json())["error"]["code"]=="unauthorized"
    await client.send_json({"id":1,"type":f"{DOMAIN}/stock/add","name":"Cacao"})
    item=(await client.receive_json())["result"]
    assert (await readonly.receive_json())["event"]["items"][0]["quantity"]==1
    await client.send_json({"id":2,"type":f"{DOMAIN}/stock/adjust","item_id":item["id"],"delta":1})
    assert (await client.receive_json())["result"]["quantity"]==2
    await readonly.receive_json()
    await readonly.close();await hass.async_block_till_done()
    assert len(hass.data[DOMAIN]["stock"]._listeners)==2  # Stock automation and recurrence synchronization remain subscribed.
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.data[DOMAIN]["stock"]._listeners
    await client.send_json({"id":3,"type":f"{DOMAIN}/stock/get"})
    assert (await client.receive_json())["error"]["code"]=="not_loaded"
