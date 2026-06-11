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
    {
        "id": "lidl",
        "company": "Lidl",
        "queries": {
            "promotion": {"label": "Akció / promóció", "keyword": "Lidl akció"},
            "store_access": {"label": "Bolt / nyitvatartás", "keyword": "Lidl nyitvatartás"},
            "price": {"label": "Ár / drágulás", "keyword": "Lidl ár"},
            "jobs": {"label": "Állás / karrier", "keyword": "Lidl állás"},
            "digital": {"label": "App / online", "keyword": "Lidl app"},
        },
    },
    {
        "id": "aldi",
        "company": "ALDI",
        "queries": {
            "promotion": {"label": "Akció / promóció", "keyword": "ALDI akció"},
            "store_access": {"label": "Bolt / nyitvatartás", "keyword": "ALDI nyitvatartás"},
            "price": {"label": "Ár / drágulás", "keyword": "ALDI ár"},
            "jobs": {"label": "Állás / karrier", "keyword": "ALDI állás"},
            "digital": {"label": "App / online", "keyword": "ALDI app"},
        },
    },
    {
        "id": "penny",
        "company": "Penny",
        "queries": {
            "promotion": {"label": "Akció / promóció", "keyword": "Penny akció"},
            "store_access": {"label": "Bolt / nyitvatartás", "keyword": "Penny nyitvatartás"},
            "price": {"label": "Ár / drágulás", "keyword": "Penny ár"},
            "jobs": {"label": "Állás / karrier", "keyword": "Penny állás"},
            "digital": {"label": "App / online", "keyword": "Penny app"},
        },
    },
    {
        "id": "spar",
        "company": "SPAR",
        "queries": {
            "promotion": {"label": "Akció / promóció", "keyword": "SPAR akció"},
            "store_access": {"label": "Bolt / nyitvatartás", "keyword": "SPAR nyitvatartás"},
            "price": {"label": "Ár / drágulás", "keyword": "SPAR ár"},
            "jobs": {"label": "Állás / karrier", "keyword": "SPAR állás"},
            "digital": {"label": "App / online", "keyword": "SPAR app"},
        },
    },
    {
        "id": "tesco",
        "company": "Tesco",
        "queries": {
            "promotion": {"label": "Akció / promóció", "keyword": "Tesco akció"},
            "store_access": {"label": "Bolt / nyitvatartás", "keyword": "Tesco nyitvatartás"},
            "price": {"label": "Ár / drágulás", "keyword": "Tesco ár"},
            "jobs": {"label": "Állás / karrier", "keyword": "Tesco állás"},
            "digital": {"label": "Clubcard / digitális", "keyword": "Tesco clubcard"},
        },
    },
    {
        "id": "auchan",
        "company": "Auchan",
        "queries": {
            "promotion": {"label": "Akció / promóció", "keyword": "Auchan akció"},
            "store_access": {"label": "Bolt / nyitvatartás", "keyword": "Auchan nyitvatartás"},
            "price": {"label": "Ár / drágulás", "keyword": "Auchan ár"},
            "jobs": {"label": "Állás / karrier", "keyword": "Auchan állás"},
            "digital": {"label": "Online / digitális", "keyword": "Auchan online"},
        },
    },
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
        },
    )


def fetch_brand_payload(brand):
    pytrends = create_pytrends_client()
    intent_items = list(brand["queries"].items())
    keywords = [item[1]["keyword"] for item in intent_items]

    try:
        pytrends.build_payload(
            kw_list=keywords,
            cat=0,
            timeframe=TIMEFRAME,
            geo=GEO,
            gprop="",
        )

        time.sleep(5)

        df = pytrends.interest_over_time()

        if df is None or df.empty:
            return {}, "empty_dataframe"

        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])

        result = {}

        for intent_id, item in intent_items:
            keyword = item["keyword"]

            if keyword not in df.columns:
                result[intent_id] = {
                    "keyword": keyword,
                    "values": [],
                    "error": "keyword_missing_from_dataframe",
                }
                continue

            values = [float(v) for v in df[keyword].fillna(0).tolist()]

            if not values:
                result[intent_id] = {
                    "keyword": keyword,
                    "values": [],
                    "error": "empty_values",
                }
                continue

            if max(values) <= 0:
                result[intent_id] = {
                    "keyword": keyword,
                    "values": [],
                    "error": "all_zero_values",
                }
                continue

            result[intent_id] = {
                "keyword": keyword,
                "values": values,
                "error": None,
            }

        return result, None

    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


