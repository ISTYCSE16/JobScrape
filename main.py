from datetime import date

from scripts.scrape import scrape_all
from scripts.score import score_jobs
from scripts.report import generate_report
from scripts.webreport import generate_web_report
from scripts.database import get_db, init_db, store_jobs


def main():
    print("=== Job Search Pipeline ===")
    print("Step 1: Scraping...")
    df = scrape_all()
    if df.empty:
        print("No jobs found. Exiting.")
        return
    print(f"Found {len(df)} jobs")

    print("Step 2: Storing in database...")
    conn = get_db()
    init_db(conn)
    batch_id = date.today().isoformat()
    stored = store_jobs(conn, df, batch_id)
    conn.close()
    print(f"Stored {stored} jobs (batch {batch_id})")

    print("Step 3: Scoring...")
    scored_df = score_jobs(df)
    print(f"Scored {len(scored_df)} jobs")

    print("Step 4: Generating report...")
    generate_report(scored_df)

    print("Step 5: Generating web report...")
    generate_web_report(scored_df)
    print("Done!")


if __name__ == "__main__":
    main()
