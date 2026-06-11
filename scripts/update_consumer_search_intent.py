import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_DIR / "consumer-search-intent.json"

GEO = "HU"
TIMEFRAME = "today 12-m"

BRANDS = [
    {"id": "lidl", "company": "Lidl", "base": "Lidl"},
    {"id": "aldi", "company": "ALDI", "base": "ALDI"},
    {"id": "penny", "company": "Penny", "base": "Penny"},
    {"id": "spar", "company": "SPAR", "base": "SPAR"},
    {"id": "tesco", "company": "Tesco", "base": "Tesco"},
    {"id": "auchan", "company": "Auchan", "base": "Auchan"},
]

INTENTS = [
    {"id": "promotion", "label": "Akció / promóció", "terms": ["akció", "újság", "kupon"]},
    {"id": "store_access", "label": "Bolt / nyitvatartás", "terms": ["nyitvatartás", "bolt", "áruház"]},
    {"id": "price", "label": "Ár / drágulás", "terms": ["ár", "olcsó", "drága"]},
    {"id": "jobs", "label": "Állás / karrier", "terms": ["állás", "karrier", "munka"]},
    {"id": "digital", "label": "App / online", "terms": ["app", "online", "webshop"]},
    {"id": "complaint", "label": "Panasz / probléma", "terms": ["panasz", "reklamáció", "probléma"]},
]


def clamp(value, low=0, high=100):
    try:
        value = float(value)
    except Exception:
        value = 0
    return max(low, min(high, round(value)))


def safe_avg(values):
    clean = []
    for v in values:
        try:
            clean.append(float(v))
        except Exception:
            pass
    return sum(clean) / len(clean) if clean else 0


def volatility_score(values):
    clean = []
    for v in values:
        try:
            clean.append(float(v))
        except Exception:
            pass

    if len(clean) < 3:
        return 0

    avg = safe_avg(clean)
    if avg <= 0:
        return 0

    return clamp((statistics.pstdev(clean) / avg) * 100)


def trend_direction(last_7, previous_7):
    if previous_7 <= 0 and last_7 > 0:
        return "up"
    if previous_7 <= 0:
        return "stable"

    change = ((last_7 - previous_7) / previous_7) * 100

    if change >= 10:
        return "up"
    if change <= -10:
        return "down"
    return "stable"


def create_pytrends_client():
    from pytrends.request import TrendReq

    return TrendReq(
        hl="hu-HU",
        tz=60,
        requests_args={
            "headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                ),
                "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        }
    )


def fetch_keyword_values(keyword):
    from pytrends.exceptions import ResponseError

    pytrends = create_pytrends_client()

    try:
        pytrends.build_payload(
            kw_list=[keyword],
            cat=0,
            timeframe=TIMEFRAME,
            geo=GEO,
            gprop=""
        )

        time.sleep(4)

        df = pytrends.interest_over_time()

        if df is None or df.empty:
            return [], "empty_dataframe"

        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])

        if keyword not in df.columns:
            return [], "keyword_missing_from_dataframe"

        values = [float(v) for v in df[keyword].fillna(0).tolist()]

        if not values:
            return [], "empty_values"

        if max(values) <= 0:
            return [], "all_zero_values"

        return values, None

    except ResponseError as e:
        return [], f"google_response_error: {e}"
    except Exception as e:
        return [], f"exception: {type(e).__name__}: {e}"


def build_intent_query(base, term):
    return f"{base} {term}"


