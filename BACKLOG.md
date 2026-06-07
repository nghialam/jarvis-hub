# Jarvis Hub — Backlog & Project Health Audit

**Last Audited:** 2026-06-05 07:00 (Vietnam Time)
**Total Issues Found:** 17
**Overall Health:** 🔴 NEEDS ATTENTION

---

## CRITICAL (Fix Now)

### C01 [FIXED ✅] Trend Analysis Truncation
- **Issue:** `jarvis_intelligence.py` line 554 had `[:4500]` hard-slice on full LLM output before Telegram send — silently dropped content after char 4500 with no warning
- **Fix Applied:** Removed `[:4500]` slice. `send_telegram()` already handles splitting at 3896/4096 chars correctly
- **Also Fixed:** Bedtime mode hard-cuts on lines 539 (`[:3000]`) and 544 (`[:3500]`) — both removed
- **Status:** ✅ Resolved

### C02 [IN PROGRESS] Entertainment Wrap Crash
- **Job:** `jarvis-entertainment-wrap` (cron, 07:00 weekdays)
- **Error:** `TypeError: not all arguments converted during string formatting` at line 352/242
- **Root Cause:** `run-entertainment-wrap.sh` shim MISSING from `/Users/nghialam/.hermes/scripts/` (only 9 of 10 shims exist)
- **Fix Needed:** Create shim + fix Python string format bug on line 352
- **Status:** 🔴 Open

### C03 [IN PROGRESS] Market Eval Report — Stale Error Status
- **Job:** `jarvis-market-eval-report` (cron, 08:30 weekdays)
- **Error:** Shows status "error" but last run at 10:47 shows `"Delivered (ok=True, msg_id=193)"`
- **Root Cause:** Likely an earlier failed run set the error status; subsequent runs worked OK but status wasn't reset
- **Fix NEEDED:** Investigate and force-reset status, or add error-handling to cron runner
- **Status:** 🔴 Open

### C04 [IN PROGRESS] Regression QA — Silent Failure in Cron
- **Job:** `jarvis-regression-qa` (cron, 03:02 AM daily)
- **Error:** Shows status "error" but manual test runs successfully (6/6 tests pass)
- **Root Cause:** Script works interactively (`python3 jarvis_regression_test.py --test`) but cron mode may lack environment variables or workdir context
- **Fix NEEDED:** Add `set -euo pipefail` to log captures, verify cron workdir `/Users/nghialam/jarvis-hub/scripts` is correct at 02:30 AM execution time
- **Status:** 🔴 Open

### C05 [IN PROGRESS] Trading Scans — "Chat Not Found" Errors
- **Jobs:** `jarvis-scan-morning`, `afternoon`, `evening` (all show status errors)
- **Error:** `Telegram HTTP 400: Bad Request: chat not found`
- **Root Cause:** `scan_reporter.py` line `"chat_id": TELEGRAM_CHAT_ID` — the `_DEFAULT_CHAT_IDS` dict uses `-1001670013239` but Gotham channel ID is `1670013239` (negative prefix wrong)
- **Fix NEEDED:** Check `trading_bot/scan_reporter.py` `_DEFAULT_CHAT_IDS` — remove leading `-` or verify if negative is intentional for Telegram API
- **Status:** 🔴 Open

---

## HIGH PRIORITY

### H01 Codebase Bloat — Cleanup Needed
- **Issue:** 4,837 Python files in jarvis-hub/, many are dead/old versions
- **Evidence:** `app_append.py`, `new_app_full.py`, `verify_pipeline.py` (multiple versions), orphan test scripts scattered in root and subdirs
- **Risk:** Hard to find active code, increases git clone time (~283MB total)
- **Fix Needed:** Audit live vs. dead files. Delete duplicates/old versions. Target: <500 Python files + clean git history (consider `git filter-repo` or fresh init)
- **Status:** 📋 Backlog