def build_intent_record(intent_id, label, keyword, values, error):
    if not values:
        return {
            "intent_id": intent_id,
            "intent_label": label,
            "keyword": keyword,
            "data_status": "no_data",
            "intent_score": None,
            "trend_direction": "n.a.",
            "avg_last_7": None,
            "avg_previous_7": None,
            "avg_last_30": None,
            "avg_period": None,
            "peak_period": None,
            "search_volatility": None,
            "error": error,
        }

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

    return {
        "intent_id": intent_id,
        "intent_label": label,
        "keyword": keyword,
        "data_status": "ok",
        "intent_score": score,
        "trend_direction": direction,
        "avg_last_7": round(last_7, 2),
        "avg_previous_7": round(previous_7, 2),
        "avg_last_30": round(avg_30, 2),
        "avg_period": round(avg_period, 2),
        "peak_period": round(peak, 2),
        "search_volatility": volatility,
        "error": None,
    }


def build_company_result(brand):
    print(f"Fetching search intent payload for {brand['company']}...")

    payload, payload_error = fetch_brand_payload(brand)

    intents = []

    for intent_id, item in brand["queries"].items():
        label = item["label"]
        keyword = item["keyword"]
        data = payload.get(intent_id, {
            "keyword": keyword,
            "values": [],
            "error": payload_error or "no_payload_data",
        })

        record = build_intent_record(
            intent_id=intent_id,
            label=label,
            keyword=data.get("keyword", keyword),
            values=data.get("values", []),
            error=data.get("error"),
        )

        intents.append(record)

    valid_intents = [x for x in intents if x["data_status"] == "ok"]

    if valid_intents:
        dominant = sorted(
            valid_intents,
            key=lambda x: x["intent_score"] or 0,
            reverse=True
        )[0]

        total_score = sum((x["intent_score"] or 0) for x in valid_intents)

        intent_share = []
        for x in valid_intents:
            share = ((x["intent_score"] or 0) / total_score * 100) if total_score > 0 else 0
            intent_share.append({
                "intent_id": x["intent_id"],
                "intent_label": x["intent_label"],
                "score": x["intent_score"],
                "share_pct": round(share, 1),
            })

        interpretation = (
            f"{brand['company']} esetében a legerősebb keresési szándék: "
            f"{dominant['intent_label']}."
        )

        status = "ok"
    else:
        dominant = None
        intent_share = []
        interpretation = (
            f"{brand['company']} esetében jelenleg nincs értelmezhető Google Trends keresési szándék adat."
        )
        status = "no_data"

    return {
        "id": brand["id"],
        "company": brand["company"],
        "data_status": status,
        "dominant_intent": dominant["intent_id"] if dominant else None,
        "dominant_intent_label": dominant["intent_label"] if dominant else None,
        "dominant_intent_score": dominant["intent_score"] if dominant else None,
        "intent_share": intent_share,
        "intents": intents,
        "payload_error": payload_error,
        "interpretation": interpretation,
    }


def main():
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    companies = []
    global_errors = []

    try:
        import pytrends  # noqa: F401
        pytrends_available = True
    except Exception as e:
        pytrends_available = False
        global_errors.append(f"pytrends_import_error: {e}")

    if pytrends_available:
        for brand in BRANDS:
            result = build_company_result(brand)
            companies.append(result)
            time.sleep(12)

    valid_companies = [c for c in companies if c.get("data_status") == "ok"]

    status = "ok" if valid_companies else "fallback_error"
    error = None if valid_companies else "No valid Google Trends search intent data returned."

    output = {
        "updated_at": updated_at,
        "status": status,
        "source": "google_trends",
        "method": "pytrends_unofficial_best_effort_search_intent_v2_one_payload_per_company",
        "geo": GEO,
        "timeframe": TIMEFRAME,
        "important_note": (
            "A Google Trends keresési szándék mutató relatív keresési indexekből készül. "
            "Nem abszolút keresési darabszám, nem reprezentatív fogyasztói kutatás. "
            "A PyTrends nem hivatalos Google API, ezért rate limit és adatkimaradás előfordulhat. "
            "Egy céghez egyszerre legfeljebb 5 kulcsszó kerül lekérdezésre."
        ),
        "error": error,
        "global_errors": global_errors,
        "companies": companies,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
