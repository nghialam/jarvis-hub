"""
cli.py -- Jarvis Hub CLI entry point via Click.

commands:
    jarvis briefing       - Run daily briefings (morning/evening)
    jarvis analyze        - Stock/gold/crypto analysis
    jarvis watch          - Manage watchlist
    jarvis search         - Search knowledge base
    jarvis quiz           - Spaced repetition quiz mode
    jarvis log            - View activity logs
    jarvis history        - Compare daily snapshots
    jarvis doctor         - System health check
"""
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import click
import requests

# Resolve local imports
sys.path.insert(0, "/Users/nghialam/jarvis-hub")
from core import config as cfg_module
from core.news import (
    fetch_rss_feeds,
    enrich_article,
    get_exchange_rate,
    fetch_market_indices,
)
from core.market import (
    analyze_stock,
    fetch_gold_price,
    fetch_crypto,
)
from core.db import Database


STATUS_EMOJI = {
    "ok": "\u2705",
    "warn": "\u26a0\ufe0f",
    "error": "\u274c",
}

BULLISH_ICON = "\u00f3\u00a2"
BEARISH_ICON = "\u00f3\u00b4"
NEUTRAL_ICON = "\u00f3\u00a1"


@click.group()
def cli():
    """Jarvis Hub - Finance Intelligence System"""
    pass


# --- BRIEFING ---------------------------------------------------------

