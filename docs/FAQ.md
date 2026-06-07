# Jarvis Hub — FAQ & Troubleshooting

**Phiên bản:** v2.0 — *Cập nhật: 2026-05-22*

---

## 🔧 Sự cố thường gặp

### ❌ Dashboard không load được data

**Triệu chứng:** Open http://localhost:8100, thấy trang blank hoặc chỉ có loading spinner.

**Nguyên nhân & Giải pháp:**

1. **Server chưa chạy**:
```bash
# Check process
ps aux | grep python | grep app.py

# Restart nếu cần
kill $(lsof -t -i :8100) 2>/dev/null
cd ~/jarvis-hub && python app.py &
```

2. **Port 8100 bị chiếm bởi process khác**:
```bash
lsof -i :8100         # xem ai đang giữ port
lsof -t -i :8100 | xargs kill -9    # force kill
python app.py          # start lại
```

3. **Database chưa được init**: Server tự động tạo DB lần đầu tiên chạy. Nếu thấy lỗi, xóa `knowledge/jarvis.db` và chạy lại.

### ❌ Ollama connection failed

**Triệu chứng:** Analysis report bị empty, LLM report không sinh được.

**Kiểm tra:**
```bash
# Check Ollama server
curl http://localhost:11434/api/tags

# Start Ollama nếu chưa chạy
ollama serve &

# Kiểm tra model đã pull chưa
ollama list | grep qwen3.6
```

Nếu model chưa tồn tại:
```bash
ollama pull qwen3.6:35b-a3b-mxfp8
# Hoặc model nhẹ hơn nếu RAM hạn chế:
ollama pull qwen3.6:latest
# Sau đó sửa config.yaml cho đúng model name
```

### ❌ RSS feeds fetch fail (403 / timeout)

**Triệu chứng:** Articles list trống, sentiment không có.

**Nguyên nhân:** Một số RSS sources chặn request từ server IP hoặc cần User-Agent header.

**Giải pháp:**
1. Kiểm tra log output trong shell khi chạy `python app.py`
2. Mở rộng thêm source mới vào `config.yaml`:
```yaml
  sources:
    - name: "Báo Mới Kinh tế"     # Nguồn mới thay thế
      url: "https://bomoi.com/rss/kinh-te.rss"
      category: "vn-business"
      priority: 2
```

### ❌ Knowledge base search trả về "No results"

**Triệu chứng:** Search trong KB không tìm thấy term dù nghĩ là đã có.

**Nguyên nhân & Giải pháp:**

1. **KB chưa được seed**: Chạy `python seed_kb.py` từ terminal để populate entries cơ bản
2. **Term format khác**: KB dùng exact match trên term field — thử search với term gốc (vd "P/E ratio" thay vì "PE ratio")
3. **FTS index cần rebuild**: Nếu vừa update content trong DB:
```python
# Trong Python REPL:
from core.db import Database
db = Database()
db.rebuild_fts_index()  # rebuild full-text search index
```

### ❌ Dữ liệu analysis bị "outdate" (vấn đề issue #4)

**Triệu chứng:** Eval report, market evaluation hiển thị số liệu cũ (VD: giá cổ phiếu hôm qua nhưng báo cáo nói hôm nay).

**Nguyên nhân:** GET endpoint `market-evaluation` trước đây gọi luôn `generate_daily_evaluation()` mà không fetch data mới.

**Đã fix trong v2:**
- Now calls `_refresh_all_sources()` trước tiên — fetch parallel 7+ nguồn (VN-Index, USD/VND, BTC/ETH/SOL, Gold, DXY, Oil)
- Cache timestamp được refresh sau mỗi lần update
- `should_refresh()` check: tự động trigger refresh khi stale > 12h hoặc qua new day

**Kiểm tra data freshness:**
```bash
# Health endpoint trả về cache_age_seconds
curl -s http://localhost:8100/api/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Cache age: {d[\"cache_age_seconds\"]//60} minutes')"
```

> **Khuyến nghị:** Đánh giá thị trường nên chạy vào buổi sáng (sau 7:35) để có data market opening đầy đủ.

---

## ❓ Câu hỏi thường gặp (FAQ)

### Q: Jarvis Hub hoạt động offline được không?
**A:** Không hoàn toàn. Cần:
- **Ollama server running locally** cho LLM analysis, sentiment, keyword generation
- **Internet access** cho RSS feeds + Yahoo Finance data
- **SQLite DB local** — chỉ component chạy offline

