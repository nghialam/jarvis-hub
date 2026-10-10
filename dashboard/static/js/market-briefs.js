/**
 * market-briefs.js - Market Briefs Dashboard JavaScript
 *
 * Handles: pagination, filtering, search, view toggle, detail modal
 */

let currentView = 'card';
let currentPage = 1;
let totalPages = 1;
let currentSearch = '';
let currentDateFrom = '';
let currentDateTo = '';
let currentSource = '';
let currentBriefData = null;
let searchTimeout = null;

function toggleView() {
    currentView = currentView === 'card' ? 'table' : 'card';
    const btn = document.getElementById('toggle-view-btn');
    const cardView = document.getElementById('briefs-card-view');
    const tableView = document.getElementById('briefs-table-view');

    if (currentView === 'card') {
        cardView.style.display = 'block';
        tableView.style.display = 'none';
        btn.textContent = '📋 Table View';
    } else {
        cardView.style.display = 'none';
        tableView.style.display = 'block';
        btn.textContent = '🃏 Card View';
    }
}

function loadBriefsSummary() {
    fetch('/api/v1/market-briefs/count')
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                document.getElementById('total-briefs').textContent = data.total;
                document.getElementById('briefs-count').textContent = `${data.total} briefs`;
                if (data.by_source) {
                    Object.keys(data.by_source).forEach(source => {
                        const el = document.getElementById(`source-${source}`);
                        if (el) el.textContent = data.by_source[source];
                    });
                }
            } else {
                document.getElementById('total-briefs').textContent = '0';
            }
        })
        .catch(err => {
            console.error('Failed to load summary:', err);
        });
}

function loadMarketBriefs() {
    loadBriefsPaginated();
}

function loadBriefsPaginated() {
    const loading = document.getElementById('briefs-loading');
    const error = document.getElementById('briefs-error');
    const cardView = document.getElementById('briefs-card-view');
    const tableView = document.getElementById('briefs-table-view');

    loading.style.display = 'block';
    error.style.display = 'none';

    const source = document.getElementById('source-filter').value;
    const dateFrom = document.getElementById('date-from').value;
    const dateTo = document.getElementById('date-to').value;

    const params = new URLSearchParams({
        page: currentPage,
        per_page: 20,
        source: source,
        date_from: dateFrom,
        date_to: dateTo,
        search: currentSearch
    });

    fetch(`/api/v1/market-briefs?${params}`)
        .then(r => r.json())
        .then(data => {
            loading.style.display = 'none';
            if (!data.success) {
                error.textContent = data.error || 'Failed to load briefs';
                error.style.display = 'block';
                return;
            }

            const briefs = data.data;
            const pagination = data.pagination;
            totalPages = pagination.pages || 1;

            if (briefs.length === 0) {
                cardView.innerHTML = '<div class="empty-state">No market briefs found.</div>';
                tableView.querySelector('#briefs-table-body').innerHTML = '<tr><td colspan="5" class="empty-state">No briefs found.</td></tr>';
                document.getElementById('briefs-pagination').style.display = 'none';
                return;
            }

            // Update date range
            if (briefs.length > 0) {
                const dates = briefs.map(b => b.date).sort();
                document.getElementById('date-range').textContent = `${dates[0]} → ${dates[dates.length - 1]}`;
            }

            // Render cards
            renderCardView(briefs);

            // Render table
            renderTableView(briefs);

            // Update pagination
            document.getElementById('page-info').textContent = `Page ${pagination.page} of ${pagination.pages}`;
            document.getElementById('prev-page').disabled = pagination.page <= 1;
            document.getElementById('next-page').disabled = pagination.page >= pagination.pages;
            document.getElementById('briefs-pagination').style.display = 'flex';
        })
        .catch(err => {
            loading.style.display = 'none';
            error.textContent = 'Failed to load briefs: ' + err.message;
            error.style.display = 'block';
        });
}

