# Job Search Automation Pipeline — Claude Code Instructions

## What this project is

A daily job search pipeline that:
1. Scrapes jobs from LinkedIn, Indeed, Google Jobs, and ZipRecruiter using JobSpy
2. Scores each job against my skills and CV using Claude API (Haiku)
3. Outputs a ranked Excel report
4. On demand, generates per-job CV tailoring suggestions for jobs I select

## Tech stack

- **Python 3.10+**
- **python-jobspy** — multi-board scraper (LinkedIn, Indeed, Google, ZipRecruiter)
- **anthropic** — Claude API client (use claude-haiku-4-5-20251001 for scoring)
- **openpyxl** — Excel generation
- **pandas** — data handling
- **pyyaml** — config parsing
- **GitHub Actions** — scheduled daily runs (free tier, public repo)

## Project structure

```
job-search-pipeline/
├── .github/
│   └── workflows/
│       └── daily-search.yml
├── config/
│   ├── skills.md              # my skills and experience (I'll fill this)
│   ├── criteria.yaml          # search parameters (I'll fill this)
│   └── base_cv.md             # my current CV content (I'll fill this)
├── scripts/
│   ├── scrape.py              # JobSpy → raw DataFrame
│   ├── score.py               # Claude API scoring + keyword extraction
│   ├── report.py              # DataFrame → Excel
│   └── tailor.py              # generate per-job CV suggestions
├── output/                    # daily Excel reports land here
├── applications/              # per-job suggestion folders land here
├── main.py                    # orchestrator: scrape → score → report
├── tailor_jobs.py             # CLI to generate suggestions for selected jobs
├── requirements.txt
├── .gitignore
└── README.md
```

## Step 1: Scaffold all files

Create the full directory structure above. Create all files with the content described below. Do not leave any file as a stub.

## Step 2: config/ files

### config/criteria.yaml

```yaml
searches:
  - term: "Software Developer"
    location: "Edmonton, AB"
    distance: 50
    job_type: "fulltime"
  - term: "AI Engineer"
    location: "Edmonton, AB"
    distance: 50
    job_type: "fulltime"
  - term: "Software Developer"
    location: "Calgary, AB"
    distance: 50
    job_type: "fulltime"

sites:
  - linkedin
  - indeed
  - google
  - zip_recruiter

hours_old: 24
results_wanted: 25
country_indeed: "canada"
```

### config/skills.md

```markdown
# Skills & Experience

<!-- I will fill this in with my actual skills. Leave this placeholder. -->

## Technical Skills
- Python, Java, JavaScript
- Machine Learning: CNN, RNN, Keras
- CI/CD: GitLab CI, GitHub Actions
- Cloud: AWS (free tier experience)
- Testing: Maestro, pytest
- Tools: Git, Docker, Sentry, Jira

## Experience
- Co-op at Mottiv (QA Automation, Maestro, GitLab CI/CD)
- Self-healing software system (Claude API + Sentry)
- Video content analysis pipeline
- Published research applying CNN/RNN techniques

## Education
- M.Sc. Computing Science, University of Alberta (graduating Dec 2026)
- B.Sc. Computer Science and Engineering, RUET
```

### config/base_cv.md

```markdown
# Base CV

<!-- I will paste my actual CV content here. Leave this placeholder. -->
```

## Step 3: scripts/scrape.py

This script:
- Reads `config/criteria.yaml`
- Runs JobSpy `scrape_jobs()` for each search term defined in criteria
- Deduplicates results by job URL
- Returns a combined pandas DataFrame with columns: `site`, `title`, `company`, `location`, `job_url`, `description`, `date_posted`, `job_type`
- Adds a computed column `hours_since_posted` calculated from `date_posted` relative to now
- Sorts by `hours_since_posted` ascending (freshest first)

