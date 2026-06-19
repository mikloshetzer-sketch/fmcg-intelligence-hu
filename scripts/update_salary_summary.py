#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Summary Builder v2

Input:
- docs/data/salary-raw-data.json

Outputs:
- docs/data/salary-summary.json
- docs/data/salary-role-summary.json

Cél:
- A nyers béradatokból dashboard-kompatibilis összefoglaló készítése.
- Külön munkakör szerinti táblázat:
  egy szereplőnél egy munkakörben mennyi a talált bér.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

RAW_FILE = DATA_DIR / "salary-raw-data.json"
SUMMARY_FILE = DATA_DIR / "salary-summary.json"
ROLE_SUMMARY_FILE = DATA_DIR / "salary-role-summary.json"


COMPANIES = [
    {"company_id": "lidl", "company": "Lidl"},
    {"company_id": "aldi", "company": "ALDI"},
    {"company_id": "spar", "company": "SPAR"},
    {"company_id": "tesco", "company": "Tesco"},
    {"company_id": "penny", "company": "PENNY"},
    {"company_id": "auchan", "company": "Auchan"},
]


ROLE_LABELS = {
    "general_worker": "Általános / alapbér",
    "cashier": "Pénztáros",
    "stocker": "Áruházi / bolti dolgozó",
    "bakery_worker": "Pék / pékáru dolgozó",
    "shift_leader": "Műszakvezető",
    "department_manager": "Osztályvezető / részlegvezető",
    "store_manager": "Üzletvezető / áruházvezető",
    "warehouse_worker": "Raktári dolgozó",
    "office_specialist": "Központi / irodai munkakör",
    "unknown": "Nem azonosított munkakör",
}


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


def is_salary_record(record):
    return record.get("value_type") in [
        "salary_huf_month",
        "salary_range_huf_month",
    ]


def is_raise_record(record):
    return record.get("value_type") == "salary_raise_pct"


def normalize_role(record):
    role = record.get("role_key")
    text = (record.get("evidence_text") or "").lower()

    if role:
        return role

    if "alapbér" in text:
        return "general_worker"

    if "fizikai munkát végző" in text:
        return "general_worker"

    if "dolgozó" in text or "munkatárs" in text:
        return "general_worker"

    return "unknown"


def get_salary_value(record):
    return record.get("salary_median_huf_month")


def get_salary_min(record):
    return record.get("salary_min_huf_month")


def get_salary_max(record):
    return record.get("salary_max_huf_month")


def average_confidence(records):
    values = [
        record.get("confidence")
        for record in records
        if isinstance(record.get("confidence"), (int, float))
    ]

    if not values:
        return 0

    return round(sum(values) / len(values))


def collect_sources(records):
    sources = []

    for record in records:
        item = {
            "source_name": record.get("source_name"),
            "source_url": record.get("source_url"),
            "value_type": record.get("value_type"),
            "evidence_text": record.get("evidence_text"),
            "published_or_found_date": record.get("published_or_found_date"),
            "confidence": record.get("confidence"),
        }

        if item not in sources:
            sources.append(item)

    return sources[:10]


def choose_base_salary_record(salary_records):
    if not salary_records:
        return None

    base_candidates = []

    for record in salary_records:
        normalized_role = normalize_role(record)
        text = (record.get("evidence_text") or "").lower()

        if normalized_role in ["general_worker", "stocker"]:
            base_candidates.append(record)
            continue

        if "alapbér" in text or "fizikai munkát végző" in text:
            base_candidates.append(record)
            continue

    candidates = base_candidates if base_candidates else salary_records

    return sorted(
        candidates,
        key=lambda item: (
            get_salary_value(item) or 999999999,
            -(item.get("confidence") or 0),
        ),
    )[0]


def choose_highest_salary_record(salary_records):
    if not salary_records:
        return None

    return sorted(
        salary_records,
        key=lambda item: (
            get_salary_max(item) or 0,
            item.get("confidence") or 0,
        ),
        reverse=True,
    )[0]


def choose_raise_pct(raise_records):
    values = [
        record.get("raise_pct")
        for record in raise_records
        if isinstance(record.get("raise_pct"), (int, float))
    ]

    if not values:
        return None

    return max(values)


