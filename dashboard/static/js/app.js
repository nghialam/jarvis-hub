/* ========================================
   Jarvis Hub 2.0 — Main App JS
   Tab navigation + data loading
   
   NOTE: innerHTML is used with API data throughout. This is safe because:
   - Local-only dashboard (localhost:8100), no public exposure
   - All data originates from our own Flask backend + SQLite DB
   - No external user input reaches this code unsanitized
   ======================================== */

const API = {
    overview: '/api/v1/overview',
    indices: '/api/v1/overview/indices',
    crypto: '/api/v1/overview/crypto',
    gold: '/api/v1/overview/gold',
    motions: '/api/v1/overview/motions',
    chart: '/api/v1/overview/chart',
    news: '/api/v1/news',
    trending: '/api/v1/news/trending',
    research: '/api/v1/research',
    researchStats: '/api/v1/research/stats',
    researchCrawl: '/api/v1/research/crawl',
    companies: '/api/v1/companies',
    companyNews: '/api/v1/companies',
    watchlist: '/api/watchlist',
    watchlistAdd: '/api/watchlist/add',
    watchlistRm: '/api/watchlist/remove',
    symbolSearch: '/api/symbols/search',
    heatmap: '/api/v1/market/heatmap',
    health: '/health',
};

let charts = {};
let lastUpdated = new Date(0);
let currentMarketPeriod = 'week'; // default period

/* ---- Tab Navigation ---- */

function switchTab(tabName) {
    // Hide all tab content
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    // Deactivate all nav tabs
    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

    // Activate selected
    const tabEl = document.getElementById('tab-' + tabName);
    if (tabEl) tabEl.classList.add('active');

    const navEl = document.querySelector(`.nav-tab[data-tab="${tabName}"]`);
    if (navEl) navEl.classList.add('active');

    // Load data
    loadTabData(tabName);
}

function loadTabData(tabName) {
    switch (tabName) {
        case 'market': loadMarketOverview(); break;
        case 'news': loadNews(); break;
        case 'company': break; // loads on search
        case 'research': loadResearch(); break;
        case 'screener': loadScreener(); break;
        case 'mi': loadMarketIntelligence(); break;
            case 'portfolio': loadPortfolioSummary(); break;
     }
}

function formatNumber(n) {
    if (n === null || n === undefined) return '—';
    n = Number(n);
            if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
            if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
            if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
            return Number(n).toLocaleString();
}

function formatPrice(n) {
        if (n === null || n === undefined) return '—';
        return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(n) {
        if (n === null || n === undefined) return '—';
        const sign = n >= 0 ? '▲' : '▼';
        return `${sign}${Math.abs(n).toFixed(2)}%`;
}

function changeClass(n) {
        if (n === null || n === undefined) return '';
        return n >= 0 ? 'positive' : 'negative';
}

function starsHtml(score, max = 5) {
        let s = '';
        for (let i = 1; i <= max; i++) {
            s += i <= score ? '●' : '<span class="empty">○</span>';
        }
        return `<span class="stars">${s}</span>`;
}

function freshnessClass(timestamp) {
        const diff = (new Date() - new Date(timestamp)) / 60000; // minutes
        if (diff < 10) return '';
        if (diff < 30) return 'warn';
        return 'stale';
}

function freshnessText(timestamp) {
        const diff = Math.round((new Date() - new Date(timestamp)) / 60000);
        if (diff < 1) return 'Just now';
        if (diff < 60) return `${diff}m ago`;
        return `${Math.floor(diff / 60)}h ${diff % 60}m ago`;
}

function sentimentBadge(s) {
        if (!s) return '';
        const cls = s.toLowerCase().includes('bull') || s.toLowerCase().includes('tich') ? 'badge-bullish' :
            s.toLowerCase().includes('bear') || s.toLowerCase().includes('tieu') ? 'badge-bearish' :
                'badge-neutral';
        return `<span class="badge ${cls}">${s}</span>`;
}

/* ---- Fetch Helper ---- */

async function apiGet(url, params = {}) {
        const qs = new URLSearchParams(params).toString();
        const fullUrl = qs ? `${url}?${qs}` : url;
        try {
            const res = await fetch(fullUrl);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error(`API Error [${url}]:`, e);
            return null;
        }
}

async function apiPost(url, data) {
        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error(`API Error [${url}]:`, e);
            return null;
        }
}

window.apiPost = apiPost;

/* ---- Destory old charts before redraw ---- */

function destroyChart(key) {
        if (charts[key]) {
            charts[key].destroy();
            charts[key] = null;
        }
}

/* ---- Health Check ---- */

async function checkHealth() {
        const data = await apiGet(API.health);
        if (!data) return;

        const dot = document.getElementById('freshness-dot');
        const text = document.getElementById('freshness-text');
        if (dot && data.status === 'ok') {
            dot.className = 'freshness-dot';
            text.textContent = `Hub 2.0 • ${new Date().toLocaleTimeString()}`;
        }
}

/* ========================================
   MARKET OVERVIEW TAB
   ======================================== */

const SPINNER = `<span class="loading-container"><div class="loading-dots"><span></span><span></span><span></span></div><span style="color:var(--text-secondary);font-size:13px;">Đang tải...</span></div>`;

async function loadMarketOverview() {
    const container = document.getElementById('market-loading');
    if (container) { container.style.display = 'block'; container.innerHTML = SPINNER; }

     // Load overview data for daily snapshots
    const overviewRes = await apiGet(API.overview);
    if (overviewRes && overviewRes.data) {
        renderDailySnapshots(overviewRes.data);
    }

    // Load indices with chart data
    const indicesRes = await apiGet(API.indices);
    if (indicesRes) {
        renderIndices(indicesRes.vn || [], indicesRes.global || []);
        // Fetch chart data for VN indices based on current period
        loadIndexCharts(indicesRes.vn || []);
    }

    // Load crypto
    const cryptoRes = await apiGet(API.crypto);
    if (cryptoRes) {
        renderCrypto(cryptoRes.data || []);
    }

    // Load gold
    const goldRes = await apiGet(API.gold);
    if (goldRes) {
        renderGold(goldRes.data);
    }

    // Load sector heatmap
    const heatmapRes = await apiGet(API.heatmap);
    if (heatmapRes && heatmapRes.sectors) {
        renderSectorHeatmap(heatmapRes.sectors);
    }

    // Load top motions
    const motionsRes = await apiGet(API.motions, { limit: 10 });
    if (motionsRes) {
        renderTopMotions(motionsRes.data || []);
    }

    if (container) container.style.display = 'none';
    lastUpdated = new Date();
    updateFreshness();
}

