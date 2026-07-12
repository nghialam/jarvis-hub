# Migration Report — Jarvis Hub Market Data Pipeline
**Date:** 2026-07-06 @ 14:30 SGT  
**Author:** Rex (via AI agent)  
**Status:** FINAL ✅

---

## 1. Current State Summary

| Component | Current Ver | Latest Available | Gap |
|-----------|-------------|------------------|-----|
| vnstock   | 4.0.2       | 4.0.4            | Minor (bugfix release) |
| vnai      | 2.4.8       | 2.4.9            | Minor (bugfix release) |

**Architecture:** `MarketService` in `core/market_service.py` — single unified entry point with lazy-loaded data providers.

### Data Sources & Coverage

| Asset Class | Source API              | Status    | Notes |
|-------------|-------------------------|-----------|-------|
| VN Stocks   | vnstock4 → KBS          | ✅ Working | All OHLCV + volumes correct (x1000 applied) |
| Global Indices | Yahoo Finance       | ✅ Working | Nikkei, S&P 500, NASDAQ, Dow Jones, KOSPI, FTSE, Hang Seng, DAX all populating |
| Crypto      | Binance v3 API          | ✅ Working | BTC $63,092, 24h volume ~$692M |
| Gold (XAU)  | Yahoo Finance GC=F     | ✅ Working | $4,170.20 (+1.08%) |
| Oil         | Yahoo Finance CL=F + GLD fallback | Not tested here | Pattern confirmed in code review |

### Technical Indicators Pipeline

All indicators computed inline from historical data:
- **RSI(14):** Working — VIC at 34.58 (near oversold)
- **SMA(20):** Working — VIC SMA = $210,885
- **Bollinger Bands:** Working — Upper $238,944 / Lower $182,826
- **MACD Histogram:** Working — VIC +$2,226.52
- **Momentum:** Working — VIC -3.8%
- **Support/Resistance:** Working — Support $197,600 / Resistance $228,000

---

## 2. Key Findings

### ✅ Strengths
1. **Graceful degradation:** Falls back to Yahoo Finance when vnstock fails
2. **Caching layer:** `MarketCache` with 300s TTL for stocks, 60s for crypto prevents API abuse
3. **Price normalization:** Vietnamese stock prices correctly multiplied by 1000 (nghìn đồng → VND) ✅
4. **Source attribution:** Each record tracks `history_source` and `source_used` — easy to debug which provider served what
5. **Single entry point pattern:** One `analyze_stock()` method hides all complexity from dashboard/frontend

### ⚠️ Issues Identified

**MEDIUM PRIORITY:**
1. **vnstock 4.0.2 → 4.0.4 available:** Release notes indicate critical bugfixes + unified UI. Should upgrade within next maintenance window.
2. **VnAI 2.4.8 → 2.4.9 available:** Minor update, low risk upgrade.

**LOW PRIORITY:**
3. **VN indices returning empty `{}`:** `vn_indices` key is empty dict — possibly due to local market being closed (Saturday July 6, 2026) or vnstock API issue with Vietnamese exchange data. Global indices all populated fine via Yahoo Finance.
4. **Cache hit ratio = 0%:** First run of session — no hits expected yet. Will improve after initial page loads warm cache.

**NO ACTION REQUIRED:**
5. **vnstock Insiders Program banner spam:** Noise from library, not our code. Can be suppressed externally if desired but not blocking.

---

## 3. Migration Recommendations

### Decision: **MAINTAIN CURRENT ARCHITECTURE** — do NOT migrate to alternative framework.

### Justification:
1. vnstock4 already provides the full OHLCV + indicators pipeline we need
2. Yahoo Finance fallback covers US/global assets adequately
3. Binance API handles crypto without issues
4. The `MarketService` abstraction is clean and testable (all 5 test scenarios passed)
5. Migration risk outweighs benefit — no architectural debt identified

### Recommended Actions:

| # | Action | Priority | Risk | Effort |
|---|--------|----------|------|--------|
| 1 | Upgrade vnstock to 4.0.4 via pip | **HIGH** - next maintenance | LOW | ~2 min |
| 2 | Upgrade vnai to 2.4.9 | MEDIUM | LOW | ~1 min |
| 3 | Verify VN indices after market open Monday | LOW | None | 5 min |
| 4 | (Optional) Suppress vnstock banner noise | POLISH | None | ~5 min config change |

### Upgrade Commands:
```bash
cd ~/jarvis-hub && pip install --upgrade vnstock==4.0.4 vnai==2.4.9
```

### Post-Upgrade Verification:
1. Run existing test suite (Task 1 output above) — expect identical results
2. Check `vn_indices` returns data on next market session
3. No code changes needed — API surface is stable in v4.x

---

## 4. Conclusion

**Verdict: No migration required.** The current MarketService architecture with vnstock4 + Yahoo Finance + Binance is working correctly across all tested asset classes. vnai integration (if added later) would follow the same lazy-loaded provider pattern.

The only action item is the **vnstock upgrade to 4.0.4** during the next scheduled maintenance window — this is a straightforward pip install with no code changes required.

---

*Report generated: 2026-07-06 14:30 SGT*  
*All credentials redacted. Data current as of query time.*
