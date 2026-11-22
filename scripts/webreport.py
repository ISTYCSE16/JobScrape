"""Scored DataFrame -> static, dependency-free web report.

Generates output/site/index.html (sortable job list) and output/site/job.html
(per-job detail view: ATS score breakdown, matched/missing keywords, full
description). Job data is embedded inline as JSON in both pages so they work
by opening the HTML file directly in a browser (no local server required) or
via GitHub Pages / `python -m http.server`.

"View" in the list opens job.html?id=<row index> in a new tab.
"""

import ast
import json
import os
from datetime import date

import pandas as pd

OUTPUT_DIR = "output"
SITE_DIRNAME = "site"

LIST_FIELDS = [
    "required_keywords",
    "preferred_keywords",
    "matched_keywords",
    "strong_keywords",
    "missing_required_keywords",
    "missing_preferred_keywords",
    "missing_keywords",
]

JOB_FIELDS = [
    "company",
    "title",
    "location",
    "site",
    "job_type",
    "hours_since_posted",
    "job_url",
    "description",
    "match_score",
    "keyword_score",
    "context_fit_score",
    "job_title_core",
    "seniority_level",
    "required_keywords",
    "preferred_keywords",
    "matched_keywords",
    "missing_required_keywords",
    "missing_preferred_keywords",
    "cv_changes_summary",
]


def _clean(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    if pd.isna(value):
        return None
    return value


def _df_to_jobs(df: pd.DataFrame) -> list:
    jobs = []
    for row in df.itertuples(index=False):
        job = {field: _clean(getattr(row, field, None)) for field in JOB_FIELDS}
        for field in LIST_FIELDS:
            if job.get(field) is None:
                job[field] = []
        jobs.append(job)
    return jobs


def _maybe_parse_list(value):
    """Parse a Python-list-repr string (as written by df.to_csv) back into a list."""
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            pass
    return []


def jobs_from_csv(csv_path: str) -> list:
    df = pd.read_csv(csv_path)
    for field in LIST_FIELDS:
        if field in df.columns:
            df[field] = df[field].apply(_maybe_parse_list)
    return _df_to_jobs(df)


INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Job Matches</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f8fa; --card: #ffffff; --text: #1a1d23; --muted: #6b7280;
    --border: #e5e7eb; --accent: #2563eb;
    --green-bg: #dcfce7; --green-text: #166534;
    --yellow-bg: #fef9c3; --yellow-text: #854d0e;
    --red-bg: #fee2e2; --red-text: #991b1b;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #16181d; --card: #1f232b; --text: #e8eaed; --muted: #9aa1ac;
      --border: #2c313a; --accent: #60a5fa;
      --green-bg: #12351f; --green-text: #86efac;
      --yellow-bg: #3a3110; --yellow-text: #fde68a;
      --red-bg: #3a1414; --red-text: #fca5a5;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  h1 { font-size: 1.4rem; margin: 0 0 4px; }
  .subtitle { color: var(--muted); margin: 0 0 20px; font-size: 0.9rem; }
  .controls { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .controls input, .controls select {
    padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--card); color: var(--text); font-size: 0.9rem;
  }
  .controls input { flex: 1; min-width: 160px; }
  .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--card); }
  table { border-collapse: collapse; width: 100%; min-width: 720px; }
  th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
  th { cursor: pointer; user-select: none; color: var(--muted); font-weight: 600; white-space: nowrap; }
  th:hover { color: var(--text); }
  tr:last-child td { border-bottom: none; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-weight: 700; font-size: 0.82rem; }
  .badge-green { background: var(--green-bg); color: var(--green-text); }
  .badge-yellow { background: var(--yellow-bg); color: var(--yellow-text); }
  .badge-red { background: var(--red-bg); color: var(--red-text); }
  .view-btn {
    display: inline-block; padding: 6px 14px; border-radius: 8px; background: var(--accent);
    color: white; text-decoration: none; font-size: 0.85rem; font-weight: 600; white-space: nowrap;
  }
  .view-btn:hover { opacity: 0.9; }
  .muted { color: var(--muted); }
  .empty { padding: 40px; text-align: center; color: var(--muted); }
