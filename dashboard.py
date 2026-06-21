#!/usr/bin/env python3
"""
Juniper AI Network Assistant — Web Dashboard
Serves a local web UI showing audit reports from the reports/ directory.
Run: ./juniper-env/bin/python dashboard.py
Then open: http://localhost:5000
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template_string, abort, send_file

# ── Config ────────────────────────────────────────────────────────────────────
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
HOST        = "0.0.0.0"   # listen on all interfaces so team can access on LAN
PORT        = 5000
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)

# ── HTML Template ─────────────────────────────────────────────────────────────
BASE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}Juniper AI Audit{% endblock %}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@300;400;500;600&display=swap');

  :root {
    --bg:        #0d1117;
    --surface:   #161b22;
    --border:    #21262d;
    --accent:    #58a6ff;
    --red:       #f85149;
    --green:     #3fb950;
    --yellow:    #d29922;
    --grey:      #8b949e;
    --text:      #e6edf3;
    --text-dim:  #8b949e;
    --mono:      'JetBrains Mono', monospace;
    --sans:      'Inter', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }

  /* ── Nav ── */
  nav {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    height: 52px;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  nav .logo {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.05em;
    text-decoration: none;
  }
  nav .logo span { color: var(--text-dim); font-weight: 400; }
  nav .spacer { flex: 1; }
  nav .nav-tag {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    background: var(--border);
    padding: 2px 8px;
    border-radius: 4px;
  }

  /* ── Layout ── */
  .container { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }

  /* ── Page header ── */
  .page-header { margin-bottom: 28px; }
  .page-header h1 {
    font-size: 20px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 4px;
  }
  .page-header p { color: var(--text-dim); font-size: 13px; }

  /* ── Report grid ── */
  .reports-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .report-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    text-decoration: none;
    color: inherit;
    transition: border-color 0.15s;
  }
  .report-card:hover { border-color: var(--accent); }

  .report-card .timestamp {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text-dim);
    min-width: 160px;
  }

  .report-card .device {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    min-width: 140px;
  }

  .report-card .tags {
    display: flex;
    gap: 6px;
    flex: 1;
  }

  .tag {
    font-size: 11px;
    font-family: var(--mono);
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
  }
  .tag-critique  { background: #1f2d3d; color: #58a6ff; border: 1px solid #2d4a6d; }
  .tag-stig      { background: #2d1f3d; color: #bc8cff; border: 1px solid #4a2d6d; }
  .tag-pass      { background: #1a2f1a; color: #3fb950; border: 1px solid #2a4a2a; }
  .tag-fail      { background: #2f1a1a; color: #f85149; border: 1px solid #4a2a2a; }
  .tag-config    { background: #2a2a1f; color: #d29922; border: 1px solid #4a3a1a; }

  .report-card .arrow {
    color: var(--text-dim);
    font-size: 16px;
    margin-left: auto;
  }

  .empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-dim);
  }
  .empty p { font-family: var(--mono); font-size: 13px; margin-top: 8px; }

  /* ── Report detail ── */
  .report-detail-header {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 28px;
    flex-wrap: wrap;
  }
  .report-detail-header .back {
    color: var(--accent);
    text-decoration: none;
    font-size: 13px;
    font-family: var(--mono);
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 12px;
  }
  .report-detail-header .back:hover { text-decoration: underline; }

  /* ── Score bar ── */
  .score-row {
    display: flex;
    gap: 16px;
    margin-bottom: 28px;
    flex-wrap: wrap;
  }
  .score-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    flex: 1;
    min-width: 120px;
  }
  .score-card .label {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
  }
  .score-card .value {
    font-size: 28px;
    font-weight: 600;
    font-family: var(--mono);
  }
  .score-card .value.red   { color: var(--red); }
  .score-card .value.green { color: var(--green); }
  .score-card .value.blue  { color: var(--accent); }
  .score-card .value.grey  { color: var(--grey); }

  /* ── Progress bar ── */
  .progress-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 28px;
  }
  .progress-label {
    font-size: 11px;
    font-family: var(--mono);
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
  }
  .progress-bar {
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--red), var(--green));
    border-radius: 4px;
    transition: width 0.5s ease;
  }

  /* ── Sections ── */
  .section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 16px;
    overflow: hidden;
  }
  .section-header {
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    user-select: none;
  }
  .section-header:hover { background: #1c2128; }
  .section-title {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    flex: 1;
  }
  .section-count {
    font-family: var(--mono);
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 10px;
    background: var(--border);
    color: var(--text-dim);
  }
  .section-toggle { color: var(--text-dim); font-size: 12px; }

  /* ── Finding rows ── */
  .finding {
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 12px;
    align-items: start;
  }
  .finding:last-child { border-bottom: none; }

  .finding-status {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    flex-shrink: 0;
    margin-top: 1px;
  }
  .finding-status.fail  { background: #2f1a1a; color: var(--red); border: 1px solid #4a2a2a; }
  .finding-status.pass  { background: #1a2f1a; color: var(--green); border: 1px solid #2a4a2a; }
  .finding-status.info  { background: #1f2d3d; color: var(--accent); border: 1px solid #2d4a6d; }

  .finding-body {}
  .finding-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text);
    margin-bottom: 4px;
  }
  .finding-detail {
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 6px;
  }
  .finding-cmd {
    font-family: var(--mono);
    font-size: 11px;
    color: #79c0ff;
    background: #0d1117;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 10px;
    margin-top: 4px;
    white-space: pre-wrap;
    word-break: break-all;
  }

  /* ── Files section ── */
  .files-grid {
    padding: 16px 20px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .file-link {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    background: var(--border);
    padding: 4px 12px;
    border-radius: 4px;
    text-decoration: none;
    border: 1px solid transparent;
    transition: border-color 0.15s;
  }
  .file-link:hover { border-color: var(--accent); }
  .file-link.cklb { color: #bc8cff; }

  /* ── Raw text view ── */
  .raw-content {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text);
    background: var(--bg);
    padding: 20px;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.7;
    border-top: 1px solid var(--border);
  }

  .collapsible { display: block; }
  .collapsible.collapsed { display: none; }
</style>
</head>
<body>
<nav>
  <a class="logo" href="/">juniper-ai<span>/audit</span></a>
  <div class="spacer"></div>
  <span class="nav-tag">A5 · local</span>
</nav>
{% block content %}{% endblock %}
<script>
  document.querySelectorAll('.section-header').forEach(h => {
    h.addEventListener('click', () => {
      const body = h.nextElementSibling;
      const tog  = h.querySelector('.section-toggle');
      if (body.classList.contains('collapsed')) {
        body.classList.remove('collapsed');
        if (tog) tog.textContent = '▲';
      } else {
        body.classList.add('collapsed');
        if (tog) tog.textContent = '▼';
      }
    });
  });
</script>
</body>
</html>"""

