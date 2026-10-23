"""Allow loading this repository as a custom Home Assistant integration."""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable custom integration discovery for every test."""
    yield


@pytest.fixture(autouse=True)
def product_translation(monkeypatch):
    """Catalog tests never depend on the public translation service."""
    translate = AsyncMock(return_value="")
    monkeypatch.setattr("custom_components.improved_shopping_list.catalog.async_translate_name", translate)
    return translate


@pytest.fixture
def archived_store_capabilities(monkeypatch):
    """Exercise preserved connectors deliberately, outside the shipping policy."""
    from custom_components.improved_shopping_list import store_availability
    from custom_components.improved_shopping_list.store_links import STORES
    monkeypatch.setattr(store_availability, "AVAILABLE_STORES", frozenset(STORES))
