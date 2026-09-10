# JobScrape

Automated job search pipeline using JobSpy + Claude API + GitHub Actions.

## Architecture

```
                 daily, 8 AM MST (GitHub Actions cron)
                              │
                              ▼
   ┌─────────┐   ┌─────────┐   ┌──────────┐        ┌──────────┐
   │ Scrape  │──▶│  Score  │──▶│  Report  │   -->   │  Tailor  │
   └─────────┘   └─────────┘   └──────────┘        └──────────┘
   scripts/       scripts/       scripts/            tailor_jobs.py
   scrape.py      score.py       report.py           (manual, on demand)

   JobSpy pulls    Claude Haiku   openpyxl writes    Claude Haiku writes
   LinkedIn,        scores each    output/            a tailored CV +
   Indeed, Google,  job 0-100      jobs_YYYY-MM-DD    job notes into
   ZipRecruiter     against your   .xlsx (+ .csv)     applications/ for
   listings         skills/CV                          jobs you pick
```

- `main.py` orchestrates **Scrape → Score → Report** and is what the GitHub
  Action runs every day.
- `tailor_jobs.py` is run manually, after you've reviewed the Excel report,
  to generate tailored CV suggestions for specific jobs.

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your Anthropic API key as an environment variable locally:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
3. For the scheduled GitHub Action, add `ANTHROPIC_API_KEY` as a repository
   secret: **Settings → Secrets and variables → Actions → New repository
   secret**.
4. Edit the config files with your own information:
   - `config/criteria.yaml` — search terms, locations, job sites, freshness window
   - `config/skills.md` — your skills and experience summary
   - `config/base_cv.md` — your current CV content (markdown)

## Local usage

Run the full daily pipeline (scrape → score → report):

```bash
python main.py
```

This writes `output/jobs_YYYY-MM-DD.xlsx` and `output/jobs_YYYY-MM-DD.csv`.

After reviewing the Excel report, generate tailored CV suggestions for the
rows you want to apply to (0-indexed):

```bash
python tailor_jobs.py output/jobs_2026-09-10.csv 0 3 7
```

This creates a folder per job under `applications/` (git-ignored) containing
`tailored_cv.md` and `job_details.md`.

## Scheduling

`.github/workflows/daily-search.yml` runs the pipeline every day at 8 AM MST
and commits the new `output/` files back to the repo. You can also trigger
it manually from the **Actions** tab (`workflow_dispatch`).

## Cost estimate

At Haiku rates, scoring ~50 jobs/day costs roughly **$0.05–$0.15/day**.
Tailoring is on-demand and only costs per job you explicitly select.
