#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Intelligence Hungary
Employer Review Text Collector v4

Cél:
- Valódi dolgozói vélemény jellegű szövegek gyűjtése.
- Sajtóhírek, bérhírek, karrieroldal-címek és álláshirdetés-címek kiszűrése.
- Reddit, Google News/RSS, Profession és LinkedIn publikus említések vizsgálata.
- A nem megfelelő találatok külön excluded_items részbe kerülnek.
- Kimenet:
  docs/data/employer-review-texts.json
"""

import json
import re
import time
import random
import hashlib
import html
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
OUTPUT_FILE = DATA_DIR / "employer-review-texts.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT = 25
SLEEP_MIN = 1.5
SLEEP_MAX = 4.0
MAX_ITEMS_PER_COMPANY = 20
MAX_EXCLUDED_PER_COMPANY = 30
MAX_QUOTE_LENGTH = 420


COMPANIES = {
    "Auchan": ["Auchan Magyarország", "Auchan"],
    "Lidl": ["Lidl Magyarország", "Lidl"],
    "Aldi": ["ALDI Magyarország", "Aldi", "ALDI"],
    "Penny": ["PENNY Magyarország", "Penny Market", "PENNY", "Penny"],
    "Spar": ["SPAR Magyarország", "SPAR", "Spar"],
    "Tesco": ["Tesco Magyarország", "Tesco"],
}


TOPIC_KEYWORDS = {
    "bérezés": [
        "fizetés", "bér", "bérezés", "órabér", "kereset", "jövedelem",
        "pénz", "nettó", "bruttó", "alulfizetett", "keveset fizetnek"
    ],
    "juttatások": [
        "juttatás", "cafeteria", "bónusz", "prémium", "kedvezmény",
        "utalvány", "jutalom", "dolgozói kedvezmény"
    ],
    "munkaterhelés": [
        "sok munka", "leterhelt", "túlterhelt", "hajtás", "fárasztó",
        "kevés ember", "létszámhiány", "tempó", "pörgés", "nehéz munka",
        "széthajtják", "robotolni", "pakolni"
    ],
    "beosztás": [
        "beosztás", "műszak", "hétvége", "túlóra", "munkaidő",
        "vasárnap", "éjszaka", "szabadnap", "váltás"
    ],
    "vezetés": [
        "vezető", "főnök", "menedzser", "vezetőség", "felettes",
        "kommunikáció", "boltvezető", "irányítás", "osztályvezető"
    ],
    "csapat": [
        "csapat", "kolléga", "munkatárs", "közösség", "segítőkész",
        "összetartás", "jó hangulat", "brigád"
    ],
    "előrelépés": [
        "karrier", "előrelépés", "fejlődés", "képzés", "betanítás",
        "tanulás", "lehetőség", "előmenetel"
    ],
    "munkahelyi légkör": [
        "légkör", "stressz", "megbecsülés", "tisztelet", "hangulat",
        "konfliktus", "nyomás", "kiégés", "mérgező"
    ],
}


POSITIVE_WORDS = [
    "jó", "pozitív", "korrekt", "segítőkész", "stabil", "rugalmas",
    "barátságos", "megbecsül", "támogató", "fejlődés", "lehetőség",
    "kiszámítható", "elégedett", "szeretek", "ajánlom", "rendben van",
    "jó csapat", "jó hely"
]

NEGATIVE_WORDS = [
    "rossz", "kevés", "alacsony", "nehéz", "stressz", "túlóra",
    "leterhelt", "létszámhiány", "fárasztó", "probléma", "gyenge",
    "elégedetlen", "nyomás", "konfliktus", "kaotikus", "nem ajánlom",
    "széthajtják", "nem fizetik", "borzalmas", "kizsigerel"
]


HARD_EXCLUDE_PATTERNS = [
    r"\bbéremelés\b",
    r"\bbérfejlesztés\b",
    r"\bemeli a béreket\b",
    r"\bemel a fizetéseken\b",
    r"\bfizetésemelés\b",
    r"\bjuttatási csomag\b",
    r"\begészségprogramot indított\b",
    r"\bállások, karrier\b",
    r"\bkarrier profession\b",
    r"\bvélemények profession\.hu\b",
    r"\bértékelések profession\.hu\b",
    r"\bállás profession\.hu\b",
    r"\bálláshirdetés\b",
    r"\bállások\b",
    r"\bmunkaadója\b",
    r"\blegismertebb munkaadó\b",
    r"\bszezonális állások\b",
    r"\bfelvételét tervezik\b",
    r"\bközlemény\b",
    r"\b(x)\b",
]


NEWS_SOURCE_HINTS = [
    "hvg.hu",
    "pénzcentrum",
    "24.hu",
    "portfolio.hu",
    "blikk",
    "index.hu",
    "világgazdaság",
    "trade magazin",
    "hr portál",
    "mindmegette",
    "nool",
    "azüzlet",
    "onbrands",
]


FIRST_PERSON_REVIEW_HINTS = [
    "dolgoztam",
    "dolgozom",
    "ott dolgoztam",
    "náluk dolgoztam",
    "náluk dolgozom",
    "munkatársként",
    "eladóként",
    "pénztárosként",
    "árufeltöltőként",
    "raktárosként",
    "vezetőként",
    "szerintem",
    "tapasztalatom",
    "az én tapasztalatom",
    "nem ajánlom",
    "ajánlom",
    "felmondtam",
    "kiléptem",
    "ott hagytam",
    "ott dolgozik",
    "ismerősöm ott dolgozik",
]


WORKPLACE_REVIEW_HINTS = [
    "munkahely",
    "munkavállaló",
    "dolgozó",
    "kolléga",
    "munkatárs",
    "főnök",
    "vezető",
    "beosztás",
    "műszak",
    "túlóra",
    "fizetés",
    "bér",
    "cafeteria",
    "létszámhiány",
    "stressz",
    "munkaterhelés",
    "hangulat",
    "csapat",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_hash(text: str) -> str:
    return hashlib.sha256(clean_text(text).lower().encode("utf-8")).hexdigest()[:16]


def remove_personal_data(text: str) -> str:
    text = text or ""

    text = re.sub(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "[email eltávolítva]",
        text,
    )

    text = re.sub(
        r"(\+36|06)?[\s\-]?\(?\d{1,2}\)?[\s\-]?\d{3}[\s\-]?\d{3,4}",
        "[telefonszám eltávolítva]",
        text,
    )

    text = re.sub(
        r"\b[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]{2,}\s+"
        r"[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]{2,}\b",
        "[név eltávolítva]",
        text,
    )

    return clean_text(text)


def normalize_quote(text: str) -> str:
    text = remove_personal_data(text)

    if len(text) > MAX_QUOTE_LENGTH:
        text = text[:MAX_QUOTE_LENGTH].rsplit(" ", 1)[0] + "..."

    return text


def contains_company(text: str, company: str) -> bool:
    lower = text.lower()
    aliases = COMPANIES.get(company, [company])

    return any(alias.lower() in lower for alias in aliases)


def has_hard_exclusion(text: str) -> bool:
    lower = text.lower()

    for pattern in HARD_EXCLUDE_PATTERNS:
        if re.search(pattern, lower, flags=re.IGNORECASE):
            return True

    return False


def looks_like_news_or_pr(text: str) -> bool:
    lower = text.lower()

    news_hits = sum(1 for hint in NEWS_SOURCE_HINTS if hint in lower)

    pr_terms = [
        "jelentett be",
        "közölte",
        "tájékoztatása szerint",
        "sajtóközlemény",
        "programot indított",
        "megállapodott",
        "döntött",
        "kapnak a dolgozók",
        "minden dolgozójának üzent",
    ]

    pr_hits = sum(1 for term in pr_terms if term in lower)

    return news_hits >= 1 or pr_hits >= 1


def review_signal_score(text: str) -> int:
    lower = text.lower()

    first_person_score = sum(2 for hint in FIRST_PERSON_REVIEW_HINTS if hint in lower)
    workplace_score = sum(1 for hint in WORKPLACE_REVIEW_HINTS if hint in lower)

    opinion_terms = [
        "szerintem",
        "tapasztalat",
        "vélemény",
        "pozitívum",
        "negatívum",
        "előny",
        "hátrány",
        "jó volt",
        "rossz volt",
        "nehéz volt",
        "megérte",
        "nem érte meg",
    ]

    opinion_score = sum(1 for term in opinion_terms if term in lower)

    return first_person_score + workplace_score + opinion_score


def exclusion_reason(text: str, company: str) -> Optional[str]:
    text = clean_text(text)

    if len(text) < 90:
        return "too_short"

    if len(text.split()) < 14:
        return "too_few_words"

    if not contains_company(text, company):
        return "company_not_found"

    if has_hard_exclusion(text):
        return "hard_excluded_news_or_job_listing"

    if looks_like_news_or_pr(text):
        return "news_or_pr_content"

    score = review_signal_score(text)

    if score < 4:
        return "weak_employee_review_signal"

    return None


def is_real_employee_review(text: str, company: str) -> bool:
    return exclusion_reason(text, company) is None


def classify_topic(text: str) -> str:
    lower = text.lower()
    scores = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        scores[topic] = sum(1 for kw in keywords if kw in lower)

    best_topic = max(scores, key=scores.get)

    if scores[best_topic] == 0:
        return "általános munkáltatói tapasztalat"

    return best_topic


def classify_sentiment(text: str) -> str:
    lower = text.lower()

    pos = sum(1 for word in POSITIVE_WORDS if word in lower)
    neg = sum(1 for word in NEGATIVE_WORDS if word in lower)

    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def request_url(url: str) -> Optional[str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
    }

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f"  skipped status={response.status_code}: {url}")
            return None

        return response.text

    except Exception as error:
        print(f"  request failed: {url} | {error}")
        return None


def google_news_rss_search(query: str) -> List[Dict[str, str]]:
    encoded = quote_plus(query)
    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}&hl=hu&gl=HU&ceid=HU:hu"
    )

    xml_text = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not xml_text:
        return []

    results = []

    try:
        root = ET.fromstring(xml_text)

        for item in root.findall(".//item"):
            title = clean_text(item.findtext("title", default=""))
            link = clean_text(item.findtext("link", default=""))
            description = clean_text(item.findtext("description", default=""))
            pub_date = clean_text(item.findtext("pubDate", default=""))

            if title or description:
                results.append({
                    "title": title,
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                })

    except Exception as error:
        print(f"  RSS parse failed for query={query}: {error}")

    return results


def reddit_public_search(query: str) -> List[Dict[str, str]]:
    encoded = quote_plus(query)
    url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit=20"

    raw = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not raw:
        return []

    results = []

    try:
        data = json.loads(raw)
        children = data.get("data", {}).get("children", [])

        for child in children:
            post = child.get("data", {})
            title = clean_text(post.get("title", ""))
            selftext = clean_text(post.get("selftext", ""))
            permalink = post.get("permalink", "")
            url_full = f"https://www.reddit.com{permalink}" if permalink else ""

            combined = clean_text(f"{title}. {selftext}")

            results.append({
                "title": title,
                "link": url_full,
                "description": combined,
                "pub_date": str(post.get("created_utc", "")),
            })

    except Exception as error:
        print(f"  Reddit parse failed for query={query}: {error}")

    return results


def build_valid_item(
    company: str,
    source: str,
    source_url: str,
    raw_text: str,
    pub_date: str = "",
) -> Optional[Dict[str, Any]]:
    quote = normalize_quote(raw_text)

    reason = exclusion_reason(quote, company)
    if reason:
        return None

    return {
        "id": make_hash(company + source + source_url + quote),
        "company": company,
        "source": source,
        "source_url": source_url,
        "published_or_found_date": pub_date,
        "date_collected": now_iso(),
        "role": None,
        "topic": classify_topic(quote),
        "sentiment": classify_sentiment(quote),
        "quote": quote,
        "length": len(quote),
        "confidence": "high" if review_signal_score(quote) >= 7 else "medium",
        "privacy_note": "Személyes adatok automatikusan eltávolítva, ha felismerhetőek voltak.",
    }


def build_excluded_item(
    company: str,
    source: str,
    source_url: str,
    raw_text: str,
    reason: str,
    pub_date: str = "",
) -> Dict[str, Any]:
    quote = normalize_quote(raw_text)

    return {
        "id": make_hash("excluded" + company + source + source_url + quote),
        "company": company,
        "source": source,
        "source_url": source_url,
        "published_or_found_date": pub_date,
        "date_collected": now_iso(),
        "reason": reason,
        "quote": quote,
        "length": len(quote),
    }


def detect_source(link: str, raw_text: str) -> str:
    lower_link = link.lower()
    lower_text = raw_text.lower()

    if "profession.hu" in lower_link or "profession.hu" in lower_text:
        return "profession_via_google_news"

    if "linkedin.com" in lower_link or "linkedin.com" in lower_text:
        return "linkedin_via_google_news"

    return "google_news_rss"


def collect_google_items(company: str, aliases: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    queries = []

    for alias in aliases:
        queries.extend([
            f'"{alias}" "dolgoztam"',
            f'"{alias}" "tapasztalatom"',
            f'"{alias}" "nem ajánlom"',
            f'"{alias}" "ajánlom"',
            f'"{alias}" "fizetés" "műszak"',
            f'"{alias}" "vezető" "beosztás"',
            f'"{alias}" "dolgozói vélemény"',
            f'"{alias}" "munkavállalói vélemény"',
            f'"{alias}" site:profession.hu vélemény',
            f'"{alias}" site:linkedin.com dolgoztam',
        ])

    valid_items = []
    excluded_items = []

    for query in queries:
        print(f"  Google News RSS query: {query}")
        results = google_news_rss_search(query)

        for result in results:
            raw_text = clean_text(
                f"{result.get('title', '')}. {result.get('description', '')}"
            )

            link = result.get("link", "")
            source = detect_source(link, raw_text)
            pub_date = result.get("pub_date", "")

            reason = exclusion_reason(raw_text, company)

            if reason:
                excluded_items.append(
                    build_excluded_item(
                        company=company,
                        source=source,
                        source_url=link,
                        raw_text=raw_text,
                        reason=reason,
                        pub_date=pub_date,
                    )
                )
                continue

            item = build_valid_item(
                company=company,
                source=source,
                source_url=link,
                raw_text=raw_text,
                pub_date=pub_date,
            )

            if item:
                valid_items.append(item)

    return {
        "valid": valid_items,
        "excluded": excluded_items,
    }


def collect_reddit_items(company: str, aliases: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    queries = []

    for alias in aliases:
        queries.extend([
            f'"{alias}" dolgoztam',
            f'"{alias}" fizetés',
            f'"{alias}" műszak',
            f'"{alias}" főnök',
            f'"{alias}" nem ajánlom',
            f'"{alias}" tapasztalat',
        ])

    valid_items = []
    excluded_items = []

    for query in queries:
        print(f"  Reddit query: {query}")
        results = reddit_public_search(query)

        for result in results:
            raw_text = clean_text(
                f"{result.get('title', '')}. {result.get('description', '')}"
            )

            link = result.get("link", "")
            pub_date = result.get("pub_date", "")

            reason = exclusion_reason(raw_text, company)

            if reason:
                excluded_items.append(
                    build_excluded_item(
                        company=company,
                        source="reddit_public_search",
                        source_url=link,
                        raw_text=raw_text,
                        reason=reason,
                        pub_date=pub_date,
                    )
                )
                continue

            item = build_valid_item(
                company=company,
                source="reddit_public_search",
                source_url=link,
                raw_text=raw_text,
                pub_date=pub_date,
            )

            if item:
                valid_items.append(item)

    return {
        "valid": valid_items,
        "excluded": excluded_items,
    }


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def deduplicate_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []

    for item in items:
        key = item.get("id") or make_hash(item.get("quote", ""))

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def merge_existing_valid(existing: Dict[str, Any], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = {}

    for item in existing.get("items", []):
        item_id = item.get("id")
        if item_id:
            merged[item_id] = item

    for item in new_items:
        item_id = item.get("id")
        if item_id:
            merged[item_id] = item

    return list(merged.values())


def summarize_company(company: str, items: List[Dict[str, Any]], excluded: List[Dict[str, Any]]) -> Dict[str, Any]:
    company_items = [item for item in items if item.get("company") == company]
    company_excluded = [item for item in excluded if item.get("company") == company]

    topic_counts: Dict[str, int] = {}
    sentiment_counts = {
        "positive": 0,
        "neutral": 0,
        "negative": 0,
    }
    source_counts: Dict[str, int] = {}
    exclusion_counts: Dict[str, int] = {}

    for item in company_items:
        topic = item.get("topic", "általános munkáltatói tapasztalat")
        sentiment = item.get("sentiment", "neutral")
        source = item.get("source", "unknown")

        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

        if sentiment not in sentiment_counts:
            sentiment = "neutral"

        sentiment_counts[sentiment] += 1

    for item in company_excluded:
        reason = item.get("reason", "unknown")
        exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1

    dominant_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    dominant_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
    dominant_exclusions = sorted(exclusion_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "company": company,
        "review_text_count": len(company_items),
        "excluded_count": len(company_excluded),
        "dominant_topics": [
            {"topic": topic, "count": count}
            for topic, count in dominant_topics[:6]
        ],
        "sentiment_counts": sentiment_counts,
        "source_counts": [
            {"source": source, "count": count}
            for source, count in dominant_sources
        ],
        "exclusion_counts": [
            {"reason": reason, "count": count}
            for reason, count in dominant_exclusions
        ],
        "sample_quotes": company_items[:5],
        "sample_excluded": company_excluded[:3],
    }


def build_output(
    valid_items: List[Dict[str, Any]],
    excluded_items: List[Dict[str, Any]],
    status: str,
) -> Dict[str, Any]:
    return {
        "updated_at": now_iso(),
        "status": status,
        "source_type": "public_osint_employee_reviews",
        "method": "strict_employee_voice_filter_v4",
        "important_note": (
            "A fő items tömb csak olyan szövegeket tartalmazhat, amelyek valódi dolgozói "
            "vélemény jellegűek. A sajtóhírek, bérhírek, álláshirdetések és karrieroldal-címek "
            "az excluded_items részbe kerülnek. Az eredmény OSINT jelzés, nem reprezentatív felmérés."
        ),
        "privacy_note": (
            "A script automatikusan eltávolítja az e-mail címeket, telefonszámokat "
            "és felismerhető teljes neveket. Személyes adatot nem szabad menteni."
        ),
        "companies": [
            summarize_company(company, valid_items, excluded_items)
            for company in COMPANIES.keys()
        ],
        "items": valid_items,
        "excluded_items": excluded_items,
    }


def collect_all() -> Dict[str, List[Dict[str, Any]]]:
    all_valid = []
    all_excluded = []

    for company, aliases in COMPANIES.items():
        print(f"Collecting strict employee voice data for: {company}")

        google_result = collect_google_items(company, aliases)
        reddit_result = collect_reddit_items(company, aliases)

        company_valid = []
        company_excluded = []

        company_valid.extend(google_result["valid"])
        company_valid.extend(reddit_result["valid"])

        company_excluded.extend(google_result["excluded"])
        company_excluded.extend(reddit_result["excluded"])

        company_valid = deduplicate_items(company_valid)[:MAX_ITEMS_PER_COMPANY]
        company_excluded = deduplicate_items(company_excluded)[:MAX_EXCLUDED_PER_COMPANY]

        print(f"  valid employee reviews for {company}: {len(company_valid)}")
        print(f"  excluded non-review items for {company}: {len(company_excluded)}")

        all_valid.extend(company_valid)
        all_excluded.extend(company_excluded)

    return {
        "valid": deduplicate_items(all_valid),
        "excluded": deduplicate_items(all_excluded),
    }


def main() -> None:
    print("Strict Employer Review OSINT collector started.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_json(OUTPUT_FILE, fallback={})
    collected = collect_all()

    valid_items = merge_existing_valid(existing, collected["valid"])
    valid_items = deduplicate_items(valid_items)

    excluded_items = deduplicate_items(collected["excluded"])

    if valid_items:
        status = "ok"
    elif excluded_items:
        status = "no_valid_employee_reviews_only_excluded_items"
    else:
        status = "no_results_found"

    output = build_output(valid_items, excluded_items, status)
    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Valid employee review items: {len(valid_items)}")
    print(f"Excluded items: {len(excluded_items)}")
    print(f"Status: {status}")


if __name__ == "__main__":
    main()
