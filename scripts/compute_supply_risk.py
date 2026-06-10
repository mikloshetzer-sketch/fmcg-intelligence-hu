#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

STORE_FILE = DATA_DIR / "store-network-hu-final.json"
DC_FILE = DATA_DIR / "distribution-centers.json"
SIM_FILE = DATA_DIR / "supply-simulation.json"

OUT_FILE = DATA_DIR / "supply-risk-intelligence.json"
STATUS_FILE = DATA_DIR / "supply-risk-intelligence-status.json"


CITY_POPULATION_ESTIMATE = {
    "Budapest": 1700000,
    "Debrecen": 200000,
    "Szeged": 160000,
    "Miskolc": 150000,
    "Pécs": 140000,
    "Győr": 130000,
    "Nyíregyháza": 115000,
    "Kecskemét": 110000,
    "Székesfehérvár": 95000,
    "Szombathely": 78000,
    "Szolnok": 70000,
    "Tatabánya": 65000,
    "Kaposvár": 60000,
    "Békéscsaba": 58000,
    "Veszprém": 56000,
    "Zalaegerszeg": 55000,
    "Eger": 52000,
    "Sopron": 62000,
    "Nagykanizsa": 45000,
    "Dunaújváros": 43000,
    "Hódmezővásárhely": 43000,
    "Salgótarján": 34000,
    "Baja": 34000,
    "Esztergom": 28000,
    "Szigetszentmiklós": 40000,
    "Dunakeszi": 45000,
    "Budaörs": 30000,
    "Vác": 33000,
    "Cegléd": 35000,
    "Gödöllő": 33000,
    "Mosonmagyaróvár": 33000,
    "Keszthely": 20000,
    "Kőszeg": 11000
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def city_population(city):
    if not city:
        return 8000

    city = str(city).strip()

    if city in CITY_POPULATION_ESTIMATE:
        return CITY_POPULATION_ESTIMATE[city]

    # Egyszerű proxy ismeretlen városokra.
    return 12000


def active_dcs_for_company(dcs, company):
    return [
        dc for dc in dcs
        if dc.get("company") == company and dc.get("status", "active") == "active"
    ]


def nearest_dc(store, dcs):
    best = None

    for dc in dcs:
        if "lat" not in dc or "lon" not in dc:
            continue

        dist = haversine_km(store["lat"], store["lon"], dc["lat"], dc["lon"])

        if best is None or dist < best["distance_km"]:
            best = {
                "dc_id": dc.get("dc_id") or dc.get("name"),
                "dc_name": dc.get("name"),
                "dc_city": dc.get("city"),
                "distance_km": dist
            }

    return best


def get_simulation_row(sim_payload, company):
    for row in sim_payload.get("benchmark", []):
        if row.get("company") == company:
            return row
    return {}


def risk_level(score):
    if score >= 70:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def normalize_score(value, max_value):
    if max_value <= 0:
        return 0
    return max(0, min(100, (value / max_value) * 100))


def compute_company(company, stores, dcs, sim_payload):
    company_stores = [
        s for s in stores
        if s.get("company") == company and "lat" in s and "lon" in s
    ]

    company_dcs = active_dcs_for_company(dcs, company)
    sim = get_simulation_row(sim_payload, company)

    city_set = sorted(set(s.get("city") for s in company_stores if s.get("city")))
    reached_population = sum(city_population(city) for city in city_set)

    city_store_counts = {}
    for s in company_stores:
        city = s.get("city", "n.a.")
        city_store_counts[city] = city_store_counts.get(city, 0) + 1

    assignments = []
    dc_impact = {}

    for store in company_stores:
        ndc = nearest_dc(store, company_dcs)
        if not ndc:
            continue

        city = store.get("city", "n.a.")
        pop_share = city_population(city) / max(city_store_counts.get(city, 1), 1)

        dc_id = ndc["dc_id"]

        if dc_id not in dc_impact:
            dc_impact[dc_id] = {
                "dc_id": dc_id,
                "dc_name": ndc["dc_name"],
                "dc_city": ndc["dc_city"],
                "affected_stores": 0,
                "affected_population_proxy": 0,
                "distances": []
            }

        dc_impact[dc_id]["affected_stores"] += 1
        dc_impact[dc_id]["affected_population_proxy"] += pop_share
        dc_impact[dc_id]["distances"].append(ndc["distance_km"])

        assignments.append({
            "store_id": store.get("store_id"),
            "store_name": store.get("name"),
            "city": city,
            "region": store.get("region", "n.a."),
            "dc_id": dc_id,
            "dc_name": ndc["dc_name"],
            "distance_km": round(ndc["distance_km"], 1),
            "population_proxy": round(pop_share)
        })

    for item in dc_impact.values():
        dists = item.pop("distances", [])
        item["affected_population_proxy"] = round(item["affected_population_proxy"])
        item["avg_distance_km"] = round(sum(dists) / len(dists), 1) if dists else 0
        item["max_distance_km"] = round(max(dists), 1) if dists else 0
        item["affected_store_share_pct"] = round(
            item["affected_stores"] / max(len(company_stores), 1) * 100,
            1
        )

    dc_impact_list = sorted(
        dc_impact.values(),
        key=lambda x: x["affected_stores"],
        reverse=True
    )

    max_dc_share = dc_impact_list[0]["affected_store_share_pct"] if dc_impact_list else 0

    complexity = float(sim.get("complexity_score", 0))
    avg_distance = float(sim.get("avg_distance_km", 0))
    max_distance = float(sim.get("max_distance_km", 0))
    store_dc_ratio = float(sim.get("store_dc_ratio", 0))
    cluster_count = float(sim.get("cluster_count", 0))

    long_distance_pressure = normalize_score(max_distance, 300)
    dc_concentration_pressure = max_dc_share
    store_dc_pressure = normalize_score(store_dc_ratio, 260)
    cluster_pressure = normalize_score(cluster_count, 25)

    supply_risk_score = round(
        0.35 * complexity
        + 0.25 * dc_concentration_pressure
        + 0.20 * long_distance_pressure
        + 0.10 * store_dc_pressure
        + 0.10 * cluster_pressure,
        1
    )

    coverage_score = round(min(100, reached_population / 9600000 * 100), 1)

    return {
        "company": company,
        "store_count": len(company_stores),
        "active_dc_count": len(company_dcs),
        "city_count": len(city_set),
        "reached_population_proxy": round(reached_population),
        "coverage_score": coverage_score,
        "avg_distance_km": round(avg_distance, 1),
        "max_distance_km": round(max_distance, 1),
        "store_dc_ratio": round(store_dc_ratio, 1),
        "cluster_count": int(cluster_count),
        "complexity_score": round(complexity, 1),
        "supply_risk_score": supply_risk_score,
        "supply_risk_level": risk_level(supply_risk_score),
        "risk_drivers": {
            "complexity": round(complexity, 1),
            "largest_dc_exposure_pct": round(dc_concentration_pressure, 1),
            "long_distance_pressure": round(long_distance_pressure, 1),
            "store_dc_pressure": round(store_dc_pressure, 1),
            "cluster_pressure": round(cluster_pressure, 1)
        },
        "dc_impact": dc_impact_list,
        "assignments_sample": assignments[:300],
        "method_note": (
            "A lefedett lakosság becslés települési proxy alapján készül. "
            "A DC-kiesési hatás a legközelebbi aktív DC modellből számolódik. "
            "Nem valós vállalati fuvarszervezési adat."
        )
    }


def main():
    stores_payload = load_json(STORE_FILE, {"stores": []})
    dc_payload = load_json(DC_FILE, {"items": []})
    sim_payload = load_json(SIM_FILE, {"benchmark": []})

    stores = stores_payload.get("stores", [])
    dcs = dc_payload.get("items", [])

    companies = sorted(set(s.get("company") for s in stores if s.get("company")))

    companies_result = [
        compute_company(company, stores, dcs, sim_payload)
        for company in companies
    ]

    risk_ranking = sorted(
        [
            {
                "company": c["company"],
                "supply_risk_score": c["supply_risk_score"],
                "supply_risk_level": c["supply_risk_level"],
                "coverage_score": c["coverage_score"],
                "reached_population_proxy": c["reached_population_proxy"],
                "largest_dc_exposure_pct": c["risk_drivers"]["largest_dc_exposure_pct"]
            }
            for c in companies_result
        ],
        key=lambda x: x["supply_risk_score"],
        reverse=True
    )

    payload = {
        "updated_at": now_iso(),
        "version": "supply-risk-intelligence-v1",
        "method": "population_proxy_plus_dc_vulnerability",
        "method_note": (
            "A modul települési népességi proxy, bolthálózat, DC-hálózat és a supply simulation eredmények alapján "
            "becsül lefedettséget, DC-kitettséget és supply risk score-t. "
            "Nem belső vállalati adat, hanem OSINT-alapú összehasonlító modell."
        ),
        "companies": companies_result,
        "risk_ranking": risk_ranking
    }

    status = {
        "updated_at": now_iso(),
        "status": "ok",
        "version": "supply-risk-intelligence-v1",
        "store_count": len(stores),
        "dc_count": len(dcs),
        "company_count": len(companies),
        "companies": companies,
        "risk_ranking": risk_ranking
    }

    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Supply risk written: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")
    print(f"Companies: {companies}")


if __name__ == "__main__":
    main()
