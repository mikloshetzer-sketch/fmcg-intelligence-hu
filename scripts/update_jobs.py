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
EMPLOYER_REVIEWS_FILE = DATA_DIR / "employer-reviews.json"
BENEFITS_FILE = DATA_DIR / "benefits.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 25
REQUEST_DELAY_SECONDS = 3


PROFESSION_COMPANY_URLS = {
    "lidl": "https://www.profession.hu/allasok/lidl-magyarorszag-bt/1,0,0,0,0,0,0,0,0,0,5644",
    "aldi": "https://www.profession.hu/allasok/aldi-magyarorszag-elelmiszer-bt/1,0,0,0,0,0,0,0,0,0,43793",
    "spar": "https://www.profession.hu/allasok/1,0,0,0,0,0,0,0,0,0,4719_112707",
    "tesco": "https://www.profession.hu/allasok/tesco-global-zrt/1,0,0,0,0,0,0,0,0,0,3710",
    "penny": "https://www.profession.hu/allasok/1,0,0,penny%401%401?keywordsearch",
    "auchan": "https://www.profession.hu/allasok/auchan-retail-magyarorszag/1,0,0,0,0,0,0,0,0,0,7267"
}


KNOWN_JOBS = {
    "lidl": [
        ("Bolti dolgozó", "store"),
        ("Higiéniai munkatárs", "store"),
        ("Üzletvezető", "management"),
        ("Üzletvezető-helyettes", "management"),
        ("Területi értékesítési vezető", "management"),
        ("Raktári dolgozó", "warehouse"),
        ("Targoncavezető", "warehouse"),
        ("Áruösszekészítő", "warehouse"),
        ("Raktári csoportvezető", "warehouse"),
        ("Raktári csoportvezető-helyettes", "warehouse")
    ],
    "aldi": [
        ("Bolti eladó", "store"),
        ("Árufeltöltő", "store"),
        ("Pénztáros", "store"),
        ("Raktári dolgozó", "warehouse"),
        ("Logisztikai munkatárs", "warehouse"),
        ("Üzletvezető", "management"),
        ("Üzletvezető-helyettes", "management"),
        ("Manager", "management"),
        ("Asszisztens", "office")
    ],
    "spar": [
        ("Eladó-pénztáros", "store"),
        ("Bolti eladó", "store"),
        ("Shop eladó", "store"),
        ("Pék", "store"),
        ("Hentes", "store"),
        ("Csemegepultos", "store"),
        ("Raktári munkatárs", "warehouse"),
        ("Raktáros", "warehouse"),
        ("Boltvezető", "management"),
        ("Boltvezető-helyettes", "management"),
        ("Műszak részlegvezető", "management"),
        ("Műszak-részlegvezető", "management")
    ],
    "tesco": [
        ("Eladó", "store"),
        ("Árufeltöltő", "store"),
        ("Pénztáros", "store"),
        ("Online bevásárlás összekészítő", "store"),
        ("Raktáros", "warehouse"),
        ("Raktári munkatárs", "warehouse"),
        ("Manager", "management"),
        ("Buying Manager", "management"),
        ("Bér-TB szenior specialista", "office"),
        ("Specialista", "office")
    ],
    "penny": [
        ("Eladó-pénztáros", "store"),
        ("Bolti dolgozó", "store"),
        ("Üzletvezető", "management"),
        ("Üzletvezető-helyettes", "management"),
        ("Osztályvezető", "management"),
        ("Csoportvezető", "management"),
        ("Targoncavezető", "warehouse"),
        ("Raktári dolgozó", "warehouse"),
        ("Asszisztens", "office"),
        ("Elemző", "office")
    ],
    "auchan": [
        ("Eladó", "store"),
        ("Eladó/Pénztáros", "store"),
        ("Árufeltöltő", "store"),
        ("Áruátvevő", "warehouse"),
        ("Raktár", "warehouse"),
        ("Kamion leszedő munkatárs", "warehouse"),
        ("Kereskedelmi manager", "management"),
        ("Üzletvezető-helyettes", "management"),
        ("Manager", "management")
    ]
}