Key details:
- Use `hours_old` from criteria.yaml as the JobSpy `hours_old` parameter
- Use `results_wanted` from criteria.yaml per search per site
- Catch and log errors per search term (don't crash if one search fails)
- Print summary: total jobs scraped, count per site

## Step 4: scripts/score.py

This script:
- Takes the scraped DataFrame + reads `config/skills.md` and `config/base_cv.md`
- For each job, sends ONE Claude API call (model: `claude-haiku-4-5-20251001`) with this prompt structure:

```
You are a job-match analyst. Given a candidate's skills/experience and a job posting, return ONLY a JSON object (no markdown, no explanation):

{
  "match_score": <0-100 integer>,
  "strong_keywords": ["keyword1", "keyword2", ...],
  "missing_keywords": ["keyword1", "keyword2", ...],
  "cv_changes_summary": "One paragraph: what specific lines/sections of the CV should change for this job"
}

CANDIDATE SKILLS:
{skills_md_content}

CANDIDATE CV:
{base_cv_content}

JOB POSTING:
Title: {title}
Company: {company}
Description: {description}
```

- Parse the JSON response. If parsing fails, set match_score to -1 and log the error.
- Add columns to DataFrame: `match_score`, `strong_keywords`, `missing_keywords`, `cv_changes_summary`
- Sort by `match_score` descending
- Use `max_tokens: 500` per call
- Add a 0.5 second sleep between calls to stay under rate limits
- Print progress: "Scoring job X of Y..."

**Important:** The ANTHROPIC_API_KEY comes from environment variable, not hardcoded.

## Step 5: scripts/report.py

This script:
- Takes the scored DataFrame
- Writes an Excel file to `output/jobs_YYYY-MM-DD.xlsx`
- Sheet name: "Job Matches"
- Columns in this order:
  1. Company
  2. Job Title
  3. Location
  4. Site (linkedin/indeed/google/zip_recruiter)
  5. Hours Since Posted
  6. Match Score (0-100)
  7. Strong Keywords (comma-separated string)
  8. Missing Keywords (comma-separated string)
  9. CV Changes Summary
  10. Job URL (as a clickable hyperlink)
  11. Description (truncated to 500 chars in the cell)
- Formatting:
  - Header row: bold, light blue fill
  - Match Score column: conditional — green fill if >= 70, yellow if 40-69, red if < 40
  - Column widths: auto-fit roughly (Company 25, Title 30, Description 50, others 15-20)
  - Freeze the header row
- Also save the full DataFrame as `output/jobs_YYYY-MM-DD.csv` for programmatic access

## Step 6: tailor_jobs.py

This is a separate CLI script, NOT run by the daily pipeline. I run it manually after reviewing the Excel.

Usage: `python tailor_jobs.py output/jobs_2026-09-10.csv 0 3 7`

Arguments:
- First arg: path to the CSV from today's run
- Remaining args: row indices (0-based) of jobs I want to apply to

For each selected job:
- Create folder: `applications/{Company}_{JobTitle}_{Date}/`
  - Sanitize folder name (replace spaces with underscores, remove special chars)
- Send a Claude API call (model: `claude-haiku-4-5-20251001`, `max_tokens: 1500`) with:

```
You are a CV tailoring expert. Given a candidate's base CV and a specific job posting, produce a tailored version of the CV in markdown.

Rules:
- Keep all truthful content. Do not fabricate experience.
- Reorder bullet points to lead with the most relevant ones for this job.
- Adjust wording to echo the job posting's keywords where honest.
- Add a 2-line "Summary" section at the top tailored to this specific role.
- At the end, add a section "## Changes Made" listing each change and why.

BASE CV:
{base_cv_content}

JOB POSTING:
Title: {title}
Company: {company}
Description: {full_description}
```

- Save the response as `tailored_cv.md` in that job's folder
- Also save `job_details.md` in the folder with the full job title, company, URL, and description for reference
- Print: "Generated suggestions for {Company} - {Title}"

## Step 7: main.py

Orchestrator script:
```python
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
```

## Step 8: .github/workflows/daily-search.yml

```yaml
name: Daily Job Search

on:
  schedule:
    - cron: '0 14 * * *'  # 8 AM MST (UTC-6) every day
  workflow_dispatch:  # allow manual trigger

jobs:
  search:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run pipeline
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python main.py

      - name: Commit results
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add output/
          git diff --staged --quiet || git commit -m "Daily job search $(date +%Y-%m-%d)"
          git push
```

## Step 9: requirements.txt

```
python-jobspy
anthropic
pandas
openpyxl
pyyaml
```

## Step 10: .gitignore

```
__pycache__/
*.pyc
.env
applications/
```

Note: `output/` is NOT in .gitignore — we want the Excel/CSV committed by the GitHub Action so I can pull them down. `applications/` IS in .gitignore since tailored CVs are local only.

## Step 11: README.md

Write a clean README with:
- One-line description: "Automated job search pipeline using JobSpy + Claude API + GitHub Actions"
- Architecture diagram (text/ascii): Scrape → Score → Report → (manual) Tailor
- Setup instructions: clone, set ANTHROPIC_API_KEY as GitHub secret, edit config/ files
- Local usage: `python main.py` and `python tailor_jobs.py`
- Cost estimate: ~$0.05-0.15/day at Haiku rates for 50 jobs

## Build order

1. Create the full directory structure and all config files
2. Build `scripts/scrape.py` and test it standalone: `python -c "from scripts.scrape import scrape_all; print(scrape_all())"`
3. Build `scripts/score.py` — test with a small DataFrame (2-3 rows) first
4. Build `scripts/report.py` — verify the Excel opens and looks right
5. Build `main.py` — run the full pipeline end to end locally
6. Build `tailor_jobs.py` — test with a row index from today's output
7. Add `.github/workflows/daily-search.yml`
8. Write `README.md`
9. Commit and push. Add `ANTHROPIC_API_KEY` to GitHub repo secrets. Trigger the workflow manually to verify.

## Important constraints

- Never hardcode API keys. Always use `os.environ["ANTHROPIC_API_KEY"]`.
- All Claude calls use `claude-haiku-4-5-20251001` to keep costs minimal.
- If JobSpy throws an error on one site or one search term, catch it and continue with the others. Never crash the whole pipeline because LinkedIn rate-limited.
- The Excel report is the primary output. Make it look professional and be immediately usable.
- Keep all scripts importable (use `if __name__ == "__main__"` guards) so main.py can orchestrate them.