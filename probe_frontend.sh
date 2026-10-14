#!/usr/bin/env bash
# Probe the EXACT endpoints the frontend (app.js/async_tasks.js/market-briefs.js) calls
BASE=http://127.0.0.1:8100
eps=(
  "/api/v1/overview"
  "/api/v1/overview/indices"
  "/api/v1/overview/crypto"
  "/api/v1/overview/gold"
  "/api/v1/overview/motions"
  "/api/v1/overview/chart"
  "/api/v1/news"
  "/api/v1/news/trending"
  "/api/v1/news/categories"
  "/api/v1/research"
  "/api/v1/research/stats"
  "/api/v1/companies"
  "/api/watchlist"
  "/api/v1/stocks/symbols/search?q=V"
  "/api/v1/market/heatmap"
  "/api/market-intelligence/run"
  "/api/market-intelligence/latest"
  "/api/market-intelligence/history?limit=20"
  "/api/market-intelligence/sentiment-dist"
  "/api/v1/portfolio/pnl-summary"
  "/api/v1/portfolio/holdings"
  "/api/v1/portfolio/transactions"
  "/api/v1/screener/signals"
  "/api/v1/screener/alert-feed"
  "/api/v1/intelligence/market/latest"
  "/api/v1/intelligence/pipeline/status"
  "/api/v1/llm/health"
  "/api/v1/llm/tasks"
  "/api/v1/cms/articles"
  "/api/v1/events"
  "/api/v1/events/stats"
  "/api/v1/market-briefs/count"
  "/api/v1/market-briefs/latest"
  "/api/v1/health"
  "/api/v1/status"
)
ok=0; bad=0
for e in "${eps[@]}"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 6 "$BASE$e")
  if [ "$code" = "200" ]; then st="OK "; ok=$((ok+1)); else st="***"; bad=$((bad+1)); fi
  printf "%s  %s  %s\n" "$st" "$code" "$e"
done
echo "--------------------------------"
echo "OK=$ok  BROKEN=$bad"