BENEFIT_KEYWORDS = {
    "cafeteria": ["cafeteria", "szép kártya", "szep kártya"],
    "commuting_support": ["munkába járás", "bejárás támogatás", "utazási támogatás", "bérlet támogatás"],
    "bonus": ["bónusz", "jutalom", "prémium"],
    "health_insurance": ["egészségbiztosítás", "magánegészségügy", "egészségügyi biztosítás"],
    "sport_support": ["sport támogatás", "sportolási támogatás"],
    "life_insurance": ["életbiztosítás", "balesetbiztosítás"],
    "training": ["képzés", "betanulás", "fejlődési lehetőség", "tréning"],
    "language_support": ["nyelvtanulás", "nyelvi képzés", "nyelvoktatás"],
    "employee_discount": ["dolgozói kedvezmény", "munkavállalói kedvezmény"]
}


BAD_TEXT_PARTS = [
    "áttekintés",
    "karrier",
    "értékesítés",
    "raktár / logisztika",
    "raktár/logisztika",
    "központi irodaház",
    "vállalati kommunikáció",
    "beszerzés marketing",
    "munkatársaik",
    "életkörülményeiről",
    "adatvédelem",
    "cookie",
    "süti",
    "impresszum",
    "kapcsolat",
    "rendezvényeink",
    "történetünk"
]


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


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
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                html = response.read().decode(charset, errors="ignore")

                if len(html) > 500:
                    return html

        except Exception:
            time.sleep(2 + attempt)

    return None


def make_search_url(source_type, company, company_id=None):
    if source_type == "job_portal" and company_id in PROFESSION_COMPANY_URLS:
        return PROFESSION_COMPANY_URLS[company_id]

    q = urllib.parse.quote_plus(company + " állás")

    if source_type == "job_portal":
        return f"https://www.profession.hu/allasok/1,0,0,{q}"

    if source_type == "indeed":
        return f"https://hu.indeed.com/jobs?q={q}"

    if source_type == "linkedin":
        return f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote_plus(company)}"

    return None


def normalize_title(title):
    title = unescape(title)
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"^\d{4}\s+", "", title)
    title = re.sub(r"^\d{1,2}\s+", "", title)
    title = re.sub(r"\s+\d{1,2}$", "", title)
    title = re.sub(r"^(ma|tegnap|új|állás|részletek|feladva|tipp)\s+", "", title, flags=re.I)
    title = title.strip(" -|•,.;:")
    return title


def is_bad_fragment(text):
    lower = text.lower()

    if any(bad in lower for bad in BAD_TEXT_PARTS):
        return True

    if len(text.split()) > 8:
        return True

    if text[:1].islower() and not text.lower().startswith(("áru", "eladó", "pék", "hentes")):
        return True

    return False


def posting_id(company_id, source_name, title, location=None):
    raw = f"{company_id}|{source_name}|{title}|{location or ''}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def extract_location_from_title(title):
    if " - " not in title:
        return None

    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) < 2:
        return None

    location = parts[-1]
    location = re.sub(r"\s+\d{1,2}$", "", location).strip()

    bad_location_terms = [
        "franchise", "feladva", "magyarország", "élelmisz",
        "rossmann", "sinsay", "tesco-bst", "kft", "zrt", "bt",
        "aldi", "auchan", "spar", "tesco", "penny", "lidl"
    ]

    if len(location) > 35:
        return None

    if any(term in location.lower() for term in bad_location_terms):
        return None

    return location


def extract_known_jobs_from_text(company_id, company_name, source_name, source_type, url, html):
    text = clean_text(html)
    results = []

    known_jobs = KNOWN_JOBS.get(company_id, [])

    for job_name, category in known_jobs:
        pattern = re.escape(job_name)
        matches = list(re.finditer(pattern, text, flags=re.I))

        for match in matches:
            start = max(0, match.start() - 45)
            end = min(len(text), match.end() + 55)
            window = normalize_title(text[start:end])

            location = extract_location_from_title(window)
            title = job_name
            item_category = category

            if "toborzónap" in window.lower():
                title = f"{job_name} toborzónap"
                item_category = "recruitment_event"

            if is_bad_fragment(window) and source_type == "career_site":
                if "toborzónap" not in window.lower():
                    continue

            results.append({
                "posting_id": posting_id(company_id, source_name, title, location),
                "company_id": company_id,
                "company": company_name,
                "source": source_name,
                "source_type": source_type,
                "title": title,
                "category": item_category,
                "location": location,
                "salary_min_huf": None,
                "salary_max_huf": None,
                "salary_visible": False,
                "benefits_visible": None,
                "commuting_support_visible": None,
                "full_time_visible": None,
                "part_time_visible": None,
                "url": url
            })

    unique = {}
    for item in results:
        unique[item["posting_id"]] = item

    return list(unique.values())


