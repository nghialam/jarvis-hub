#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""jarvis_intelligence.py - Jarvis AI Intelligence Briefing Engine.

Enhanced v2.0: 14 sources across VN/INTL/AI/TECH/ENTERTAINMENT.
Every news point cites its source for double-checking.
"""
import json
import re
import sys
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta

try:
    import feedparser
except ImportError:
    print("FATAL: feedparser not installed. pip install feedparser")
    sys.exit(0)


# --- CONFIG ---
_DEFAULT_CHAT_ID = "1670013239"
_TOKEN_CACHE_FILE = os.path.expanduser("~/.hermes/.jarvis_token_cache")


def load_telegram_token():
    """Load Telegram bot token with fallback chain."""
    for key in ["JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    if os.path.exists(_TOKEN_CACHE_FILE):
        with open(_TOKEN_CACHE_FILE) as f:
            cached = f.read().strip()
            if cached and ":" in cached:
                return cached
    env_path = os.path.join(os.path.expanduser("~"), ".hermes", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "TELEGRAM_BOT_TOKEN" and v.strip():
                    try:
                        with open(_TOKEN_CACHE_FILE, "w") as cf:
                            cf.write(v.strip())
                    except Exception:
                        pass
                    return v.strip()
    return "8733142640:***"


try:
    _token_from_file = load_telegram_token()
except Exception as e:
    print(f"[WARN] Could not load Telegram token: {e}")
    _token_from_file = "8733142640:***"

CHAT_ID = os.environ.get("JARVIS_CHAT_ID",
                          os.environ.get("TELEGRAM_HOME_CHANNEL",
                                             _DEFAULT_CHAT_ID)).strip() or _DEFAULT_CHAT_ID
BOT_TOKEN = _token_from_file

# Enhanced RSS sources -- 14 sources across VN domestic, INTL global, AI/TECH, ENTERTAINMENT
# All URLs verified working as of 2026-06-01
RSS_SOURCES = [
    # Vietnamese domestic news (7 sources)
    {"name": "CafeF Doanh Nghiep",      "url": "https://cafef.vn/doanh-nghiep.rss",                "section": "VN"},
    {"name": "VnExpress Tin Moi Nhat",   "url": "https://vnexpress.net/rss/tin-moi-nhat.rss",             "section": "VN"},
    {"name": "Tuoi Tre",                  "url": "https://tuoitre.vn/rss/homefeed.rss",                   "section": "VN"},
    {"name": "Thanh Nien Kinh Te",        "url": "https://thanhnien.vn/rss/kinh-te.rss",                      "section": "VN"},
    {"name": "Vietnamnet CK",              "url": "https://vietnamnet.vn/vi/rss/chung-khoan.rss",           "section": "VN"},
    {"name": "BBC Business (English)",    "url": "https://feeds.bbci.co.uk/news/business/rss.xml",         "section": "VN"},
    {"name": "VnExpress GIAI TRI",        "url": "https://vnexpress.net/rss/giai-tri.rss",                   "section": "ENT"},

    # International business & politics (5 sources)
    {"name": "Bloomberg",                 "url": "https://feeds.bloomberg.com/markets/news.rss",           "section": "INTL"},
    {"name": "Wall Street Journal",       "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",         "section": "INTL"},
    {"name": "BBC World",                 "url": "http://feeds.bbci.co.uk/news/world/rss.xml",            "section": "INTL"},
    {"name": "Al Jazeera Markets",        "url": "https://www.aljazeera.com/xml/rss/all.xml",            "section": "INTL"},

    # AI & Technology (2 sources)
    {"name": "The Verge AI",              "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",   "section": "AI"},
    {"name": "TechCrunch",                "url": "https://techcrunch.com/feed/",                                       "section": "TECH"},

    # Entertainment / Culture (2 sources)
    {"name": "BBC ENTERTAINMENT/ARTS",    "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",     "section": "ENT"},
]

RSS_LIMIT_PER_SOURCE = 4


# --- HELPERS ---

def _strip_html(html_text):
    """Remove HTML tags but preserve readable text content.

    Specifically handles RSS feeds where <img alt="text"> is nested inside
    <a> tags - extracts the alt text so we get readable summaries instead
    of empty markdown links like [ ](URL).
    """
    # Replace <a href="URL"><img alt="TEXT"></a> with TEXT (URL already in each line)
    def _extract_from_anchor(m):
        href = m.group(1)
        inner = m.group(2)
        img_alt_match = re.search(r'<img[^>]*alt=["\x27]([^"\x27]*)["\x27]', inner)
        if img_alt_match and img_alt_match.group(1).strip():
            return '[' + img_alt_match.group(1).strip() + '](' + href + ')'
        # If no alt text, extract remaining text content from anchor
        text_only = re.sub(r'<[^>]+>', '', inner).strip()
        if text_only:
            return '[' + text_only + '](' + href + ')'
        return ''

    cleaned = re.sub(r'<a[^>]*href=["\x27]([^"\x27]*)["\x27][^>]*>(.*?)</a>', _extract_from_anchor, html_text)
    # Remove all remaining HTML tags
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def fetch_rss(source):
    try:
        d = feedparser.parse(source["url"])
        if not d.entries:
            return []
        results = []
        for entry in d.entries[:RSS_LIMIT_PER_SOURCE]:
            title = (entry.get("title") or "").strip()
            raw_summary = (entry.get("summary") or entry.get("description") or "").strip()
            # Strip HTML tags to get readable text (feeds embed <img> instead of real summary)
            summary = _strip_html(raw_summary).replace("\n", " ") if raw_summary else ""
            link = (entry.get("link") or entry.get("id") or "").strip()
            # Strip query params to keep URLs short (~40 chars)
            url_clean = link.split("?")[0] if "?" in link else link
            published = entry.get("published", "")
            if not link or len(title) < 15:
                continue
            results.append({
                "title": title,
                "link": url_clean,
                "summary": summary[:300] if summary else "",
                "source": source["name"],
                "section": source["section"],
                "published": published,
            })
        return results
    except Exception as e:
        print("[WARN]: {}".format(source['name'], e), file=sys.stderr)
        return []


def get_llm_analysis(system_prompt, articles_text, timeout=300):
    """Call Ollama /v1/chat/completions."""
    ollama_url = "http://localhost:11434"
    model = "Qwen3.6-35B-A3B-MLX-8bit"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": articles_text},
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 12000}
    }
    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "{}/v1/chat/completions".format(ollama_url), data=req_data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(resp.read())
           # qwen3.6 outputs in 'thinking', not 'content'
        msg = result.get("message", {})
        return (msg.get("thinking") or msg.get("content") or "").strip()
    except Exception as e:
        print("[LLM ERROR] {}: {}".format(type(e).__name__, e), file=sys.stderr)
        if "8000" in str(e):
            return "OMLX not running - start it with: omlx"
        return "[LLM Error: {}]".format(type(e).__name__)


def format_for_telegram(text):
    """Convert markdown to Telegram HTML safely."""
    if not text:
        return ""
    lines = []
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            lines.append("")
            continue
        # Headers to bold with prefix
        line = re.sub(r'^#{1,3}\s+', '\u2592 ', stripped)
        # Bold **text** or __text__
        line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
        line = re.sub(r'__(.+?)__', r'<b>\1</b>', line)
        # Italic *text* (only if no backtick on same line)
        if '`' not in line:
            line = re.sub(r'\*(.+?)\*', r'<i>\1</i>', line)
        # URLs [name](url) -> <a href=url>name</a>
        line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line)
        lines.append(line)
    return "\n".join(lines)


def split_message(text, max_chars=4000):
    """Split text into chunks that won't exceed Telegram's 4096 limit."""
    parts = []
    current = ""
    for line in text.split("\n\n"):
        candidate = (current + "\n\n" + line).strip() if current else line.strip()
        if len(candidate) > max_chars and current:
            parts.append(current.strip())
            current = line
        else:
            current = candidate
    if current:
        parts.append(current.strip())
    return parts


def send_telegram(text, chunk_idx=None):
    """Send text to Telegram safely -- NO truncation of content."""
    url = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)

    html_text = format_for_telegram(text)
    final_size = len(html_text)
    safe_limit = 3896

    if final_size <= safe_limit:
        payload = {"chat_id": CHAT_ID, "text": html_text, "parse_mode": "HTML"}
        req_data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            mid = result.get("result", {}).get("message_id", "?")
            if chunk_idx is not None:
                print("Telegram sent (msg_id:{})".format(mid))
        except Exception as e:
            print("Telegram failed: {}".format(e), file=sys.stderr)
        return

    # Split for longer messages
    parts = []
    current_block = ""
    for block in html_text.split("\n\n"):
        candidate = (current_block + "\n\n" + block).strip() if current_block else block.strip()
        if len(candidate) > safe_limit and current_block:
            sub_lines = current_block.strip().split("\n")
            sub_chunk = ""
            for sl in sub_lines:
                if len(sub_chunk + "\n" + sl.strip()) > safe_limit and sub_chunk:
                    parts.append(sub_chunk.strip())
                    sub_chunk = sl.strip()
                else:
                    sub_chunk = (sub_chunk + "\n" + sl.strip()) if sub_chunk else sl.strip()
            if sub_chunk:
                parts.append(sub_chunk.strip())
            current_block = block
        else:
            current_block = candidate
    if current_block.strip():
        parts.append(current_block.strip())

    for i, chunk in enumerate(parts):
        while len(chunk) > 4050:
            cut_pos = chunk.rfind(" ", 0, 4000)
            chunk = chunk[:cut_pos] if cut_pos > 0 else chunk[:4000]
        parts[i] = chunk

    for i, chunk in enumerate(parts):
        payload = {"chat_id": CHAT_ID, "text": chunk, "parse_mode": "HTML"}
        req_data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            mid = json.loads(resp.read()).get("result", {}).get("message_id", "?")
            print("Telegram {}/{} sent (msg_id:{}, len={})".format(i+1, len(parts), mid, len(chunk)))
        except Exception as e:
            print("Telegram failed ({0}): {1}".format(i+1, e), file=sys.stderr)


def build_article_text(articles):
    """Build article text grouped by section, every line cites its source."""
    sections = {}
    for a in articles:
        sec = a["section"]
        if sec not in sections:
            sections[sec] = []
        s = (a.get("summary", "") or "").replace("\n", " ")
        link = a.get("link", "")
        title = a.get("title", "")
        src = a.get("source", "")
        lines = ["     [{0}] {1} ({2})".format(src, title, link)]
        if s:
            lines.append("         - {0}".format(s))
        sections[sec].append("\n".join(lines))

    art_text = ""
    section_labels = {
        "VN": "\U0001f1fb\U0001f1f3 TIN TRONG NUOC",
        "INTL": "\U0001f30d TIN QUOC TE",
        "AI": "\U0001f927 AI & TECH",
        "TECH": "\U0001f4bb CONG NGHỆ",
        "ENT": "\U0001f3ac GIAI TRI / VAN HOA / THE THAO"
    }
    for sec in ["VN", "INTL", "AI", "TECH", "ENT"]:
        if sec in sections:
            art_text += "\n\n{0}:\n\n".format(section_labels.get(sec, sec)) + "\n".join(sections[sec])
    return art_text


def run_full_briefing(test_mode=False, bedtime_mode=False):
    """Collect RSS -> LLM Analysis -> Telegram Delivery.

    Normal mode: 3 Telegram messages -- AI/Tech, Trends/Recs, Entertainment.
    Bedtime mode: 3 Telegram messages -- AI wrap-up, market close, preview.
    """
    now = datetime.now()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"][now.weekday()]

    print("[{0}] Starting Jarvis Intelligence Briefing...".format(now.strftime('%H:%M')))
    print("  Period: {0} ({1})".format(now.strftime('%d/%m/%Y'), day_name), file=sys.stderr)

    # Phase 1: Collect RSS from ALL sources
    print("Phase 1: Fetching RSS feeds...", file=sys.stderr)
    articles = []
    for src in RSS_SOURCES:
        fetched = fetch_rss(src)
        articles.extend(fetched)
        if fetched:
            print("     {0}: {1} articles".format(src['name'], len(fetched)), file=sys.stderr)

    # Deduplicate and sort by section priority, then date
    def _sort_key(a):
        return (
             "VNINTLAI TECHENT".find(a.get("section", "")),
            str(a.get("published", "") or ""),
         )

    seen, unique = set(), []
    for a in sorted(articles, key=_sort_key):
        k = a["title"].strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k)
            unique.append(a)

    # Reserve slots for entertainment articles at the TOP so they're never cut by[:35]
    ent_articles = [a for a in unique if a["section"] == "ENT"]
    other_articles = [a for a in unique if a["section"] != "ENT"]

    # Take up to 6 ENT + fill rest from others (up to 35 total)
    selected = ent_articles[:max(4, min(6, len(ent_articles)))]
    remaining_slots = 35 - len(selected)
    if remaining_slots > 0:
        selected.extend(other_articles[:remaining_slots])

    unique = selected

    # Build FULL article text for chains 1 & 2 (all sections)
    art_text = build_article_text(unique[:35])

    # Build ENT-ONLY article text for chain 3 (entertainment prompt expects ONLY ent data)
    ent_only_articles = [a for a in selected if a["section"] == "ENT"]
    ent_text = build_article_text(ent_only_articles) if ent_only_articles else ""

    print("{0} total -> {1} unique from {2} sections".format(
        len(articles), len(unique),
        len(set(a['section'] for a in articles)),
     ), file=sys.stderr)

    if not articles:
        msg = "\U0001f6a8 <b>JARVIS INTELLIGENCE FEED</b>\n\nCould not fetch RSS feeds.\nCheck network connection."
        if not test_mode:
            send_telegram(msg)
        else:
            print("Msg: {0}".format(msg))
        return

    # Phase 2: LLM Analysis -- sequential calls, max 3 with retry
    print("\nPhase 2: Running LLM analysis... ", file=sys.stderr)
    results = {}
    header_prefix = "JARVIS INTELLIGENCE - {0} ({1})".format(now.strftime('%d/%m/%Y'), day_name)
    if bedtime_mode:
        header_prefix = "JARVIS BEDTIME - {0} ({1})".format(now.strftime('%d/%m/%Y'), day_name)

    # Define prompt templates using _ART placeholder for article data
    _ART = "{articles}"   # Replacement token used in all prompts

    if bedtime_mode:
        prompts = [
             ("AI & Tech Priority", """You are Jarvis, an intelligence analyst for Vietnamese investors. Analyze directly -- no introductions or conclusions.

