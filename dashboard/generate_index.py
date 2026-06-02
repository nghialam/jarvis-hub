#!/usr/bin/env python3
"""Generate clean index.html for Jarvis Hub v1.2.0"""
import os

# Read base HTML (without JS)
base_path = '/Users/nghialam/jarvis-hub/dashboard/templates/index.html'
with open(base_path, 'r') as f:
    base_html = f.read()

# All JavaScript - carefully validated for correct bracket/paren balance
js_code = r"""
     <script>
        // === UTILITIES ===
       function updateDateTime() {
           const now = new Date();
           document.getElementById('currentDateTime').textContent = now.toLocaleString('vi-VN', {
               weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
               hour: '2-digit', minute: '2-digit'
               });
         }
       setInterval(updateDateTime, 1000);
       updateDateTime();

       function getSentimentClass(sentiment) {
           if (!sentiment) return 'neutral';
           const s = sentiment.toLowerCase();
           if (s.includes('tich cuc') || s.includes('positive') || s.includes('bullish')) return 'positive';
           if (s.includes('tieu cuc') || s.includes('negative') || s.includes('bearish')) return 'negative';
           return 'neutral';
         }

       function escapeHtml(text) {
           const div = document.createElement('div');
           div.textContent = text;
           return div.innerHTML;
         }

         // === TAB SWITCHING ===
       function switchTab(tabName) {
           document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
           document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
           const buttons = document.querySelectorAll('.nav-tab');
           const tabs = ['dashboard', 'analyze', 'knowledge', 'watchlist', 'history', 'eval', 'health'];
           const idx = tabs.indexOf(tabName);
           if (idx >= 0) buttons[idx].classList.add('active');
           document.getElementById(tabName).classList.add('active');
           if (tabName === 'dashboard') loadDashboard();
           else if (tabName === 'watchlist') loadWatchlist();
           else if (tabName === 'history') loadSnapshots();
           else if (tabName === 'health') loadHealth();
           else if (tabName === 'eval') { loadEvaluation(); loadEvalHistory(); }
         }

         // === DASHBOARD ===
       let allArticles = [];
       let selectedCategory = localStorage.getItem('jarvis_selected_category') || 'all';
       const CACHE_KEY = 'jarvis_articles_cache';
       const CACHE_TTL_MS = 180 * 1000;

       function loadDashboard() {
           const grid = document.getElementById('vnIndices');
           const globalGrid = document.getElementById('globalIndices');
           const miscGrid = document.getElementById('miscIndicesGrid');
           const cryptoGrid = document.getElementById('cryptoMarketGrid');
           grid.innerHTML = '<div class="loading">Loading indices...</div>';
           globalGrid.innerHTML = '';
           if (miscGrid) miscGrid.innerHTML = '';
           if (cryptoGrid) cryptoGrid.innerHTML = '';

           fetch('/api/health')
                .then(r => r.json())
                .then(data => {
                    if (data.indices && data.indices['VN-Index']) {
                        const vni = data.indices['VN-Index'];
                        const cls = vni.change_pct >= 0 ? 'positive' : 'negative';
                        const arrow = vni.change_pct >= 0 ? '\u25B2' : '\u25BC';
                        grid.innerHTML = '<div class="index-card ' + cls + '"><div class="index-name">VN-Index</div><div class="index-value">' + Number(vni.price).toLocaleString('en-US', {maximumFractionDigits: 2}) + '</div><div class="index-change text-' + (vni.change_pct >= 0 ? 'green' : 'red') + '">' + arrow + ' ' + Math.abs(vni.change_pct) + '%</div></div>';
                      }
                    if (data.indices && data.indices['global']) {
                        let html = '';
                        Object.entries(data.indices['global']).slice(0, 5).forEach(([name, info]) => {
                            const cls2 = info.change_pct >= 0 ? 'positive' : 'negative';
                            const arrow2 = info.change_pct >= 0 ? '\u25B2' : '\u25BC';
                            html += '<div class="index-card ' + cls2 + '"><div class="index-name">' + name + '</div><div class="index-value">' + Number(info.price).toLocaleString('en-US', {maximumFractionDigits: 2}) + '</div><div class="index-change text-' + (info.change_pct >= 0 ? 'green' : 'red') + '">' + arrow2 + ' ' + Math.abs(info.change_pct) + '%</div></div>';
                          });
                        globalGrid.innerHTML = html;
                      }
                    if (miscGrid) {
                        let miscHtml = '';
                        if (data.gold) {
                            const arrow3 = data.gold.change_pct >= 0 ? '\u25B2' : '\u25BC';
                            const gcls = data.gold.change_pct < 0 ? 'negative' : 'positive';
                            miscHtml += '<div class="index-card ' + gcls + '"><div class="index-name">Gold</div><div class="index-value">$' + Number(data.gold.price).toLocaleString() + '</div><div class="index-change text-' + (data.gold.change_pct >= 0 ? 'green' : 'red') + '">' + arrow3 + ' ' + Math.abs(data.gold.change_pct) + '%</div></div>';
                          }
                        if (data.dxy) {
                            const dxyCls = data.dxy.change_pct >= 0 ? 'positive' : 'negative';
                            const da = data.dxy.change_pct >= 0 ? '\u25B2' : '\u25BC';
                            miscHtml += '<div class="index-card ' + dxyCls + '"><div class="index-name">DXY</div><div class="index-value">' + Number(data.dxy.price).toLocaleString('en-US', {maximumFractionDigits: 2}) + '</div><div class="index-change text-' + (data.dxy.change_pct >= 0 ? 'green' : 'red') + '">' + da + ' ' + Math.abs(data.dxy.change_pct) + '%</div></div>';
                          }
                        if (data.oil) {
                            const oilCls = data.oil.change_pct >= 0 ? 'positive' : 'negative';
                            const oa = data.oil.change_pct >= 0 ? '\u25B2' : '\u25BC';
                            miscHtml += '<div class="index-card ' + oilCls + '"><div class="index-name">WTI Oil</div><div class="index-value">' + Number(data.oil.price).toLocaleString('en-US', {maximumFractionDigits: 2}) + '</div><div class="index-change text-' + (data.oil.change_pct >= 0 ? 'green' : 'red') + '">' + oa + ' ' + Math.abs(data.oil.change_pct) + '%</div></div>';
                          }
                        miscGrid.innerHTML = miscHtml || '<div class="loading">No DXY/Oil/Gold data</div>';
                      }
                    if (data.rates && data.rates['USD']) {
                        const usd = data.rates['USD'];
                        document.getElementById('usdVndRate').textContent = usd.transfer ? Number(usd.transfer).toLocaleString('en-US', {maximumFractionDigits: 2}) + ' d' : 'N/A';
                      }
                    if (data.crypto && typeof data.crypto === 'object') {
                        let cryptoHtml = '';
                        Object.entries(data.crypto).forEach(([sym, cData]) => {
                            if (!cData) return;
                            const cls3 = cData.change_pct >= 0 ? 'positive' : 'negative';
                            const arrow4 = cData.change_pct >= 0 ? '\u25B2' : '\u25BC';
                            cryptoHtml += '<div class="index-card ' + cls3 + '"><div class="index-name">' + sym + '</div><div class="index-value">$' + Number(cData.price).toLocaleString('en-US', {maximumFractionDigits: 2}) + '</div><div class="index-change text-' + (cData.change_pct >= 0 ? 'green' : 'red') + '">' + arrow4 + ' ' + Math.abs(cData.change_pct) + '%</div></div>';
                          });
                        cryptoGrid.innerHTML = cryptoHtml || '<div class="loading">No crypto data</div>';
                      }
                    loadArticles();
                  })
                .catch(() => { grid.innerHTML = '<div class="loading">Failed to load dashboard.</div>'; });
         }

         // === ARTICLES ===
       function getArticlesFromCache() {
           try {
               const raw = localStorage.getItem(CACHE_KEY);
               if (!raw) return null;
               const data = JSON.parse(raw);
               if ((Date.now() - data.timestamp) < CACHE_TTL_MS) return data.items;
             } catch (e) {}
           return null;
         }

       function saveArticlesToCache(items) {
           try { localStorage.setItem(CACHE_KEY, JSON.stringify({ timestamp: Date.now(), items: items })); } catch (e) {}
         }

       function loadArticles() {
           const grid = document.getElementById('articlesGrid');
           let items = getArticlesFromCache();
           if (items && items.length > 0) {
               renderArticles(selectedCategory, items);
               setTimeout(() => fetchAndRefreshArticles(), 120000);
             } else {
               grid.innerHTML = '<div class="loading" style="grid-column:1/-1;">Loading headlines...</div>';
               fetchAndRefreshArticles();
             }
         }

       function fetchAndRefreshArticles() {
           const grid = document.getElementById('articlesGrid');
           fetch('/api/articles?limit=30')
                .then(r => r.json())
                .then(data => {
                    if (data.articles && data.articles.length > 0) {
                        allArticles = data.articles;
                        saveArticlesToCache(allArticles);
                        renderArticles(selectedCategory, allArticles);
                      } else {
                        if (!getArticlesFromCache()) grid.innerHTML = '<div class="loading" style="grid-column:1/-1;">No articles. Run "jarvis briefing" first.</div>';
                      }
                })
                .catch(() => {
                    if (!getArticlesFromCache()) grid.innerHTML = '<div class="loading" style="grid-column:1/-1;">Failed to load articles.</div>';
                });
         }

       function renderArticles(category, items) {
           const grid = document.getElementById('articlesGrid');
           selectedCategory = category;
           localStorage.setItem('jarvis_selected_category', category);
           function matchesCategory(articleCat, filterCat) {
               if (filterCat === 'all') return true;
               return (articleCat || '').toLowerCase().trim() === filterCat;
             }
           const filtered = category === 'all' ? items : items.filter(a => matchesCategory(a.category, category));
           if (filtered.length === 0) { grid.innerHTML = '<div class="loading" style="grid-column:1/-1;">No articles in this category.</div>'; return; }
           const catLabels = {'vn-stock':'VN Stock','vn-business':'VN Business','vn-economy':'VN Economy','global-economy':'Global Econ','ai-tech':'AI & Tech'};
           let html = '';
           for (let i = 0; i < filtered.length; i++) {
               const a = filtered[i];
               const sentClass = getSentimentClass(a.sentiment_class || a.sentiment);
               const catLabel = catLabels[a.category] || a.category;
               const url = a.link || '#';
               html += '<a href="' + escapeHtml(url) + '" target="_blank"><div class="article-cat-card article-card sentiment-' + sentClass + '" data-category="' + escapeHtml(a.category) + '"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;"><span class="badge badge-' + sentClass + '">' + escapeHtml(a.sentiment_class || a.sentiment || 'TRUNG LAP') + '</span><span style="color:var(--text-secondary);font-size:10px;">' + escapeHtml(catLabel) + '</span></div><div style="font-weight:bold;color:var(--accent-blue);font-size:13px;margin-bottom:6px;line-height:1.4;">' + escapeHtml(a.title || 'N/A') + '</div><div style="display:flex;justify-content:space-between;align-items:center;"><span style="color:var(--text-secondary);font-size:11px;">' + escapeHtml(a.source || '') + ' | Bull:' + (a.bull_count||0) + ' / Bear:' + (a.bear_count||0) + '</span>' + (a.published ? '<span style="color:var(--text-secondary);font-size:11px;">' + escapeHtml(a.published) + '</span>' : '') + '</div></div></a>';
             }
           grid.innerHTML = html;
         }

       function filterArticles(category) {
           localStorage.setItem('jarvis_selected_category', category);
           document.querySelectorAll('.article-cat-tab').forEach(tab => tab.classList.toggle('active', tab.getAttribute('data-category') === category));
           const items = allArticles.length > 0 ? allArticles : getArticlesFromCache();
           if (!items || items.length === 0) { loadArticles(); return; }
           renderArticles(category, items);
         }

         // === EVALUATION TAB ===
       function renderMarkdown(text) {
           if (!text) return '<div style="color:var(--text-secondary);">No evaluation available.</div>';
           let html = text.replace(/### (.+)$/gm, '<h4 style="color:var(--accent-purple);margin-top:15px;">$1</h4>');
           html = html.replace(/## (.+)$/gm, '<h3 style="color:var(--accent-blue);margin-top:18px;">$1</h3>');
           html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
           html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
           html = html.replace(/\n\n/g, '</p><p style="margin:8px 0;">');
           html = html.replace(/\n/g, '<br>');
           return '<div class="eval-content">' + html + '</div>';
         }

       function loadEvaluation() {
           fetch('/api/market-evaluation?force=true&_t=' + Date.now())
                .then(r => r.json())
                .then(data => {
                    const cdiv = document.getElementById('evalContent');
                    if (data.evaluation) {
                        let h = '<div class="eval-timestamp">Generated: ' + (data.date || new Date().toLocaleString('vi-VN')) + '</div>';
                        h += renderMarkdown(data.evaluation);
                        if (data.summary) h += '<div style="margin-top:12px;padding:10px;background:var(--bg-card);border-radius:6px;color:var(--accent-blue);font-style:italic;">' + escapeHtml(data.summary) + '</div>';
                        cdiv.innerHTML = h;
                      } else {
                        cdiv.innerHTML = '<div style="color:var(--text-secondary);padding:30px;text-align:center;">No evaluation yet. Click "Generate" to create one.</div>';
                      }
                })
                .catch(() => { document.getElementById('evalContent').innerHTML = '<div style="color:var(--accent-red);">Failed to load.</div>'; });
         }

       function generateEvaluation() {
           const statusSpan = document.getElementById('evalStatus');
           statusSpan.textContent = 'Generating...';
           fetch('/api/market-evaluation/generate', { method: 'GET' })
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'ok' || data.ok) { statusSpan.textContent = 'Generated!'; setTimeout(loadEvaluation, 500); }
                    else { statusSpan.textContent = 'Error: ' + (data.error || 'Unknown'); }
                })
                .catch(e => { console.error('[Eval] failed:', e); statusSpan.textContent = 'Generation failed.'; });
         }

       function loadEvalHistory() {
           fetch('/api/market-evaluation/history')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('evalHistory');
                    if (!data.evaluations || data.evaluations.length === 0) { container.innerHTML = ''; return; }
                    let html = '<h3 style="color:var(--accent-purple);margin-bottom:12px;">Evaluation History</h3>';
                    data.evaluations.slice(0, 10).forEach(e => {
                        const summary = e.summary ? '<div style="color:var(--accent-blue);font-style:italic;margin-top:4px;">' + escapeHtml(e.summary) + '</div>' : '';
                        html += '<div class="eval-card" onclick="this.querySelector(\\'.eval-preview\\').style.display=this.querySelector(\\'.eval-preview\\').style.display===\\'none\\'?\\'block\\':\\'none\\'" style="cursor:pointer;"><div class="eval-timestamp">' + escapeHtml(e.date) + '</div><div class="eval-preview" style="display:none;white-space:pre-wrap;margin-top:8px;color:var(--text-primary);">' + escapeHtml(e.evaluation.substring(0, 500)) + (e.evaluation.length > 500 ? '...' : '') + '</div>' + summary + '</div>';
                      });
                    container.innerHTML = html;
                })
                .catch(() => { document.getElementById('evalHistory').innerHTML = ''; });
         }

         // === ANALYZE SYMBOL ===
       function analyzeSymbol() {
           const symbol = document.getElementById('symbolInput').value.trim().toUpperCase();
           if (!symbol) return alert('Enter a symbol');
           const resultDiv = document.getElementById('analysisResult');
           resultDiv.innerHTML = '<div class="loading">Analyzing ' + symbol + '...</div>';
           fetch('/api/analyze?symbol=' + encodeURIComponent(symbol) + '&_t=' + Date.now())
                .then(r => r.json())
                .then(data => {
                    if (data.error) { resultDiv.innerHTML = '<div style="color:var(--accent-red);">' + escapeHtml(data.error) + '</div>'; return; }
                    const d = data.price !== undefined ? data : (data.data || null);
                    if (!d) { resultDiv.innerHTML = '<div style="color:var(--accent-red);">No market data for this symbol.</div>'; return; }
                    let html = '<div style="margin-bottom:20px;"><h3>' + escapeHtml(d.name || d.symbol) + ' (' + escapeHtml(d.symbol) + ')</h3><p style="font-size:24px;margin:10px 0;">' + (d.price ? Number(d.price).toLocaleString('en-US',{maximumFractionDigits:2}) + ' ' + (d.currency||'') : 'N/A') + '</p>';
                    if (d.change_pct !== undefined) html += '<span class="' + (d.change_pct >= 0 ? 'text-green' : 'text-red') + '" style="font-size:18px;">' + (d.change_pct >= 0 ? '+' : '') + d.change_pct + '% | ' + (d.prev_close ? 'Prev: ' + Number(d.prev_close).toLocaleString('en-US',{maximumFractionDigits:2}) : '') + '</span>';
                    const finMetrics = [];
                    if (d.pe_ratio) finMetrics.push('P/E:' + d.pe_ratio);
                    if (d.eps) finMetrics.push('EPS:' + d.eps);
                    if (d.market_cap) finMetrics.push('Mkt Cap:' + d.market_cap);
                    if (d.volume) finMetrics.push('Vol:' + Number(d.volume).toLocaleString('en-US'));
                    if (finMetrics.length > 0) html += '<div style="margin-top:12px;padding:12px;background:var(--bg-card);border-radius:6px;border-left:3px solid var(--accent-purple);">' + finMetrics.map(m => '<span style="color:var(--text-secondary);font-size:13px;margin-right:20px;">' + m + '</span>').join('') + '</div>';
                    if (d.technical && typeof d.technical === 'object') {
                        html += '<h4 style="margin-top:24px;color:var(--accent-purple);font-size:16px;">Technical Analysis</h4><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:12px;">';
                        const rsi = d.technical.rsi || d.technical.RSI || d.technical.RSI_14;
                        if (rsi) {
                            let rc = 'var(--accent-blue)', rl = 'Neutral';
                            if (rsi >= 70) { rc = 'var(--accent-red)'; rl = 'Overbought'; } else if (rsi <= 30) { rc = 'var(--accent-green)'; rl = 'Oversold'; }
                            html += '<div style="background:var(--bg-card);border-radius:8px;padding:12px;border-left:3px solid ' + rc + ';"><div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">RSI(14)</div><div style="font-size:20px;font-weight:bold;color:' + rc + ';">' + Number(rsi).toFixed(1) + '</div><div style="font-size:11px;color:' + rc + ';margin-top:4px;">' + rl + '</div></div>';
                          }
                        const sma20 = d.technical.sma_20 || d.technical.SMA_20;
                        if (sma20 && d.price) html += '<div style="background:var(--bg-card);border-radius:8px;padding:12px;border-left:3px solid var(--accent-blue);"><div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">SMA(20)</div><div style="font-size:16px;font-weight:bold;">' + Number(sma20).toFixed(2) + '</div><div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">Price ' + (d.price > sma20 ? 'Above' : 'Below') + '</div></div>';
                        const macdHist = d.technical.macd_histogram || (d.technical.MACD && d.technical.MACD.histogram) || 0;
                        if (macdHist !== undefined) { try { const val = parseFloat(macdHist); if (!isNaN(val)) html += '<div style="background:var(--bg-card);border-radius:8px;padding:12px;border-left:3px solid ' + (val > 0 ? 'var(--accent-green)' : 'var(--accent-red)') + ';"><div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">MACD</div><div style="font-size:16px;font-weight:bold;color:' + (val > 0 ? 'var(--accent-green)' : 'var(--accent-red')) + ';">' + val.toFixed(4) + '</div><div style="font-size:11px;color:' + (val > 0 ? 'var(--accent-green)' : 'var(--accent-red') + ';margin-top:4px;">' + (val > 0 ? 'Bullish' : 'Bearish') + '</div></div>'; } catch(e) {} }
                        const support = d.technical.support_level || (d.technical.SUPPORT && d.technical.SUPPORT[0]);
                        if (support) html += '<div style="background:var(--bg-card);border-radius:8px;padding:12px;border-left:3px solid var(--accent-green);"><div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Support</div><div style="font-size:16px;font-weight:bold;color:var(--accent-green);">' + Number(support).toFixed(2) + '</div></div>';
                        const resistance = d.technical.resistance_level || (d.technical.RESISTANCE && d.technical.RESISTANCE[0]);
                        if (resistance) html += '<div style="background:var(--bg-card);border-radius:8px;padding:12px;border-left:3px solid var(--accent-red);"><div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">Resistance</div><div style="font-size:16px;font-weight:bold;color:var(--accent-red);">' + Number(resistance).toFixed(2) + '</div></div>';
                        html += '</div>';
                      } else if (d.technical_summary) {
                        html += '<h4 style="margin-top:20px;color:var(--accent-purple);">Technical Indicators</h4><pre style="background:var(--bg-card);padding:15px;border-radius:6px;overflow-x:auto;">' + escapeHtml(d.technical_summary) + '</pre>';
                      }
                    if (d.llm_report) {
                        const recMatch = d.llm_report.match(/(?:KHUYEN NGH[IA]|RECOMMENDATION|ACTION)[\s]*([^\n]+)/i);
                        const recommendation = recMatch ? recMatch[1].trim() : 'Chua co khuyen nghi';
                        let signalClass = 'neutral'; if (/MUA|BUY/.test(recommendation)) signalClass = 'positive'; else if (/BAN|SELL/.test(recommendation)) signalClass = 'negative';
                        html += '<div style="margin-top:20px;padding:15px;background:var(--bg-card);border-radius:8px;border-left:4px solid var(--accent-blue);"><h4 style="color:var(--accent-purple);margin-bottom:10px;">AI Analysis</h4><div class="badge badge-' + signalClass + '" style="font-size:14px;padding:6px 12px;display:inline-block;margin-bottom:12px;">' + escapeHtml(recommendation) + '</div></div>';
                        html += '<details style="margin-top:15px;background:var(--bg-card);border-radius:6px;border:1px solid var(--border-color);"><summary style="padding:12px;cursor:pointer;color:var(--accent-blue);font-weight:bold;">View full AI report</summary><pre style="padding:15px;margin:0;white-space:pre-wrap;line-height:1.6;max-height:400px;overflow-y:auto;">' + escapeHtml(d.llm_report) + '</pre></details>';
                      }
                    html += '<p style="margin-top:20px;color:var(--text-secondary);font-size:12px;">Last update: ' + escapeHtml(d.last_update || 'N/A') + '</p></div>';
                    resultDiv.innerHTML = html;
                })
                .catch(() => { resultDiv.innerHTML = '<div style="color:var(--accent-red);">Failed to fetch data.</div>'; });
         }

         // === KNOWLEDGE BASE ===
       function searchKnowledge() {
           const query = document.getElementById('knowledgeInput').value.trim();
           if (query.length < 2) return alert('Enter at least 2 characters');
           const resultsDiv = document.getElementById('knowledgeResults');
           resultsDiv.innerHTML = '<div class="loading">Searching...</div>';
           fetch('/api/search?q=' + encodeURIComponent(query))
                .then(r => r.json())
                .then(data => {
                    if (!data.results || data.results.length === 0) {
                        resultsDiv.innerHTML = '<div style="color:var(--text-secondary);padding:20px;text-align:center;">No results for "' + escapeHtml(query) + '"<br><button class="btn btn-primary" onclick="generateKnowledge()">Generate with AI</button></div>';
                        return;
                      }
                    let html = '<p style="margin-bottom:15px;">Found ' + data.count + ' results for "<strong>' + escapeHtml(query) + '</strong>"</p>';
                    data.results.forEach(item => {
                        const r = Array.isArray(item) ? item[1] : item; if (!r || !r.term) return;
                        html += '<div class="knowledge-result"><div class="knowledge-term">' + escapeHtml(r.term) + '</div><div>' + (r.content ? (r.content.length > 300 ? r.content.substring(0,300) + '...' : r.content) : 'No content') + '</div>';
                        if (r.tags) html += '<div style="margin-top:8px;"><span style="color:var(--accent-purple);font-size:12px;">' + escapeHtml(r.tags) + '</span></div>';
                        html += '<div style="margin-top:8px;color:var(--text-secondary);font-size:12px;">Updated: ' + escapeHtml(r.updated_at||'N/A') + (r.score !== undefined ? ' | Score:' + r.score : '') + '</div></div>';
                      });
                    resultsDiv.innerHTML = html;
                })
                .catch(() => { resultsDiv.innerHTML = '<div style="color:var(--accent-red);padding:15px;">Failed to load.</div>'; });
         }

       function generateKnowledge() {
           const term = document.getElementById('knowledgeInput').value.trim();
           if (!term) return alert('Enter a term');
           const resultsDiv = document.getElementById('knowledgeResults');
           resultsDiv.innerHTML = '<div class="loading">Generating...</div>';
           fetch('/api/search?q=' + encodeURIComponent(term) + '&generate=true')
                .then(r => r.json())
                .then(data => {
                    if (data.generated) {
                        const div = document.createElement('div'); div.className = 'knowledge-result';
                        const termEl = document.createElement('div'); termEl.className = 'knowledge-term'; termEl.textContent = term; div.appendChild(termEl);
                        const preEl = document.createElement('pre'); preEl.style.cssText = 'white-space:pre-wrap;margin-top:10px;'; preEl.textContent = data.generated; div.appendChild(preEl);
                        const saveBtn = document.createElement('button'); saveBtn.className = 'btn btn-primary btn-sm'; saveBtn.style.cssText = 'margin-top:15px;'; saveBtn.textContent = 'Save to KB';
                        saveBtn.onclick = () => { fetch('/api/knowledge/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({term,content:preEl.textContent})}).then(r=>r.json()).then(d=>{if(d.ok){saveBtn.textContent='Saved!';saveBtn.disabled=true;}}); };
                        div.appendChild(saveBtn);
                        resultsDiv.innerHTML = ''; resultsDiv.appendChild(div);
                      } else { resultsDiv.innerHTML = '<div style="color:var(--accent-red);">Failed.</div>'; }
                })
                .catch(() => { resultsDiv.innerHTML = '<div style="color:var(--accent-red);">Generation failed.</div>'; });
         }

         // === WATCHLIST ===
       function loadWatchlist() {
           fetch('/api/watchlist').then(r => r.json()).then(data => {
               const tbody = document.getElementById('watchlistBody');
               const items = data.watchlist || data.items || [];
               if (items.length === 0) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary);">Watchlist empty. Add symbols above.</td></tr>'; return; }
               let html = '';
               items.forEach(item => {
                   const priceH = item.price !== null ? Number(item.price).toLocaleString('en-US',{maximumFractionDigits:2}) + (item.symbol.includes('BTC')?' USD':'') : '<span style="color:var(--text-secondary);">N/A</span>';
                   const ccls = item.change_pct >= 0 ? 'text-green' : 'text-red';
                   const changeH = item.change_pct !== null ? '<span class="' + ccls + '">' + (item.change_pct >= 0 ? '+' : '') + item.change_pct + '%</span>' : '<span style="color:var(--text-secondary);">N/A</span>';
                   html += '<tr><td><strong>' + escapeHtml(item.symbol) + '</strong></td><td>' + escapeHtml(item.name||'-') + '</td><td>' + priceH + '</td><td>' + changeH + '</td><td><button class="btn btn-danger btn-sm" onclick="removeFromWatchlist(\'' + escapeHtml(item.symbol) + '\', ' + (item.id||0) + ')">Remove</button></td></tr>';
                 });
               tbody.innerHTML = html;
            }).catch(() => { document.getElementById('watchlistBody').innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--accent-red);">Failed to load.</td></tr>'; });
         }

       function addToWatchlist() {
           const input = document.getElementById('newSymbolInput');
           const symbol = input.value.trim().toUpperCase();
           if (!symbol) return alert('Enter a symbol');
           fetch('/api/watchlist/add', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol}) })
                .then(r => r.json())
                .then(data => { if (data.ok) { input.value = ''; loadWatchlist(); } else alert('Error: ' + data.error); });
         }

       function removeFromWatchlist(symbol, id) {
           if (!confirm('Remove ' + symbol + '?')) return;
           fetch('/api/watchlist/remove', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({symbol}) })
                .then(r => r.json())
                .then(data => { if (data.ok) loadWatchlist(); });
         }

         // === HISTORY / SNAPSHOTS ===
       function loadSnapshots() {
           const listDiv = document.getElementById('snapshotsList');
           listDiv.innerHTML = '<div class="loading">Loading...</div>';
           fetch('/api/snapshots').then(r => r.json()).then(data => {
               if (!data.snapshots || data.snapshots.length === 0) { listDiv.innerHTML = '<div class="loading">No snapshots. Run "jarvis briefing" first.</div>'; return; }
               window._cachedSnapshots = data.snapshots;
               let html = '';
               data.snapshots.forEach(snap => {
                   html += '<div class="snapshot-card" onclick="showSnapshot(event,\'' + snap.date + '\'); event.stopPropagation();"><div style="font-weight:bold;color:var(--accent-blue);">' + escapeHtml(snap.date) + '</div><div style="color:var(--text-secondary);font-size:13px;">' + (snap.article_count||'') + ' articles | ' + new Date(snap.date).toLocaleDateString('vi-VN') + '</div></div>';
                 });
               listDiv.innerHTML = html;
            }).catch(() => { listDiv.innerHTML = '<div style="color:var(--accent-red);">Failed to load snapshots.</div>'; });
         }

       function showSnapshot(event, date) {
           const modal = document.getElementById('snapshotDetailModal');
           if (!modal) return;
           modal.classList.remove('hidden'); modal.style.display = 'flex';
           document.getElementById('snapshotTitle').textContent = 'Daily Briefing - ' + date;
           document.getElementById('snapshotContent').innerHTML = '<div class="loading">Loading...</div>';

           if (window._cachedSnapshots) {
               const snap = window._cachedSnapshots.find(s => s.date === date);
               if (snap && snap.full_content) {
                   document.getElementById('snapshotContent').innerHTML = renderMarkdown(snap.full_content);
                   return;
               }
           }

           fetch('/api/snapshots/' + encodeURIComponent(date))
                .then(r => r.json())
                .then(data => {
                    if (data.content) document.getElementById('snapshotContent').innerHTML = renderMarkdown(data.content);
                    else document.getElementById('snapshotContent').innerHTML = '<div style="color:var(--text-secondary);text-align:center;padding:30px;">No content for ' + date + '</div>';
                })
                .catch(() => { document.getElementById('snapshotContent').innerHTML = '<div style="color:var(--accent-red);text-align:center;padding:30px;">Failed to load.</div>'; });
         }

       function handleModalClick(event) {
           const modal = event.target;
           if (modal.id === 'snapshotDetailModal') {
               modal.classList.add('hidden'); modal.style.display = 'none';
             }
         }

         // === HEALTH CHECK ===
       function loadHealth() {
           fetch('/api/health').then(r => r.json()).then(data => {
               let html = '';
               const status = data.status || 'unknown';
               html += '<div class="health-item"><span><span class="status-dot ' + (status === 'ok' ? 'healthy' : 'error') + '"></span>Jarvis Hub</span><strong style="color:' + (status === 'ok' ? 'var(--accent-green)' : 'var(--accent-red)') + ';">' + status.toUpperCase() + '</strong></div>';
               if (data.indices) {
                   html += '<h4 style="margin-top:20px;color:var(--accent-purple);">Market Data Sources</h4>';
                   Object.keys(data.indices).forEach(key => {
                       const idx = data.indices[key];
                       if (idx && typeof idx === 'object' && idx.price !== undefined) {
                           html += '<div class="index-card ' + (idx.change_pct >= 0 ? 'positive' : 'negative') + '" style="margin-bottom:8px;display:inline-block;"><div class="index-name">' + escapeHtml(key) + '</div><div class="index-value">' + Number(idx.price).toLocaleString() + '</div></div>';
                         }
                     });
                 }
               const endpoints = ['/api/watchlist', '/api/snapshots', '/api/articles?limit=1'];
               endpoints.forEach(ep => {
                   fetch(ep).then(r => r.json()).then(data => {
                       const el = document.getElementById('healthStatus');
                       if (el) el.innerHTML += '<div class="health-item"><span><span class="status-dot healthy"></span>' + ep.split('?')[0] + '</span><strong style="color:var(--accent-green);">OK</strong></div>';
                     }).catch(() => {
                         const el = document.getElementById('healthStatus');
                         if (el) el.innerHTML += '<div class="health-item"><span><span class="status-dot error"></span>' + ep.split('?')[0] + '</span><strong style="color:var(--accent-red);">FAIL</strong></div>';
                       });
                 });
               document.getElementById('healthStatus').innerHTML += html;
            }).catch(() => { document.getElementById('healthStatus').innerHTML = '<div style="color:var(--accent-red);padding:20px;text-align:center;">Failed to connect.</div>'; });
         }

         // === INIT ON LOAD ===
       window.addEventListener('load', () => { updateDateTime(); loadDashboard(); });

          // Enter key handlers
       document.addEventListener('DOMContentLoaded', () => {
           const symInput = document.getElementById('symbolInput');
           if (symInput) symInput.addEventListener('keypress', e => { if (e.key === 'Enter') analyzeSymbol(); });
           const kbInput = document.getElementById('knowledgeInput');
           if (kbInput) kbInput.addEventListener('keypress', e => { if (e.key === 'Enter') searchKnowledge(); });
           const wlInput = document.getElementById('newSymbolInput');
           if (wlInput) wlInput.addEventListener('keypress', e => { if (e.key === 'Enter') addToWatchlist(); });
         });

     </script>
"""

# Combine base HTML + JavaScript and write
final_html = base_html.rstrip() + '\n' + js_code + '\n</body>\n</html>\n'

output_path = '/Users/nghialam/jarvis-hub/dashboard/templates/index.html'
with open(output_path, 'w') as f:
    f.write(final_html)

# Validate bracket/paren balance in JS section
js_only = js_code
ob = js_only.count('{')
cb = js_only.count('}')
op = js_only.count('(')
cp = js_only.count(')')

print(f"Total file written: {len(final_html)} bytes")
print(f"JS bracket balance: {{ = {ob}, }} = {cb} (diff={ob-cb}) {'OK' if ob==cb else 'FAIL!'}")
print(f"JS paren balance: ( = {op}, ) = {cp} (diff={op-cp}) {'OK' if op==cp else 'FAIL!'}")

# Count functions defined
import re
functions = re.findall(r'function\s+(\w+)', js_only)
print(f"\nFunctions defined ({len(functions)}):")
for fn in sorted(set(functions)):
    print(f"  - {fn}")