@cli.command()
@click.option("--type", "briefing_type", type=click.Choice(["morning", "evening"]), default=None)
def briefing(briefing_type):
    """Run daily news briefing with sentiment analysis."""
    config = cfg_module.load_config()
    db = Database()
    start = time.time()

    click.echo("=== JARVIS HUB BRIEFING ===")
    click.echo("Time: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")))
    click.echo("")

    # 1. Fetch news
    click.echo("[1/4] Fetching news feeds...")
    articles = fetch_rss_feeds()
    click.echo("       -> Found {} unique articles".format(len(articles)))

    # 2. Enrich with sentiment
    click.echo("[2/4] Analyzing sentiment (Layer 1 + Layer 2)...")
    for i, article in enumerate(articles[:20], 1):
        enrich_article(article)
        if i <= 5:  # Show first 5 as preview
            sent = article.get("sentiment_layer2") or article.get("sentiment_layer1", "")
            if "tich_cuc" in sent.lower() or "TICH_CUC" in sent:
                icon = BULLISH_ICON
            elif "tieu_cuc" in sent.lower():
                icon = BEARISH_ICON
            else:
                icon = NEUTRAL_ICON
            click.echo("       {} [{}] {}".format(icon, article["sector"], article["title"][:60]))

    # 3. Market indices
    click.echo("[3/4] Fetching market indices...")
    indices = fetch_market_indices()
    vn_idx = indices.get("VN-Index")
    if vn_idx:
        arrow = "\u25b2" if vn_idx["change_pct"] >= 0 else "\u25bc"
        click.echo("       VN-Index: {} ({} {:.2f}%)".format(vn_idx["price"], arrow, vn_idx["change_pct"]))

    global_data = indices.get("global", {})
    if global_data:
        click.echo("     Global:")
        for name, data in list(global_data.items())[:5]:
            if isinstance(data, dict) and "price" in data:
                arrow = "\u25b2" if data["change_pct"] >= 0 else "\u25bc"
                click.echo("       {}: {} ({} {:+.2f}%)".format(name, data["price"], arrow, data["change_pct"]))

    # 4. Exchange rates
    click.echo("[4/4] Fetching exchange rates...")
    rates = get_exchange_rate()
    usd = rates.get("USD", {})
    if usd:
        transfer = usd.get("transfer", "N/A")
        sell = usd.get("sell", "N/A")
        click.echo("       USD/VND: Transfer {} | Sell {}".format(transfer, sell))

    # Count sentiment distribution
    bullish = sum(1 for a in articles if "TICH_CUC" in a.get("sentiment_layer1", ""))
    bearish = sum(1 for a in articles if "TIEU_CUC" in a.get("sentiment_layer1", ""))
    neutral = len(articles) - bullish - bearish

    click.echo("\n  Summary: {} {} | {} {} | {} {}".format(
        BULLISH_ICON if bullish > 0 else " ", "tich_cuc" if bullish > 0 else "",
        BEARISH_ICON if bearish > 0 else " ", "tieu_cuc" if bearish > 0 else "",
        NEUTRAL_ICON if neutral > 0 else " ", "trung_lap" if neutral > 0 else ""
    ))

    # Generate briefing text for Telegram (using emoji-safe chars)
    lines = []
    transfer = usd.get("transfer", "?") if usd else "N/A"
    sell_val = usd.get("sell", "?") if usd else "N/A"
    updated_at = rates.get("updated", "N/A")

    lines.append("{} **Ty gia (Vietcombank)** _Cap nhat: {}_".format("\u00f0\u009f\u0092\xb1", updated_at))
    lines.append("**VND/USD** Transfer: {}d / Ban: {}d".format(transfer, sell_val))
    lines.append("")

    lines.append("TIN TUC & CAM XUC")

    for i, article in enumerate(articles[:8], 1):
        sentiment = article.get("sentiment_layer2") or article.get("sentiment_layer1", "")
        summary = article["summary_raw"][:200]
        lines.append("**{}. {}**".format(i, article["title"]))
        lines.append("      Source: {} | {}".format(article["source"], sentiment))
        lines.append("     {}".format(summary))
        lines.append("")

    overall = "Tich_cuc" if bullish > bearish else ("Tieu_cuc" if bearish > bullish else "Trung_lap")
    lines.append("---" * 26)
    lines.append("Tong quan: {} {} | {} {} | {} {}".format(
        BULLISH_ICON if bullish > 0 else "", str(bullish),
        BEARISH_ICON if bearish > 0 else "", str(bearish),
        NEUTRAL_ICON if neutral > 0 else "", str(neutral)
    ))
    lines.append("Xu huong: **{}**".format(overall))

    briefing_text = "\n".join(lines)

    duration_ms = int((time.time() - start) * 1000)

    # Save to DB
    today = datetime.now().strftime("%Y-%m-%d")
    db.save_daily_snapshot(today, briefing_text, "{} articles fetched, sentiment: {}".format(len(articles), overall))
    db.log_activity("briefing", "type={}".format(briefing_type or "auto"), "ok",
                     "{} articles, {} bullish, {} bearish".format(len(articles), bullish, bearish),
                     duration_ms)

    click.echo("\nOK Briefing complete in {}ms".format(duration_ms))
    click.echo("  Snapshot saved for {}".format(today))


# --- ANALYZE (Stock/Gold/Crypto) --------------------------------

