"""Product identity without modifying the native todo item or its UID."""
from unicodedata import category, normalize


def _text(value):
    return " ".join(str(value or "").split())


def _key(value):
    return "".join(char for char in normalize("NFKD", value) if not category(char).startswith("M")).lower()


def combined_name(summary, description):
    summary, description = _text(summary), _text(description)
    if not description:
        return summary
    if not summary:
        return description
    name_key, detail_key = _key(summary), _key(description)
    if name_key == detail_key or name_key.endswith(" " + detail_key):
        return summary
    if detail_key.startswith(name_key + " "):
        return description
    return summary + " " + description


def item_name(settings, entity_id, item):
    snapshot = settings if isinstance(settings, dict) else settings.snapshot
    get = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
    summary = get("source_summary", get("summary", ""))
    if snapshot.get("description_as_name", {}).get(entity_id, False):
        return combined_name(summary, get("source_description", get("description", "")))
    return str(summary or "")


def named_item(settings, entity_id, item):
    if not (settings if isinstance(settings, dict) else settings.snapshot).get("description_as_name", {}).get(entity_id, False):
        return item
    return {**item, "source_summary": item.get("source_summary", item.get("summary", "")),
            "source_description": item.get("source_description", item.get("description", "")),
            "summary": item_name(settings, entity_id, item), "description": ""}