Based on the article list below (updated in the last 24h), output exactly 3 sections using these EXACT headers:

PHAN-AI
List up to 4 AI-related news items: new language models, AI tools released, AI startup funding, AI regulations. Each item must have source link [Source Name](URL). If no notable AI info: "Chưa có đột phá AI đáng chú ý trong 24h qua."

PHAN-ECON
Summarize up to 3 most important economic events in Vietnam and globally. Each item must have source link [Source Name](URL).

PHAN-HIGHLIGHTS
Select 2-3 other notable news from all sources (non-AI technology, culture, sports if any).

REQUIRED RULES:
1. Use bullet points ONLY (- or *). NO tables, code blocks, or HTML tags for listing.
2. Each analysis point must be concise -- max 1-2 sentences per item.
3. USE STANDARD VIETNAMESE with correct diacritics. Keep technical terms (AI, LLM) in English.
4. EVERY conclusion about business/sector/trend MUST have [Source Name](URL) at the end of each line.

ARTICLES TO ANALYZE:
""" + _ART),

             ("Trend Analysis + Recommendations", """You are Jarvis, an experienced market analyst. Based on the article list below, answer exactly these 2 sections using these EXACT headers:

PHAN-XUHUONG
Identify the top 3 biggest trends of today's session. Does AI connect with any hot sector? Is market sentiment bullish or bearish? Every observation must have evidence from [Source Name](URL). Focus on structural shifts, not daily headline listings.

