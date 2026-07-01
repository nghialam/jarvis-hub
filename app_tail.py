# --- API: Daily snapshots -------------------------------------------------

@app.route("/api/snapshots", methods=["GET"])
def api_snapshots():
    dates = db.get_all_dates() if db else []
    snapshots = []

    for date in dates[:5]:   # Last 5 days
        snap = db.get_daily_snapshot(date)
        if snap:
            content = snap["briefing_content"]
            preview = content[:300].replace("\n", " ")
            article_count = content.count("**.")   # rough count

            snapshots.append({
                 "date": date,
                 "preview": preview,
                 "article_count": article_count,
                 "full_content": content,
             })

    return jsonify({"count": len(snapshots), "snapshots": snapshots})


# --- API: Articles / News Feed --------------------------------------------

@app.route("/api/articles", methods=["GET"])
def api_articles():
     """Fetch live RSS articles, optionally filtered by category."""
    cat_filter = request.args.get("category", "").strip().lower()

    try:
        articles = fetch_rss_feeds()[:30]
        for a in articles:
            try:
                enrich_article(a)
            except Exception:
                pass

        if cat_filter:
            articles = [a for a in articles if (a.get("category") or "").lower() == cat_filter]

         # Return clean article list with sentiment + category
        result = []
        for a in articles:
            sentiment = a.get("sentiment_layer1") or "TRUNG_LAP"
            sent_class = "positive" if "TICH_CUC" in sentiment else ("negative" if "TIEU_CUC" in sentiment else "neutral")
            result.append({
                 "id": a.get("link", ""),
                 "title": a.get("title", "").strip(),
                 "source": a.get("source", ""),
                 "category": a.get("category", "general"),
                 "sentiment": sentiment,
                 "sentiment_class": sent_class,
                 "link": a.get("link", ""),
                 "published": a.get("published", ""),
                 "priority": a.get("priority", 2),
             })
        return jsonify({"count": len(result), "articles": result})
    except Exception as e:
        print("[WARN] Articles API error: %s" % str(e), file=sys.stderr)
        return jsonify({"count": 0, "articles": [], "error": str(e)})


# --- API: Health check ---------------------------------------------------

@app.route("/api/health", methods=["GET"])
def api_health():
    omlx_status = "unknown"
    try:
        import requests
        base_url = config.get("omlx", {}).get("url", "http://localhost:11434") if config else "http://localhost:11434"
        r = requests.get(base_url + "/health", timeout=5)
        omlx_status = "online" if r.status_code == 200 else "offline"
    except Exception as e:
        omlx_status = "error: %s" % str(e)[:40]

    db_path = str(config.get("db_path", "N/A")) if config else "N/A"

     # Include market indices and exchange rates for dashboard display
    indices_data = {}
    rates_data = {}
    try:
        if config:
            indices_data = fetch_market_indices()
            rates_data = get_exchange_rate()
    except Exception:
        pass

    return jsonify({
         "status": "ok",
         "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
         "omlx": omlx_status,
         "db_path": db_path,
         "indices": indices_data,
         "rates": rates_data,
     })


# --- Start server ---------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Jarvis Hub Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8100, help="Port to listen on")
    args = parser.parse_args()

    print("=" * 60)
    print("JARVIS HUB Dashboard starting...")
    print("Open: http://%s:%s" % (args.host, args.port))
    print("=" * 60)

      # Start Flask first, then init data in background thread
    threading.Thread(target=_init, daemon=True).start()
    app.run(host=args.host, port=args.port, debug=True)
