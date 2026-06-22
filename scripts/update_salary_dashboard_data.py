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
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    name, url, quality, label, confidence = sources.get(company_id, (NA, NA, NA, NA, 0))
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
    data = [
        ("aldi", "ALDI", "541 900 - 750 600 Ft", "Részletes 2026-os bérstruktúra.", "detailed_structure", "Részletes bérstruktúra",
         ["áruházi dolgozó kezdő bér", "1 év utáni bér", "maximális áruházi bér", "logisztikai béradatok"]),
        ("lidl", "Lidl", "599 000 - 700 000+ Ft", "Több munkakörre vonatkozó 2026-os bérinformáció.", "detailed_structure", "Részletes bérstruktúra",
         ["bolti dolgozó bére", "üzletvezetői bérek", "logisztikai bérek", "maximális jövedelmi szintek"]),
        ("auchan", "Auchan", "9,2%-os éves béremelés", "Fizikai munkaköröket érintő 2026-os bérinformáció.", "partial_information", "Részleges bérinformáció",
         ["kétlépcsős béremelés", "pék munkakör", "hentes munkakör", "cukrász munkakör", "logisztikai munkakörök"]),
        ("tesco", "Tesco", "+7,2% béremelés", "2026-os béremelési és alapbér-információ.", "partial_information", "Részleges bérinformáció",
         ["átlagos béremelés", "áruházi alapbér", "maximális elérhető jövedelem", "juttatási elemek"]),
        ("penny", "PENNY", "+8% béremelés", "Értékesítési és logisztikai területet érintő 2026-os béremelés.", "partial_information", "Részleges bérinformáció",
         ["értékesítési béremelés", "logisztikai béremelés", "központi béremelés", "rugalmas juttatási rendszer"]),
        ("spar", "SPAR", "Nincs hivatalos 2026-os bérközlés", "Csak referencia szintű információ áll rendelkezésre.", "reference_only", "Referencia szintű információ",
         ["általános piaci bérinformáció", "dolgozói önbevallásos referencia", "hivatalos 2026-os közlés nem azonosítható"]),
    ]

    cards = []
    for company_id, company, headline, subheadline, depth, depth_label, items in data:
        src = source(company_id)
        cards.append({
            "company_id": company_id,
            "company": company,
            "headline": headline,
            "subheadline": subheadline,
            "information_depth": depth,
            "information_depth_label": depth_label,
            "information_items": items,
            **src,
            "source_priority": src["confidence"],
            "data_year": 2026,
        })
    return cards


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
            status, score, label, salary_count, raise_count = "current_2026_salary", 100, "magas", 1, 0
        elif depth == "partial_information":
            status, score, label, salary_count, raise_count = "current_2026_partial", 75, "közepes", 0, 1
        elif depth == "reference_only":
            status, score, label, salary_count, raise_count = "reference_only", 40, "referencia", 0, 0
        else:
            status, score, label, salary_count, raise_count = "no_data", 0, "nincs adat", 0, 0

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
            "notes": "2026 Salary Intelligence kártya.",
        })
    return out


