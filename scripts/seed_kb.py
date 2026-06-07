# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""seed_kb.py - Pre-populate knowledge base with essential financial terms for Jarvis Hub."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import Database

FINANCIAL_TERMS = [
    {
        "term": "pe ratio",
        "content": ("Price-to-Earnings (P/E) ratio là chỉ số đo lường mối quan hệ giữa giá chứng khoán và thu nhập trên mỗi cổ phiếu (EPS).\n\n"
                     "Công thức: P/E = Giá cổ phiếu / EPS\n\n"
                     "Ý nghĩa:\n"
                     "- P/E cao: Nhà đầu tư kỳ vọng tăng trưởng tương lai cao, hoặc cổ phiếu đang bị định giá đắt.\n"
                     "- P/E thấp: Có thể báo hiệu cổ phiếu bị định giá rẻ, hoặc doanh nghiệp gặp khó khăn.\n"
                     "- P/E trung bình thị trường thường dao động 15-25 (tùy ngành).\n\n"
                     "Ví dụ: Cổ phiếu ABC có giá $100 và EPS $5 -> P/E = 20x.\n\n"
                     "Lưu ý: P/E không hữu ích với công ty không có lợi nhuận (P/E âm)."),
        "tags": "valuation fundamental analysis ratio"
    },
    {
        "term": "eps earnings per share",
        "content": ("EPS (Earnings Per Share - Lợi nhuận trên mỗi cổ phiếu) là chỉ số đo hiệu quả hoạt động của công ty.\n\n"
                     "Công thức: EPS = (Lợi nhuận ròng - Cổ tức CP ưu đãi) / Số lượng CP phổ thông trung bình\n\n"
                     "Ý nghĩa:\n"
                     "- EPS tăng hàng năm: Công ty đang phát triển tốt.\n"
                     "- EPS âm: Công ty đang thua lỗ.\n"
                     "- So sánh EPS giữa các công ty cùng ngành giúp đánh giá tương đối.\n\n"
                     "Ví dụ: XYZ có lợi nhuận $10 triệu và 5 triệu CP phổ thông -> EPS = $2/cp."),
        "tags": "fundamental analysis earnings ratio"
    },
    {
        "term": "pb ratio price to book",
        "content": ("P/B Ratio (Price-to-Book ratio - Hệ số giá trên giá trị sổ sách) so sánh giá thị trường với giá trị sổ sách mỗi cổ phiếu.\n\n"
                     "Công thức: P/B = Giá cổ phiếu / Book Value Per Share\n\n"
                     "Ý nghĩa:\n"
                     "- P/B < 1: Cổ phiếu có thể bị định giá rẻ hơn giá trị thực tế (cơ hội).\n"
                     "- P/B cao (>5): Đầu tư tăng trưởng, thị trường kỳ vọng cao.\n"
                     "- Ngân hàng thường P/B thấp (1-2x), công ty công nghệ cao (3-10x).\n\n"
                     "Ví dụ: ABC có giá $50 và Book Value $25 -> P/B = 2.0x.\n\n"
                     "Lưu ý: Không hữu ích với công ty dịch vụ/kiến thức (ít tài sản hữu hình)."),
        "tags": "valuation fundamental analysis ratio"
    },
    {
        "term": "rsi relative strength index",
        "content": ("RSI (Relative Strength Index - Chỉ số sức mạnh tương đối) là oscillator đo động lượng giá, thang 0-100.\n\n"
                     "Công thức: RSI = 100 - [100 / (1 + RS)], RS = Avg Gain / Avg Loss (14 chu kỳ)\n\n"
                     "Cách sử dụng:\n"
                     "- RSI >= 70: QUÁ MUA (Overbought) - Có thể điều chỉnh giảm.\n"
                     "- RSI <= 30: QUÁ BÁN (Oversold) - Có thể hồi phục tăng giá.\n"
                     "- RSI 40-60: Trung tính.\n"
                     "- Golden Cross RSI: RSI vượt lên trên 50 = Tín hiệu Bullish.\n\n"
                     "Ví dụ: Cổ phiếu tăng mạnh 14 phiên, RSI = 78 -> Quá mua, cân nhắc chốt lời."),
        "tags": "technical analysis indicator oscillator momentum"
    },
    {
        "term": "macd moving average convergence divergence",
        "content": ("MACD (Moving Average Convergence Divergence) là chỉ báo động lượng so sánh hai đường EMA.\n\n"
                     "Công thức:\n"
                     "- MACD Line = EMA(12) - EMA(26)\n"
                     "- Signal Line = EMA(9 ngày) của MACD Line\n"
                     "- Histogram = MACD Line - Signal Line\n\n"
                     "Cách sử dụng:\n"
                     "- Golden Cross (MACD cắt lên Signal): Tín hiệu MUA.\n"
                     "- Death Cross (MACD cắt xuống Signal): Tín hiệu BÁN.\n"
                     "- Histogram dương và tăng: Xu hướng tăng mạnh.\n"
                     "- Divergence: MACD đi ngược xu hướng giá = tín hiệu đảo chiều.\n\n"
                     "Ví dụ: MACD crossing lên Signal Line, histogram chuyển âm sang dương -> Tín hiệu mua mạnh."),
        "tags": "technical analysis indicator trend momentum"
    },
    {
        "term": "sma ema moving average",
        "content": ("Moving Average (MA) là chỉ báo xu hướng sử dụng trung bình giá trong khoảng thời gian xác định.\n\n"
                     "1. SMA (Simple Moving Average): Trung bình cộng đơn giản.\n"
                     "- SMA(20): Xu hướng ngắn hạn.\n"
                     "- SMA(50): Xu hướng trung hạn.\n"
                     "- SMA(200): Xu hướng dài hạn. Giá trên SMA(200) = Bullish.\n\n"
                     "2. EMA (Exponential Moving Average): Trọng sốcho giá mới cao hơn, phản ứng nhanh hơn.\n\n"
                     "Cách sử dụng:\n"
                     "- Golden Cross: SMA50 cắt lên SMA200 -> Bullish mạnh.\n"
                     "- Death Cross: SMA50 cắt xuống SMA200 -> Bearish.\n"
                     "- Giá nằm trên MA = xu hướng tăng, hỗ trợ động.\n"
                     "- Giá nằm dưới MA = xu hướng giảm, kháng cự động."),
        "tags": "technical analysis indicator trend support resistance"
    },
    {
        "term": "bollinger bands bb",
        "content": ("Bollinger Bands là chỉ báo biến động giá gồm 3 đường: Middle Band SMA(20), Upper = SMA20 + 2x STD, Lower = SMA20 - 2x STD.\n\n"
                     "Cách sử dụng:\n"
                     "- Giá chạm Upper Band = Quá mua tương đối.\n"
                     "- Giá chạm Lower Band = Quá bán tương đối.\n"
                     "- Narrowing Bands (Bollinger Squeeze): Biến động thấp -> Sắp có breakout mạnh.\n"
                     "- Band mở rộng: Biến động tăng, xu hướng đang mạnh.\n\n"
                     "Kết hợp với RSI để kiểm chứng. Band co lại + volume tăng thường báo hiệu biến động lớn sắp xảy ra."),
        "tags": "technical analysis indicator volatility reversal"
    },
    {
        "term": "volume trading",
        "content": ("Khối lượng giao dịch (Volume) là số lượng CP được giao dịch, xác nhận tính vững chắc của xu hướng.\n\n"
                     "Quy tắc cơ bản:\n"
                     "- Giá tăng + Volume tăng -> Xu hướng tăng mạnh và bền vững.\n"
                     "- Giá tăng + Volume giảm -> Thiếu lực mua, có thể đảo chiều.\n"
                     "- Giá giảm + Volume cao -> Áp lực bán lớn, rủi ro cao.\n"
                     "- Breakout + Volume rất cao -> Xác nhận breakout thành công.\n\n"
                     "Volume Profile & OBV:\n"
                     "- On-Balance Volume (OBV): Cộng volume ngày tăng, trừ volume ngày giảm. OBV tăng giá đi phẳng = Tích lũy ngầm.\n"
                     "- Volume đỉnh đột biến thường là điểm đảo chiều.\n\n"
                     "Ví dụ: CPA tăng 5% với volume gấp 3 lần trung bình -> Xác nhận mạnh."),
        "tags": "technical analysis indicator trend confirmation"
    },
]

def seed_database():
    db = Database()
    saved_count = 0

    print(f"\n{'=' * 60}")
    print("SEEDING FINANCIAL KNOWLEDGE BASE")
    print(f"{'=' * 60}\n")

    for term_data in FINANCIAL_TERMS:
        rowid = db.save_term(
            term=term_data["term"],
            content=term_data["content"],
            tags=term_data.get("tags", "")
         )
        if rowid:
            saved_count += 1
            print(f"   {term_data['term']} - SAVED")
        else:
            print(f"   {term_data['term']} - SKIPPED (already exists)")

    print(f"\n{'=' * 60}")
    print(f"SEED COMPLETE: {saved_count}/{len(FINANCIAL_TERMS)} terms saved")
    print(f"{'=' * 60}\n")

if __name__ == "__main__":
    seed_database()
