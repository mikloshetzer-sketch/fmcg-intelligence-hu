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

OUT_FILE = DATA_DIR / "supply-simulation.json"
STATUS_FILE = DATA_DIR / "supply-simulation-status.json"


ROUTE_STORE_CAPACITY = {
    "default": 4,
    "Auchan": 3,
    "Tesco": 4,
    "SPAR": 5,
    "Lidl": 4,
    "ALDI": 4,
    "Penny": 4
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
    r = 6371.0

    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )

    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def company_list(stores):
    return sorted(set(s.get("company") for s in stores if s.get("company")))


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

        distance = haversine_km(
            store.get("lat"),
            store.get("lon"),
            dc.get("lat"),
            dc.get("lon")
        )

        if best is None or distance < best["distance_km"]:
            best = {
                "dc_id": dc.get("dc_id"),
                "dc_name": dc.get("name"),
                "dc_city": dc.get("city"),
                "dc_type": dc.get("type"),
                "dc_lat": dc.get("lat"),
                "dc_lon": dc.get("lon"),
                "distance_km": distance
            }

    return best


def distance_bucket(distance):
    if distance <= 50:
        return "0-50 km"
    if distance <= 100:
        return "50-100 km"
    if distance <= 150:
        return "100-150 km"
    if distance <= 200:
        return "150-200 km"
    return "200+ km"


def risk_level(score):
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def efficiency_score(avg_distance, max_distance, store_dc_ratio, clusters):
    """
    Egyszerű benchmark index.
    Nem valós TMS optimalizáció, hanem hálózati szerkezeti becslés.
    Magasabb pontszám = kedvezőbb becsült logisztikai szerkezet.
    """

    score = 100

    score -= min(avg_distance / 3.0, 35)
    score -= min(max_distance / 15.0, 20)
    score -= min(store_dc_ratio / 8.0, 20)
    score -= min(clusters / 3.0, 15)

    return max(0, min(100, round(score, 1)))


def complexity_score(avg_distance, max_distance, store_count, dc_count, clusters):
    """
    Magasabb érték = bonyolultabb hálózat.
    """

    if dc_count <= 0:
        return 100

    score = 0
    score += min(avg_distance / 2.0, 35)
    score += min(max_distance / 10.0, 25)
    score += min((store_count / max(dc_count, 1)) / 5.0, 25)
    score += min(clusters / 2.0, 15)

    return max(0, min(100, round(score, 1)))


def simulate_company(company, stores, dcs):
    company_stores = [
        s for s in stores
        if s.get("company") == company and "lat" in s and "lon" in s
    ]

    company_dcs = active_dcs_for_company(dcs, company)

    assignments = []
    dc_loads = {}
    distance_buckets = {
        "0-50 km": 0,
        "50-100 km": 0,
        "100-150 km": 0,
        "150-200 km": 0,
        "200+ km": 0
    }
    regional_counts = {}

    for store in company_stores:
        ndc = nearest_dc(store, company_dcs)

        region = store.get("region") or "n.a."
        regional_counts[region] = regional_counts.get(region, 0) + 1

        if not ndc:
            continue

        distance = ndc["distance_km"]
        bucket = distance_bucket(distance)
        distance_buckets[bucket] = distance_buckets.get(bucket, 0) + 1

        dc_id = ndc["dc_id"] or ndc["dc_name"] or "unknown_dc"

        if dc_id not in dc_loads:
            dc_loads[dc_id] = {
                "dc_id": dc_id,
                "dc_name": ndc["dc_name"],
                "dc_city": ndc["dc_city"],
                "dc_type": ndc["dc_type"],
                "stores": 0,
                "avg_distance_km": 0,
                "max_distance_km": 0,
                "distances": [],
                "regions": {}
            }

        dc_loads[dc_id]["stores"] += 1
        dc_loads[dc_id]["distances"].append(distance)
        dc_loads[dc_id]["regions"][region] = dc_loads[dc_id]["regions"].get(region, 0) + 1

        assignments.append({
            "store_id": store.get("store_id"),
            "store_name": store.get("name"),
            "city": store.get("city"),
            "region": region,
            "lat": store.get("lat"),
            "lon": store.get("lon"),
            "dc_id": ndc["dc_id"],
            "dc_name": ndc["dc_name"],
            "dc_city": ndc["dc_city"],
            "distance_km": round(distance, 1),
            "distance_bucket": bucket,
            "assignment_method": "nearest_active_dc"
        })

    distances = [a["distance_km"] for a in assignments]

    for dc_id, dc in dc_loads.items():
        dists = dc.pop("distances", [])
        if dists:
            dc["avg_distance_km"] = round(sum(dists) / len(dists), 1)
            dc["max_distance_km"] = round(max(dists), 1)

    clusters = len(set(
        f"{a.get('dc_id')}|{a.get('region')}"
        for a in assignments
    ))

    route_capacity = ROUTE_STORE_CAPACITY.get(company, ROUTE_STORE_CAPACITY["default"])
    estimated_routes = math.ceil(len(company_stores) / route_capacity)

    avg_distance = round(sum(distances) / len(distances), 1) if distances else 0
    max_distance = round(max(distances), 1) if distances else 0
    store_dc_ratio = round(len(company_stores) / max(len(company_dcs), 1), 1) if company_dcs else 0

    eff = efficiency_score(
        avg_distance=avg_distance,
        max_distance=max_distance,
        store_dc_ratio=store_dc_ratio,
        clusters=clusters
    )

    comp = complexity_score(
        avg_distance=avg_distance,
        max_distance=max_distance,
        store_count=len(company_stores),
        dc_count=len(company_dcs),
        clusters=clusters
    )

    most_loaded_dc = None
    if dc_loads:
        most_loaded_dc = sorted(
            dc_loads.values(),
            key=lambda x: x.get("stores", 0),
            reverse=True
        )[0]

    remote_stores = sorted(
        assignments,
        key=lambda x: x.get("distance_km", 0),
        reverse=True
    )[:10]

    return {
        "company": company,
        "store_count": len(company_stores),
        "active_dc_count": len(company_dcs),
        "cluster_count": clusters,
        "estimated_routes": estimated_routes,
        "route_capacity_assumption": route_capacity,
        "avg_distance_km": avg_distance,
        "max_distance_km": max_distance,
        "store_dc_ratio": store_dc_ratio,
        "efficiency_score": eff,
        "complexity_score": comp,
        "complexity_level": risk_level(comp),
        "distance_buckets": distance_buckets,
        "regional_counts": dict(sorted(regional_counts.items())),
        "dc_loads": sorted(
            dc_loads.values(),
            key=lambda x: x.get("stores", 0),
            reverse=True
        ),
        "most_loaded_dc": most_loaded_dc,
        "remote_stores": remote_stores,
        "assignments_sample": assignments[:200],
        "assignment_method": "nearest_active_dc",
        "method_warning": (
            "Ez becsült szimuláció. Nem valós vállalati TMS-hozzárendelés. "
            "A rendszer a legközelebbi aktív DC alapján rendel üzletet raktárhoz."
        )
    }


