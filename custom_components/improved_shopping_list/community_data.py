"""Bounded community protocol and consensus rules shared with GitHub Actions.

No Home Assistant imports: the repository validates untrusted submissions using
the same reference and URL rules, without executing contributor-supplied code.
"""

import base64
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata
import zlib

from .store_links import normalize_links, STORES
from .store_location import REFERENCE_LOCATIONS

CLIENT_ID = "Iv23livqjR0U5qqayu6f"
APP_ID = 5414585
APP_URL = "https://github.com/apps/improved-shopping-list-community"
REPO = "TitoTB/Improved-Shopping-List"
SCHEMA = 2
REFERENCE_VERSION = 1
DAY = 86400
MAX_BYTES = 2 * 1024 * 1024
MAX_PRODUCTS = 2000
CHUNK_SIZE = 48000
MARKER = "ISL-COMMUNITY-2\n"
ICON_ID = re.compile(r"[a-z0-9-]{1,40}:[a-z0-9-]{1,100}")


def normalized(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(c)).casefold().split())


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def ean(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value):
        return ""
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(value[:-1])))
    return value.zfill(14) if (10-total % 10) % 10 == int(value[-1]) else ""


def text(value, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError("Texto comunitario no válido.")
    return value.strip()


def scope(store):
    config = REFERENCE_LOCATIONS[store]
    if store in ("consum", "lasirena", "eroski", "dia"):
        return config["postal_code"] + ":" + config["area_id"]
    return config.get("warehouse", config.get("region_id", config.get("sale_point", "")))


def validate_product(raw, now):
    if not isinstance(raw, dict) or set(raw)-{"name", "name_en", "eans", "store_links", "nutriscore", "icons", "prices", "borrowed_fields"}:
        raise ValueError("Campos comunitarios no admitidos.")
    item = {"name": text(raw.get("name")), "name_en": text(raw["name_en"]) if raw.get("name_en") else ""}
    codes = raw.get("eans", [])
    if not isinstance(codes, list) or len(codes) > 50 or any(not ean(code) for code in codes):
        raise ValueError("EAN comunitario no válido.")
    item["eans"] = sorted({ean(code) for code in codes})
    item["store_links"] = normalize_links(raw.get("store_links", {}))
    grade = raw.get("nutriscore", "")
    if grade not in ("", "a", "b", "c", "d", "e"):
        raise ValueError("Nutri-Score no válido.")
    item["nutriscore"] = grade
    borrowed = raw.get("borrowed_fields", [])
    allowed = {"name", "name_en", "eans", "nutriscore", "icons", *("store_links."+store for store in STORES)}
    if not isinstance(borrowed, list) or any(not isinstance(field, str) or field not in allowed for field in borrowed):
        raise ValueError("Procedencia comunitaria no válida.")
    item["borrowed_fields"] = sorted(set(borrowed))
    icons = raw.get("icons", [])
    if not isinstance(icons, list) or len(icons) > 5 or any(not isinstance(icon, str) or not ICON_ID.fullmatch(icon) for icon in icons):
        raise ValueError("Icono comunitario no válido.")
    item["icons"] = sorted(set(icons))
    prices = raw.get("prices", [])
    if not isinstance(prices, list) or len(prices) > len(STORES):
        raise ValueError("Precios comunitarios no válidos.")
    item["prices"] = []
    for price in prices:
        if not isinstance(price, dict) or set(price) != {"store", "reference_id", "price", "currency", "checked_at"}:
            raise ValueError("Campos de precio no admitidos.")
        store = price["store"]
        if store not in item["store_links"] or price["reference_id"] != item["store_links"][store]["id"] or price["currency"] != "EUR":
            raise ValueError("El precio no corresponde a su referencia.")
        try:
            amount = Decimal(price["price"])
            valid = amount.is_finite() and 0 < amount <= 10000 and amount.as_tuple().exponent >= -2
        except (InvalidOperation, ValueError, TypeError):
            valid = False
        checked = price["checked_at"]
        if not valid or type(checked) not in (int, float) or not now-DAY <= checked <= now+300:
            raise ValueError("Importe o fecha de precio no válido.")
        item["prices"].append({**price, "price": format(amount, ".2f"), "checked_at": min(checked, now)})
    return item


def validate_payload(raw, now):
    if (not isinstance(raw, dict) or set(raw) != {"schema", "reference_version", "products"}
        or raw.get("schema") != SCHEMA or raw.get("reference_version") != REFERENCE_VERSION
        or not isinstance(raw.get("products"), list) or len(raw["products"]) > MAX_PRODUCTS):
        raise ValueError("Lote comunitario no válido.")
    return {**raw, "products": [validate_product(item, now) for item in raw["products"]]}


def pack(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("El catálogo supera el tamaño de sincronización permitido.")
    data = base64.b64encode(zlib.compress(raw)).decode()
    parts = [data[i:i+CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]
    if len(parts) > 60:
        raise ValueError("El catálogo supera el tamaño de sincronización permitido.")
    return {"schema": SCHEMA, "digest": hashlib.sha256(raw).hexdigest(), "parts": len(parts)}, parts


def unpack(manifest, parts):
    if (not isinstance(manifest, dict) or set(manifest) != {"schema", "digest", "parts"}
        or manifest.get("schema") != SCHEMA or type(manifest.get("parts")) is not int
        or not 1 <= manifest["parts"] <= 60 or len(parts) != manifest["parts"]
        or not isinstance(manifest.get("digest"), str) or not re.fullmatch(r"[a-f0-9]{64}", manifest["digest"])
        or any(not isinstance(p, str) or len(p) > CHUNK_SIZE for p in parts)):
        raise ValueError("Fragmentos comunitarios no válidos.")
    compressed = base64.b64decode("".join(parts), validate=True)
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(compressed, MAX_BYTES+1)
    except zlib.error as err:
        raise ValueError("Compresión comunitaria no válida.") from err
    if len(raw) > MAX_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Lote comunitario demasiado grande o incompleto.")
    if hashlib.sha256(raw).hexdigest() != manifest["digest"]:
        raise ValueError("El lote comunitario no coincide con su huella.")
    try:
        return json.loads(raw)
    except RecursionError as err:
        raise ValueError("Estructura comunitaria demasiado profunda.") from err


def identities(item):
    if item["eans"]:
        return {"ean:"+code for code in item["eans"]}
    return {"store:"+store+":"+link["id"] for store,link in item["store_links"].items()}


def new_registry():
    return {"schema": SCHEMA, "records": {}, "last_submission": {}, "processed": [], "revoked_prices": []}


def price_fingerprint(price):
    return fingerprint({key:price.get(key) for key in ("store", "reference_id", "price", "currency", "checked_at")})


def record_votes(record):
    """Read old snapshots as well as compact, deduplicated choices."""
    return {user: {"item": vote.get("item", record.get("choices", {}).get(vote.get("choice"))),
                   "eligible": vote["eligible"]} for user, vote in record["votes"].items()}


def compact_registry(registry):
    """Store each distinct selection once; one lightweight vote per account."""
    for record in registry["records"].values():
        choices, votes = {}, {}
        for user, vote in record_votes(record).items():
            key = fingerprint(vote["item"])
            choices[key] = vote["item"]
            votes[user] = {"choice": key, "eligible": vote["eligible"]}
        record["choices"], record["votes"] = choices, votes
    registry["processed"] = registry["processed"][-10000:]
    return registry


def _accept_price(record, price, user, created, eligible, blocked, max_variation, confirmations):
    store = price["store"]
    previous = record["prices"].get(store)
    if previous and previous["contributor"] in blocked:
        previous = next((old for old in reversed(record.get("price_history", {}).get(store, []))
                         if old["contributor"] not in blocked), None)
    if previous and previous["checked_at"] > created-DAY:
        return  # The first fresh accepted observation remains authoritative for this day.
    suspicious = previous and abs(Decimal(price["price"])-Decimal(previous["price"]))/Decimal(previous["price"])*100 > Decimal(str(max_variation))
    candidate = {**price, "contributor":user, "received_at":created}
    if suspicious:
        pending = record.setdefault("price_candidates", {}).setdefault(store, {})
        pending = {key:value for key,value in pending.items() if value["price"]["checked_at"] >= created-DAY}
        # Bounded alternatives prevent a contributor from growing the registry indefinitely.
        record["price_candidates"][store] = pending
        group = pending.setdefault(price["price"], {"price":candidate, "reporters":{}})
        if eligible:
            group["reporters"][user] = created
        voters = {who for who, when in group["reporters"].items() if who not in blocked and when >= created-DAY}
        if len(voters) < confirmations:
            if len(pending) > 10:
                del pending[next(iter(pending))]
            return
        candidate = group["price"]  # Confirmation never renews the observation timestamp.
    if previous:
        history = record.setdefault("price_history", {}).setdefault(store, [])
        history.append(previous)
        record["price_history"][store] = history[-20:]
    record["prices"][store] = candidate
    record.get("price_candidates", {}).pop(store, None)


def restore_registry(previous, current):
    """Recover trusted observations and publish withdrawals for overwritten prices."""
    restored = deepcopy(previous)
    restored["last_submission"] = {user:max(previous["last_submission"].get(user, 0), current["last_submission"].get(user, 0))
        for user in set(previous["last_submission"]) | set(current["last_submission"])}
    restored["processed"] = sorted(set(restored["processed"]) | set(current["processed"]))[-10000:]
    revoked = set(restored.get("revoked_prices", [])) | set(current.get("revoked_prices", []))
    for key, record in current["records"].items():
        trusted = restored["records"].get(key, {}).get("prices", {})
        for store, price in record["prices"].items():
            if price_fingerprint(price) != price_fingerprint(trusted.get(store, {})):
                revoked.add(price_fingerprint(price))
    restored["revoked_prices"] = sorted(revoked)
    return restored


def contribute(registry, payload, user_id, created, issue_id, *, banned=(), eligible=True, max_price_variation=50, outlier_confirmations=3):
    """Use the GitHub-authenticated author and server timestamp, never payload identity."""
    user = str(user_id)
    blocked = set(map(str, banned))
    if user in blocked or issue_id in registry["processed"]:
        return False
    if created < registry["last_submission"].get(user, -DAY)+DAY:
        return False
    payload = validate_payload(payload, created)
    records = registry["records"]
    for item in payload["products"]:
        keys = identities(item)
        matches = [key for key, record in records.items() if keys.intersection(record["identities"])] if keys else []
        term = normalized(item["name_en"] or item["name"])
        if not matches and not keys:
            matches = [key for key, record in records.items() if not record["identities"] and record["term"] == term]
        if len(matches) > 1:
            continue  # Ambiguous identities never merge unrelated records.
        key = matches[0] if matches else fingerprint(sorted(keys) if keys else ["term", term])[:32]
        record = records.setdefault(key, {"identities": [], "term": term, "votes": {}, "prices": {}})
        # Only established accounts contribute votes; young accounts can still submit candidates/prices.
        choice = {k:v for k,v in item.items() if k != "prices"}
        choice_id = fingerprint(choice)
        record.setdefault("choices", {})[choice_id] = choice
        record["votes"][user] = {"choice":choice_id, "eligible":eligible}
        record["identities"] = sorted(set(record["identities"]) | keys)
        for price in item["prices"] if len(item["eans"])==1 else []:
            _accept_price(record, price, user, created, eligible, blocked, max_price_variation, outlier_confirmations)
    registry["last_submission"][user] = created
    registry["processed"].append(issue_id)
    return True


def compile_dictionary(registry, now, *, banned=(), icon_metadata=None):
    blocked = set(map(str, banned))
    result = []
    revoked = set(registry.get("revoked_prices", []))
    for identifier, record in registry["records"].items():
        for price in [*record["prices"].values(), *(old for history in record.get("price_history", {}).values() for old in history)]:
            if price["contributor"] in blocked:
                revoked.add(price_fingerprint(price))
        votes = [vote for user, vote in record_votes(record).items() if user not in blocked]
        if not votes:
            continue
        item = {"id": identifier, "confirmed_fields": [], "confirmations": {}, "icons": [], "prices": []}
        item["terms"] = sorted({vote["item"].get(field,"") for vote in votes if vote["eligible"] for field in ("name","name_en")}-{""})[:100]
        for field in ("name", "name_en", "eans", "nutriscore"):
            candidates = {}
            for vote in votes:
                value = vote["item"][field]
                if not value:
                    continue
                key = fingerprint(normalized(value) if field in ("name", "name_en") else value)
                group = candidates.setdefault(key, {"value": value, "count": 0})
                group["count"] += int(vote["eligible"] and field not in vote["item"].get("borrowed_fields", []))
            ranked = sorted(candidates.values(), key=lambda c:(-c["count"], fingerprint(c["value"])))
            item[field] = deepcopy(ranked[0]["value"]) if ranked else [] if field == "eans" else ""
            count = ranked[0]["count"] if ranked else 0
            item["confirmations"][field] = count
            if count >= 3 and (len(ranked) == 1 or count > ranked[1]["count"]):
                item["confirmed_fields"].append(field)
        item["store_links"] = {}
        for store in STORES:
            candidates = {}
            for vote in votes:
                if len(item["eans"])!=1 or vote["item"]["eans"]!=item["eans"]:
                    continue
                link = vote["item"]["store_links"].get(store)
                if link:
                    group = candidates.setdefault(link["id"], {"value": link, "count": 0})
                    group["count"] += int(vote["eligible"] and "store_links."+store not in vote["item"].get("borrowed_fields", []))
            ranked = sorted(candidates.values(), key=lambda c:(-c["count"], c["value"]["id"]))
            if ranked:
                item["store_links"][store] = deepcopy(ranked[0]["value"])
                if ranked[0]["count"] >= 3 and (len(ranked) == 1 or ranked[0]["count"] > ranked[1]["count"]):
                    item["confirmed_fields"].append("store_links."+store)
        counts, selections = {}, {}
        for vote in votes:
            for icon in vote["item"]["icons"]:
                counts[icon] = counts.get(icon, 0)+int(vote["eligible"] and "icons" not in vote["item"].get("borrowed_fields", []))
                selections[icon] = selections.get(icon, 0)+int(vote["eligible"])
        for icon, count in sorted(counts.items(), key=lambda pair:(-selections[pair[0]], -pair[1], pair[0])):
            info = (icon_metadata or {}).get(icon)
            if count >= 3 and info:
                item["icons"].append({"id": icon, "confirmations": count, "selections": selections[icon], **info})
                if len(item["icons"]) == 5:
                    break
        for price in record["prices"].values():
            observation=record_votes(record).get(price["contributor"],{}).get("item",{})
            if (len(item["eans"])==1 and observation.get("eans")==item["eans"] and price["contributor"] not in blocked and price["checked_at"] >= now-DAY
                and item["store_links"].get(price["store"], {}).get("id") == price["reference_id"]
                and price_fingerprint(price) not in revoked):
                item["prices"].append({key:value for key,value in price.items() if key not in ("contributor", "received_at")})
        result.append(item)
    return {"schema": SCHEMA, "reference_version": REFERENCE_VERSION, "generated_at": now, "products": result, "revoked_prices": sorted(revoked)}


def validate_dictionary(data, now):
    if (not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("reference_version") != REFERENCE_VERSION
        or type(data.get("generated_at")) not in (int, float) or not 0 <= data["generated_at"] <= now+300
        or not isinstance(data.get("products"), list) or len(data["products"]) > 20000):
        raise ValueError("Diccionario comunitario no válido.")
    result = deepcopy(data)
    revoked = result.get("revoked_prices", [])
    if not isinstance(revoked, list) or len(revoked) > 50000 or any(not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) for key in revoked):
        raise ValueError("Revocaciones comunitarias no válidas.")
    seen = set()
    for item in result["products"]:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier) or identifier in seen:
            raise ValueError("Identidad comunitaria no válida.")
        seen.add(identifier)
        terms=item.get("terms",[])
        if not isinstance(terms,list) or len(terms)>100 or any(not isinstance(term,str) or not term.strip() or len(term)>160 for term in terms):
            raise ValueError("Términos comunitarios no válidos.")
        # Reuse strict validators; old prices are omitted rather than refreshed by a download.
        item["prices"] = [p for p in item.get("prices", []) if type(p.get("checked_at")) in (int,float) and p["checked_at"] >= now-DAY]
        raw = {key:item.get(key, [] if key in ("eans", "prices") else {} if key == "store_links" else "")
               for key in ("name", "name_en", "eans", "store_links", "nutriscore", "prices")}
        raw["name"] = raw["name"] or raw["name_en"] or "Producto"
        raw["icons"] = [icon["id"] for icon in item.get("icons", [])]
        validate_product(raw, now)
        allowed = {"name", "name_en", "eans", "nutriscore", *("store_links."+s for s in STORES)}
        if not isinstance(item.get("confirmed_fields"), list) or set(item["confirmed_fields"])-allowed:
            raise ValueError("Confirmaciones comunitarias no válidas.")
        for icon in item.get("icons", []):
            if (not isinstance(icon.get("author"), str) or not isinstance(icon.get("license"), str)
                or not isinstance(icon.get("license_url"), str) or not icon["license_url"].startswith("https://")):
                raise ValueError("Licencia comunitaria no válida.")
    return result
