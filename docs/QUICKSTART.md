# Jarvis Hub — Quick Start Guide

**Jarvis Hub** là hệ sinh thái trí tuệ tài chính tự vận hành, tích hợp:
- RSS news aggregation + sentiment analysis (Ollama LLM)
- Phân tích chứng khoán / vàng / tiền điện tử
- Knowledge base (glossary tài chính tra cứu kiểu Investopedia)
- Flask web dashboard + CLI tool

---

## 🚀 1. Cài đặt

### Yêu cầu hệ thống
- Python 3.9+
- Ollama đã cài và chạy (`ollama serve` với model `qwen3.6:latest`)
- macOS / Linux

### Cài đặt dependencies

```bash
cd ~/jarvis-hub
pip install -r requirements.txt
```

Phụ thuộc tối thiểu: `flask`, `click`, `requests`, `feedparser`, `pyyaml`

---

## ⚙️ 2. Cấu hình

Tất cả config nằm trong file `config.yaml`:

```yaml
system:
  name: "Jarvis Hub"
  timezone: "Asia/Saigon"

telegram:
  target_chat_id: "1670013239"    # Chat ID nhận briefing

ollama:
  url: "http://localhost:11434"
  model: "qwen3.6:35b-a3b-mxfp8"  # Model LLM để phân tích

feed:                         # RSS nguồn tin
  sources:
    - name: "Cafef Doanh nghiệp"
      url: "https://cafef.vn/doanh-nghiep.rss"
      category: "vn-stock"
      priority: 1
    - name: "VnExpress Kinh doanh"
      url: "https://vnexpress.net/rss/kinh-doanh.rss"
      category: "vn-business"
      priority: 2
    # ... thêm nguồn ở đây

exchange_rates_source: "vietcombank"   # vietcombank | sacombank

schedule:
  morning_briefing: "06:18"   # Giờ GMT+7
  evening_briefing: "23:00"

db_path: "~/jarvis-hub/knowledge/jarvis.db"
daily_dir: "~/jarvis-hub/daily"
```

### Chỉnh sửa model Ollama

Nếu muốn đổi model khác (vd `llama3.2`):
```bash
# 1. Download model mới
ollama pull llama3.2

# 2. Sửa config.yaml
# ollama.model: "llama3.2"
```

---

## 📋 3. Chạy Jarvis Hub

### Cách 1: Web Dashboard (khuyên dùng)

```bash
cd ~/jarvis-hub
python app.py
```

Mở trình duyệt: **http://localhost:8100**

Dashboard bao gồm các tab:
- **📰 News Feed** — RSS news + sentiment (tích cực/tiêu cực/trung lập)
- **📈 Analysis** — Phân tích mã cổ phiếu / vàng / crypto (S/R, TA signals, buy/sell/hold)
- **💡 Knowledge Base** — Tra cứu thuật ngữ tài chính + AI generate definition
- **⏰ Daily Snapshots** — Lịch sử briefing hàng ngày
- **📊 Market Eval** — Đánh giá thị trường tổng quan
- **⭐ Watchlist** — Quản lý danh sách theo dõi

Dữ liệu tự động refresh:
- Khi cache bị stale (trên 12 giờ hoặc qua new day)
- Hoặc mỗi ngày lúc 07:30 AM

### Cách 2: CLI Tool

```bash
cd ~/jarvis-hub
python cli.py <command> [options]
# hoặc nếu đã pip install -e .
jarvis <command> [options]
```

Xem danh sách lệnh chi tiết ở `docs/COMMANDS.md`

---

## 📊 4. Workflow điển hình

### Buổi sáng (ngay sau khi mở máy)

1. Chạy briefing:  `jarvis briefing --type morning`
2. Web dashboard hiện tin tức + sentiment tự động
3. Kiểm tra watchlist: `jarvis watch list`

### Khi muốn phân tích một mã cổ phiếu