</style>
</head>
<body>
  <h1>Job Matches</h1>
  <p class="subtitle" id="subtitle"></p>
  <div class="controls">
    <input id="search" type="text" placeholder="Filter by company, title, or location...">
    <select id="siteFilter"><option value="">All sites</option></select>
  </div>
  <div class="table-wrap">
    <table id="jobsTable">
      <thead>
        <tr>
          <th data-key="company">Company</th>
          <th data-key="title">Title</th>
          <th data-key="location">Location</th>
          <th data-key="site">Site</th>
          <th data-key="hours_since_posted">Posted</th>
          <th data-key="match_score">Match</th>
          <th></th>
        </tr>
      </thead>
      <tbody id="jobsBody"></tbody>
    </table>
    <div id="emptyState" class="empty" hidden>No jobs match your filter.</div>
  </div>

<script>
const JOBS = __JOBS_JSON__;

function scoreBadgeClass(score) {
  if (score === null || score === undefined || score < 0) return '';
  if (score >= 70) return 'badge-green';
  if (score >= 40) return 'badge-yellow';
  return 'badge-red';
}

function fmtHours(h) {
  if (h === null || h === undefined || !isFinite(h)) return '—';
  if (h < 1) return '<1h ago';
  if (h < 24) return Math.round(h) + 'h ago';
  return Math.round(h / 24) + 'd ago';
}

let sortKey = 'match_score';
let sortDir = -1;

