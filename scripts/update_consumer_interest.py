import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_DIR / "consumer-interest.json"

BRANDS = [
    {"id": "lidl", "company": "Lidl", "keyword": "Lidl"},
    {"id": "aldi", "company": "ALDI", "keyword": "ALDI"},
    {"id": "penny", "company": "Penny", "keyword": "Penny Market"},
    {"id": "spar", "company": "SPAR", "keyword": "SPAR"},
    {"id": "tesco", "company": "Tesco", "keyword": "Tesco"},
    {"id": "auchan", "company": "Auchan", "keyword": "Auchan"},
]

GEO = "HU"
TIMEFRAME = "today 3-m"


def clamp(value, low=0, high=100):
    return max(low, min(high, round(value)))


def safe_avg(values):
    clean = [float(v) for v in values if v is not None]
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
    clean = [float(v) for v in values if v is not None]
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


def interpretation(company, interest, momentum, direction):
    if interest >= 70 and direction == "up":
        return f"{company} esetében magas és emelkedő fogyasztói keresési érdeklődés látszik."
    if interest >= 70:
        return f"{company} esetében magas keresési érdeklődés látszik, de a rövid távú momentum nem feltétlenül erősödik."
    if direction == "up":
        return f"{company} esetében emelkedő keresési momentum látszik, de az érdeklődési szint még nem kiugró."
    if direction == "down":
        return f"{company} esetében csökkenő keresési momentum látszik."
    return f"{company} esetében stabil vagy mérsékelt fogyasztói keresési érdeklődés látszik."


def fetch_google_trends():
    try:
        from pytrends.request import TrendReq
    except Exception as e:
        raise RuntimeError(f"PyTrends import error: {e}")

    pytrends = TrendReq(
        hl="hu-HU",
        tz=60,
        timeout=(10, 25),
        retries=2,
        backoff_factor=0.3
    )

    keywords = [b["keyword"] for b in BRANDS]
    pytrends.build_payload(
        kw_list=keywords,
        cat=0,
        timeframe=TIMEFRAME,
        geo=GEO,
        gprop=""
    )

    df = pytrends.interest_over_time()

    if df is None or df.empty:
        raise RuntimeError("Google Trends returned empty dataframe")

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    return df


def build_company_rows(df):
    rows = []

    for brand in BRANDS:
        keyword = brand["keyword"]
        company = brand["company"]

        if keyword not in df.columns:
            values = []
        else:
            values = [float(v) for v in df[keyword].fillna(0).tolist()]

        last_7 = safe_avg(values[-7:]) if values else 0
        previous_7 = safe_avg(values[-14:-7]) if len(values) >= 14 else 0
        avg_30 = safe_avg(values[-30:]) if values else 0
        avg_all = safe_avg(values)
        peak = max(values) if values else 0

        direction = trend_direction(last_7, previous_7)
        momentum = momentum_score(last_7, previous_7, avg_30)
        volatility = volatility_score(values)

        interest_index = clamp((last_7 * 0.45) + (avg_30 * 0.35) + (peak * 0.20))
        consumer_momentum = clamp((interest_index * 0.55) + (momentum * 0.30) + (volatility * 0.15))

        rows.append({
            "id": brand["id"],
            "company": company,
            "keyword": keyword,
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
            "interpretation": interpretation(company, interest_index, momentum, direction)
        })

    return sorted(rows, key=lambda x: x["consumer_momentum_score"], reverse=True)


def main():
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        df = fetch_google_trends()
        companies = build_company_rows(df)
        status = "ok"
        error = None
    except Exception as e:
        companies = []
        status = "fallback_error"
        error = str(e)

    leader = companies[0] if companies else None

    output = {
        "updated_at": updated_at,
        "status": status,
        "source": "google_trends",
        "method": "pytrends_unofficial_best_effort",
        "geo": GEO,
        "timeframe": TIMEFRAME,
        "important_note": "A Google Trends értékek relatív keresési indexek, nem abszolút keresési darabszámok. A PyTrends nem hivatalos Google API, ezért időnként rate limit vagy adatbetöltési hiba előfordulhat.",
        "error": error,
        "leader": leader,
        "companies": companies
    }

    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