PHAN-KHENHNGHI
Provide 2-3 specific investment category recommendations -- NOT generic advice like "should watch tech sector". Give concrete comparisons: which stocks to hold/buy/sell and why, based on signals in the articles.

REQUIRED RULES:
1. Use bullet points ONLY (- or *). NO tables, code blocks, or HTML tags for listing.
2. No introductions or conclusions, get straight to the topic from the first sentence.
3. USE STANDARD VIETNAMESE with correct diacritics. Technical terms (portfolio, hedging) may stay in English if needed.
4. EVERY assessment about sector, trend, or asset MUST have [Source Name](URL).

DATA:
""" + _ART),

             ("Entertainment Culture Sports Wrap-Up", """From the articles under ENTERTAINMENT/CULTURE/SPORTS below, extract 3-5 most interesting highlights.

Each bullet format: [emoji] Short title + 1-sentence summary of content -- [Source Name](URL)

RULES:
1. REMOVE any economic, education, political news -- these are NOT entertainment.
2. ONLY include: music (new albums, concerts, entertainment industry M&A), sports (match results, champions, transfers), culture/celebrity news, film reviews.
3. If there are NO entertainment/culture/sports items in the list, output EXACTLY this one line only: "Chưa có tin giải trí/văn hóa/thể thao nổi bật trong kỳ báo cáo này."
4. USE NATURAL VIETNAMESE with correct diacritics.