function render() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const site = document.getElementById('siteFilter').value;

  let rows = JOBS.map((job, idx) => ({ job, idx }));

  if (q) {
    rows = rows.filter(({ job }) =>
      (job.company || '').toLowerCase().includes(q) ||
      (job.title || '').toLowerCase().includes(q) ||
      (job.location || '').toLowerCase().includes(q)
    );
  }
  if (site) {
    rows = rows.filter(({ job }) => job.site === site);
  }

  rows.sort((a, b) => {
    let av = a.job[sortKey], bv = b.job[sortKey];
    if (av === null || av === undefined) av = -Infinity;
    if (bv === null || bv === undefined) bv = -Infinity;
    if (typeof av === 'string') return sortDir * av.localeCompare(bv);
    return sortDir * (av - bv);
  });

  const tbody = document.getElementById('jobsBody');
  tbody.innerHTML = '';
  document.getElementById('emptyState').hidden = rows.length > 0;

  for (const { job, idx } of rows) {
    const tr = document.createElement('tr');
    const score = job.match_score;
    tr.innerHTML = `
      <td>${job.company || ''}</td>
      <td>${job.title || ''}</td>
      <td>${job.location || ''}</td>
      <td class="muted">${job.site || ''}</td>
      <td class="muted">${fmtHours(job.hours_since_posted)}</td>
      <td><span class="badge ${scoreBadgeClass(score)}">${score >= 0 ? score : 'N/A'}</span></td>
      <td><a class="view-btn" href="job.html?id=${idx}" target="_blank" rel="noopener">View &rarr;</a></td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById('subtitle').textContent =
    `${rows.length} of ${JOBS.length} jobs shown — sorted by ${sortKey.replace(/_/g,' ')} (${sortDir === -1 ? 'desc' : 'asc'})`;
}

document.querySelectorAll('th[data-key]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    if (sortKey === key) { sortDir *= -1; } else { sortKey = key; sortDir = key === 'match_score' ? -1 : 1; }
    render();
  });
});

const sites = [...new Set(JOBS.map(j => j.site).filter(Boolean))].sort();
const siteFilter = document.getElementById('siteFilter');
for (const s of sites) {
  const opt = document.createElement('option');
  opt.value = s; opt.textContent = s;
  siteFilter.appendChild(opt);
}

document.getElementById('search').addEventListener('input', render);
document.getElementById('siteFilter').addEventListener('change', render);

render();
</script>
</body>
</html>
"""

JOB_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Job Detail</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f8fa; --card: #ffffff; --text: #1a1d23; --muted: #6b7280;
    --border: #e5e7eb; --accent: #2563eb;
    --green-bg: #dcfce7; --green-text: #166534; --green-border: #86efac;
    --yellow-bg: #fef9c3; --yellow-text: #854d0e;
    --red-bg: #fee2e2; --red-text: #991b1b; --red-border: #fca5a5;
    --gray-bg: #f3f4f6; --gray-text: #4b5563;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #16181d; --card: #1f232b; --text: #e8eaed; --muted: #9aa1ac;
      --border: #2c313a; --accent: #60a5fa;
      --green-bg: #12351f; --green-text: #86efac; --green-border: #1f5c34;
      --yellow-bg: #3a3110; --yellow-text: #fde68a;
      --red-bg: #3a1414; --red-text: #fca5a5; --red-border: #5c2323;
      --gray-bg: #2a2e36; --gray-text: #c2c7d0;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width: 860px; margin: 0 auto; }
  a.back { color: var(--accent); text-decoration: none; font-size: 0.9rem; }
  a.back:hover { text-decoration: underline; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 24px; margin-top: 16px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px; }
  .company { font-size: 1.05rem; color: var(--muted); margin: 0 0 16px; }
  .meta { display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted); font-size: 0.88rem; margin-bottom: 16px; }
  .apply-btn {
    display: inline-block; padding: 10px 18px; border-radius: 8px; background: var(--accent);
    color: white; text-decoration: none; font-weight: 600; font-size: 0.9rem;
  }
  .score-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 20px 0; }
  .score-box { flex: 1; min-width: 140px; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid var(--border); }
  .score-box .num { font-size: 2rem; font-weight: 800; line-height: 1; }
  .score-box .label { margin-top: 6px; color: var(--muted); font-size: 0.8rem; }
  .score-green { background: var(--green-bg); }
  .score-green .num { color: var(--green-text); }
  .score-yellow { background: var(--yellow-bg); }
  .score-yellow .num { color: var(--yellow-text); }
  .score-red { background: var(--red-bg); }
  .score-red .num { color: var(--red-text); }
  .formula-note { color: var(--muted); font-size: 0.8rem; margin-top: -8px; margin-bottom: 20px; }
  h2 { font-size: 1.05rem; margin: 24px 0 10px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { padding: 5px 12px; border-radius: 999px; font-size: 0.82rem; border: 1px solid var(--border); }
  .chip-matched { background: var(--green-bg); color: var(--green-text); border-color: var(--green-border); }
  .chip-missing-required { background: var(--red-bg); color: var(--red-text); border-color: var(--red-border); }
  .chip-missing-preferred { background: var(--gray-bg); color: var(--gray-text); }
  .summary { line-height: 1.5; white-space: pre-wrap; }
  .description { line-height: 1.55; white-space: pre-wrap; font-size: 0.92rem; }
  .none { color: var(--muted); font-size: 0.85rem; }
</style>
</head>
<body>
  <div class="wrap">
    <a class="back" href="index.html">&larr; Back to job list</a>
    <div id="content"></div>
  </div>

<script>
const JOBS = __JOBS_JSON__;
const params = new URLSearchParams(location.search);
const id = parseInt(params.get('id'), 10);
const job = JOBS[id];
const content = document.getElementById('content');

function scoreClass(score) {
  if (score === null || score === undefined || score < 0) return '';
  if (score >= 70) return 'score-green';
  if (score >= 40) return 'score-yellow';
  return 'score-red';
}

function chips(items, cls) {
  if (!items || items.length === 0) return '<p class="none">None</p>';
  return '<div class="chips">' + items.map(k => `<span class="chip ${cls}">${k}</span>`).join('') + '</div>';
}

if (!job) {
  content.innerHTML = '<div class="card"><p>Job not found.</p></div>';
} else {
  const matched = job.matched_keywords || [];
  const missingReq = job.missing_required_keywords || [];
  const missingPref = job.missing_preferred_keywords || [];
  const score = job.match_score;
  const kwScore = job.keyword_score;
  const ctxScore = job.context_fit_score;

  content.innerHTML = `
    <div class="card">
      <h1>${job.title || ''}</h1>
      <p class="company">${job.company || ''}${job.job_title_core ? ' &middot; ' + job.job_title_core : ''}${job.seniority_level ? ' &middot; ' + job.seniority_level : ''}</p>
      <div class="meta">
        <span>${job.location || ''}</span>
        <span>${job.site || ''}</span>
        <span>${job.job_type || ''}</span>
      </div>
      ${job.job_url ? `<a class="apply-btn" href="${job.job_url}" target="_blank" rel="noopener">Open original listing &rarr;</a>` : ''}

      <div class="score-row">
        <div class="score-box ${scoreClass(score)}">
          <div class="num">${score >= 0 ? score : 'N/A'}</div>
          <div class="label">Overall ATS Match</div>
        </div>
        <div class="score-box">
          <div class="num">${kwScore !== null && kwScore !== undefined ? kwScore : '—'}</div>
          <div class="label">Keyword Coverage</div>
        </div>
        <div class="score-box">
          <div class="num">${ctxScore !== null && ctxScore !== undefined ? ctxScore : '—'}</div>
          <div class="label">Context Fit</div>
        </div>
      </div>
      <p class="formula-note">ATS-style formula: 65% keyword coverage (required keywords weighted 2x vs. preferred) + 35% context fit (seniority &amp; career-trajectory match).</p>

      <h2>Matched keywords</h2>
      ${chips(matched, 'chip-matched')}

      <h2>Missing required keywords</h2>
      ${chips(missingReq, 'chip-missing-required')}

      <h2>Missing preferred keywords</h2>
      ${chips(missingPref, 'chip-missing-preferred')}

      <h2>Suggested CV changes</h2>
      <p class="summary">${job.cv_changes_summary || 'N/A'}</p>

      <h2>Full job description</h2>
      <p class="description">${(job.description || '').replace(/</g, '&lt;')}</p>
    </div>
  `;
}
</script>
</body>
</html>
"""


def _write_pages(jobs: list, site_dir: str):
    os.makedirs(site_dir, exist_ok=True)
    jobs_json = json.dumps(jobs)

    with open(os.path.join(site_dir, "index.html"), "w") as f:
        f.write(INDEX_HTML_TEMPLATE.replace("__JOBS_JSON__", jobs_json))

    with open(os.path.join(site_dir, "job.html"), "w") as f:
        f.write(JOB_HTML_TEMPLATE.replace("__JOBS_JSON__", jobs_json))


def generate_web_report(df: pd.DataFrame, output_dir: str = OUTPUT_DIR) -> str:
    site_dir = os.path.join(output_dir, SITE_DIRNAME)
    jobs = _df_to_jobs(df)
    _write_pages(jobs, site_dir)
    index_path = os.path.join(site_dir, "index.html")
    print(f"Web report saved: {index_path}")
    return index_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        jobs = jobs_from_csv(sys.argv[1])
        site_dir = os.path.join(OUTPUT_DIR, SITE_DIRNAME)
        _write_pages(jobs, site_dir)
        print(f"Web report saved: {os.path.join(site_dir, 'index.html')}")
    else:
        sample = pd.DataFrame(
            [
                {
                    "company": "Example Corp",
                    "title": "Software Developer",
                    "location": "Edmonton, AB",
                    "site": "linkedin",
                    "job_type": "fulltime",
                    "hours_since_posted": 5,
                    "job_url": "https://example.com/job/1",
                    "description": "We are looking for a Python developer with ML experience.",
                    "match_score": 85,
                    "keyword_score": 90,
                    "context_fit_score": 75,
                    "job_title_core": "Software Developer",
                    "seniority_level": "mid",
                    "required_keywords": ["Python", "Machine Learning"],
                    "preferred_keywords": ["Docker", "AWS"],
                    "matched_keywords": ["Python", "Machine Learning"],
                    "missing_required_keywords": [],
                    "missing_preferred_keywords": ["Docker", "AWS"],
                    "cv_changes_summary": "Lead with ML pipeline experience.",
                }
            ]
        )
        generate_web_report(sample)
