#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Dashboard Data Builder v3

Input:
- docs/data/retail-salary-benchmark.json
- docs/data/salary-verified-data.json
- docs/data/salary-role-summary.json

Output:
- docs/data/salary-dashboard-data.json

Cél:
- 2026-os Salary Intelligence blokk előállítása.
- A dashboard ne csak bérszámot mutasson, hanem azt is, milyen információt sikerült beszerezni.
- Hivatalos vállalati források elsőbbsége.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

BENCHMARK_FILE = DATA_DIR / "retail-salary-benchmark.json"
SALARY_VERIFIED_FILE = DATA_DIR / "salary-verified-data.json"
SALARY_ROLE_SUMMARY_FILE = DATA_DIR / "salary-role-summary.json"
OUTPUT_FILE = DATA_DIR / "salary-dashboard-data.json"

NA = "N.A."


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def is_number(value):
    return isinstance(value, (int, float))


def format_salary(value):
    if not is_number(value):
        return NA

    return f"{int(value):,}".replace(",", " ") + " Ft"


def format_salary_range(min_value, mid_value, max_value):
    if not is_number(min_value) and not is_number(max_value):
        return NA

    if is_number(min_value) and is_number(max_value) and min_value != max_value:
        return f"{format_salary(min_value)} - {format_salary(max_value)}"

    if is_number(mid_value):
        return format_salary(mid_value)

    if is_number(min_value):
        return format_salary(min_value)

    if is_number(max_value):
        return format_salary(max_value)

    return NA


def build_benchmark_table(benchmark):
    rows = []

    for role in benchmark.get("roles", []):
        rows.append({
            "role_key": role.get("role_key"),
            "role_label": role.get("role_label"),
            "benchmark_salary_display": format_salary_range(
                role.get("salary_min_huf_month"),
                role.get("salary_mid_huf_month"),
                role.get("salary_max_huf_month"),
            ),
            "salary_min_huf_month": role.get("salary_min_huf_month"),
            "salary_mid_huf_month": role.get("salary_mid_huf_month"),
            "salary_max_huf_month": role.get("salary_max_huf_month"),
        })

    return rows


