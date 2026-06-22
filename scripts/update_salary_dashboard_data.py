#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Dashboard Data Builder v1

Input:
- docs/data/retail-salary-benchmark.json
- docs/data/salary-summary.json
- docs/data/salary-role-summary.json

Output:
- docs/data/salary-dashboard-data.json

Feladat:
- Általános kiskereskedelmi bérbenchmark és OSINT vállalati béradatok összefésülése.
- Dashboard-kompatibilis adatfájl készítése.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

BENCHMARK_FILE = DATA_DIR / "retail-salary-benchmark.json"
SALARY_SUMMARY_FILE = DATA_DIR / "salary-summary.json"
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


def coverage_score(company):
    score = 0

    if company.get("salary_record_count", 0) > 0:
        score += 50

    if company.get("raise_record_count", 0) > 0:
        score += 25

    if company.get("sources"):
        score += 25

    return min(score, 100)


def coverage_label(score):
    if score >= 75:
        return "magas"
    if score >= 50:
        return "közepes"
    if score > 0:
        return "alacsony"
    return "nincs adat"


def build_company_cards(summary):
    companies = summary.get("companies", [])

    cards = []

    for company in companies:
        score = coverage_score(company)

        base_min = company.get("physical_worker_base_salary_min_huf_month")
        base_mid = company.get("physical_worker_base_salary_huf_month")
        base_max = company.get("physical_worker_base_salary_max_huf_month")

        cards.append({
            "company_id": company.get("company_id"),
            "company": company.get("company"),
            "status": company.get("status", "unknown"),

            "base_salary_display": format_salary_range(base_min, base_mid, base_max),
            "base_salary_huf_month": base_mid if is_number(base_mid) else NA,

            "highest_salary_display": format_salary(company.get("highest_public_salary_huf_month")),
            "highest_salary_huf_month": (
                company.get("highest_public_salary_huf_month")
                if is_number(company.get("highest_public_salary_huf_month"))
                else NA
            ),

            "salary_raise_pct": company.get("salary_raise_pct", NA),

            "salary_record_count": company.get("salary_record_count", 0),
            "raise_record_count": company.get("raise_record_count", 0),
            "total_record_count": company.get("total_record_count", 0),

            "coverage_score": score,
            "coverage_label": coverage_label(score),

            "confidence": company.get("confidence", 0),
            "notes": company.get("notes", ""),
        })

    return cards


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


def build_benchmark_table(benchmark):
    roles = benchmark.get("roles", [])

    rows = []

    for role in roles:
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


def build_evidence_table(summary):
    rows = []

    for company in summary.get("companies", []):
        for source in company.get("sources", []):
            rows.append({
                "company_id": company.get("company_id"),
                "company": company.get("company"),
                "value_type": source.get("value_type", NA),
                "source_name": source.get("source_name", NA),
                "source_url": source.get("source_url", NA),
                "published_or_found_date": source.get("published_or_found_date", NA),
                "confidence": source.get("confidence", 0),
                "evidence_text": source.get("evidence_text", NA),
            })

    return rows


def build_output():
    benchmark = load_json(BENCHMARK_FILE, {})
    summary = load_json(SALARY_SUMMARY_FILE, {})
    role_summary = load_json(SALARY_ROLE_SUMMARY_FILE, {})

    company_cards = build_company_cards(summary)
    role_matrix = build_role_matrix(role_summary)
    benchmark_table = build_benchmark_table(benchmark)
    evidence_table = build_evidence_table(summary)

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_dashboard_data_v1",
        "input_files": [
            "docs/data/retail-salary-benchmark.json",
            "docs/data/salary-summary.json",
            "docs/data/salary-role-summary.json",
        ],
        "important_note": (
            "Ez a dashboardhoz előkészített béradat. "
            "Az általános bérbenchmark nem vállalatspecifikus adat. "
            "Az OSINT vállalati adatok csak nyilvánosan elérhető forrásokon alapulnak. "
            "A hiányzó adat nem jelent alacsonyabb bérezést."
        ),
        "benchmark": {
            "source": benchmark.get("source", NA),
            "source_type": benchmark.get("source_type", NA),
            "currency": benchmark.get("currency", "HUF"),
            "period": benchmark.get("period", "month"),
            "salary_type": benchmark.get("salary_type", "gross"),
            "rows": benchmark_table,
        },
        "company_cards": company_cards,
        "role_matrix": role_matrix,
        "evidence_table": evidence_table,
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