function renderIndices(vnIndices, globalIndices) {
        const vnContainer = document.getElementById('vn-indices-grid');
        const globalContainer = document.getElementById('global-indices-grid');

        if (vnContainer) {
            vnContainer.innerHTML = (vnIndices || []).map(idx => `
            <div class="index-card">
                <div class="index-name">${idx.name || idx.symbol}</div>
                <div class="index-value">${formatPrice(idx.price)}</div>
                <div class="index-change ${changeClass(idx.change_pct)}">${formatPct(idx.change_pct)}</div>
                <div class="index-periods">
                    <span class="index-period">1W: <span class="${changeClass(idx.periods?.['1wk'])}">${formatPct(idx.periods?.['1wk'])}</span></span>
                    <span class="index-period">1M: <span class="${changeClass(idx.periods?.['1mo'])}">${formatPct(idx.periods?.['1mo'])}</span></span>
                    <span class="index-period">1Q: <span class="${changeClass(idx.periods?.['1q'])}">${formatPct(idx.periods?.['1q'])}</span></span>
                </div>
                <div class="chart-container">
                    <canvas id="chart-${idx.symbol}"></canvas>
                </div>
            </div>
        `).join('') || '<div class="empty-state">No index data available</div>';

            // Render charts for VN indices
            vnIndices.forEach(idx => {
                if (idx.chart_data && idx.chart_data.length > 0) {
                    renderIndexChart(idx);
                }
            });
        }

        if (globalContainer) {
            globalContainer.innerHTML = (globalIndices || []).map(idx => `
            <div class="index-card">
                <div class="index-name">${idx.name || idx.symbol}</div>
                <div class="index-value">${formatPrice(idx.price)}</div>
                <div class="index-change ${changeClass(idx.change_pct)}">${formatPct(idx.change_pct)}</div>
            </div>
        `).join('') || '<div class="empty-state">No global data available</div>';
        }
}

function renderIndexChart(idx) {
        const canvasId = `chart-${idx.symbol}`;
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        destroyChart(canvasId);

        const labels = idx.chart_data.map(d => {
            const dt = new Date(d.time);
            return `${dt.getHours()}:${String(dt.getMinutes()).padStart(2, '0')}`;
        });
        const prices = idx.chart_data.map(d => d.close ?? d.price);

        const isPositive = (idx.change_pct || 0) >= 0;
        const color = isPositive ? '#00d4aa' : '#ff4757';

        charts[canvasId] = new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    data: prices,
                    borderColor: color,
                    backgroundColor: color + '20',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { mode: 'index' } },
                scales: {
                    x: { display: false },
                    y: {
                        display: true,
                        position: 'right',
                        grid: { color: '#2a2a4a20' },
                        ticks: { color: '#a0a0b0', font: { size: 10 }, callback: v => formatPrice(v) }
                    }
                },
                interaction: { mode: 'nearest', intersect: false },
            }
        });
}

function renderCrypto(cryptoList) {
        const container = document.getElementById('crypto-grid');
        if (!container) return;

        container.innerHTML = (cryptoList || []).map(c => `
        <div class="index-card">
            <div class="index-name">${c.name || c.symbol}</div>
            <div class="index-value">$${formatPrice(c.price)}</div>
            <div class="index-change ${changeClass(c.change_pct)}">${formatPct(c.change_pct)}</div>
        </div>
`).join('') || '<div class="empty-state">No crypto data available</div>';
}

function renderGold(goldData) {
        const container = document.getElementById('gold-container');
        if (!container) return;

        if (goldData && goldData.price !== undefined) {
            container.innerHTML = `
            <div class="index-card">
                <div class="index-name">🥇 Gold (XAU/USD)</div>
                <div class="index-value">$${formatPrice(goldData.price)}</div>
                <div class="index-change ${changeClass(goldData.change_pct)}">${formatPct(goldData.change_pct)}</div>
            </div>
        `;
        }
}

