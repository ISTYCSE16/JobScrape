(function () {
  'use strict';

  // ---- state ----
  var selectedJobId = null;
  var currentJob = null;
  var activeTab = 'description';

  // ---- api helper ----
  function api(path, opts) {
    return fetch(path, opts).then(function (res) {
      if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
      return res.json();
    });
  }

  // ---- formatting ----
  function esc(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function fmtSalary(j) {
    var min = j.salary_min, max = j.salary_max, p = j.salary_period;
    if (!min && !max) return 'Not listed';
    function f(n) { return n >= 1000 ? '$' + Math.round(n / 1000) + 'K' : '$' + Math.round(n); }
    var s = p === 'yearly' ? '/yr' : p === 'hourly' ? '/hr' : p === 'monthly' ? '/mo' : '';
    if (min && max) return f(min) + ' - ' + f(max) + s;
    if (min) return f(min) + '+' + s;
    return 'Up to ' + f(max) + s;
  }

  function fmtExp(y) {
    if (y === null || y === undefined) return '--';
    if (y === 0) return 'Entry level';
    return y + '+ yrs';
  }

  function fmtDate(s) {
    if (!s) return '--';
    try {
      var d = new Date(s), now = new Date(), h = Math.round((now - d) / 3600000);
      if (h < 1) return 'Just now';
      if (h < 24) return h + 'h ago';
      var days = Math.round(h / 24);
      return days === 1 ? '1 day ago' : days + ' days ago';
    } catch (e) { return s; }
  }

  function scoreClass(s) {
    if (s == null || s < 0) return '';
    if (s >= 70) return 'score-high';
    if (s >= 40) return 'score-mid';
    return 'score-low';
  }

  // ---- stats ----
  function loadStats() {
    api('/api/stats').then(function (s) {
      document.getElementById('count-recent').textContent = s.recent;
      document.getElementById('count-all').textContent = s.all;
      document.getElementById('count-saved').textContent = s.saved;
      document.getElementById('count-preferred').textContent = s.preferred;
    });
  }

  // ---- sidebar navigation ----
  function showOptions() {
    document.getElementById('sidebar-options').hidden = false;
    document.getElementById('sidebar-list').hidden = true;
    loadStats();
  }

  function showCategory(cat) {
    var titles = { recent: 'Jobs Found', all: 'All Jobs', saved: 'Saved Jobs', preferred: 'Preferred Companies' };
    document.getElementById('sidebar-options').hidden = true;
    document.getElementById('sidebar-list').hidden = false;
    document.getElementById('list-title').textContent = titles[cat] || cat;
    var listEl = document.getElementById('job-list');
    listEl.innerHTML = '<div class="loading"><span class="spinner"></span> Loading...</div>';
    api('/api/jobs?category=' + cat).then(function (jobs) {
      renderJobList(jobs);
    }).catch(function () {
      listEl.innerHTML = '<div class="error">Failed to load jobs</div>';
    });
  }

  function renderJobList(jobs) {
    var listEl = document.getElementById('job-list');
    if (!jobs.length) { listEl.innerHTML = '<div class="empty-list">No jobs found</div>'; return; }
    listEl.innerHTML = jobs.map(function (j) {
      return '<button class="job-item' + (j.id === selectedJobId ? ' active' : '') + '" data-job-id="' + j.id + '">'
        + '<div class="job-item-title">' + esc(j.title) + '</div>'
        + '<div class="job-item-meta">'
        + '<span>' + esc(j.company) + '</span>'
        + '<span class="job-item-dot">&middot;</span>'
        + '<span>' + fmtSalary(j) + '</span>'
        + '<span class="job-item-dot">&middot;</span>'
        + '<span>' + fmtExp(j.min_experience) + '</span>'
        + '</div>'
        + '<div class="job-item-footer">'
        + '<span>' + esc(j.site) + '</span>'
        + '<span>' + fmtDate(j.date_posted) + '</span>'
        + '</div>'
        + '</button>';
    }).join('');
  }

  // ---- detail pane ----
  function selectJob(id) {
    selectedJobId = id;
    activeTab = 'description';
    document.querySelectorAll('.job-item').forEach(function (el) {
      el.classList.toggle('active', parseInt(el.dataset.jobId) === id);
    });
    document.getElementById('job-detail').hidden = false;
    document.getElementById('empty-state').hidden = true;
    document.getElementById('scrape-progress').hidden = true;
    document.getElementById('tab-content').innerHTML = '<div class="loading"><span class="spinner"></span> Loading...</div>';
    api('/api/jobs/' + id).then(function (job) {
      currentJob = job;
      renderDetail(job);
    }).catch(function () {
      document.getElementById('tab-content').innerHTML = '<div class="error">Failed to load job</div>';
    });
  }

  function renderDetail(job) {
    var has = !!job.match;
    document.getElementById('tab-ats').hidden = !has;
    document.getElementById('tab-resume').hidden = !has;
    document.getElementById('tab-missing').hidden = !has;
    document.querySelectorAll('.tab').forEach(function (t) {
      t.classList.toggle('active', t.dataset.tab === activeTab);
    });
    renderTab(job, activeTab);
  }

  function renderTab(job, tab) {
    var c = document.getElementById('tab-content');
    if (tab === 'description') c.innerHTML = descriptionHTML(job);
    else if (tab === 'ats') c.innerHTML = atsHTML(job.match);
    else if (tab === 'resume') c.innerHTML = resumeHTML(job.match);
    else if (tab === 'missing') c.innerHTML = missingHTML(job.match);
  }

  // ---- tab renderers ----
  function descriptionHTML(job) {
    var has = !!job.match;
    var work = job.is_remote ? 'Remote' : 'On-site';
    return '<div class="detail-header">'
      + '<div class="detail-header-left">'
      + '<h1 class="detail-title">' + esc(job.title) + '</h1>'
      + '<p class="detail-company">' + esc(job.company) + '</p>'
      + '<div class="detail-meta">'
      + '<span>' + esc(job.location || '--') + '</span>'
      + '<span class="meta-sep">&middot;</span>'
      + '<span>' + fmtSalary(job) + '</span>'
      + '<span class="meta-sep">&middot;</span>'
      + '<span>' + esc(job.job_type || '--') + '</span>'
      + '<span class="meta-sep">&middot;</span>'
      + '<span>' + work + '</span>'
      + '</div>'
      + '<div class="detail-actions">'
      + (job.job_url ? '<a href="' + esc(job.job_url) + '" target="_blank" rel="noopener" class="btn btn-apply">View Original</a>' : '')
      + '<button class="btn ' + (job.is_saved ? 'btn-saved' : '') + '" id="save-btn" data-job-id="' + job.id + '">' + (job.is_saved ? 'Saved' : 'Save') + '</button>'
      + '</div>'
      + '</div>'
      + '<div class="detail-header-right">'
      + '<button class="btn ' + (has ? 'btn-matched' : 'btn-match') + '" id="match-btn" data-job-id="' + job.id + '"' + (has ? ' disabled' : '') + '>' + (has ? 'Matched' : 'Match Job') + '</button>'
      + (has ? '<div class="match-score-badge ' + scoreClass(job.match.match_score) + '">' + job.match.match_score + '</div>' : '')
      + '</div>'
      + '</div>'
      + '<div class="detail-description">' + esc(job.description || 'No description available') + '</div>';
  }

  function chipsHTML(items, cls) {
    if (!items || !items.length) return '<p class="none-text">None</p>';
    return '<div class="chips">' + items.map(function (k) {
      return '<span class="chip ' + cls + '">' + esc(k) + '</span>';
    }).join('') + '</div>';
  }

  function atsHTML(m) {
    if (!m) return '<p>No match data</p>';
    return '<div class="ats-section">'
      + '<div class="score-cards">'
      + '<div class="score-card ' + scoreClass(m.match_score) + '"><div class="score-card-num">' + (m.match_score != null ? m.match_score : '--') + '</div><div class="score-card-label">Overall Match</div></div>'
      + '<div class="score-card"><div class="score-card-num">' + (m.keyword_score != null ? m.keyword_score : '--') + '</div><div class="score-card-label">Keyword Coverage</div></div>'
      + '<div class="score-card"><div class="score-card-num">' + (m.context_fit_score != null ? m.context_fit_score : '--') + '</div><div class="score-card-label">Context Fit</div></div>'
      + '</div>'
      + '<p class="ats-formula">Score = 65% keyword coverage (required 2x weight) + 35% context fit</p>'
      + (m.ats_summary ? '<div class="ats-summary">' + esc(m.ats_summary) + '</div>' : '')
      + '<h3 class="section-title">Matched Keywords</h3>'
      + chipsHTML(m.matched_keywords, 'chip-matched')
      + '<h3 class="section-title">Missing Required Keywords</h3>'
      + chipsHTML(m.missing_required_keywords, 'chip-missing-req')
      + '<h3 class="section-title">Missing Preferred Keywords</h3>'
      + chipsHTML(m.missing_preferred_keywords, 'chip-missing-pref')
      + '</div>';
  }

  function resumeHTML(m) {
    if (!m) return '<p>No match data</p>';
    var sug = m.resume_suggestions || [];
    if (!sug.length) return '<div class="resume-section"><p class="none-text">No resume suggestions available.</p></div>';
    return '<div class="resume-section"><h2>Resume Suggestions</h2>'
      + sug.map(function (sec) {
        var changes = (sec.changes || []).map(function (c) {
          return '<div class="suggestion-item">'
            + '<span class="suggestion-type suggestion-type-' + (c.type || 'modify') + '">' + esc((c.type || 'modify').toUpperCase()) + '</span>'
            + '<div class="suggestion-target">' + esc(c.target) + '</div>'
            + '<div class="suggestion-text">' + esc(c.suggestion) + '</div>'
            + '<div class="suggestion-reason">' + esc(c.reason) + '</div>'
            + '</div>';
        }).join('');
        return '<div class="suggestion-section">'
          + '<div class="suggestion-section-title">' + esc(sec.section) + '</div>'
          + changes
          + '</div>';
      }).join('')
      + '</div>';
  }

  function missingHTML(m) {
    if (!m) return '<p>No match data</p>';
    var bits = m.missing_bits || [];
    if (!bits.length) return '<div class="missing-section"><p class="none-text">No critical missing qualifications found.</p></div>';
    return '<div class="missing-section"><h2>Missing Qualifications</h2>'
      + bits.map(function (b) {
        var cls = b.importance === 'critical' ? 'importance-critical' : b.importance === 'important' ? 'importance-important' : 'importance-nice';
        return '<div class="missing-item ' + cls + '">'
          + '<div class="missing-header">'
          + '<span class="missing-qual">' + esc(b.qualification) + '</span>'
          + '<span class="missing-importance">' + esc(b.importance) + '</span>'
          + (b.impact_score ? '<span class="missing-impact">Impact: ' + b.impact_score + '/10</span>' : '')
          + '</div>'
          + '<p class="missing-desc">' + esc(b.description) + '</p>'
          + '<p class="missing-mitigation"><strong>How to address:</strong> ' + esc(b.mitigation) + '</p>'
          + '</div>';
      }).join('')
      + '</div>';
  }

  // ---- match job ----
  function handleMatch(id) {
    var btn = document.getElementById('match-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Matching...';
    btn.className = 'btn btn-matching';
    api('/api/jobs/' + id + '/match', { method: 'POST' }).then(function (result) {
      currentJob.match = result;
      btn.textContent = 'Matched';
      btn.className = 'btn btn-matched';
      document.getElementById('tab-ats').hidden = false;
      document.getElementById('tab-resume').hidden = false;
      document.getElementById('tab-missing').hidden = false;
      activeTab = 'ats';
      document.querySelectorAll('.tab').forEach(function (t) {
        t.classList.toggle('active', t.dataset.tab === 'ats');
      });
      renderTab(currentJob, 'ats');
    }).catch(function (err) {
      btn.textContent = 'Match Failed - Retry';
      btn.className = 'btn btn-match';
      btn.disabled = false;
      alert('Matching failed: ' + err.message);
    });
  }

  // ---- save/unsave ----
  function handleSave(id) {
    var btn = document.getElementById('save-btn');
    var saved = currentJob.is_saved;
    var url = '/api/jobs/' + id + (saved ? '/unsave' : '/save');
    api(url, { method: 'POST' }).then(function () {
      currentJob.is_saved = saved ? 0 : 1;
      btn.textContent = currentJob.is_saved ? 'Saved' : 'Save';
      btn.classList.toggle('btn-saved', !!currentJob.is_saved);
      loadStats();
    });
  }

  // ---- scrape jobs ----
  var scrapeController = null;

  function showToast(msg, type) {
    var toast = document.createElement('div');
    toast.className = 'scrape-toast scrape-toast-' + type;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(function () { toast.style.opacity = '0'; }, 3000);
    setTimeout(function () { toast.remove(); }, 3400);
  }

  function showProgress() {
    document.getElementById('empty-state').hidden = true;
    document.getElementById('job-detail').hidden = true;
    var el = document.getElementById('scrape-progress');
    el.hidden = false;
    document.getElementById('progress-log').innerHTML = '';
    document.getElementById('progress-summary').textContent = '';
    document.getElementById('progress-title').textContent = 'Scraping Jobs...';
  }

  function hideProgress() {
    var el = document.getElementById('scrape-progress');
    el.hidden = false;
  }

  function addProgressLine(html, cls) {
    var log = document.getElementById('progress-log');
    var line = document.createElement('div');
    line.className = 'progress-line ' + (cls || '');
    line.innerHTML = html;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function updateLastLine(html, cls) {
    var log = document.getElementById('progress-log');
    var last = log.lastElementChild;
    if (last) {
      last.innerHTML = html;
      last.className = 'progress-line ' + (cls || '');
    }
  }

  function handleScrape() {
    var scrapeBtn = document.getElementById('scrape-btn');
    var stopBtn = document.getElementById('stop-btn');
    scrapeBtn.disabled = true;
    scrapeBtn.innerHTML = '<span class="spinner"></span> Scraping...';
    stopBtn.hidden = false;

    showProgress();

    var totalSearches = 0;
    var completed = 0;
    var errors = 0;
    var totalJobs = 0;

    scrapeController = new AbortController();

    fetch('/api/scrape', { method: 'POST', signal: scrapeController.signal })
      .then(function (res) {
        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        function read() {
          return reader.read().then(function (result) {
            if (result.done) { finish(); return; }
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop();
            lines.forEach(function (line) {
              if (line.startsWith('data: ')) {
                try {
                  var evt = JSON.parse(line.slice(6));
                  handleEvent(evt);
                } catch (e) {}
              }
            });
            return read();
          });
        }

        function handleEvent(evt) {
          if (evt.type === 'start') {
            totalSearches = evt.total_searches;
            document.getElementById('progress-summary').textContent = '0 / ' + totalSearches + ' searches';

          } else if (evt.type === 'searching') {
            addProgressLine(
              '<span class="spinner"></span> Searching <strong>' + esc(evt.term) + '</strong> in <strong>' + esc(evt.location) + '</strong>...',
              'progress-active'
            );

          } else if (evt.type === 'result') {
            completed++;
            document.getElementById('progress-summary').textContent = completed + ' / ' + totalSearches + ' searches';
            if (evt.count > 0) {
              totalJobs += evt.count;
              var storedInfo = evt.stored > 0 ? ' (' + evt.stored + ' new)' : '';
              updateLastLine(
                '<span class="progress-icon progress-ok">&#10003;</span> <strong>' + esc(evt.term) + '</strong> in <strong>' + esc(evt.location) + '</strong> &mdash; ' + evt.count + ' jobs' + storedInfo,
                'progress-success'
              );
              loadStats();
            } else {
              updateLastLine(
                '<span class="progress-icon progress-empty">&#8212;</span> <strong>' + esc(evt.term) + '</strong> in <strong>' + esc(evt.location) + '</strong> &mdash; no results',
                'progress-none'
              );
            }

          } else if (evt.type === 'error') {
            completed++;
            errors++;
            document.getElementById('progress-summary').textContent = completed + ' / ' + totalSearches + ' searches';
            updateLastLine(
              '<span class="progress-icon progress-fail">&#10007;</span> <strong>' + esc(evt.term) + '</strong> in <strong>' + esc(evt.location) + '</strong> &mdash; ' + esc(evt.message),
              'progress-error'
            );

          } else if (evt.type === 'done') {
            totalJobs = evt.total;
            var msg = totalJobs + ' jobs found';
            if (evt.new_jobs > 0) msg += ' (' + evt.new_jobs + ' new)';
            if (errors > 0) msg += ', ' + errors + ' errors logged';
            showToast(msg, 'success');

          } else if (evt.type === 'stopped') {
            showToast('Scraping stopped', 'success');

          } else if (evt.type === 'fatal') {
            showToast('Scrape crashed: ' + evt.message, 'error');
          }
        }

        function finish() {
          scrapeBtn.textContent = 'Scrape Jobs';
          scrapeBtn.disabled = false;
          stopBtn.hidden = true;
          scrapeController = null;
          document.getElementById('progress-title').textContent = 'Scrape Complete';
          loadStats();
        }

        return read();
      })
      .catch(function (err) {
        if (err.name === 'AbortError') {
          document.getElementById('progress-title').textContent = 'Scrape Stopped';
        } else {
          showToast('Scrape failed: ' + err.message, 'error');
        }
        scrapeBtn.textContent = 'Scrape Jobs';
        scrapeBtn.disabled = false;
        stopBtn.hidden = true;
        scrapeController = null;
        loadStats();
      });
  }

  function handleStop() {
    if (scrapeController) scrapeController.abort();
    fetch('/api/scrape/stop', { method: 'POST' });
  }

  // ---- event listeners ----
  document.getElementById('scrape-btn').addEventListener('click', handleScrape);
  document.getElementById('stop-btn').addEventListener('click', handleStop);

  document.querySelectorAll('.nav-item').forEach(function (item) {
    item.addEventListener('click', function () { showCategory(item.dataset.category); });
  });

  document.getElementById('go-back').addEventListener('click', showOptions);

  document.getElementById('job-list').addEventListener('click', function (e) {
    var el = e.target.closest('.job-item');
    if (el) selectJob(parseInt(el.dataset.jobId));
  });

  document.querySelectorAll('.tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      if (tab.hidden) return;
      activeTab = tab.dataset.tab;
      document.querySelectorAll('.tab').forEach(function (t) { t.classList.toggle('active', t === tab); });
      if (currentJob) renderTab(currentJob, activeTab);
    });
  });

  document.getElementById('tab-content').addEventListener('click', function (e) {
    if (e.target.id === 'match-btn' && !e.target.disabled) handleMatch(parseInt(e.target.dataset.jobId));
    if (e.target.id === 'save-btn') handleSave(parseInt(e.target.dataset.jobId));
  });

  // ---- init ----
  loadStats();
})();
