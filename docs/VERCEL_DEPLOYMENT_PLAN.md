# Jarvis Hub Dashboard — Vercel Deployment Plan

**Date**: 02/07/2026  
**Goal**: Deploy frontend dashboard to Vercel free tier; keep LLM/AI processing local on Mac Mini. Database migrates to Cloud for reliability.

---

## 1. Architecture Overview

```
┌──────────────────────┐          ┌─────────────────────────────────┐
│   User / Browser     │          │       macMini (Local)           |
│                      │          │                                 │
│  Access at:          │    ╔═════╧══════════╗   ╔════════════╦════╣
│  jarvis-dashboard.vercel.app             │   ║ tunnel-agent║      ║
├──────────────────────┤   ┌────->║ cloudflared     │──────>|  localhost:8100
│                      │   │      ╚══════════════╝    ║ Ollama/Ollama
│  Frontend            │   │                         ╚════════════╩────────┘
│  (React/Vanilla JS)  │   │                               │
│  served by Vercel    │   │                               ▼
├──────────────────────┤   │                    ┌─────────────────┐
│  API Routes          │   │                    │ Local Jarvis Hub│
│  on Vercel Serverless│   │                    │ Flask @ :8100   │
│  (@vercel/functions) │   │                    └─────────────────┘
├──────────────────────┤   │                       ▲
│  Cloud DB            │   │   Reverse Proxy     │  AI-dependent routes
│  (Postgres free tier)│   │   via Tunnel        │
│  (watchlist,Articles,)│  │                     │  /api/analyze
└──────────────────────┘   └─────────────────────┘  /api/market-evaluation/generate
                             cloudflared tunnel
```

---

## 2. Scope — What Goes Where

| Component          | Location     | Details                                          |
|---------------------|-------------|--------------------------------------------------|
| Frontend (HTML/CSS/JS)   | Vercel     | Static files deployed via `vercel deploy --prod` or Git push |
| API Routes    | Vercel     | Node.js serverless functions (`/api/*`)          |
| SQLite DB         → PostgreSQL  | Cloud (Railway free, Supabase free, vercel postgrees)  | Migrate existing `jarvis.db` data              |
| LLM/AI processing   | **Local** | Remains on Mac Mini via Jarvis Hub Flask server |
| News RSS fetching    | Vercel     | Run as cron-triggered function (no local dependency)        |

---

## 3. Vercel Configuration

### 3.1 Project Setup

```bash
# In ~/jarvis-hub/ directory:
npx vercel login
vercel init flask-dashboard   # or use existing project
vercel link --yes             # creates vercel.json + .vercel/project.json
```

### 3.2 `vercel.json` Configuration

```json
{
  "version": 2,
  "builds": [
    { "src": "dashboard/*.html", "use": "@vercel/static" },
    { "src": "api/**/*.js",    "use": "@vercel/node" }
  ],
  "routes": [
    {"src": "/health",          "dest": "/api/health.js"},         | 
    {"src": "/api/(.*)\.json$", "dest": "/api/$1.json"},            },
    {"src": "/(.*)",            "dest": "/dashboard/$1"}           |
  ],
  "env": {
    "TUNNEL_PROXY_BASE_URL": "https://jarvis-tunnel.yourname.cloudflareaccess.com" | 
    "DATABASE_URL": "postgresql://user:pass@db.xxx.supabase.co/jarvis"
  },
  "crons": [
    {
      "path": "/api/cron/rss-fetch",
      "schedule": "0 6 * * *"
    }
  ]
}
```

### 3.3 `vercel.json` Routes Proxy Pattern

The key challenge: proxy AI-dependent requests back to the local Mac Mini without exposing it directly to the internet. **Solution**: `cloudflared` reverse tunnel.

---

## 4. Cloudflare Tunnel Setup (Mac Mini side)

### 4.1 Install cloudflared

```bash
brew install cloudflared          # or download from cf docs
cloudflared tunnel login           # authenticates via browser → writes ~/.cloudflared/
cloudflared tunnel create jarvis   # generates tunnel ID + JSON creds
```

### 4.2 Tunnel config (`~/.cloudflared/config.yml`)

```yaml
tunnel: <TUNNEL-ID-HERE>
credentials-file: /Users/nghialam/.cloudflared/<TUNNEL-ID>.json

ingress:
  # Proxy AI-dependent routes back to local Jarvis Hub
  - match:
      hostname: ai.jarvis-dashboard.vercel.app        | 
    service: http://localhost:8100
  
  # Catch-all rule for non-matching patterns
  - match: 
      hostname: jarvis-dashboard.vercel.app
    service: http_status:404

```

