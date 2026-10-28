"""User-facing stores, excluding connectors explicitly archived by the project.

Keep archived connectors and stored references intact. Re-enabling a connector
requires deliberately changing this capability list after validating it.
"""

AVAILABLE_STORES = frozenset({"mercadona", "carrefour", "lidl", "consum", "lasirena", "eroski"})


def apply_availability(snapshot):
    """Mask archived activations at runtime without overwriting saved options."""
    for store, config in snapshot["stores"].items():
        if store not in AVAILABLE_STORES:
            config["enabled"] = False
    active = [store for store, config in snapshot["stores"].items()
              if config.get("enabled") and store in AVAILABLE_STORES]
    if snapshot["favorite_store"] not in active:
        snapshot["favorite_store"] = next(iter(active), "")
    return snapshot
