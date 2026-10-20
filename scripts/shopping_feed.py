"""Build a five-field Carrefour snapshot and delta; never downloads or exposes Awin keys."""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import importlib.util
import json
from pathlib import Path

PROTOCOL = Path(__file__).resolve().parents[1] / "custom_components/improved_shopping_list/feed_protocol.py"
spec = importlib.util.spec_from_file_location("shopping_feed_protocol", PROTOCOL)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


def build(source, output, source_updated_at=None):
    output = Path(output)
    products = []
    with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"merchant_id", "merchant_product_id", "product_name", "search_price", "currency", "aw_deep_link"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("El feed no contiene las columnas necesarias.")
        for number, row in enumerate(reader, 2):
            if number > protocol.MAX_PRODUCTS + 1 or None in row or any(value is None for value in row.values()):
                raise ValueError("El feed está incompleto o supera el tamaño permitido.")
            if row["merchant_id"] != "25399":
                raise ValueError("El feed contiene productos de otro anunciante.")
            try:
                products.append(protocol.record({"ean": row["merchant_product_id"].strip(), "name": row["product_name"],
                    "price": row["search_price"], "currency": row["currency"], "affiliate_url": row["aw_deep_link"]}))
            except ValueError:
                raise ValueError(f"Producto no válido en la fila {number}; no se publica un catálogo parcial.") from None
    raw = protocol.snapshot(products)
    version = protocol.digest(raw)
    files = {f"snapshots/{version}.json": raw}
    old = None
    previous = output / "manifest.json"
    if previous.exists():
        old = json.loads(previous.read_bytes())
        reference = protocol.check_descriptor(old["snapshot"])
        old_raw = (output / reference["path"]).read_bytes()
        if protocol.digest(old_raw) != old["version"]:
            raise ValueError("La copia anterior del catálogo no es válida.")
        old_products = protocol.read_snapshot(old_raw)
    manifest = {"schema": 1, "store": "carrefour", "version": version, "products_count": len(products),
        "generated_at": datetime.now(timezone.utc).isoformat(), "source_updated_at": source_updated_at,
        "snapshot": protocol.descriptor(f"snapshots/{version}.json", raw), "delta": None}
    if old and old["version"] != version:
        current = protocol.index(products)
        delta = protocol.encode({"schema": 1, "base_version": old["version"], "version": version,
            "upsert": [current[key] for key in sorted(current) if current[key] != old_products.get(key)],
            "deleted": sorted(set(old_products) - set(current))})
        delta_path = f"deltas/{protocol.digest(delta)}.json"
        files[delta_path] = delta
        manifest["delta"] = {**protocol.descriptor(delta_path, delta), "base_version": old["version"]}
    elif old:
        manifest["delta"] = old.get("delta")
    # Write immutable content first, and the manifest last. A failed parse never touches output.
    output.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(body)
        temporary.replace(path)
    temporary = output / "manifest.tmp"
    temporary.write_bytes(protocol.encode(manifest))
    temporary.replace(previous)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-updated-at")
    args = parser.parse_args()
    try:
        result = build(args.input, args.output, args.source_updated_at)
    except (ValueError, OSError, EOFError, csv.Error):
        parser.exit(1, "No se pudo validar el feed. Se conserva la publicación anterior.\n")
    print(json.dumps({"products": result["products_count"], "version": result["version"]}))