### 4.3 Run tunnel

```bash
cloudflared tunnel run jarvis
# Tunnel stays alive, routes ai.* traffic → localhost:8100 (OmLX running)
```

*Auto-start on boot:*  
`sudo brew services start cloudflared` + systemd/service file for cloudflared.

**OR** — simpler approach using vercel.json `proxy` env variable pointing to a publicly accessible tunnel endpoint that forwards to your Mac.

---

## 5. Database Migration Strategy

### 5.1 Current State

`sqlite jarvis.db` at `/Users/nghialam/jarvis-hub/` — used for activities, watchlist, knowledge base cache.

### 5.2 Target: Supabase / Vercel Postgres (Free Tier)

```bash
# Backup local SQLite data first
cp jarvis.db jarvis.db.backup.vercel-migration

# Export SQLite schema + data
sqlite3 jarvis.db .schema > schema.sql
sqlite3 jarvis.db ".dump" > dump.sql

# Create Supabase free project → get DATABASE_URL
# Apply SQL to cloud Postgres
psql "$DATABASE_URL" -f schema.sql
psql "$DATABASE_URL" -f dump.sql --on-error-stop
```

### 5.3 Connection string env var for Vercel deployment

Set in `vercel.json` or via Vercel Dashboard → Project Settings → Environment Variables:

| Variable        | Value                          |
|-----------------|------------------------------- |
| DATABASE_URL    | `postgresql://...@supabase.co/jarvis` |
| TUNNEL_PROXY_BASE_URL | `https://jarvis-tunnel.yourname.dns.af.dev`  | 

---

## 6. API Route Redirection

### 6.1 Non-AI endpoints (full deployment to Vercel)

These routes have no LLM dependency — fully deployable as serverless functions:

| Route                         | Functionality                 |
|------------------------------|-------------------------------|
| `GET  /api/health`           | Basic healthcheck             |
| `GET  /api/indices`          | VN market indices data        |
| `GET  /api/signals`          | Signal feed                   |
| `POST /api/signals/add`      | Add signal                    | 
| `GET  /api/snapshots/<date>` | Daily market snapshots       |
| `GET  /api/articles`         | RSS-fetched articles           |
| `GET  /api/daily-snapshot/:date` | Day-specific snapshot   | 
| `POST api/cron/rss-fetch`    | Scheduled news fetch (vercel cron) |

### 6.2 AI-dependent endpoints (proxy to local Mac)

These routes call Ollama/Ollama and MUST stay on the Mac Mini:

| Route                                 | Proxied To                     |
|----------------------------------------|------------------------------- |  
| `GET /api/search`                     | Proxy → localhost:8100/api/search via tunnel |
| `GET /api/analyze?symbol=VIC`         | Proxy → localhost:8100/api/analyze?symbol=VIC |
| `POST /api/market-evaluation/generate`| Proxy → localhost:8100/api/market-evaluation/generate |

---

## 7. Proxy Serverless Function Template

File: `api/proxy-ai.js` (Vercel serverless function)

```js
// /api/proxy-ai — proxies LLM-dependent calls to local Mac Mini via Cloudflare tunnel export default async function handler(req, res) {
  const proxyBase = process.env.TUNNEL_PROXY_BASE_URL; // e.g. https://jarvis-tunnel....cf.af.dev 
  
  if (!proxyBase) {
    return res.status(500).json({ error: 'Tunnel URL not configured' });
  }

  // Build target URL from the original request path and query
  const targetUrl = `${proxyBase}${req.url}`;
  
  try {
    const response = await fetch(targetUrl, { method: req.method, headers: req.headers, body: req.method === 'POST' ? JSON.stringify(req.body): undefined });
    const contentType = response.headers.get('content-type') || 'application/json';
    res.setHeader('Content-Type', contentType);
    res.status(response.status);

    const text await response.text();
    try {
      res.json(JSON.parse(text));
    } catch (_) {
      res.send(text);
    }
  } catch (err) {
    console.error('[proxy-ai] Failed:', err.message);
    // Handle connection timeout gracefully — tunnel may be down if Mac is asleep
    return res.status(503}.json({ error: 'Local Jarvis Hub unavailable' });
  }
}```

### 6.2 Routing in Vercel Functions

Each AI-dependent route should call this proxy utility:

```js
// api/search.js
export default async function handler(req, res) {
  return fetchHandlerWithProxy(req, res); // proxy to local Mac
}
```

---

## 7. Deployment Workflow

### 7.1 Pre-deploy Checklist

