# BACKLOG — Jarvis Hub 2.0 — Consolidated & Trimmed [2026-08-01]

||| ID | Prio | Category | Title | Status | Notes |
||---|---|---|---|---|---|
|| [ARCHIVED S01] | - | System | Telegram Network Diagnosis | Archived | User infrastructure issue, not a code task |
|| J20 | P1 | Feature | Jarvis Hub 2.0 Implementation | In Progress | Flask dashboard on port 8100; ~60 API routes, 38 DB tables — **Phases A-B done Jul 25, C-E pending** |
|| N01 | P1 | Feature | AI News Sentinel Construction | Open | Phase 1 of dashboard expansion — stalled |
|| S02 | P1 | System | Skill Namespace Normalization | Open | Audit `openclaw:*`/`finance:*` refs → bare strings |
|| [ARCHIVED M03] | - | System | Telegram Proxy/VPN Setup | Archived | Duplicate of S01, not a code task |
|| [ARCHIVED DBR01] | - | Error | Daily Brief Data — 8 Silent Failures | Archived | Fixed by daily-brief-data.py v17 and cron prompt fix |
|| C04 | P2 | Error | Regression QA Silent Fail | Open | Keep running, verify weekly |
|| [ARCHIVED N02] | - | Feature | vnstock4 Migration Completion | Archived | Upgraded vnstock→4.0.5, vnai→2.5.3; integration test passed VIC on 2026-07-25 |
|| CTX01 | P2 | System | Context Overflow Monitoring | Open | Session overflow Jun 22 — monitor LCM tuning |
|| M01 | P2 | System | Health Monitoring Cron | Open | Plan: add simple /health cron checker |
|| H01 | P2 | System | Codebase Bloat Cleanup | Open | Prune old .py from knowledge/scripts/ dirs |
|| [ARCHIVED IMP01] | - | System | jarvis-auto-improve stub files | Archived | Created ERRORS.md + SESSION_SUMMARY.md on 2026-07-25 |
|| CRON01 | P2 | Error | Cron Timeout Pattern (memory-daily + backlog-sync) | Open | qwen3.6:35b too slow for 600s deadline — consider migrating to 27b-mxfp8 |
|| AI01 | P3 | Experiment | Multimodal input pipeline (vision) | Open | Feed charts + text into qwen3.6 via vision variant |

--- Daily Autoupdate 2026-07-31 ---
- System self-audit completed; Health: {flask_8100: unreachable, ollama: not loaded, sqlite_db: ok, git_changes: dirty}

--- Daily Autoupdate 2026-08-01 ---
- Backlog audit complete: **9 active items maintained, 0 new candidates added** (memory scan returned 0 actionable facts; 10 error log entries reviewed — no new backlog items).
| Third consecutive day of daily collection scans returning zero new facts. Persistently empty pipeline warrants investigation of source logs and fact extraction pipeline health on next opportunity.

--- Daily Autoupdate 2026-08-02 ---
- Backlog audit complete: **9 active items maintained, 0 new candidates added** (memory scan returned 0 actionable facts; 1 error from ERRORS.md — gotham-brief chunk 2 Telegram 400, pre-existing and tracked as open).
- Fourth consecutive day of zero new facts from memory collection — fact extraction pipeline health remains degraded. Recommend investigating source log availability or cron timing on next opportunity.

|| ARCHIVED / HISTORY |
|- C_NULL, C_PQ, C02/05, M02, N05/06, H04, N03, ERR1, L01/02, F01, C_JB, C03, N07: Stale/completed/obsolete |

--- Daily Autoupdate 2026-08-03 ---
- System self-audit completed
- Health: {"flask_8100": "unreachable", "ollama": "not loaded", "sqlite_db": "ok", "git_changes": "dirty"}
