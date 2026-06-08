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


SOURCE_QUERIES = [
    "{company} élelmiszer kiskereskedelem Magyarország",
    "{company} áruház Magyarország",
    "{company} akció árak Magyarország",
    "{company} munkaerő bér állás Magyarország",
    "{company} beruházás üzletnyitás Magyarország",
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
    "startlap": 1,
    "mindmegette": 1,
    "nlc": 1
}


EVENT_TYPES = {
    "financial": [
        "árbevétel", "forgalom", "eredmény", "profit", "veszteség",
        "árrés", "árrésstop", "bevétel", "növekedés", "visszaesés"
    ],
    "expansion": [
        "új üzlet", "üzletnyitás", "áruháznyitás", "beruházás",
        "fejlesztés", "logisztikai központ", "terjeszkedés",
        "franchise hálózat", "bővítés", "nyitott"
    ],
    "promotion": [
        "akció", "kedvezmény", "olcsóbb", "leárazás", "sztártermék",
        "árak", "árverseny", "kupon", "előrendelés", "akciós újság"
    ],
    "workforce": [
        "munkaerő", "bér", "fizetés", "dolgozó", "állás",
        "sztrájk", "munkavállaló", "toborzás", "karrier"
    ],
    "regulatory": [
        "GVH", "NAV", "hatóság", "bírság", "vizsgálat",
        "plázastop", "plázabizottság", "döntés", "engedély"
    ],
    "reputation": [
        "panasz", "kritika", "visszahívás", "botrány",
        "nem örülnek", "pofont kapott", "nem építhet", "durva"
    ],
    "sustainability": [
        "fenntartható", "fenntarthatóság", "zöld", "energia",
        "napelem", "környezet", "újrahasznosítás"
    ],
    "supplier": [
        "beszállító", "hazai kkv", "termelő", "ellátási lánc",
        "hazai termék", "partner"
    ]
}


NARRATIVE_KEYWORDS = {
    "árverseny": [
        "ár", "akció", "olcsó", "infláció", "drágulás",
        "kedvezmény", "árrésstop", "leárazás"
    ],
    "munkaerő": [
        "munkaerő", "bér", "fizetés", "állás", "dolgozó",
        "sztrájk", "toborzás"
    ],
    "terjeszkedés": [
        "új üzlet", "üzletnyitás", "beruházás", "fejlesztés",
        "logisztikai központ", "franchise", "bővítés"
    ],
    "fenntarthatóság": [
        "fenntartható", "zöld", "energia", "napelem",
        "környezet", "újrahasznosítás"
    ],
    "beszállítók": [
        "beszállító", "ellátási lánc", "termelő",
        "hazai termék", "hazai kkv"
    ],
    "reputációs kockázat": [
        "bírság", "hatóság", "panasz", "botrány",
        "visszahívás", "NAV", "GVH", "nem építhet",
        "plázastop", "plázabizottság"
    ]
}


POSITIVE_WORDS = [
    "fejlesztés", "beruházás", "nyitás", "bővítés", "növekedés",
    "kedvezmény", "elismerés", "díj", "fenntartható", "támogatás",
    "szakmai díj", "nyert", "új ügyvezető", "forgalma nőtt",
    "kinyitja kapuit", "hazai kkv"
]

NEGATIVE_WORDS = [
    "bírság", "panasz", "botrány", "bezárás", "veszteség",
    "drágulás", "sztrájk", "munkaerőhiány", "visszahívás",
    "hatóság", "GVH", "NAV", "nem építhet", "pofont kapott",
    "nem örülnek", "visszaszorult", "eltűnik", "előírták",
    "vizsgálat", "plázastop", "plázabizottság"
]


DOMAIN_EXCLUDE_PATTERNS = [
    "jednota",
    "dunaszerdahely",
    "szlovák",
    "slovakia",
    "slovensko"
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


def is_bad_match(company_id, text):
    lower = text.lower()

    if company_id == "coop":
        if any(pattern in lower for pattern in DOMAIN_EXCLUDE_PATTERNS):
            return True

    return False


def classify_sentiment(text):
    lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w.lower() in lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w.lower() in lower)

    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def detect_narratives(text):
    lower = text.lower()
    found = []

    for narrative, words in NARRATIVE_KEYWORDS.items():
        if any(w.lower() in lower for w in words):
            found.append(narrative)

    return found or ["általános"]


def detect_event_type(text):
    lower = text.lower()
    scores = {}

    for event_type, words in EVENT_TYPES.items():
        score = sum(1 for w in words if w.lower() in lower)
        if score > 0:
            scores[event_type] = score

    if not scores:
        return "general"

    return max(scores.items(), key=lambda x: x[1])[0]


def detect_impact(event_type, source_weight_value, sentiment):
    score = source_weight_value

    if event_type in ["financial", "regulatory", "reputation"]:
        score += 2

    if event_type in ["expansion", "supplier"]:
        score += 1

    if sentiment == "negative":
        score += 2

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

    if "reputációs kockázat" in article["narratives"]:
        score += 20

    score += article["source_weight"] * 2

    return min(100, score)


def company_risk_score(articles):
    if not articles:
        return 0

    raw = sum(article_risk_score(a) for a in articles)
    normalized = min(100, round(raw / max(1, len(articles))))
    return normalized


