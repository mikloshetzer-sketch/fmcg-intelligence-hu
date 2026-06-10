#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

SIM_FILE = DATA_DIR / "supply-simulation.json"
RISK_FILE = DATA_DIR / "supply-risk-intelligence.json"

OUT_FILE = DATA_DIR / "expansion-simulation.json"
STATUS_FILE = DATA_DIR / "expansion-simulation-status.json"


GROWTH_SCENARIOS = [10, 20, 50, 100]

TARGET_STORE_DC_RATIO = {
    "Auchan": 60,
    "Lidl": 70,
    "Penny": 75,
    "ALDI": 90,
    "Tesco": 90,
    "SPAR": 120,
    "default": 80
}

CANDIDATE_DC_REGIONS = [
    "Debrecen",
    "Szeged",
    "Győr",
    "Pécs",
    "Miskolc",
    "Kecskemét",
    "Székesfehérvár",
    "Nyíregyháza",
    "Szolnok",
    "Nagykanizsa"
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def risk_level(score):
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def target_ratio(company):
    return TARGET_STORE_DC_RATIO.get(company, TARGET_STORE_DC_RATIO["default"])


def estimate_new_dc_need(company, new_store_count, current_dc_count):
    target = target_ratio(company)
    required_dc = max(1, math.ceil(new_store_count / target))
    additional = max(0, required_dc - current_dc_count)
    return required_dc, additional


def estimate_growth_risk(base_risk, current_store_count, new_store_count, current_dc_count, additional_dc):
    growth_factor = new_store_count / max(current_store_count, 1)

    if additional_dc > 0:
        dc_relief = min(18, additional_dc * 7)
    else:
        dc_relief = 0

    pressure = min(35, (growth_factor - 1) * 35)

    new_risk = base_risk + pressure - dc_relief
    return round(max(0, min(100, new_risk)), 1)


def estimate_new_routes(current_routes, current_store_count, new_store_count):
    if current_store_count <= 0:
        return 0
    return math.ceil(current_routes * new_store_count / current_store_count)


def estimate_new_clusters(current_clusters, growth_pct):
    if growth_pct <= 20:
        return current_clusters + 1
    if growth_pct <= 50:
        return current_clusters + 2
    return current_clusters + 4


def estimate_capacity_pct(company, store_count, dc_count):
    target = target_ratio(company)
    current_capacity = max(1, dc_count) * target
    spare = current_capacity - store_count

    if spare <= 0:
        return 0

    return round(spare / store_count * 100, 1)


def suggested_regions(company, additional_dc):
    if additional_dc <= 0:
        return []

    if company in ["ALDI", "Tesco"]:
        return ["Debrecen", "Szeged", "Miskolc"][:additional_dc + 1]

    if company == "SPAR":
        return ["Szeged", "Debrecen", "Győr"][:additional_dc + 1]

    if company == "Auchan":
        return ["Debrecen", "Szeged", "Győr", "Pécs"][:additional_dc + 1]

    if company == "Lidl":
        return ["Pécs", "Nyíregyháza", "Nagykanizsa"][:additional_dc + 1]

    if company == "Penny":
        return ["Győr", "Pécs", "Miskolc"][:additional_dc + 1]

    return CANDIDATE_DC_REGIONS[:additional_dc + 1]


def get_risk_company(risk_payload, company):
    for row in risk_payload.get("companies", []):
        if row.get("company") == company:
            return row
    return {}


def simulate_company(sim_row, risk_payload):
    company = sim_row.get("company")
    store_count = int(sim_row.get("store_count", 0))
    dc_count = int(sim_row.get("active_dc_count", 0))
    current_routes = int(sim_row.get("estimated_routes", 0))
    current_clusters = int(sim_row.get("cluster_count", 0))
    current_avg_distance = float(sim_row.get("avg_distance_km", 0))
    current_complexity = float(sim_row.get("complexity_score", 0))

    risk_row = get_risk_company(risk_payload, company)
    current_risk = float(risk_row.get("supply_risk_score", sim_row.get("complexity_score", 0)))

    capacity_pct = estimate_capacity_pct(company, store_count, dc_count)

    scenarios = []

    for growth_pct in GROWTH_SCENARIOS:
        new_store_count = math.ceil(store_count * (1 + growth_pct / 100))
        required_dc, additional_dc = estimate_new_dc_need(company, new_store_count, dc_count)

        new_routes = estimate_new_routes(current_routes, store_count, new_store_count)
        new_clusters = estimate_new_clusters(current_clusters, growth_pct)
        new_store_dc_ratio = round(new_store_count / max(required_dc, 1), 1)

        distance_pressure = 1 + min(0.25, growth_pct / 500)
        if additional_dc > 0:
            distance_pressure -= min(0.18, additional_dc * 0.06)

        new_avg_distance = round(current_avg_distance * distance_pressure, 1)

        new_complexity = round(
            min(
                100,
                current_complexity
                + min(18, growth_pct / 4)
                - min(16, additional_dc * 6)
            ),
            1
        )

        new_risk = estimate_growth_risk(
            base_risk=current_risk,
            current_store_count=store_count,
            new_store_count=new_store_count,
            current_dc_count=dc_count,
            additional_dc=additional_dc
        )

        scenarios.append({
            "growth_pct": growth_pct,
            "new_store_count": new_store_count,
            "required_dc_count": required_dc,
            "additional_dc_needed": additional_dc,
            "new_store_dc_ratio": new_store_dc_ratio,
            "estimated_routes": new_routes,
            "estimated_clusters": new_clusters,
            "new_avg_distance_km": new_avg_distance,
            "new_complexity_score": new_complexity,
            "new_supply_risk_score": new_risk,
            "new_supply_risk_level": risk_level(new_risk),
            "suggested_new_dc_regions": suggested_regions(company, additional_dc)
        })

    first_dc_need = next((s for s in scenarios if s["additional_dc_needed"] > 0), None)

    return {
        "company": company,
        "current": {
            "store_count": store_count,
            "active_dc_count": dc_count,
            "estimated_routes": current_routes,
            "cluster_count": current_clusters,
            "avg_distance_km": current_avg_distance,
            "complexity_score": current_complexity,
            "supply_risk_score": current_risk,
            "store_dc_ratio": round(store_count / max(dc_count, 1), 1)
        },
        "growth_capacity_without_new_dc_pct": capacity_pct,
        "target_store_dc_ratio": target_ratio(company),
        "first_growth_level_requiring_new_dc": first_dc_need["growth_pct"] if first_dc_need else None,
        "scenarios": scenarios,
        "method_note": (
            "Ez stratégiai növekedési szimuláció. Nem konkrét új boltcímeket helyez el, "
            "hanem az üzletszám-növekedés hatását becsüli a DC-terhelésre, túraszámra, "
            "komplexitásra és supply risk score-ra."
        )
    }


def main():
    sim_payload = load_json(SIM_FILE, {"benchmark": []})
    risk_payload = load_json(RISK_FILE, {"companies": []})

    benchmark = sim_payload.get("benchmark", [])

    companies = [simulate_company(row, risk_payload) for row in benchmark]

    capacity_ranking = sorted(
        [
            {
                "company": c["company"],
                "growth_capacity_without_new_dc_pct": c["growth_capacity_without_new_dc_pct"],
                "first_growth_level_requiring_new_dc": c["first_growth_level_requiring_new_dc"],
                "current_store_count": c["current"]["store_count"],
                "active_dc_count": c["current"]["active_dc_count"],
                "target_store_dc_ratio": c["target_store_dc_ratio"]
            }
            for c in companies
        ],
        key=lambda x: x["growth_capacity_without_new_dc_pct"],
        reverse=True
    )

    stress_50 = sorted(
        [
            {
                "company": c["company"],
                **next(s for s in c["scenarios"] if s["growth_pct"] == 50)
            }
            for c in companies
        ],
        key=lambda x: x["new_supply_risk_score"],
        reverse=True
    )

    payload = {
        "updated_at": now_iso(),
        "version": "expansion-simulation-v1",
        "method": "store_growth_stress_test",
        "method_note": (
            "A modul azt becsüli, hogy különböző üzletszám-növekedési forgatókönyvek "
            "milyen hatással lennének a jelenlegi DC-hálózatra, Store/DC arányra, túraszámra, "
            "komplexitásra és supply risk score-ra. Nem valós vállalati beruházási terv."
        ),
        "growth_scenarios_pct": GROWTH_SCENARIOS,
        "companies": companies,
        "capacity_ranking": capacity_ranking,
        "stress_test_50_pct": stress_50
    }

    status = {
        "updated_at": now_iso(),
        "status": "ok",
        "version": "expansion-simulation-v1",
        "company_count": len(companies),
        "growth_scenarios_pct": GROWTH_SCENARIOS,
        "capacity_ranking": capacity_ranking,
        "stress_test_50_pct": stress_50
    }

    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Expansion simulation written: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")


if __name__ == "__main__":
    main()
