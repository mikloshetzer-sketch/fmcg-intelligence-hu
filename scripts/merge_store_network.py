#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

BASE_FILE = DATA_DIR / "store-network-hu.json"
LIDL_FILE = DATA_DIR / "lidl-stores.json"
OUT_FILE = DATA_DIR / "store-network-hu-final.json"
STATUS_FILE = DATA_DIR / "store-network-hu-final-status.json"


REGION_CITY_MAP = {
    "budapest": "Közép-Magyarország",
    "budaörs": "Közép-Magyarország",
    "szigetszentmiklós": "Közép-Magyarország",
    "dunakeszi": "Közép-Magyarország",
    "érd": "Közép-Magyarország",
    "vecsés": "Közép-Magyarország",
    "gyál": "Közép-Magyarország",
    "maglód": "Közép-Magyarország",
    "monor": "Közép-Magyarország",
    "gödöllő": "Közép-Magyarország",
    "vác": "Közép-Magyarország",
    "cegléd": "Közép-Magyarország",

    "győr": "Nyugat-Dunántúl",
    "sopron": "Nyugat-Dunántúl",
    "szombathely": "Nyugat-Dunántúl",
    "zalaegerszeg": "Nyugat-Dunántúl",
    "nagykanizsa": "Nyugat-Dunántúl",

    "veszprém": "Közép-Dunántúl",
    "székesfehérvár": "Közép-Dunántúl",
    "tatabánya": "Közép-Dunántúl",
    "dunaújváros": "Közép-Dunántúl",
    "esztergom": "Közép-Dunántúl",

    "pécs": "Dél-Dunántúl",
    "kaposvár": "Dél-Dunántúl",
    "szekszárd": "Dél-Dunántúl",
    "siófok": "Dél-Dunántúl",

    "miskolc": "Észak-Magyarország",
    "eger": "Észak-Magyarország",
    "salgótarján": "Észak-Magyarország",

    "debrecen": "Észak-Alföld",
    "nyíregyháza": "Észak-Alföld",
    "szolnok": "Észak-Alföld",
    "karcag": "Észak-Alföld",

    "szeged": "Dél-Alföld",
    "kecskemét": "Dél-Alföld",
    "békéscsaba": "Dél-Alföld",
    "baja": "Dél-Alföld",
    "gyula": "Dél-Alföld"
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def slugify(value):
    value = str(value).lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o", "ő": "o",
        "ú": "u", "ü": "u", "ű": "u",
        " ": "_", "-": "_", ".": "", ",": "", "/": "_", "\\": "_",
        "(": "", ")": "", "[": "", "]": ""
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = "".join(ch for ch in value if ch.isalnum() or ch == "_")

    while "__" in value:
        value = value.replace("__", "_")

    return value.strip("_")


def region_from_city(city):
    return REGION_CITY_MAP.get(str(city or "").lower(), "n.a.")


def make_store_id(company, city, address, idx):
    return slugify(f"{company}_{city}_{address}_{idx}")[:90]


def load_json(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def normalize_store(store, idx=0):
    company = store.get("company") or "Lidl"
    name = store.get("name") or f"{company} {store.get('city', '')}".strip()
    city = store.get("city") or "n.a."
    address = store.get("address") or "n.a."

    if "lat" not in store or "lon" not in store:
        return None

    lat = store.get("lat")
    lon = store.get("lon")

    try:
        lat = round(float(lat), 6)
        lon = round(float(lon), 6)
    except Exception:
        return None

    return {
        "store_id": store.get("store_id") or make_store_id(company, city, address, idx),
        "company": company,
        "name": name,
        "city": city,
        "area": store.get("area") or city,
        "region": store.get("region") or region_from_city(city),
        "address": address,
        "lat": lat,
        "lon": lon,
        "source": store.get("source") or "lidl_static_file",
        "confidence": store.get("confidence") or "medium",
        "keywords": store.get("keywords") or [
            name,
            f"{company} {city}",
            address
        ]
    }


def deduplicate(stores):
    seen = set()
    result = []

    for store in stores:
        key = (
            store.get("company"),
            round(float(store.get("lat", 0)), 5),
            round(float(store.get("lon", 0)), 5)
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(store)

    return result


def company_counts(stores):
    counts = {}

    for store in stores:
        company = store.get("company", "n.a.")
        counts[company] = counts.get(company, 0) + 1

    return dict(sorted(counts.items()))


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()

    base_payload = load_json(BASE_FILE, {"stores": []})
    lidl_payload = load_json(LIDL_FILE, {"stores": []})

    base_stores = base_payload.get("stores", [])
    raw_lidl_stores = lidl_payload.get("stores", [])

    lidl_stores = []

    for idx, store in enumerate(raw_lidl_stores):
        normalized = normalize_store(store, idx)
        if normalized:
            lidl_stores.append(normalized)

    merged = deduplicate(base_stores + lidl_stores)
    merged.sort(key=lambda x: (x.get("company", ""), x.get("city", ""), x.get("address", "")))

    payload = {
        "updated_at": updated_at,
        "version": "store-network-hu-final-v1",
        "scope": "Hungarian FMCG store network final merged model",
        "method_note": (
            "A véglegesített hálózati fájl a store-network-hu.json alapadatbázisból "
            "és a lidl-stores.json statikus Lidl adatbázisból készül. "
            "Nem hív külső API-t, ezért gyors és stabil."
        ),
        "stores": merged
    }

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "store-network-hu-final-v1",
        "base_file": str(BASE_FILE),
        "lidl_file": str(LIDL_FILE),
        "output_file": str(OUT_FILE),
        "base_store_count": len(base_stores),
        "lidl_raw_count": len(raw_lidl_stores),
        "lidl_valid_count": len(lidl_stores),
        "final_store_count": len(merged),
        "company_totals": company_counts(merged)
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Final store network written: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")
    print(f"Final store count: {len(merged)}")
    print(f"Company totals: {company_counts(merged)}")


if __name__ == "__main__":
    main()
