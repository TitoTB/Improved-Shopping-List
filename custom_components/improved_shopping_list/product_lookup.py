"""Optional product hints from Open Food Facts; never associate a scan automatically."""

from asyncio import Lock, sleep
from copy import deepcopy
import json
import logging
import math
import time

from aiohttp import ClientError, ClientTimeout
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN, VERSION
from .product_references import brand_name
from .ean_common import NUTRITION_TTL, nutrition_from_hint

_LOGGER = logging.getLogger(__name__)
BASE_URL = "https://world.openfoodfacts.org"
FIELDS = "code,generic_name_es,generic_name,product_name_es,product_name,brands,quantity,nutriscore_grade,nutriscore_score,nutriscore_version,nutriments,nova_group,ingredients_analysis_tags,categories_tags"
TTLS = {"found": 30 * 86400, "not_found": 86400, "error": 300}


def is_product_barcode(code):
    """Only send GTIN-shaped identifiers with a valid check digit, never QR/NFC data."""
    if not isinstance(code, str) or len(code) not in (8, 12, 13, 14) or not code.isascii() or not code.isdigit():
        return False
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(code[:-1])))
    return (10 - total % 10) % 10 == int(code[-1])


def nutrition_facts(product):
    """Keep normalized facts for the exact barcode, never inferred nutritional scores."""
    facts = {}
    nutrients = product.get("nutriments")
    if isinstance(nutrients, dict):
        values = {}
        for field in ("energy-kcal", "fat", "saturated-fat", "sugars", "salt", "fiber", "proteins"):
            value = nutrients.get(field + "_100g")
            if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= (10000 if field == "energy-kcal" else 100):
                values[field] = value
        if values:
            facts["nutrients"] = values
    nova = product.get("nova_group")
    if type(nova) is int and 1 <= nova <= 4:
        facts["nova"] = nova
    tags = product.get("ingredients_analysis_tags", [])
    if isinstance(tags, list):
        for field in ("vegan", "vegetarian"):
            if "en:non-" + field in tags:
                facts[field] = False
            elif "en:" + field in tags:
                facts[field] = True
    categories = product.get("categories_tags", [])
    if isinstance(categories, list) and categories:
        facts["categories"] = [value[:120] for value in categories[:80] if isinstance(value, str)]
    return facts


def product_hint(data, code):
    if not isinstance(data, dict) or not isinstance(data.get("product"), dict):
        raise ValueError("Invalid product response")
    product = data["product"]
    if str(product.get("code", "")).zfill(14) != code.zfill(14):
        raise ValueError("Product barcode mismatch")

    def field(key, limit):
        value = product.get(key)
        return " ".join(value.split())[:limit] if isinstance(value, str) else ""

    name = next((value for key in ("generic_name_es", "generic_name", "product_name_es", "product_name") if (value := field(key, 160))), "")
    result = ({"status": "found", "name": name, "product_name": field("product_name_es", 160) or field("product_name", 160),
               "source": "Open Food Facts", "url": f"{BASE_URL}/product/{code}", "license": "ODbL"}
              if name else {"status": "not_found"})
    if brand := field("brands", 160):
        result["brand"] = brand_name(brand)
    if quantity := field("quantity", 160):
        from .product_references import content, inferred_content
        amount, unit = inferred_content({"description": quantity})
        if amount is not None:
            try:
                result["content_quantity"], result["content_unit"] = content(amount, unit)
            except ValueError:
                pass
    grade = field("nutriscore_grade", 20).lower()
    if grade in ("a", "b", "c", "d", "e"):
        result["nutriscore"] = {"grade": grade}
        score = product.get("nutriscore_score")
        if type(score) is int and -100 <= score <= 100:
            result["nutriscore"]["score"] = score
        version = product.get("nutriscore_version")
        if str(version) in ("2021", "2023"):
            result["nutriscore"]["version"] = str(version)
    if facts := nutrition_facts(product):
        result["nutrition"] = facts
        unit = result.get("content_unit")
        if unit in ("g", "kg", "ml", "cl", "l"):
            result["basis"] = "g" if unit in ("g", "kg") else "ml"
    return result