INDEX_HTML = BASE_HTML.replace("{% block title %}Juniper AI Audit{% endblock %}", "Juniper AI Audit — Reports").replace("{% block content %}{% endblock %}", """
<div class="container">
  <div class="page-header">
    <h1>Audit Reports</h1>
    <p>{{ reports|length }} report{{ 's' if reports|length != 1 else '' }} — most recent first</p>
  </div>

  {% if reports %}
  <div class="reports-grid">
    {% for r in reports %}
    <a class="report-card" href="/report/{{ r.folder }}">
      <div class="timestamp">{{ r.date }} {{ r.time }}</div>
      <div class="device">{{ r.device }}</div>
      <div class="tags">
        {% if r.has_config %}<span class="tag tag-config">config</span>{% endif %}
        {% if r.has_critique %}<span class="tag tag-critique">critique</span>{% endif %}
        {% if r.has_stig %}
          <span class="tag tag-stig">STIG</span>
          {% if r.fail_count is not none %}<span class="tag tag-fail">{{ r.fail_count }} fail</span>{% endif %}
          {% if r.pass_count is not none %}<span class="tag tag-pass">{{ r.pass_count }} pass</span>{% endif %}
        {% endif %}
      </div>
      <span class="arrow">›</span>
    </a>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty">
    <div style="font-size:32px">📁</div>
    <p>No reports yet. Run an audit from start.py to generate reports.</p>
  </div>
  {% endif %}
</div>
""")

