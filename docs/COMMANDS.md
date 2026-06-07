# Jarvis Hub — CLI Commands Reference

**Phiên bản:** v2.0 — *Cập nhật: 2026-05-22*

---

## 🔑 Chạy cơ bản

```bash
cd ~/jarvis-hub
python cli.py <command> [options]
# hoặc nếu đã pip install -e . trong project:
jarvis <command> [options]
```

---

## 📰 1. `jarvis briefing`

Chạy daily briefing news summary + sentiment analysis. Lưu snapshot vào DB.

```bash
jarvis briefing
jarvis briefing --type morning
jarvis briefing --type evening
```

**Output:**
- Số lượng articles đã fetch từ RSS
- Sentiment breakdown (tích cực / tiêu cực / trung lập)
- VN-Index + global indices snapshot
- Tỷ giá USD/VND
- Briefing text được lưu vào `daily/YYYY-MM-DD.md`

**Cron job example (Hermes Agent):**
```bash
jarvis cron job create \
  --prompt "Run jarvis briefing" \
  --schedule "0 23 * * *" \    # 6:18 AM GMT+7
  --name jarvis-morning-briefing
```

---

## 📈 2. `jarvis analyze`

Phân tích một mã cổ phiếu / vàng / crypto.

```bash
jarvis analyze VNM
jarvis analyze FRT
jarvis analyze BTC
jarvis analyze ETH
jarvis analyze SOL
jarvis analyze XAUUSD
```

**Output:**
- Price, Change %, Volume, Market Cap
- P/E, EPS (nếu có)
- Technical Indicators: SMA\_20/50, RSI\_14, MACD histogram
- **LLM Report**: phân tích chi tiết bởi Ollama bao gồm:
  - Xu hướng ngắn/trung/dài hạn
  - Support & Resistance levels (S1-S3, R1-R3)
  - Technical signals (MACD cross, RSI zone)
  - Recommendation: MUA / HOLD / BÁN + confidence %
  - Investment catalysts (cả bullish và bearish)

**Lưu ý:**
- Cache LLM response — lần sau gọi cùng symbol sẽ nhanh hơn (không gọi Ollama nữa)
- Nếu chưa có Ollama report, hệ thống tự tạo qua API call (~15-30s)

---

## ⭐ 3. `jarvis watch`

Quản lý danh sách theo dõi (watchlist).

### Thêm symbol vào watchlist

```bash
jarvis watch add VNM
jarvis watch add VNM -n "Vinamilex"    # kèm custom name
```

Hệ thống tự fetch tên từ Yahoo Finance nếu không cung cấp `--name`.

### Xem watchlist

```bash
jarvis watch list
```

Hiển thị: tên mã, giá hiện tại, % thay đổi cho từng symbol.

### Xóa khỏi watchlist

```bash
jarvis watch remove VNM
```

---

## 🔍 4. `jarvis search`

Tra cứu knowledge base (glossary thuật ngữ tài chính).

```bash
jarvis search "P/E ratio"
jarvis search RSI
jarvis search Bollinger bands
```

**Output:**
- Hiển thị các results có term gần nhất với query
- Tags, snippet content, score matching

**Generate mode (khi KB chưa có entry):**
Nếu không có kết quả từ search, hệ thống tự generate definition bằng LLM và hỏi có lưu vào KB hay không.

---

## 🧠 5. `jarvis quiz`

Chế độ flashcard spaced repetition:
```bash
jarvis quiz
```

- Randomly selects 5 terms from knowledge base
- Shows hint (content snippet first 150 chars)
- User can guess or press Enter to see answer
- Rates recall: "rt_tot" (rất tốt) | "kha" (khá) | "can_hoc_lai" (cần học lại)

---

## 📋 6. `jarvis log`

Xem activity logs hệ thống:
```bash
jarvis log                    # default: last 20 entries
jarvis log -l 50             # last 50 entries
jarvis log --last 100        # also works (same as -l)
```

Hiển thị: timestamp, command, args, status (✅/⚠️/❌), summary, execution time.

---

## 📊 7. `jarvis history`

So sánh hai daily briefing snapshots:
```bash
jarvis history                # show available dates only
jarvis history 2026-05-20 2026-05-21    # diff hai ngày
```

Output là line-by-line diff giữa hai briefing, highlight những thay đổi.

---

## 🏥 8. `jarvis doctor`

Health check toàn bộ hệ thống:
```bash
jarvis doctor
```

Kiểm tra:
- ✅ Config file loading
- ✅ Ollama endpoint + available models
- ✅ Database connectivity
- ✅ DB size on disk (JARVIS KB entries count)
- ✅ RSS sources reachability

---

## 📊 9. Các lệnh không có trong CLI nhưng qua Web Dashboard

Một số chức năng chỉ có trên web dashboard tại **http://localhost:8100**:

| Tab | Tính năng |
|-----|-----------|
| 📰 News Feed | RSS articles + sentiment (tích cực/tiêu cực/trung lập) |
| 📈 Analysis | Input symbol → analysis report giống CLI |
| 💡 Knowledge Base | Tra cứu thuật ngữ + AI generate definition |
| ⏰ Daily Snapshots | Lịch sử briefing từng ngày, click xem full content |
| 📊 Market Evaluation | Đánh giá thị trường tổng quan (fresh data) |
| ⭐ Watchlist | Quản lý watchlist từ UI |

---

## ⚙️ Cấu hình tham số (`config.yaml`)

Mọi tham số đều chỉnh trong file `~/jarvis-hub/config.yaml`:

```yaml
ollama:
  url: "http://localhost:11434"    # Ollama endpoint
  model: "qwen3.6:35b-a3b-mxfp8"  # Model dùng cho phân tích

feed:
  sources:                         # Danh sách RSS sources
     - name: "Cafef Doanh nghiệp"
       url: "..."
       category: "vn-stock"
       priority: 1                  # Số thấp = ưu tiên cao

exchange_rates_source: "vietcombank"  # vietcombank | sacombank

schedule:
  morning_briefing: "06:18"    # Giờ GMT+7 cho automated briefing
  evening_briefing: "23:00"
```

---

*Cập nhật lần cuối: 2026-05-22*
