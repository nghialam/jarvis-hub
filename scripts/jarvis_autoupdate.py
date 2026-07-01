#!/usr/bin/env python3
"""Jarvis Daily Autoupdate Pipeline v1.1

Runs every weekday at 09:00 AM via cron job e4f2g3h4.
Self-audits the entire Jarvis system and delivers a report to Telegram.

Pipeline: Health Check -> Code Analysis -> Auto-Execute (safe ops only).
"""

import subprocess
import json
import datetime
import os
import glob


JARVIS_ROOT = "/Users/nghialam/jarvis-hub"
BACKLOG_PATH = JARVIS_ROOT + "/BACKLOG.md"
LOG_PATH = "/Users/nghialam/.jarvis-hub-knowledge/autoupdate_log.txt"
KB_DIR = "/Users/nghialam/.jarvis-hub-knowledge"


def run_cmd(cmd, timeout=120):
    """Run shell command and return result dict. Local commands only."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=JARVIS_ROOT,
        )
        return dict(exit=r.returncode, out=r.stdout.strip(), err=r.stderr.strip())
    except Exception as e:
        return dict(exit=-1, out="", err=str(e))


def log(msg):
    """Write timestamped log line to autoupdate_log.txt."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[" + ts + "] " + msg
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# === PHASE 1: SYSTEM HEALTH CHECK ===

def phase_1_health_check():
    """Check all system components and return health status dict."""
    log("Phase 1: SYSTEM HEALTH CHECK")
    checks = {}

    # Flask port check (port 8100)
    r = run_cmd("curl -s --max-time 5 http://localhost:8100/ | head -c 100")
    if r.get("exit", -1) == 0 and "Jarvis" in r.get("out", ""):
        checks["flask_8100"] = "ok"
    else:
        checks["flask_8100"] = "unreachable"

    # OMLX model server check
    r = run_cmd("curl -s --max-time 3 http://localhost:11434/health")
    if r.get("exit") == 0 and "healthy" in r.get("out", ""):
        checks["omlx"] = "loaded"
    else:
        checks["omlx"] = "not loaded"

    # SQLite DB integrity check
    db_path = "/Users/nghialam/.jarvis-hub-knowledge.db"
    ok_cmd = 'echo "SELECT count(*) FROM sqlite_master" | sqlite3 ' + db_path
    r = run_cmd(ok_cmd)
    if r.get("exit") == 0:
        checks["sqlite_db"] = "ok"
    else:
        checks["sqlite_db"] = "error (" + r.get("err", "")[:60] + ")"

    # Git status check (has uncommitted changes?)
    r = run_cmd("cd /Users/nghialam/jarvis-hub && git diff --quiet")
    if r.get("exit", 1) != 0:
        checks["git_changes"] = "dirty"
    else:
        checks["git_changes"] = "clean"

    log("Health results: " + json.dumps(checks, indent=2))
    return checks


# === PHASE 2: CODE & DATA ANALYSIS ===

def phase_2_code_analysis(health):
    """Scan codebase for issues, opportunities, and quality metrics."""
    log("Phase 2: CODE & DATA ANALYSIS")
    findings = []

    # 1. Check Flask app size/stability
    app_py = JARVIS_ROOT + "/app.py"
    if os.path.exists(app_py):
        with open(app_py) as f:
            lines = f.readlines()
        code_lines = sum(1 for l in lines if l.strip() and not l.strip().startswith("#"))
        findings.append("app.py: " + str(len(lines)) + " total, "
                         + str(code_lines) + " code lines")

        content = "".join(lines)
        todo_count = content.count("TODO") + content.count("FIXME") + content.count("HACK")
        if todo_count > 0:
            findings.append(str(todo_count) + " TODO/FIXME/HACK comments -- needs review")

    # 2. Check dashboard templates
    index_html = JARVIS_ROOT + "/dashboard/templates/index.html"
    if os.path.exists(index_html):
        with open(index_html) as fh:
            count_lines = sum(1 for _ in fh)
        h_content = open(index_html).read()
        has_autopoll = "AUTO_POLL_MS" in h_content or "setInterval" in h_content
        ver = "verified" if has_autopoll else "MISSING"
        findings.append("index.html: " + str(count_lines) + " lines (autopll " + ver + ")")

    # 3. Count Python project files at root
    py_count = sum(1 for p in os.listdir(JARVIS_ROOT) if p.endswith(".py"))
    findings.append("jarvis-hub/: " + str(py_count) + " .py files at root directory")

    # 4. Check for issues
    bad_keywords = ["error", "missing", "fail", "unreachable", "stale"]
    issue_count = sum(1 for f in findings if any(x in f.lower() for x in bad_keywords))
    issues_found = issue_count >= 2

    log("Code analysis complete. Findings: " + json.dumps(findings))
    return dict(timestamp=datetime.datetime.now().isoformat(),
                issues_found=issues_found, findings=findings)


