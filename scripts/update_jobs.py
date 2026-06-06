import json
import re
import time
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from html import unescape


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
HISTORY_DIR = DATA_DIR / "jobs-history"
RAW_DIR = DATA_DIR / "jobs-raw"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

SOURCES_FILE = DATA_DIR / "job-sources.json"
JOBS_FILE = DATA_DIR / "jobs.json"
CURRENT_POSTINGS_FILE = DATA_DIR / "job-postings-current.json"
STATUS_FILE = DATA_DIR / "jobs-monitor-status.json"

USER_AGENT = "Mozilla/5.0 (compatible; FMCG-Intelligence-Hungary/1.0; +https://github.com/mikloshetzer-sketch/fmcg-intelligence-hu)"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 2


KEYWORDS = {
    "store": [
        "eladó", "pénztáros", "árufeltöltő", "bolti", "üzleti", "áruházi",
        "csemegepult", "pékáru", "zöldség", "frissáru", "hentes"
    ],
    "warehouse": [
        "raktár", "raktáros", "komissiózó", "logisztika", "targonca",
        "árukiadó", "árufogadó", "kiszállítás"
    ],
    "office": [
        "iroda", "központ", "beszerző", "kontroller", "marketing",
        "hr", "pénzügy", "it", "elemző", "specialista", "asszisztens"
    ],
    "management": [
        "vezető", "manager", "menedzser", "műszakvezető", "üzletvezető",
        "áruházvezető", "osztályvezető", "részlegvezető", "team leader"
    ]
}


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_url(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except Exception as exc:
        return None


def clean_text(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_search_url(source_type, company):
    q = urllib.parse.quote_plus(company + " állás")

    if source_type == "job_portal":
        return f"https://www.profession.hu/allasok/1,0,0,{q}"
    if source_type == "indeed":
        return f"https://hu.indeed.com/jobs?q={q}"
    if source_type == "linkedin":
        return f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote_plus(company)}"
    if source_type == "facebook":
        return None
    if source_type == "career_site":
        return None

    return None


def extract_possible_job_titles(html, company):
    text = clean_text(html)
    titles = []

    patterns = [
        r"([A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű0-9 \-/]{4,80}(?:eladó|pénztáros|árufeltöltő|raktáros|vezető|manager|specialista|asszisztens|munkatárs)[A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű0-9 \-/]{0,80})",
        r"((?:eladó|pénztáros|árufeltöltő|raktáros|vezető|manager|specialista|asszisztens|munkatárs)[A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű0-9 \-/]{4,80})"
    ]

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            title = match.strip(" -|•,.;:")
            if len(title) >= 4 and company.lower() not in title.lower():
                titles.append(title)

    unique = []
    seen = set()

    for title in titles:
        key = title.lower()
        if key not in seen:
            unique.append(title)
            seen.add(key)

    return unique[:30]


def extract_count_hint(html):
    text = clean_text(html).lower()

    patterns = [
        r"(\d+)\s+(?:állás|találat|hirdetés)",
        r"(?:állás|találat|hirdetés)[^\d]{0,20}(\d+)"
    ]

    numbers = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            try:
                value = int(match)
                if 0 <= value <= 5000:
                    numbers.append(value)
            except ValueError:
                pass

    if not numbers:
        return None

    return max(numbers)


def detect_category(title):
    lower = title.lower()

    scores = {}
    for category, words in KEYWORDS.items():
        scores[category] = sum(1 for word in words if word in lower)

    best = max(scores, key=scores.get)

    if scores[best] == 0:
        return "unknown"

    return best


def detect_salary(text):
    lower = text.lower()
    salary_patterns = [
        r"(\d{3})\s?000\s?ft",
        r"(\d{3})\s?ezer\s?ft",
        r"bruttó\s+(\d{3})"
    ]

    values = []
    for pattern in salary_patterns:
        for match in re.findall(pattern, lower):
            try:
                value = int(match) * 1000
                if 250000 <= value <= 2500000:
                    values.append(value)
            except ValueError:
                pass

    if not values:
        return None

    return {
        "salary_min_huf": min(values),
        "salary_max_huf": max(values)
    }


def posting_id(company_id, source_name, title):
    raw = f"{company_id}|{source_name}|{title}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def collect_from_source(company_id, company_name, source):
    source_type = source.get("type")
    source_name = source.get("name")
    base_url = source.get("url")
    enabled = source.get("enabled", True)

    result = {
        "source_name": source_name,
        "source_type": source_type,
        "source_url": base_url,
        "status": "skipped",
        "count_hint": None,
        "postings": [],
        "error": None
    }

    if not enabled:
        result["status"] = "disabled"
        return result

    if source_type in ["facebook", "linkedin"]:
        result["status"] = "manual_or_limited"
        result["error"] = "Ez a forrás automatizáltan korlátozottan gyűjthető."
        return result

    url = base_url

    if source_type in ["job_portal", "indeed"]:
        url = make_search_url(source_type, company_name)

    if source_type == "career_site":
        url = base_url

    if not url:
        result["status"] = "no_url"
        return result

    html = fetch_url(url)

    if not html:
        result["status"] = "fetch_failed"
        result["error"] = "Nem sikerült letölteni az oldalt."
        return result

    result["status"] = "fetched"
    result["count_hint"] = extract_count_hint(html)

    titles = extract_possible_job_titles(html, company_name)

    for title in titles:
        category = detect_category(title)
        salary = detect_salary(title)

        posting = {
            "posting_id": posting_id(company_id, source_name, title),
            "company_id": company_id,
            "company": company_name,
            "source": source_name,
            "source_type": source_type,
            "title": title,
            "category": category,
            "location": None,
            "salary_min_huf": salary["salary_min_huf"] if salary else None,
            "salary_max_huf": salary["salary_max_huf"] if salary else None,
            "salary_visible": salary is not None,
            "benefits_visible": None,
            "commuting_support_visible": None,
            "full_time_visible": None,
            "part_time_visible": None,
            "url": url
        }

        result["postings"].append(posting)

    time.sleep(REQUEST_DELAY_SECONDS)
    return result


def summarize_company(company, source_results, collected_at):
    company_id = company["id"]
    company_name = company["company"]

    postings = []
    source_statuses = []

    for result in source_results:
        postings.extend(result.get("postings", []))
        source_statuses.append({
            "source_name": result.get("source_name"),
            "source_type": result.get("source_type"),
            "status": result.get("status"),
            "count_hint": result.get("count_hint"),
            "error": result.get("error")
        })

    unique_postings = {}
    for posting in postings:
        unique_postings[posting["posting_id"]] = posting

    postings = list(unique_postings.values())

    category_counts = {
        "store": 0,
        "warehouse": 0,
        "office": 0,
        "management": 0,
        "unknown": 0
    }

    for posting in postings:
        category_counts[posting.get("category", "unknown")] += 1

    count_hints = [
        result.get("count_hint")
        for result in source_results
        if isinstance(result.get("count_hint"), int)
    ]

    total_verified_ads = len(postings)

    if count_hints:
        total_ads_hint = max(count_hints)
    else:
        total_ads_hint = total_verified_ads if total_verified_ads > 0 else None

    salary_visible_ads = sum(1 for p in postings if p.get("salary_visible") is True)

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": collected_at,
        "total_verified_ads": total_ads_hint,
        "parsed_postings_count": len(postings),

        "store_jobs": category_counts["store"],
        "warehouse_jobs": category_counts["warehouse"],
        "office_jobs": category_counts["office"],
        "management_jobs": category_counts["management"],
        "unknown_jobs": category_counts["unknown"],

        "salary_visible_ads": salary_visible_ads,
        "benefits_visible_ads": None,
        "travel_support_ads": None,
        "bonus_ads": None,
        "cafeteria_ads": None,

        "career_site_present": any(s.get("type") == "career_site" for s in company.get("sources", [])),
        "profession_present": any(s.get("type") == "job_portal" for s in company.get("sources", [])),
        "linkedin_jobs_present": any(s.get("type") == "linkedin" for s in company.get("sources", [])),
        "indeed_present": any(s.get("type") == "indeed" for s in company.get("sources", [])),

        "career_site_active_ads": None,
        "profession_active_ads": None,
        "linkedin_active_ads": None,
        "indeed_active_ads": None,

        "salary_visible_in_examples": salary_visible_ads > 0,
        "benefits_visible_in_examples": None,
        "commuting_support_visible": None,
        "cafeteria_visible": None,
        "bonus_visible": None,
        "training_visible": None,
        "full_time_visible": None,
        "part_time_visible": None,

        "source_confidence": "medium" if total_ads_hint is not None else "low",
        "labor_pressure_status": "automatikus gyűjtés előzetes",
        "source_statuses": source_statuses,
        "notes": "Automatikusan gyűjtött előzetes adat. A portálok szerkezete változhat, ezért kézi ellenőrzés javasolt."
    }, postings


