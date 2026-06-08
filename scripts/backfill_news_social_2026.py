import json
import re
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

COMPANIES_FILE = DATA_DIR / "companies.json"

OUTPUT_FILE = DATA_DIR / "news-social-history-2026.json"
STATUS_FILE = DATA_DIR / "news-social-history-2026-status.json"

START_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)
TODAY = datetime.now(timezone.utc)


SOURCE_QUERIES = [
    "{company} élelmiszer kiskereskedelem Magyarország after:2026-01-01",
    "{company} áruház Magyarország after:2026-01-01",
    "{company} akció árak Magyarország after:2026-01-01",
    "{company} munkaerő bér állás Magyarország after:2026-01-01",
    "{company} beruházás üzletnyitás Magyarország after:2026-01-01",
    "{company} hatóság bírság GVH NAV Magyarország after:2026-01-01",
    "{company} beszállító logisztika Magyarország after:2026-01-01",
]


SOURCE_WEIGHTS = {
    "portfolio": 5,
    "telex": 5,
    "hvg": 5,
    "világgazdaság": 4,
    "vg": 4,
    "trade magazin": 4,
    "piac&profit": 4,
    "store insider": 3,
    "24.hu": 3,
    "economx": 3,
    "pénzcentrum": 2,
    "haszon": 3,
    "forbes": 3,
    "startlap": 1,
    "mindmegette": 1,
}


EVENT_TYPES = {
    "financial": [
        "árbevétel", "forgalom", "forgalma", "profit", "veszteség",
        "milliárd", "milliárd forint", "piacvezető", "rangsor",
        "részesedés", "árrés", "árrésstop"
    ],
    "expansion": [
        "új üzlet", "üzletnyitás", "áruháznyitás", "beruházás",
        "franchise", "bővítés", "terjeszkedés", "logisztikai központ"
    ],
    "promotion": [
        "akció", "kedvezmény", "leárazás", "olcsóbb", "árverseny",
        "kupon", "akciós újság", "fél áron"
    ],
    "workforce": [
        "munkaerő", "bér", "fizetés", "dolgozó", "állás",
        "sztrájk", "toborzás", "karrier", "kasszás"
    ],
    "regulatory": [
        "GVH", "NAV", "hatóság", "bírság", "vizsgálat",
        "plázastop", "plázabizottság", "engedély", "nem építhet"
    ],
    "reputation": [
        "panasz", "kritika", "botrány", "visszahívás",
        "pofont kapott", "áll a bál", "nem örülnek"
    ],
    "supplier": [
        "beszállító", "hazai kkv", "kkv", "termelő",
        "ellátási lánc", "hazai termék", "logisztika"
    ],
}


BUSINESS_IMPACT_LABELS = {
    "revenue": "Bevételi hatás",
    "cost": "Költséghatás",
    "reputation": "Reputációs hatás",
    "expansion": "Terjeszkedési hatás",
    "regulation": "Szabályozási hatás",
    "supply_chain": "Ellátási lánc hatás",
    "workforce": "Munkaerő hatás",
    "general": "Általános hatás",
    "n.a.": "n.a.",
}


NARRATIVE_LABELS = {
    "growth": "Növekedés",
    "competition": "Piaci verseny",
    "reputation": "Reputáció",
    "workforce": "Munkaerő",
    "supply_chain": "Ellátási lánc",
    "regulation": "Szabályozás",
    "defensive": "Védekezés",
    "general": "Általános",
    "n.a.": "n.a.",
}


BUSINESS_IMPACT = {
    "revenue": [
        "forgalom", "forgalma", "árbevétel", "árbevétele", "bevétel",
        "akció", "árverseny", "kedvezmény", "leárazás", "árrés", "árrésstop",
        "piacvezető", "részesedés", "milliárd forint"
    ],
    "cost": [
        "költség", "bér", "energia", "infláció", "veszteség",
        "veszteséges", "mínuszban", "falnak ment"
    ],
    "reputation": [
        "panasz", "bírság", "botrány", "visszahívás",
        "pofont kapott", "áll a bál", "kritika"
    ],
    "expansion": [
        "új üzlet", "üzletnyitás", "áruháznyitás", "beruházás",
        "franchise", "bővítés", "terjeszkedés"
    ],
    "regulation": [
        "GVH", "NAV", "hatóság", "bírság", "vizsgálat",
        "plázastop", "plázabizottság", "engedély", "nem építhet"
    ],
    "supply_chain": [
        "beszállító", "ellátási lánc", "készlethiány",
        "hazai kkv", "kkv", "termelő", "hazai termék", "logisztika"
    ],
    "workforce": [
        "munkaerő", "bér", "fizetés", "dolgozó",
        "állás", "sztrájk", "toborzás", "kasszás"
    ],
}


