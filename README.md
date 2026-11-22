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
   scrape.py      score.py      report.py +          (manual, on demand)
                                 webreport.py

   JobSpy pulls    ATS-style      openpyxl writes    Claude Haiku writes
   LinkedIn,        hybrid score   output/            a tailored CV +
   Indeed, Google,  (see below)    jobs_YYYY-MM-DD    job notes into
   ZipRecruiter     per job        .xlsx/.csv, plus   applications/ for
   listings                        output/site/       jobs you pick
                                    (web view)
```

- `main.py` orchestrates **Scrape → Score → Report → Web report** and is what
  the GitHub Action runs every day.
- `tailor_jobs.py` is run manually, after you've reviewed the Excel or web
  report, to generate tailored CV suggestions for specific jobs.

## ATS-style match scoring

Real Applicant Tracking Systems rank candidates mainly by deterministic
**keyword coverage** against the job's stated requirements, not by a single
subjective "vibe" score. `scripts/score.py` follows that model instead of
just asking an LLM to guess a number:

1. One Claude Haiku call per job extracts structured requirements from the
   posting: `required_keywords` (must-have hard skills/tools stated as
   minimum qualifications), `preferred_keywords` (nice-to-have), and a
   `context_fit_score` (0-100) judging seniority/career-trajectory fit —
   the qualitative part a keyword scan can't capture.
2. Python then deterministically checks which of those keywords actually
   appear in your `config/skills.md` + `config/base_cv.md` text, using
   word-boundary matching — the same mechanical approach a real ATS parser
   uses on a resume.
3. The final **Match Score** is a weighted blend:
   `65% keyword coverage (required keywords weighted 2x vs. preferred) + 35% context fit`.

Every job carries the full breakdown — `keyword_score`, `context_fit_score`,
matched keywords, and separate missing-required vs. missing-preferred
keyword lists — so you can see exactly why it scored the way it did, both in
the Excel report and the web view below.

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

This writes `output/jobs_YYYY-MM-DD.xlsx`, `output/jobs_YYYY-MM-DD.csv`, and
a static web report at `output/site/`.

### Web report

Open `output/site/index.html` directly in a browser — it's a self-contained
static page (no server needed) listing every job, sortable by clicking a
column header and filterable by company/title/location or site. Click
**View →** on any row to open that job's full detail page in a new tab:
overall ATS match score, the keyword-coverage/context-fit breakdown, chips
for matched keywords and for missing required vs. missing preferred
keywords, the suggested CV changes, and the full (untruncated) job
description with a link to the original listing.

If your browser blocks local `file://` access to the page's own assets, serve
it instead:

```bash
python -m http.server 8000 --directory output/site
# then open http://localhost:8000
```

To regenerate the web report from an already-saved CSV without re-running
the whole pipeline:

```bash
python scripts/webreport.py output/jobs_2026-09-10.csv
```

After reviewing the report, generate tailored CV suggestions for the
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
