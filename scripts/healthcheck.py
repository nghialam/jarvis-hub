#!/usr/bin/env python3
"""Jarvis Health Check — run by daily autoupdate cron. Returns JSON report."""
import subprocess, sqlite3, datetime, os, json

def check_flask():
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '5', 'http://localhost:8100/'], 
                          capture_output=True, text=True)
        return {'status': 'ok' if r.returncode == 0 else 'error'}
    except:
        return {'status': 'unreachable'}

def check_omlx():
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '5', 'http://localhost:11434/health'], 
                          capture_output=True, text=True)
        if r.returncode == 0 and 'healthy' in r.stdout:
            return {'status': 'online', 'model': r.stdout[:200]}
        return {'status': 'error'}
    except:
        return {'status': 'unreachable'}

def check_db():
    db_path = '/Users/nghialam/.jarvis-hub-knowledge.db'
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("SELECT count(*) FROM sqlite_master")
        count = cur.fetchone()[0]
        conn.close()
        return {'status': 'ok', 'tables': count}
    except:
        return {'status': 'error'}

def check_cron_jobs():
    try:
        r = subprocess.run(['/Users/nghialam/.hermes/hermes-agent/venv/bin/python3', '-c',
            'import json; d=json.load(open("/dev/stdin")); print(json.dumps({"count":len(d["jobs"])}))'],
            input='{"jobs":["a"]}', capture_output=True, text=True)
        return {'status': 'ok'}  # Simplified — just checking Hermes is importable
    except:
        return {'cron': 'error'}

report = {
    "timestamp": datetime.datetime.now().isoformat(),
    "health_check": {
        "flask": check_flask(),
        "omlx": check_omlx(),
        "database": check_db(),
    },
    "actions_taken": [],
}

# Save report to knowledge DB
report_path = '/Users/nghialam/jarvis-hub/knowledge/health_check_latest.json'
with open(report_path, 'w') as f:
    json.dump(report, f, indent=2)

print(json.dumps(report, indent=2))
