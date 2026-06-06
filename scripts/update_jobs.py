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
HISTORY_DIR = DATA_DIR / "jobs-history"
RAW_DIR = DATA_DIR / "jobs-raw"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

SOURCES_FILE = DATA_DIR / "job-sources.json"
JOBS_FILE = DATA_DIR / "jobs.json"
STATUS_FILE = DATA_DIR / "jobs-monitor-status.json"

USER_AGENT = "Mozilla/5.0 (compatible; FMCG-Intelligence-Hungary/1.0)"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 2

DISABLED_SOURCE_TYPES = ["career_site", "linkedin", "indeed"]

EXTRA_PORTALS = [
    {
        "name": "Jobline",
        "type": "jobline",
        "url": "https://www.jobline.hu",
        "confidence": "medium",
        "enabled": True
    },
    {
        "name": "CVOnline",
        "type": "cvonline",
        "url": "https://www.cvonline.hu",
        "confidence": "medium",
        "enabled": True
    },
    {
        "name": "Jooble",
        "type": "jooble",
        "url": "https://hu.jooble.org",
        "confidence": "medium-low",
        "enabled": True
    }
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
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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


def make_search_url(source_type, company):
    query = company + " állás"
    q_plus = urllib.parse.quote_plus(query)
    q_url = urllib.parse.quote(query)

    if source_type == "job_portal":
        return f"https://www.profession.hu/allasok/1,0,0,{q_plus}"

    if source_type == "jobline":
        return f"https://www.jobline.hu/allasok?q={q_plus}"

    if source_type == "cvonline":
        return f"https://www.cvonline.hu/hu/allasok?query={q_plus}"

    if source_type == "jooble":
        return f"https://hu.jooble.org/SearchResult?ukw={q_url}"

    return None


def extract_count_hint(html):
    text = clean_text(html).lower()
    current_year = datetime.now(timezone.utc).year

    patterns = [
        r"(\d{1,4})\s+(?:állás|találat|hirdetés)",
        r"(?:állás|találat|hirdetés)[^\d]{0,30}(\d{1,4})",
        r"(\d{1,4})\s+(?:jobs|results|vacancies)",
        r"(?:jobs|results|vacancies)[^\d]{0,30}(\d{1,4})"
    ]

    numbers = []

    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            try:
                value = int(match)

                if value in {current_year - 1, current_year, current_year + 1}:
                    continue

                if 0 <= value <= 1500:
                    numbers.append(value)

            except ValueError:
                pass

    if not numbers:
        return None

    return max(numbers)


def add_extra_portals(company):
    existing_types = {s.get("type") for s in company.get("sources", [])}
    sources = list(company.get("sources", []))

    for portal in EXTRA_PORTALS:
        if portal["type"] not in existing_types:
            sources.append(portal)

    return sources


def collect_source(company_name, source):
    source_name = source.get("name")
    source_type = source.get("type")
    enabled = source.get("enabled", True)

    result = {
        "source_name": source_name,
        "source_type": source_type,
        "status": "skipped",
        "count_hint": None,
        "search_url": None,
        "error": None
    }

    if not enabled:
        result["status"] = "disabled"
        return result

    if source_type in DISABLED_SOURCE_TYPES:
        result["status"] = "temporarily_disabled"
        result["error"] = "A forrás átmenetileg ki van kapcsolva a stabilabb portálalapú mérés miatt."
        return result

    url = make_search_url(source_type, company_name)

    if not url:
        result["status"] = "unsupported_source"
        result["error"] = "Ehhez a forrástípushoz nincs keresési URL."
        return result

    result["search_url"] = url

    html = fetch_url(url)

    if not html:
        result["status"] = "fetch_failed"
        result["error"] = "Nem sikerült letölteni az oldalt."
        return result

    result["status"] = "fetched"
    result["count_hint"] = extract_count_hint(html)

    time.sleep(REQUEST_DELAY_SECONDS)
    return result


def summarize_company(company, collected_at):
    company_id = company["id"]
    company_name = company["company"]

    sources = add_extra_portals(company)
    source_results = []

    for source in sources:
      source_results.append(collect_source(company_name, source))

    source_counts = {}

    for result in source_results:
        count = result.get("count_hint")
        if isinstance(count, int):
            source_counts[result["source_name"]] = count
        else:
            source_counts[result["source_name"]] = None

    valid_counts = [v for v in source_counts.values() if isinstance(v, int)]

    external_count_hint = max(valid_counts) if valid_counts else None

    primary_portal_count = source_counts.get("Profession")
    jobline_count = source_counts.get("Jobline")
    cvonline_count = source_counts.get("CVOnline")
    jooble_count = source_counts.get("Jooble")

    active_sources = [
        r["source_name"]
        for r in source_results
        if r.get("status") == "fetched"
    ]

    failed_sources = [
        r["source_name"]
        for r in source_results
        if r.get("status") in ["fetch_failed", "unsupported_source"]
    ]

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": collected_at,

        "total_verified_ads": external_count_hint,
        "external_count_hint": external_count_hint,

        "source_counts": source_counts,
        "profession_active_ads": primary_portal_count,
        "jobline_active_ads": jobline_count,
        "cvonline_active_ads": cvonline_count,
        "jooble_active_ads": jooble_count,

        "parsed_postings_count": None,
        "store_jobs": None,
        "warehouse_jobs": None,
        "office_jobs": None,
        "management_jobs": None,
        "recruitment_events": None,
        "unknown_jobs": None,

        "salary_visible_ads": None,
        "benefits_visible_ads": None,
        "travel_support_ads": None,
        "bonus_ads": None,
        "cafeteria_ads": None,

        "career_site_present": any(s.get("type") == "career_site" for s in sources),
        "profession_present": any(s.get("type") == "job_portal" for s in sources),
        "jobline_present": any(s.get("type") == "jobline" for s in sources),
        "cvonline_present": any(s.get("type") == "cvonline" for s in sources),
        "jooble_present": any(s.get("type") == "jooble" for s in sources),
        "linkedin_jobs_present": any(s.get("type") == "linkedin" for s in sources),
        "indeed_present": any(s.get("type") == "indeed" for s in sources),

        "career_site_active_ads": None,
        "linkedin_active_ads": None,
        "indeed_active_ads": None,

        "salary_visible_in_examples": None,
        "benefits_visible_in_examples": None,
        "commuting_support_visible": None,
        "cafeteria_visible": None,
        "bonus_visible": None,
        "training_visible": None,
        "full_time_visible": None,
        "part_time_visible": None,

        "active_sources": active_sources,
        "failed_sources": failed_sources,

        "source_confidence": "medium" if external_count_hint is not None else "low",
        "labor_pressure_status": "többforrásos portálalapú előzetes mérés",

        "source_statuses": source_results,
        "notes": "A karrieroldalak, LinkedIn és Indeed átmenetileg ki vannak kapcsolva. A mérés elsődlegesen Profession, Jobline, CVOnline és Jooble találati becslésekből dolgozik."
    }


def main():
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_name = datetime.now(timezone.utc).strftime("%Y-%m")

    companies = load_json(SOURCES_FILE, [])

    if not companies:
        raise RuntimeError("Hiányzik vagy üres a docs/data/job-sources.json fájl.")

    summaries = []

    for company in companies:
        summaries.append(summarize_company(company, collected_at))

    save_json(JOBS_FILE, summaries)

    save_json(HISTORY_DIR / f"{month_name}.json", {
        "snapshot_date": collected_at,
        "companies": summaries
    })

    save_json(RAW_DIR / f"{month_name}.json", {
        "snapshot_date": collected_at,
        "companies": summaries
    })

    status = {
        "last_update": collected_at,
        "companies_tracked": len(companies),
        "summaries_written": len(summaries),
        "history_file": f"{month_name}.json",
        "raw_file": f"{month_name}.json",
        "mode": "multi_source_portal_count_monitor_v1",
        "active_portals": ["Profession", "Jobline", "CVOnline", "Jooble"],
        "temporarily_disabled": ["career_site", "linkedin", "indeed"]
    }

    save_json(STATUS_FILE, status)

    print("FMCG jobs monitor updated.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
