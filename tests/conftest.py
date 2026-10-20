"""Allow loading this repository as a custom Home Assistant integration."""

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable custom integration discovery for every test."""
    yield
