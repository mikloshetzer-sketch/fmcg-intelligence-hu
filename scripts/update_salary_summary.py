#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Summary Builder v5

Input:
- docs/data/salary-raw-data.json

Outputs:
- docs/data/salary-summary.json
- docs/data/salary-role-summary.json

Feladat:
- Cégszintű összesítő készítése.
- Munkakör × szereplő mátrix készítése.
- Ahol nincs adat, ott "N.A." szerepel.
- Az ismeretlen, de értékes béradatokat nem dobja el.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

RAW_FILE = DATA_DIR / "salary-raw-data.json"
SUMMARY_FILE = DATA_DIR / "salary-summary.json"
ROLE_SUMMARY_FILE = DATA_DIR / "salary-role-summary.json"

NA = "N.A."


COMPANIES = [
    {"company_id": "lidl", "company": "Lidl"},
    {"company_id": "aldi", "company": "ALDI"},
    {"company_id": "penny", "company": "PENNY"},
    {"company_id": "spar", "company": "SPAR"},
    {"company_id": "tesco", "company": "Tesco"},
    {"company_id": "auchan", "company": "Auchan"},
]


ROLE_ORDER = [
    {"role_key": "stocker", "role_label": "Áruházi / bolti dolgozó"},
    {"role_key": "store_manager", "role_label": "Üzletvezető / vezetői munkakör"},
    {"role_key": "warehouse_worker", "role_label": "Raktári dolgozó"},
    {"role_key": "cashier", "role_label": "Pénztáros"},
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
    return record.get("value_type") in ["salary_huf_month", "salary_range_huf_month"]


def is_raise_record(record):
    return record.get("value_type") == "salary_raise_pct"


def normalize_role(record):
    role = record.get("role_key")
    text = (record.get("evidence_text") or "").lower()

    if role in ["stocker", "store_manager", "warehouse_worker", "cashier"]:
        return role

    if "pénztáros" in text or "kasszás" in text or "kassza" in text:
        return "cashier"

    if "raktár" in text or "raktáros" in text or "logisztikai" in text or "targoncavezető" in text:
        return "warehouse_worker"

    if (
        "üzletvezető" in text
        or "áruházvezető" in text
        or "boltvezető" in text
        or "vezető" in text
        or "vezetői" in text
        or "vezetőket" in text
    ):
        return "store_manager"

    if (
        "kereshetnek" in text
        or "kereshet" in text
        or "lehet majd keresni" in text
        or "kik kereshetnek" in text
    ):
        salary = get_salary_value(record)
        if isinstance(salary, int) and salary >= 650000:
            return "store_manager"

    if (
        "alapbér" in text
        or "fizikai munkát végző" in text
        or "dolgozó" in text
        or "munkatárs" in text
        or "üzleteiben" in text
        or "áruházi" in text
        or "bolti" in text
    ):
        return "stocker"

    return "stocker"


def get_salary_value(record):
    return record.get("salary_median_huf_month")


def get_salary_min(record):
    return record.get("salary_min_huf_month")


def get_salary_max(record):
    return record.get("salary_max_huf_month")


def safe_value(value):
    return NA if value is None else value


def average_confidence(records):
    values = [
        record.get("confidence")
        for record in records
        if isinstance(record.get("confidence"), (int, float))
    ]
    return round(sum(values) / len(values)) if values else 0


def collect_sources(records):
    sources = []

    for record in records:
        item = {
            "source_name": record.get("source_name") or NA,
            "source_url": record.get("source_url") or NA,
            "value_type": record.get("value_type") or NA,
            "evidence_text": record.get("evidence_text") or NA,
            "published_or_found_date": record.get("published_or_found_date") or NA,
            "confidence": record.get("confidence") if record.get("confidence") is not None else 0,
        }

        if item not in sources:
            sources.append(item)

    return sources[:10]


def choose_base_salary_record(salary_records):
    if not salary_records:
        return None

    base_candidates = []

    for record in salary_records:
        role = normalize_role(record)
        text = (record.get("evidence_text") or "").lower()

        if role == "stocker":
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
    return max(values) if values else None


def build_company_summary(company_id, company_name, records):
    company_records = [r for r in records if r.get("company_id") == company_id]
    salary_records = [r for r in company_records if is_salary_record(r)]
    raise_records = [r for r in company_records if is_raise_record(r)]

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
        "physical_worker_base_salary_huf_month": safe_value(get_salary_value(base_record) if base_record else None),
        "physical_worker_base_salary_min_huf_month": safe_value(get_salary_min(base_record) if base_record else None),
        "physical_worker_base_salary_max_huf_month": safe_value(get_salary_max(base_record) if base_record else None),
        "highest_public_salary_huf_month": safe_value(get_salary_max(high_record) if high_record else None),
        "highest_public_salary_min_huf_month": safe_value(get_salary_min(high_record) if high_record else None),
        "highest_public_salary_median_huf_month": safe_value(get_salary_value(high_record) if high_record else None),
        "salary_raise_pct": safe_value(salary_raise_pct),
        "salary_record_count": len(salary_records),
        "raise_record_count": len(raise_records),
        "total_record_count": len(company_records),
        "confidence": average_confidence(company_records),
        "base_salary_source": base_record.get("source_name") if base_record else NA,
        "base_salary_source_url": base_record.get("source_url") if base_record else NA,
        "highest_salary_source": high_record.get("source_name") if high_record else NA,
        "highest_salary_source_url": high_record.get("source_url") if high_record else NA,
        "sources": collect_sources(company_records),
        "notes": (
            "Jelenleg nincs elérhető OSINT béradat."
            if not salary_records
            else "OSINT alapján gyűjtött, nem hivatalos bérinformáció."
        ),
    }


