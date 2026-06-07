#!/usr/bin/env python3
"""
Batch 5: Basic Investing & Market Mechanics (Investopedia-style definitions)
Purpose: Enrich KB with fundamental investing concepts, market structure, and trading terminology.

Run:    python scripts/enrich_kb_batch5.py
DB:     knowledge/jarvis.db (same as seed KB)
"""

import sqlite3
import os

# --- DB setup ---
DB_DIR = os.path.join(os.path.dirname(__file__), '..', 'knowledge')
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'jarvis.db')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Verify table exists
cursor.execute("""
    SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge'
""")
if not cursor.fetchone():
    print("ERROR: knowledge table not found. Run seed_kb.py first.")
    conn.close()
    exit(1)

# --- Terms to add (Investopedia basic investing concepts) ---
TERMS = [
    # === Portfolio & Asset Management ===
    {
        "term": "portfolio diversification",
        "category": "Investment Strategy",
        "content": """**Portfolio Diversification** là chiến lược phân tán đầu tư vào nhiều loại tài sản khác nhau để giảm thiểu rủi ro tổn thất tổng thể.

**Nguyên tắc cốt lõi:**
- "**Đừng đặt tất cả trứng vào một giỏ**" — spread risk across uncorrelated assets
- Diversify across: stocks, bonds, commodities, real estate, cash
- Within stocks: diversify by sector (tech, healthcare, energy...), market cap (large/micro/small), geography (VN, US, global)
- Correlation < 0.5 giữa các asset classes trong portfolio là mục tiêu tối ưu

**Lợi ích:**
- Giảmdrawdown khi một sector/sector suy thoái
- Tăng Sharpe Ratio của portfolio tổng thể
- Không cần predict market direction chính xác

**Thiếu sót:**
- Over-diversification → "diworsification" (quá nhiều holdings, tracking khó, fee cao)
- Ideal: 15-30 stocks cho portfolio cá nhân VN

See also: *asset allocation*, *risk tolerance*"""
    },
    {
        "term": "asset allocation",
        "category": "Investment Strategy",
        "content": """**Asset Allocation** là việc phân bổ vốn đầu tư giữa các class tài sản khác nhau (stocks, bonds, cash, commodities...) dựa trên mục tiêu và rủi ro chấp nhận được.

**Mô hình phổ biến:**
- **60/40 Portfolio**: 60% stocks + 40% bonds — balanced growth/stability (1970s-2000s gold standard)
- **Age-based Rule**: \%bonds = age (30 tuổi → 30% bonds, 70% stocks)
- **Conservative**: 30/40/30 (stocks/bonds/cash) cho người sắp nghỉ
- **Aggressive**: 80/15/5 (stocks/bonds/cash) cho young investors

**Nguyên tắc:**
- Strategic Asset Allocation: set target % và rebalance định kỳ (quarterly/yearly)
- Tactical Asset Allocation: adjust ngắn hạn theo market conditions
- Rebalancing frequency: quarterly hoặc khi deviation > 5% từ target

**Tại VN:** Most retail portfolios heavily concentrated stocks (~80%+), bonds (~10%), cash (~10%). Consider adding more bonds for stability.

See also: *portfolio diversification*, *risk tolerance*"""
    },
    {
        "term": "risk tolerance",
        "category": "Investment Strategy",
        "content": """**Risk Tolerance** (Khả năng chịu rủi ro) là mức độ biến động/mất mát vốn mà một nhà đầu tư có thể chấp nhận về mặt tài chính và tâm lý.

**3 yếu tố quyết định:**
1. **Time Horizon**: Thời gian đầu tư越长 → tolerance càng cao (young = 20-30+ năm, can take more risk)
2. **Financial Situation**: Income stability, emergency fund size, debt level
3. **Psychological Capacity**: Can you sleep when portfolio drops 30%?

**Risk Profile Levels:**
- **Conservative**: 30/40/30 (stocks/bonds/cash) — Max drawdown < -15%
- **Moderate**: 60/30/10 — Max drawdown -20% to -35%
- **Aggressive**: 80/15/5 — Max drawdown -35% to -50%
- **Speculative**: 90/5/5 — Max drawdown -50%+ accepted

**Key takeaway:** Your risk tolerance determines asset allocation → which determines portfolio performance and volatility.

See also: *asset allocation*, *stop-loss order*"""
    },
    
    # === Core Investment Concepts ===
    {
        "term": "dollar cost averaging",
        "category": "Investment Strategy",
        "content": """**Dollar-Cost Averaging (DCA)** là chiến lược đầu tư một số tiền cố định vào cùng một tài sản mỗi khoảng thời gian đều đặn, bất kể market price thế nào.

**Cách hoạt động:**
- Month 1: $1000 at $50/share → 20 shares
- Month 2: $1000 at $40/share → 25 shares  
- Month 3: $1000 at $60/share → ~16.7 shares
- Average cost per share = ($3000 / 61.7) = **$48.63** (lower than $50 average price!)

**Ưu điểm:**
- Không cần timing market — buy more when cheap, less when expensive
- Giảm emotional decisions (FOMO khi market tăng panic sell khi giảm)
- phù hợp cho salary-based investors (auto-debit monthly)

**Nhược điểm:**
- Trong bull market dài hạn → lump sum invest có hiệu suất cao hơn (~90% thời gian theo Dalbar study)
- Không tối ưu nếu biết trước downturn sắp đến

**Tại VN:** Auto-DCA qua các app VCSC, FPT-Aviva, hoặc trực tiếp từ SSI/market mỗi tháng cuối. Ideal frequency: monthly (end/begin month).

Also known as: *ruy-roic* (đầu tư định kỳ) in Vietnamese.
See also: *compound interest*, *index fund investment*"""
    },
    {
        "term": "compound interest",
        "category": "Basic Concept",
        "content": """**Compound Interest** (Lãi suất kép) là hiện tượng lợi nhuận được reinvest lại và tiếp tục sinh lợi nhuận — "interest on interest."

**Công thức:** FV = PV × (1 + r)^n
   
- FV = Future Value  
- PV = Present Value
- r = annual rate of return
- n = number of years

**Ví dụ thực tế:**
- $10,000 đầu tư ở 12%/year:
  - Year 5: $17,623 
  - Year 10: $31,059 
  - Year 20: $96,462 (gần gấp 10x!)
  - Year 30: $299,599 (gấp ~30x — power of time!)

**Quy tắc 72:** Số năm để vốn gấp đôi ≈ 72 ÷ \% return/năm
- 8% → ~9 years to double
- 12% → ~6 years to double  
- 24% → ~3 years to double

**Tại sao quan trọng trong đầu tư?**
- Time in market > timing market (Bogle)
- Bắt đầu sớm = advantage compounding cực lớn
- $500/month @ 12%/yr: Year 10 = $151k, Year 30 = $2.1M

Key principle: **Start early, stay consistent.** Time is your strongest ally in investing.
See also: *dollar cost averaging*"""
    },
    
    # === Market Terminology ===
    {
        "term": "bull market bear market",
        "category": "Market Terminology",
        "content": """**Bull Market & Bear Market** — Hai trạng thái cyclical của thị trường chứng khoán.

| Feature | Bull Market 🐂 | Bear Market 🐻 |
|---------|--------------|---------------| 
| Price movement | +20%+ từ low gần nhất | -20%+ từ high gần nhất |
| Sentiment | Optimistic, greed-dominated | Pessimistic, fear-dominated |
| Economy | Expanding, GDP growth > 3% | Contrasting, recession/unemployment rising |
| Duration | ~5-7 years (US long-term avg) | ~1.5-2 years (sharper but shorter) |
| Volume | Increasing highs & lows | Decreasing volume on rallies |
| Investor behavior | Buying more, holding | Selling off, defensive positioning |

**At VN context:**
- VN-Index bull phase: 300 → 1,500+ (2020-2022)
- Bear phases: corrections of -10% to -35% (e.g., March 2020 -34%, August 2022 -16%)

**Hybrid/Neutral**: "Sideways" or "range-bound" — no clear trend, typical choppy market conditions.

> Warren Buffett: "**Be fearful when others are greedy, and greedy when others are fearful.**"

See also: *market cycle*, *technical analysis*"""
    },
    {
        "term": "blue chip stocks",
        "category": "Stock Types",
        "content": """**Blue Chip Stocks** là cổ phiếu của các công ty lớn, uy tín, có lịch sử hoạt động ổn định dài hạn và thường trả dividend.

**Tiêu chí Blue Chip:**
- Market cap > $10 billion (hoặc ~250k+ tỷ USD tại VN)
- Operating history: 10+ years profitable 
- Dividend paying consistency (≥ 5 years consecutive)
- Industry leader position (market share #1 or #2)
- Stable earnings growth, low beta (< 1.2 typically)

**Tại Việt Nam — Examples:**
| Stock | Company | Sector | Market Cap (VNĐ) |
|-------|---------|--------|-------------------| 
| VNM | Vinamilk | FMCG/Dairy | ~300k+ tỷ |
| VIC | Vingroup | Real Estate/Diversified | ~250k+ tỷ |
| FPT | FPT Corporation | Tech/IT Services | ~180k+ tỷ |
| VCBC | Vietcombank | Banking | ~150k+ tỷ |
| HPG | Hoa Phat Group | Steel/Manufacturing | ~120k+ tỷ |

**Ưu điểm Blue Chips:**
- Lower volatility, more resilient in bear markets
- Dividend income for passive investors
- Easy to research (lots of analyst coverage)

**Nhược điểm:**
- Slower growth vs small/mid caps
- Known as "safe" but still carry market/system risk
- Value traps possible even for blue chips!

See also: *market capitalization*"""
    },
    
    # === Instrument Types ===
    {
        "term": "etf exchange traded fund",
        "category": "Investment Instruments",
        "content": """**ETF (Exchange Traded Fund)** là quỹ đầu tư được niêm yết và giao dịch như cổ phiếu trên sàn chứng khoán — kết hợp tính đa dạng của mutual fund với khả năng trade intraday giống stock.

**Cấu trúc hoạt động:**
- Tập hợp vốn từ nhiều investors → buy basket of securities 
- Each ETF share = fractional ownership in underlying assets
- Tracked index (VN30, NASDAQ-100) or active manager pick holdings

**Tại VN — Popular Vn-ETFs:**
| ETF | Fund House | Tracks | AUM approx. |
|-----|-----------|--------|-------------|
| VNAI | VNDirect | VN-Index (all stocks) | ~Vietnamese billion |
| VIETF | VCSC | VN30 Index | Largest in VN |
| FND1F | FRTech | FRTech Core 30 | Growing rapidly |
| MNB1 | MBS | Mid-cap focused | Niche but useful |

**ETF vs Stock vs Mutual Fund:**
| Feature | ETF | Individual Stocks | Mutual Fund |
|---------|-----|------------------|-------------|
| Diversification | High (one share = 30+ stocks) | None (one company) | Medium-High |
| Cost (fee) | Low (0.1-0.75%/yr) | No management fee | High (1-2%/yr) |
| Trading | Intraday real-time market prices | Intraday single stock | End-of-day NAV only |
| Tax-efficient | More tax efficient | Most tax efficient | Least due to frequent turnover |

**Why ETFs are recommended for beginners:** Lowest barrier to instant diversification across a whole index.
See also: *index fund*, *passive investing*"""
    },
    {
        "term": "dividend yield ex-dividend",
        "category": "Investment Instruments",
        "content": """**Dividend Yield & Ex-Dividend Date** — hai khái niệm quan trọng khi đầu tư cổ phiếu có chia cổ tức.

**Dividend Yield (Cổ tức yield):**
- Formula: **Dividend Yield = Annual Dividend per Share / Current Share Price × 100%**
- Example: stock $100, pays $4/year dividend → 4% yield
- High yield (>5%) attracts income investors but can signal distress (value trap!)
- Low yield (<2%) or no dividend = growth company reinvest profits

**Ex-Dividend Date (Trích cổ tức):**
- Ngày đầu tiên mà người mua KHÔNG nhận được cổ tức đã được declare
- Trước ex-dividend: buyer gets dividend; after ex-dividend date: seller keeps dividend
- Price normally drops by approximate amount on ex-date (no free money!)

**Tại VN — Notable High-Yield Stocks:**
| Stock | Approx. Yield (%) | Payment Frequency |
|-------|-------------------|-------------------|
| FPT | ~1.5% | Annual |
| ACB | ~3-4% | Semiannual |
| VCBC | ~2-3% | Annual quarterly |
| VNM | ~1-2% | Annual |

**Lưu ý quan trọng:**
- Dividend income subject to 5% personal tax in Vietnam  
- Reinvesting dividends (DRIP) massively boosts compound returns over time
- High yield + low payout ratio (<60%) = sustainable dividend; high yield + high payout (>90%) = potential cut ahead

See also: *compound interest*, *blue chip stocks*"""
    },
    
    # === Risk Management / Order Types ===
    {
        "term": "stop-loss take-profit order",
        "category": "Risk Management",
        "content": """**Stop-Loss & Take-Profit Orders** — Tools để quản lý rủi ro và chốt lời trong trading.

**Order Types:**
- **Market Order**: Buy/sell immediately at current price → guaranteed fill, no price control
- **Limit Order**: Specify max buy price / min sell price → price-guaranteed but no guarantee of execution  
- **Stop-Loss Order**: Triggered when price drops below stop price → becomes market order (sells automatically to limit losses)
- **Take-Profit Order (Limit Sell)**: Automatically sells at target profit level
  
**Tại VN - practical examples:**
- Buy HPG at $40 → place Stop-Loss at $36 (-10%) → automatic sell if drops
- If HPG reaches target $50 → Take-Profit order executes automatically, locking in gain

**Risk Management Rules:**
- Never risk > 2% of account value on one trade (position sizing with Kelly Criterion)
- Risk/Reward Ratio minimum: 1:2 (risk $1 to potentially gain $2+)
- Always use stop-loss — "hope is NOT a strategy"

**Mental frameworks:**
- Predefine entries/exits BEFORE placing trade
- Trail stop-loss upward as price rises ("trailing stop")  
- Psychological challenge: cutting losses hurts but preserves capital for future opportunities

See also: *Kelly Criterion position sizing*, *risk tolerance*"""
    },
    {
        "term": "market volatility beta",
        "category": "Risk & Volatility",
        "content": """**Market Volatility & Beta** — đo lường độ biến động and risk of a stock relative to overall market.

**Beta (β): Relative Volatility measure:**
- **β = 1**: Stock moves exactly with market (matches market volatility)
- **β > 1**: More volatile than market (higher risk, potentially higher returns). Example: tech stocks β=1.3-1.8
- **β < 1**: Less volatile than market (defensive). Example: utilities β=0.4-0.7
- **β < 0**: Inversely correlated with market (rare, some gold/commodities)

**Tại VN — Approximate betas:**
| Stock | Approx Beta | Sector |
|-------|------------|--------|
| VHM | ~1.5+ | Real Estate (volatile) |
| VNM | ~0.8-1.0 | FMCG (defensive, steady) |
| FPT | ~1.2-1.3 | Tech/Growth |
| VCBC | ~0.9-1.1 | Banking (moderate volatility) |

**Key insights:**
- High beta = suitable for aggressive traders who can handle -20-30% drawdowns 
- Low beta/beta < 1 = defensive portfolio during bear markets/uncertainty
- Diversifying across high & low beta stocks reduces overall portfolio volatility but doesn't eliminate systematic risk

**Related concepts:** Standard Deviation of returns = absolute volatility measure. Sharpe Ratio = (Return - Risk-Free) / Standard Deviation — measures return per unit of risk.

See also: *risk tolerance*, *portfolio diversification*"""
    },
    
    # === Analysis Frameworks ===
    {
        "term": "fundamental analysis earnings report",
        "category": "Analysis Methods",
        "content": """**Fundamental Analysis & Earnings Report**  — Phương pháp phân tích giá trị nội tại của công ty dựa trên financial statements và business fundamentals.

**Key Financial Statements (3 primary):**
1. **Income Statement** (Báo cáo kết quả kinh doanh): Revenue, COGS, operating profit, net income → determines EPS growth trend
2. **Balance Sheet** (Bảng cân đối kế toán): Assets = Liabilities + Equity → solvency and debt ratio analysis  
3. **Cash Flow Statement** (Báo cáo lưu chuyển tiền tệ): Operating/investing/financing cash flows → ability to fund operations/grow/dividends without new debt

**Earnings Report ( quarterly for VN listed companies):**
- Released within 45 days of quarter end per regulations
- **Beat**: actual EPS/revenue > analyst expectations → stock typically rises
- **Miss**: actual < expectations → stock drops
- Guidance/forward outlook matters as much as trailing results

**Key ratios from fundamentals:**
| Ratio | Formula | What it tells you | Good range |
|-------|---------|-------------------|-----------| 
| P/E | Price / EPS | How expensive relative to earnings | 10-20 (VN varies) |
| P/B | Price / Book Value per share | Market vs tangible net assets | < 3 for value stocks |
| ROE | Net Income / Shareholders' Equity | Profitability efficiency | > 15% excellent |
| Debt-to-Equity (D/E) | Total Liabilities / Equity | Leverage & solvency risk | < 1.0 generally safe |

**VN-specific:** VnIndex stocks report quarterly; some large caps also release annual reports with full audit.
See also: *EPS*, *P/E ratio*"""
    },
    {
        "term": "technical analysis trendline support resistance",
        "category": "Analysis Methods", 
        "content": """**Technical Analysis & Trendlines:** Phương pháp phân tích dựa trên price action, volume, patterns — giả định market discounts all info and moves in trends.

**Key Principles:**
1. **Trend is your friend**: Price tends to continue in its established direction
2. Support/resistance levels create "floors" and "ceilings" on price movement  
3. Volume confirms trend strength (breakouts need volume support)

**Support & Resistance:**
- **Support level**: Price level where buying pressure historically prevents further decline → "floor"
- **Resistance level**: Price level where selling pressure historically keeps price from rising → "ceiling"
- When support breaks → becomes resistance; when resistance breaks → becomes support (role reversal)

**Trendline Drawing:**
- Uptrend line: draw below prices connecting successive HIGHER LOWS
- Downtrend line: draw above prices connecting successive LOWER HIGHS 
- Break above uptrend line = potential reversal signal; break below downtrend = further decline likely

**Tại VN practice:**
- VN-Index historically finds strong support at round numbers (700, 800, 900, 1000)
- Resistance levels identified from previous peaks before corrections
- Volume on breakout days: if volume > 2x daily average → more reliable signal

See also: *moving average*, *volume profile*, *MACD crossover*"""
    },
]

# --- Insert terms ---
print(f"📝 Seeding {len(TERMS)} new terms into KB...\n")

for i, term in enumerate(TERMS):
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO knowledge (term, content)
            VALUES (:term, :content)
        """, term)
        print(f"  ✓ {i+1}. {term['term']} [{term['category']}]")
    except Exception as e:
        print(f"  ✗ {term['term']}: {e}")

conn.commit()

# Verify counts
cursor.execute("SELECT COUNT(*) FROM knowledge")
total = cursor.fetchone()[0]

print(f"\n✅ SUCCESS! Total KB entries: {total}")

conn.close()
print("\n📤 Batch 5 complete! Run app and test with /api/search?q=etf")