def extract_count_hint(html):
    text = clean_text(html).lower()
    current_year = datetime.now(timezone.utc).year

    patterns = [
        r"(\d{1,4})\s+(?:állás|találat|hirdetés)",
        r"(?:állás|találat|hirdetés)[^\d]{0,25}(\d{1,4})"
    ]

    numbers = []

    for pattern in patterns:
        for match in re.findall(pattern, text):
            try:
                value = int(match)

                if value in {current_year - 1, current_year, current_year + 1}:
                    continue

                if 0 <= value <= 1000:
                    numbers.append(value)

            except ValueError:
                pass

    return max(numbers) if numbers else None


def extract_employer_review_data(html, company_id, company_name, source_url):
    text = clean_text(html).lower()

    rating = None
    review_count = None
    opinion_count = None

    rating_match = re.search(r"(\d[,.]\d)", text)
    if rating_match:
        try:
            candidate = float(rating_match.group(1).replace(",", "."))
            if 1 <= candidate <= 5:
                rating = candidate
        except ValueError:
            rating = None

    review_match = re.search(r"(\d{1,5})\s*értékelés", text)
    if review_match:
        try:
            review_count = int(review_match.group(1))
        except ValueError:
            review_count = None

    opinion_match = re.search(r"(\d{1,5})\s*vélemény", text)
    if opinion_match:
        try:
            opinion_count = int(opinion_match.group(1))
        except ValueError:
            opinion_count = None

    return {
        "id": company_id,
        "company": company_name,
        "source": "Profession",
        "source_url": source_url,
        "rating": rating,
        "review_count": review_count,
        "opinion_count": opinion_count,
        "source_status": "parsed" if any(v is not None for v in [rating, review_count, opinion_count]) else "not_found",
        "notes": "Profession cégoldalról automatikusan kinyert munkáltatói értékelési adat."
    }


def extract_benefits_from_text(text):
    lower = text.lower()
    result = {}

    for benefit, keywords in BENEFIT_KEYWORDS.items():
        result[benefit] = any(keyword in lower for keyword in keywords)

    result["benefits_detected_count"] = sum(
        1 for key, value in result.items()
        if key != "benefits_detected_count" and value is True
    )

    return result


def last_good_jobs():
    previous = {}

    current = load_json(JOBS_FILE, [])
    if isinstance(current, list):
        for row in current:
            if row.get("id"):
                previous[row["id"]] = row

    for path in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        data = load_json(path, {})
        companies = data.get("companies", [])
        if isinstance(companies, list):
            for row in companies:
                company_id = row.get("id")
                if not company_id:
                    continue

                has_good_profession = (
                    isinstance(row.get("profession_active_ads"), int)
                    or isinstance(row.get("external_count_hint"), int)
                )

                if has_good_profession:
                    previous[company_id] = row

    return previous


def last_good_reviews():
    previous = {}

    current = load_json(EMPLOYER_REVIEWS_FILE, [])
    if isinstance(current, list):
        for row in current:
            if row.get("id"):
                previous[row["id"]] = row

    for path in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        data = load_json(path, {})
        reviews = data.get("employer_reviews", [])
        if isinstance(reviews, list):
            for row in reviews:
                company_id = row.get("id")
                if company_id and row.get("source_status") == "parsed":
                    previous[company_id] = row

    return previous