@cli.command()
@click.argument("symbol")
def analyze(symbol):
    """Analyze a stock, gold, or crypto."""
    start = time.time()
    db = Database()

    symbol_upper = symbol.upper()
    click.echo("--- Analyzing {} ---".format(symbol_upper))

    # Dispatch to correct fetcher
    if any(c in symbol_upper for c in ("BTC", "ETH", "SOL", "BNB")):
        data = fetch_crypto(symbol)
    elif symbol_upper in ("XAUUSD", "XAU/USD", "XAUUSD=X"):
        data = fetch_gold_price()
    else:
        data = analyze_stock(symbol)

    if not data or "error" in data:
        click.echo("! Error: {}".format(data.get("error", "Could not fetch data")))
        db.log_activity("analyze", symbol, "error", "Could not fetch data for {symbol}")
        return

    # Display results
    name = data.get("name", symbol)
    price = data.get("price")
    change_pct = data.get("change_pct", 0)
    type_ = data.get("type", "stock")

    if price:
        arrow = "+" if change_pct >= 0 else ""
        emoji = "\u2795" if change_pct >= 0 else "\u2796"

        click.echo("\u00f0\u009f\u0092\xb0 {} ({})".format(name, data.get("symbol", symbol)))
        click.echo("{} Gia: {:,.0f} {}".format(emoji, price, data.get("currency", "")))
        click.echo("   Thay doi: {}{}%".format(arrow, change_pct))

        if data.get("pe_ratio"):
            click.echo("     P/E:    {:.2f}".format(data["pe_ratio"]))
        if data.get("eps"):
            click.echo("     EPS:    {:.2f}".format(data["eps"]))
        if data.get("market_cap"):
            click.echo("  Von hoa: {}".format(data["market_cap"]))

        # Technical indicators
        technical = data.get("technical")
        if technical and "error" not in technical:
            click.echo("\n--- Chi so ky thuat ---")

            for key in ["SMA_20", "SMA_50", "RSI_14"]:
                val = technical.get(key)
                if val:
                    click.echo("  {}: {}".format(key, val))

            macd = technical.get("MACD")
            if macd:
                click.echo("   MACD:")
                click.echo("      MACD line: {}".format(macd.get("macd")))
                click.echo("      Signal:     {}".format(macd["signal"]))
                click.echo("      Histogram: {}".format(macd["histogram"]))

        # LLM report
        llm_report = data.get("llm_report")
        if llm_report:
            click.echo("\n--- Bao cao LLM ---")
            click.echo(llm_report)

    duration_ms = int((time.time() - start) * 1000)
    db.log_activity("analyze", symbol, "ok", "{} analyzed in {}ms".format(name, duration_ms), duration_ms)

    click.echo("\nOK Analysis complete in {}ms".format(duration_ms))


# --- WATCHLIST -----------------------------------------------------------

@cli.group()
def watch():
    """Manage your stock/currency watchlist."""
    pass


@watch.command("add")
@click.argument("symbol")
@click.option("--name", "-n", default="")
def watch_add(symbol, name):
    """Add a symbol to your watchlist."""
    db = Database()

    # Try to fetch name if not provided
    if not name:
        try:
            data = analyze_stock(symbol)
            if data and "name" in data:
                db.add_watchlist(symbol, data["name"])
                click.echo("Added {} - {}".format(symbol.upper(), data["name"]))
        except Exception as e:
            click.echo("! Could not fetch name: {}".format(e))
            db.add_watchlist(symbol)

    click.echo("Watchlist updated. Use 'jarvis watch list' to view.")


@watch.command("list")
def watch_list():
    """Show your current watchlist."""
    db = Database()
    items = db.get_watchlist()

    if not items:
        click.echo("! Watchlist is empty. Add symbols with 'jarvis watch add SYMBOL'")
        return

    click.echo("--- YOUR WATCHLIST ---\n")

    # Get latest prices for each symbol
    for item in items:
        symbol = item["symbol"]
        try:
            data = analyze_stock(symbol)
            name = item["name"] or data.get("name", symbol)

            if data and "price" in data:
                price = data["price"]
                change_pct = data.get("change_pct", 0)
                arrow = "+" if change_pct >= 0 else ""
                emoji = "\u2795" if change_pct >= 0 else "\u2796"

                click.echo("- {} ({})".format(name, symbol))
                click.echo("    {} {:,.0f} | {}{}%".format(emoji, price, arrow, change_pct))
            else:
                click.debug("   {} ({}) - No price data".format(name, symbol))

        except Exception as e:
            click.echo("     {} ({}) - Error: {}".format(item["name"] if item.get("name") else symbol, symbol, str(e)[:50]))

    click.echo("\n--- End of watchlist ---")


@watch.command("remove")
@click.argument("symbol")
def watch_remove(symbol):
    """Remove a symbol from your watchlist."""
    db = Database()
    success = db.remove_watchlist(symbol)
    if success:
        click.echo("! Removed {} from watchlist".format(symbol.upper()))
    else:
        click.echo("- Symbol not found in watchlist")


# --- KNOWLEDGE BASE SEARCH -----------------------------------------------