STRATEGIC_NARRATIVES = {
    "growth": [
        "beruházás", "új üzlet", "üzletnyitás", "terjeszkedés",
        "franchise", "bővítés", "piacvezető", "elsőség", "forgalma nőtt"
    ],
    "competition": [
        "akció", "árverseny", "kedvezmény", "olcsóbb",
        "leárazás", "árrésstop", "részesedés", "rangsor", "megelőzte"
    ],
    "reputation": [
        "panasz", "botrány", "visszahívás", "pofont kapott",
        "áll a bál", "kritika"
    ],
    "workforce": [
        "munkaerő", "bér", "toborzás", "állás", "dolgozó", "kasszás"
    ],
    "supply_chain": [
        "beszállító", "logisztika", "ellátási lánc",
        "hazai kkv", "termelő", "hazai termék"
    ],
    "regulation": [
        "GVH", "NAV", "hatóság", "plázastop",
        "plázabizottság", "engedély", "nem építhet", "bírság"
    ],
    "defensive": [
        "veszteség", "bezárás", "visszaesés",
        "eltűnik", "mínuszban", "veszteséges", "falnak ment"
    ],
}


POSITIVE_WORDS = [
    "fejlesztés", "beruházás", "nyitás", "bővítés", "növekedés",
    "díj", "elismerés", "nyert", "piacvezető", "forgalma nőtt"
]

NEGATIVE_WORDS = [
    "bírság", "panasz", "botrány", "veszteség", "visszahívás",
    "GVH", "NAV", "hatóság", "nem építhet", "pofont kapott",
    "plázastop", "plázabizottság", "áll a bál", "mínuszban",
    "veszteséges", "eltűnik", "falnak ment"
]


DOMAIN_EXCLUDE_PATTERNS = [
    "jednota",
    "dunaszerdahely",
    "szlovák",
    "slovakia",
    "slovensko",
]


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize(text):
    return clean_text(text).lower()


def make_google_news_rss(query):
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=hu&gl=HU&ceid=HU:hu"


def entry_date(entry):
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return TODAY


def article_id(company_id, title, link):
    raw = f"{company_id}|{title}|{link}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def source_weight(source):
    lower = normalize(source)
    for key, weight in SOURCE_WEIGHTS.items():
        if key in lower:
            return weight
    return 2


def is_bad_match(company_id, company_name, title, summary):
    text = normalize(f"{title} {summary}")
    company = normalize(company_name)

    if company_id == "coop" and any(p in text for p in DOMAIN_EXCLUDE_PATTERNS):
        return True

    if company not in text:
        return True

    return False


def score_dictionary(text, dictionary):
    lower = normalize(text)
    scores = {}
    for category, words in dictionary.items():
        score = sum(1 for w in words if w.lower() in lower)
        if score > 0:
            scores[category] = score
    return scores


def detect_best(text, dictionary, default="general"):
    scores = score_dictionary(text, dictionary)
    if not scores:
        return default
    return max(scores.items(), key=lambda x: x[1])[0]


def classify_sentiment(text):
    lower = normalize(text)
    pos = sum(1 for w in POSITIVE_WORDS if w.lower() in lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w.lower() in lower)

    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def detect_event_type(text):
    return detect_best(text, EVENT_TYPES)


def detect_business_impact(text):
    return detect_best(text, BUSINESS_IMPACT)


def detect_strategic_narrative(text):
    return detect_best(text, STRATEGIC_NARRATIVES)


def impact_level(event_type, business_impact, narrative, sw, sentiment):
    score = sw

    if event_type in ["financial", "regulatory", "reputation"]:
        score += 2
    if business_impact in ["regulation", "reputation", "cost"]:
        score += 2
    if narrative in ["regulation", "reputation", "defensive"]:
        score += 2
    if sentiment == "negative":
        score += 2

    if score >= 9:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def article_risk_score(article):
    score = 0

    if article["sentiment"] == "negative":
        score += 20
    if article["event_type"] in ["regulatory", "reputation"]:
        score += 25
    if article["business_impact"] in ["regulation", "reputation", "cost"]:
        score += 18
    if article["strategic_narrative"] in ["regulation", "reputation", "defensive"]:
        score += 18
    if article["impact"] == "critical":
        score += 18
    elif article["impact"] == "high":
        score += 12
    elif article["impact"] == "medium":
        score += 6

    score += article["source_weight"] * 2

    return min(100, score)


