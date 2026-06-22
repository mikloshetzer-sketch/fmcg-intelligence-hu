#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Dashboard Data Builder v2

Input:
- docs/data/retail-salary-benchmark.json
- docs/data/salary-verified-data.json
- docs/data/salary-role-summary.json

Output:
- docs/data/salary-dashboard-data.json
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


def coverage_score(row):
    score = 0

    if row.get("year_status") == "current_2026_salary":
        score += 60
    elif row.get("year_status") == "current_2026_raise_only":
        score += 35
    elif row.get("year_status") in ["older_salary_reference", "dated_reference"]:
        score += 20

    if row.get("sources"):
        score += 25

    if is_number(row.get("confidence")):
        score += min(15, round(row.get("confidence") / 10))

    return min(score, 100)


def coverage_label(score):
    if score >= 75:
        return "magas"
    if score >= 50:
        return "közepes"
    if score > 0:
        return "alacsony"
    return "nincs adat"


def build_company_cards(verified):
    rows = verified.get("rows", [])
    cards = []

    for row in rows:
        score = coverage_score(row)

        cards.append({
            "company_id": row.get("company_id"),
            "company": row.get("company"),
            "status": row.get("verified_status", "unknown"),
            "year_status": row.get("year_status", "no_data"),
            "data_year": row.get("data_year", NA),

            "base_salary_display": row.get("salary_display", NA),
            "base_salary_huf_month": (
                row.get("salary_median_huf_month")
                if is_number(row.get("salary_median_huf_month"))
                else NA
            ),

            "highest_salary_display": format_salary(row.get("salary_max_huf_month")),
            "highest_salary_huf_month": (
                row.get("salary_max_huf_month")
                if is_number(row.get("salary_max_huf_month"))
                else NA
            ),

            "salary_raise_pct": row.get("salary_raise_pct", NA),
            "salary_record_count": 1 if row.get("year_status") == "current_2026_salary" else 0,
            "raise_record_count": 1 if row.get("year_status") == "current_2026_raise_only" else 0,
            "total_record_count": 1 if row.get("year_status") != "no_data" else 0,

            "coverage_score": score,
            "coverage_label": coverage_label(score),
            "confidence": row.get("confidence", 0),

            "primary_source_name": row.get("primary_source_name", NA),
            "primary_source_url": row.get("primary_source_url", NA),
            "notes": row.get("notes", ""),
        })

    return cards


def build_role_matrix(verified, role_summary):
    matrix = []

    verified_rows = {
        row.get("company_id"): row
        for row in verified.get("rows", [])
    }

    role_rows = role_summary.get("rows", [])

    for row in role_rows:
        company_id = row.get("company_id")
        verified_row = verified_rows.get(company_id)

        if verified_row and verified_row.get("company_id") == "aldi":
            for detail in verified_row.get("role_details", []):
                matrix.append({
                    "company_id": "aldi",
                    "company": "ALDI",
                    "role_key": detail.get("role_key"),
                    "role_label": detail.get("role_label"),
                    "salary_display": format_salary_range(
                        detail.get("salary_min_huf_month"),
                        detail.get("salary_after_1_year_huf_month"),
                        detail.get("salary_max_huf_month"),
                    ),
                    "salary_min_huf_month": detail.get("salary_min_huf_month", NA),
                    "salary_median_huf_month": detail.get("salary_after_1_year_huf_month", NA),
                    "salary_max_huf_month": detail.get("salary_max_huf_month", NA),
                    "record_count": 1,
                    "confidence": verified_row.get("confidence", 95),
                    "source_name": verified_row.get("primary_source_name", NA),
                    "source_url": verified_row.get("primary_source_url", NA),
                    "evidence_text": "Ellenőrzött 2026-os ALDI béradat.",
                    "data_year": 2026,
                    "notes": verified_row.get("notes", ""),
                })
            continue

        min_value = row.get("salary_min_huf_month")
        mid_value = row.get("salary_median_huf_month")
        max_value = row.get("salary_max_huf_month")

        matrix.append({
            "company_id": company_id,
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
            "data_year": verified_row.get("data_year", NA) if verified_row else NA,
            "notes": row.get("notes", ""),
        })

    return matrix


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


def build_evidence_table(verified):
    rows = []

    for row in verified.get("rows", []):
        for source in row.get("sources", []):
            if source.get("data_year") != 2026:
                continue

            rows.append({
                "company_id": row.get("company_id"),
                "company": row.get("company"),
                "value_type": source.get("value_type", NA),
                "source_name": source.get("source_name", NA),
                "source_url": source.get("source_url", NA),
                "published_or_found_date": source.get("published_or_found_date", NA),
                "data_year": source.get("data_year", NA),
                "confidence": source.get("confidence", 0),
                "evidence_text": source.get("evidence_text", NA),
            })

    return rows


def build_output():
    benchmark = load_json(BENCHMARK_FILE, {})
    verified = load_json(SALARY_VERIFIED_FILE, {})
    role_summary = load_json(SALARY_ROLE_SUMMARY_FILE, {})

    company_cards = build_company_cards(verified)
    role_matrix = build_role_matrix(verified, role_summary)
    benchmark_table = build_benchmark_table(benchmark)
    evidence_table = build_evidence_table(verified)

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_dashboard_data_v2_from_verified_salary_data",
        "input_files": [
            "docs/data/retail-salary-benchmark.json",
            "docs/data/salary-verified-data.json",
            "docs/data/salary-role-summary.json",
        ],
        "important_note": (
            "Ez a dashboardhoz előkészített béradat. "
            "A vállalati OSINT blokkban elsődlegesen 2026-os, ellenőrzött adatok jelennek meg. "
            "A 2025-ös vagy régebbi adatok csak háttér-referenciák, és nem keverendők a 2026-os bérinformációkkal. "
            "A hiányzó adat nem jelent alacsonyabb bérezést."
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
        "company_cards": company_cards,
        "role_matrix": role_matrix,
        "evidence_table": evidence_table,
        "verified_salary_summary": {
            "current_2026_records": len(verified.get("current_2026", [])),
            "older_reference_records": len(verified.get("older_reference", [])),
            "no_data_records": len(verified.get("no_data", [])),
        },
    }


def main():
    print("Salary Dashboard Data Builder started.")

    output = build_output()
    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Company cards: {len(output.get('company_cards', []))}")
    print(f"Role matrix rows: {len(output.get('role_matrix', []))}")
    print(f"Evidence rows: {len(output.get('evidence_table', []))}")


if __name__ == "__main__":
    main()