def build_company_summary(company_id, company_name, records):
    company_records = [
        record for record in records
        if record.get("company_id") == company_id
    ]

    salary_records = [
        record for record in company_records
        if is_salary_record(record)
    ]

    raise_records = [
        record for record in company_records
        if is_raise_record(record)
    ]

    base_record = choose_base_salary_record(salary_records)
    high_record = choose_highest_salary_record(salary_records)
    salary_raise_pct = choose_raise_pct(raise_records)

    if not company_records:
        status = "no_recent_salary_data"
    elif salary_records and raise_records:
        status = "salary_and_raise_found"
    elif salary_records:
        status = "salary_found"
    elif raise_records:
        status = "raise_only"
    else:
        status = "no_usable_salary_data"

    return {
        "company_id": company_id,
        "company": company_name,
        "status": status,

        "physical_worker_base_salary_huf_month": get_salary_value(base_record) if base_record else None,
        "physical_worker_base_salary_min_huf_month": get_salary_min(base_record) if base_record else None,
        "physical_worker_base_salary_max_huf_month": get_salary_max(base_record) if base_record else None,

        "highest_public_salary_huf_month": get_salary_max(high_record) if high_record else None,
        "highest_public_salary_min_huf_month": get_salary_min(high_record) if high_record else None,
        "highest_public_salary_median_huf_month": get_salary_value(high_record) if high_record else None,

        "salary_raise_pct": salary_raise_pct,

        "salary_record_count": len(salary_records),
        "raise_record_count": len(raise_records),
        "total_record_count": len(company_records),

        "confidence": average_confidence(company_records),

        "base_salary_source": base_record.get("source_name") if base_record else None,
        "base_salary_source_url": base_record.get("source_url") if base_record else None,
        "highest_salary_source": high_record.get("source_name") if high_record else None,
        "highest_salary_source_url": high_record.get("source_url") if high_record else None,

        "sources": collect_sources(company_records),

        "notes": (
            "Nincs friss konkrét béradat."
            if not salary_records
            else "OSINT alapján gyűjtött, nem hivatalos bérinformáció."
        ),
    }


def build_role_summary(records):
    rows = []

    salary_records = [
        record for record in records
        if is_salary_record(record)
    ]

    grouped = {}

    for record in salary_records:
        company_id = record.get("company_id")
        company = record.get("company")
        role_key = normalize_role(record)

        key = (company_id, role_key)

        if key not in grouped:
            grouped[key] = {
                "company_id": company_id,
                "company": company,
                "role_key": role_key,
                "role_label": ROLE_LABELS.get(role_key, role_key),
                "records": [],
            }

        grouped[key]["records"].append(record)

    for item in grouped.values():
        role_records = item["records"]

        min_values = [
            get_salary_min(record)
            for record in role_records
            if isinstance(get_salary_min(record), int)
        ]

        median_values = [
            get_salary_value(record)
            for record in role_records
            if isinstance(get_salary_value(record), int)
        ]

        max_values = [
            get_salary_max(record)
            for record in role_records
            if isinstance(get_salary_max(record), int)
        ]

        best_record = sorted(
            role_records,
            key=lambda record: (
                record.get("confidence") or 0,
                get_salary_value(record) or 0,
            ),
            reverse=True,
        )[0]

        rows.append({
            "company_id": item["company_id"],
            "company": item["company"],
            "role_key": item["role_key"],
            "role_label": item["role_label"],

            "salary_min_huf_month": min(min_values) if min_values else None,
            "salary_median_huf_month": round(sum(median_values) / len(median_values)) if median_values else None,
            "salary_max_huf_month": max(max_values) if max_values else None,

            "record_count": len(role_records),
            "confidence": average_confidence(role_records),

            "source_name": best_record.get("source_name"),
            "source_url": best_record.get("source_url"),
            "published_or_found_date": best_record.get("published_or_found_date"),
            "evidence_text": best_record.get("evidence_text"),

            "notes": "Egy adott szereplő adott munkakörére talált OSINT béradat.",
        })

    rows = sorted(
        rows,
        key=lambda row: (
            row["role_label"],
            -(row["salary_median_huf_month"] or 0),
            row["company"],
        )
    )

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_role_summary_v1_from_salary_raw_data",
        "input_file": "docs/data/salary-raw-data.json",
        "important_note": (
            "Ez munkakör szerinti OSINT bértábla. "
            "Nem hivatalos bérstatisztika. "
            "Egy sor egy szereplő egy munkakörének talált béradata."
        ),
        "rows": rows,
    }


def build_summary():
    raw = load_json(RAW_FILE, {})
    records = raw.get("records", [])

    companies = [
        build_company_summary(
            company_id=item["company_id"],
            company_name=item["company"],
            records=records,
        )
        for item in COMPANIES
    ]

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_summary_v2_from_salary_raw_data",
        "input_file": "docs/data/salary-raw-data.json",
        "important_note": (
            "Ez dashboard-kompatibilis összefoglaló a salary-raw-data.json alapján. "
            "Nem hivatalos bérstatisztika, hanem OSINT alapú indikátor."
        ),
        "companies": companies,
    }


def main():
    print("Salary Summary Builder v2 started.")

    raw = load_json(RAW_FILE, {})
    records = raw.get("records", [])

    summary = build_summary()
    role_summary = build_role_summary(records)

    save_json(SUMMARY_FILE, summary)
    save_json(ROLE_SUMMARY_FILE, role_summary)

    print(f"Saved: {SUMMARY_FILE}")
    print(f"Saved: {ROLE_SUMMARY_FILE}")
    print(f"Companies: {len(summary.get('companies', []))}")
    print(f"Role rows: {len(role_summary.get('rows', []))}")


if __name__ == "__main__":
    main()