```bash
jarvis analyze VNM
# Hoặc trên web: tab 📈 → nhập "VNM" → Enter
```

Kết quả trả về:
- Price, Volume, Market Cap, P/E, EPS
- Technical indicators (SMA, RSI, MACD)
- **LLM-generated analysis** với recommendation Buy/Hold/Sell
- Support/Resistance levels
- Investment catalysts

### Tra cứu thuật ngữ tài chính

```bash
jarvis search "P/E ratio"
# Hoặc trên web: tab 💡 → nhập từ khóa → Search
```

Nếu KB chưa có, hệ thống tự generate definition qua Ollama.

---

## 🗓️ 5. Cron Jobs (tự động hóa)

Jarvis Hub không tự chạy cron — dùng `jarvis cron job create` trong Hermes Agent:

Example (morning briefing):
```bash
jarvis cron job create \
  --prompt "Run jarvis briefing" \
  --schedule "0 23 * * *" \   # 6:18 AM GMT+7 = 23:00 UTC
  --name jarvis-morning-briefing
```

### Các cron jobs nên có:
| Schedule | Command | Purpose |
|----------|---------|---------|
| `0 23 * * *` (6:18 AM) | `jarvis briefing --type morning` | Morning briefing đẩy lên Telegram |
| `36 16 * * *` (5:00 PM) | `jarvis briefing --type evening` | Evening briefing tổng kết ngày |

---

## 🔧 6. Troubleshooting nhanh

| Vấn đề | Giải pháp |
|--------|----------|
| Dashboard không load data | Chạy `jarvis doctor` để check Ollama + DB status |
| Analysis chậm ( >30s) | Kiểm tra Ollama model size, model đang chạy hoặc không |
| RSS fetch lỗi 403 | Một số nguồn cần User-Agent. Sửa trong `core/news.py` |
| Knowledge base search trả về empty | Chưa có entry nào, dùng generate mode: thêm `?generate=true` vào URL |
| Port 8100 bị chiếm | `lsof -t -i :8100 \| xargs kill -9` rồi chạy lại |

---

## 📁 7. Cấu trúc thư mục

```
jarvis-hub/
├── app.py              # Flask web dashboard (main server)
├── cli.py              # CLI tool (Click-based commands)
├── config.yaml         # Configuration file
├── seed_kb.py          # Seed knowledge base entries
├── requirements.txt    # Python dependencies
├── core/               # Core engine package
│   ├── __init__.py
│   ├── config.py       # Config loader
│   ├── db.py           # SQLite database (knowledge, logs, watchlist)
│   ├── news.py         # RSS fetching + sentiment analysis
│   ├── market.py       # Stock/Gold/Crypto analysis + TA calculation
│   └── llm_cache.py    # LLM response cache decorator
├── dashboard/
│   ├── templates/
│   │   └── index.html  # Web UI (HTML + JavaScript)
│   └── static/          # Static assets (CSS, JS)
├── knowledge/
│   └── jarvis.db        # SQLite database
├── scripts/             # Helper scripts
│   ├── seed_kb.py       # Initial KB seeding
│   └── enrich_kb.py     # Enrich existing KB entries
├── docs/                # Documentation (bạn đang đọc)
│   ├── QUICKSTART.md    # ← This file
│   ├── ARCHITECTURE.md  # System architecture deep-dive
│   ├── COMMANDS.md      # CLI commands reference
│   └── FAQ.md           # Troubleshooting & FAQ
├── daily/               # Daily briefing snapshots (auto-created)
├── tests/               # Test suite
└── .learnings/          # Error logs & learnings
```

---

## 📚 Tài liệu chi tiết

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Kiến trúc, flow data, API endpoints
- **[COMMANDS.md](COMMANDS.md)** — Liệt kê đầy đủ CLI commands + options
- **[FAQ.md](FAQ.md)** — Troubleshooting các trường hợp thường gặp

---

*Cập nhật lần cuối: 2026-05-22*