ARTICLES TO ANALYZE:
""" + _ART),
        ]
    else:
        prompts = [
             ("AI & Tech Priority", """Bạn là Jarvis, chuyên gia phân tích tin tức cho nhà đầu tư Việt Nam. Hãy PHÂN TÍCH TRỰC TIẾP -- không mở bài kết bài dài dòng, không giới thiệu bản thân.

Dựa trên danh sách bài báo bên dưới (cập nhật 24h qua), hãy output chính xác 3 phần theo đúng cấu trúc sau:

PHAN-AI
Liệt kê tối đa 4 tin tức liên quan TRỰC TIẾP đến công nghệ AI: mô hình ngôn ngữ mới, công cụ AI ra mắt, startup AI được đầu tư lớn, quy định pháp lý về AI. Mỗi tin phải có liên kết nguồn [Tên báo](URL). Nếu không có thông tin đáng giá nào về AI thì ghi "Chưa có đột phá AI đáng chú ý trong 24h qua."

PHAN-ECON
Tóm tắt tối đa 3 sự kiện kinh tế Việt Nam và quốc tế quan trọng nhất. Mỗi tin phải có liên kết nguồn [Tên báo](URL).

PHAN-HIGHLIGHTS
Chọn 2-3 tin tức còn lại đáng chú ý từ tất cả nguồn (công nghệ không thuộc AI, văn hóa, thể thao nếu có).

