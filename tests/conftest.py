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
