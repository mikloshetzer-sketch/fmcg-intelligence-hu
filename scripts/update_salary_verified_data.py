#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Salary Verified Data Builder v1

Input:
- docs/data/salary-summary.json

Output:
- docs/data/salary-verified-data.json

Feladat:
- A vegyes OSINT béradatok megtisztítása.
- 2026-os, ellenőrzött vállalati adatok külön kezelése.
- Régebbi, de hasznos OSINT béradatok megtartása évjelöléssel.
- N.A. kezelése ott, ahol nincs ellenőrzött adat.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

INPUT_FILE = DATA_DIR / "salary-summary.json"
OUTPUT_FILE = DATA_DIR / "salary-verified-data.json"

COMPANY_ORDER = ["lidl", "aldi", "penny", "spar", "tesco", "auchan"]

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


def parse_year(date_text):
    if not date_text or date_text == NA:
        return None

    try:
        return parsedate_to_datetime(date_text).year
    except Exception:
        pass

    for year in [2026, 2025, 2024]:
        if str(year) in str(date_text):
            return year

    return None


def salary_display(min_value, median_value, max_value):
    if is_number(min_value) and is_number(max_value) and min_value != max_value:
        return f"{min_value:,} - {max_value:,} Ft".replace(",", " ")

    if is_number(median_value):
        return f"{median_value:,} Ft".replace(",", " ")

    if is_number(min_value):
        return f"{min_value:,} Ft".replace(",", " ")

    return NA


def source_year_from_company(company_row):
    years = []

    for source in company_row.get("sources", []):
        year = parse_year(source.get("published_or_found_date"))
        if year:
            years.append(year)

    return max(years) if years else None


def source_list(company_row):
    sources = []

    for source in company_row.get("sources", []):
        sources.append({
            "source_name": source.get("source_name", NA),
            "source_url": source.get("source_url", NA),
            "value_type": source.get("value_type", NA),
            "published_or_found_date": source.get("published_or_found_date", NA),
            "data_year": parse_year(source.get("published_or_found_date")),
            "confidence": source.get("confidence", 0),
            "evidence_text": source.get("evidence_text", NA),
        })

    return sources


def build_from_summary(company_row):
    company_id = company_row.get("company_id")
    company = company_row.get("company")

    data_year = source_year_from_company(company_row)

    min_salary = company_row.get("physical_worker_base_salary_min_huf_month")
    mid_salary = company_row.get("physical_worker_base_salary_huf_month")
    max_salary = company_row.get("physical_worker_base_salary_max_huf_month")

    has_salary = is_number(mid_salary) or is_number(min_salary) or is_number(max_salary)
    has_raise = is_number(company_row.get("salary_raise_pct"))

    if has_salary and has_raise:
        verified_status = "salary_and_raise_found"
    elif has_salary:
        verified_status = "salary_found"
    elif has_raise:
        verified_status = "raise_only"
    else:
        verified_status = "no_verified_salary_data"

    if data_year == 2026 and has_salary:
        year_status = "current_2026_salary"
    elif data_year == 2026 and has_raise:
        year_status = "current_2026_raise_only"
    elif data_year == 2025 and has_salary:
        year_status = "older_salary_reference"
    elif has_salary or has_raise:
        year_status = "dated_reference"
    else:
        year_status = "no_data"

    return {
        "company_id": company_id,
        "company": company,
        "verified_status": verified_status,
        "year_status": year_status,
        "data_year": data_year if data_year else NA,

        "salary_type": "gross_monthly",
        "salary_min_huf_month": min_salary if is_number(min_salary) else NA,
        "salary_median_huf_month": mid_salary if is_number(mid_salary) else NA,
        "salary_max_huf_month": max_salary if is_number(max_salary) else NA,
        "salary_display": salary_display(min_salary, mid_salary, max_salary),

        "salary_raise_pct": company_row.get("salary_raise_pct", NA),
        "confidence": company_row.get("confidence", 0),

        "primary_source_name": company_row.get("base_salary_source", NA),
        "primary_source_url": company_row.get("base_salary_source_url", NA),
        "sources": source_list(company_row),

        "notes": (
            "2026-os adatként csak akkor kezelhető, ha a forrás dátuma 2026-os. "
            "Régebbi béradat esetén a sor csak háttér-referencia."
        ),
    }


