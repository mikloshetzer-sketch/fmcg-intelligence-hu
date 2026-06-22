#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

BENCHMARK_FILE = DATA_DIR / "retail-salary-benchmark.json"
SALARY_VERIFIED_FILE = DATA_DIR / "salary-verified-data.json"
OUTPUT_FILE = DATA_DIR / "salary-dashboard-data.json"

NA = "N.A."


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_number(v):
    return isinstance(v, (int, float))


def format_salary(v):
    if not is_number(v):
        return NA
    return f"{int(v):,}".replace(",", " ") + " Ft"


def format_salary_range(min_v=None, mid_v=None, max_v=None):
    if is_number(min_v) and is_number(max_v) and min_v != max_v:
        return f"{format_salary(min_v)} - {format_salary(max_v)}"
    if is_number(mid_v):
        return format_salary(mid_v)
    if is_number(min_v):
        return format_salary(min_v)
    if is_number(max_v):
        return format_salary(max_v)
    return NA


def source(company_id):
    sources = {
        "aldi": ("ALDI sajtóközlemény", "https://www.aldi.hu/az-aldirol/sajtoszoba/sajtokozlemenyek/koezlemenyek-2026/beremeles-az-aldi-nal--minden-pozicioban-noevekedes", "official_company", "Hivatalos vállalati közlés", 100),
        "lidl": ("Lidl sajtóközlemény", "https://vallalat.lidl.hu/sajtoszoba/sajtokoezlemenyek/20260420_berfejlesztes", "official_company", "Hivatalos vállalati közlés", 100),
        "auchan": ("Auchan sajtóközlemény", "https://auchan.hu/sajtokozlemenyek/2026-beremeles", "official_company", "Hivatalos vállalati közlés", 100),
        "tesco": ("Tesco vállalati közlés", "https://corporate.tesco.hu/beremeles-2026", "official_company", "Hivatalos vállalati közlés", 100),
        "penny": ("PENNY vállalati közlés", "https://www.penny.hu/tovabbi-3-4-milliard-forintot-fordit-berfejlesztesre-a-penny", "official_company", "Hivatalos vállalati közlés", 100),
        "spar": ("WhereWeWork referencia", "https://www.wherewework.hu/hu/fizetesek-spar-magyarorszag-minden-a-munkakornyezetrol-ertekeles-fizetes-allasinterjuk-juttatasok-234", "secondary_reference", "Másodlagos referenciaforrás", 70),
    }

    name, url, quality, label, confidence = sources.get(
        company_id,
        (NA, NA, NA, NA, 0)
    )

    return {
        "source_name": name,
        "source_url": url,
        "source_quality": quality,
        "source_label": label,
        "confidence": confidence,
    }


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


def salary_intelligence_cards():
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
                "logisztikai béradatok",
            ],
            **source("aldi"),
            "source_priority": 100,
            "data_year": 2026,
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
                "maximális jövedelmi szintek",
            ],
            **source("lidl"),
            "source_priority": 100,
            "data_year": 2026,
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
                "cukrász munkakör",
                "logisztikai munkakörök",
            ],
            **source("auchan"),
            "source_priority": 100,
            "data_year": 2026,
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
                "juttatási elemek",
            ],
            **source("tesco"),
            "source_priority": 100,
            "data_year": 2026,
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
                "rugalmas juttatási rendszer",
            ],
            **source("penny"),
            "source_priority": 100,
            "data_year": 2026,
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
                "hivatalos 2026-os közlés nem azonosítható",
            ],
            **source("spar"),
            "source_priority": 70,
            "data_year": 2026,
        },
    ]


def build_salary_intelligence_summary(cards):
    return {
        "detailed_structure": sum(1 for c in cards if c["information_depth"] == "detailed_structure"),
        "partial_information": sum(1 for c in cards if c["information_depth"] == "partial_information"),
        "reference_only": sum(1 for c in cards if c["information_depth"] == "reference_only"),
        "official_sources": sum(1 for c in cards if c["source_quality"] == "official_company"),
        "companies_total": len(cards),
    }


def build_company_cards(cards):
    out = []

    for card in cards:
        depth = card["information_depth"]

        if depth == "detailed_structure":
            status = "current_2026_salary"
            score = 100
            label = "magas"
            salary_count = 1
            raise_count = 0
        elif depth == "partial_information":
            status = "current_2026_partial"
            score = 75
            label = "közepes"
            salary_count = 0
            raise_count = 1
        elif depth == "reference_only":
            status = "reference_only"
            score = 40
            label = "referencia"
            salary_count = 0
            raise_count = 0
        else:
            status = "no_data"
            score = 0
            label = "nincs adat"
            salary_count = 0
            raise_count = 0

        out.append({
            "company_id": card["company_id"],
            "company": card["company"],
            "status": status,
            "year_status": depth,
            "data_year": 2026,
            "base_salary_display": card["headline"],
            "base_salary_huf_month": NA,
            "highest_salary_display": card["headline"],
            "highest_salary_huf_month": NA,
            "salary_raise_pct": NA,
            "salary_record_count": salary_count,
            "raise_record_count": raise_count,
            "total_record_count": 1,
            "coverage_score": score,
            "coverage_label": label,
            "confidence": card["confidence"],
            "primary_source_name": card["source_name"],
            "primary_source_url": card["source_url"],
            "source_quality": card["source_quality"],
            "source_label": card["source_label"],
            "source_priority": card["source_priority"],
            "information_depth": card["information_depth"],
            "information_depth_label": card["information_depth_label"],
            "information_items": card["information_items"],
            "subheadline": card["subheadline"],
            "notes": "2026 Salary Intelligence kártya. A rendszer azt is mutatja, milyen mélységű információt sikerült beszerezni.",
        })

    return out