def company_queries(company):
    return [q.format(company=company) for q in SOURCE_QUERIES]


def count_values(items, field):
    result = {}
    for item in items:
        value = item.get(field, "general")
        result[value] = result.get(value, 0) + 1
    return result


def dominant_from_counts(counts, ignore_general=True):
    if not counts:
        return "n.a."

    tmp = dict(counts)
    if ignore_general:
        tmp.pop("general", None)
        tmp.pop("n.a.", None)

    if not tmp:
        return "general" if "general" in counts else "n.a."

    return max(tmp.items(), key=lambda x: x[1])[0]


def collect_company(company):
    company_id = company.get("id")
    company_name = company.get("company") or company.get("name")

    articles_by_id = {}

    for query in company_queries(company_name):
        rss_url = make_google_news_rss(query)
        feed = feedparser.parse(rss_url)

        for entry in feed.entries:
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            source = getattr(getattr(entry, "source", None), "title", None) or "Google News"
            published_at = entry_date(entry)

            if published_at < START_DATE:
                continue

            if is_bad_match(company_id, company_name, title, summary):
                continue

            full_text = f"{title} {summary}"

            sentiment = classify_sentiment(full_text)
            event_type = detect_event_type(full_text)
            business_impact = detect_business_impact(full_text)
            narrative = detect_strategic_narrative(full_text)
            sw = source_weight(source)
            impact = impact_level(event_type, business_impact, narrative, sw, sentiment)

            item = {
                "id": article_id(company_id, title, link),
                "company_id": company_id,
                "company": company_name,
                "title": title,
                "summary": summary,
                "url": link,
                "source": source,
                "source_weight": sw,
                "published_at": published_at.strftime("%Y-%m-%d"),
                "sentiment": sentiment,
                "event_type": event_type,
                "business_impact": business_impact,
                "business_impact_label": BUSINESS_IMPACT_LABELS.get(business_impact, business_impact),
                "strategic_narrative": narrative,
                "strategic_narrative_label": NARRATIVE_LABELS.get(narrative, narrative),
                "impact": impact,
                "article_risk_score": 0,
                "query": query,
            }

            item["article_risk_score"] = article_risk_score(item)
            articles_by_id[item["id"]] = item

    articles = list(articles_by_id.values())
    articles.sort(key=lambda x: (x["published_at"], x["source_weight"]), reverse=True)

    event_types = count_values(articles, "event_type")
    business_impacts = count_values(articles, "business_impact")
    narratives = count_values(articles, "strategic_narrative")

    risk_score = round(sum(article_risk_score(a) for a in articles) / max(1, len(articles)))
    risk_score = min(100, risk_score)

    highlight = None
    if articles:
        highlight = sorted(
            articles,
            key=lambda a: (
                a.get("article_risk_score", 0),
                a.get("source_weight", 0),
                a.get("published_at", "")
            ),
            reverse=True
        )[0]

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "period_start": START_DATE.strftime("%Y-%m-%d"),
        "period_end": TODAY.strftime("%Y-%m-%d"),
        "news_count": len(articles),
        "media_impact_score": sum(a["source_weight"] for a in articles),
        "risk_score": risk_score,
        "social_index": None,
        "social_signal_status": "not_collected",
        "high_impact_count": sum(1 for a in articles if a["impact"] in ["high", "critical"]),
        "critical_impact_count": sum(1 for a in articles if a["impact"] == "critical"),
        "positive_count": sum(1 for a in articles if a["sentiment"] == "positive"),
        "neutral_count": sum(1 for a in articles if a["sentiment"] == "neutral"),
        "negative_count": sum(1 for a in articles if a["sentiment"] == "negative"),
        "dominant_event_type": dominant_from_counts(event_types),
        "dominant_business_impact": dominant_from_counts(business_impacts),
        "dominant_business_impact_label": BUSINESS_IMPACT_LABELS.get(dominant_from_counts(business_impacts), "n.a."),
        "dominant_strategic_narrative": dominant_from_counts(narratives),
        "dominant_strategic_narrative_label": NARRATIVE_LABELS.get(dominant_from_counts(narratives), "n.a."),
        "dominant_market_narrative": NARRATIVE_LABELS.get(dominant_from_counts(narratives), "n.a."),
        "highlight_event": highlight["title"] if highlight else "n.a.",
        "highlight_event_source": highlight["source"] if highlight else "n.a.",
        "highlight_event_date": highlight["published_at"] if highlight else "n.a.",
        "event_types": event_types,
        "business_impacts": business_impacts,
        "strategic_narratives": narratives,
        "source_confidence": "medium" if articles else "low",
        "articles": articles,
    }


