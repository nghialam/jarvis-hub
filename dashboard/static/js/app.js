/* ========================================
   Jarvis Hub 2.0 — Main App JS
   Tab navigation + data loading
   
   NOTE: innerHTML is used with API data throughout. This is safe because:
   - Local-only dashboard (localhost:8100), no public exposure
   - All data originates from our own Flask backend + SQLite DB
   - No external user input reaches this code unsanitized
   ======================================== */

const API = {
    overview: '/api/overview',
    indices: '/api/overview/indices',
    crypto: '/api/overview/crypto',
    gold: '/api/overview/gold',
    motions: '/api/overview/motions',
    chart: '/api/overview/chart',
    news: '/api/articles',
    trending: '/api/articles?category=all&limit=5',
    research: '/api/research/list',
    researchStats: '/api/research/stats',
    researchCrawl: '/api/research/crawl',
    companies: '/api/companies/search',
    companyNews: '/api/companies/news',
    watchlist: '/api/watchlist',
    watchlistAdd: '/api/watchlist/add',
    watchlistRm: '/api/watchlist/remove',
    health: '/health',
};

let charts = {};
let lastUpdated = new Date(0);

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
            if (n >= 1e12) return (n / 1e12).toFixed(1) + 'T';
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

async function loadMarketOverview() {
        const container = document.getElementById('market-loading');
        if (container) container.style.display = 'block';

        // Load indices
        const indicesRes = await apiGet(API.indices);
        if (indicesRes) {
            renderIndices(indicesRes.vn || [], indicesRes.global || []);
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

/* ========================================
   NEWS TAB
   ======================================== */

async function loadNews() {
        const container = document.getElementById('news-loading');
        if (container) container.style.display = 'block';

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

        container.innerHTML = articles.map(a => `
        <div class="news-card">
            <h4><a href="${a.url || '#'}" target="_blank">${a.title}</a></h4>
            <div class="news-meta">
                <span class="badge badge-source">${a.source || 'Unknown'}</span>
                ${sentimentBadge(a.sentiment)}
                <span>${a.published_at ? new Date(a.published_at).toLocaleString() : ''}</span>
                ${starsHtml(Math.round(a.importance || 0) / 2)}
            </div>
            ${a.summary ? `<div class="news-snippet">${a.summary.substring(0, 200)}${a.summary.length > 200 ? '...' : ''}</div>` : ''}
        </div>
`).join('');
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
        if (container) container.innerHTML = '<div class="loading">Searching companies</div>';

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
        if (container) container.innerHTML = '<div class="loading">Loading company news</div>';

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
        if (container) container.style.display = 'block';

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
        if (container) container.style.display = 'block';

        // Load watchlist
        const wlRes = await apiGet(API.watchlist);
        if (wlRes) {
            renderWatchlist(wlRes.watchlist || []);
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

        const res = await apiPost(API.watchlistAdd, { symbol, name, sector });
        if (res && res.status === 'ok') {
            symbolEl.value = '';
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
        // Update active filter button
        document.querySelectorAll('#market-filters .filter-btn').forEach(b => b.classList.remove('active'));
        const btn = document.querySelector(`#market-filters .filter-btn[data-period="${period}"]`);
        if (btn) btn.classList.add('active');

        // Reload (the API handles period param)
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
        const container = document.getElementById('mi-loading');
        if (container) container.style.display = 'block';

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

            container.innerHTML = `
             <div class="card" style="margin-bottom: 16px;">
                 <div class="card-header">
                     <span class="card-title">🧠 Market Intelligence Brief</span>
                     <span style="font-size: 12px; color: var(--text-secondary);">
                         ${data.run_date} • ${data.run_period || 'unknown'} period • ${articles.length} articles
                     </span>
                 </div>
                 <div style="margin-bottom: 16px;">
                     <span class="badge badge-bullish">🟢 Bullish: ${bullCount}</span>
                     <span class="badge badge-bearish">🔴 Bearish: ${bearCount}</span>
                     <span class="badge badge-neutral">⚪ Neutral: ${neuCount}</span>
                 </div>
                 <div style="white-space: pre-wrap; line-height: 1.6;">${data.market_brief || 'No brief generated.'}</div>
             </div>

             ${articles.length > 0 ? `
                 <h4 style="margin: 16px 0 8px; color: var(--text-secondary); font-size: 13px;">Articles Analyzed</h4>
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
        } catch (e) {
            container.innerHTML = `<div class="empty-state">Failed to load latest brief: ${e.message}</div>`;
        }
}

async function loadMiHistory() {
        const container = document.getElementById('mi-history-container');
        if (!container) return;

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

/* ---- Init ---- */

    document.addEventListener('DOMContentLoaded', () => {
        // Load market tab by default
        loadMarketOverview();
        checkHealth();

        // Auto-refresh every 5 minutes
        setInterval(() => {
            const activeTab = document.querySelector('.nav-tab.active');
            if (activeTab) {
                loadTabData(activeTab.dataset.tab);
            }
            checkHealth();
        }, 300000);
    });