@cli.command()
@click.argument("query")
def search(query):
    """Search the knowledge base (Investopedia-like)."""
    db = Database()
    results = db.search_knowledge(query)

    if not results:
        click.echo("! No results found for '{}'. Try a different keyword.".format(query))

        # Suggest creating one via LLM
        suggestion_prompt = "Explain the financial concept '{}' in Vietnamese, under 200 words. Include definition, examples, and related concepts.".format(query)
        try:
            config = cfg_module.load_config()
            omlx_url = config.get("omlx", {}).get("url", "http://localhost:11434")
            model = config.get("omlx", {}).get("model", "qwen3.6:latest")

            response = requests.post(
                 "{} /v1/chat/completions".format(omlx_url),
                json={
                     "model": model,
                     "messages": [
                         {"role": "user", "content": suggestion_prompt}
                     ],
                     "stream": False,
                 },
                timeout=15,
             )

            if response.status_code == 200:
                generated_text = response.json().get("message", {}).get("content", "")
                click.echo("\n! AI-generated explanation for '{}':\n".format(query))
                click.echo(generated_text)

                # Offer to save it
                save = click.confirm("\nSave this to knowledge base?")
                if save:
                    db.upsert_knowledge(query, generated_text)
                    click.echo("OK Saved to knowledge base!")
        except Exception as e:
            click.echo("! Could not generate answer: {}".format(e))
        return

    click.echo("\n=== Found {} results for '{}' ===\n".format(len(results), query))

    for i, result in enumerate(results, 1):
        click.echo("- {}".format(result["term"]))
        if result.get("tags"):
            click.echo("   Tags: {}".format(result["tags"]))

        snippet = result["content"][:300].replace("\n", " ")
        if len(result["content"]) > 300:
            snippet += "..."

        click.echo("  {}\n".format(snippet))


# --- QUIZ/ FLASHCARD ---------------------------------------------------

@cli.command()
def quiz():
    """Spaced repetition quiz mode."""
    db = Database()
    terms = db.get_all_terms()

    if not terms:
        click.echo("! Knowledge base is empty. Use 'jarvis search TERM' to learn first.")
        return

     # Random selection (simplistic spaced repetition)
    quiz_count = min(5, len(terms))
    selected = random.sample(terms, quiz_count)

    click.echo("=== SPACED REPETITION QUIZ ({}) ===\n".format(quiz_count))

    for i, term in enumerate(selected, 1):
        answer = db.get_knowledge_by_term(term)

        if not answer:
            continue

        question = answer["content"][:200].replace("\n", " ")
        click.echo("[Quiz {}/{}] Gia thuc khai niem: {}".format(i, quiz_count, term))
        click.echo("    Gợi y: {}...\n".format(question[:150]))

        user_answer = click.prompt("Tra loi cua ban (Enter de xem dap an)", default="")

        answer_text = answer["content"][:300].replace("\n", " ")
        if len(answer["content"]) > 300:
            answer_text += "..."

        click.echo("\nDap an: {}".format(answer_text))

        # User rate their recall (just for UX feedback)
        rating = click.prompt("Ban da nho tot?", type=click.Choice(["rat_tot", "kha", "can_hoc_lai"]), default="kha")

        db.log_activity("quiz", term, "ok", "Rating: {}".format(rating))

        click.echo("")


# --- ACTIVITY LOG -----------------------------------------------------------

@cli.command()
@click.option("--last", "-l", default=20, help="Number of recent entries to show.")
def log(last):
    """View system activity logs."""
    db = Database()
    activities = db.get_activities(int(last))

    if not activities:
        click.echo("Khong co hoat dong nao duoc ghi nhan.")
        return

    click.echo("=== HOAT DONG GAN DAY ({}) ===\n".format(len(activities)))

     # Show newest first
    for a in reversed(activities):
        status_icon = STATUS_EMOJI.get(a["status"], "?")

        details = ""
        if a.get("summary"):
            details = " | {}".format(a["summary"][:60])

        click.echo("{} {} {}{}{}".format(status_icon, a["timestamp"], a["command"], a["args"], details))

        if a.get("duration_ms"):
            click.echo("    Time: {}ms".format(a["duration_ms"]))