- [ ] Backup SQLite: `cp jarvis.db jarvis.db.backup.vercel-migration`
- [ ] Export schema+data: `sqlite3 jarvis.db .dump > dump.sql + schema.sql`  
- [ ] Create Supabase/Vercel Postgres free project
- [ ] Apply SQL to cloud DB — verify tables intact
- [ ] Set DATABASE_URL env var in Vercel → Project Settings
- [ ] Cloudflare tunnel configured, running, verified on Mac Mini
- [ ] `vercel.json` created with correct routes + env vars
- [ ] `api/proxy-ai.js` proxy functions built for all 3 AI endpoints
- [ ] Frontend dashboard HTML files prepared

### 7.2 Deploy Steps

```bash
cd ~/jarvis-hub/
npx vercel deploy --prod                  # initial prod deploy  
# OR: git push → auto-deploy if linked to Vercel Git integration
vercel aliasJarvis-dashboard.vercel.app   # optional custom alias/domain | 
```

### 7.3 Post-deploy Verification

1. Visit `https://jarvis-dashboard.vercel.app` — should show dashboard homepage
2. Test non-AI API: `curl https://jarvis-dashboard.vercel.app/api/health` → expects healthy response
3. Test AI proxy: `curl https://jarvis-dashboard.vercel.app/api/analyze?symbol=VIC` → **should fail with 503 if tunnel is down** (expected during dev), then verify working when tunnel active

---

## 8. Risk Mitigation & Fallbacks

| Risk                                   | Mitigation                                  |
|----------------------------------------|---------------------------------------------|
| Mac Mini sleep / offline             | Tunnel returns 503 gracefully; frontend shows "Local Jarvis Hub unavailable" toast/alert   |
| Vercel serverless timeout (~10s)      | AI analysis calls can take long; add timeout handling + retry with exponential backoff  |
| DB migration errors                    | Always backup → test on staging → prod deploy; keep old jarvis.db as fallbac | 
| Cloudflare tunnel drops              | cloudflared has auto-reconnect; also use `brew services start cloudflared` for persistent launch |  
| Vercel free tier limits               | 100GB bandwidth/mo, 500 invocations/day — should be fine for personal dashboard; monitor usage at dashboard.vercel.com/account  |  

---

## 9. Future Improvements (Post-launch MVP)

- [ ] Add WebSocket support for real-time signal streaming from Jarvis Hub → Vercel frontend
- [ ] Implement server-side caching for frequently accessed endpoints (/api/indices, /api/signals/latest) using Vercel edge cache headers (`Cache-Control: s-maxage=60`)
- [ ] Add basic auth / JWT token for dashboard access (prevent public exposure of watchlists and knowledge base)
- [ ] Auto-reconnect logic in frontend to detect tunnel status without user action | 
- [ ] Consider migrating RSS fetching from Vercel cron to a lightweight cloud function run on a schedule

---

## 10. File Structure (Post-Migration)

```
jarvis-hub/
├── dashboard/                    ← frontend (HTML/CSS/JS) for vercel deployment
│   ├── index.html
│   └── css/, js/ components
├── api/                          ← Vercel serverless functions
│   ├── health.js              | 
│   ├── proxy-ai.js            ← central proxy utility for AI endpoints
│   ├── search.js             | 
 │  ├── analyze.js            |     |
│   ├── market-evaluation.js  |     |    <-- all proxy to local Mac Mini
│   ├── signals.js             |  
│   ├── snapshots.js           |
│   └── cron/                  |
│       └── rss-fetch.js       ← scheduled news fetching (runs on Vercel, no local dependency)
├── core/                         ← local-only Python logic stays on Mac Mini
├── config.yaml                   ← unchanged
├── docs/
│   └── VERCEL_DEPLOYMENT_PLAN.md  ← THIS FILE
└── jarvis.db                     ← backup; cloud DB used in production
```

---

## Summary

| Aspect            | Current (Local Only)    | Target (Vercel Deployed)       |
|--------------------|--------------------------|----------------------------------|
| Frontend           | Served by Flask app     | Static on Vercel CDN           | 
| API endpoints      | All local Flask routes  | Split: non-AI → Vercel, AI → local Mac via tunnel | 
| Database           | SQLite (jarvis.db)      | PostgreSQL (Supabase/Vercel Postgres free tier) |
| LLM processing     | Local Ollama/Ollama       | Same — no change               |
| News fetching      | RSS via Flask cron      | Vercel Cron Job or Serverless function  
| Access             | localhost:8100 only     | jarvis-dashboard.vercel.app (global access)
| Availability       | Mac must be on          | Dashboard always up; AI features degrade gracefully when local machine is offline | 

---

**Status**: Draft v — ready for implementation.  
**Next step**: Confirm plan → proceed to migration & deployment.