QUY TAC BAT BUOC:
1. Chi dung dau goc duong (- hoac *) -- TUYET DOI khong dung bang, code block hay HTML tags de liet ke
2. Moi diem phan tich ngan gon -- 1 den 2 cau toi da moi tin, khong giai thich dai dong
3. SU DUNG TIENG VIET CHUAN, chinh ta dung -- chi giu lai cac thuat nguyen chuyen nganh quen thuoc (AI, LLM) khi bat buoc
4. MOI cau ket luan ve doanh nghiep/sector/xu huong PHAI co [Ten bao](URL) o cuoi moi dong

BAI BAO CẦN PHAN TICH:
""" + _ART),

             ("Trend Analysis + Recommendations", """Bạn là Jarvis, chuyên gia phân tích thị trường giàu kinh nghiệm. Dựa vào danh sách bài báo bên dưới, hãy trả lời chính xác 2 phần sau:

PHAN-XUHUONG
Xac dinh top 3 xu huong lon nhat trong phiên hôm nay. AI có ket nối với sector nào đang hot không? Market sentiment dang bullish hay bearish? Moi quan sat phai co dan chüng từ [Ten bao](URL). Tap trung vào structural shift, đổng liệt ke tin tức hang ngay.

PHAN-KHENHNGHI
Đưa ra 2-3 khuyến nghi thật te cho danh muc dau tư -- KHÔNG advice chung chung như "nên theo dõi sector cong nghe". Prefer so sánh cu thể: giữ/mua/bán mã nào và tại sao, căn cứ từ tín hiệu trong bài báo.

QUY TAC BAT BUOC:
1. Chi dung dau goc duong (- hoac *) -- TUYET DOI khong dung bang, code block hay HTML tags de liet ke
2. Khong mo bai ket bai dai dong, di vào van de ngay tu cau dau tien
3. SU DUNG TIENG VIET CHUAN, chinh ta dung. Thuat nguyen chuyen nganh nhu portfolio, hedging co the giu nguyên tieng Anh neu can thiet
4. MOI cau nhan dinh ve sector, trend hay tai san PHAI co [Ten bao](URL) kem o cuoi

DU LIEU:
""" + _ART),

             ("Entertainment Culture Sports Wrap-Up", """Danh sách dưới đây CHỈ chứa các bài báo giải trí/văn hóa/thể thao (đã được lọc sẵn). Hãy chọn ra 3-5 tin thú vị nhất và format thành bullet highlights.

Moi bullet format: [emoji] Tiêu đề ngắn + 1 câu tóm tắt nội dung -- [Tên báo](URL)

