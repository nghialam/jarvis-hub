# BACKLOG — Consolidated 2026-06-26

## STILL RELEVANT (Action Items)
| ID | Priority | Category | Title | Status | Notes |
|---|---|---|---|---|---|
| S01 | P1 | System | Telegram Network Diagnosis | Open | api.telegram.org unreachable since Jun 5 — user must resolve via VPN/proxy |
| J20 | P1 | Feature | Jarvis Hub 2.0 Implementation | In Progress | Flask port 8100 unreachable since at least Jun 12; db schema aligned, /logs endpoint working |
| N01 | P1 | Feature | AI News Sentinel Construction | Open | Phase 1 of dashboard expansion — stalled |
| S02 | P1 | System | Skill Namespace Normalization | Open | Audit and fix all `openclaw:*` and `finance:*` references to bare strings (supersedes N07) |
| M03 | P1 | System | Telegram Proxy/VPN Setup | Open | Document and test stable routes for api.telegram.org |
| DBR01 | P2 | Error | Daily Brief Data — 8 Silent Failures | Open | bd165385f815: zero-byte outputs Jun 25 (14:20-15:18) — root cause: [SILENT] per prompt directive; fix: remove silent fallback, keep at least one data section populated |
| N02 | P2 | Feature | vnstock4 Migration Completion | Open | Legacy deprecated, imports fail silently |
| CTX01 | P2 | System | Context Overflow Monitoring | Open | 14,065 token overflow Jun 22 — monitor LCM tuning |
| M01 | P2 | System | Health Monitoring Cron | Open | Plan: add simple /health cron checker |
| H01 | P2 | System | Codebase Bloat Cleanup | Open | Prune old .py files from knowledge/scripts/ directories |
| C04 | P2 | Error | Regression QA Silent Fail | Open | Keep running, verify weekly |
| N04 | P3 | Macro | Google-SpaceX Compute Deal Tracker | Open | Low priority, keep if useful |

## HISTORY (Closed/Abandoned — no action)
| ID | Reason |
|---|---|
| C_NULL | Cron `model: null` silent failures — fixed Jun 26, migrated to qwen3.6 |
| C_PQ | Cron prompt quality fixes — normalized step numbering, removed duplicate headers |
| C02, C05, M02 | Entertainment/Trading pipelines — obsolete, disabled |
| N05, N06 | Price targets expired, market pipeline disabled |
| H04, N03 | Memory compact done, WWDC passed |
| ERR1 | Legacy error, no active code path |
| L01, L02 | Correlation Engine, Trend Alerts — dead pipelines |
| F01 | Absorbed into regular backlog intake |
| C_JB | Daily News Briefing — confirmed running Jun 22-23 (was falsely marked PAUSED) |
| C03 | Market Eval Report — no active code path |
| N07 | Duplicated by S02 (Skill Namespace Normalization) |

---
- Summary: 12 active items (5 P1, 6 P2, 1 P3) — last sync 2026-06-26 22:00. No new issues this cycle; all MEMORY.md items already tracked.

--- Daily Autoupdate 2026-06-30 ---
- System self-audit completed
- Health: {"flask_8100": "unreachable", "omlx": "not loaded", "sqlite_db": "ok", "git_changes": "dirty"}
