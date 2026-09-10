from scripts.scrape import scrape_all
from scripts.score import score_jobs
from scripts.report import generate_report


def main():
    print("=== Job Search Pipeline ===")
    print("Step 1: Scraping...")
    df = scrape_all()
    if df.empty:
        print("No jobs found. Exiting.")
        return
    print(f"Found {len(df)} jobs")

    print("Step 2: Scoring...")
    scored_df = score_jobs(df)
    print(f"Scored {len(scored_df)} jobs")

    print("Step 3: Generating report...")
    generate_report(scored_df)
    print("Done!")


if __name__ == "__main__":
    main()
