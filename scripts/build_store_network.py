#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

OUT_FILE = DATA_DIR / "store-network-hu.json"
STATUS_FILE = DATA_DIR / "store-network-hu-status.json"
OVERRIDE_FILE = DATA_DIR / "store-network-overrides.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FETCH_SLEEP = 2

# Ezeknél az OSM/Overpass lekérdezés eddig stabilan működött.
OSM_BRANDS = {
    "ALDI": ["ALDI", "Aldi"],
    "SPAR": ["SPAR", "Spar", "INTERSPAR", "Interspar"],
    "Tesco": ["Tesco", "TESCO"]
}

# Ezeknél az OSM címkézés hiányos vagy zajos volt, ezért override fájlból jönnek.
OVERRIDE_COMPANIES = ["Lidl", "Auchan", "Penny"]


REGION_CITY_MAP = {
    "budapest": "Közép-Magyarország",
    "budaörs": "Közép-Magyarország",
    "budakeszi": "Közép-Magyarország",
    "budakalász": "Közép-Magyarország",
    "szigetszentmiklós": "Közép-Magyarország",
    "dunakeszi": "Közép-Magyarország",
    "érd": "Közép-Magyarország",
    "vecsés": "Közép-Magyarország",
    "gyál": "Közép-Magyarország",
    "monor": "Közép-Magyarország",
    "maglód": "Közép-Magyarország",
    "gödöllő": "Közép-Magyarország",
    "vác": "Közép-Magyarország",
    "cegléd": "Közép-Magyarország",
    "abony": "Közép-Magyarország",
    "fót": "Közép-Magyarország",
    "dabas": "Közép-Magyarország",
    "dunaharaszti": "Közép-Magyarország",

    "győr": "Nyugat-Dunántúl",
    "sopron": "Nyugat-Dunántúl",
    "szombathely": "Nyugat-Dunántúl",
    "zalaegerszeg": "Nyugat-Dunántúl",
    "nagykanizsa": "Nyugat-Dunántúl",
    "mosonmagyaróvár": "Nyugat-Dunántúl",
    "celldömölk": "Nyugat-Dunántúl",

    "veszprém": "Közép-Dunántúl",
    "székesfehérvár": "Közép-Dunántúl",
    "tatabánya": "Közép-Dunántúl",
    "dunaújváros": "Közép-Dunántúl",
    "esztergom": "Közép-Dunántúl",
    "ajka": "Közép-Dunántúl",
    "balatonalmádi": "Közép-Dunántúl",
    "balatonfüred": "Közép-Dunántúl",
    "enying": "Közép-Dunántúl",

    "pécs": "Dél-Dunántúl",
    "kaposvár": "Dél-Dunántúl",
    "szekszárd": "Dél-Dunántúl",
    "siófok": "Dél-Dunántúl",
    "bonyhád": "Dél-Dunántúl",
    "balatonfenyves": "Dél-Dunántúl",
    "balatonlelle": "Dél-Dunántúl",
    "dunaföldvár": "Dél-Dunántúl",

    "miskolc": "Észak-Magyarország",
    "eger": "Észak-Magyarország",
    "salgótarján": "Észak-Magyarország",
    "kazincbarcika": "Észak-Magyarország",
    "balassagyarmat": "Észak-Magyarország",

    "debrecen": "Észak-Alföld",
    "nyíregyháza": "Észak-Alföld",
    "szolnok": "Észak-Alföld",
    "karcag": "Észak-Alföld",
    "hajdúböszörmény": "Észak-Alföld",
    "berettyóújfalu": "Észak-Alföld",

    "szeged": "Dél-Alföld",
    "kecskemét": "Dél-Alföld",
    "békéscsaba": "Dél-Alföld",
    "hódmezővásárhely": "Dél-Alföld",
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


def make_store_id(company, name, city, source_id):
    return slugify(f"{company}_{city}_{name}_{source_id}")[:90]


def region_from_city(city):
    return REGION_CITY_MAP.get((city or "").lower(), "n.a.")


def build_overpass_query(brand_values):
    filters = []

    for value in brand_values:
        escaped = value.replace('"', '\\"')

        for shop_type in ["supermarket", "convenience"]:
            filters.append(f'node["shop"="{shop_type}"]["brand"="{escaped}"](area.searchArea);')
            filters.append(f'way["shop"="{shop_type}"]["brand"="{escaped}"](area.searchArea);')
            filters.append(f'relation["shop"="{shop_type}"]["brand"="{escaped}"](area.searchArea);')

    block = "\n".join(filters)

    return f"""
[out:json][timeout:180];
area["ISO3166-1"="HU"][admin_level=2]->.searchArea;
(
{block}
);
out center tags;
"""


def fetch_overpass(query):
    headers = {
        "User-Agent": "fmcg-intelligence-hu-store-network-builder/1.3"
    }

    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers=headers,
        timeout=240
    )

    response.raise_for_status()
    return response.json()


def element_coordinates(element):
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]

    center = element.get("center", {})
    if "lat" in center and "lon" in center:
        return center["lat"], center["lon"]

    return None, None


def extract_city(tags):
    return (
        tags.get("addr:city")
        or tags.get("is_in:city")
        or tags.get("addr:town")
        or tags.get("addr:village")
        or tags.get("addr:suburb")
        or "n.a."
    )


def extract_address(tags):
    street = tags.get("addr:street", "")
    house = tags.get("addr:housenumber", "")
    postcode = tags.get("addr:postcode", "")
    city = extract_city(tags)

    parts = []

    if postcode and city != "n.a.":
        parts.append(f"{postcode} {city}")
    elif city != "n.a.":
        parts.append(city)

    street_line = " ".join(x for x in [street, house] if x)
    if street_line:
        parts.append(street_line)

    return ", ".join(parts) if parts else "n.a."