DETAIL_HTML = BASE_HTML.replace("{% block title %}Juniper AI Audit{% endblock %}", "{{ folder }} — Juniper AI Audit").replace("{% block content %}{% endblock %}", """
<div class="container">
  <a class="back" href="/">← All Reports</a>

  <div class="page-header">
    <h1>{{ device }}</h1>
    <p style="font-family: var(--mono); font-size: 12px;">{{ folder }}</p>
  </div>

  <!-- Score cards -->
  {% if fail_count is not none %}
  <div class="score-row">
    <div class="score-card">
      <div class="label">STIG Failures</div>
      <div class="value red">{{ fail_count }}</div>
    </div>
    <div class="score-card">
      <div class="label">STIG Passes</div>
      <div class="value green">{{ pass_count }}</div>
    </div>
    <div class="score-card">
      <div class="label">Total Rules</div>
      <div class="value blue">{{ total_count }}</div>
    </div>
    <div class="score-card">
      <div class="label">Compliance</div>
      <div class="value grey">{{ compliance_pct }}%</div>
    </div>
  </div>
  <div class="progress-wrap">
    <div class="progress-label">
      <span>Compliance Score</span>
      <span>{{ compliance_pct }}%</span>
    </div>
    <div class="progress-bar">
      <div class="progress-fill" style="width: {{ compliance_pct }}%"></div>
    </div>
  </div>
  {% endif %}

  <!-- Files -->
  <div class="section">
    <div class="section-header">
      <span class="section-title">Report Files</span>
      <span class="section-toggle">▲</span>
    </div>
    <div class="files-grid collapsible">
      {% for f in files %}
      <a class="file-link {% if '.cklb' in f %}cklb{% endif %}" href="/report/{{ folder }}/file/{{ f }}">{{ f }}</a>
      {% endfor %}
    </div>
  </div>

  <!-- Critique findings -->
  {% if critique_issues %}
  <div class="section">
    <div class="section-header">
      <span class="section-title">Day One Book Critique</span>
      <span class="section-count">{{ critique_issues|length }} issues</span>
      <span class="section-toggle">▲</span>
    </div>
    <div class="collapsible">
      {% for issue in critique_issues %}
      <div class="finding">
        <div class="finding-status fail">✕</div>
        <div class="finding-body">
          <div class="finding-title">{{ issue.title }}</div>
          {% if issue.detail %}<div class="finding-detail">{{ issue.detail }}</div>{% endif %}
          {% if issue.cmds %}<div class="finding-cmd">{{ issue.cmds }}</div>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  {% if critique_correct %}
  <div class="section">
    <div class="section-header">
      <span class="section-title">Correctly Configured</span>
      <span class="section-count">{{ critique_correct|length }}</span>
      <span class="section-toggle">▲</span>
    </div>
    <div class="collapsible">
      {% for item in critique_correct %}
      <div class="finding">
        <div class="finding-status pass">✓</div>
        <div class="finding-body">
          <div class="finding-title">{{ item }}</div>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- STIG findings -->
  {% if stig_fails %}
  <div class="section">
    <div class="section-header">
      <span class="section-title">STIG Failures</span>
      <span class="section-count">{{ stig_fails|length }}</span>
      <span class="section-toggle">▲</span>
    </div>
    <div class="collapsible">
      {% for f in stig_fails %}
      <div class="finding">
        <div class="finding-status fail">✕</div>
        <div class="finding-body">
          <div class="finding-title">{{ f.vuln_id }}</div>
          {% if f.justification %}<div class="finding-detail">{{ f.justification }}</div>{% endif %}
          {% if f.fixes %}<div class="finding-cmd">{{ f.fixes }}</div>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  {% if stig_passes %}
  <div class="section">
    <div class="section-header">
      <span class="section-title">STIG Passes</span>
      <span class="section-count">{{ stig_passes|length }}</span>
      <span class="section-toggle">▲</span>
    </div>
    <div class="collapsible collapsed">
      {% for f in stig_passes %}
      <div class="finding">
        <div class="finding-status pass">✓</div>
        <div class="finding-body">
          <div class="finding-title">{{ f.vuln_id }}</div>
          {% if f.justification %}<div class="finding-detail">{{ f.justification }}</div>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

</div>
""")


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_stig_audit(path):
    """Parse stig_audit.txt into structured findings."""
    findings = []
    try:
        with open(path) as f:
            content = f.read()

        pass_count = fail_count = 0
        # Get counts from header
        for line in content.splitlines():
            if line.startswith("PASS"):
                try: pass_count = int(line.split(":")[1].strip())
                except: pass
            if line.startswith("FAIL"):
                try: fail_count = int(line.split(":")[1].strip())
                except: pass

        blocks = content.split("---")
        for block in blocks:
            lines = block.strip().splitlines()
            finding = {}
            fixes = []
            for line in lines:
                line = line.strip()
                if line.startswith("VULN_ID:"):
                    finding["vuln_id"] = line.replace("VULN_ID:", "").strip()
                elif line.startswith("STATUS:"):
                    finding["status"] = line.replace("STATUS:", "").strip()
                elif line.startswith("JUSTIFICATION:"):
                    finding["justification"] = line.replace("JUSTIFICATION:", "").strip()
                elif line.startswith("FIX:") and "NONE" not in line:
                    cmd = line.replace("FIX:", "").strip()
                    if cmd:
                        fixes.append(cmd)
            if "vuln_id" in finding:
                finding["fixes"] = "\n".join(fixes)
                findings.append(finding)

        return findings, pass_count, fail_count
    except Exception:
        return [], 0, 0


