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
OUTPUT_FILE = DATA_DIR / "news-social.json"
STATUS_FILE = DATA_DIR / "news-social-status.json"
HISTORY_DIR = DATA_DIR / "news-social-history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.now(timezone.utc)
DAYS_BACK = 30
LAST_WEEK_DAYS = 7


SOURCE_QUERIES = [
    "{company} élelmiszer kiskereskedelem Magyarország",
    "{company} áruház Magyarország",
    "{company} akció árak Magyarország",
    "{company} munkaerő bér állás Magyarország",
    "{company} beruházás üzletnyitás Magyarország",
    "{company} hatóság bírság GVH NAV Magyarország",
    "{company} beszállító logisztika Magyarország",
]


SOURCE_WEIGHTS = {
    "portfolio.hu": 5,
    "portfolio": 5,
    "telex": 5,
    "hvg": 5,
    "világgazdaság": 4,
    "vg": 4,
    "trade magazin": 4,
    "piac&profit": 4,
    "piac profit": 4,
    "store insider": 3,
    "pénzcentrum": 2,
    "24.hu": 3,
    "economx": 3,
    "haszon": 3,
    "forbes": 3,
    "agrárszektor": 2,
    "media1": 2,
    "növekedés.hu": 2,
    "heol": 2,
    "feol": 2,
    "origo": 2,
    "startlap": 1,
    "mindmegette": 1,
    "nlc": 1,
}


EVENT_TYPES = {
    "financial": [
        "árbevétel", "forgalom", "forgalma", "forgalma nőtt",
        "forgalma emelkedett", "eredmény", "profit", "veszteség",
        "árrés", "árrésstop", "bevétel", "árbevétele", "árbevétele nőtt",
        "növekedés", "visszaesés", "milliárd", "milliárd forint",
        "forintra nőtt", "mínuszban", "minuszban", "veszteséges",
        "legnagyobb forgalmú", "piacvezető", "vezető szerep",
        "elsőség", "részesedés", "piaci részesedés", "helyezett",
        "helyen végzett", "rangsor",
    ],
    "expansion": [
        "új üzlet", "üzletnyitás", "áruháznyitás", "beruházás",
        "fejlesztés", "logisztikai központ", "terjeszkedés",
        "franchise hálózat", "franchise", "bővítés", "bővült",
        "nyitott", "újra kinyitott", "kinyitott", "új áruház",
        "új üzletformátum",
    ],
    "promotion": [
        "akció", "kedvezmény", "olcsóbb", "leárazás", "sztártermék",
        "árak", "árverseny", "kupon", "előrendelés", "akciós újság",
        "fél áron", "37 százalékkal", "43 százalékkal", "árengedmény",
    ],
    "workforce": [
        "munkaerő", "bér", "fizetés", "dolgozó", "állás",
        "sztrájk", "munkavállaló", "toborzás", "karrier",
        "munkaerőpiac", "kasszás", "pénztáros",
    ],
    "regulatory": [
        "GVH", "NAV", "hatóság", "bírság", "vizsgálat",
        "plázastop", "plázabizottság", "döntés", "engedély",
        "nem építhet", "előírták", "hatósági",
    ],
    "reputation": [
        "panasz", "kritika", "visszahívás", "botrány",
        "nem örülnek", "pofont kapott", "durva", "áll a bál",
        "falnak ment",
    ],
    "sustainability": [
        "fenntartható", "fenntarthatóság", "zöld", "energia",
        "napelem", "környezet", "újrahasznosítás",
    ],
    "supplier": [
        "beszállító", "hazai kkv", "kkv", "termelő", "ellátási lánc",
        "hazai termék", "partner", "logisztika", "magyar termelő",
        "hazai beszállító",
    ],
}


