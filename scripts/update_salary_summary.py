#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Summary Builder v1

Input:
- docs/data/salary-raw-data.json

Output:
- docs/data/salary-summary.json

Cél:
- A nyers OSINT béradatokból dashboard-kompatibilis összefoglaló készítése.
- Nem gyűjt új adatot.
- Nem módosítja a salaries.json fájlt.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

RAW_FILE = DATA_DIR / "salary-raw-data.json"
SUMMARY_FILE = DATA_DIR / "salary-summary.json"


COMPANIES = [
    {"company_id": "lidl", "company": "Lidl"},
    {"company_id": "aldi", "company": "ALDI"},
    {"company_id": "spar", "company": "SPAR"},
    {"company_id": "tesco", "company": "Tesco"},
    {"company_id": "penny", "company": "PENNY"},
    {"company_id": "auchan", "company": "Auchan"},
]


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


def get_salary_value(record):
    return record.get("salary_median_huf_month")


def get_salary_min(record):
    return record.get("salary_min_huf_month")


def get_salary_max(record):
    return record.get("salary_max_huf_month")


def choose_base_salary_record(salary_records):
    if not salary_records:
        return None

    base_candidates = []

    for record in salary_records:
        text = (record.get("evidence_text") or "").lower()
        role = record.get("role_key")

        if role == "stocker":
            base_candidates.append(record)
            continue

        if "alapbér" in text:
            base_candidates.append(record)
            continue

        if "fizikai munkát végző" in text:
            base_candidates.append(record)
            continue

        if "dolgozó" in text or "munkatárs" in text:
            base_candidates.append(record)
            continue

    if base_candidates:
        return sorted(
            base_candidates,
            key=lambda item: (
                get_salary_value(item) or 999999999,
                -(item.get("confidence") or 0),
            ),
        )[0]

    return sorted(
        salary_records,
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
        source_name = record.get("source_name")
        source_url = record.get("source_url")

        if not source_name and not source_url:
            continue

        item = {
            "source_name": source_name,
            "source_url": source_url,
            "value_type": record.get("value_type"),
            "evidence_text": record.get("evidence_text"),
            "published_or_found_date": record.get("published_or_found_date"),
            "confidence": record.get("confidence"),
        }

        if item not in sources:
            sources.append(item)

    return sources[:10]


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
        "method": "salary_summary_v1_from_salary_raw_data",
        "input_file": "docs/data/salary-raw-data.json",
        "important_note": (
            "Ez dashboard-kompatibilis összefoglaló a salary-raw-data.json alapján. "
            "Nem hivatalos bérstatisztika, hanem OSINT alapú indikátor."
        ),
        "companies": companies,
    }


def main():
    print("Salary Summary Builder started.")

    summary = build_summary()

    save_json(SUMMARY_FILE, summary)

    print(f"Saved: {SUMMARY_FILE}")
    print(f"Companies: {len(summary.get('companies', []))}")


if __name__ == "__main__":
    main()