def parse_critique(path):
    """Parse critique.txt into issues and correct items."""
    issues  = []
    correct = []
    try:
        with open(path) as f:
            content = f.read()

        in_issues  = False
        in_correct = False
        current    = None
        cmds       = []

        for line in content.splitlines():
            if line.strip().startswith("ISSUES"):
                in_issues  = True
                in_correct = False
                continue
            if line.strip().startswith("RECOMMENDATIONS"):
                if current:
                    current["cmds"] = "\n".join(cmds)
                    issues.append(current)
                    current = None
                    cmds = []
                in_issues = False
                continue
            if line.strip().startswith("CORRECT"):
                in_issues  = False
                in_correct = True
                continue

            if in_issues:
                if line.strip().startswith("ISSUE"):
                    if current:
                        current["cmds"] = "\n".join(cmds)
                        issues.append(current)
                    title = line.strip().split(":", 1)[-1].strip() if ":" in line else line.strip()
                    current = {"title": title, "detail": "", "cmds": ""}
                    cmds = []
                elif current:
                    stripped = line.strip()
                    if stripped.startswith(("set ", "delete ")):
                        cmds.append(stripped)
                    elif stripped and not stripped.startswith("set ") and not stripped.startswith("delete "):
                        if not current["detail"]:
                            current["detail"] = stripped

            if in_correct and line.strip():
                correct.append(line.strip())

        if current:
            current["cmds"] = "\n".join(cmds)
            issues.append(current)

    except Exception:
        pass
    return issues, correct