def build_intent_result(brand, intent):
    base = brand["base"]
    term_results = []
    best_score = 0
    best_term = None
    best_values = []
    errors = []

    for term in intent["terms"]:
        keyword = build_intent_query(base, term)
        values, error = fetch_keyword_values(keyword)

        if values:
            last_7 = safe_avg(values[-7:])
            previous_7 = safe_avg(values[-14:-7]) if len(values) >= 14 else 0
            avg_30 = safe_avg(values[-30:])
            avg_period = safe_avg(values)
            peak = max(values)
            volatility = volatility_score(values)
            direction = trend_direction(last_7, previous_7)

            score = clamp(
                last_7 * 0.40
                + avg_30 * 0.35
                + peak * 0.15
                + volatility * 0.10
            )

            term_results.append({
                "term": term,
                "keyword": keyword,
                "status": "ok",
                "intent_score": score,
                "avg_last_7": round(last_7, 2),
                "avg_previous_7": round(previous_7, 2),
                "avg_last_30": round(avg_30, 2),
                "avg_period": round(avg_period, 2),
                "peak_period": round(peak, 2),
                "trend_direction": direction,
                "search_volatility": volatility
            })

            if score > best_score:
                best_score = score
                best_term = term
                best_values = values

        else:
            errors.append({
                "term": term,
                "keyword": keyword,
                "error": error
            })
            term_results.append({
                "term": term,
                "keyword": keyword,
                "status": "no_data",
                "intent_score": None
            })

        time.sleep(8)

    valid_terms = [x for x in term_results if x.get("status") == "ok"]

    if valid_terms:
        avg_score = safe_avg([x["intent_score"] for x in valid_terms])
        strongest = sorted(valid_terms, key=lambda x: x["intent_score"], reverse=True)[0]
        direction = strongest.get("trend_direction", "stable")
        data_status = "ok"
    else:
        avg_score = None
        strongest = None
        direction = "n.a."
        data_status = "no_data"

    return {
        "intent_id": intent["id"],
        "intent_label": intent["label"],
        "data_status": data_status,
        "intent_score": clamp(avg_score) if avg_score is not None else None,
        "strongest_term": strongest["term"] if strongest else None,
        "strongest_keyword": strongest["keyword"] if strongest else None,
        "trend_direction": direction,
        "terms": term_results,
        "errors": errors
    }


def build_company_result(brand):
    print(f"Building search intent profile for {brand['company']}...")

    intents = []

    for intent in INTENTS:
        result = build_intent_result(brand, intent)
        intents.append(result)
        time.sleep(12)

    valid_intents = [i for i in intents if i.get("data_status") == "ok"]

    if valid_intents:
        dominant = sorted(
            valid_intents,
            key=lambda x: x["intent_score"] or 0,
            reverse=True
        )[0]

        total_score = sum((i["intent_score"] or 0) for i in valid_intents)

        intent_share = []
        for i in valid_intents:
            share = ((i["intent_score"] or 0) / total_score * 100) if total_score > 0 else 0
            intent_share.append({
                "intent_id": i["intent_id"],
                "intent_label": i["intent_label"],
                "score": i["intent_score"],
                "share_pct": round(share, 1)
            })

        interpretation = (
            f"{brand['company']} esetében a legerősebb keresési szándék: "
            f"{dominant['intent_label']}."
        )
    else:
        dominant = None
        intent_share = []
        interpretation = (
            f"{brand['company']} esetében jelenleg nincs értelmezhető Google Trends keresési szándék adat."
        )

    return {
        "id": brand["id"],
        "company": brand["company"],
        "base_keyword": brand["base"],
        "data_status": "ok" if valid_intents else "no_data",
        "dominant_intent": dominant["intent_id"] if dominant else None,
        "dominant_intent_label": dominant["intent_label"] if dominant else None,
        "dominant_intent_score": dominant["intent_score"] if dominant else None,
        "intent_share": intent_share,
        "intents": intents,
        "interpretation": interpretation
    }


def main():
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    companies = []
    global_errors = []

    try:
        import pytrends
        pytrends_available = True
    except Exception as e:
        pytrends_available = False
        global_errors.append(f"pytrends_import_error: {e}")

    if pytrends_available:
        for brand in BRANDS:
            company_result = build_company_result(brand)
            companies.append(company_result)
            time.sleep(20)

    valid_companies = [c for c in companies if c.get("data_status") == "ok"]

    if valid_companies:
        status = "ok"
        error = None
    else:
        status = "fallback_error"
        error = "No valid Google Trends search intent data returned."

    output = {
        "updated_at": updated_at,
        "status": status,
        "source": "google_trends",
        "method": "pytrends_unofficial_best_effort_search_intent_v1",
        "geo": GEO,
        "timeframe": TIMEFRAME,
        "important_note": (
            "A Google Trends keresési szándék mutató relatív keresési indexekből készül. "
            "Nem abszolút keresési darabszám, nem reprezentatív fogyasztói kutatás. "
            "A PyTrends nem hivatalos Google API, ezért rate limit és adatkimaradás előfordulhat."
        ),
        "error": error,
        "global_errors": global_errors,
        "companies": companies
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
