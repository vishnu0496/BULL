/* ============================================================
   News Analyst — Page Module
   ============================================================ */

registerPage('analyst', async function(container) {
    container.innerHTML = `
        <div class="flex justify-between items-center mb-16">
            <div>
                <h1 class="page-title">News Analyst Desk</h1>
                <p class="page-subtitle" style="margin-bottom:0;">Turns free market headlines into event type, materiality, stock impact, and a daily caution/watch report.</p>
            </div>
            <button id="refreshAnalystBtn" class="btn btn-primary">Refresh Report</button>
        </div>

        <div id="analystContent">
            <div class="skeleton-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>
        </div>
    `;

    document.getElementById('refreshAnalystBtn').addEventListener('click', () => loadAnalystReport(true));
    await loadAnalystReport(false);
});

async function loadAnalystReport(forceRefresh) {
    const container = document.getElementById('analystContent');
    const btn = document.getElementById('refreshAnalystBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = forceRefresh ? 'Refreshing...' : 'Loading...';
    }

    try {
        const report = await API.get(`/api/news-analyst/report?force_refresh=${forceRefresh ? 'true' : 'false'}&limit=12`);
        renderAnalystReport(report);
    } catch (err) {
        showError(container, err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Refresh Report';
        }
    }
}

function analystCommandBadge(command) {
    if (command === 'CAUTION') return '<span class="badge badge-wait">CAUTION</span>';
    if (command === 'SELECTIVE_WATCH') return '<span class="badge badge-good">SELECTIVE WATCH</span>';
    return '<span class="badge badge-neutral">NEWS NEUTRAL</span>';
}

function impactBadge(impact) {
    const map = {
        POSITIVE: 'good',
        NEGATIVE: 'bad',
        CAUTION: 'wait',
        NEUTRAL: 'neutral'
    };
    return `<span class="badge badge-${map[impact] || 'neutral'}">${escapeHtml(impact || 'NEUTRAL')}</span>`;
}

function renderEventCard(event) {
    return `
        <div class="card-static mb-16" style="padding:16px;">
            <div class="flex justify-between items-center gap-16 mb-8">
                <div class="text-bold">${escapeHtml(cleanTicker(event.ticker))}</div>
                ${impactBadge(event.impact)}
            </div>
            <div style="font-size:0.9rem; line-height:1.45; color:var(--text-primary);">${escapeHtml(event.title)}</div>
            <div class="flex gap-8 mt-12" style="flex-wrap:wrap;">
                <span class="badge badge-neutral">${escapeHtml(event.event_type)}</span>
                <span class="badge badge-neutral">${escapeHtml(event.materiality)} ${event.materiality_score}</span>
                <span class="badge badge-neutral">${escapeHtml(event.sentiment_label)}</span>
            </div>
            <div class="text-muted mt-8" style="font-size:0.82rem; line-height:1.45;">${escapeHtml(event.reason)}</div>
        </div>
    `;
}

function renderStockReportCard(item) {
    const verdictType = item.verdict === 'NEWS_SUPPORTIVE' ? 'good' : (item.verdict === 'NEWS_RISK' ? 'bad' : (item.verdict === 'EVENT_CAUTION' ? 'wait' : 'neutral'));
    const events = (item.top_events || []).map(renderEventCard).join('');
    return `
        <div class="card-static">
            <div class="flex justify-between items-center mb-8">
                <div class="pick-ticker">${escapeHtml(cleanTicker(item.ticker))}</div>
                <span class="badge badge-${verdictType}">${escapeHtml(item.verdict)}</span>
            </div>
            <div class="metric-note">News score: <strong>${Number(item.net_news_score || 0).toFixed(2)}</strong> | Headlines: ${item.news_count || 0}</div>
            <p class="mt-16" style="color:var(--text-secondary); line-height:1.5;">${escapeHtml(item.summary || '')}</p>
            <div class="mt-16">${events || '<div class="text-muted">No important events found.</div>'}</div>
        </div>
    `;
}

function renderAnalystReport(report) {
    const container = document.getElementById('analystContent');
    const topEvents = (report.top_events || []).map(renderEventCard).join('');
    const riskCards = (report.risk_stocks || []).map(renderStockReportCard).join('');
    const supportCards = (report.supportive_stocks || []).map(renderStockReportCard).join('');
    const allRows = (report.stock_reports || []).map(item => `
        <tr>
            <td class="text-bold">${escapeHtml(cleanTicker(item.ticker))}</td>
            <td>${escapeHtml(item.verdict)}</td>
            <td class="text-right">${Number(item.net_news_score || 0).toFixed(2)}</td>
            <td class="text-right">${item.news_count || 0}</td>
            <td style="white-space:normal; min-width:260px;">${escapeHtml(item.summary || '')}</td>
        </tr>
    `).join('');

    container.innerHTML = `
        <div class="command-panel ${report.desk_command === 'CAUTION' ? 'wait' : 'trade'} mb-24">
            <div class="flex justify-between items-center gap-16">
                <div>
                    <div class="command-title">Daily News Command</div>
                    <div class="command-subtitle">${escapeHtml(report.desk_reason || '')}</div>
                    <div class="metric-note mt-8">Generated: ${escapeHtml(report.generated_at || '')} | ${escapeHtml(report.source_cost || '')}</div>
                </div>
                ${analystCommandBadge(report.desk_command)}
            </div>
        </div>

        <div class="bento-grid bento-4 mb-24">
            <div class="metric-card">
                <div class="metric-label">Tracked</div>
                <div class="metric-value">${report.counts?.tracked || 0}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Supportive</div>
                <div class="metric-value success">${report.counts?.supportive || 0}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Risk / Caution</div>
                <div class="metric-value warning">${report.counts?.risky || 0}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Neutral</div>
                <div class="metric-value">${report.counts?.neutral || 0}</div>
            </div>
        </div>

        <div class="bento-grid bento-2 mb-24">
            <div>
                <h3 class="section-title">High-Impact Events</h3>
                ${topEvents || '<div class="card-static text-muted">No high-impact news found from free sources.</div>'}
            </div>
            <div>
                <h3 class="section-title">Stocks To Treat Carefully</h3>
                ${riskCards || '<div class="card-static text-muted">No risky stock-specific news found.</div>'}
            </div>
        </div>

        <div class="mb-24">
            <h3 class="section-title">Supportive News Watchlist</h3>
            <div class="bento-grid bento-2">
                ${supportCards || '<div class="card-static text-muted">No strongly supportive stock news found.</div>'}
            </div>
        </div>

        <div class="card-static">
            <h3 class="section-title">All Stock News Scores</h3>
            <div style="overflow-x:auto;">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Verdict</th>
                            <th class="text-right">Score</th>
                            <th class="text-right">Headlines</th>
                            <th>Analyst Summary</th>
                        </tr>
                    </thead>
                    <tbody>${allRows}</tbody>
                </table>
            </div>
        </div>
    `;
}