def main():
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    companies = load_json(SOURCES_FILE, [])
    if not companies:
        raise RuntimeError("Hiányzik vagy üres a docs/data/job-sources.json fájl.")

    all_summaries = []
    all_postings = []
    raw_results = []

    for company in companies:
        company_id = company["id"]
        company_name = company["company"]

        source_results = []

        for source in company.get("sources", []):
            result = collect_from_source(company_id, company_name, source)
            source_results.append(result)

        summary, postings = summarize_company(company, source_results, collected_at)

        all_summaries.append(summary)
        all_postings.extend(postings)

        raw_results.append({
            "id": company_id,
            "company": company_name,
            "sources": source_results
        })

    month_name = datetime.now(timezone.utc).strftime("%Y-%m")

    save_json(JOBS_FILE, all_summaries)
    save_json(CURRENT_POSTINGS_FILE, all_postings)
    save_json(HISTORY_DIR / f"{month_name}.json", {
        "snapshot_date": collected_at,
        "companies": all_summaries,
        "postings": all_postings
    })
    save_json(RAW_DIR / f"{month_name}.json", {
        "snapshot_date": collected_at,
        "raw_results": raw_results
    })

    status = {
        "last_update": collected_at,
        "companies_tracked": len(companies),
        "summaries_written": len(all_summaries),
        "postings_parsed": len(all_postings),
        "history_file": f"{month_name}.json",
        "raw_file": f"{month_name}.json",
        "mode": "weekly_preliminary_public_web_collection"
    }

    save_json(STATUS_FILE, status)

    print("FMCG jobs monitor updated.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