def best_record_for_company_role(records, company_id, role_key):
    candidates = []

    for record in records:
        if record.get("company_id") != company_id:
            continue
        if not is_salary_record(record):
            continue
        if normalize_role(record) != role_key:
            continue
        candidates.append(record)

    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda record: (
            record.get("confidence") or 0,
            get_salary_value(record) or 0,
        ),
        reverse=True,
    )[0]


def build_role_summary(records):
    rows = []

    for role in ROLE_ORDER:
        role_key = role["role_key"]
        role_label = role["role_label"]

        for company in COMPANIES:
            company_id = company["company_id"]
            company_name = company["company"]

            record = best_record_for_company_role(records, company_id, role_key)

            if record:
                rows.append({
                    "company_id": company_id,
                    "company": company_name,
                    "role_key": role_key,
                    "role_label": role_label,
                    "salary_min_huf_month": safe_value(get_salary_min(record)),
                    "salary_median_huf_month": safe_value(get_salary_value(record)),
                    "salary_max_huf_month": safe_value(get_salary_max(record)),
                    "record_count": 1,
                    "confidence": record.get("confidence") or 0,
                    "source_name": record.get("source_name") or NA,
                    "source_url": record.get("source_url") or NA,
                    "published_or_found_date": record.get("published_or_found_date") or NA,
                    "evidence_text": record.get("evidence_text") or NA,
                    "notes": "Egy adott szereplő adott munkakörére talált OSINT béradat.",
                })
            else:
                rows.append({
                    "company_id": company_id,
                    "company": company_name,
                    "role_key": role_key,
                    "role_label": role_label,
                    "salary_min_huf_month": NA,
                    "salary_median_huf_month": NA,
                    "salary_max_huf_month": NA,
                    "record_count": 0,
                    "confidence": 0,
                    "source_name": NA,
                    "source_url": NA,
                    "published_or_found_date": NA,
                    "evidence_text": NA,
                    "notes": "Jelenleg nincs elérhető OSINT béradat.",
                })

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_role_summary_v3_compact_matrix_with_na",
        "input_file": "docs/data/salary-raw-data.json",
        "important_note": (
            "Ez munkakör szerinti OSINT bértábla. "
            "Nem hivatalos bérstatisztika. "
            "Ahol nincs adat, ott N.A. szerepel."
        ),
        "companies": COMPANIES,
        "roles": ROLE_ORDER,
        "rows": rows,
    }


def build_summary(records):
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
        "method": "salary_summary_v5_from_salary_raw_data_with_na",
        "input_file": "docs/data/salary-raw-data.json",
        "important_note": (
            "Ez dashboard-kompatibilis összefoglaló a salary-raw-data.json alapján. "
            "Nem hivatalos bérstatisztika. Ahol nincs adat, ott N.A. szerepel."
        ),
        "companies": companies,
    }


def main():
    print("Salary Summary Builder v5 started.")

    raw = load_json(RAW_FILE, {})
    records = raw.get("records", [])

    summary = build_summary(records)
    role_summary = build_role_summary(records)

    save_json(SUMMARY_FILE, summary)
    save_json(ROLE_SUMMARY_FILE, role_summary)

    print(f"Saved: {SUMMARY_FILE}")
    print(f"Saved: {ROLE_SUMMARY_FILE}")
    print(f"Companies: {len(summary.get('companies', []))}")
    print(f"Role rows: {len(role_summary.get('rows', []))}")


if __name__ == "__main__":
    main()
