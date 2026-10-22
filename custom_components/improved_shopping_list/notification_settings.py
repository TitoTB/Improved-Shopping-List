"""Validated notification rules, stored in config-entry options."""
from copy import deepcopy
import re

DEFAULT_NOTIFICATIONS = {
    "shopping_list": {"enabled": False, "threshold": 10, "targets": [], "title": "Lista de la compra",
                      "message": "{lista} tiene {cantidad} productos pendientes."},
    "low_stock": {"enabled": False, "threshold": 3, "targets": [], "title": "Stock bajo",
                  "message": "Hay {cantidad} productos con stock bajo: {productos}."},
}
RESERVED_SERVICES = {"notify", "send_message", "persistent_notification", "reload"}


def notification_options(data=None):
    return {key: {**deepcopy(defaults), **deepcopy((data or {}).get(key, {}))}
            for key, defaults in DEFAULT_NOTIFICATIONS.items()}


def normalize_notifications(data):
    if not isinstance(data, dict) or set(data) != set(DEFAULT_NOTIFICATIONS):
        raise ValueError("La configuración de notificaciones no es válida.")
    result = {}
    for key, defaults in DEFAULT_NOTIFICATIONS.items():
        rule = data[key]
        if not isinstance(rule, dict) or set(rule) != set(defaults):
            raise ValueError("La regla de notificaciones contiene campos no válidos.")
        if type(rule["enabled"]) is not bool or type(rule["threshold"]) is not int or not 0 <= rule["threshold"] <= 100000:
            raise ValueError("Indica un límite de productos entero entre 0 y 100000.")
        targets = rule["targets"]
        if not isinstance(targets, list) or len(targets) > 50 or any(
            not isinstance(target, str) or not re.fullmatch(r"(?:service|entity):notify\.[a-z0-9_]{1,150}", target)
            or target.startswith("service:") and target.split(".", 1)[1] in RESERVED_SERVICES for target in targets):
            raise ValueError("Selecciona dispositivos o destinos de notificación válidos.")
        for field, limit in (("title", 160), ("message", 2000)):
            if not isinstance(rule[field], str) or len(rule[field]) > limit or any(ord(char) < 32 and char not in "\n\t" for char in rule[field]):
                raise ValueError("El título o el mensaje de la notificación no es válido.")
        if rule["enabled"] and (not targets or not rule["message"].strip()):
            raise ValueError("Selecciona al menos un dispositivo y escribe un mensaje para activar el aviso.")
        result[key] = {**rule, "targets": list(dict.fromkeys(targets)), "title": rule["title"].strip(), "message": rule["message"].strip()}
    return result
