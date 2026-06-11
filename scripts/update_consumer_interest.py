import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_DIR / "consumer-interest.json"

BRANDS = [
    {"id": "lidl", "company": "Lidl", "keywords": ["Lidl", "Lidl Magyarország", "Lidl akció"]},
    {"id": "aldi", "company": "ALDI", "keywords": ["ALDI", "ALDI Magyarország", "ALDI akció"]},
    {"id": "penny", "company": "Penny", "keywords": ["Penny Market", "Penny Magyarország", "Penny akció"]},
    {"id": "spar", "company": "SPAR", "keywords": ["SPAR", "SPAR Magyarország", "SPAR akció"]},
    {"id": "tesco", "company": "Tesco", "keywords": ["Tesco", "Tesco Magyarország", "Tesco akció"]},
    {"id": "auchan", "company": "Auchan", "keywords": ["Auchan", "Auchan Magyarország", "Auchan akció"]},
]

GEO = "HU"
TIMEFRAME = "today 12-m"


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


def momentum_score(last_7, previous_7, avg_30):
    score = 50

    if previous_7 > 0:
        score += ((last_7 - previous_7) / previous_7) * 25

    if avg_30 > 0:
        score += ((last_7 - avg_30) / avg_30) * 20

    return clamp(score)


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


def classify_level(score):
    if score >= 75:
        return "ERŐS"
    if score >= 55:
        return "KÖZEPES"
    if score >= 35:
        return "GYENGE-KÖZEPES"
    return "GYENGE"


def interpretation(company, data_status, interest, direction):
    if data_status != "ok":
        return f"{company} esetében jelenleg nincs megbízható Google Trends adat. A mutató nem értelmezhető."

    if interest >= 70 and direction == "up":
        return f"{company} esetében magas és emelkedő fogyasztói keresési érdeklődés látszik."
    if interest >= 70:
        return f"{company} esetében magas keresési érdeklődés látszik, de a rövid távú momentum nem feltétlenül erősödik."
    if direction == "up":
        return f"{company} esetében emelkedő keresési momentum látszik, de az érdeklődési szint még nem kiugró."
    if direction == "down":
        return f"{company} esetében csökkenő keresési momentum látszik."
    return f"{company} esetében stabil vagy mérsékelt fogyasztói keresési érdeklődés látszik."


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


def fetch_brand_values(brand):
    errors = []

    for keyword in brand["keywords"]:
        values, error = fetch_keyword_values(keyword)

        if values:
            return {
                "selected_keyword": keyword,
                "values": values,
                "errors": errors,
                "data_status": "ok"
            }

        errors.append({
            "keyword": keyword,
            "error": error
        })

        time.sleep(6)

    return {
        "selected_keyword": brand["keywords"][0],
        "values": [],
        "errors": errors,
        "data_status": "no_data"
    }


def build_company_row(brand, fetch_result):
    company = brand["company"]
    values = fetch_result["values"]
    data_status = fetch_result["data_status"]

    if not values:
        return {
            "id": brand["id"],
            "company": company,
            "keyword": fetch_result["selected_keyword"],
            "data_status": data_status,
            "consumer_interest_index": None,
            "consumer_interest_level": "NINCS ADAT",
            "consumer_momentum_score": None,
            "momentum_score": None,
            "trend_direction": "n.a.",
            "avg_last_7": None,
            "avg_previous_7": None,
            "avg_last_30": None,
            "avg_period": None,
            "peak_period": None,
            "search_volatility": None,
            "errors": fetch_result["errors"],
            "interpretation": interpretation(company, data_status, 0, "n.a.")
        }

    last_7 = safe_avg(values[-7:])
    previous_7 = safe_avg(values[-14:-7]) if len(values) >= 14 else 0
    avg_30 = safe_avg(values[-30:])
    avg_all = safe_avg(values)
    peak = max(values)

    direction = trend_direction(last_7, previous_7)
    momentum = momentum_score(last_7, previous_7, avg_30)
    volatility = volatility_score(values)

    interest_index = clamp(
        (last_7 * 0.45)
        + (avg_30 * 0.35)
        + (peak * 0.20)
    )

    consumer_momentum = clamp(
        (interest_index * 0.55)
        + (momentum * 0.30)
        + (volatility * 0.15)
    )

    return {
        "id": brand["id"],
        "company": company,
        "keyword": fetch_result["selected_keyword"],
        "data_status": data_status,
        "consumer_interest_index": interest_index,
        "consumer_interest_level": classify_level(interest_index),
        "consumer_momentum_score": consumer_momentum,
        "momentum_score": momentum,
        "trend_direction": direction,
        "avg_last_7": round(last_7, 2),
        "avg_previous_7": round(previous_7, 2),
        "avg_last_30": round(avg_30, 2),
        "avg_period": round(avg_all, 2),
        "peak_period": round(peak, 2),
        "search_volatility": volatility,
        "errors": fetch_result["errors"],
        "interpretation": interpretation(company, data_status, interest_index, direction)
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
            print(f"Fetching Google Trends data for {brand['company']}...")
            result = fetch_brand_values(brand)
            row = build_company_row(brand, result)
            companies.append(row)
            time.sleep(8)

    valid_companies = [c for c in companies if c.get("data_status") == "ok"]

    if valid_companies:
        status = "ok"
        error = None
        leader = sorted(
            valid_companies,
            key=lambda x: x["consumer_momentum_score"] or 0,
            reverse=True
        )[0]
    else:
        status = "fallback_error"
        error = "No valid Google Trends data returned. Check per-company errors."
        leader = None

    output = {
        "updated_at": updated_at,
        "status": status,
        "source": "google_trends",
        "method": "pytrends_unofficial_best_effort_v4_debug_and_keyword_fallback",
        "geo": GEO,
        "timeframe": TIMEFRAME,
        "important_note": (
            "A Google Trends értékek relatív keresési indexek, nem abszolút keresési darabszámok. "
            "A PyTrends nem hivatalos Google API. GitHub Actions környezetben előfordulhat, hogy "
            "a Google nem ad vissza adatot vagy blokkolja a lekérést. Nincs adat esetén a mutató nem értelmezhető."
        ),
        "error": error,
        "global_errors": global_errors,
        "leader": leader,
        "companies": companies
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
