# -*- coding: utf-8 -*-
"""enrich_kb.py - Enrich jarvis.db with additional financial knowledge terms.

Usage:
    cd /Users/nghialam/jarvis-hub
    python3 scripts/enrich_kb.py [--batch 1|2|3|4|all]
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database


# ==============================================================================
# BATCH 1: Fundamental Analysis (8 terms) + Momentum Indicators (4 terms) = 12 terms
# ==============================================================================
BATCH_1_TERMS = [
    {
        "term": "pe ratio",
        "content": "Price-to-Earnings (P/E) ratio là chỉ số đo lường mối quan hệ giữa giá chứng khoán và thu nhập trên mỗi cổ phiếu (EPS).\n\n**Công thức:** P/E = Giá cổ phiếu / EPS (Earnings Per Share)\n\n**Ý nghĩa:**\n"
                   "- P/E cao: Nhà đầu tư kỳ vọng tăng trưởng tương lai cao, hoặc cổ phiếu đang bị định giá đắt.\n"
                   "- P/E thấp: Có thể báo hiệu cổ phiếu bị định giá rẻ, hoặc doanh nghiệp gặp khó khăn.\n"
                   "- P/E trung bình thị trường Việt Nam dao động 10-20x (bank ~6-8x, tech ~25-40x).\n\n"
                   "**Lưu ý:** P/E không hữu ích với công ty không có lợi nhuận (P/E âm). Khi earnings bị thao túng (nhuường nhịn kế toán), P/E sẽ gây hiểu lầm về định giá thực.",
        "tags": "valuation fundamental analysis ratio profit",
    },
    {
        "term": "eps earnings per share",
        "content": "EPS (Earnings Per Share - Lợi nhuận trên mỗi cổ phiếu) là chỉ số đo hiệu quả hoạt động của công ty.\n\n**Công thức:** EPS = (Lợi nhuận ròng - Cổ tức CP ưu đãi) / Số lượng CP phổ thông trung bình\n\n"
                   "**Ý nghĩa:**\n"
                   "- EPS tăng hàng năm: Công ty đang phát triển tốt, giá trị thực tế tăng.\n"
                   "- EPS âm (loss): Công ty đang thua lỗ, rủi ro cao. Cần xem xét khả năng hoàn vốn.\n"
                   "- EPS growth rate >15% là strong grower, bị institutional investors theo dõi kỹ.\n\n"
                   "**Ví dụ:** XYZ có lợi nhuận 500 tỷ và 500 triệu CP phổ thông -> EPS = 1000đ/cp. Tăng trưởng EPS YoY +20% là tín hiệu tích cực.",
        "tags": "fundamental analysis earnings ratio profit growth",
    },
    {
        "term": "pb ratio price to book",
        "content": "P/B Ratio (Price-to-Book - Hệ số giá trên giá trị sổ sách) so sánh giá thị trường với Book Value Per Share.\n\n"
                   "**Công thức:** P/B = Giá cổ phiếu / Book Value Per Share (BVPS)\n\n**Ý nghĩa:**\n"
                   "- P/B < 1: Cổ phiếu được định giá rẻ hơn giá trị tài sản thật (potential value play).\n"
                   "- P/B > 5 hoặc cao bất thường: Đầu tư tăng trưởng, thị trường kỳ vọng rất cao.\n"
                   "- Ngân hàng/VN-Index thường có P/B ~0.8-1.2x; Tech/consumer không vốn nặng thì cao hơn (2-4x).\n\n"
                   "**Lưu ý:** Không hữu ích với công ty dịch vụ, software - vì tài sản chủ yếu là nhân lực/intangible assets.",
        "tags": "valuation fundamental analysis ratio asset",
    },
    {
        "term": "fcf free cash flow",
        "content": "Free Cash Flow (FCF) = Cash from Operations (CFO) - Capital Expenditures (CapEx). Đây là dòng tiền thực tế công ty có thể trả cổ tức hoặc tái đầu tư.\n\n"
                   "**Tại sao FCF quan trọng:**\n"
                   "- Net income có thể bị ảnh hưởng bởi các khoản phi tiền mặt (khấu hao, accruals).\n"
                   "- FCF luôn dương và tăng trưởng là báo hiệu tài chính mạnh, cổ tức bền vững.\n\n"
                   "**Chỉ số liên quan:**\n"
                   "- FCF Yield = FCF / Market Cap (%). > 5% thường undervalued.\n"
                   "- FCF Margin = FCF / Revenue (%) thể hiện chất lượng lợi nhuận.\n\n"
                   "**Ví dụ:** CFO = 100 tỷ, CapEx = 30 tỷ → FCF = 70 tỷ. Cao hơn net income cho thấy quality of earnings tốt.",
        "tags": "fundamental analysis cash flow ratio",
    },
    {
        "term": "stochastic oscillator",
        "content": "Stochastic Oscillator (%K và %D) đo vị trí giá đóng cửa so với range N ngày, thang 0-100.\n\n"
                   "**Công thức cơ bản:**\n"
                   "- %K = (Close - Lowest Low của N kỳ) / (Highest High của N kỳ - Lowest Low) x 100\n"
                   "- thường dùng N=14, Signal line (%D) là EMA-3 của %K\n\n"
                   "**Cách đọc:**\n"
                   "- Trên 80: Overbought (quá mua), khả năng điều chỉnh giảm.\n"
                   "- Dưới 20: Oversold (quá bán), khả năng hồi tăng.\n"
                   "- Crossover tín hiệu mạnh nhất: Khi %K cắt lên trên %D trong vùng Oversold = Buy signal; khi cắt xuống dưới %D trong vùng Overbought = Sell signal.\n\n"
                   "**Lưu ý:** Trong strong trend, Stochastic có thể ở mức overbought/oversold rất lâu. Cần kết hợp với trend filter (SMA > EMA50).",
        "tags": "technical analysis indicator oscillator momentum",
    },
]

# ==============================================================================
# BATCH 2: Trend Following + Volatility/Volume (6 terms)
# ==============================================================================
BATCH_2_TERMS = [
    {
        "term": "atr average true range",
        "content": "ATR (Average True Range) là chỉ báo đo độ biến động giá tuyệt đối, không cho biết hướng di chuyển.\n\n"
                   "**Cách tính:**\n"
                   "- True Range (TR) = Max của:\n  • High - Low ngày hiện tại\n  • |High - Close_prev|\n  • |Low - Close_prev|\n"
                   "- ATR(N) = SMA của TR trong N kỳ (thường 14)\n\n"
                   "**Ứng dụng thực chiến:**\n"
                   "- Stop-loss động: Đặt dưới giá thấp nhất gần đây trừ 2xATR, tránh bị 'dọn phòng' khi market volatility tăng.\n"
                   "- Position sizing: Risk per trade = distance đến stop-loss x ATR multiplier, từ đó tính số CP phù hợp với 1-2% risk on capital.\n\n"
                   "**Ví dụ:** Giá cổ phiếu 50.000đ, ATR(14) = 2.500đ → Stop-loss ở ~50.000 - (2 x 2.500) = 45.000đ.",
        "tags": "technical analysis indicator volatility risk stop-loss",
    },
    {
        "term": "obv on balance volume",
        "content": "On-Balance Volume (OBV) là chỉ báo dòng tiền cumulative, kết hợp giá và khối lượng giao dịch để dự đoán xu hướng.\n\n"
                   "**Cách tính:**\n"
                   "- Nếu Close > Open: OBV ngày = OBV trước + Volume phiên đó\n"
                   "- Nếu Close < Open: OBV = OBV trước - Volume\n"
                   "- Nếu Close == Open: OBV giữ nguyên\n\n"
                   "**Cách đọc:**\n"
                   "- OBV tăng trong khi giá consolidate/sideways → Smart money đang tích lũy (accumulation = bullish).\n"
                   "- OBV giảm trong consolidation → Distribution (phân phối, smart money bán ra = bearish).\n"
                   "- Divergence mạnh nhất: Giá tạo đỉnh thấp hơn nhưng OBV đỉnh cao hơn → chuẩn bị breakout tăng.\n\n"
                   "**Lưu ý:** OBV không chính xác 100% trong phiên T+3 Việt Nam vì volume ghi nhận có độ trễ, nên dùng kết hợp với RSI và SMA.",
        "tags": "technical analysis indicator volume trend accumulation",
    },
    {
        "term": "bollinger squeeze",
        "content": "Bollinger Bands Squeeze là hiện tượng các band co lại cực kỳ narrow, báo hiệu sắp có biến động mạnh (breakout).\n\n"
                   "**Khái niệm:**\n"
                   "- Upper Band = SMA20 + 2xStDev(20)\n"
                   "- Lower Band = SMA20 - 2xStDev(20)\n"
                   "- Band Width = (Upper - Lower) / SMA20 x 100%\n\n"
                   "**Squeeze Signal:**\n"
                   "- Khi Band Width < 5% so với trung bình historical (20-30 ngày) → market đang consolidation.\n"
                   "- Breakout lên trên Upper Band + Volume tăng mạnh → Buy signal, target là chiều rộng band x entry price.\n"
                   "- Breakdown xuống dưới Lower Band + Volume lớn → Sell/short signal.\n\n"
                   "**Ví dụ:** Cổ phiếu VNM đi ngang trong 6 tuần, band_width từ 15% giảm còn 3%, đột ngột break up với volume gấp 2 trung bình → xu hướng uptrend mới có thể bắt đầu.",
        "tags": "technical analysis indicator volatility breakout squeeze",
    },
    {
        "term": "vwap volume weighted average price",
        "content": "VWAP (Volume Weighted Average Price) là đường trung bình động giá theo khối lượng, dùng chủ yếu cho intraday analysis.\n\n"
                   "**Công thức:** VWAP = Cumulative(Price x Volume) / Cumulative(Volume)\n\n"
                   "**Cách sử dụng:**\n"
                   "- Giá > VWAP trong phiên → Bullish intraday (institutional buyers đang đẩy giá).\n"
                   "- Giá < VWAP → Bearish session (sellers đang kiểm soát).\n"
                   "- Pullback về VWAP trong uptrend thường là entry opportunity tốt, vì đây là vùng institutional support.\n\n"
                   "**Khác với SMA:** VWAP chỉ reset vào đầu phiên giao dịch mỗi ngày, nên là benchmark intraday của các fund manager, không phải swing trading indicator.",
        "tags": "technical analysis indicator volume intraday",
    },
]

# ==============================================================================
# BATCH 3: Candlestick Patterns + Risk Management Math (6 terms)
# ==============================================================================
BATCH_3_TERMS = [
    {
        "term": "doji candlestick pattern",
        "content": "Doji là nến có Open và Close bằng nhau hoặc gần như bằng nhau, tạo thân nến rất nhỏ.\n\n"
                   "**Đặc điểm:**\n"
                   "- Thân nến gần như zero (khoảng cách Open-Close < 0.1% of range).\n"
                   "- Bóng trên/dưới thể hiện áp lực buy/sell trong phiên nhưng kết thúc cân bằng.\n\n"
                   "**Phân loại và ý nghĩa:**\n"
                   "- Long-legged Doji (bóng cả 2 đầu dài): Indecision mạnh nhất, reversal potential cao.\n"
                   "- Gravestone Doji (Open=Close thấp, bóng trên dài): Bears thắng phiên. Nếu sau uptrend là strong sell signal.\n"
                   "- Dragonfly Doji (Open=Close cao, bóng dưới dài): Bulls phản công từ đáy, bullish reversal.\n\n"
                   "**Xác nhận:** Chỉ có giá trị khi xuất hiện sau 1-2 tuần trending mạnh, không phải trong consolidation. "
                   "Cần candlestick xác nhận tiếp theo (ví dụ: doji + next day green body = indecision → buyers stepping in).",
        "tags": "technical analysis candlestick pattern reversal",
    },
    {
        "term": "hammer shooting star candlestick",
        "content": "Hammer và Shooting Star là hai nến reversal mạnh với thân nhỏ và bóng dài.\n\n"
                   "**Nến Hammer (bullish reversal):**\n"
                   "- Xuất hiện sau downtrend → báo hiệu bottoming.\n"
                   "- Thân nhỏ ở top, bóng dưới dài gấp 2x body.\n"
                   "- Open/Close nằm trong nửa trên của range.\n"
                   "- Xác nhận: Ngày tiếp theo close cao hơn hammer's open → buy signal xác thực.\n\n"
                   "**Nến Shooting Star (bearish reversal):**\n"
                   "- Xuất hiện sau uptrend → báo hiệu toping/potential correction.\n"
                   "- Thân nhỏ ở bottom, bóng trên dài gấp 2x body.\n"
                   "- Xác nhận: Ngày tiếp close thấp hơn shooting star's open → sell/short signal.\n\n"
                   "**Lưu ý:** Nếu không có xác nhận candlestick phía sau, Hammer/Shooting Star chỉ là indecision pattern, không phải reversal mạnh.",
        "tags": "technical analysis candlestick pattern reversal bottom top",
    },
    {
        "term": "kelly criterion position sizing",
        "content": "Kelly Criterion là công thức tính optimal position sizing để tối đa hóa tăng trưởng vốn dài hạn. Được sử dụng bởi các hedge fund như Renaissance Technologies.\n\n"
                   "**Công thức Kelly:**\n"
                   "- f* = (p x b - q) / b\n"
                   "- f* = fraction vốn nên đầu tư vào trade này\n"
                   "- p = probability win (tỷ lệ thắng từ backtest, ví dụ 40%)\n"
                   "- q = probability lose = 1 - p (60%)\n"
                   "- b = avg profit / avg loss (Reward-to-Risk ratio, ví dụ 2.5)\n\n"
                   "**Ví dụ:** p=0.40, q=0.60, b=2.5\n"
                   "→ f* = (0.4 x 2.5 - 0.6) / 2.5 = 0.20\n"
                   "→ Kelly suger 20% capital vào trade này.\n\n"
                   "**Quan trọng:** Thực tế nên dùng Half-Kelly (= f*/2) để giảm over-leverage và draw-down cực đại vì probability estimates thường optimistic. "
                   "Half Kelly ở trên = ~10% per trade.",
        "tags": "risk management position sizing math portfolio capital",
    },
]

# ==============================================================================
# BATCH 4: Macro VN/Crypto Specifics + Psychology (5 terms)
# ==============================================================================
BATCH_4_TERMS = [
    {
        "term": "sbv vietnam interest rate rrr",
        "content": "SBV Interest Rate (Lãi suất dự trữ bắt buộc - Reserve Requirement Ratio/RRR) là công cụ điều tiết tiền tệ của Ngân hàng Nhà nước Việt Nam.\n\n"
                   "**Cơ chế truyền dẫn:**\n"
                   "- Tăng RRR → ngân hàng thương mại bị khóa nhiều vốn hơn → thanh khoản thị trường giảm → áp lực bán lên market (VN-Index).\n"
                   "- Giảm RRR → tăng lending capacity → dòng tiền vào thị trường chứng khoán tăng.\n\n"
                   "**Ảnh hưởng sector:**\n"
                   "- BANK/NH: Trực tiếp - margin lending thay đổi, NIM bị ảnh hưởng.\n"
                   "- REE (Bất động sản): Highly leveraged → lợi từ RRR giảm (vay rẻ hơn).\n"
                   "- Consumer/Manufacturing: Indirectly受惠 từ liquidity increase.\n\n"
                   "**Theo dõi:** Bảng RRR của từng ngân hàng thương mại (TCBS, VPBank, BID...) do mỗi bank có mức reserve riêng.",
        "tags": "macro economics vietnam central bank interest rate liquidity",
    },
    {
        "term": "fii foreign institutional investor flow",
        "content": "FII (Foreign Institutional Investor) Flow tracking là chỉ báo dòng vốn nước ngoài vào/ra thị trường chứng khoán Việt Nam.\n\n"
                   "**Tại sao FII quan trọng:**\n"
                   "- FII nắm giữ ~25-30% market cap của VN-Index, di chuyển lớn ảnh hưởng trực tiếp đến giá cổ phiếu/blue chips (VNM, VIC, FPT,...).\n"
                   "- Net buy > 200 tỷ/ngày là tín hiệu bullish; net sell liên tục > 3 ngày = bearish warning.\n\n"
                   "**Cách theo dõi qua CTCK:** VPSec, VPS, SCBS đều có bảng Foreign Flow hàng ngày (Net Buys/Sells per stock + total market).\n\n"
                   "**Mối quan hệ với USD/VND và lãi suất Fed:**\n"
                   "- Fed cắt giảm → USD yếu → FII quay về emerging markets như VN ↑\n"
                   "- Fed tăng → USD mạnh → FII rút vốn từ EM (emerging markets).",
        "tags": "macro economics vietnam foreign investment fii capital flow",
    },
    {
        "term": "btc dominance halving cycle crypto",
        "content": "BTC Dominance và Halving Cycles là hai yếu tố quan trọng nhất để hiểu xu hướng crypto market.\n\n"
                   "**BTC.D (Bitcoin Dominance):**\n"
                   "- BTC.D = BTC Market Cap / Total Crypto MC x 100%\n"
                   "- Rising (↑ từ 50% → 60%+): Altcoins bleed, capital rút về BTC → risk-off trong crypto.\n"
                   "- Falling (↓ xuống dưới 50%): Capital rotates vào altcoins → altseason bắt đầu.\n\n"
                   "**Bitcoin Halving Cycle (~4 năm):**\n"
                   "- Giảm block reward từ 50 → 25 → 12.5 → 6.25 BTC.\n"
                   "- Historical pattern: Pre-halving pump (tích lũy) → Post-halving correction - Bull run Year after halving confirmed.\n\n"
                   "**Ví dụ:** Halving tháng 4/2024, đỉnh altseason ~tháng 9/2024-3/2025 là pattern lặp lại từ chu kỳ 2016-2017 và 2020-2021.",
        "tags": "crypto bitcoin halving dominance cycle altseason",
    },
    {
        "term": "fomo psychology trading discipline",
        "content": "FOMO (Fear Of Missing Out) là tâm lý mua đỉnh khi giá đã tăng mạnh, chạy theo momentum khi RSI > 80.\n\n"
                   "**Cơ chế FOMO:**\n"
                   "- Khi giá cổ phiếu/coin tăng liên tục nhiều phiên mà không vào lệnh → lo ngại lỡ cơ hội → mua ở đỉnh (buy the top).\n"
                   "- Thường bị retail investors rơi vào, institutional traders đợi pullback/retest.\n\n"
                   "**Quy tắc discipline chống FOMO:**\n"
                   "- Chỉ vào lệnh khi setup hoàn chỉnh (breakout + volume confirm + RSI không overbought).\n"
                   "- Không follow social media hype hoặc group chat FOMO alerts.\n"
                   "- Thiết lập limit order thay vì market buy để tránh emotional trading.\n\n"
                   "**Mẹo tâm lý:** Ghi trading journal hàng ngày để tự nhận ra pattern FOMO của chính mình.",
        "tags": "trading psychology discipline fomo risk mindset",
    },
    {
        "term": "risk reward expectancy position math",
        "content": "Risk/Reward Ratio và Expectancy là hai công thức toán học then chốt cho trading system bền vững.\n\n"
                   "**Risk/Reward Ratio (RR):**\n"
                   "- RR = Average Profit when win / Average Loss when lose\n"
                   "- Minimum nên 1:2 hoặc 1:3. Nếu stop-loss cách entry 3%, target profit tối thiểu 6-9%.\n\n"
                   "**Expectancy Formula:**\n"
                   "- Expectancy = (WinRate x AvgWin) - (LossRate x AvgLoss)\n"
                   "- Kết quả > 0 → hệ thống có edge (có lợi về lâu dài).\n\n"
                   "**Ví dụ tính expectancy:**\n"
                   "- Win Rate = 40% (3 thắng / 7 thua, ratio W:L = 4:6)\n"
                   "- Avg Win = 12% trên capital, Avg Loss = 4%\n"
                   "- Expectancy per trade = (0.4 x 12%) - (0.6 x 4%) = 4.8% - 2.4% = +2.4%\n\n"
                   "**Tuy Win Rate chỉ 40%, nhưng kỳ vọng dương → profitable system. **Không cố tối ưu Win Rate mà bỏ đi Risk Management.**",
        "tags": "risk management position sizing expectancy math statistics trading",
    },
]


# ==============================================================================
# BATCH EXECUTOR
# ==============================================================================

BATCHES = {
    1: BATCH_1_TERMS,
    2: BATCH_2_TERMS,
    3: BATCH_3_TERMS,
    4: BATCH_4_TERMS,
}


def seed_batch(batch_number, batch_terms):
    """Seed a specific batch of terms into jarvis.db."""
    db = Database()
    saved_count = 0
    skipped_count = 0

    print("\n" + "=" * 60)
    print("BATCH %d: Seeding %d terms" % (batch_number, len(batch_terms)))
    print("=" * 60)

    for term_data in batch_terms:
        term = term_data["term"]
        content = term_data["content"]
        tags = term_data.get("tags", "")

        rowid = db.save_term(term=term, content=content, tags=tags)

        if rowid is not None:
            print("  %s" % term)
            saved_count += 1
        else:
            print("  SKIPPED (already exists): %s" % term)
            skipped_count += 1

    print("\n" + "=" * 60)
    print("BATCH %d COMPLETE:" % batch_number)
    print("   Saved:     %d terms" % saved_count)
    print("   Skipped:   %d terms" % skipped_count)
    print("=" * 60)

    return saved_count, skipped_count


def main():
    """Main entry point. Supports --batch N or no arg to run all batches."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enrich jarvis.db with financial knowledge terms."
    )
    parser.add_argument(
        "--batch",
        type=int,
        choices=[1, 2, 3, 4],
        default=0,
        help="Batch to seed (0 or omit to run all batches)",
    )
    args = parser.parse_args()

    if args.batch == 0:
        # Run ALL batches sequentially
        total_saved = 0
        total_skipped = 0
        for batch_num in [1, 2, 3, 4]:
            saved, skipped = seed_batch(batch_num, BATCHES[batch_num])
            total_saved += saved
            total_skipped += skipped

        print("\n" + "=" * 60)
        print("ALL BATCHES COMPLETE")
        print("  Total saved:    %d terms" % total_saved)
        print("  Total skipped:  %d terms" % total_skipped)
        print("=" * 60)
    else:
        # Run specific batch only (for partial enrichment)
        seed_batch(args.batch, BATCHES[args.batch])


if __name__ == "__main__":
    main()
