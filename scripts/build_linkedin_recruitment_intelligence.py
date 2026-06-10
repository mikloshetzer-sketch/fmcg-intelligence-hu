import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

INPUT_FILE = DATA_DIR / "linkedin-jobs-monitor.json"
OUTPUT_FILE = DATA_DIR / "linkedin-recruitment-intelligence.json"

COMPANY_CONTEXT = {
    "auchan": {"stores": 24, "dc": 1},
    "lidl": {"stores": 220, "dc": 4},
    "aldi": {"stores": 188, "dc": 3},
    "spar": {"stores": 520, "dc": 7},
    "tesco": {"stores": 182, "dc": 4},
    "penny": {"stores": 242, "dc": 4},
}

FOCUS_LABELS = {
    "store": "Bolti működés",
    "warehouse": "Logisztika / raktár",
    "management": "Vezetői toborzás",
    "office": "Központi funkciók",
    "expansion": "Expanziós jel",
}

def clamp(value, low=0, high=100):
    return max(low, min(high, round(value)))

def safe_int(value):
    if isinstance(value, int):
        return value
    return 0

def get_focus(scores):
    if not scores:
        return "Gyenge jel"
    key = max(scores, key=lambda k: scores.get(k, 0))
    if scores.get(key, 0) <= 0:
        return "Gyenge jel"
    return FOCUS_LABELS.get(key, key)

def signal_level(score):
    if score >= 75:
        return "ERŐS"
    if score >= 55:
        return "KÖZEPES"
    if score >= 35:
        return "GYENGE-KÖZEPES"
    return "GYENGE"

def build_company(item):
    cid = item.get("id")
    company = item.get("company", cid)
    scores = item.get("category_scores", {}) or {}
    ads = item.get("linkedin_active_ads_hint")

    store = safe_int(scores.get("store"))
    warehouse = safe_int(scores.get("warehouse"))
    management = safe_int(scores.get("management"))
    office = safe_int(scores.get("office"))
    expansion = safe_int(scores.get("expansion"))

    context = COMPANY_CONTEXT.get(cid, {"stores": 0, "dc": 0})
    stores = context["stores"]
    dc = context["dc"]

    ads_score = min(40, safe_int(ads) * 2) if isinstance(ads, int) else 8
    category_score = store * 5 + warehouse * 7 + management * 6 + office * 5 + expansion * 12
    confidence_bonus = 8 if item.get("source_confidence") == "medium" else 0

    recruitment_pressure = clamp(ads_score + category_score + confidence_bonus)

    logistics_pressure = clamp(warehouse * 18 + (stores / max(dc, 1)) * 0.15)
    management_pressure = clamp(management * 20 + office * 8)
    store_pressure = clamp(store * 20 + safe_int(ads) * 1.2 if isinstance(ads, int) else store * 20)

    expansion_signal = clamp(
        expansion * 30
        + warehouse * 12
        + store * 8
        + (safe_int(ads) if isinstance(ads, int) else 0)
        + (stores / max(dc, 1)) * 0.08
    )

    focus = get_focus(scores)

    if recruitment_pressure >= 65 and expansion_signal >= 55:
        interpretation = f"{company} esetében a LinkedIn alapú álláspiaci jel erősödő toborzási és lehetséges bővülési nyomást mutat."
    elif logistics_pressure >= 55:
        interpretation = f"{company} esetében a legerősebb jel a logisztikai vagy raktári kapacitásokhoz kapcsolódik."
    elif management_pressure >= 55:
        interpretation = f"{company} esetében inkább vezetői vagy központi funkciókhoz kapcsolódó toborzási jel látszik."
    elif recruitment_pressure >= 45:
        interpretation = f"{company} esetében mérsékelt toborzási aktivitás látszik, de ez önmagában még nem jelent expanziót."
    else:
        interpretation = f"{company} esetében jelenleg gyenge LinkedIn alapú toborzási jel látszik."

    return {
        "id": cid,
        "company": company,
        "linkedin_active_ads_hint": ads,
        "source_confidence": item.get("source_confidence", "low"),
        "recruitment_pressure": recruitment_pressure,
        "recruitment_level": signal_level(recruitment_pressure),
        "recruitment_focus": focus,
        "expansion_signal": expansion_signal,
        "logistics_pressure": logistics_pressure,
        "management_pressure": management_pressure,
        "store_pressure": store_pressure,
        "category_scores": scores,
        "store_count_context": stores,
        "dc_count_context": dc,
        "interpretation": interpretation
    }

def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    source = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    companies = [build_company(c) for c in source.get("companies", [])]

    companies_sorted = sorted(
        companies,
        key=lambda x: x["recruitment_pressure"],
        reverse=True
    )

    leader = companies_sorted[0] if companies_sorted else None

    output = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok",
        "source": "linkedin-jobs-monitor.json",
        "method": "derived_recruitment_signal_model_v1",
        "important_note": "Ez nem hivatalos LinkedIn API adat. Nyilvános keresési jelekből képzett óvatos munkaerőpiaci indikátor.",
        "leader": leader,
        "companies": companies_sorted
    }

    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
