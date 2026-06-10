import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from html import unescape

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_DIR / "linkedin-jobs-monitor.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)

COMPANIES = [
    {"id": "auchan", "company": "Auchan", "queries": ["Auchan Magyarország", "Auchan Retail Magyarország"]},
    {"id": "lidl", "company": "Lidl", "queries": ["Lidl Magyarország", "Lidl Hungary"]},
    {"id": "aldi", "company": "ALDI", "queries": ["ALDI Magyarország", "ALDI Hungary"]},
    {"id": "spar", "company": "SPAR", "queries": ["SPAR Magyarország", "SPAR Hungary"]},
    {"id": "tesco", "company": "Tesco", "queries": ["Tesco Magyarország", "Tesco Hungary"]},
    {"id": "penny", "company": "Penny", "queries": ["Penny Magyarország", "Penny Market Hungary"]},
]

KEYWORDS = {
    "store": ["eladó", "pénztáros", "árufeltöltő", "bolti", "store", "shop assistant"],
    "warehouse": ["raktár", "logisztika", "targoncavezető", "warehouse", "logistics"],
    "management": ["vezető", "manager", "üzletvezető", "area manager", "vezető-helyettes"],
    "office": ["iroda", "hr", "finance", "kontrolling", "beszerzés", "marketing", "it"],
    "expansion": ["új áruház", "new store", "expansion", "opening", "nyitás"],
}

def fetch_url(url):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=25) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except Exception as e:
        return None

def clean_text(html):
    if not html:
        return ""
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def linkedin_jobs_url(query):
    q = urllib.parse.quote_plus(query)
    loc = urllib.parse.quote_plus("Hungary")
    return f"https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}"

def extract_job_count(text):
    patterns = [
        r"(\d{1,4})\s+(?:jobs|állás|találat)",
        r"jobs[^\d]{0,30}(\d{1,4})",
        r"állás[^\d]{0,30}(\d{1,4})",
    ]
    nums = []
    for p in patterns:
        for m in re.findall(p, text, flags=re.I):
            try:
                n = int(m)
                if 0 <= n <= 1000:
                    nums.append(n)
            except ValueError:
                pass
    return max(nums) if nums else None

def score_categories(text):
    low = text.lower()
    result = {}
    for category, words in KEYWORDS.items():
        result[category] = sum(1 for w in words if w.lower() in low)
    return result

def classify_signal(category_scores, job_count):
    total = sum(category_scores.values())
    if job_count is None and total == 0:
        return "no_signal"

    if category_scores.get("expansion", 0) > 0:
        return "possible_expansion_signal"

    if category_scores.get("warehouse", 0) >= 2:
        return "logistics_recruitment_signal"

    if category_scores.get("management", 0) >= 2:
        return "management_recruitment_signal"

    if category_scores.get("store", 0) >= 2:
        return "store_recruitment_signal"

    return "weak_signal"

def collect_company(company):
    company_results = []
    best_count = None
    combined_scores = {k: 0 for k in KEYWORDS.keys()}
    statuses = []

    for query in company["queries"]:
        url = linkedin_jobs_url(query)
        html = fetch_url(url)

        if not html:
            statuses.append({
                "query": query,
                "url": url,
                "status": "fetch_failed"
            })
            time.sleep(3)
            continue

        text = clean_text(html)
        count = extract_job_count(text)
        scores = score_categories(text)

        if isinstance(count, int):
            best_count = max(best_count or 0, count)

        for k, v in scores.items():
            combined_scores[k] += v

        statuses.append({
            "query": query,
            "url": url,
            "status": "fetched",
            "count_hint": count,
            "category_scores": scores
        })

        time.sleep(3)

    signal = classify_signal(combined_scores, best_count)

    return {
        "id": company["id"],
        "company": company["company"],
        "linkedin_active_ads_hint": best_count,
        "category_scores": combined_scores,
        "dominant_signal": signal,
        "source_confidence": "medium" if best_count is not None else "low",
        "source_note": "Publikus LinkedIn Jobs keresési oldal alapján. Nem belépett scraping, nem hivatalos API. Blokkolás esetén a jel alacsony megbízhatóságú.",
        "queries": statuses
    }

def main():
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    companies = []
    for company in COMPANIES:
        companies.append(collect_company(company))

    summary = {
        "updated_at": collected_at,
        "status": "ok",
        "source": "linkedin_public_jobs_search",
        "method": "non_login_public_search_best_effort",
        "companies_tracked": len(companies),
        "companies": companies
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
