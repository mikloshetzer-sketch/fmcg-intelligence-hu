#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Employee Review Collector v6
Cél: valódi dolgozói vélemények gyűjtése.

Forráslogika:
- Reddit publikus JSON keresés
- DuckDuckGo HTML keresés publikus oldalakhoz
- Profession / Reddit / GyakoriKérdések / fórum találatok
- kézi URL-lista

Google News és LinkedIn nincs használatban.
"""

import json
import re
import time
import random
import hashlib
import html
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
OUTPUT_FILE = DATA_DIR / "employer-review-texts.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

REQUEST_TIMEOUT = 25
SLEEP_MIN = 2.0
SLEEP_MAX = 5.0

MAX_SEARCH_RESULTS_PER_QUERY = 8
MAX_ITEMS_PER_COMPANY = 30
MAX_EXCLUDED_PER_COMPANY = 60
MAX_QUOTE_LENGTH = 520


COMPANIES = {
    "Auchan": ["Auchan", "Auchan Magyarország"],
    "Lidl": ["Lidl", "Lidl Magyarország"],
    "Aldi": ["Aldi", "ALDI", "ALDI Magyarország"],
    "Penny": ["Penny", "PENNY", "Penny Market", "PENNY Magyarország"],
    "Spar": ["Spar", "SPAR", "SPAR Magyarország"],
    "Tesco": ["Tesco", "Tesco Magyarország"],
}


MANUAL_REVIEW_URLS = {
    "Auchan": [],
    "Lidl": [],
    "Aldi": [],
    "Penny": [],
    "Spar": [],
    "Tesco": [],
}


ALLOWED_DISCOVERY_DOMAINS = [
    "reddit.com",
    "old.reddit.com",
    "profession.hu",
    "gyakorikerdesek.hu",
    "forum.index.hu",
    "hoxa.hu",
]


EXCLUDED_DOMAINS = [
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "news.google.com",
]


NEWS_TERMS = [
    "béremelés",
    "bérfejlesztés",
    "emeli a béreket",
    "emel a fizetéseken",
    "fizetésemelés",
    "juttatási csomag",
    "álláshirdetés",
    "állások",
    "karrier",
    "szezonális állások",
    "felvételét tervezik",
    "sajtóközlemény",
    "hvg.hu",
    "pénzcentrum",
    "portfolio.hu",
    "24.hu",
    "blikk",
    "index.hu",
    "világgazdaság",
    "trade magazin",
    "hr portál",
    "onbrands",
    "mindmegette",
    "nool",
]


REVIEW_STRONG_SIGNALS = [
    "dolgoztam",
    "dolgozom",
    "ott dolgoztam",
    "ott dolgozom",
    "náluk dolgoztam",
    "náluk dolgozom",
    "munkatársként",
    "eladóként",
    "pénztárosként",
    "árufeltöltőként",
    "raktárosként",
    "vezetőként",
    "tapasztalatom",
    "saját tapasztalat",
    "felmondtam",
    "kiléptem",
    "nem ajánlom",
    "ajánlom",
]


REVIEW_WEAK_SIGNALS = [
    "munkahely",
    "munkavállaló",
    "dolgozó",
    "munkatárs",
    "kolléga",
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
    "vélemény",
    "értékelés",
    "tapasztalat",
]


TOPIC_KEYWORDS = {
    "bérezés": ["fizetés", "bér", "bérezés", "órabér", "kereset", "nettó", "bruttó", "pénz"],
    "juttatások": ["cafeteria", "juttatás", "bónusz", "prémium", "kedvezmény", "utalvány"],
    "munkaterhelés": ["sok munka", "leterhelt", "túlterhelt", "hajtás", "fárasztó", "kevés ember", "létszámhiány", "tempó", "pörgés"],
    "beosztás": ["beosztás", "műszak", "hétvége", "túlóra", "munkaidő", "éjszaka", "vasárnap", "szabadnap"],
    "vezetés": ["vezető", "főnök", "menedzser", "felettes", "boltvezető", "osztályvezető", "vezetőség"],
    "csapat": ["csapat", "kolléga", "munkatárs", "közösség", "brigád", "jó hangulat"],
    "előrelépés": ["karrier", "előrelépés", "fejlődés", "betanítás", "képzés", "előmenetel"],
    "munkahelyi légkör": ["stressz", "légkör", "hangulat", "megbecsülés", "nyomás", "konfliktus", "kiégés"],
}


POSITIVE_WORDS = ["jó", "korrekt", "pozitív", "segítőkész", "stabil", "rugalmas", "elégedett", "ajánlom", "jó csapat", "jó hely"]
NEGATIVE_WORDS = ["rossz", "kevés", "alacsony", "nehéz", "stressz", "túlóra", "létszámhiány", "fárasztó", "nem ajánlom", "felmondtam", "borzalmas"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_hash(text: str) -> str:
    return hashlib.sha256(clean_text(text).lower().encode("utf-8")).hexdigest()[:16]


def normalize_url(url: str) -> str:
    if not url:
        return ""

    if "duckduckgo.com/l/" in url or url.startswith("/l/"):
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "uddg" in params:
            return unquote(params["uddg"][0])

    return url


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_allowed_domain(url: str) -> bool:
    domain = domain_of(url)

    if any(blocked in domain for blocked in EXCLUDED_DOMAINS):
        return False

    return any(allowed in domain for allowed in ALLOWED_DISCOVERY_DOMAINS)


def remove_personal_data(text: str) -> str:
    text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[email eltávolítva]", text or "")
    text = re.sub(r"(\+36|06)?[\s\-]?\(?\d{1,2}\)?[\s\-]?\d{3}[\s\-]?\d{3,4}", "[telefonszám eltávolítva]", text)
    return clean_text(text)


def normalize_quote(text: str) -> str:
    text = remove_personal_data(text)

    if len(text) > MAX_QUOTE_LENGTH:
        text = text[:MAX_QUOTE_LENGTH].rsplit(" ", 1)[0] + "..."

    return text


def contains_company(text: str, company: str) -> bool:
    lower = text.lower()
    return any(alias.lower() in lower for alias in COMPANIES.get(company, [company]))


def has_news_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in NEWS_TERMS)


def review_score(text: str) -> int:
    lower = text.lower()
    score = 0
    score += sum(3 for signal in REVIEW_STRONG_SIGNALS if signal in lower)
    score += sum(1 for signal in REVIEW_WEAK_SIGNALS if signal in lower)
    if "?" in text:
        score += 1
    return score


def exclusion_reason(text: str, company: str) -> Optional[str]:
    text = clean_text(text)

    if len(text) < 70:
        return "too_short"

    if len(text.split()) < 10:
        return "too_few_words"

    if not contains_company(text, company):
        return "company_not_found"

    if has_news_terms(text):
        return "news_or_job_content"

    if review_score(text) < 4:
        return "weak_review_signal"

    return None


def classify_topic(text: str) -> str:
    lower = text.lower()
    scores = {topic: sum(1 for keyword in keywords if keyword in lower) for topic, keywords in TOPIC_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "általános munkáltatói tapasztalat"


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


def duckduckgo_search(query: str) -> List[Dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html_text = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    results = []

    for result in soup.select(".result"):
        title_node = result.select_one(".result__a")
        snippet_node = result.select_one(".result__snippet")

        if not title_node:
            continue

        href = normalize_url(title_node.get("href", ""))
        title = clean_text(title_node.get_text(" ", strip=True))
        snippet = clean_text(snippet_node.get_text(" ", strip=True)) if snippet_node else ""

        if not href or not is_allowed_domain(href):
            continue

        results.append({
            "title": title,
            "snippet": snippet,
            "url": href,
        })

        if len(results) >= MAX_SEARCH_RESULTS_PER_QUERY:
            break

    return results


def reddit_search(query: str) -> List[Dict[str, str]]:
    url = f"https://www.reddit.com/search.json?q={quote_plus(query)}&sort=new&limit=25"
    raw = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not raw:
        return []

    results = []

    try:
        data = json.loads(raw)
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = clean_text(post.get("title", ""))
            body = clean_text(post.get("selftext", ""))
            permalink = post.get("permalink", "")
            link = f"https://www.reddit.com{permalink}" if permalink else ""

            if title or body:
                results.append({
                    "title": title,
                    "snippet": body,
                    "url": link,
                    "date": str(post.get("created_utc", "")),
                })
    except Exception as error:
        print(f"  reddit parse failed: {query} | {error}")

    return results


def extract_text_blocks_from_page(url: str) -> List[str]:
    html_text = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    selectors = [
        "article",
        ".review",
        ".reviews",
        ".comment",
        ".opinion",
        ".rating",
        ".description",
        ".content",
        "[class*='review']",
        "[class*='comment']",
        "[class*='opinion']",
        "p",
        "li",
    ]

    blocks = []
    seen = set()

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            key = make_hash(text)

            if key in seen:
                continue

            seen.add(key)

            if len(text) >= 60:
                blocks.append(text)

    return blocks


def build_item(company: str, source: str, url: str, raw_text: str, date: str = "") -> Optional[Dict[str, Any]]:
    quote = normalize_quote(raw_text)
    reason = exclusion_reason(quote, company)

    if reason:
        return None

    score = review_score(quote)

    return {
        "id": make_hash(company + source + url + quote),
        "company": company,
        "source": source,
        "source_url": url,
        "published_or_found_date": date,
        "date_collected": now_iso(),
        "topic": classify_topic(quote),
        "sentiment": classify_sentiment(quote),
        "quote": quote,
        "length": len(quote),
        "review_signal_score": score,
        "confidence": "high" if score >= 8 else "medium",
        "privacy_note": "Személyes adatok automatikusan eltávolítva, ha felismerhetőek voltak.",
    }


def build_excluded_item(company: str, source: str, url: str, raw_text: str, reason: str) -> Dict[str, Any]:
    quote = normalize_quote(raw_text)

    return {
        "id": make_hash("excluded" + company + source + url + quote),
        "company": company,
        "source": source,
        "source_url": url,
        "date_collected": now_iso(),
        "reason": reason,
        "quote": quote,
        "length": len(quote),
    }


def process_candidate_text(company: str, source: str, url: str, text: str, valid: List[Dict[str, Any]], excluded: List[Dict[str, Any]]) -> None:
    reason = exclusion_reason(text, company)

    if reason:
        excluded.append(build_excluded_item(company, source, url, text, reason))
        return

    item = build_item(company, source, url, text)

    if item:
        valid.append(item)


def collect_company(company: str, aliases: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    valid = []
    excluded = []

    search_queries = []

    for alias in aliases:
        search_queries.extend([
            f'site:reddit.com "{alias}" dolgoztam',
            f'site:reddit.com "{alias}" fizetés',
            f'site:reddit.com "{alias}" műszak',
            f'site:reddit.com "{alias}" nem ajánlom',
            f'site:profession.hu "{alias}" vélemények',
            f'site:profession.hu "{alias}" értékelések',
            f'site:gyakorikerdesek.hu "{alias}" munka',
            f'site:forum.index.hu "{alias}" munka',
            f'site:hoxa.hu "{alias}" munka',
        ])

    for alias in aliases:
        for reddit_query in [
            f'"{alias}" dolgoztam',
            f'"{alias}" fizetés',
            f'"{alias}" műszak',
            f'"{alias}" nem ajánlom',
            f'"{alias}" tapasztalat',
        ]:
            print(f"  Reddit query: {reddit_query}")
            for result in reddit_search(reddit_query):
                combined = clean_text(f"{result.get('title', '')}. {result.get('snippet', '')}")
                process_candidate_text(company, "reddit_public_search", result.get("url", ""), combined, valid, excluded)

    discovered_urls = set()

    for query in search_queries:
        print(f"  DuckDuckGo query: {query}")
        for result in duckduckgo_search(query):
            url = result.get("url", "")

            if not url or url in discovered_urls:
                continue

            discovered_urls.add(url)

            combined = clean_text(f"{result.get('title', '')}. {result.get('snippet', '')}")
            process_candidate_text(company, "duckduckgo_search_result", url, combined, valid, excluded)

    for url in list(discovered_urls) + MANUAL_REVIEW_URLS.get(company, []):
        if not is_allowed_domain(url):
            continue

        print(f"  Reading page: {url}")
        for block in extract_text_blocks_from_page(url):
            process_candidate_text(company, "public_page_text", url, block, valid, excluded)

    return {
        "valid": deduplicate_items(valid)[:MAX_ITEMS_PER_COMPANY],
        "excluded": deduplicate_items(excluded)[:MAX_EXCLUDED_PER_COMPANY],
    }


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


def summarize_company(company: str, valid_items: List[Dict[str, Any]], excluded_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    company_valid = [item for item in valid_items if item.get("company") == company]
    company_excluded = [item for item in excluded_items if item.get("company") == company]

    topic_counts = {}
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    source_counts = {}
    exclusion_counts = {}

    for item in company_valid:
        topic = item.get("topic", "általános munkáltatói tapasztalat")
        sentiment = item.get("sentiment", "neutral")
        source = item.get("source", "unknown")

        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
        sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1

    for item in company_excluded:
        reason = item.get("reason", "unknown")
        exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1

    return {
        "company": company,
        "review_text_count": len(company_valid),
        "excluded_count": len(company_excluded),
        "dominant_topics": [{"topic": k, "count": v} for k, v in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)],
        "sentiment_counts": sentiment_counts,
        "source_counts": [{"source": k, "count": v} for k, v in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)],
        "exclusion_counts": [{"reason": k, "count": v} for k, v in sorted(exclusion_counts.items(), key=lambda x: x[1], reverse=True)],
        "sample_quotes": company_valid[:5],
        "sample_excluded": company_excluded[:3],
    }


def build_output(valid_items: List[Dict[str, Any]], excluded_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if valid_items:
        status = "ok"
    elif excluded_items:
        status = "no_valid_employee_reviews_only_excluded_items"
    else:
        status = "no_results_found"

    return {
        "updated_at": now_iso(),
        "status": status,
        "source_type": "public_osint_employee_reviews",
        "method": "reddit_duckduckgo_profession_forum_public_pages_v6",
        "important_note": (
            "Google News és LinkedIn nincs használatban. A rendszer Reddit, Profession, fórum és "
            "egyéb publikus oldalak találataiból próbál valódi dolgozói véleményeket kinyerni."
        ),
        "privacy_note": "A script automatikusan eltávolítja az e-mail címeket és telefonszámokat.",
        "companies": [summarize_company(company, valid_items, excluded_items) for company in COMPANIES.keys()],
        "items": valid_items,
        "excluded_items": excluded_items,
    }


def collect_all() -> Dict[str, List[Dict[str, Any]]]:
    all_valid = []
    all_excluded = []

    for company, aliases in COMPANIES.items():
        print(f"Collecting employee reviews for: {company}")

        result = collect_company(company, aliases)

        print(f"  valid reviews: {len(result['valid'])}")
        print(f"  excluded: {len(result['excluded'])}")

        all_valid.extend(result["valid"])
        all_excluded.extend(result["excluded"])

    return {
        "valid": deduplicate_items(all_valid),
        "excluded": deduplicate_items(all_excluded),
    }


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def main() -> None:
    print("Employee Review Collector v6 started.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    collected = collect_all()
    output = build_output(collected["valid"], collected["excluded"])

    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Valid review items: {len(collected['valid'])}")
    print(f"Excluded items: {len(collected['excluded'])}")
    print(f"Status: {output['status']}")


if __name__ == "__main__":
    main()
