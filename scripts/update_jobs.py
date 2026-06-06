import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "docs" / "data"
HISTORY_DIR = DATA_DIR / "jobs-history"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)

sources_file = DATA_DIR / "job-sources.json"
jobs_file = DATA_DIR / "jobs.json"

with open(sources_file, "r", encoding="utf-8") as f:
    companies = json.load(f)

if jobs_file.exists():
    with open(jobs_file, "r", encoding="utf-8") as f:
        current_jobs = json.load(f)
else:
    current_jobs = []

today = datetime.utcnow()

snapshot_name = today.strftime("%Y-%m") + ".json"

snapshot_file = HISTORY_DIR / snapshot_name

snapshot = {
    "snapshot_date": today.strftime("%Y-%m-%d"),
    "companies": current_jobs
}

with open(snapshot_file, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)

summary = {
    "last_update": today.strftime("%Y-%m-%d"),
    "companies_tracked": len(companies),
    "history_file": snapshot_name
}

with open(DATA_DIR / "jobs-monitor-status.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("Jobs history snapshot created:")
print(snapshot_file)
