# Jarvis Hub — FAQ & Troubleshooting

**Version:** v2.0 — *Updated: 2026-05-22*

---

## 🔧 Common Issues

### ❌ Dashboard fails to load data

**Symptom:** Open http://localhost:8100, see a blank page or only a loading spinner.

**Causes & Solutions:**

1. **Server not running:**
```bash
# Check process
ps aux | grep python | grep app.py

# Restart if needed
kill $(lsof -t -i :8100) 2>/dev/null
cd ~/jarvis-hub && python app.py &
```

2. **Port 8100 occupied by another process:**
```bash
lsof -i :8100         # see who is holding the port
lsof -t -i :8100 | xargs kill -9    # force kill
python app.py          # start again
```

3. **Database not initialized:** The server auto-creates the DB on first run. If you see errors, delete `knowledge/jarvis.db` and run again.

### ❌ Ollama connection failed

**Symptom:** Analysis report is empty, LLM report not generated.

**Check:**
```bash
# Check Ollama server
curl http://localhost:11434/api/tags

# Start Ollama if not running
ollama serve &

# Check if model is pulled
ollama list | grep qwen3.6
```

If model does not exist:
```bash
ollama pull qwen3.6:35b-a3b-mxfp8
# Or a lighter model if RAM is limited:
ollama pull qwen3.6:latest
# Then update config.yaml with the correct model name
```

### ❌ RSS feeds fetch fail (403 / timeout)

**Symptom:** Articles list is empty, no sentiment data.

**Cause:** Some RSS sources block requests from server IPs or require a User-Agent header.

**Solution:**
1. Check log output in the shell when running `python app.py`
2. Add new sources to `config.yaml`:
```yaml
  sources:
    - name: "Bao Moi Economics"     # New replacement source
      url: "https://bomoi.com/rss/kinh-te.rss"
      category: "vn-business"
      priority: 2
```

### ❌ Knowledge base search returns "No results"

**Symptom:** Search in KB does not find the term even though you think it exists.

**Causes & Solutions:**

1. **KB not seeded:** Run `python seed_kb.py` from the terminal to populate basic entries
2. **Term format mismatch:** KB uses exact match on the term field — try searching with the original term (e.g., "P/E ratio" instead of "PE ratio")
3. **FTS index needs rebuild:** If you recently updated content in the DB:
```python
# In Python REPL:
from core.db import Database
db = Database()
db.rebuild_fts_index()  # rebuild full-text search index
```

### ❌ Analysis data is "outdated" (issue #4)

**Symptom:** Eval report, market evaluation shows old data (e.g., yesterday's stock price but the report says today).

**Cause:** The `market-evaluation` GET endpoint previously always called `generate_daily_evaluation()` without fetching fresh data.

**Fixed in v2:**
- Now calls `_refresh_all_sources()` first — parallel fetches 7+ sources (VN-Index, USD/VND, BTC/ETH/SOL, Gold, DXY, Oil)
- Cache timestamp refreshed after each update
- `should_refresh()` check: auto-triggers refresh when stale > 12h or on a new day

**Check data freshness:**
```bash
# Health endpoint returns cache_age_seconds
curl -s http://localhost:8100/api/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Cache age: {d[\"cache_age_seconds\"]//60} minutes')"
```

> **Recommendation:** Market evaluation should run in the morning (after 7:35) to have full market opening data.

---

## ❓ Frequently Asked Questions (FAQ)

### Q: Can Jarvis Hub work offline?
**A:** Not completely. It requires:
- **Ollama server running locally** for LLM analysis, sentiment, keyword generation
- **Internet access** for RSS feeds + Yahoo Finance data
- **SQLite DB local** — the only component that runs offline

### Q: Can I change the default LLM model?
**A:** Yes. Edit in `config.yaml`:
```yaml
ollama:
  model: "llama3.2"    # change from qwen3.6 to llama3.2
```
Available models: `ollama list`

### Q: DB file jarvis.db is too large, what should I do?
**A:** The DB file only contains knowledge base entries + activity log + watchlist — usually < 1MB. If you see > 50MB, the FTS index may need optimization:
```bash
# Run VACUUM to compact the DB
sqlite3 knowledge/jarvis.db "VACUUM;"
```

### Q: How many RSS sources are configured?
**A:** Currently **8 sources**:

- **Cafef Business** | vn-stock | 1 (highest)
- **VnExpress Business** | vn-business | 2
- **VnExpress Economy** | vn-economy | 2
- **Reuters Business** | global-business | 3
- **BBC Business** | global-economy | 3
- **TechCrunch** | ai-tech | 3
- **The Verge** | ai-tech | 4
- **Ars Technica AI** | ai-tech | 4 (lowest)

### Q: LLM report takes ~30 seconds, is there a faster way?
**A:** Three options:
1. **LLM Cache:** Same symbol caches the result — 2nd call is nearly instant (<1s). Cache works per full prompt hash (symbol + price data snapshot).
2. **Use a smaller model:** `qwen3.6:latest` instead of `35b-a3b-mxfp8` (~9GB vs ~37GB RAM, 3-4x faster)
3. **Set llm_rank > 0** in `enrich_article()` to skip Ollama sentiment analysis for articles (keep LLM report only for stock analysis)

### Q: What's the difference between sentiment layer 1 and layer 2?
**A:**
- **Layer 1:** Keyword-based scoring, runs locally very fast. Uses positive/negative/Vietnamese sentiment keyword lists. Only ~50ms/article.
- **Layer 2:** Deep LLM analysis via Ollama model. More accurate but takes ~2-5s/article.

Default: Layer 1 always runs, Layer 2 only when config allows (`llm_rank >= 0`).

### Q: Is the daily briefing sent to Telegram yet?
**A:** No fully integrated Telegram bot module yet. Briefings are currently saved to DB + terminal output.

To push to Telegram, set up a Hermes Agent cron job:
```bash
# Hermes will call jarvis briefing and send results via Telegram
jarvis cron job create \
   --prompt "Run jarvis briefing and send output to user" \
   --schedule "0 23 * * *"     # 6:18 AM GMT+7
```

Brief results will be auto-delivered to the user's Telegram chat.

---

## 🔍 Debug Checklist

When encountering issues, run in order:

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

6. **Test analysis endpoint directly?**
   ```bash
   curl -s "http://localhost:8100/api/analyze?symbol=VNM" | python3 -m json.tool | head -30
   ```

---

## 📊 Performance Tips

- **Dashboard loads slowly** — Cache is automatic, but the server needs ~2 minutes idle after startup to fetch all sources
- **Ollama consumes too much RAM** — Use `qwen3.6:latest` (9GB) instead of `35b-a3b-mxfp8` (37GB)
- **DB file bloated** — Run `VACUUM` periodically every month
- **RSS sources failing** — Switch to CDN-friendly sources like vnexpress, cafef

---

*Last updated: 2026-05-22*