def manual_verified_records():
    return [
        {
            "company_id": "aldi",
            "company": "ALDI",
            "verified_status": "salary_found",
            "year_status": "current_2026_salary",
            "data_year": 2026,

            "salary_type": "gross_monthly",
            "salary_min_huf_month": 541900,
            "salary_median_huf_month": 562600,
            "salary_max_huf_month": 750600,
            "salary_display": "541 900 - 750 600 Ft",

            "salary_raise_pct": NA,
            "confidence": 95,

            "primary_source_name": "hvg.hu / ALDI közlés",
            "primary_source_url": "https://hvg.hu/gazdasag/20260105_aldi-fizetes-beremeles-mennyi-2026-januar",

            "sources": [
                {
                    "source_name": "hvg.hu",
                    "source_url": "https://hvg.hu/gazdasag/20260105_aldi-fizetes-beremeles-mennyi-2026-januar",
                    "value_type": "salary_range_huf_month",
                    "published_or_found_date": "2026-01-05",
                    "data_year": 2026,
                    "confidence": 95,
                    "evidence_text": "2026. január 1-jétől az újonnan belépő áruházi dolgozók kezdő bére 541 900 Ft, egy év után 562 600 Ft, a maximum 750 600 Ft."
                },
                {
                    "source_name": "HR Portál",
                    "source_url": "https://www.hrportal.hu/c/beremelesek-az-aldinal-vannak-akik-mar-egymillio-forint-felett-keresnek-majd-20260106.html",
                    "value_type": "salary_range_huf_month",
                    "published_or_found_date": "2026-01-06",
                    "data_year": 2026,
                    "confidence": 90,
                    "evidence_text": "Az ALDI 2026-os béremelése áruházi és logisztikai munkakörökre is konkrét bruttó havi béradatokat közölt."
                }
            ],

            "role_details": [
                {
                    "role_key": "store_worker",
                    "role_label": "Áruházi dolgozó",
                    "salary_min_huf_month": 541900,
                    "salary_after_1_year_huf_month": 562600,
                    "salary_max_huf_month": 750600
                },
                {
                    "role_key": "logistics_worker",
                    "role_label": "Logisztikai dolgozó",
                    "salary_min_huf_month": 600100,
                    "salary_after_1_year_huf_month": 623100,
                    "salary_max_huf_month": 795200
                },
                {
                    "role_key": "store_manager",
                    "role_label": "Áruházvezető",
                    "salary_min_huf_month": 1003500,
                    "salary_max_huf_month": 1549500
                }
            ],

            "notes": "Ellenőrzött 2026-os ALDI béradat. Ez felülírja a salary-summary.json N.A. értékét."
        }
    ]


def build_output():
    summary = load_json(INPUT_FILE, {})
    rows = []

    summary_companies = summary.get("companies", [])

    for company_row in summary_companies:
        rows.append(build_from_summary(company_row))

    manual_rows = manual_verified_records()

    rows_by_company = {row["company_id"]: row for row in rows}

    for manual in manual_rows:
        rows_by_company[manual["company_id"]] = manual

    ordered_rows = []

    for company_id in COMPANY_ORDER:
        if company_id in rows_by_company:
            ordered_rows.append(rows_by_company[company_id])

    for company_id, row in rows_by_company.items():
        if company_id not in COMPANY_ORDER:
            ordered_rows.append(row)

    current_2026 = [
        row for row in ordered_rows
        if row.get("year_status") in ["current_2026_salary", "current_2026_raise_only"]
    ]

    older_reference = [
        row for row in ordered_rows
        if row.get("year_status") in ["older_salary_reference", "dated_reference"]
    ]

    no_data = [
        row for row in ordered_rows
        if row.get("year_status") == "no_data"
    ]

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_verified_data_v1_cleaned_2026_priority",
        "input_file": "docs/data/salary-summary.json",
        "output_file": "docs/data/salary-verified-data.json",
        "important_note": (
            "Ez tisztított béradat-réteg. A 2026-os adatok elsőbbséget kapnak. "
            "A 2025-ös vagy korábbi adatok háttér-referenciaként maradnak meg. "
            "Ahol nincs ellenőrzött adat, ott N.A. szerepel."
        ),
        "summary": {
            "companies_total": len(ordered_rows),
            "current_2026_records": len(current_2026),
            "older_reference_records": len(older_reference),
            "no_data_records": len(no_data),
        },
        "current_2026": current_2026,
        "older_reference": older_reference,
        "no_data": no_data,
        "rows": ordered_rows,
    }


def main():
    print("Salary Verified Data Builder started.")

    output = build_output()

    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