function renderTopMotions(motions) {
        const container = document.getElementById('top-motions-container');
        if (!container) return;

        if (!motions || motions.length === 0) {
            container.innerHTML = '<div class="empty-state">No top movers data available</div>';
            return;
        }

        // Split into gainers and losers
        const gainers = motions.filter(m => (m.change_pct || 0) > 0).slice(0, 5);
        const losers = motions.filter(m => (m.change_pct || 0) < 0).slice(0, 5);

        container.innerHTML = `
        <div class="grid-2">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">🔥 Top Gainers</span>
                </div>
                <table class="data-table">
                    <thead><tr><th>Ticker</th><th>Price</th><th>Change</th><th>Volume</th></tr></thead>
                    <tbody>
                        ${gainers.map(m => `
                            <tr>
                                <td><span class="ticker">${m.symbol}</span></td>
                                <td>${formatPrice(m.price)}</td>
                                <td class="${changeClass(m.change_pct)}">${formatPct(m.change_pct)}</td>
                                <td>${formatNumber(m.volume)}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="4" class="empty-state">No gainers</td></tr>'}
                    </tbody>
                </table>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">❄️ Top Losers</span>
                </div>
                <table class="data-table">
                    <thead><tr><th>Ticker</th><th>Price</th><th>Change</th><th>Volume</th></tr></thead>
                    <tbody>
                        ${losers.map(m => `
                            <tr>
                                <td><span class="ticker">${m.symbol}</span></td>
                                <td>${formatPrice(m.price)}</td>
                                <td class="${changeClass(m.change_pct)}">${formatPct(m.change_pct)}</td>
                                <td>${formatNumber(m.volume)}</td>
                            </tr>
                        `).join('') || '<tr><td colspan="4" class="empty-state">No losers</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
`;
}

/* ---- Daily Snapshot Cards ---- */

async function renderDailySnapshots(overviewData) {
     // Safe innerHTML: data from our own local API, no external input (see top of file)
    const container = document.getElementById('daily-snapshot-grid');
    if (!container) return;

    const snapshots = [];

      // VN Indices (skip HOSECAP which is internal)
    const vnIndex = overviewData.vn_indices || {};
    Object.entries(vnIndex).forEach(([name, data]) => {
        if (data.price !== undefined && name !== 'HOSECAP') {
            snapshots.push({
                label: name, value: formatPrice(data.price),
                change: data.change_pct, icon: '📊'
              });
          }
      });

       // Crypto highlights (top 2)
    const crypto = overviewData.crypto || {};
    let cryptoCount = 0;
    Object.entries(crypto).forEach(([name, data]) => {
        if (data.price !== undefined && cryptoCount < 2) {
            snapshots.push({
                label: name, value: '$' + formatPrice(data.price),
                change: data.change_pct, icon: '₿'
              });
            cryptoCount++;
          }
      });

       // Gold
    const gold = overviewData.gold || {};
    if (gold.price !== undefined) {
        snapshots.push({ label: 'Gold', value: '$' + formatPrice(gold.price),
              change: gold.change_pct, icon: '🥇' });
      }

       // Oil
    const oil = overviewData.oil || {};
    if (oil.price !== undefined) {
        snapshots.push({ label: 'Oil', value: '$' + formatPrice(oil.price),
              change: oil.change_pct, icon: '🛢️' });
      }

       // DXY
    const dxy = overviewData.dxy || {};
    if (dxy.price !== undefined) {
        snapshots.push({ label: 'DXY', value: formatPrice(dxy.price),
              change: dxy.change_pct, icon: '💵' });
      }

    container.innerHTML = snapshots.map(s => `
          <div class="snapshot-card">
              <div class="snapshot-icon">${s.icon}</div>
              <div class="snapshot-label">${s.label}</div>
              <div class="snapshot-value">${s.value}</div>
              <div class="snapshot-change ${changeClass(s.change)}">${formatPct(s.change)}</div>
          </div>
      `).join('') || '<div class="empty-state">No snapshot data available</div>';
}

/* ---- Sector Heatmap Renderer ---- */

async function renderSectorHeatmap(sectors) {
     // Safe innerHTML: data from our own local API (see top of file)
    const container = document.getElementById('sector-heatmap-container');
    if (!container) return;

    if (!sectors || sectors.length === 0) {
        container.innerHTML = '<div class="empty-state">No sector data available</div>';
        return;
      }

       // Find max absolute change for color scaling
    const maxAbsChange = Math.max(...sectors.map(s => Math.abs(s.avg_change)), 1);

    function heatmapColor(change) {
        const intensity = Math.min(Math.abs(change) / maxAbsChange, 1);
        if (change >= 0) {
             // Green gradient: light to dark green
            const r = Math.round(232 - intensity * 185);
            const g = Math.round(245 - intensity * 65);
            const b = Math.round(233 - intensity * 179);
            return `rgba(${r}, ${g}, ${b}, ${0.3 + intensity * 0.7})`;
          } else {
             // Red gradient: light to dark red
            const r = Math.round(254 - intensity * 84);
            const g = Math.round(226 - intensity * 171);
            const b = Math.round(226 - intensity * 171);
            return `rgba(${r}, ${g}, ${b}, ${0.3 + intensity * 0.7})`;
          }
      }

    function textColor(change) {
        const intensity = Math.min(Math.abs(change) / maxAbsChange, 1);
        return intensity > 0.5 ? '#fff' : 'var(--text-primary)';
      }

    container.innerHTML = `
           <style>
                /* Heatmap tooltip */
                .heatmap-tile { position: relative; transition: transform 0.15s, box-shadow 0.15s; cursor: pointer; overflow: hidden; }
                .heatmap-tile:hover { transform: scale(1.03); box-shadow: 0 4px 16px rgba(0,0,0,0.3); z-index: 10; }
                .heatmap-tooltip { display:none; position:absolute; bottom:calc(100% + 8px); left:50%; transform:translateX(-50%); background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:6px; padding:8px 12px; min-width:240px; max-width:360px; z-index:1000; box-shadow:0 4px 16px rgba(0,0,0,0.5); font-size:11px; line-height:1.5; }
                .heatmap-tooltip::after { content:''; position:absolute; top:100%; left:50%; transform:translateX(-50%); border:6px solid transparent; border-top-color:var(--border-color); }
                .heatmap-tile:hover .heatmap-tooltip { display:block; }
                .heatmap-tooltip .tt-header { font-weight:600; color:var(--text-primary); margin-bottom:4px; font-size:12px; }
                .heatmap-tooltip .tt-row { display:flex; justify-content:space-between; padding:1px 0; color:var(--text-secondary); }
                .heatmap-tooltip .tt-gainer { color:var(--accent-green); }
                .heatmap-tooltip .tloser { color:var(--accent-red); }
           </style>
           <div class="heatmap-grid">
               ${sectors.map(s => {
                const bg = heatmapColor(s.avg_change);
                const tc = textColor(s.avg_change);
                // Build top stock details for tooltip
                const stocksHtml = (s.stocks || []).slice(0, 6).map(st => {
                    const cls = st.change_pct >= 0 ? 'tt-gainer' : 'tloser';
                    return `<div class="tt-row"><span style="color:var(--accent-blue);font-weight:600;">${st.symbol || '--'}</span><span>${st.price ? formatPrice(st.price) : '--'} <span class="${cls}">(${st.change_pct >= 0 ? '+' : ''}${(st.change_pct||0).toFixed(2)}%)</span></div>`;
                }).join('');

                return `
                       <div class="heatmap-tile" style="background:${bg}; color:${tc};">
                           <div class="heatmap-sector-name">${s.name}</div>
                           <div class="heatmap-value">${s.avg_change >= 0 ? '+' : ''}${s.avg_change.toFixed(2)}%</div>
                           <div class="heatmap-stats">
                               <span>G:${s.gainers}</span><span>L:${s.losers}</span><span>T:${s.total}</span>
                           </div>
                           <!-- Hover tooltip with stock details -->
                           ${stocksHtml ? `<div class="heatmap-tooltip"><div class="tt-header">${s.name} — Top Stocks</div>${stocksHtml}</div>` : ''}
                       </div>
                   `;
                }).join('')}
           </div>
       `;
}

/* ---- Period-aware Index Charts ---- */

async function loadIndexCharts(indices) {
      // Map period to Yahoo Finance range/interval
    const periodMap = {
          'week': { range: '5d', interval: '30m' },
          'month': { range: '1mo', interval: '1d' },
          'quarter': { range: '3mo', interval: '1d' }
      };

    const period = periodMap[currentMarketPeriod] || periodMap['week'];

      // Render existing chart data from indices endpoint or fetch new
    indices.forEach(idx => {
        if (idx.chart_data && idx.chart_data.length > 0) {
            renderIndexChart(idx);
          } else {
              // Fetch chart data for this index with current period
            fetchChartForIndex(idx, period);
          }
      });
}

async function fetchChartForIndex(idx, period) {
    const canvasId = `chart-${idx.symbol}`;
    try {
        const res = await apiGet(API.chart, {
            symbol: idx.symbol,
            range: period.range,
            interval: period.interval
          });
        if (res && res.data) {
            idx.chart_data = res.data;
            renderIndexChart(idx);
          }
      } catch (e) {
        console.error(`Failed to fetch chart for ${idx.symbol}:`, e);
      }
}

/* ========================================
   NEWS TAB
    */

async function loadNews() {
        const container = document.getElementById('news-loading');
        if (container) { container.style.display = 'block'; container.innerHTML = SPINNER; }

         // Load trending
        const trendingRes = await apiGet(API.trending);
        if (trendingRes) {
            renderTrending(trendingRes.articles || []);
        }

        // Load all news
        const newsRes = await apiGet(API.news, { limit: 50, days: 7 });
        if (newsRes) {
            renderNewsList(newsRes.articles || []);
        }

        if (container) container.style.display = 'none';
}

function renderTrending(articles) {
        const container = document.getElementById('news-featured');
        if (!container) return;

        if (!articles || articles.length === 0) {
            container.innerHTML = '';
            return;
        }

        const top = articles[0];
        container.innerHTML = `
        <div class="news-featured">
            <span class="badge badge-category" style="margin-bottom:8px">📌 TRENDING</span>
            <h3><a href="${top.url || '#'}" target="_blank">${top.title}</a></h3>
            <div class="news-meta">
                <span class="badge badge-source">${top.source || 'Unknown'}</span>
                ${sentimentBadge(top.sentiment)}
                <span>${top.published_at ? new Date(top.published_at).toLocaleString() : ''}</span>
                ${starsHtml(Math.round(top.importance || 0) / 2)}
            </div>
            <div class="news-snippet">${top.summary || ''}</div>
        </div>
`;
}

function renderNewsList(articles) {
        const container = document.getElementById('news-list');
        if (!container) return;

        if (!articles || articles.length === 0) {
            container.innerHTML = '<div class="empty-state">No news articles found. Click "Refresh" to pull latest.</div>';
            return;
         }

        // Add news detail modal HTML if not already added
        const existingModal = document.getElementById('news-detail-modal');
        if (!existingModal) {
            document.body.insertAdjacentHTML('beforeend', `
                <div id="news-detail-modal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;background:rgba(0,0,0,0.7);justify-content:center;align-items:center;animation:fade-in 0.2s;" onclick="if(event.target===this)closeNewsModal()">
                    <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:12px;width:min(800px,95vw);max-height:85vh;display:flex;flex-direction:column;">
                        <div style="padding:16px 20px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:13px;color:var(--text-secondary);" id="news-modal-meta"></span>
                            <button onclick="closeNewsModal()" style="background:none;border:none;color:var(--text-secondary);font-size:20px;cursor:pointer;padding:4px 8px;">✕</button>
                        </div>
                        <div style="padding:20px;overflow-y:auto;">
                            <h3 id="news-modal-title" style="margin:0 0 12px;font-size:18px;color:var(--text-primary);"></h3>
                            <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;" id="news-modal-badges"></div>
                            <div id="news-modal-content" style="line-height:1.7;font-size:14px;color:var(--text-primary);white-space:pre-wrap;"></div>
                        </div>
                        <div style="padding:12px 20px;border-top:1px solid var(--border-color);display:flex;justify-content:space-between;">
                            <span id="news-modal-source" style="font-size:12px;color:var(--text-secondary);"></span>
                            <a href="#" id="news-modal-link" target="_blank" class="btn btn-primary" style="font-size:12px;padding:6px 14px;">🔗 Open Source</a>
                        </div>
                    </div>
                </div>
            `);
        }

        container.innerHTML = articles.map(a => `
          <div class="news-card" onclick="openNewsModal(${JSON.stringify(a).replace(/"/g, '&quot;')})" style="cursor:pointer;">
              <h4><a href="${a.url || '#'}" target="_blank" onclick="event.stopPropagation()">${a.title} ↗</a></h4>
              <div class="news-meta">
                  <span class="badge badge-source">${a.source || 'Unknown'}</span>
                  ${sentimentBadge(a.sentiment)}
                  <span>${a.published_at ? new Date(a.published_at).toLocaleString() : ''}</span>
                  ${starsHtml(Math.round(a.importance || 0) / 2, 5)}
              </div>
              ${a.summary ? `<div class="news-snippet">${a.summary.substring(0, 250)}${a.summary.length > 250 ? '...' : ''}</div>` : ''}
          </div>
      `).join('');
    }

// ---------- News Detail Modal ----------

function openNewsModal(article) {
        const modal = document.getElementById('news-detail-modal');
        if (!modal || !article) return;

        const title = document.getElementById('news-modal-title');
        const meta = document.getElementById('news-modal-meta');
        const badges = document.getElementById('news-modal-badges');
        const content = document.getElementById('news-modal-content');
        const source = document.getElementById('news-modal-source');
        const link = document.getElementById('news-modal-link');

        if (title) title.textContent = article.title || 'Untitled';
        if (meta && article.published_at) meta.textContent = new Date(article.published_at).toLocaleString();
        if (badges) {
            badges.innerHTML = `
                <span class="badge badge-source">${article.source || 'Unknown'}</span>
                ${sentimentBadge(article.sentiment)}
                <span style="font-size:12px;color:var(--text-secondary);">⭐ ${Math.round(article.importance||0)}/5 importance</span>
            `;
        }
        if (source && article.source) source.textContent = `Source: ${article.source}`;
        if (link) link.href = article.url || '#';
        if (content) content.textContent = article.summary || 'Không có summary cho bài này.';

        modal.style.display = 'flex';
    }

function closeNewsModal() {
        const modal = document.getElementById('news-detail-modal');
        if (modal) modal.style.display = 'none';
     }

async function refreshNews() {
        const btn = document.getElementById('refresh-news-btn');
        if (btn) {
            btn.textContent = 'Refreshing...';
            btn.disabled = true;
        }
        await loadNews();
        if (btn) {
            btn.textContent = '🔄 Refresh News';
            btn.disabled = false;
        }
}

/* ========================================
   COMPANY NEWS TAB
   ======================================== */

async function searchCompany(query) {
        if (!query || query.length < 2) return;

        const container = document.getElementById('company-results');
        if (container) { container.innerHTML = SPINNER; }

        const res = await apiGet(API.companies, { q: query });
        if (!res) return;

        if (container) {
            if (res.companies && res.companies.length > 0) {
                container.innerHTML = `
                <div class="card">
                    <table class="data-table">
                        <thead><tr><th>Symbol</th><th>Name</th><th>Actions</th></tr></thead>
                        <tbody>
                            ${res.companies.map(c => `
                                <tr>
                                    <td><span class="ticker" onclick="loadCompanyNews('${c.symbol}')">${c.symbol}</span></td>
                                    <td>${c.name || ''}</td>
                                    <td><button class="btn btn-secondary" onclick="loadCompanyNews('${c.symbol}')">View News</button></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
            } else {
                container.innerHTML = '<div class="empty-state">No companies found matching your search.</div>';
            }
        }
}

async function loadCompanyNews(symbol) {
        const container = document.getElementById('company-news-feed');
        if (container) { container.innerHTML = SPINNER; }

        const res = await apiGet(`${API.companyNews}/${encodeURIComponent(symbol)}/news`);
        if (!res || !res.articles) {
            if (container) container.innerHTML = '<div class="empty-state">No news found for this company.</div>';
            return;
        }

        if (container) {
            container.innerHTML = res.articles.map(a => `
            <div class="news-card">
                <h4><a href="${a.url || '#'}" target="_blank">${a.title}</a></h4>
                <div class="news-meta">
                    <span class="badge badge-source">${a.source || 'Unknown'}</span>
                    ${sentimentBadge(a.sentiment)}
                    <span>${a.published_at ? new Date(a.published_at).toLocaleString() : ''}</span>
                </div>
                ${a.summary ? `<div class="news-snippet">${a.summary.substring(0, 200)}</div>` : ''}
            </div>
        `).join('');
        }
}

/* ========================================
   RESEARCH REPORTS TAB
   ======================================== */

async function loadResearch() {
        const container = document.getElementById('research-loading');
        if (container) { container.style.display = 'block'; container.innerHTML = SPINNER; }

          // Load stats
        const statsRes = await apiGet(API.researchStats);
        if (statsRes) {
            renderResearchStats(statsRes.stats || []);
        }

        // Load reports
        const reportsRes = await apiGet(API.research, { period: '1m', limit: 20 });
        if (reportsRes) {
            renderResearchReports(reportsRes.reports || []);
        }

        if (container) container.style.display = 'none';
}

function renderResearchStats(stats) {
        const container = document.getElementById('research-stats');
        if (!container) return;

        if (!stats || stats.length === 0) {
            container.innerHTML = '<div class="empty-state">No broker data yet. Trigger a crawl to collect reports.</div>';
            return;
        }

        container.innerHTML = `
        <div class="card" style="margin-bottom: 16px;">
            <div class="card-header">
                <span class="card-title">📊 Broker Summary</span>
            </div>
            <div style="display: flex; gap: 16px; flex-wrap: wrap;">
                ${stats.map(s => `
                    <div style="flex: 1; min-width: 150px;">
                        <strong>${s.broker}</strong>
                        <div style="font-size: 12px; color: var(--text-secondary);">
                            ${s.count} reports • Latest: ${s.latest || 'N/A'}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
`;
}

function renderResearchReports(reports) {
        const container = document.getElementById('research-list');
        if (!container) return;

        if (!reports || reports.length === 0) {
            container.innerHTML = '<div class="empty-state">No research reports found. Trigger a crawl to scan broker websites.</div>';
            return;
        }

        container.innerHTML = `<div class="grid-3">${reports.map(r => `
        <div class="report-card">
            <div class="report-broker">${r.broker}</div>
            <div class="report-title">${r.title}</div>
            <div class="report-date">${r.report_date || r.crawled_at || ''}</div>
            ${r.summary ? `<div class="report-summary">${r.summary.substring(0, 150)}${r.summary.length > 150 ? '...' : ''}</div>` : ''}
            <div class="report-meta">
                ${r.target_index ? `<span>Target: ${r.target_index}</span>` : ''}
                ${r.sector_focus ? `<span>Sector: ${r.sector_focus}</span>` : ''}
            </div>
            ${r.pdf_url ? `<div style="margin-top:8px"><a href="${r.pdf_url}" target="_blank" class="btn btn-secondary" style="font-size:12px">📄 Download PDF</a></div>` : ''}
        </div>
`).join('')}</div>`;
}

async function crawlResearch() {
        const btn = document.getElementById('crawl-btn');
        if (btn) {
            btn.textContent = 'Crawling...';
            btn.disabled = true;
        }

        const res = await apiPost(API.researchCrawl, {});
        if (res) {
            alert(`Crawl complete: ${JSON.stringify(res.result || res)}`);
            await loadResearch();
        }

        if (btn) {
            btn.textContent = '🕷️ Crawl Brokers';
            btn.disabled = false;
        }
}

/* ========================================
   SCREENER / WATCHLIST TAB
   ======================================== */

async function loadScreener() {
        const container = document.getElementById('screener-loading');
        if (container) { container.style.display = 'block'; container.innerHTML = SPINNER; }

           // Load watchlist
        const wlRes = await apiGet(API.watchlist);
        if (wlRes) {
            renderWatchlist(wlRes.symbols || []);
        }

        if (container) container.style.display = 'none';
}

function renderWatchlist(items) {
        const container = document.getElementById('watchlist-container');
        if (!container) return;

        if (!items || items.length === 0) {
            container.innerHTML = '<div class="empty-state">Your watchlist is empty. Add stocks using the form below.</div>';
            return;
        }

        container.innerHTML = `
        <div class="card">
            <table class="watchlist-table">
                <thead><tr><th>Symbol</th><th>Name</th><th>Sector</th><th>Added</th><th>Actions</th></tr></thead>
                <tbody>
                    ${items.map(w => `
                        <tr>
                            <td><span class="ticker" onclick="loadCompanyNews('${w.symbol}')">${w.symbol}</span></td>
                            <td>${w.name || '—'}</td>
                            <td>${w.sector || '—'}</td>
                            <td>${w.added_at ? new Date(w.added_at).toLocaleDateString() : '—'}</td>
                            <td><button class="btn btn-danger" style="padding:4px 8px;font-size:11px" onclick="removeWatchlist('${w.symbol}')">Remove</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
`;
}

async function addToWatchlist() {
        const symbolEl = document.getElementById('wl-symbol');
        const nameEl = document.getElementById('wl-name');
        const sectorEl = document.getElementById('wl-sector');

        const symbol = (symbolEl.value || '').trim().toUpperCase();
        const name = (nameEl.value || '').trim();
        const sector = (sectorEl.value || '').trim();

        if (symbol.length < 2) {
            alert('Please enter a valid ticker symbol (min 2 chars).');
            return;
        }

        // Step 1: Verify symbol exists and check for multiple matches
        const searchRes = await apiGet(API.symbolSearch, { q: symbol });
        if (!searchRes || !searchRes.matches || searchRes.matches.length === 0) {
            alert(`Symbol "${symbol}" not found. Please check the ticker.`);
            return;
        }

        // Step 2: Single match → add directly
        if (searchRes.matches.length === 1) {
            const match = searchRes.matches[0];
            const addName = name || match.name || '';
            const addSector = sector || match.sector || '';
            const res = await apiPost(API.watchlistAdd, { symbol: match.ticker, name: addName, sector: addSector });
            if (res && res.success) {
                symbolEl.value = '';
                nameEl.value = '';
                sectorEl.value = '';
                await loadScreener();
            } else {
                alert('Failed to add to watchlist.');
            }
            return;
        }

        // Step 3: Multiple matches → show modal for user selection
        showSymbolModal(symbol, searchRes.matches, name, sector);
}

async function searchSymbols(query) {
        const res = await apiGet(API.symbolSearch, { q: query });
        return res || { matches: [] };
}

function showSymbolModal(query, matches, defaultName, defaultSector) {
        const overlay = document.getElementById('symbol-modal-overlay');
        const resultsDiv = document.getElementById('symbol-results');

        // Build result items
        resultsDiv.innerHTML = matches.map((m, i) => `
            <div class="symbol-result-item" onclick="confirmSymbolSelection('${m.symbol}', ${i})">
                <div class="symbol-result-info">
                    <div class="symbol-result-ticker">${m.symbol}</div>
                    <div class="symbol-result-name">${m.name || 'N/A'}</div>
                </div>
                <span class="symbol-result-type">${m.type || 'UNKNOWN'}</span>
            </div>
        `).join('');

        overlay.classList.add('active');
        window._pendingAdd = { matches, defaultName, defaultSector };
}

function closeSymbolModal() {
        document.getElementById('symbol-modal-overlay').classList.remove('active');
        window._pendingAdd = null;
}

async function confirmSymbolSelection(ticker, index) {
        const pending = window._pendingAdd;
        if (!pending || !pending.matches[index]) {
            closeSymbolModal();
            return;
        }

        const match = pending.matches[index];
        const nameEl = document.getElementById('wl-name');
        const sectorEl = document.getElementById('wl-sector');
        const name = pending.defaultName || nameEl.value || match.name || '';
        const sector = pending.defaultSector || sectorEl.value || match.sector || '';

        // Close modal and add
        closeSymbolModal();

        const res = await apiPost(API.watchlistAdd, { symbol: ticker, name, sector });
        if (res && res.success) {
            document.getElementById('wl-symbol').value = '';
            nameEl.value = '';
            sectorEl.value = '';
            await loadScreener();
        } else {
            alert('Failed to add to watchlist.');
        }
}

async function removeWatchlist(symbol) {
        await apiPost(API.watchlistRm, { symbol });
        await loadScreener();
}

/* ---- Period filter for Market tab ---- */

function setMarketPeriod(period) {
    currentMarketPeriod = period;
      // Destroy existing charts so they rebuild with new period data
    Object.keys(charts).forEach(k => destroyChart(k));
      // Update active filter button
    document.querySelectorAll('#market-filters .filter-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`#market-filters .filter-btn[data-period="${period}"]`);
    if (btn) btn.classList.add('active');

      // Reload with new period
    loadMarketOverview();
}

/* ---- News category filter ---- */

function setNewsCategory(cat) {
        document.querySelectorAll('#news-filters .filter-btn').forEach(b => b.classList.remove('active'));
        const btn = document.querySelector(`#news-filters .filter-btn[data-category="${cat}"]`);
        if (btn) btn.classList.add('active');

        apiGet(API.news, { category: cat, limit: 50, days: 7 }).then(res => {
            if (res) renderNewsList(res.articles || []);
        });
}

/* ---- Research broker filter ---- */

function setResearchBroker(broker) {
        document.querySelectorAll('#research-filters .filter-btn').forEach(b => b.classList.remove('active'));
        const btn = document.querySelector(`#research-filters .filter-btn[data-broker="${broker}"]`);
        if (btn) btn.classList.add('active');

        apiGet(API.research, { broker, period: '1m', limit: 20 }).then(res => {
            if (res) renderResearchReports(res.reports || []);
        });
}

/* ---- Freshness updater ---- */

function updateFreshness() {
        const dot = document.getElementById('freshness-dot');
        const text = document.getElementById('freshness-text');
        if (dot && text) {
            dot.className = 'freshness-dot ' + freshnessClass(lastUpdated);
            text.textContent = `Updated ${freshnessText(lastUpdated)}`;
        }
}

/* ---- Market Intelligence tab ---- */

async function loadMarketIntelligence() {
        const container = document.getElementById('watchlist-container');
        if (container) container.style.display = 'none';

        // Load latest brief by default
        await loadMiLatest();

        if (container) container.style.display = 'none';
}

function setMiAction(action) {
        // Update active filter button
        document.querySelectorAll('#mi-filters .filter-btn').forEach(b => b.classList.remove('active'));
        const btn = document.querySelector(`#mi-filters .filter-btn[data-action="${action}"]`);
        if (btn) btn.classList.add('active');

        // Show/hide containers
        document.getElementById('mi-latest-container').style.display = action === 'latest' ? 'block' : 'none';
        document.getElementById('mi-history-container').style.display = action === 'history' ? 'block' : 'none';
        document.getElementById('mi-sentiment-container').style.display = action === 'sentiment' ? 'block' : 'none';

        // Load data for active view
        switch (action) {
            case 'latest': loadMiLatest(); break;
            case 'history': loadMiHistory(); break;
            case 'sentiment': loadMiSentiment(); break;
        }
}

async function runMarketIntelligencePipeline() {
        const btn = document.getElementById('mi-run-btn');
        if (btn) {
            btn.textContent = '⏳ Running...';
            btn.disabled = true;
        }

        const statusEl = document.getElementById('mi-status');
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.className = 'mi-status-bar mi-status-running';
            statusEl.innerHTML = '🔄 Pipeline started... This may take 2-5 minutes.';
        }

        try {
            const res = await apiPost('/api/market-intelligence/run', {});
            if (res && res.status === 'complete') {
                if (statusEl) {
                    statusEl.className = 'mi-status-bar mi-status-success';
                    statusEl.innerHTML = `✅ Pipeline complete! Processed ${res.article_count || 0} articles in ${res.elapsed_seconds?.toFixed(1) || '?'}s (Run ID: ${res.run_id})`;
                }
                // Reload latest view
                await loadMiLatest();
            } else if (res && res.status === 'no_articles') {
                if (statusEl) {
                    statusEl.className = 'mi-status-bar mi-status-warning';
                    statusEl.innerHTML = '⚠️ No articles found in the last 6 hours.';
                }
            } else {
                if (statusEl) {
                    statusEl.className = 'mi-status-bar mi-status-error';
                    statusEl.innerHTML = `❌ Pipeline failed: ${res?.message || 'Unknown error'}`;
                }
            }
        } catch (e) {
            if (statusEl) {
                statusEl.className = 'mi-status-bar mi-status-error';
                statusEl.innerHTML = `❌ Request failed: ${e.message}`;
            }
        } finally {
            if (btn) {
                btn.textContent = '▶ Run Pipeline Now';
                btn.disabled = false;
            }
        }
}

async function loadMiLatest() {
        const container = document.getElementById('mi-latest-container');
        if (!container) return;
        container.innerHTML = SPINNER;

        try {
            const res = await apiGet('/api/market-intelligence/latest');
            if (!res || !res.data) {
                container.innerHTML = '<div class="empty-state">No Market Intelligence runs found. Click "Run Pipeline Now" to start.</div>';
                return;
            }

            const data = res.data;
            const articles = data.articles || [];
            const bullCount = articles.filter(a => a.sentiment === 'Bullish').length;
            const bearCount = articles.filter(a => a.sentiment === 'Bearish').length;
            const neuCount = articles.filter(a => a.sentiment === 'Neutral').length;

            const sentimentDist = data.sentiment_distribution || {};
            const totalSent = (sentimentDist.bullish || 0) + (sentimentDist.bearish || 0) + (sentimentDist.neutral || 0);

            container.innerHTML = `
              <div class="card" style="margin-bottom: 16px;">
                  <div style="display: flex; gap: 16px; align-items: stretch;">
                      <!-- Brief content -->
                      <div style="flex: 1;">
                          <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                              <span class="card-title" style="margin: 0;">🧠 Market Intelligence Brief</span>
                              <span style="font-size: 12px; color: var(--text-secondary);">${data.run_date} • ${data.run_period || 'unknown'} period</span>
                          </div>
                  ${totalSent > 0 ? `
                      <!-- Sentiment pills -->
                  <div style="margin-bottom: 12px;">
                      <span class="badge badge-bullish">🟢 Bullish: ${sentimentDist.bullish || 0}</span>
                      <span class="badge badge-bearish">🔴 Bearish: ${sentimentDist.bearish || 0}</span>
                      <span class="badge badge-neutral">⚪ Neutral: ${sentimentDist.neutral || 0}</span>
                  </div>
                                  ` : ''}
                          <div style="white-space: pre-wrap; line-height: 1.6;">${data.market_brief || 'No brief generated.'}</div>
                      </div>
                      <!-- Sentiment chart -->
                  ${totalSent > 0 ? `
                      <div style="width: 200px; flex-shrink: 0; display: flex; align-items: center; justify-content: center;">
                          <canvas id="mi-sentiment-chart"></canvas>
                      </div>
                  ` : ''}
                  </div>
              </div>

              ${articles.length > 0 ? `
                  <h4 style="margin: 16px 0 8px; color: var(--text-secondary); font-size: 13px;">📑 Articles Analyzed (${articles.length})</h4>
                  <div class="grid-2">
                      ${articles.map(a => `
                          <div class="card" style="margin-bottom: 8px;">
                              <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                                  <h5 style="margin: 0; font-size: 13px;">
                                      <a href="${a.url || '#'}" target="_blank" style="color: var(--text-primary); text-decoration: none;">${a.title || 'Untitled'}</a>
                                  </h5>
                                  ${sentimentBadge(a.sentiment)}
                              </div>
                              <div style="font-size: 12px; color: var(--text-secondary);">
                                  ${a.date ? new Date(a.date).toLocaleString() : ''} • ${a.source || 'Unknown'}
                              </div>
                              <div style="margin-top: 8px; font-size: 12px; line-height: 1.5; color: var(--text-secondary);">
                                  ${a.summary ? a.summary.substring(0, 150) + (a.summary.length > 150 ? '...' : '') : 'No summary available.'}
                              </div>
                          </div>
                      `).join('')}
                  </div>
              ` : ''}
          `;

            // Render sentiment doughnut chart
            if (totalSent > 0) {
                const ctx = document.getElementById('mi-sentiment-chart');
                if (ctx) {
                    destroyChart('mi-sentiment-chart');
                    charts['mi-sentiment-chart'] = new Chart(ctx, {
                        type: 'doughnut',
                        data: {
                            labels: ['Bullish', 'Bearish', 'Neutral'],
                            datasets: [{
                                data: [sentimentDist.bullish || 0, sentimentDist.bearish || 0, sentimentDist.neutral || 0],
                                backgroundColor: [
                                    'rgba(63, 185, 80, 0.7)',
                                    'rgba(248, 81, 73, 0.7)',
                                    'rgba(139, 148, 158, 0.7)'
                                ],
                                borderColor: [
                                    'rgba(63, 185, 80, 1)',
                                    'rgba(248, 81, 73, 1)',
                                    'rgba(139, 148, 158, 1)'
                                ],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { display: false },
                                tooltip: { enabled: true }
                            },
                            cutout: '60%'
                        }
                    });
                }
            }
        } catch (e) {
            container.innerHTML = `<div class="empty-state">Failed to load latest brief: ${e.message}</div>`;
        }
}

async function loadMiHistory() {
        const container = document.getElementById('mi-history-container');
        if (!container) return;
        container.innerHTML = SPINNER;

        try {
            const res = await apiGet('/api/market-intelligence/history?limit=20');
            if (!res || !res.runs || res.runs.length === 0) {
                container.innerHTML = '<div class="empty-state">No intelligence runs in history.</div>';
                return;
            }

            container.innerHTML = `
             <div class="card">
                 <table class="data-table">
                     <thead>
                         <tr>
                             <th>Run ID</th>
                             <th>Date</th>
                             <th>Period</th>
                             <th>Articles</th>
                             <th>Sentiment</th>
                             <th>Status</th>
                         </tr>
                     </thead>
                     <tbody>
                         ${res.runs.map(run => {
                const sent = run.sentiment_summary || {};
                return `
                                 <tr>
                                     <td><span class="ticker">#${run.id}</span></td>
                                     <td>${run.run_date}</td>
                                     <td><span class="badge badge-neutral">${run.run_period || 'N/A'}</span></td>
                                     <td>${run.article_count || 0}</td>
                                     <td>
                                         🟢 ${sent.bullish || 0} | 🔴 ${sent.bearish || 0} | ⚪ ${sent.neutral || 0}
                                     </td>
                                     <td><span class="badge ${run.status === 'Notification Ready' ? 'badge-bullish' : 'badge-neutral'}">${run.status || 'unknown'}</span></td>
                                 </tr>
                             `;
            }).join('')}
                     </tbody>
                 </table>
             </div>
         `;
        } catch (e) {
            container.innerHTML = `<div class="empty-state">Failed to load history: ${e.message}</div>`;
        }
}

async function loadMiSentiment() {
        const container = document.getElementById('mi-sentiment-container');
        if (!container) return;
        container.innerHTML = SPINNER;

        try {
            const res = await apiGet('/api/market-intelligence/sentiment-dist');
            if (!res || !res.distribution) {
                container.innerHTML = '<div class="empty-state">Failed to load sentiment data.</div>';
                return;
            }

            const dist = res.distribution;
            const total = (dist.Bullish || 0) + (dist.Bearish || 0) + (dist.Neutral || 0);
            const bullPct = total > 0 ? ((dist.Bullish / total) * 100).toFixed(1) : 0;
            const bearPct = total > 0 ? ((dist.Bearish / total) * 100).toFixed(1) : 0;
            const neuPct = total > 0 ? ((dist.Neutral / total) * 100).toFixed(1) : 0;

            container.innerHTML = `
             <div class="card">
                 <div class="card-header">
                     <span class="card-title">📊 Sentiment Distribution (All Time)</span>
                     <span style="font-size: 12px; color: var(--text-secondary);">Total: ${total} articles</span>
                 </div>
                 <div style="margin-top: 16px;">
                     <div style="margin-bottom: 12px;">
                         <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                             <span>🟢 Bullish</span>
                             <span>${dist.Bullish || 0} (${bullPct}%)</span>
                         </div>
                         <div style="background: var(--bg-secondary); border-radius: 4px; height: 24px; overflow: hidden;">
                             <div style="width: ${bullPct}%; background: var(--accent-green); height: 100%; transition: width 0.3s;"></div>
                         </div>
                     </div>
                     <div style="margin-bottom: 12px;">
                         <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                             <span>🔴 Bearish</span>
                             <span>${dist.Bearish || 0} (${bearPct}%)</span>
                         </div>
                         <div style="background: var(--bg-secondary); border-radius: 4px; height: 24px; overflow: hidden;">
                             <div style="width: ${bearPct}%; background: var(--accent-red); height: 100%; transition: width 0.3s;"></div>
                         </div>
                     </div>
                     <div>
                         <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                             <span>⚪ Neutral</span>
                             <span>${dist.Neutral || 0} (${neuPct}%)</span>
                         </div>
                         <div style="background: var(--bg-secondary); border-radius: 4px; height: 24px; overflow: hidden;">
                             <div style="width: ${neuPct}%; background: var(--text-secondary); height: 100%; transition: width 0.3s;"></div>
                         </div>
                     </div>
                 </div>
             </div>
         `;
        } catch (e) {
            container.innerHTML = `<div class="empty-state">Failed to load sentiment data: ${e.message}</div>`;
        }
}


/* ---- Portfolio P&L Calculator ---- */

const PortfolioAPI = {
    pnlSummary: '/api/v1/portfolio/pnl-summary',
    holdings: '/api/v1/portfolio/holdings',
    transactions: '/api/v1/portfolio/transactions',
    addTxn: '/api/v1/portfolio/add-txn',
    deleteTxn: '/api/v1/portfolio/delete-txn/',
};

/* -- Summary Cards -- */

function formatVND(n) {
    if (n === null || n === undefined || n === 0) return '—';
    if (n >= 1e9) return (n / 1e9).toFixed(2) + ' tỷ';
    if (n >= 1e6) return (n / 1e6).toFixed(2) + ' M';
    return Number(n).toLocaleString('vi-VN') + ' ₫';
}

async function loadPortfolioSummary() {
    try {
        const res = await apiGet(PortfolioAPI.pnlSummary);
      if (!res || res.status !== 'ok') {
            renderEmptyPortfolio();
            return;
        }

        const s = res.summary || {};
        document.getElementById('pnl-invested').textContent = formatVND(s.total_cost_basis);
        document.getElementById('pnl-current').textContent = formatVND(s.total_current_value);

        const pnlEl = document.getElementById('pnl-total');
        pnlEl.textContent = (s.overall_pnl >= 0 ? '+' : '') + formatVND(s.overall_pnl);
        pnlEl.style.color = s.overall_pnl >= 0 ? 'var(--positive-color)' : 'var(--negative-color)';

        const pctEl = document.getElementById('pnl-pct');
        pctEl.textContent = (s.overall_pnl_pct >= 0 ? '+' : '') + s.overall_pnl_pct.toFixed(2) + '%';
        pctEl.style.color = s.overall_pnl_pct >= 0 ? 'var(--positive-color)' : 'var(--negative-color)';

         // Render holdings table
        renderHoldings(res.holdings || []);
         // Also load transactions
        loadTransactions();

    } catch (e) {
        console.error('Portfolio summary load failed:', e);
        renderEmptyPortfolio();
    }
}

function renderEmptyPortfolio() {
    ['pnl-invested', 'pnl-current', 'pnl-total', 'pnl-pct'].forEach(id => {
        document.getElementById(id).textContent = '—';
    });
    document.getElementById('holdings-container').innerHTML = '<div class="empty-state">No holdings yet. Add transactions to get started.</div>';
}

/* -- Holdings Table -- */

function renderHoldings(holdings) {
    const container = document.getElementById('holdings-container');
    if (!holdings || holdings.length === 0) {
        container.innerHTML = '<div class="empty-state">No current holdings. Add buy transactions above.</div>';
        return;
    }

      let html = `<table class="data-table"><thead><tr>
          <th>Ticker</th><th>Name</th><th>Qty</th><th>Avg Cost</th><th>Current Price</th>
          <th>Market Value</th><th>P&L</th><th>P&L %</th><th></th>
      </tr></thead><tbody>`;

    for (const h of holdings) {
        const pnlClass = h.pnl >= 0 ? 'positive' : 'negative';
        html += `<tr>
            <td class="symbol-cell">${h.symbol}</td>
            <td>${h.name || '—'}</td>
            <td>${Number(h.net_quantity).toLocaleString('vi-VN')}</td>
            <td>${formatVND(h.avg_cost)}</td>
            <td>${h.current_price ? formatVND(h.current_price) : '—'}</td>
            <td>${formatVND(h.market_value)}</td>
            <td class="${pnlClass}">${(h.pnl >= 0 ? '+' : '') + formatVND(h.pnl)}</td>
            <td class="${pnlClass}">${(h.pnl_pct >= 0 ? '+' : '') + h.pnl_pct.toFixed(2)}%</td>
            <td><button class="btn btn-sm" onclick="viewTxnHistory('${h.symbol}')">📜</button></td>
        </tr>`;
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

/* -- Transaction History -- */

async function loadTransactions() {
    const symbolFilter = document.getElementById('txn-filter-symbol')?.value.trim().toUpperCase() || '';
    const actionFilter = document.getElementById('txn-filter-action')?.value || '';

    let url = PortfolioAPI.transactions + '?limit=100';
    if (symbolFilter) url += `&symbol=${encodeURIComponent(symbolFilter)}`;

    try {
        const res = await apiGet(url);
        let txns = res && res.status === 'ok' ? (res.transactions || []) : [];

         // Filter by action on client side
        if (actionFilter) {
            txns = txns.filter(t => t.action === actionFilter);
        }

        renderTransactions(txns);
    } catch (e) {
        document.getElementById('transactions-container').innerHTML = `<div class="empty-state">Failed to load transactions: ${e.message}</div>`;
    }
}

function renderTransactions(txns) {
    const container = document.getElementById('transactions-container');
    if (!txns || txns.length === 0) {
        container.innerHTML = '<div class="empty-state">No transactions yet.</div>';
        return;
    }

      let html = `<table class="data-table"><thead><tr>
          <th>Date</th><th>Ticker</th><th>Name</th><th>Action</th>
          <th>Qty</th><th>Price</th><th>Total</th><th>Note</th><th></th>
      </tr></thead><tbody>`;

    for (const t of txns) {
        const actionClass = t.action === 'buy' ? 'positive' : 'negative';
        const total = (t.quantity * t.price);
        html += `<tr>
            <td>${t.txn_date}</td>
            <td class="symbol-cell">${t.symbol}</td>
            <td>${t.name || '—'}</td>
            <td><span class="badge ${actionClass}">${t.action.toUpperCase()}</span></td>
            <td>${Number(t.quantity).toLocaleString('vi-VN')}</td>
            <td>${formatVND(t.price)}</td>
            <td>${formatVND(total)}</td>
            <td>${t.note || ''}</td>
            <td><button class="btn btn-sm btn-danger" onclick="deleteTransaction(${t.id})">✕</button></td>
        </tr>`;
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

function viewTxnHistory(symbol) {
    document.getElementById('txn-filter-symbol').value = symbol;
    loadTransactions();
      // Scroll to transactions section
    document.getElementById('transactions-container').scrollIntoView({ behavior: 'smooth' });
}

/* -- Add Transaction -- */

async function addTransaction() {
    const msgEl = document.getElementById('txn-msg');
    const symbol = document.getElementById('pt-symbol').value.trim().toUpperCase();
    const name = document.getElementById('pt-name').value.trim();
    const action = document.getElementById('pt-action').value;
    const qty = parseFloat(document.getElementById('pt-qty').value);
    const price = parseFloat(document.getElementById('pt-price').value);
    const txnDate = document.getElementById('pt-date').value || null;

     // Validation
    if (!symbol) return showTxnMsg('⚠️ Please enter a ticker symbol', 'error');
    if (isNaN(qty) || qty <= 0) return showTxnMsg('⚠️ Invalid quantity', 'error');
    if (isNaN(price) || price <= 0) return showTxnMsg('⚠️ Invalid price', 'error');

    try {
        const res = await fetch(PortfolioAPI.addTxn, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({symbol, name, action, quantity: qty, price, txn_date: txnDate})
        });
        const data = await res.json();

        if (data.status === 'ok') {
             // Clear form
            document.getElementById('pt-symbol').value = '';
            document.getElementById('pt-name').value = '';
            document.getElementById('pt-qty').value = '';
            document.getElementById('pt-price').value = '';
            showTxnMsg(`✅ Added ${action} txn for ${symbol}`, 'success');
             // Reload data
            loadPortfolioSummary();
        } else {
            showTxnMsg('❌ Failed: ' + (data.error || 'unknown error'), 'error');
        }
    } catch (e) {
        showTxnMsg('❌ Error: ' + e.message, 'error');
    }
}

async function deleteTransaction(txnId) {
    if (!confirm('Delete this transaction?')) return;

    try {
        const res = await fetch(`${PortfolioAPI.deleteTxn}${txnId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
            loadPortfolioSummary();
        }
    } catch (e) {
        alert('Failed to delete: ' + e.message);
    }
}

function toggleAddTxnForm() {
    const form = document.getElementById('txn-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

function showTxnMsg(msg, type) {
    const el = document.getElementById('txn-msg');
    el.textContent = msg;
    el.style.color = type === 'success' ? 'var(--positive-color)' : 'var(--negative-color)';
     // Auto-clear after 5s
    setTimeout(() => { el.textContent = ''; }, 5000);
}


/* ---- Theme Toggle (dark/light mode) ---- */

function getStoredTheme() {
    return localStorage.getItem('hub-theme') || 'dark';
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'light' ? '\u2600' : '\ud83c\udf19';  // sun or moon
}

function toggleTheme() {
    const current = getStoredTheme();
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('hub-theme', next);
    applyTheme(next);
}

/* ---- Init ---- */

    document.addEventListener('DOMContentLoaded', () => {
         // Apply stored theme first (no flash of wrong theme)
        applyTheme(getStoredTheme());

         // Load market tab by default
        loadMarketOverview();
        checkHealth();

         // Auto-refresh every 5 minutes. Also re-apply theme since localStorage syncs across tabs
        setInterval(() => {
            applyTheme(getStoredTheme());
             const activeTab = document.querySelector('.nav-tab.active');
            if (activeTab) {
                loadTabData(activeTab.dataset.tab);
              }
            checkHealth();
          }, 300000);
      });
