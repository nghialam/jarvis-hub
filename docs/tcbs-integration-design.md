# TCBS MCP Integration — Hybrid Architecture (JH3.0)
# Added: 2026-10-05 | Updated: 2026-10-06

## Purpose
Integrate TCBS MCP public API as **secondary data source** for data vnstock cannot provide:
1. Foreign volume/flow analysis (grouped by symbol + sector)
2. Sector-level market analysis
3. Ratings, evaluation, fundamentals
4. Technical indicators (enrichment only, not replacement)

## Data Source Architecture — Hybrid Pattern

### Primary: vnstock v4 (OHLCV + Market Data)
- **Role**: OHLCV, market overview, basic indicators
- **Auth**: None required
- **Why**: Stable, free, no rate limit, proven pipeline
- **Scope**: All tickers, daily/weekly/monthly OHLCV, VN-Index/HNX-Index/UPCoM

### Secondary: TCBS MCP (Foreign Flow + Sector + Ratings)
- **Role**: Foreign flow, sector analysis, ratings, evaluation, fundamentals
- **Auth**: `TCBS_API_KEY` (Bearer token, no refresh needed)
- **Why**: vnstock lacks foreign flow data entirely; TCBS has unique datasets
- **Scope**: vol-foreign, portfolio/sector, ratings, evaluation, fundamentals

### Do NOT duplicate OHLCV
- TCBS OHLCV = duplicate overhead, wastes context tokens
- Use vnstock for all OHLCV
- Use TCBS ONLY for unique endpoints

## Authentication

### TCBS MCP
- **Single API key** (Bearer token) — no OAuth flow, no token refresh
- Key obtained from: https://help.tcbs.com.vn/tcbs-mcp-server/
- API: `https://apiext.tcbs.com.vn` (fallback: `apiextaws.tcbs.com.vn`)
- Stateless requests — no session management needed

### vnstock
- No authentication required
- Free public API

### SSI FastConnect (tertiary)
- Requires API Key + Secret pair
- JWT + refresh token (8h validity)
- RSA signing for order placement
- Not yet integrated — pending user credentials

## File Structure

```
~/.hermes/scripts/
  tcbs/
    constants.py    — API endpoints, ticker lists, sector codes
    fetch.py        — HTTP client wrapper + data collection
  vnmarket.py       — vnstock wrapper (OHLCV, market data)
  tcbs-data-collector.py  — NEW: fetches ONLY unique TCBS data

jarvis-hub/
  core/
    market.py       — vnstock data provider (OHLCV primary)
    tcbs.py         — TCBS data provider (foreign flow, sector, ratings)
```

## Cron Integration

- TCBS data injected into cron job 4bbf22ee2ad7 (VN Market + Gold Daily Brief)
- Pattern: Python script outputs JSON → cron prompt consumes JSON → LLM produces briefing
- No separate cron job for TCBS — merged into existing pipeline
- Data fields: `tcbs_foreign_flow`, `tcbs_sector_analysis`, `tcbs_ratings`

## TCBS Unique Endpoints (vs vnstock)

| TCBS Endpoint | vnstock Equivalent | Decision |
|---------------|-------------------|----------|
| `vol-foreign` | ❌ None | ✅ TCBS only |
| `portfolio` (sector) | ❌ None | ✅ TCBS only |
| `rating/{ticker}` | ❌ None | ✅ TCBS only |
| `evaluation/{ticker}` | ❌ None | ✅ TCBS only |
| `finance/income-statement` | ⚠️ Partial | ✅ TCBS only |
| `data-charts/indicator` | ✅ vnai | ⚠️ TCBS enrichment only |
| `data-charts/ohlc` | ✅ vnstock | ❌ Skip (vnstock primary) |

## Error Handling

- HTTP errors → warn to stderr, return empty dict
- Rate limiting → 0.5s delay between calls
- Invalid symbols → skip silently, log to stderr
- Network timeout → 30s per request
- TCBS API key missing → script exits gracefully (exit code 1)

## Testing

```bash
# Test TCBS data collector (requires TCBS_API_KEY)
cd ~/.hermes/scripts
export TCBS_API_KEY=your_key_here
python3 tcbs-data-collector.py

# Test vnstock data (no auth needed)
python3 vnmarket.py
```

## Migration from tcbs-ohlc-daily.py

- `tcbs-ohlc-daily.py` (394 lines) → deprecated, fetches OHLCV (duplicate)
- Replaced by `tcbs-data-collector.py` → fetches ONLY unique TCBS data
- vnstock continues handling all OHLCV independently

## Future Extensions

- TCBS foreign flow alerting (threshold-based, e.g., >100B net buy)
- SSI FastConnect integration (pending credentials)
- TCBS sector analysis dashboard (web UI)
- Multi-source aggregation layer (vnstock + TCBS + SSI)