function renderCardView(briefs) {
    const container = document.getElementById('briefs-card-view');
    let html = '<div class="card-grid">';

    briefs.forEach(brief => {
        const preview = brief.formatted_output ? brief.formatted_output.substring(0, 200) + '...' : 'No content';
        const date = brief.date || 'Unknown';
        const source = brief.source || 'unknown';

        html += `
            <div class="card brief-card" onclick="showBriefDetail(${brief.id})">
                <div class="card-header">
                    <h4>📊 Market Brief - ${escapeHtml(date)}</h4>
                    <span class="badge">${escapeHtml(source)}</span>
                </div>
                <div class="card-body">
                    <p class="text-muted">${escapeHtml(preview)}</p>
                </div>
                <div class="card-footer">
                    <small>Created: ${new Date(brief.created_at).toLocaleString()}</small>
                    <button class="btn btn-sm" onclick="event.stopPropagation(); showBriefDetail(${brief.id})">View Full</button>
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

function renderTableView(briefs) {
    const tbody = document.getElementById('briefs-table-body');
    let html = '';

    briefs.forEach(brief => {
        const preview = brief.formatted_output ? brief.formatted_output.substring(0, 100) + '...' : 'No content';
        const date = brief.date || 'Unknown';
        const source = brief.source || 'unknown';
        const created = new Date(brief.created_at).toLocaleString();

        html += `
            <tr>
                <td>${date}</td>
                <td><span class="badge">${source}</span></td>
                <td class="text-muted">${escapeHtml(preview)}</td>
                <td>${created}</td>
                <td>
                    <button class="btn btn-sm" onclick="showBriefDetail(${brief.id})">View</button>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

function changePage(delta) {
    const newPage = currentPage + delta;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        loadBriefsPaginated();
    }
}

function debounceSearch() {
    const input = document.getElementById('search-input');
    if (searchTimeout) clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentSearch = input.value.trim();
        currentPage = 1;
        loadBriefsPaginated();
    }, 300);
}

function showBriefDetail(id) {
    const modal = document.getElementById('brief-modal');
    const body = document.getElementById('modal-body');
    const title = document.getElementById('modal-title');

    modal.style.display = 'flex';
    body.innerHTML = '<div class="loading">Loading brief...</div>';
    title.textContent = 'Loading...';

    fetch(`/api/v1/market-briefs/${id}`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                body.innerHTML = `<div class="error-message">${data.error}</div>`;
                title.textContent = 'Error';
                return;
            }

            const brief = data.data;
            title.textContent = `Market Brief - ${brief.date}`;

            let html = '<div class="detail-view">';
            html += `<div class="detail-meta"><strong>Date:</strong> ${brief.date || 'N/A'} | <strong>Source:</strong> ${brief.source || 'N/A'} | <strong>Created:</strong> ${new Date(brief.created_at).toLocaleString()}</div>`;
            html += '<div class="detail-content">';
            html += '<h4>Formatted Output:</h4>';
            html += `<pre class="formatted-output">${escapeHtml(brief.formatted_output || 'No content')}</pre>`;
            html += '</div>';

            if (brief.raw_json) {
                html += '<div class="detail-content">';
                html += '<h4>Raw JSON:</h4>';
                try {
                    const parsed = JSON.parse(brief.raw_json);
                    html += `<pre class="formatted-output">${escapeHtml(JSON.stringify(parsed, null, 2))}</pre>`;
                } catch (e) {
                    html += `<pre class="formatted-output">${escapeHtml(brief.raw_json)}</pre>`;
                }
                html += '</div>';
            }

            html += '</div>';
            body.innerHTML = html;

            currentBriefData = brief;
        })
        .catch(err => {
            body.innerHTML = `<div class="error-message">Failed to load: ${err.message}</div>`;
            title.textContent = 'Error';
        });
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('brief-modal').style.display = 'none';
}

function copyBrief() {
    if (!currentBriefData) return;
    const text = currentBriefData.formatted_output || currentBriefData.raw_json || '';
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.querySelector('#brief-modal .modal-footer .btn-secondary');
        const original = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => btn.textContent = original, 2000);
    }).catch(err => {
        console.error('Copy failed:', err);
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
