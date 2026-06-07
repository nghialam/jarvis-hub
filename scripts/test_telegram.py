#!/usr/bin/env python3
"""Diagnose Telegram HTTP 400 from run_brief_final.py"""
import json, os, sys, urllib.request, urllib.error

# Load token like run_brief does
def _load_token():
    for k in ("JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.environ.get(k, "")
        if v: return v.strip()
    try:
        p = os.path.expanduser("~/.hermes/.jarvis_token_cache")
        with open(p) as f: t = f.read().strip()
        return t
    except Exception: pass
    return ""

TG_BOT_TOKEN = _load_token()
TG_CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "-1003801745265")
bot_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

# Build the same content run_brief_final.py would generate
sep = "=" * 50
header = "Jarvis Intelligence Brief | 31/05/2026 | Sun\n" + sep
sections = {
    "NEWS": ("Top 4 AI headlines:\n\n1. The Verge reported PAST Maps founder walked away from billions in AI hype to build analog mapping platform, showing retreat from tech overconfidence.\n\n2. BBC News warned 'AI grifters' using synthetic Black people to sell products - highlighting ethical risks of LLM image generation.\n\n3. Bloomberg markets data shows Fed policy uncertainty continuing to pressure global liquidity conditions.\n\n4. CafeF/Vietnamnet reported Vietnamese market facing regulatory tightening on listed firms.",
              "[Top 4 AI/tech items with title, why it matters [Source link], then brief coverage of other notable finance/economy/news.]"),
    "TREND": ("Dominant narratives:\n\n1. AI Hype Fatigue: Founder rejection of billion-dollar AI bets signals market skepticism about ROI on pure AI plays, traditional web still competitive.\n\n2. Synthetic Media Abuse Scaling: Shein example shows problem going mainstream from niche to enterprise - regulatory frameworks lagging.\n\n3. Vietnam Market Consolidation: Multiple sources point to regulatory enforcement accelerating in VN markets, likely leading to firm delistings/mergers over next 6-12 months.\n\n4. General Sentiment Cautious: Global macro headwinds persist; VN market showing resilience but with structural risks from tighter regulation.",
              "[Top 4 dominant narratives of the news period, AI super-cycle assessment with evidence, market sentiment per sector.]"),
    "RECS": ("Three actions for today:\n\n1. AI Tool Stack Update: Shift to Claude Opus/MAX family for code generation (better reasoning) + o3-mini for structured output tasks. Replace GPT-4o in automated pipelines.\n\n2. Workflow Automation: Implement RAG-based knowledge base using Qdrant + Ollama qwen3.6 for local-first analysis - reduces API cost 70%+ while maintaining quality.\n\n3. Portfolio Monitor: Deploy lightweight ticker tracker using Python + cron job pulling Yahoo Finance data into SQLite dashboard.",
              "[2-3 specific actions for work/life optimization using new AI tools with concrete tool names, prompt examples, workflow steps.]"),
    "TECH": ("Prototype: Local Trading Journal RAG (Rapid-Aid Generator)\n\nStack: Ollama(qwen3.6) + LangChain + SQLite + simple web dashboard\n\nArchitecture:\n- Input CSV/PDF of trading data -> LangChain pipeline -> store in SQLite with embeddings\n- Query API returns LLM analysis of past trades, patterns detection\n- Flask dashboard showing trade visualization + AI insights\n\nWeek 1 milestones:\nM1: Data ingestion script (CSV to SQLite with trade_metadata table)\nM2: Embedding pipeline using sentence-transformers + FAISS or SQLite FTS5\n- M3: REST API returning trade analysis via /api/analyze endpoint\n- M4: Dashboard showing trade history + trend lines",
              "[Project name and description (why now), tech stack using available tools, architecture 3-5 bullets, Week 1 milestones.]")
}

full_brief = header + "\n"
for k, v in sections.items():
    full_brief += f"\n--- {k} ---\n{v[0]}\n\n{v[1]}\n"

print(f"Total brief length: {len(full_brief)} chars")

# Test flat split (current approach - FAILS)
print("\n=== TEST 1: FLAT SPLIT at 4096 (CURRENT) ===")
flat_parts = [full_brief[i:i+4096] for i in range(0, len(full_brief), 4096)]
for i, chunk in enumerate(flat_parts):
    payload = json.dumps({"chat_id": TG_CHAT_ID, "text": chunk, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"{bot_url}/sendMessage", data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        r2 = json.loads(resp.read())
        print(f"  Chunk {i}: OK (json={len(payload)} bytes, text={len(chunk)} chars)")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        # Extract Telegram error details from body if present
        try:
            err_obj = json.loads(body)
            tg_err = err_obj.get("description", body)
        except:
            tg_err = body
        print(f"  Chunk {i}: FAILED [{e.code}] json={len(payload)} text={len(chunk)} -> {tg_err}")

# Test paragraph-safe split (fixed approach)
print("\n=== TEST 2: PARAGRAPH SPLIT at 3800 (FIXED) ===")
paragraphs = [p for p in full_brief.split('\n\n') if p.strip()]
chunks = []
for para in paragraphs:
    test = "\n\n".join(chunks + [para]) if chunks else para
    json_len = len(json.dumps({"chat_id": TG_CHAT_ID, "text": test}))
    if json_len <= 3800 and len(test) < 3800:
        chunks.append(para)
    elif chunks:
        # Try putting in last chunk
        last = chunks[-1]
        combined = last + "\n\n" + para
        json_len2 = len(json.dumps({"chat_id": TG_CHAT_ID, "text": combined}))
        if json_len2 <= 3800 and len(combined) < 3800:
            chunks[-1] = combined
        else:
            chunks.append(para)
    else:
        chunks.append(para[:3500])

for i, chunk in enumerate(chunks):
    # Strip control chars that Telegram chokes on
    cleaned = ''.join(c for c in chunk if ord(c) > 127 or c in '\n\r\t')
    cleaned = ''.join(c for c in cleaned if ord(c) >= 32 or c in '\n\r\t')
    
    payload = json.dumps({"chat_id": TG_CHAT_ID, "text": cleaned, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"{bot_url}/sendMessage", data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        r2 = json.loads(resp.read())
        mid = r2.get('result', {}).get('message_id', '?')
        print(f"  Chunk {i}: OK -> msg_id={mid} (json={len(payload)} bytes, text={len(cleaned)} chars)")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            err_obj = json.loads(body)
            tg_err = err_obj.get("description", body)
        except:
            tg_err = body
        print(f"  Chunk {i}: FAILED [{e.code}] json={len(payload)} text={len(cleaned)} -> {tg_err}")

# Debug: check for problematic chars in full_brief
print("\n=== DEBUG: Content Analysis ===")
bad = [(i, c, hex(ord(c))) for i, c in enumerate(full_brief) if ord(c) < 32 and c not in '\n\r\t']
if bad:
    print(f"Found {len(bad)} control chars:")
    for idx, char, h in bad[:10]:
        context = full_brief[max(0,idx-5):idx+6].replace('\n', '\\n')
        print(f"  pos {idx}: {h} (context: ...{context}...)")
else:
    print("   No control characters found - content should be clean for JSON/Telegram")

# Check for zero-width chars, BOM, etc.
import unicodedata
zero_width = [(i, c, unicodedata.name(c, '?')) for i, c in enumerate(full_brief) if unicodedata.category(c).startswith('Cf')]
if zero_width:
    print(f"Found {len(zero_width)} zero-width/formatting chars:")
    for idx, ch, name in zero_width[:5]:
        print(f"  pos {idx}: U+{ord(ch):04X} ({name})")

print("\nDiagnostic complete.")