### H02 Flask Dashboard — Missing Health Endpoint
- **Issue:** Accessing `/health` on port 8100 returns 404 "Not Found"
- **Impact:** No way for monitoring/orchestration to check if flask app is alive
- **Fix Needed:** Add `GET /health` route returning JSON with uptime, cache status, ollama ping
- **Status:** 📋 Backlog

### H03 Single Git Commit Since May
- **Issue:** Only 2 commits total since project inception (`May 1st`), single `main` branch
- **Risk:** No version control, no rollback capability, no PR review process
- **Fix Needed:** 
  - Add `.gitignore` (venv/, __pycache__/, backups/, data/)
  - Tag current working state as `v1.0.0`
  - Initialize development workflow (branches for features)
- **Status:** 📋 Backlog

### H04 Memory Compact Job Never Ran
- **Job:** `jarvis-memory-compact` (cron, weekly Sunday 09:00)
- **Issue:** Created but `last_run_at: null` — never executed
- **Fix Needed:** Verify the cron job actually exists in Hermes system. Check if underlying script (`memory_compact.py`) was ever created
- **Status:** 📋 Backlog

### H05 Ollama Memory Footprint — Single Model Overload
- **Issue:** qwen3.6:35b-mlx consuming ~47GB RAM on Mac Mini M4 Pro 64GB
- **Impact:** Slows system, causes ~90s latency per LLM call (sequential chains take ~4.5 min for full briefing)
- **Observations:** Gemma4 is used for lighter tasks (cron jobs). Consider quantizing qwen3.6 or using gemma4 for simpler chains (AI/Tech Priority doesn't need 35B params)
- **Fix Needed:** Test smaller model for AI/tech chain, migrate heavy models to off-peak only
- **Status:** 📋 Backlog

---

## MEDIUM PRIORITY

### M01 Add Health Monitoring Cron
- Create a `jarvis-system-health` cron job (runs every 6 hours) that checks:
  - Flask dashboard response (`curl -sf localhost:8100/health`)
  - Ollama alive + model loaded (`curl -sf localhost:11434/api/tags`)
  - Disk space available (`df /`)
- Sends alert to Telegram if any check fails

### M02 Trading Bot — Rate Limit Handling
- **Issue:** `intraday-scan.log` shows `🚫 Đang bị giới hạn API? Tăng tốc độ gọi API lên 10X với Vnstock Insider`
- **Fix:** Add exponential backoff + retry logic when vnstock3 returns rate limit errors. Don't just print "poll no changes" — log the actual error

### M03 Daily Knowledge Base Organization
- `knowledge/2026-05-27.md` is only file in 1KB directory — flat structure
- Consider organizing into subdirs: `daily/`, `signals/`, `learnings/`, `metrics/`
- Add a `README.md` to knowledge with indexing/search guidance

### M04 Automated Backlog Maintenance Cron
- Create a cron job (monthly, 1st of month) that:
  - Reviews backlog items older than 30 days
  - Flags stale "TODO" items for deletion or updating
  - Generates maintenance report of completed vs. pending items

---

## LOW PRIORITY / FUTURE ENHANCEMENTS

### L01 Correlation Engine
- Combine market data (VN-Index, gold, DXY, oil, crypto) from Flask cache into daily correlation analysis
- LLM chain that outputs: "When X drops, Y follows with Z% probability"

### L02 Trend Alerts System
- Trigger-based briefing: when specific index drops >2%, fire an urgent "flash alert" micro-briefing
- Uses lightweight model (gemma4) + keyword scoring on RSS headlines

### L03 Watchlist Rebalancer
- Combine scan engine signals + NLP sentiment from daily briefings
- Suggests: add/remove symbols based on trend momentum + market conditions

### L04 Documentation
- Add `ARCHITECTURE.md` to root explaining system (Flask dashboard, cron pipeline, trading bot)
- Update existing `/Users/nghialam/jarvis-hub/.plans/` files with current state
- Generate mermaid diagram showing component relationships

---

## COMPLETED ITEMS

|| Item | Date | Notes |
|------|------|-------|
| RSS pipeline (14 sources, 3 LLM chains) | 2026-05-31 | Working after initial fixes |
| Telegram HTML delivery with split logic | 2026-06-01 | Verified working for 3800+ char messages |
| Cron job automation (17 scheduled jobs) | 2026-06-04 | 4/17 have issues, rest OK |
| Trading bot scans (morning/afternoon/evening/intraday) | 2026-06-04 | Working but chat ID bug affects daily output |
| Self-memory for truncation pattern | 2026-06-05 | Saved as "TRUNCATION PATTERN AVOIDANCE" in memory store |
| Daily News & Strategy Briefing v2 (cron) | 2026-06-07 | Replace old 4x/day briefings; clickable links; pausing old jobs |

---

## NEW — ACTION ITEMS FROM DAILY BRIEFING (v2)
**Added: 2026-06-07** | *Triggered by "Daily News & Strategy" cron execution*

*All items below are for FUTURE execution: "khi nào có thời gian và cơ hội thật tốt thì cùng làm" — not urgent, but worth tracking.*

### AI & Intelligence Monitoring (Priority H)

| ID   | Item | Why It Matters | Status |
|------|------|----------------|--------|
| **N01** | **AI News Sentinel**: Build automated RSS → LLM sentiment analysis → push signal alerts to Telegram when market-moving event detected | Current manual scan is slow; we need 24/7 agent that fires actionable signals in real-time. Use existing Ollama (qwen3.6:35b-mlx) + RSS feeds + cron trigger. Low effort, high ROI for trader alerting. | 📋 Future |
| **N02** | **Manus Startup Tracker**: Reid Hoffman joined Manus board; 215K users in days. Build a lightweight agent that monitors Manus releases, user growth, funding news → output daily score. | Could be the "OpenAI killer" in consumer AI agent space. Tracking it helps anticipate market shifts in AI/ML sector. | 📋 Future |
| **N03** | **WWDC 2026 Watch Mode**: Apple Intelligence revamp upcoming. Set up monitoring for WWDC announcements, then assess impact on local LLM pipeline (Gemma, Ollama). | Apple Intelligence updates could directly improve our Jarvis agent architecture. Stay ready to integrate early. | 📋 Future |

### Market Opportunity Tracking (Priority M)

| ID   | Item | Why It Matters | Status |
|------|------|----------------|--------|
| **N04** | **Google-SpaceX Compute Deal Tracker**: $920M/mo compute deal — monitor for implications on AI infrastructure stock, cloud pricing, energy sector. Signal: if Google commits to massive compute, other majors will follow → GPU/Energy stocks bullish. | Macro signal for AI investment thesis. | 📋 Future |
| **N05** | **Bitcoin $62K Trend Analysis**: BTC up +3% this week. Build a simple trend tracker (7-day moving average + volume) to identify entry/exit zones. | Current market is volatile (VIX +40%). Need data-driven conviction, not gut feel. | 📋 Future |
| **N06** | **VIX Spike Early Warning**: VIX jumped +40% last week. Build a cron check on VIX level; if >25 flag for attention. | High VIX = fear = potential selling opportunity or warning signal. | 📋 Future |

---

## NOTES & DECISIONS

1. **Codebase cleanup approach:** Don't delete aggressively — audit first. Mark dead files with `.dead` extension, then purge after 30 days of no reference
2. **Git hygiene:** First step is just tag `v1.0.0` and add `.gitignore`. Development branches come after backlog items are addressed
3. **Prioritization philosophy:** Fix broken things first (C01-C05), then prevent rot (H01-H05), then enhance value (M01-M04+L+N)
4. **Memory vs Backlog:** This file is the canonical backlog. Critical findings also saved to `memory` tool for cross-session recall
5. **Cron Strategy (2026-06-07):** Paused old 13 jobs. Replaced with single Daily News & Strategy cron at 06:00. Old briefings can be resumed selectively later if needed.

---

*Generated: 2026-06-05 07:00 AM — Rex's Jarvis Hub Audit v1.0*