def add_role(
    rows,
    company_id,
    company,
    role_key,
    role_label,
    min_v=None,
    mid_v=None,
    max_v=None,
    info_display=None,
    evidence_text="",
    notes="2026 Salary Intelligence role matrix sor.",
):
    src = source(company_id)

    salary_display = format_salary_range(min_v, mid_v, max_v)

    if salary_display == NA and info_display:
        salary_display = info_display

    has_numeric = is_number(min_v) or is_number(mid_v) or is_number(max_v)

    rows.append({
        "company_id": company_id,
        "company": company,
        "role_key": role_key,
        "role_label": role_label,
        "salary_display": salary_display,
        "salary_min_huf_month": min_v if is_number(min_v) else NA,
        "salary_median_huf_month": mid_v if is_number(mid_v) else NA,
        "salary_max_huf_month": max_v if is_number(max_v) else NA,
        "information_display": info_display if info_display else salary_display,
        "information_type": "salary_range" if has_numeric else "salary_information",
        "record_count": 1 if has_numeric or info_display else 0,
        "confidence": src["confidence"],
        "source_name": src["source_name"],
        "source_url": src["source_url"],
        "source_quality": src["source_quality"],
        "source_label": src["source_label"],
        "data_year": 2026,
        "evidence_text": evidence_text,
        "notes": notes,
    })


def build_role_matrix():
    rows = []

    add_role(rows, "aldi", "ALDI", "stocker", "Áruházi / bolti dolgozó", 541900, 562600, 750600, evidence_text="Áruházi dolgozó: kezdő bér, 1 év utáni bér és maximális bér azonosítva.")
    add_role(rows, "aldi", "ALDI", "warehouse_worker", "Raktári / logisztikai dolgozó", 600100, 623100, 795200, evidence_text="Logisztikai dolgozó: kezdő bér, 1 év utáni bér és maximális bér azonosítva.")
    add_role(rows, "aldi", "ALDI", "store_manager", "Üzletvezető / vezetői munkakör", 1003500, None, 1549500, evidence_text="Áruházvezetői bérsáv azonosítva.")

    add_role(rows, "lidl", "Lidl", "stocker", "Áruházi / bolti dolgozó", 599000, None, 700000, evidence_text="Bolti dolgozói kezdő bér és 700 ezer Ft feletti elérhető szint azonosítva.")
    add_role(rows, "lidl", "Lidl", "store_manager", "Üzletvezető / vezetői munkakör", 1104000, None, 1349000, evidence_text="Üzletvezetői bérsáv azonosítva.")
    add_role(rows, "lidl", "Lidl", "warehouse_worker", "Raktári / logisztikai dolgozó", info_display="logisztikai bérek említve", evidence_text="Logisztikai bérek említve, de pontos bérsáv nem került rögzítésre.", notes="2026-os hivatalos közlés alapján részleges munkaköri információ.")

    add_role(rows, "auchan", "Auchan", "stocker", "Áruházi / fizikai munkakör", info_display="9,2%-os éves béremelés", evidence_text="9,2%-os éves béremelés és fizikai munkakörök érintettsége azonosítva.", notes="2026-os hivatalos Auchan közlés alapján béremelési információ.")
    add_role(rows, "auchan", "Auchan", "bakery_butcher", "Pék / hentes / cukrász", info_display="érintett munkakör", evidence_text="Pék, hentes és cukrász munkakörök érintettsége azonosítva.", notes="2026-os hivatalos Auchan közlés alapján munkaköri információ.")
    add_role(rows, "auchan", "Auchan", "warehouse_worker", "Raktári / logisztikai dolgozó", info_display="logisztikai munkakör érintett", evidence_text="Logisztikai munkakörök érintettsége azonosítva.", notes="2026-os hivatalos Auchan közlés alapján részleges információ.")

    add_role(rows, "tesco", "Tesco", "stocker", "Áruházi / bolti dolgozó", 418000, None, 562000, evidence_text="8 órás áruházi alapbér és maximálisan elérhető bruttó jövedelem azonosítva.")
    add_role(rows, "tesco", "Tesco", "general_raise", "Átlagos béremelés", info_display="+7,2% béremelés", evidence_text="7,2%-os átlagos béremelés azonosítva.", notes="2026-os hivatalos közlés alapján béremelési információ.")

    add_role(rows, "penny", "PENNY", "sales_logistics_raise", "Értékesítés és logisztika", info_display="+8% béremelés", evidence_text="Átlagosan 8%-os béremelés az értékesítési és logisztikai területen.", notes="2026-os hivatalos közlés alapján béremelési információ.")
    add_role(rows, "penny", "PENNY", "office_raise", "Központi terület", info_display="+6% béremelés", evidence_text="Átlagosan 6%-os béremelés a központi területen.", notes="2026-os hivatalos közlés alapján béremelési információ.")

    add_role(rows, "spar", "SPAR", "reference_salary", "Referencia bérinformáció", info_display="nincs hivatalos 2026-os bérközlés", evidence_text="Hivatalos 2026-os bérközlés nem azonosítható; másodlagos referenciaforrás használható.", notes="Nem hivatalos, referencia szintű adat.")

    return rows


def build_evidence_table(cards):
    rows = []

    for card in cards:
        rows.append({
            "company_id": card["company_id"],
            "company": card["company"],
            "value_type": card["information_depth"],
            "source_name": card["source_name"],
            "source_url": card["source_url"],
            "published_or_found_date": "2026",
            "data_year": 2026,
            "confidence": card["confidence"],
            "source_quality": card["source_quality"],
            "source_label": card["source_label"],
            "evidence_text": "; ".join(card["information_items"]),
        })

    return rows


def build_output():
    benchmark = load_json(BENCHMARK_FILE, {})