def last_good_benefits():
    previous = {}

    current = load_json(BENEFITS_FILE, [])
    if isinstance(current, list):
        for row in current:
            if row.get("id"):
                previous[row["id"]] = row

    for path in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        data = load_json(path, {})
        benefits = data.get("benefits", [])
        if isinstance(benefits, list):
            for row in benefits:
                company_id = row.get("id")
                if company_id and row.get("benefits_detected_count", 0) > 0:
                    previous[company_id] = row

    return previous


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
        "employer_review": None,
        "benefits": None,
        "error": None
    }

    if not enabled:
        result["status"] = "disabled"
        return result

    if source_type in ["facebook", "linkedin"]:
        result["status"] = "manual_or_limited"
        result["error"] = "Ez a forrás automatizáltan korlátozottan gyűjthető."
        return result

    if source_type in ["job_portal", "indeed"]:
        url = make_search_url(source_type, company_name, company_id)
    elif source_type == "career_site":
        url = base_url
    else:
        url = base_url

    if not url:
        result["status"] = "no_url"
        return result

    result["source_url"] = url
    html = fetch_url(url)

    if not html:
        result["status"] = "fetch_failed"
        result["error"] = "Nem sikerült letölteni az oldalt."
        return result

    result["status"] = "fetched"
    result["count_hint"] = extract_count_hint(html)

    if source_type == "job_portal":
        result["employer_review"] = extract_employer_review_data(html, company_id, company_name, url)
        result["benefits"] = {
            "id": company_id,
            "company": company_name,
            "source": "Profession",
            "source_url": url,
            **extract_benefits_from_text(clean_text(html)),
            "notes": "Profession HTML alapján előzetesen érzékelt juttatási kulcsszavak."
        }

    result["postings"] = extract_known_jobs_from_text(
        company_id=company_id,
        company_name=company_name,
        source_name=source_name,
        source_type=source_type,
        url=url,
        html=html
    )

    time.sleep(REQUEST_DELAY_SECONDS)
    return result


def summarize_company(company, source_results, collected_at, fallback_jobs, fallback_reviews, fallback_benefits):
    company_id = company["id"]
    company_name = company["company"]

    postings = []
    source_statuses = []
    employer_review = None
    benefits = None

    profession_fetched = False

    for result in source_results:
        postings.extend(result.get("postings", []))

        source_statuses.append({
            "source_name": result.get("source_name"),
            "source_type": result.get("source_type"),
            "status": result.get("status"),
            "count_hint": result.get("count_hint"),
            "error": result.get("error")
        })

        if result.get("source_type") == "job_portal" and result.get("status") == "fetched":
            profession_fetched = True

        if result.get("employer_review") and result["employer_review"].get("source_status") == "parsed":
            employer_review = result["employer_review"]

        if result.get("benefits"):
            benefits = result["benefits"]

    unique_postings = {}
    for posting in postings:
        unique_postings[posting["posting_id"]] = posting

    postings = list(unique_postings.values())

    category_counts = {
        "store": 0,
        "warehouse": 0,
        "office": 0,
        "management": 0,
        "recruitment_event": 0,
        "unknown": 0
    }

    for posting in postings:
        category = posting.get("category", "unknown")
        if category not in category_counts:
            category = "unknown"
        category_counts[category] += 1

    count_hints = [
        result.get("count_hint")
        for result in source_results
        if isinstance(result.get("count_hint"), int)
    ]

    parsed_postings_count = len(postings)
    external_count_hint = max(count_hints) if count_hints else None
    profession_active_ads = external_count_hint

    previous_job = fallback_jobs.get(company_id, {})

    if profession_active_ads is None:
        profession_active_ads = previous_job.get("profession_active_ads")
        if profession_active_ads is None:
            profession_active_ads = previous_job.get("external_count_hint")

    if external_count_hint is None and isinstance(profession_active_ads, int):
        external_count_hint = profession_active_ads

    active_ads_for_dashboard = (
        profession_active_ads
        if isinstance(profession_active_ads, int)
        else parsed_postings_count
    )

    salary_visible_ads = sum(1 for p in postings if p.get("salary_visible") is True)

    if employer_review is None:
        employer_review = fallback_reviews.get(company_id)

    if employer_review is None:
        employer_review = {
            "id": company_id,
            "company": company_name,
            "source": "Profession",
            "source_url": PROFESSION_COMPANY_URLS.get(company_id),
            "rating": None,
            "review_count": None,
            "opinion_count": None,
            "source_status": "not_found",
            "notes": "Nem sikerült stabilan kinyerni értékelési adatot."
        }

    if benefits is None:
        benefits = fallback_benefits.get(company_id)

    if benefits is None:
        benefits = {
            "id": company_id,
            "company": company_name,
            "source": "Profession",
            "source_url": PROFESSION_COMPANY_URLS.get(company_id),
            **{key: False for key in BENEFIT_KEYWORDS.keys()},
            "benefits_detected_count": 0,
            "notes": "Nem sikerült stabilan kinyerni juttatási adatot."
        }

    if not profession_fetched and isinstance(profession_active_ads, int):
        source_confidence = "medium-stale"
        notes = "Profession aktuálisan nem volt letölthető, ezért az utolsó jó hirdetésszámot tartotta meg a rendszer."
    else:
        source_confidence = "medium" if active_ads_for_dashboard > 0 else "low"
        notes = "Automatikusan gyűjtött előzetes adat. A Profession cégprofilokat és cégspecifikus karrieroldal-parserrel szűrt munkaköröket használ."

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": collected_at,

        "total_verified_ads": active_ads_for_dashboard,
        "parsed_postings_count": parsed_postings_count,
        "external_count_hint": external_count_hint,

        "store_jobs": category_counts["store"],
        "warehouse_jobs": category_counts["warehouse"],
        "office_jobs": category_counts["office"],
        "management_jobs": category_counts["management"],
        "recruitment_events": category_counts["recruitment_event"],
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
        "profession_active_ads": profession_active_ads,
        "linkedin_active_ads": None,
        "indeed_active_ads": None,

        "salary_visible_in_examples": salary_visible_ads > 0,
        "benefits_visible_in_examples": benefits.get("benefits_detected_count", 0) > 0,
        "commuting_support_visible": benefits.get("commuting_support"),
        "cafeteria_visible": benefits.get("cafeteria"),
        "bonus_visible": benefits.get("bonus"),
        "training_visible": benefits.get("training"),
        "full_time_visible": None,
        "part_time_visible": None,

        "source_confidence": source_confidence,
        "labor_pressure_status": "automatikus gyűjtés előzetes, fallback védelemmel",
        "source_statuses": source_statuses,
        "notes": notes
    }, postings, employer_review, benefits


