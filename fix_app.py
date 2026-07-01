import ast

filepath = '/Users/nghialam/jarvis-hub/app.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

# Find the start and end of the api_articles function to replace it
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if '@app.route("/api/articles"' in line:
        start_idx = i
    elif start_idx is not None and i > start_idx + 2 and ('@app.route' in line or (line.strip() and not line[0].isspace() and i > start_idx + 5)):
        end_idx = i
        break

if start_idx is None:
    print("ERROR: api_articles route not found")
else:
    new_func = '''@app.route("/api/articles", methods=["GET"])
def api_articles():
     """Fetch articles from DB (Tier 1 cron), optionally filtered by category."""
    try:
        if not db or not hasattr(db, "get_articles"):
            return jsonify({"articles": [], "count": 0, "note": "DB not initialized"})

        cat_filter = request.args.get("category", "").strip().lower() or None
        arts = db.get_articles(limit=30, category=cat_filter) or []

         # Map DB record -> dashboard format
        result = []
        for a in arts[:30]:
            entry = {
                 "id": a.get("id"),
                 "title": a.get("title", ""),
                 "summary_raw": a.get("summary_raw", ""),
                 "category": a.get("category", "general"),
                 "sentiment_class": a.get("sentiment", "TRUNG_LAP"),
                 "published": a.get("publication_date", ""),
                 "link": a.get("url", ""),
             }
             # Merge news_enhanced data if DB has it
            try:
                ne = db._c().execute(
                     "SELECT content, sentiment, sentiment_score, importance, affected_symbols FROM news_enhanced WHERE article_id=?",
                     (a.get("id"),)
                 ).fetchone()
                if ne:
                    entry["content"] = ne[0] or ""
                    entry["sentiment_score"] = float(ne[2]) if ne[2] else 0.0
                    entry["importancescore"] = float(ne[3]) if ne[3] else 0.0
            except Exception:
                pass
            result.append(entry)

        return jsonify({"articles": result, "count": len(result), "source": "DB"})
    except Exception as e:
        print("[ARTICLES] DB fetch error: %s" % e)
        return jsonify({"articles": [], "error": str(e)[:100]})


'''

    # Replace old lines with new function
    result = lines[:start_idx] + [new_func + '\n'] + lines[end_idx:]

    with open(filepath, 'w') as f:
        f.writelines(result)

    print(f"Replaced api_articles (lines {start_idx+1}-{end_idx})")

    # Validate syntax
    content = ''.join(result)
    try:
        ast.parse(content)
        print("✅ Syntax OK")
    except SyntaxError as e:
        print(f"❌ Syntax Error: {e}")

print("Done.")