def company_queries(company):
    return [q.format(company=company) for q in SOURCE_QUERIES]


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

            full_text = f"{title} {summary}"

            if is_bad_match(company_id, full_text):
                continue

            narratives = detect_narratives(full_text)
            sentiment = classify_sentiment(full_text)
            event_type = detect_event_type(full_text)
            sw = source_weight(source)
            impact = detect_impact(event_type, sw, sentiment)

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
                "impact": impact,
                "article_risk_score": 0,
                "narratives": narratives,
                "query": query
            }

            item["article_risk_score"] = article_risk_score(item)
            articles_by_id[item["id"]] = item

    articles = list(articles_by_id.values())
    articles.sort(key=lambda x: (x["published_at"], x["source_weight"]), reverse=True)

    last_7 = [
        a for a in articles
        if datetime.fromisoformat(a["published_at"]).replace(tzinfo=timezone.utc) >= TODAY - timedelta(days=7)
    ]

    sentiment_counts = {
        "positive": sum(1 for a in articles if a["sentiment"] == "positive"),
        "neutral": sum(1 for a in articles if a["sentiment"] == "neutral"),
        "negative": sum(1 for a in articles if a["sentiment"] == "negative")
    }

    narrative_counts = {}
    event_type_counts = {}

    for a in articles:
        event_type_counts[a["event_type"]] = event_type_counts.get(a["event_type"], 0) + 1

        for n in a["narratives"]:
            narrative_counts[n] = narrative_counts.get(n, 0) + 1

    dominant_narrative = max(narrative_counts.items(), key=lambda x: x[1])[0] if narrative_counts else "n.a."
    dominant_event_type = max(event_type_counts.items(), key=lambda x: x[1])[0] if event_type_counts else "n.a."

    media_impact_score = sum(a["source_weight"] for a in articles)
    high_impact_articles = [a for a in articles if a["impact"] == "high"]

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "news_count_7d": len(last_7),
        "news_count_30d": len(articles),
        "media_impact_score": media_impact_score,
        "high_impact_count": len(high_impact_articles),
        "social_mentions": None,
        "social_signal_status": "not_collected",
        "positive_count": sentiment_counts["positive"],
        "neutral_count": sentiment_counts["neutral"],
        "negative_count": sentiment_counts["negative"],
        "risk_score": company_risk_score(articles),
        "dominant_narrative": dominant_narrative,
        "dominant_event_type": dominant_event_type,
        "narratives": narrative_counts,
        "event_types": event_type_counts,
        "source_confidence": "medium" if articles else "low",
        "articles": articles[:25]
    }


def build_weekly_insight(companies):
    if not companies:
        return "Nincs elérhető híranyag az aktuális időszakban."

    by_news = sorted(companies, key=lambda x: x["news_count_30d"], reverse=True)
    by_impact = sorted(companies, key=lambda x: x["media_impact_score"], reverse=True)
    by_risk = sorted(companies, key=lambda x: x["risk_score"], reverse=True)
    by_positive = sorted(companies, key=lambda x: x["positive_count"], reverse=True)

    top_news = by_news[0]
    top_impact = by_impact[0]
    top_risk = by_risk[0]
    top_positive = by_positive[0]

    return (
        f"Az elmúlt 30 nap nyilvános hírforrásai alapján a legtöbb azonosított megjelenés "
        f"{top_news['company']} körül látható, {top_news['news_count_30d']} cikkel. "
        f"A legnagyobb médiahatás-pontszámot {top_impact['company']} érte el, "
        f"{top_impact['media_impact_score']} ponttal, amely már a forrásminőséget is figyelembe veszi. "
        f"A legmagasabb reputációs kockázati jelzés {top_risk['company']} esetében jelent meg, "
        f"{top_risk['risk_score']}/100 értékkel. "
        f"A legtöbb pozitív jellegű említés {top_positive['company']} oldalán látható. "
        f"A social media adatgyűjtés ebben a verzióban még nem aktív, ezért a social signal külön fejlesztési körben kezelendő."
    )


def top_events(companies, limit=10):
    all_articles = []

    for c in companies:
        all_articles.extend(c.get("articles", []))

    all_articles.sort(
        key=lambda a: (
            a.get("impact") == "high",
            a.get("article_risk_score", 0),
            a.get("source_weight", 0),
            a.get("published_at", "")
        ),
        reverse=True
    )

    return all_articles[:limit]


def main():
    companies = load_json(COMPANIES_FILE, [])

    if not companies:
        raise RuntimeError("Hiányzik vagy üres a docs/data/companies.json fájl.")

    collected = []

    for company in companies:
        collected.append(collect_company(company))

    output = {
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "mode": "public_news_rss_collection_v2_event_impact_risk",
        "social_status": "not_collected",
        "companies": collected,
        "weekly_insight": build_weekly_insight(collected),
        "top_events": top_events(collected),
        "notes": (
            "Az adatok Google News RSS keresésekből származó nyilvános hírmegjelenések. "
            "A sentiment, event_type, impact és risk_score mezők kulcsszavas, előzetes gépi osztályozáson alapulnak. "
            "A media_impact_score a forrás súlyát is figyelembe veszi. "
            "A social media adatok ebben a verzióban még nem kerülnek gyűjtésre."
        )
    }

    save_json(OUTPUT_FILE, output)

    history_file = HISTORY_DIR / f"{TODAY.strftime('%Y-%m')}.json"
    save_json(history_file, output)

    status = {
        "last_update": TODAY.strftime("%Y-%m-%d"),
        "companies_tracked": len(collected),
        "mode": "public_news_rss_collection_v2_event_impact_risk",
        "output_file": "news-social.json",
        "history_file": f"{TODAY.strftime('%Y-%m')}.json",
        "social_status": "not_collected"
    }

    save_json(STATUS_FILE, status)

    print("News & Social Monitor updated.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
