"""JobSpy scraping: config/criteria.yaml -> combined, deduplicated pandas DataFrame."""

from datetime import datetime, timezone

import pandas as pd
import yaml
from jobspy import scrape_jobs

CRITERIA_PATH = "config/criteria.yaml"

OUTPUT_COLUMNS = [
    "site",
    "title",
    "company",
    "location",
    "job_url",
    "description",
    "date_posted",
    "job_type",
]


def load_criteria(path: str = CRITERIA_PATH) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _compute_hours_since_posted(date_posted) -> float:
    if pd.isna(date_posted):
        return float("inf")
    posted = pd.to_datetime(date_posted, utc=True, errors="coerce")
    if pd.isna(posted):
        return float("inf")
    now = datetime.now(timezone.utc)
    delta = now - posted.to_pydatetime()
    return round(delta.total_seconds() / 3600, 1)


def scrape_all(config_path: str = CRITERIA_PATH) -> pd.DataFrame:
    criteria = load_criteria(config_path)
    sites = criteria.get("sites", [])
    hours_old = criteria.get("hours_old", 24)
    results_wanted = criteria.get("results_wanted", 25)
    country_indeed = criteria.get("country_indeed", "canada")

    all_frames = []
    per_site_counts = {}

    for search in criteria.get("searches", []):
        term = search.get("term")
        location = search.get("location")
        distance = search.get("distance")
        job_type = search.get("job_type")

        print(f"Searching: '{term}' in '{location}'...")
        try:
            jobs_df = scrape_jobs(
                site_name=sites,
                search_term=term,
                location=location,
                distance=distance,
                job_type=job_type,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=country_indeed,
            )
        except Exception as e:
            print(f"  ERROR scraping '{term}' in '{location}': {e}")
            continue

        if jobs_df is None or jobs_df.empty:
            print(f"  No results for '{term}' in '{location}'")
            continue

        for site_name, count in jobs_df["site"].value_counts().items():
            per_site_counts[site_name] = per_site_counts.get(site_name, 0) + count

        all_frames.append(jobs_df)

    if not all_frames:
        print("Total jobs scraped: 0")
        return pd.DataFrame(columns=OUTPUT_COLUMNS + ["hours_since_posted"])

    combined = pd.concat(all_frames, ignore_index=True)

    for col in OUTPUT_COLUMNS:
        if col not in combined.columns:
            combined[col] = None

    combined = combined.drop_duplicates(subset=["job_url"], keep="first")
    combined = combined[OUTPUT_COLUMNS].copy()

    combined["hours_since_posted"] = combined["date_posted"].apply(
        _compute_hours_since_posted
    )
    combined = combined.sort_values("hours_since_posted", ascending=True).reset_index(
        drop=True
    )

    print(f"Total jobs scraped: {len(combined)}")
    print("Per-site counts:")
    for site_name, count in per_site_counts.items():
        print(f"  {site_name}: {count}")

    return combined


if __name__ == "__main__":
    df = scrape_all()
    print(df.head())