def main():
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_name = datetime.now(timezone.utc).strftime("%Y-%m")

    companies = load_json(SOURCES_FILE, [])
    if not companies:
        raise RuntimeError("Hiányzik vagy üres a docs/data/job-sources.json fájl.")

    fallback_jobs = last_good_jobs()
    fallback_reviews = last_good_reviews()
    fallback_benefits = last_good_benefits()

    all_summaries = []
    all_postings = []
    all_reviews = []
    all_benefits = []
    raw_results = []

    for company in companies:
        company_id = company["id"]
        company_name = company["company"]

        source_results = []

        for source in company.get("sources", []):
            result = collect_from_source(company_id, company_name, source)
            source_results.append(result)

        summary, postings, employer_review, benefits = summarize_company(
            company,
            source_results,
            collected_at,
            fallback_jobs,
            fallback_reviews,
            fallback_benefits
        )

        all_summaries.append(summary)
        all_postings.extend(postings)
        all_reviews.append(employer_review)
        all_benefits.append(benefits)

        raw_results.append({
            "id": company_id,
            "company": company_name,
            "sources": source_results
        })

    save_json(JOBS_FILE, all_summaries)
    save_json(CURRENT_POSTINGS_FILE, all_postings)
    save_json(EMPLOYER_REVIEWS_FILE, all_reviews)
    save_json(BENEFITS_FILE, all_benefits)

    save_json(HISTORY_DIR / f"{month_name}.json", {
        "snapshot_date": collected_at,
        "companies": all_summaries,
        "postings": all_postings,
        "employer_reviews": all_reviews,
        "benefits": all_benefits
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
        "employer_reviews_written": len(all_reviews),
        "benefits_written": len(all_benefits),
        "history_file": f"{month_name}.json",
        "raw_file": f"{month_name}.json",
        "mode": "profession_retry_with_last_good_fallback_v2"
    }

    save_json(STATUS_FILE, status)

    print("FMCG jobs monitor updated.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