def build_failure_simulation(company_result):
    failures = []

    for dc in company_result.get("dc_loads", []):
        affected = dc.get("stores", 0)
        company_total = company_result.get("store_count", 0)
        share = affected / company_total if company_total else 0

        if share >= 0.6:
            level = "high"
        elif share >= 0.3:
            level = "medium"
        else:
            level = "low"

        failures.append({
            "company": company_result.get("company"),
            "dc_id": dc.get("dc_id"),
            "dc_name": dc.get("dc_name"),
            "dc_city": dc.get("dc_city"),
            "affected_stores": affected,
            "affected_share_pct": round(share * 100, 1),
            "risk_level": level,
            "note": (
                "Becsült kiesési hatás a nearest-DC modell alapján. "
                "Nem tartalmaz kapacitás- és átterhelési szabályokat."
            )
        })

    return sorted(
        failures,
        key=lambda x: x.get("affected_stores", 0),
        reverse=True
    )


def main():
    stores_payload = load_json(STORE_FILE, {"stores": []})
    dc_payload = load_json(DC_FILE, {"items": []})

    stores = stores_payload.get("stores", [])
    dcs = dc_payload.get("items", [])

    companies = company_list(stores)

    company_results = []
    failure_results = []

    for company in companies:
        result = simulate_company(company, stores, dcs)
        company_results.append(result)
        failure_results.extend(build_failure_simulation(result))

    benchmark = sorted(
        [
            {
                "company": r["company"],
                "store_count": r["store_count"],
                "active_dc_count": r["active_dc_count"],
                "cluster_count": r["cluster_count"],
                "estimated_routes": r["estimated_routes"],
                "avg_distance_km": r["avg_distance_km"],
                "max_distance_km": r["max_distance_km"],
                "store_dc_ratio": r["store_dc_ratio"],
                "efficiency_score": r["efficiency_score"],
                "complexity_score": r["complexity_score"],
                "complexity_level": r["complexity_level"]
            }
            for r in company_results
        ],
        key=lambda x: x["efficiency_score"],
        reverse=True
    )

    payload = {
        "updated_at": now_iso(),
        "version": "supply-simulation-v1",
        "method": "nearest_active_dc_route_cluster_simulation",
        "method_note": (
            "A szimuláció nem valós vállalati fuvarszervezési adat. "
            "A modell az üzleteket a legközelebbi aktív logisztikai központhoz rendeli, "
            "majd ebből becsül klasztert, túraszámot, távolsági sávokat és hálózati komplexitást."
        ),
        "assumptions": {
            "assignment": "nearest_active_dc",
            "distance": "haversine_air_distance",
            "route_capacity": ROUTE_STORE_CAPACITY,
            "cluster_definition": "dc_region_pair"
        },
        "benchmark": benchmark,
        "companies": company_results,
        "failure_simulation": failure_results
    }

    status = {
        "updated_at": now_iso(),
        "status": "ok",
        "version": "supply-simulation-v1",
        "store_file": str(STORE_FILE),
        "dc_file": str(DC_FILE),
        "store_count": len(stores),
        "dc_count": len(dcs),
        "company_count": len(companies),
        "companies": companies,
        "benchmark": benchmark
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Supply simulation written: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")
    print(f"Companies: {companies}")


if __name__ == "__main__":
    main()