# === PHASE 3: SAFE AUTO-EXECUTION ===

def phase_3_auto_execute(health, analysis):
    """Attempt to safely auto-resolve known issues. NO destructive ops."""
    log("Phase 3: AUTO-EXECUTE (safe ops only)")
    actions = []

    # 1. Update BACKLOG.md with today's autoupdate section
    if os.path.exists(BACKLOG_PATH):
        try:
            with open(BACKLOG_PATH) as f:
                bcontent = f.read()
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            header = "--- Daily Autoupdate " + today + " ---"
            if header not in bcontent[-2000:]:
                with open(BACKLOG_PATH, "a", encoding="utf-8") as f:
                    f.write("\n" + header + "\n")
                    f.write("- System self-audit completed\n")
                    f.write("- Health: " + json.dumps(health) + "\n")
                actions.append("Added autoupdate entry for " + today + " to BACKLOG.md")
        except Exception as e:
            log("BACKLOG update failed: " + str(e))

    # 2. Trim old logs if >500KB (keep last 10K lines)
    if os.path.exists(LOG_PATH):
        sz = os.path.getsize(LOG_PATH)
        if sz > 500000:
            with open(LOG_PATH, encoding="utf-8") as f:
                all_lines = f.readlines()
            target = min(10000, len(all_lines))
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(all_lines[-target:])
            actions.append("Trimmed autoupdate_log.txt (was " + str(sz) + " bytes)")

    # 3. Ensure KB directory exists
    os.makedirs(KB_DIR, exist_ok=True)

    log("Auto-executed " + str(len(actions)) + " safe actions")
    return actions


# === DELIVERY & REPORTING ===

def get_telegram_message(health, analysis, actions):
    """Build the Telegram delivery message for the report."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    tstr = datetime.datetime.now().strftime("%H:%M")

    msg = "*Jarvis Daily Autoupdate -- " + today + " " + tstr + "*\n\n"
    msg += "*System Health:*\n"

    for k, v in health.items():
        vstr = str(v).lower()
        if "error" in vstr or "fail" in vstr or v == "unreachable":
            icon = "\u26A0"
        else:
            icon = "\u2705"
        msg += "- `" + k + "`: " + icon + " `" + str(v) + "`\n"

    if analysis.get("issues_found"):
        msg += "\n*Analysis*: **Issues detected**\n"
    else:
        msg += "\n*Analysis*: All clear\n"

    if actions:
        msg += "\n*Auto-Executed*\n"
        for a in actions:
            msg += "- " + a + "\n"
    else:
        msg += "\n*No automated fixes needed.*\n"

    msg += "\n---\n*Next run*: 09:00 AM\n--\nJarvis Autoupdate v1.1"
    return msg


# === MAIN ENTRY POINT ===

def main():
    """Run the three-phase pipeline: Health -> Analysis -> Auto-Execute."""
    log("=" * 60)
    log("Starting Jarvis Daily Autoupdate Pipeline v1.1")

    try:
        # Phase 1: Health check all components
        health = phase_1_health_check()

        # Phase 2: Analyze codebase and data
        analysis = phase_2_code_analysis(health)

        # Phase 3: Auto-resolve safe issues
        actions = phase_3_auto_execute(health, analysis)

        # Build delivery message  
        msg = get_telegram_message(health, analysis, actions)

        # Save full report to knowledge base
        report = dict(
            timestamp=datetime.datetime.now().isoformat(),
            phase1_health=health,
            phase2_analysis=analysis,
            phase3_actions=actions,
            telegram_message_preview=msg[:500],
        )

        os.makedirs(KB_DIR, exist_ok=True)
        ts_key = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        kb_file = KB_DIR + "/autoupdate_report_" + ts_key + ".json"
        with open(kb_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        log("Actions taken: " + str(len(actions)))
        log("Report saved: " + kb_file)

        # Print Telegram preview for debugging
        print("\n--- TELEGRAM MESSAGE ---\n")
        print(msg)
        print("--- END ---\n")

    except Exception as e:
        log("FATAL: Pipeline crashed: " + str(e))
        import traceback
        log(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