def get_reports():
    """List all report folders sorted newest first."""
    if not os.path.exists(REPORTS_DIR):
        return []

    reports = []
    for folder in sorted(os.listdir(REPORTS_DIR), reverse=True):
        folder_path = os.path.join(REPORTS_DIR, folder)
        if not os.path.isdir(folder_path):
            continue

        files = os.listdir(folder_path)

        # Parse folder name: YYYYMMDD_HHMMSS_IP
        parts = folder.split("_")
        try:
            date = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:8]}"
            time = f"{parts[1][:2]}:{parts[1][2:4]}:{parts[1][4:6]}"
            device = ".".join(parts[2:]) if len(parts) > 2 else "unknown"
        except Exception:
            date, time, device = folder, "", "unknown"

        # Parse counts from stig_audit.txt if present
        pass_count = fail_count = None
        audit_path = os.path.join(folder_path, "stig_audit.txt")
        if os.path.exists(audit_path):
            _, p, f = parse_stig_audit(audit_path)
            pass_count, fail_count = p, f

        reports.append({
            "folder":      folder,
            "date":        date,
            "time":        time,
            "device":      device,
            "has_config":  "config.txt" in files,
            "has_critique": "critique.txt" in files,
            "has_stig":    "stig_audit.txt" in files,
            "pass_count":  pass_count,
            "fail_count":  fail_count,
        })

    return reports


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    reports = get_reports()
    from jinja2 import Environment
    env = Environment()
    tmpl = env.from_string(INDEX_HTML)
    return tmpl.render(reports=reports)


@app.route("/report/<folder>")
def report_detail(folder):
    folder_path = os.path.join(REPORTS_DIR, folder)
    if not os.path.isdir(folder_path):
        abort(404)

    files = sorted(os.listdir(folder_path))
    parts = folder.split("_")
    try:
        device = ".".join(parts[2:]) if len(parts) > 2 else "unknown"
    except Exception:
        device = "unknown"

    # Parse STIG findings
    stig_fails = stig_passes = []
    pass_count = fail_count = total_count = compliance_pct = None
    audit_path = os.path.join(folder_path, "stig_audit.txt")
    if os.path.exists(audit_path):
        findings, pass_count, fail_count = parse_stig_audit(audit_path)
        stig_fails  = [f for f in findings if "FAIL" in f.get("status","").upper()]
        stig_passes = [f for f in findings if "PASS" in f.get("status","").upper()]
        total_count = pass_count + fail_count
        compliance_pct = round((pass_count / total_count * 100) if total_count else 0)

    # Parse critique
    critique_issues = critique_correct = []
    crit_path = os.path.join(folder_path, "critique.txt")
    if os.path.exists(crit_path):
        critique_issues, critique_correct = parse_critique(crit_path)

    from jinja2 import Environment
    env = Environment()
    tmpl = env.from_string(DETAIL_HTML)
    return tmpl.render(
        folder=folder,
        device=device,
        files=files,
        pass_count=pass_count,
        fail_count=fail_count,
        total_count=total_count,
        compliance_pct=compliance_pct,
        stig_fails=stig_fails,
        stig_passes=stig_passes,
        critique_issues=critique_issues,
        critique_correct=critique_correct,
    )


@app.route("/report/<folder>/file/<filename>")
def serve_file(folder, filename):
    folder_path = os.path.join(REPORTS_DIR, folder)
    file_path   = os.path.join(folder_path, filename)
    if not os.path.isfile(file_path):
        abort(404)
    # Serve text files inline, binary files as download
    if filename.endswith((".txt", ".ckl", ".cklb")):
        return send_file(file_path, mimetype="text/plain")
    return send_file(file_path, as_attachment=True)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("")
    print("=" * 50)
    print("  Juniper AI Audit Dashboard")
    print(f"  http://localhost:{PORT}")
    print(f"  http://<your-ip>:{PORT}  (team access)")
    print("=" * 50)
    print("")
    if not os.path.exists(REPORTS_DIR):
        print(f"  ℹ️  No reports directory found at {REPORTS_DIR}")
        print(f"  Run an audit from start.py first.")
        print("")
    app.run(host=HOST, port=PORT, debug=False)