BUSINESS_IMPACT = {
    "revenue": [
        "akció", "árverseny", "forgalom", "forgalma", "forgalma nőtt",
        "forgalma emelkedett", "árbevétel", "árbevétele", "árbevétele nőtt",
        "bevétel", "kedvezmény", "leárazás", "árrés", "árrésstop",
        "legnagyobb forgalmú", "milliárd forint", "piacvezető",
        "részesedés", "piaci részesedés", "elsőség",
        "növelte részesedését", "rangsor", "helyezett",
    ],
    "cost": [
        "bér", "energia", "infláció", "költség", "munkaerőhiány",
        "veszteség", "mínuszban", "minuszban", "veszteséges",
        "falnak ment",
    ],
    "reputation": [
        "panasz", "bírság", "visszahívás", "botrány", "pofont kapott",
        "nem örülnek", "áll a bál", "kritika", "durva",
    ],
    "expansion": [
        "új üzlet", "üzletnyitás", "áruháznyitás", "beruházás",
        "terjeszkedés", "franchise", "bővítés", "bővült",
        "nyitott", "újra kinyitott", "új áruház", "új üzletformátum",
    ],
    "regulation": [
        "GVH", "NAV", "hatóság", "plázastop", "plázabizottság",
        "engedély", "nem építhet", "döntés", "bírság", "vizsgálat",
    ],
    "supply_chain": [
        "beszállító", "ellátási lánc", "készlethiány",
        "hazai kkv", "kkv", "logisztika", "termelő",
        "magyar termelő", "hazai beszállító", "hazai termék",
    ],
    "workforce": [
        "munkaerő", "bér", "fizetés", "dolgozó", "állás",
        "sztrájk", "munkavállaló", "toborzás", "karrier",
        "kasszás", "pénztáros",
    ],
}