def official_salary_intelligence_cards():
    return [
        {
            "company_id": "aldi",
            "company": "ALDI",
            "headline": "541 900 - 750 600 Ft",
            "subheadline": "Részletes 2026-os bérstruktúra.",
            "information_depth": "detailed_structure",
            "information_depth_label": "Részletes bérstruktúra",
            "information_items": [
                "áruházi dolgozó kezdő bér",
                "1 év utáni bér",
                "maximális áruházi bér",
                "logisztikai béradatok"
            ],
            "source_quality": "official_company",
            "source_label": "Hivatalos vállalati közlés",
            "source_priority": 100,
            "source_name": "ALDI sajtóközlemény",
            "source_url": "https://www.aldi.hu/az-aldirol/sajtoszoba/sajtokozlemenyek/koezlemenyek-2026/beremeles-az-aldi-nal--minden-pozicioban-noevekedes",
            "confidence": 100,
            "data_year": 2026
        },
        {
            "company_id": "lidl",
            "company": "Lidl",
            "headline": "599 000 - 700 000+ Ft",
            "subheadline": "Több munkakörre vonatkozó 2026-os bérinformáció.",
            "information_depth": "detailed_structure",
            "information_depth_label": "Részletes bérstruktúra",
            "information_items": [
                "bolti dolgozó bére",
                "üzletvezetői bérek",
                "logisztikai bérek",
                "maximális jövedelmi szintek"
            ],
            "source_quality": "official_company",
            "source_label": "Hivatalos vállalati közlés",
            "source_priority": 100,
            "source_name": "Lidl sajtóközlemény",
            "source_url": "https://vallalat.lidl.hu/sajtoszoba/sajtokoezlemenyek/20260420_berfejlesztes",
            "confidence": 100,
            "data_year": 2026
        },
        {
            "company_id": "auchan",
            "company": "Auchan",
            "headline": "9,2%-os éves béremelés",
            "subheadline": "Fizikai munkaköröket érintő 2026-os bérinformáció.",
            "information_depth": "partial_information",
            "information_depth_label": "Részleges bérinformáció",
            "information_items": [
                "kétlépcsős béremelés",
                "pék munkakör",
                "hentes munkakör",
                "cukrász és logisztikai munkakörök"
            ],
            "source_quality": "official_company",
            "source_label": "Hivatalos vállalati közlés",
            "source_priority": 100,
            "source_name": "Auchan sajtóközlemény",
            "source_url": "https://auchan.hu/sajtokozlemenyek/2026-beremeles",
            "confidence": 100,
            "data_year": 2026
        },
        {
            "company_id": "tesco",
            "company": "Tesco",
            "headline": "+7,2% béremelés",
            "subheadline": "2026-os béremelési és alapbér-információ.",
            "information_depth": "partial_information",
            "information_depth_label": "Részleges bérinformáció",
            "information_items": [
                "átlagos béremelés",
                "áruházi alapbér",
                "maximális elérhető jövedelem",
                "juttatási elemek"
            ],
            "source_quality": "official_company",
            "source_label": "Hivatalos vállalati közlés",
            "source_priority": 100,
            "source_name": "Tesco vállalati közlés",
            "source_url": "https://corporate.tesco.hu/beremeles-2026",
            "confidence": 100,
            "data_year": 2026
        },
        {
            "company_id": "penny",
            "company": "PENNY",
            "headline": "+8% béremelés",
            "subheadline": "Értékesítési és logisztikai területet érintő 2026-os béremelés.",
            "information_depth": "partial_information",
            "information_depth_label": "Részleges bérinformáció",
            "information_items": [
                "értékesítési béremelés",
                "logisztikai béremelés",
                "központi béremelés",
                "rugalmas juttatási rendszer"
            ],
            "source_quality": "official_company",
            "source_label": "Hivatalos vállalati közlés",
            "source_priority": 100,
            "source_name": "PENNY vállalati közlés",
            "source_url": "https://www.penny.hu/tovabbi-3-4-milliard-forintot-fordit-berfejlesztesre-a-penny",
            "confidence": 100,
            "data_year": 2026
        },
        {
            "company_id": "spar",
            "company": "SPAR",
            "headline": "Nincs hivatalos 2026-os bérközlés",
            "subheadline": "Csak referencia szintű információ áll rendelkezésre.",
            "information_depth": "reference_only",
            "information_depth_label": "Referencia szintű információ",
            "information_items": [
                "általános piaci bérinformáció",
                "dolgozói önbevallásos referencia",
                "hivatalos 2026-os közlés nem azonosítható"
            ],
            "source_quality": "secondary_reference",
            "source_label": "Másodlagos referenciaforrás",
            "source_priority": 70,
            "source_name": "WhereWeWork referencia",
            "source_url": "https://www.wherewework.hu/hu/fizetesek-spar-magyarorszag-minden-a-munkakornyezetrol-ertekeles-fizetes-allasinterjuk-juttatasok-234",
            "confidence": 70,
            "data_year": 2026
        }
    ]


def build_salary_intelligence_summary(cards):
    detailed = sum(1 for c in cards if c.get("information_depth") == "detailed_structure")
    partial = sum(1 for c in cards if c.get("information_depth") == "partial_information")
    reference = sum(1 for c in cards if c.get("information_depth") == "reference_only")
    official = sum(1 for c in cards if c.get("source_quality") == "official_company")

    return {
        "detailed_structure": detailed,
        "partial_information": partial,
        "reference_only": reference,
        "official_sources": official,
        "companies_total": len(cards)
    }


def build_company_cards_from_intelligence(cards):
    dashboard_cards = []

    for card in cards:
        if card.get("information_depth") == "detailed_structure":
            status = "current_2026_salary"
            coverage_score = 100
            coverage_label = "magas"
        elif card.get("information_depth") == "partial_information":
            status = "current_2026_partial"
            coverage_score = 75
            coverage_label = "közepes"
        elif card.get("information_depth") == "reference_only":
            status = "reference_only"
            coverage_score = 40
            coverage_label = "referencia"
        else:
            status = "no_data"
            coverage_score = 0
            coverage_label = "nincs adat"

        dashboard_cards.append({
            "company_id": card.get("company_id"),
            "company": card.get("company"),
            "status": status,
            "year_status": card.get("information_depth"),
            "data_year": card.get("data_year", 2026),

            "base_salary_display": card.get("headline", NA),
            "base_salary_huf_month": NA,
            "highest_salary_display": card.get("headline", NA),
            "highest_salary_huf_month": NA,
            "salary_raise_pct": NA,

            "salary_record_count": 1 if card.get("information_depth") == "detailed_structure" else 0,
            "raise_record_count": 1 if card.get("information_depth") == "partial_information" else 0,
            "total_record_count": 1,

            "coverage_score": coverage_score,
            "coverage_label": coverage_label,
            "confidence": card.get("confidence", 0),

            "primary_source_name": card.get("source_name", NA),
            "primary_source_url": card.get("source_url", NA),
            "source_quality": card.get("source_quality", NA),
            "source_label": card.get("source_label", NA),
            "source_priority": card.get("source_priority", 0),

            "information_depth": card.get("information_depth"),
            "information_depth_label": card.get("information_depth_label"),
            "information_items": card.get("information_items", []),
            "subheadline": card.get("subheadline", ""),
            "notes": "2026 Salary Intelligence kártya. A rendszer azt is mutatja, milyen mélységű információt sikerült beszerezni."
        })

    return dashboard_cards


