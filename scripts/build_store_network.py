#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import hashlib
import requests
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

OUT_FILE = DATA_DIR / "store-network-hu.json"
STATUS_FILE = DATA_DIR / "store-network-hu-status.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FETCH_SLEEP = 2

BRANDS = {
    "Lidl": ["Lidl"],
    "ALDI": ["ALDI", "Aldi"],
    "SPAR": ["SPAR", "INTERSPAR", "Interspar", "Spar"],
    "Tesco": ["Tesco", "TESCO"],
    "Auchan": ["Auchan"],
    "Penny": ["Penny", "PENNY", "Penny Market", "PENNY Market"]
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def slugify(value):
    value = value.lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o", "ő": "o",
        "ú": "u", "ü": "u", "ű": "u",
        " ": "_", "-": "_", ".": "", ",": "", "/": "_"
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = "".join(ch for ch in value if ch.isalnum() or ch == "_")
    while "__" in value:
        value = value.replace("__", "_")

    return value.strip("_")


def make_store_id(company, name, city, osm_id):
    base = f"{company}_{city}_{name}_{osm_id}"
    return slugify(base)[:80]


def region_from_city(city):
    city_l = (city or "").lower()

    if city_l == "budapest":
        return "Közép-Magyarország"

    county_regions = {
        "budaörs": "Közép-Magyarország",
        "szigetszentmiklós": "Közép-Magyarország",
        "dunakeszi": "Közép-Magyarország",
        "érd": "Közép-Magyarország",
        "vecsés": "Közép-Magyarország",
        "gyál": "Közép-Magyarország",
        "monor": "Közép-Magyarország",

        "győr": "Nyugat-Dunántúl",
        "sopron": "Nyugat-Dunántúl",
        "szombathely": "Nyugat-Dunántúl",
        "zalaegerszeg": "Nyugat-Dunántúl",
        "nagykanizsa": "Nyugat-Dunántúl",

        "veszprém": "Közép-Dunántúl",
        "székesfehérvár": "Közép-Dunántúl",
        "tatabánya": "Közép-Dunántúl",
        "dunaújváros": "Közép-Dunántúl",

        "pécs": "Dél-Dunántúl",
        "kaposvár": "Dél-Dunántúl",
        "szekszárd": "Dél-Dunántúl",

        "miskolc": "Észak-Magyarország",
        "eger": "Észak-Magyarország",
        "salgótarján": "Észak-Magyarország",

        "debrecen": "Észak-Alföld",
        "nyíregyháza": "Észak-Alföld",
        "szolnok": "Észak-Alföld",

        "szeged": "Dél-Alföld",
        "kecskemét": "Dél-Alföld",
        "békéscsaba": "Dél-Alföld",
        "hódmezővásárhely": "Dél-Alföld"
    }

    return county_regions.get(city_l, "n.a.")


def build_overpass_query(brand_values):
    brand_filters = []

    for brand in brand_values:
        escaped = brand.replace('"', '\\"')
        brand_filters.append(f'node["shop"~"supermarket|convenience"]["brand"="{escaped}"](area.searchArea);')
        brand_filters.append(f'way["shop"~"supermarket|convenience"]["brand"="{escaped}"](area.searchArea);')
        brand_filters.append(f'relation["shop"~"supermarket|convenience"]["brand"="{escaped}"](area.searchArea);')

    brand_block = "\n".join(brand_filters)

    return f"""
[out:json][timeout:180];
area["ISO3166-1"="HU"][admin_level=2]->.searchArea;
(
{brand_block}
);
out center tags;
"""


def fetch_overpass(query):
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
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


def normalize_company_from_brand(raw_brand):
    raw = (raw_brand or "").lower()

    if "lidl" in raw:
        return "Lidl"
    if "aldi" in raw:
        return "ALDI"
    if "spar" in raw:
        return "SPAR"
    if "tesco" in raw:
        return "Tesco"
    if "auchan" in raw:
        return "Auchan"
    if "penny" in raw:
        return "Penny"

    return raw_brand or "n.a."


def parse_element(element, expected_company):
    tags = element.get("tags", {})
    lat, lon = element_coordinates(element)

    if lat is None or lon is None:
        return None

    raw_brand = tags.get("brand") or expected_company
    company = normalize_company_from_brand(raw_brand)

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


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()
    stores = []
    status_companies = []

    for company, brand_values in BRANDS.items():
        print(f"Fetching {company}...")

        try:
            query = build_overpass_query(brand_values)
            data = fetch_overpass(query)

            company_stores = []

            for element in data.get("elements", []):
                store = parse_element(element, company)
                if store:
                    company_stores.append(store)

            company_stores = deduplicate(company_stores)
            stores.extend(company_stores)

            status_companies.append({
                "company": company,
                "status": "ok",
                "stores": len(company_stores),
                "brand_values": brand_values
            })

            print(f"{company}: {len(company_stores)} stores")

        except Exception as exc:
            status_companies.append({
                "company": company,
                "status": "error",
                "stores": 0,
                "brand_values": brand_values,
                "error": str(exc)
            })
            print(f"{company}: ERROR {exc}")

        time.sleep(FETCH_SLEEP)

    stores = deduplicate(stores)
    stores.sort(key=lambda x: (x.get("company", ""), x.get("city", ""), x.get("name", "")))

    payload = {
        "updated_at": updated_at,
        "version": "store-network-hu-v1-openstreetmap-overpass",
        "scope": "Hungarian FMCG store network from OpenStreetMap",
        "method_note": (
            "OpenStreetMap / Overpass alapú országos bolthálózati adatbázis. "
            "Az adatok közösségi térképi forrásból származnak, ezért nem tekinthetők hivatalos teljes üzletlistának. "
            "A Supply Chain oldal fizikai hálózati elemzéséhez és Store→DC távolságszámításhoz használható alapréteg."
        ),
        "stores": stores
    }

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "store-network-hu-v1-openstreetmap-overpass",
        "source": "openstreetmap_overpass",
        "store_count": len(stores),
        "companies": status_companies,
        "filters": {
            "country": "Hungary",
            "shop": "supermarket|convenience",
            "brands": BRANDS
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
    print(f"Total stores: {len(stores)}")


if __name__ == "__main__":
    main()
