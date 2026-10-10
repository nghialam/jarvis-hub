#!/usr/bin/env python3
"""Generate test market briefs for UI verification."""
import sqlite3
import json
import os

DB_PATH = os.path.expanduser("~/jarvis-hub/data/jarvis.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Generate 3 test briefs
test_briefs = [
    {
        "date": "2026-09-25",
        "source": "cron",
        "raw_json": json.dumps({
            "date": "2026-09-25",
            "vn_index": {"close": 1285.5, "change": "+8.3", "pct": "+0.65%"},
            "gold_sjc": {"buy": "82.50", "sell": "83.30"},
            "usd_vnd": 25250,
            "volume": "12.5K tỷ"
        }),
        "formatted_output": """🇻🇳 Thị trường Việt Nam — 25/09/2026

📊 Cổ phiếu
- VN-Index: 1285.5 (+8.3, +0.65%) — Tăng nhẹ
- 52-week range: 1180 — 1310
- Khối ngoại: Mua ròng 150 tỷ
- Top gainers: VIC 3.2%, VNM 2.8%, HDB 2.1%
- Top losers: VIC -0.5%, MWG -0.3%, GAS -0.2%

🥇 Vàng
- Vàng SJC: 82.50 — 83.30 triệu đồng/lượng (tăng nhẹ)

💵 Tỷ giá
- USD/VND: 25,250 (ổn định)
- Fed rate: 4.25%

**📌 Jarvis Hub — Thị trường Việt Nam**
**📅 25/09/2026 — 🕑 16:00 SGT**
**🔗 jarvis-hub:8100"""
    },
    {
        "date": "2026-09-24",
        "source": "cron",
        "raw_json": json.dumps({
            "date": "2026-09-24",
            "vn_index": {"close": 1277.2, "change": "-5.1", "pct": "-0.40%"},
            "gold_sjc": {"buy": "82.20", "sell": "83.00"},
            "usd_vnd": 25240,
            "volume": "10.2K tỷ"
        }),
        "formatted_output": """🇻🇳 Thị trường Việt Nam — 24/09/2026

📊 Cổ phiếu
- VN-Index: 1277.2 (-5.1, -0.40%) — Giảm nhẹ
- 52-week range: 1180 — 1310
- Khối ngoại: Bán ròng 80 tỷ
- Top gainers: FPT 4.1%, GVR 3.5%, VIX 2.9%
- Top losers: VCB -1.2%, VPB -0.8%, BID -0.6%

🥇 Vàng
- Vàng SJC: 82.20 — 83.00 triệu đồng/lượng (giảm nhẹ)

💵 Tỷ giá
- USD/VND: 25,240 (tăng nhẹ)
- Fed rate: 4.25%

**📌 Jarvis Hub — Thị trường Việt Nam**
**📅 24/09/2026 — 🕑 16:00 SGT**
**🔗 jarvis-hub:8100"""
    },
    {
        "date": "2026-09-23",
        "source": "manual",
        "raw_json": json.dumps({
            "date": "2026-09-23",
            "vn_index": {"close": 1282.3, "change": "+3.7", "pct": "+0.29%"},
            "gold_sjc": {"buy": "82.30", "sell": "83.10"},
            "usd_vnd": 25235,
            "volume": "9.8K tỷ"
        }),
        "formatted_output": """🇻🇳 Thị trường Việt Nam — 23/09/2026

📊 Cổ phiếu
- VN-Index: 1282.3 (+3.7, +0.29%) — Hồi nhẹ
- 52-week range: 1180 — 1310
- Khối ngoại: Mua ròng 60 tỷ
- Top gainers: POW 5.2%, PVT 3.8%, STB 2.5%
- Top losers: VNM -0.7%, HPG -0.4%, DNC -0.3%

🥇 Vàng
- Vàng SJC: 82.30 — 83.10 triệu đồng/lượng (tăng)

💵 Tỷ giá
- USD/VND: 25,235 (giảm nhẹ)
- Fed rate: 4.25%

**📌 Jarvis Hub — Thị trường Việt Nam**
**📅 23/09/2026 — 🕑 16:00 SGT**
**🔗 jarvis-hub:8100"""
    }
]

# Insert test data
cursor = conn.cursor()
for brief in test_briefs:
    cursor.execute(
        """INSERT INTO market_briefs (date, raw_json, formatted_output, source)
           VALUES (?, ?, ?, ?)""",
        (brief['date'], brief['raw_json'], brief['formatted_output'], brief['source'])
    )
    print(f"Inserted: {brief['date']} ({brief['source']})")

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM market_briefs").fetchone()[0]
print(f"\nDone. Total briefs in DB: {total}")
conn.close()