### Q: Có thể thay model LLM mặc định được không?
**A:** Có. Sửa trong `config.yaml`:
```yaml
ollama:
  model: "llama3.2"    # đổi từ qwen3.6 sang llama3.2
```
Mẫu có sẵn: `ollama list`

### Q: DB file jarvis.db quá lớn phải làm sao?
**A:** File DB chỉ chứa knowledge base entries + activity log + watchlist — thường < 1MB. Nếu thấy > 50MB, có thể do FTS index cần optimize:
```bash
# Chạy VACUUM để compact DB
sqlite3 knowledge/jarvis.db "VACUUM;"
```

### Q: Có bao nhiêu RSS sources đang cấu hình?
**A:** Hiện tại có **8 sources**:

| Source | Category | Priority |
|--------|----------|----------|
| Cafef Doanh nghiệp | vn-stock | 1 (cao nhất) |
| VnExpress Kinh doanh | vn-business | 2 |
| VnExpress Kinh tế | vn-economy | 2 |
| Reuters Business | global-business | 3 |
| BBC Business | global-economy | 3 |
| TechCrunch | ai-tech | 3 |
| The Verge | ai-tech | 4 |
| Ars Technica AI | ai-tech | 4 (thấp nhất) |

### Q: LLM report mất ~30 second, có cách nào nhanh hơn?
**A:** Có ba cách:
1. **LLM Cache**: Cùng một symbol sẽ cache result — gọi lần 2 + gần như instant (<1s). Cache hoạt per full prompt hash (symbol + price data snapshot).
2. **Dùng model nhỏ hơn**: `qwen3.6:latest` thay vì `35b-a3b-mxfp8` (~9GB vs ~37GB RAM, nhanh hơn 3-4x)
3. **Set llm_rank > 0** trong enrich\_article() để skip Ollama sentiment analysis cho articles (giữ lại chỉ LLM report cho stock analysis)

### Q: Sentiment layer 1 và layer 2 khác nhau như thế nào?
**A:**
- **Layer 1**: Keyword-based scoring, chạy local cực nhanh. Dùng positive/negative/vietnamese sentiment keywords list. Chỉ ~50ms/article.
- **Layer 2**: Deep LLM analysis qua Ollama model. Chính xác hơn nhưng tốn ~2-5s/article.

Mặc định: Layer 1 luôn chạy, Layer 2 chỉ khi config cho phép (`llm_rank >= 0`).

### Q: Daily briefing được gửi ra Telegram chưa?
**A:** Chưa có module Telegram bot tích hợp hoàn chỉnh. Briefing hiện tại lưu vào DB + terminal output. 

Để push lên Telegram, setup Hermes Agent cron job:
```bash
# Hermes sẽ gọi jarvis briefing và gửi kết quả qua Telegram
jarvis cron job create \
   --prompt "Run jarvis briefing and send output to user" \
   --schedule "0 23 * * *"     # 6:18 AM GMT+7
```

Kết quả brief sẽ được auto-deliver về Telegram chat của user.

---

## 🔍 Debug Checklist

Khi gặp vấn đề, chạy thứ tự:

1. **Server alive?**
   ```bash
   curl -s http://localhost:8100/api/health | python3 -m json.tool
   ```

2. **Ollama running?**
   ```bash
   ollama list        # show available models
   curl localhost:11434/api/tags   # HTTP 200 = OK
   ```

3. **DB accessible?**
   ```bash
   sqlite3 knowledge/jarvis.db "SELECT count(*) FROM knowledge_base;"
   ```

4. **RSS sources reachable?**
   ```bash
   curl -sI https://cafef.vn/doanh-nghiep.rss | head -1    # HTTP 200 = OK
   ```

5. **Log recent activity?**
   ```bash
   jarvis log -l 30
   ```

6. **Test analysis endpoint direct?**
   ```bash
   curl -s "http://localhost:8100/api/analyze?symbol=VNM" | python3 -m json.tool | head -30
   ```

---

## 📊 Performance Tips

| Vấn đề | Giải pháp |
|--------|-----------|
| Dashboard load chậm | Cache đã tự động, nhưng server cần idle ~2 phút sau khởi động để fetch hết sources |
| Ollama consume nhiều RAM | Dùng model `qwen3.6:latest` (9GB) thay vì `35b-a3b-mxfp8` (37GB) |
| DB file phình to | Chạy `VACUUM` định kỳ mỗi tháng |
| RSS sources fail | Thay bằng những source CDN-friendly hơn như vnexpress, cafef |

---

*Cập nhật lần cuối: 2026-05-22*