class ProductLookup:
    def __init__(self, hass):
        self.hass = hass
        self._store = Store(hass, 1, f"{DOMAIN}.product_lookup")
        self._cache = {}
        self._nutrition_store = Store(hass, 1, f"{DOMAIN}.nutrition")
        self._nutrition_cache = {}
        self._lock = Lock()
        self._next_request = 0.0

    async def async_load(self):
        await self.async_load_nutrition()
        try:
            data = await self._store.async_load()
            if isinstance(data, dict):
                self._cache = {key: item for key, item in data.items() if isinstance(item, dict)
                               and isinstance(item.get("expires"), (int, float)) and isinstance(item.get("result"), dict)
                               and item["result"].get("status") in TTLS and item["result"].get("source")!="community"}
        except (OSError, ValueError, HomeAssistantError):
            _LOGGER.warning("Could not load the optional product lookup cache")

    async def async_load_nutrition(self):
        try:
            data = await self._nutrition_store.async_load()
            if isinstance(data, dict):
                self._nutrition_cache = {key: value for key, value in data.items() if is_product_barcode(key)
                    and isinstance(value, dict) and type(value.get("expires")) in (int, float)
                    and isinstance(value.get("result"), dict)}
        except (OSError, ValueError, HomeAssistantError):
            _LOGGER.warning("Could not load optional nutrition cache")

    def _community_nutrition(self,code):
        index=getattr(self,"common_index",None)
        return index.nutrition_cached(code) if index and hasattr(index,"nutrition_cached") else {}

    @staticmethod
    def _nutrition_hint(entry):
        result={"status":"found","source":"Open Food Facts","license":"ODbL-1.0","checked_at":entry["checked_at"]}
        if entry.get("nutriscore"):result["nutriscore"]=deepcopy(entry["nutriscore"])
        if entry.get("nova"):result["nutrition"]={"nova":entry["nova"]}
        return result

    def _nutrition_entry(self,code):
        local=self._nutrition_cache.get(code,{})
        shared=self._community_nutrition(code)
        if not shared:return local
        if local.get("result",{}).get("status")=="error" and local.get("expires",0)>time.time() and shared["checked_at"]+NUTRITION_TTL<=time.time():return local
        if shared.get("checked_at",0)>local.get("checked_at",0) or (local.get("result",{}).get("status")=="error" and shared["checked_at"]+NUTRITION_TTL>time.time()):
            hint=self._nutrition_hint(shared)
            # Keep existing local nutrients; the public dictionary contains classifications only.
            old=local.get("result",{})
            old_facts=deepcopy(old.get("nutrition",{}));old_facts.pop("nova",None)
            hint["nutrition"]={**old_facts,**hint.get("nutrition",{})}
            return {"result":hint,"checked_at":shared["checked_at"],"expires":shared["checked_at"]+NUTRITION_TTL}
        return local

    def nutrition_export(self,products):
        records={}
        for row in self.nutrition_records(products)["records"]:
            if not row["code"]:continue
            entry=self._nutrition_entry(row["code"])
            if entry.get("checked_at") and (hint:=nutrition_from_hint(entry.get("result",{}),entry["checked_at"])):
                records[row["code"]]=hint
        return records

    def nutrition_records(self, products):
        records = []
        for product in products:
            seen = set()
            refs = [ref for ref in product.get("commercial_references", []) if ref.get("active") is not False]
            for code in dict.fromkeys([product.get("barcode", ""), *product.get("barcodes", []), *[ref.get("ean", "") for ref in refs]]):
                if not is_product_barcode(code) or code.zfill(14) in seen:
                    continue
                code = code.zfill(14)
                seen.add(code)
                ref = next((ref for ref in refs if str(ref.get("ean", "")).zfill(14) == code), {})
                cached = self._nutrition_entry(code)
                hint = cached.get("result") or self._cache.get(code, {}).get("result", {})
                grade = (hint.get("nutriscore") or ref.get("nutriscore") or {}).get("grade", "")
                records.append({"product_id":product["id"], "code":code, "name":ref.get("name") or product["name"],
                    "grade":grade if grade in ("a","b","c","d","e") else "", "nutrition":deepcopy(hint.get("nutrition", {})),
                    "basis":hint.get("basis") or ("g" if ref.get("content_unit") in ("g", "kg") else "ml" if ref.get("content_unit") in ("ml", "cl", "l") else ""),
                    "checked_at":cached.get("checked_at"), "fresh":cached.get("expires", 0) > time.time()})
            if not seen:
                grade = next(((ref.get("nutriscore") or {}).get("grade") for ref in refs if (ref.get("nutriscore") or {}).get("grade") in ("a","b","c","d","e")), "")
                if grade:
                    records.append({"product_id":product["id"], "code":"", "name":product["name"], "grade":grade, "nutrition":{}, "fresh":True})
        return {"records":records}

    async def async_nutrition(self, code):
        if not is_product_barcode(code):
            return {"status":"unsupported"}
        code = code.zfill(14)
        async with self._lock:
            cached = self._nutrition_entry(code)
            if cached.get("expires", 0) > time.time():
                return deepcopy(cached["result"])
            index=getattr(self,"common_index",None)
            if index and hasattr(index,"async_nutrition_hint"):
                await index.async_nutrition_hint(code)
                cached=self._nutrition_entry(code)
                if cached.get("expires",0)>time.time():return deepcopy(cached["result"])
            delay = self._next_request - time.monotonic()
            if delay > 0:
                await sleep(delay)
            self._next_request = time.monotonic() + 4.1
            try:
                raw = await self._fetch(code[1:] if len(code)==14 and code.startswith("0") else code)
                result = {key:deepcopy(raw[key]) for key in ("nutrition", "nutriscore", "url", "basis") if key in raw}
                result["status"] = "found" if result.get("nutrition") or result.get("nutriscore") else "not_found"
            except (ClientError, TimeoutError, ValueError, TypeError):
                result = {"status":"error", **{key:deepcopy(cached.get("result", {}).get(key)) for key in ("nutrition", "nutriscore", "basis") if cached.get("result", {}).get(key)}}
            self._nutrition_cache[code] = {"expires":time.time()+TTLS[result["status"]], "checked_at":cached.get("checked_at",0) if result["status"]=="error" else int(time.time()), "result":result}
            self._nutrition_cache = dict(sorted(self._nutrition_cache.items(), key=lambda item:item[1].get("checked_at", 0))[-3000:])
            try:
                await self._nutrition_store.async_save(self._nutrition_cache)
            except (OSError, HomeAssistantError):
                _LOGGER.warning("Could not persist optional nutrition cache")
            return deepcopy(result)

    def cached(self, code):
        community = getattr(self, "community", None)
        if community and (hint := community.product_hint(code)):
            return hint
        entry = self._cache.get(code.zfill(14))
        return deepcopy(entry["result"]) if entry else None

    def is_fresh(self, code):
        discovery=getattr(self,"catalog_discovery",None)
        signature=getattr(discovery,"fingerprint",lambda:"")()
        if self._cache.get(code.zfill(14),{}).get("discovery_signature","")!=signature:return False
        community = getattr(self, "community", None)
        if community and community.product_hint(code):
            return True
        entry = self._cache.get(code.zfill(14))
        return bool(entry and entry.get("fields") == FIELDS and entry["expires"] > time.time())

    def nutrition_distribution(self, products):
        """Count catalog products once using stored hints, without network requests."""
        counts = dict.fromkeys("abcde", 0)
        product_ids = {grade: [] for grade in counts}
        for product in products:
            found = False
            for code in dict.fromkeys([product.get("barcode", ""), *product.get("barcodes", []),
                                       *[ref.get("ean", "") for ref in product.get("commercial_references", []) if ref.get("active") is not False]]):
                if not is_product_barcode(code):
                    continue
                hint = self._nutrition_entry(code.zfill(14)).get("result") or self.cached(code) or {}
                grade = (hint.get("nutriscore") or {}).get("grade")
                if grade in counts:
                    counts[grade] += 1
                    product_ids[grade].append(product["id"])
                    found = True
                    break
            if not found:
                for reference in product.get("commercial_references", []):
                    grade = (reference.get("nutriscore") or {}).get("grade")
                    if reference.get("active") is not False and grade in counts:
                        counts[grade] += 1
                        product_ids[grade].append(product["id"])
                        break
        return {"counts": counts, "total": sum(counts.values()), "product_ids": product_ids}

    async def async_lookup(self, code):
        if not is_product_barcode(code):
            return {"status": "unsupported"}
        common_index=getattr(self,'common_index',None)
        common=await common_index.async_hint(code) if common_index else {}
        fields={key:common[key] for key in ('brand','content_quantity','content_unit','pack_count') if key in common}
        def enrich(result):
            result={**result,**fields}
            shared=self._community_nutrition(code)
            if shared and shared["checked_at"]+NUTRITION_TTL>time.time():
                if shared.get("nutriscore") and not result.get("nutriscore"):result["nutriscore"]={**shared["nutriscore"],"checked_at":shared["checked_at"]}
                if shared.get("nova"):result["nutrition"]={"nova":shared["nova"],**result.get("nutrition",{})}
            if fields and result.get('status') in ('not_found','error'):result['status']='found'
            return result
        community = getattr(self, "community", None)
        if community and (hint := community.product_hint(code)):
            return enrich(hint)
        # Serialise requests, deduplicate UPC/EAN aliases and stay below 15 reads/minute.
        async with self._lock:
            discovery=getattr(self,"catalog_discovery",None)
            # Reopening a receipt must not repeat discovery before checking the
            # persistent cache. Its fingerprint already invalidates shop changes.
            if self.is_fresh(code):
                return enrich(self.cached(code))
            complete=bool(fields.get('brand') and fields.get('content_quantity') and fields.get('content_unit'))
            async def complete_name(result):
                if complete and discovery and not result.get('product_name'):
                    try:
                        if hint:=await discovery.async_hint(code):result={**result,**hint}
                    except (ClientError,TimeoutError,ValueError,OSError):pass
                return enrich(result)
            if discovery and not complete and (hint:=await discovery.async_hint(code)):
                hint=enrich(hint)
                previous=self.cached(code) or {}
                if previous.get("nutriscore") and not hint.get("nutriscore"):hint["nutriscore"]=previous["nutriscore"]
                self._cache[code.zfill(14)]={"expires":time.time()+TTLS["found"],"fields":FIELDS,"result":hint,"discovery_signature":getattr(discovery,"fingerprint",lambda:"")()}
                try:await self._store.async_save(self._cache)
                except (OSError,HomeAssistantError):_LOGGER.warning("Could not persist the optional product lookup cache")
                return deepcopy(hint)
            delay = self._next_request - time.monotonic()
            if delay > 0:
                await sleep(delay)
            self._next_request = time.monotonic() + 4.1
            try:
                result = await self._fetch(code)
            except (ClientError, TimeoutError, ValueError, TypeError):
                result = {"status": "error"}
            if result.get("nutriscore"):
                result["nutriscore"]["checked_at"] = int(time.time())
            result=await complete_name(result)
            self._cache[code.zfill(14)] = {"expires": time.time() + TTLS[result["status"]], "fields": FIELDS, "result": result,
                "discovery_signature":getattr(discovery,"fingerprint",lambda:"")()}
            self._cache = dict(sorted(self._cache.items(), key=lambda item: item[1]["expires"])[-500:])
            try:
                await self._store.async_save(self._cache)
            except (OSError, HomeAssistantError):
                _LOGGER.warning("Could not persist the optional product lookup cache")
            return deepcopy(result)

    async def _fetch(self, code):
        session = async_get_clientsession(self.hass)
        async with session.get(f"{BASE_URL}/api/v3/product/{code}", params={"fields": FIELDS, "lc": "es"},
                               headers={"User-Agent": f"ImprovedShoppingList/{VERSION} (https://github.com/TitoTB/Improved-Shopping-List)"},
                               timeout=ClientTimeout(total=10), allow_redirects=False) as response:
            if response.status == 404:
                return {"status": "not_found"}
            if response.status == 429:
                self._next_request = time.monotonic() + 60
            response.raise_for_status()
            if response.status != 200:
                raise ValueError("Unexpected response")
            body = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                body.extend(chunk)
                if len(body) > 65536:
                    raise ValueError("Product response too large")
            return product_hint(json.loads(body), code)