def normalize_company_from_brand(raw_brand, expected_company):
    raw = (raw_brand or "").lower()

    if "aldi" in raw:
        return "ALDI"
    if "spar" in raw:
        return "SPAR"
    if "tesco" in raw:
        return "Tesco"

    return expected_company


def parse_osm_element(element, expected_company):
    tags = element.get("tags", {})
    lat, lon = element_coordinates(element)

    if lat is None or lon is None:
        return None

    raw_brand = tags.get("brand") or expected_company
    company = normalize_company_from_brand(raw_brand, expected_company)

    name = tags.get("name") or f"{company} üzlet"
    city = extract_city(tags)
    address = extract_address(tags)

    osm_type = element.get("type", "n.a.")
    osm_id = element.get("id", "n.a.")

    return {
        "store_id": make_store_id(company, name, city, osm_id),
        "company": company,
        "name": name,
        "city": city,
        "area": city,
        "region": region_from_city(city),
        "address": address,
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "source": "openstreetmap_overpass",
        "osm_type": osm_type,
        "osm_id": osm_id,
        "brand": raw_brand,
        "keywords": [
            name,
            f"{company} {city}",
            address
        ]
    }


def load_overrides():
    if not OVERRIDE_FILE.exists():
        return []

    try:
        payload = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
        stores = payload.get("stores", [])

        normalized = []
        for idx, store in enumerate(stores):
            company = store.get("company", "n.a.")
            name = store.get("name", f"{company} üzlet")
            city = store.get("city", "n.a.")
            address = store.get("address", "n.a.")

            if "lat" not in store or "lon" not in store:
                continue

            normalized.append({
                "store_id": store.get("store_id") or make_store_id(company, name, city, f"override_{idx}"),
                "company": company,
                "name": name,
                "city": city,
                "area": store.get("area", city),
                "region": store.get("region") or region_from_city(city),
                "address": address,
                "lat": round(float(store.get("lat")), 6),
                "lon": round(float(store.get("lon")), 6),
                "source": store.get("source", "manual_override"),
                "confidence": store.get("confidence", "medium"),
                "keywords": store.get("keywords", [name, f"{company} {city}", address])
            })

        return normalized

    except Exception:
        return []


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


def collect_osm_stores():
    stores = []
    status_companies = []

    for company, brand_values in OSM_BRANDS.items():
        print(f"Fetching {company} from OSM...")

        try:
            query = build_overpass_query(brand_values)
            data = fetch_overpass(query)

            company_stores = []

            for element in data.get("elements", []):
                store = parse_osm_element(element, company)
                if store:
                    company_stores.append(store)

            company_stores = deduplicate(company_stores)
            stores.extend(company_stores)

            status_companies.append({
                "company": company,
                "source": "openstreetmap_overpass",
                "status": "ok",
                "stores": len(company_stores),
                "brand_values": brand_values
            })

            print(f"{company}: {len(company_stores)} stores")

        except Exception as exc:
            status_companies.append({
                "company": company,
                "source": "openstreetmap_overpass",
                "status": "error",
                "stores": 0,
                "brand_values": brand_values,
                "error": str(exc)
            })

            print(f"{company}: ERROR {exc}")

        time.sleep(FETCH_SLEEP)

    return stores, status_companies


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()

    osm_stores, status_companies = collect_osm_stores()
    override_stores = load_overrides()

    all_stores = deduplicate(osm_stores + override_stores)
    all_stores.sort(key=lambda x: (x.get("company", ""), x.get("city", ""), x.get("name", "")))

    override_counts = {}
    for store in override_stores:
        company = store.get("company", "n.a.")
        override_counts[company] = override_counts.get(company, 0) + 1

    for company in OVERRIDE_COMPANIES:
        status_companies.append({
            "company": company,
            "source": "store-network-overrides.json",
            "status": "ok" if override_counts.get(company, 0) > 0 else "missing_or_empty",
            "stores": override_counts.get(company, 0)
        })

    company_totals = {}
    for store in all_stores:
        company = store.get("company", "n.a.")
        company_totals[company] = company_totals.get(company, 0) + 1

    payload = {
        "updated_at": updated_at,
        "version": "store-network-hu-v1.3-osm-plus-overrides",
        "scope": "Hungarian FMCG store network from OSM + overrides",
        "method_note": (
            "Az országos bolthálózati adatbázis OSM/Overpass lekérdezésekből és manuális override fájlból épül. "
            "ALDI, SPAR és Tesco OSM-ből érkezik. Lidl, Auchan és Penny override rétegből kezelhető, "
            "mert az OSM címkézés ezeknél hiányos vagy zajos volt. Az adatok nem hivatalos teljes üzletlisták."
        ),
        "stores": all_stores
    }

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "store-network-hu-v1.3-osm-plus-overrides",
        "source": "openstreetmap_overpass_plus_overrides",
        "store_count": len(all_stores),
        "company_totals": company_totals,
        "companies": status_companies,
        "filters": {
            "country": "Hungary",
            "osm_shop": ["supermarket", "convenience"],
            "osm_companies": list(OSM_BRANDS.keys()),
            "override_companies": OVERRIDE_COMPANIES,
            "override_file": str(OVERRIDE_FILE)
        }
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Store network written: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")
    print(f"Total stores: {len(all_stores)}")
    print(f"Company totals: {company_totals}")


if __name__ == "__main__":
    main()