# --- DAILY HISTORY/VERSION DIFF -------------------------------------------

@cli.command()
@click.argument("date1")
@click.argument("date2", default=None)
def history(date1, date2):
    """Compare daily briefing snapshots."""
    db = Database()

    if not date2:
        dates = db.get_all_dates()
        click.echo("Available dates: {}".format(", ".join(dates[:10])))
        click.echo("\nUsage: jarvis history YYYY-MM-DD [YYYY-MM-DD]")
        return

    snap1 = db.get_daily_snapshot(date1)
    snap2 = db.get_daily_snapshot(date2)

    if not snap1 or not snap2:
        click.echo("! Not enough snapshots found:")
        if not snap1:
            click.echo("- {}: khong co".format(date1))
        if not snap2:
            click.echo("! {}: khong co".format(date2))
        return

    # Simple line-by-line diff
    lines1 = snap1["briefing_content"].split("\n")
    lines2 = snap2["briefing_content"].split("\n")

    click.echo("=== SO SANH: {} vs {} ===\n".format(date1, date2))

    max_len = max(len(lines1), len(lines2))

    for i in range(max_len):
        l1 = lines1[i] if i < len(lines1) else ""
        l2 = lines2[i] if i < len(lines2) else ""

        if l1 != l2:
            click.echo("- {}".format(l1))
            click.echo("+ {}".format(l2))


# --- DOCTOR (Health check) ----------------------------------------------

@cli.command()
def doctor():
    """System health check."""
    click.echo("=== JARVIS HUB DOCTOR ===\n")

    # Check config
    try:
        config = cfg_module.load_config()
        click.echo("\u2705 Config loaded successfully")

        omlx_url = config.get("omlx", {}).get("url", "http://localhost:11434")
        omlx_model = config.get("omlx", {}).get("model", "qwen3.6:latest")
        click.echo("  OMLX endpoint:    {}".format(omlx_url))
        click.echo("  Model:               {}".format(omlx_model))
    except Exception as e:
        click.echo("! Could not load config: {}".format(e))

    # Check DB
    try:
        db = Database()
        terms_count = len(db.get_all_terms())
        activities_count = len(db.get_activities(1))

        click.echo("\u2705 DATABASE OK")
        click.echo("  Knowledge base entries: {}".format(terms_count))
        click.echo("  Activity log entries: accessible")
    except Exception as e:
        click.echo("! Database error: {}".format(e))

    # Check OMLX connectivity
    try:
        r = requests.get("{} /v1/models".format(omlx_url), timeout=5)

        if r.status_code == 200:
            models = r.json().get("models", [])
            model_names = [m.get("name", "") for m in models]

            base_model = omlx_model.split(":")[0]
            if base_model in " ".join(model_names):
                click.echo("✅ OMLX running - {} models available".format(len(models)))
            else:
                click.echo("! Model '{}' not found. Available: {}".format(
                    omlx_model, ", ".join(model_names[:5])))
        else:
            click.echo("- OMLX endpoint returned status {}".format(r.status_code))

    except Exception as e:
        click.echo("! Could not connect to OMLX: {}".format(e))

    # Check RSS sources
    try:
        sources = config.get("feed", {}).get("sources", [])
        click.echo("\n! RSS Sources configured:")
        for s in sources:
            r_test = requests.head(s["url"], timeout=5)
            status = "OK" if r_test.status_code < 400 else "ERROR ({})".format(r_test.status_code)
            click.echo("- [{}] {}: {}".format(s.get("priority", "?"), s["name"], status))

    except Exception as e:
        click.echo("! Could not check RSS sources: {}".format(e))

     # Check DB path availability
    db_path = config.get("db_path", "jarvis-hub/knowledge/jarvis.db")
    if Path(db_path).exists():
        db_size = Path(db_path).stat().st_size / 1024
        click.echo("\u2705 Database file: {} ({} KB)".format(db_path, round(db_size, 1)))


# --- Main entry point -----------------------------------------------

if __name__ == "__main__":
    cli()
