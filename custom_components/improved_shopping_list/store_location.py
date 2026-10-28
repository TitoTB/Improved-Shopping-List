"""Verified public reference locations, independent of a user's address.

Changing these identifiers changes the price-cache scope. Never relabel cached
offers from an older center as prices of the new reference location.
"""

from copy import deepcopy

REFERENCE_LOCATIONS = {
    "lidl": {},  # Account receipts have no public-price center.
    "mercadona": {"postal_code": "28024", "warehouse": "mad1"},
    "carrefour": {"postal_code": "28024", "sale_point": "005704"},
    "alcampo": {"postal_code": "28024", "region_id": "deb03a69-3104-4451-9ffa-3a55dc156d9f"},
    "consum": {"postal_code": "46409", "area_id": "301D", "area_name": "Centro 301", "zone": "301"},
    "lasirena": {"postal_code": "28024", "area_id": "lasirena259", "area_name": "La Sirena 259", "zone": ""},
    "eroski": {"postal_code": "48001", "area_id": "f7e80707-fd7a-437c-b451-698301f2cf77", "area_name": "BIZKAIA - Eroski Deusto", "zone": "244"},
    "dia": {"postal_code": "28024", "area_id": "28024", "area_name": "DIA 28024", "zone": "28024"},
}


def reference_location(store: str) -> dict:
    """Return a fresh configuration so callers cannot modify the references."""
    return deepcopy(REFERENCE_LOCATIONS[store])