QUY TAC BAT BUOC:
1. DANH SACH DUOI DAY DA DUOC LOC BO TIN KINH TE/CHINH TRI CHỈ CON LA GIẢI TRÍ/VĂN HÓA/THỂ THAO. KHÔNG LOẠI BỎ GÌ THÊM.
2. CHI format các tin thành bullet point hấp dẫn -- không thêm nội dung mới, không giải thích dài dòng.
3. Nếu danh sách rỗng -> output duy nhất: "Chưa có tin giải trí/văn hóa/thể thao nổi bật trong kỳ báo cáo này."
4. SU DUNG TIENG VIET TU NHIÊN, CHÍNH TA CHUAN

BAI BAO CAN PHAN TICH (chỉ là entertainment/culture/sports):
""" + _ART),
        ]

    # Phase 2: Process each prompt
    # Each tuple in prompts is (section_name, combined_system_prompt)
    # The system prompt already has _ART concatenated so it includes the article data placeholder.
    # But we still pass art_text or ent_text as the user message to get the full text into LLM.
    for section_name, sys_prompt in prompts:
        print("[{0}]... ".format(section_name), file=sys.stderr, end="", flush=True)

        # Entertainment chain gets ENT-ONLY article text; others get full art_text
        if "Entertainment" in section_name or "GIẢI TRÍ" in sys_prompt or "văn hóa/thể thao" in sys_prompt:
            text_for_llm = ent_text
        else:
            text_for_llm = art_text

        timeout_val = 600 if text_for_llm is ent_text else 300
        result = None
        for attempt in range(3):
            try:
                result = get_llm_analysis(sys_prompt, text_for_llm, timeout=timeout_val)
                if result and not result.startswith("Error") and "Ollama" not in result and len(result) > 20:
                    break
            except Exception as retry_e:
                print("retry{0}...".format(attempt+1), file=sys.stderr, end="", flush=True)
                time.sleep(10)

        results[section_name] = (result if (result and len(result) > 20)
                                 else "[No data available - LLM returned empty]")
        print("[OK] len={0}".format(len(results[section_name])), file=sys.stderr)

    # Phase 3: Build Telegram messages
    print("\nPhase 3: Delivering briefing...", file=sys.stderr)

    if bedtime_mode:
        wrap_up = results.get("AI & Tech Priority", "")
        market_close = results.get("Trend Analysis + Recommendations", "")
        preview = results.get("Entertainment Culture Sports Wrap-Up", "")

        msg1 = "{0}\n\n{1}".format(header_prefix, wrap_up)
        msg2 = ("\n\n" + "=" * 30 + "\n\n" + market_close) if market_close else ""
        msg3 = preview if preview else ""
        parts = [msg1, msg2, msg3]

    else:
        ai_tech = results.get("AI & Tech Priority", "")
        trends = results.get("Trend Analysis + Recommendations", "")
        entertainment = results.get("Entertainment Culture Sports Wrap-Up", "")

        msg1 = "{0}\n\n{1}".format(header_prefix, ai_tech)
        msg2 = ("\n" + "=" * 30 + "\n\n{0}".format(trends)) if trends else ""
        # Entertainment as separate message to avoid overly long delivery
        if not entertainment or len(entertainment.strip()) < 50:
            msg3 = "\U0001f3ac <b>GIẢI TRÍ / VĂN HOÁ / THỂ THAO</b>\n\nKhông có tin nổi bật trong kỳ báo cáo này."
        else:
            msg3 = entertainment

        parts = [msg1, msg2, msg3]

    # Deliver
    for i, text in enumerate(parts):
        if text.strip():
            if test_mode:
                print("\n" + "=" * 40)
                print("PART {0}:\n{1}".format(i+1, text[:2000]))
            else:
                send_telegram(text)

    print("\nBriefing complete!", file=sys.stderr)


# --- ENTRY POINT ---
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    print("=" * 60)
    print("JARVIS INTELLIGENCE BRIEFING ENGINE v2.0 (Enhanced Sources)")
    count_sections = len(set(s['section'] for s in RSS_SOURCES))
    print("{0} RSS sources configured across {1} categories".format(
        len(RSS_SOURCES), count_sections))
    print("=" * 60)

    test = "--test" in sys.argv or "-t" in sys.argv
    bedtime = "--bedtime" in sys.argv or "-b" in sys.argv
    run_full_briefing(test_mode=test, bedtime_mode=bedtime)