def normalize_company_indexes(companies):
    max_media = max([c["media_impact_score"] for c in companies] or [1])
    max_news = max([c["news_count"] for c in companies] or [1])

    for c in companies:
        c["media_index"] = round((c["media_impact_score"] / max_media) * 100, 1) if max_media else 0
        c["news_index"] = round((c["news_count"] / max_news) * 100, 1) if max_news else 0
        c["risk_index"] = c["risk_score"]

    return companies


def top_events(companies, limit=25):
    events = []
    for c in companies:
        events.extend(c.get("articles", []))

    events.sort(
        key=lambda a: (
            a.get("article_risk_score", 0),
            a.get("source_weight", 0),
            a.get("published_at", "")
        ),
        reverse=True
    )

    return events[:limit]


def aggregate_counts(companies, field):
    result = {}
    for c in companies:
        for key, value in c.get(field, {}).items():
            result[key] = result.get(key, 0) + value
    return result


def build_summary(companies):
    if not companies:
        return {}

    by_media = sorted(companies, key=lambda x: x["media_index"], reverse=True)
    by_news = sorted(companies, key=lambda x: x["news_index"], reverse=True)
    by_risk = sorted(companies, key=lambda x: x["risk_index"], reverse=True)

    narratives = aggregate_counts(companies, "strategic_narratives")
    impacts = aggregate_counts(companies, "business_impacts")

    dominant_narrative = dominant_from_counts(narratives)
    dominant_impact = dominant_from_counts(impacts)

    return {
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "period_start": START_DATE.strftime("%Y-%m-%d"),
        "period_end": TODAY.strftime("%Y-%m-%d"),
        "total_news": sum(c["news_count"] for c in companies),
        "total_media_score": sum(c["media_impact_score"] for c in companies),
        "total_high_impact_events": sum(c["high_impact_count"] for c in companies),
        "total_critical_events": sum(c["critical_impact_count"] for c in companies),
        "media_impact_leader": by_media[0]["company"],
        "media_impact_leader_index": by_media[0]["media_index"],
        "news_leader": by_news[0]["company"],
        "news_leader_index": by_news[0]["news_index"],
        "risk_leader": by_risk[0]["company"],
        "risk_leader_index": by_risk[0]["risk_index"],
        "social_leader": "n.a.",
        "social_leader_index": None,
        "dominant_market_narrative": NARRATIVE_LABELS.get(dominant_narrative, dominant_narrative),
        "dominant_business_impact": BUSINESS_IMPACT_LABELS.get(dominant_impact, dominant_impact),
        "social_status": "not_collected",
    }


def main():
    companies_raw = load_json(COMPANIES_FILE, [])

    if not companies_raw:
        raise RuntimeError("Hiányzik vagy üres a docs/data/companies.json fájl.")

    companies = [collect_company(c) for c in companies_raw]
    companies = normalize_company_indexes(companies)

    output = {
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "period_start": START_DATE.strftime("%Y-%m-%d"),
        "period_end": TODAY.strftime("%Y-%m-%d"),
        "mode": "historical_news_social_backfill_2026",
        "social_status": "not_collected",
        "summary": build_summary(companies),
        "companies": companies,
        "events": top_events(companies, 25),
        "labels": {
            "business_impact": BUSINESS_IMPACT_LABELS,
            "strategic_narrative": NARRATIVE_LABELS,
        },
        "notes": (
            "Egyszeri történeti backfill 2026.01.01-től. "
            "A fájl nem írja felül a friss news-social.json adatot. "
            "A social media adatgyűjtés ebben a történeti verzióban sem aktív."
        ),
    }

    save_json(OUTPUT_FILE, output)

    status = {
        "last_update": TODAY.strftime("%Y-%m-%d"),
        "period_start": START_DATE.strftime("%Y-%m-%d"),
        "period_end": TODAY.strftime("%Y-%m-%d"),
        "companies_tracked": len(companies),
        "mode": "historical_news_social_backfill_2026",
        "output_file": OUTPUT_FILE.name,
        "social_status": "not_collected",
    }

    save_json(STATUS_FILE, status)

    print("Historical News & Social 2026 backfill completed.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