def build_role_matrix(role_summary):
    rows = role_summary.get("rows", [])
    matrix = []

    for row in rows:
        min_value = row.get("salary_min_huf_month")
        mid_value = row.get("salary_median_huf_month")
        max_value = row.get("salary_max_huf_month")

        matrix.append({
            "company_id": row.get("company_id"),
            "company": row.get("company"),
            "role_key": row.get("role_key"),
            "role_label": row.get("role_label"),
            "salary_display": format_salary_range(min_value, mid_value, max_value),
            "salary_min_huf_month": min_value,
            "salary_median_huf_month": mid_value,
            "salary_max_huf_month": max_value,
            "record_count": row.get("record_count", 0),
            "confidence": row.get("confidence", 0),
            "source_name": row.get("source_name", NA),
            "source_url": row.get("source_url", NA),
            "evidence_text": row.get("evidence_text", NA),
            "notes": row.get("notes", ""),
        })

    return matrix


def build_evidence_table(cards):
    rows = []

    for card in cards:
        rows.append({
            "company_id": card.get("company_id"),
            "company": card.get("company"),
            "value_type": card.get("information_depth"),
            "source_name": card.get("source_name", NA),
            "source_url": card.get("source_url", NA),
            "published_or_found_date": "2026",
            "data_year": 2026,
            "confidence": card.get("confidence", 0),
            "source_quality": card.get("source_quality", NA),
            "source_label": card.get("source_label", NA),
            "evidence_text": "; ".join(card.get("information_items", [])),
        })

    return rows


def build_output():
    benchmark = load_json(BENCHMARK_FILE, {})
    role_summary = load_json(SALARY_ROLE_SUMMARY_FILE, {})
    verified = load_json(SALARY_VERIFIED_FILE, {})

    benchmark_table = build_benchmark_table(benchmark)

    salary_intelligence_cards = official_salary_intelligence_cards()
    salary_intelligence_summary = build_salary_intelligence_summary(salary_intelligence_cards)

    company_cards = build_company_cards_from_intelligence(salary_intelligence_cards)
    role_matrix = build_role_matrix(role_summary)
    evidence_table = build_evidence_table(salary_intelligence_cards)

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_dashboard_data_v3_2026_salary_intelligence",
        "input_files": [
            "docs/data/retail-salary-benchmark.json",
            "docs/data/salary-verified-data.json",
            "docs/data/salary-role-summary.json"
        ],
        "important_note": (
            "Ez a dashboardhoz előkészített 2026 Salary Intelligence adat. "
            "A rendszer nem csak a bér nagyságát mutatja, hanem azt is, milyen mélységű információt sikerült beszerezni. "
            "Elsődleges forrásként hivatalos vállalati közléseket használunk. "
            "A SPAR esetében jelenleg csak másodlagos referenciaforrás áll rendelkezésre."
        ),
        "benchmark": {
            "source": benchmark.get("source", NA),
            "source_type": benchmark.get("source_type", NA),
            "currency": benchmark.get("currency", "HUF"),
            "period": benchmark.get("period", "month"),
            "salary_type": benchmark.get("salary_type", "gross"),
            "data_year": 2026,
            "rows": benchmark_table,
        },
        "salary_intelligence_cards": salary_intelligence_cards,
        "salary_intelligence_summary": salary_intelligence_summary,
        "company_cards": company_cards,
        "role_matrix": role_matrix,
        "evidence_table": evidence_table,
        "verified_salary_summary": verified.get("summary", {}),
    }


def main():
    print("Salary Dashboard Data Builder started.")

    output = build_output()

    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Method: {output.get('method')}")
    print(f"Salary intelligence cards: {len(output.get('salary_intelligence_cards', []))}")
    print(f"Evidence rows: {len(output.get('evidence_table', []))}")


if __name__ == "__main__":
    main()