STRATEGIC_NARRATIVES = {
    "growth": [
        "beruházás", "új üzlet", "üzletnyitás", "terjeszkedés",
        "franchise", "bővítés", "bővült", "újra kinyitott",
        "nyitott", "forgalma nőtt", "piacvezető", "elsőség",
        "vezető szerep", "növelte részesedését", "helyezett",
        "rekord", "legnagyobb forgalmú",
    ],
    "competition": [
        "akció", "árverseny", "kedvezmény", "olcsóbb",
        "leárazás", "árrésstop", "sztártermék", "részesedés",
        "piaci verseny", "verseny", "megelőzte", "visszaszorult",
        "elsőség", "piacvezető", "rangsor",
    ],
    "reputation": [
        "panasz", "botrány", "visszahívás", "pofont kapott",
        "nem örülnek", "áll a bál", "kritika", "durva",
    ],
    "workforce": [
        "munkaerő", "bér", "toborzás", "állás", "dolgozó",
        "munkaerőpiac", "kasszás", "pénztáros",
    ],
    "supply_chain": [
        "beszállító", "logisztika", "ellátási lánc", "hazai kkv",
        "kkv", "termelő", "magyar termelő", "hazai termék",
    ],
    "regulation": [
        "GVH", "NAV", "hatóság", "plázastop",
        "plázabizottság", "engedély", "nem építhet", "bírság",
        "vizsgálat",
    ],
    "defensive": [
        "veszteség", "bezárás", "költségcsökkentés",
        "visszaesés", "eltűnik", "mínuszban", "minuszban",
        "veszteséges", "falnak ment", "visszaszorult",
    ],
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


POSITIVE_WORDS = [
    "fejlesztés", "beruházás", "nyitás", "bővítés", "bővült",
    "növekedés", "kedvezmény", "elismerés", "díj", "fenntartható",
    "támogatás", "szakmai díj", "nyert", "új ügyvezető",
    "forgalma nőtt", "kinyitja kapuit", "hazai kkv", "újra kinyitott",
    "vezetése bővült", "piacvezető", "elsőség",
]

NEGATIVE_WORDS = [
    "bírság", "panasz", "botrány", "bezárás", "veszteség",
    "drágulás", "sztrájk", "munkaerőhiány", "visszahívás",
    "hatóság", "GVH", "NAV", "nem építhet", "pofont kapott",
    "nem örülnek", "visszaszorult", "eltűnik", "előírták",
    "vizsgálat", "plázastop", "plázabizottság", "áll a bál",
    "falnak ment", "mínuszban", "minuszban", "veszteséges",
]


DOMAIN_EXCLUDE_PATTERNS = [
    "jednota",
    "dunaszerdahely",
    "szlovák",
    "slovakia",
    "slovensko",
]


NON_SPECIFIC_TITLE_PATTERNS = [
    "meddig marad még egyensúlyban a munkaerőpiac",
    "munkaerőpiac?",
    "munkaerőpiac ?",
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


def normalize_text(text):
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
    if not source:
        return 1
    lower = source.lower()
    for key, weight in SOURCE_WEIGHTS.items():
        if key in lower:
            return weight
    return 2


def is_bad_match(company_id, company_name, title, summary):
    full_text = normalize_text(f"{title} {summary}")
    title_lower = normalize_text(title)
    company_lower = normalize_text(company_name)

    if company_id == "coop":
        if any(pattern in full_text for pattern in DOMAIN_EXCLUDE_PATTERNS):
            return True

    if any(pattern in title_lower for pattern in NON_SPECIFIC_TITLE_PATTERNS):
        if company_lower not in title_lower:
            return True

    if company_lower not in full_text:
        return True

    return False


def score_dictionary(text, dictionary):
    lower = normalize_text(text)
    scores = {}
    for category, words in dictionary.items():
        score = sum(1 for w in words if w.lower() in lower)
        if score > 0:
            scores[category] = score
    return scores


def detect_best_category(text, dictionary, default="general", min_score=1):
    scores = score_dictionary(text, dictionary)
    if not scores:
        return default
    best_key = max(scores, key=scores.get)
    if scores[best_key] < min_score:
        return default
    return best_key


def classify_sentiment(text):
    lower = normalize_text(text)
    pos = sum(1 for w in POSITIVE_WORDS if w.lower() in lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w.lower() in lower)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def detect_event_type(text):
    return detect_best_category(text, EVENT_TYPES, "general", min_score=1)


def detect_business_impact(text):
    return detect_best_category(text, BUSINESS_IMPACT, "general", min_score=1)


def detect_strategic_narrative(text):
    return detect_best_category(text, STRATEGIC_NARRATIVES, "general", min_score=1)


def detect_impact_level(event_type, business_impact, strategic_narrative, source_weight_value, sentiment):
    score = source_weight_value

    if event_type in ["financial", "regulatory", "reputation"]:
        score += 2
    if business_impact in ["regulation", "reputation", "cost"]:
        score += 2
    if strategic_narrative in ["regulation", "reputation", "defensive"]:
        score += 2
    if event_type in ["expansion", "supplier"]:
        score += 1
    if business_impact in ["expansion", "supply_chain", "revenue"]:
        score += 1
    if strategic_narrative in ["growth", "competition", "supply_chain"]:
        score += 1
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


def company_risk_score(articles):
    if not articles:
        return 0
    raw = sum(article_risk_score(a) for a in articles)
    normalized = round(raw / max(1, len(articles)))
    high_risk_bonus = sum(1 for a in articles if a.get("impact") in ["high", "critical"]) * 5
    negative_bonus = sum(1 for a in articles if a.get("sentiment") == "negative") * 4
    return min(100, normalized + high_risk_bonus + negative_bonus)


def company_queries(company):
    return [q.format(company=company) for q in SOURCE_QUERIES]


def count_values(articles, field):
    result = {}
    for article in articles:
        value = article.get(field, "general")
        result[value] = result.get(value, 0) + 1
    return result


def dominant_from_counts(counts, ignore_general=False):
    if not counts:
        return "n.a."
    cleaned = dict(counts)
    if ignore_general:
        cleaned.pop("general", None)
        cleaned.pop("n.a.", None)
    if not cleaned:
        return "general" if "general" in counts else "n.a."
    return max(cleaned.items(), key=lambda x: x[1])[0]


def normalize_index(value, max_value):
    if not max_value or max_value <= 0:
        return 0
    return round(min(100, (value / max_value) * 100), 1)


def trend_direction(articles):
    now_count = 0
    prev_count = 0
    now_start = TODAY - timedelta(days=LAST_WEEK_DAYS)
    prev_start = TODAY - timedelta(days=LAST_WEEK_DAYS * 2)

    for article in articles:
        try:
            d = datetime.fromisoformat(article["published_at"]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if d >= now_start:
            now_count += 1
        elif prev_start <= d < now_start:
            prev_count += 1

    if now_count > prev_count:
        return "up"
    if now_count < prev_count:
        return "down"
    return "stable"


def highlight_event(articles):
    if not articles:
        return None

    impact_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    sorted_articles = sorted(
        articles,
        key=lambda a: (
            impact_rank.get(a.get("impact", "low"), 1),
            a.get("article_risk_score", 0),
            a.get("source_weight", 0),
            a.get("published_at", ""),
        ),
        reverse=True,
    )
    return sorted_articles[0]


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

            if published_at < TODAY - timedelta(days=DAYS_BACK):
                continue
            if is_bad_match(company_id, company_name, title, summary):
                continue

            full_text = f"{title} {summary}"
            sentiment = classify_sentiment(full_text)
            event_type = detect_event_type(full_text)
            business_impact = detect_business_impact(full_text)
            strategic_narrative = detect_strategic_narrative(full_text)
            sw = source_weight(source)
            impact_level = detect_impact_level(event_type, business_impact, strategic_narrative, sw, sentiment)

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
                "strategic_narrative": strategic_narrative,
                "strategic_narrative_label": NARRATIVE_LABELS.get(strategic_narrative, strategic_narrative),
                "impact": impact_level,
                "article_risk_score": 0,
                "query": query,
            }
            item["article_risk_score"] = article_risk_score(item)
            articles_by_id[item["id"]] = item

    articles = list(articles_by_id.values())
    articles.sort(key=lambda x: (x["published_at"], x["source_weight"]), reverse=True)

    last_7 = [
        a for a in articles
        if datetime.fromisoformat(a["published_at"]).replace(tzinfo=timezone.utc) >= TODAY - timedelta(days=LAST_WEEK_DAYS)
    ]

    sentiment_counts = count_values(articles, "sentiment")
    event_type_counts = count_values(articles, "event_type")
    business_impact_counts = count_values(articles, "business_impact")
    strategic_narrative_counts = count_values(articles, "strategic_narrative")

    dominant_event_type = dominant_from_counts(event_type_counts, ignore_general=True)
    dominant_business_impact = dominant_from_counts(business_impact_counts, ignore_general=True)
    dominant_strategic_narrative = dominant_from_counts(strategic_narrative_counts, ignore_general=True)

    media_impact_score = sum(a["source_weight"] for a in articles)
    high_impact_articles = [a for a in articles if a["impact"] in ["high", "critical"]]
    risk_score = company_risk_score(articles)
    top_event = highlight_event(articles)

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "news_count_7d": len(last_7),
        "news_count_30d": len(articles),
        "media_impact_score": media_impact_score,
        "media_index": 0,
        "news_index": 0,
        "social_index": 0,
        "social_signal_status": "not_collected",
        "risk_score": risk_score,
        "risk_index": risk_score,
        "high_impact_count": len(high_impact_articles),
        "critical_impact_count": sum(1 for a in articles if a["impact"] == "critical"),
        "positive_count": sentiment_counts.get("positive", 0),
        "neutral_count": sentiment_counts.get("neutral", 0),
        "negative_count": sentiment_counts.get("negative", 0),
        "dominant_event_type": dominant_event_type,
        "dominant_business_impact": dominant_business_impact,
        "dominant_business_impact_label": BUSINESS_IMPACT_LABELS.get(dominant_business_impact, dominant_business_impact),
        "dominant_strategic_narrative": dominant_strategic_narrative,
        "dominant_strategic_narrative_label": NARRATIVE_LABELS.get(dominant_strategic_narrative, dominant_strategic_narrative),
        "dominant_market_narrative": NARRATIVE_LABELS.get(dominant_strategic_narrative, dominant_strategic_narrative),
        "highlight_event": top_event["title"] if top_event else "n.a.",
        "highlight_event_source": top_event["source"] if top_event else "n.a.",
        "highlight_event_date": top_event["published_at"] if top_event else "n.a.",
        "trend_direction": trend_direction(articles),
        "event_types": event_type_counts,
        "business_impacts": business_impact_counts,
        "strategic_narratives": strategic_narrative_counts,
        "source_confidence": "medium" if articles else "low",
        "articles": articles[:25],
    }


def apply_indices(companies):
    max_media = max([c.get("media_impact_score", 0) for c in companies], default=0)
    max_news = max([c.get("news_count_30d", 0) for c in companies], default=0)

    for company in companies:
        company["media_index"] = normalize_index(company.get("media_impact_score", 0), max_media)
        company["news_index"] = normalize_index(company.get("news_count_30d", 0), max_news)
        company["social_index"] = 0
        company["risk_index"] = company.get("risk_score", 0)
    return companies


def top_events(companies, limit=10):
    all_articles = []
    for company in companies:
        all_articles.extend(company.get("articles", []))

    impact_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    all_articles.sort(
        key=lambda a: (
            impact_rank.get(a.get("impact", "low"), 1),
            a.get("article_risk_score", 0),
            a.get("source_weight", 0),
            a.get("published_at", ""),
        ),
        reverse=True,
    )
    return all_articles[:limit]


def aggregate_counts(companies, field):
    result = {}
    for company in companies:
        counts = company.get(field, {})
        for key, value in counts.items():
            result[key] = result.get(key, 0) + value
    return result


def build_executive_intelligence(companies):
    if not companies:
        return {
            "market_situation": "Nincs elérhető híranyag az aktuális időszakban.",
            "main_risk": "Nincs értékelhető kockázati jel.",
            "main_event": "Nincs kiemelhető esemény.",
            "expected_trend": "Trend még nem állapítható meg.",
        }

    by_media = sorted(companies, key=lambda x: x.get("media_index", 0), reverse=True)
    by_risk = sorted(companies, key=lambda x: x.get("risk_index", 0), reverse=True)
    by_high_impact = sorted(companies, key=lambda x: x.get("high_impact_count", 0), reverse=True)

    all_business = aggregate_counts(companies, "business_impacts")
    all_narratives = aggregate_counts(companies, "strategic_narratives")
    dominant_business = dominant_from_counts(all_business, ignore_general=True)
    dominant_narrative = dominant_from_counts(all_narratives, ignore_general=True)

    top_media = by_media[0]
    top_risk = by_risk[0]
    top_high = by_high_impact[0]

    business_label = BUSINESS_IMPACT_LABELS.get(dominant_business, dominant_business)
    narrative_label = NARRATIVE_LABELS.get(dominant_narrative, dominant_narrative)

    return {
        "market_situation": (
            f"Az elmúlt 30 nap médiaképe alapján a legerősebb üzleti hatás '{business_label}' kategóriában jelent meg. "
            f"A stratégiai narratívák közül a '{narrative_label}' dominált. "
            f"A legnagyobb médiaindexet {top_media['company']} érte el ({top_media['media_index']}/100)."
        ),
        "main_risk": (
            f"A legmagasabb reputációs és üzleti kockázati jelzés {top_risk['company']} esetében látható, "
            f"{top_risk['risk_index']}/100 értékkel. A kockázati pontszám a negatív, szabályozási, reputációs és költséghatású híreket súlyozza."
        ),
        "main_event": (
            f"A legtöbb magas hatású esemény {top_high['company']} körül jelent meg ({top_high['high_impact_count']} darab). "
            f"Ezek a hírek nagyobb üzleti vagy reputációs figyelmet indokolnak, mint az egyszerű promóciós megjelenések."
        ),
        "expected_trend": (
            f"A következő hetekben várhatóan a '{narrative_label}' és '{business_label}' témák maradhatnak meghatározók. "
            f"A social media adatgyűjtés továbbra sem aktív, ezért a társadalmi visszhangot külön fejlesztési körben kell kezelni."
        ),
    }


def build_weekly_insight(companies):
    if not companies:
        return "Nincs elérhető híranyag az aktuális időszakban."

    by_news = sorted(companies, key=lambda x: x.get("news_count_30d", 0), reverse=True)
    by_media = sorted(companies, key=lambda x: x.get("media_index", 0), reverse=True)
    by_risk = sorted(companies, key=lambda x: x.get("risk_index", 0), reverse=True)
    by_high = sorted(companies, key=lambda x: x.get("high_impact_count", 0), reverse=True)

    return (
        f"Az elmúlt 30 nap nyilvános hírforrásai alapján a legtöbb azonosított megjelenés "
        f"{by_news[0]['company']} körül látható, {by_news[0]['news_count_30d']} cikkel. "
        f"A legnagyobb médiaindexet {by_media[0]['company']} érte el, {by_media[0]['media_index']}/100 értékkel. "
        f"A legmagasabb reputációs kockázati jelzés {by_risk[0]['company']} esetében jelent meg, "
        f"{by_risk[0]['risk_index']}/100 értékkel. "
        f"A legtöbb magas hatású esemény {by_high[0]['company']} körül azonosítható. "
        f"A social media adatgyűjtés ebben a verzióban még nem aktív."
    )


def data_quality_summary(companies):
    company_count = len(companies)
    with_news = sum(1 for c in companies if c.get("news_count_30d", 0) > 0)
    with_impact = sum(1 for c in companies if c.get("media_index", 0) > 0)
    with_risk = sum(1 for c in companies if c.get("risk_index", 0) > 0)
    with_business = sum(1 for c in companies if c.get("dominant_business_impact") not in [None, "n.a."])
    with_narrative = sum(1 for c in companies if c.get("dominant_strategic_narrative") not in [None, "n.a."])

    def p(x):
        return round((x / company_count) * 100) if company_count else 0

    return {
        "news_coverage_pct": p(with_news),
        "impact_coverage_pct": p(with_impact),
        "risk_coverage_pct": p(with_risk),
        "business_impact_coverage_pct": p(with_business),
        "strategic_narrative_coverage_pct": p(with_narrative),
        "social_coverage_pct": 0,
        "classification_method": "keyword_based_v4_index_model",
        "notes": "A news_index, media_index, risk_index, business impact és strategic narrative mezők kulcsszavas, forrássúlyozott gépi osztályozáson alapulnak. A social index jelenleg 0, mert nincs bekötött social adatgyűjtés.",
    }


def build_summary(companies):
    if not companies:
        return {}

    by_media = sorted(companies, key=lambda c: c.get("media_index", 0), reverse=True)
    by_news = sorted(companies, key=lambda c: c.get("news_index", 0), reverse=True)
    by_risk = sorted(companies, key=lambda c: c.get("risk_index", 0), reverse=True)

    total_news = sum(c.get("news_count_30d", 0) for c in companies)
    total_media_score = sum(c.get("media_impact_score", 0) for c in companies)
    total_high = sum(c.get("high_impact_count", 0) for c in companies)
    total_critical = sum(c.get("critical_impact_count", 0) for c in companies)

    narratives = aggregate_counts(companies, "strategic_narratives")
    business = aggregate_counts(companies, "business_impacts")
    dominant_narrative = dominant_from_counts(narratives, ignore_general=True)
    dominant_business = dominant_from_counts(business, ignore_general=True)

    return {
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "total_news_30d": total_news,
        "total_media_score": total_media_score,
        "total_high_impact_events": total_high,
        "total_critical_events": total_critical,
        "media_impact_leader": by_media[0]["company"],
        "media_impact_leader_index": by_media[0].get("media_index", 0),
        "news_leader": by_news[0]["company"],
        "news_leader_index": by_news[0].get("news_index", 0),
        "risk_leader": by_risk[0]["company"],
        "risk_leader_index": by_risk[0].get("risk_index", 0),
        "social_leader": "n.a.",
        "social_leader_index": 0,
        "dominant_market_narrative": NARRATIVE_LABELS.get(dominant_narrative, dominant_narrative),
        "dominant_business_impact": BUSINESS_IMPACT_LABELS.get(dominant_business, dominant_business),
        "social_status": "not_collected",
    }


def main():
    companies = load_json(COMPANIES_FILE, [])
    if not companies:
        raise RuntimeError("Hiányzik vagy üres a docs/data/companies.json fájl.")

    collected = [collect_company(company) for company in companies]
    collected = apply_indices(collected)

    events = top_events(collected)
    summary = build_summary(collected)

    output = {
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "mode": "public_news_rss_collection_v4_index_model",
        "social_status": "not_collected",
        "summary": summary,
        "companies": collected,
        "events": events,
        "top_events": events,
        "weekly_insight": build_weekly_insight(collected),
        "executive_intelligence": build_executive_intelligence(collected),
        "data_quality": data_quality_summary(collected),
        "labels": {
            "business_impact": BUSINESS_IMPACT_LABELS,
            "strategic_narrative": NARRATIVE_LABELS,
        },
        "notes": (
            "Az adatok Google News RSS keresésekből származó nyilvános hírmegjelenések. "
            "A news_index, media_index, risk_index, business_impact, strategic_narrative, impact és risk_score mezők "
            "kulcsszavas, előzetes gépi osztályozáson alapulnak. "
            "A social_index jelenleg 0, mert nincs aktív social adatgyűjtés."
        ),
    }

    save_json(OUTPUT_FILE, output)

    history_file = HISTORY_DIR / f"{TODAY.strftime('%Y-%m')}.json"
    save_json(history_file, output)

    status = {
        "last_update": TODAY.strftime("%Y-%m-%d"),
        "companies_tracked": len(collected),
        "mode": "public_news_rss_collection_v4_index_model",
        "output_file": "news-social.json",
        "history_file": f"{TODAY.strftime('%Y-%m')}.json",
        "social_status": "not_collected",
    }
    save_json(STATUS_FILE, status)

    print("News & Reputation Monitor V4 updated.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