def add_role(rows, company_id, company, role_key, role_label,
             min_v=None, mid_v=None, max_v=None, info_display=None,
             evidence_text="", notes="2026 Salary Intelligence role matrix sor."):
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

    add_role(rows, "aldi", "ALDI", "stocker", "Áruházi / bolti dolgozó", 541900, 562600, 750600,
             evidence_text="Áruházi dolgozó: kezdő bér, 1 év utáni bér és maximális bér azonosítva.")
    add_role(rows, "aldi", "ALDI", "warehouse_worker", "Raktári / logisztikai dolgozó", 600100, 623100, 795200,
             evidence_text="Logisztikai dolgozó: kezdő bér, 1 év utáni bér és maximális bér azonosítva.")
    add_role(rows, "aldi", "ALDI", "store_manager", "Üzletvezető / vezetői munkakör", 1003500, None, 1549500,
             evidence_text="Áruházvezetői bérsáv azonosítva.")

    add_role(rows, "lidl", "Lidl", "stocker", "Áruházi / bolti dolgozó", 599000, None, 700000,
             evidence_text="Bolti dolgozói kezdő bér és 700 ezer Ft feletti elérhető szint azonosítva.")
    add_role(rows, "lidl", "Lidl", "store_manager", "Üzletvezető / vezetői munkakör", 1104000, None, 1349000,
             evidence_text="Üzletvezetői bérsáv azonosítva.")
    add_role(rows, "lidl", "Lidl", "warehouse_worker", "Raktári / logisztikai dolgozó",
             info_display="logisztikai bérek említve",
             evidence_text="Logisztikai bérek említve, de pontos bérsáv nem került rögzítésre.",
             notes="2026-os hivatalos közlés alapján részleges munkaköri információ.")

    add_role(rows, "auchan", "Auchan", "stocker", "Áruházi / fizikai munkakör",
             info_display="9,2%-os éves béremelés",
             evidence_text="9,2%-os éves béremelés és fizikai munkakörök érintettsége azonosítva.")
    add_role(rows, "auchan", "Auchan", "bakery_butcher", "Pék / hentes / cukrász",
             info_display="érintett munkakör",
             evidence_text="Pék, hentes és cukrász munkakörök érintettsége azonosítva.")
    add_role(rows, "auchan", "Auchan", "warehouse_worker", "Raktári / logisztikai dolgozó",
             info_display="logisztikai munkakör érintett",
             evidence_text="Logisztikai munkakörök érintettsége azonosítva.")

    add_role(rows, "tesco", "Tesco", "stocker", "Áruházi / bolti dolgozó", 418000, None, 562000,
             evidence_text="8 órás áruházi alapbér és maximálisan elérhető bruttó jövedelem azonosítva.")
    add_role(rows, "tesco", "Tesco", "general_raise", "Átlagos béremelés",
             info_display="+7,2% béremelés",
             evidence_text="7,2%-os átlagos béremelés azonosítva.")

    add_role(rows, "penny", "PENNY", "sales_logistics_raise", "Értékesítés és logisztika",
             info_display="+8% béremelés",
             evidence_text="Átlagosan 8%-os béremelés az értékesítési és logisztikai területen.")
    add_role(rows, "penny", "PENNY", "office_raise", "Központi terület",
             info_display="+6% béremelés",
             evidence_text="Átlagosan 6%-os béremelés a központi területen.")

    add_role(rows, "spar", "SPAR", "reference_salary", "Referencia bérinformáció",
             info_display="nincs hivatalos 2026-os bérközlés",
             evidence_text="Hivatalos 2026-os bérközlés nem azonosítható; másodlagos referenciaforrás használható.",
             notes="Nem hivatalos, referencia szintű adat.")

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
    verified = load_json(SALARY_VERIFIED_FILE, {})
    cards = salary_intelligence_cards()

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "method": "salary_dashboard_data_v5_2026_salary_information_display_fix",
        "input_files": [
            "docs/data/retail-salary-benchmark.json",
            "docs/data/salary-verified-data.json",
        ],
        "important_note": (
            "Ez a dashboardhoz előkészített 2026 Salary Intelligence adat. "
            "Ahol nincs konkrét havi bérösszeg, de van hivatalos 2026-os béremelési információ, "
            "ott a role_matrix szövegesen jeleníti meg a megszerzett információt."
        ),
        "benchmark": {
            "source": benchmark.get("source", NA),
            "source_type": benchmark.get("source_type", NA),
            "currency": benchmark.get("currency", "HUF"),
            "period": benchmark.get("period", "month"),
            "salary_type": benchmark.get("salary_type", "gross"),
            "data_year": 2026,
            "rows": build_benchmark_table(benchmark),
        },
        "salary_intelligence_cards": cards,
        "salary_intelligence_summary": build_salary_intelligence_summary(cards),
        "company_cards": build_company_cards(cards),
        "role_matrix": build_role_matrix(),
        "evidence_table": build_evidence_table(cards),
        "verified_salary_summary": verified.get("summary", {}),
    }


def main():
    output = build_output()
    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Method: {output.get('method')}")
    print(f"Role matrix rows: {len(output.get('role_matrix', []))}")


if __name__ == "__main__":
    main()
