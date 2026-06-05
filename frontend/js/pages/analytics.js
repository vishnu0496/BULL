/* ============================================================
   Paper Trade Analytics - Page Module
   ============================================================ */

registerPage('analytics', async function(container) {
    container.innerHTML = `
        <div class="flex justify-between items-center mb-16">
            <div>
                <h1 class="page-title">Paper Trade Analytics</h1>
                <p class="page-subtitle" style="margin-bottom:0;">Measure whether BULL's ideas and your execution are actually improving.</p>
            </div>
            <button id="refreshAnalyticsBtn" class="btn btn-secondary">Refresh Analytics</button>
        </div>

        <div id="analyticsContent">
            <div class="skeleton-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>
        </div>
    `;

    document.getElementById('refreshAnalyticsBtn').addEventListener('click', async () => {
        await loadPaperAnalytics();
    });

    await loadPaperAnalytics();
});

async function loadPaperAnalytics() {
    const container = document.getElementById('analyticsContent');
    try {
        const data = await API.get('/api/journal/analytics');
        renderPaperAnalytics(container, data);
    } catch (err) {
        showError(container, err.message);
    }
}

function renderPaperAnalytics(container, data) {
    const summary = data.summary || {};
    const hasTrades = (summary.total_closed_trades || 0) > 0;
    const pnlClass = summary.net_pnl > 0 ? 'success' : summary.net_pnl < 0 ? 'danger' : 'warning';
    const avgR = summary.avg_r_multiple == null ? 'Not tracked' : `${formatNum(summary.avg_r_multiple, 2)}R`;

    container.innerHTML = `
        ${!hasTrades ? renderAnalyticsEmptyState() : ''}

        <div class="bento-grid bento-4 mb-24 mt-24">
            <div class="metric-card">
                <div class="metric-label">Closed Paper Trades</div>
                <div class="metric-value">${summary.total_closed_trades || 0}</div>
                <div class="metric-note">${summary.total_journal_rows || 0} journal rows logged</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Net Paper PnL</div>
                <div class="metric-value ${pnlClass}">${formatINR(summary.net_pnl || 0)}</div>
                <div class="metric-note">Includes simulated 0.15% friction</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value accent">${formatPct(summary.win_rate || 0)}</div>
                <div class="metric-note">${summary.winning_trades || 0} wins / ${summary.losing_trades || 0} losses</div>
            </div>
            <div class="metric-card">
                <div class="metric-label tooltip-container">
                    Average R-Multiple
                    <span class="tooltip-indicator">?</span>
                    <span class="tooltip-text">R-Multiple measures your risk-reward ratio. An R-Multiple of 2R means your gain was twice the initial amount risked at your stop-loss.</span>
                </div>
                <div class="metric-value ${summary.avg_r_multiple >= 0 ? 'success' : 'danger'}">${avgR}</div>
                <div class="metric-note">${summary.r_tracked_trades || 0} trades with stop-loss in notes</div>
            </div>
        </div>

        <div class="bento-grid bento-2 mb-24">
            <div class="card">
                <h3 class="section-title">Equity Curve</h3>
                <div id="paperEquityChart" class="chart-container" style="height:320px;"></div>
            </div>
            <div class="card">
                <h3 class="section-title">What BULL Learned</h3>
                <div class="learning-list">
                    ${(data.learning_summary || []).map(item => `<div class="learning-item">${escapeHtml(item)}</div>`).join('')}
                </div>
            </div>
        </div>

        <div class="bento-grid bento-2 mb-24">
            ${renderMiniRankingCard('Best Symbols', data.best_symbols || [], 'success')}
            ${renderMiniRankingCard('Weakest Symbols', data.worst_symbols || [], 'danger')}
        </div>

        <div class="bento-grid bento-2 mb-24">
            ${renderGroupTable('By Decision Source', data.groups?.by_source || [])}
            ${renderGroupTable('By Setup Type', data.groups?.by_setup_type || [])}
        </div>

        <div class="bento-grid bento-2 mb-24">
            ${renderGroupTable('By Confidence Bucket', data.groups?.by_confidence_bucket || [])}
            ${renderMistakeLog(data.mistake_log || [])}
        </div>

        <div class="card">
            <div class="flex justify-between items-center mb-16">
                <h3 class="section-title" style="margin:0;">Closed Trade Log</h3>
                <span class="text-muted" style="font-size:0.82rem;">Most recent first</span>
            </div>
            <div style="overflow-x:auto;">
                ${renderClosedTradesTable(data.closed_trades || [])}
            </div>
        </div>
    `;

    renderPaperEquityChart(data.equity_curve || []);
}

function renderAnalyticsEmptyState() {
    return `
        <div class="alert alert-warning">
            <span>!</span>
            <div>
                <strong>No closed paper trades yet.</strong><br>
                Log a BUY and then a matching SELL in Paper Journal. Add notes like "source: Research Desk, confidence: 65%, stop loss: 1240" so analytics can judge the setup properly.
            </div>
        </div>
    `;
}

function renderMiniRankingCard(title, rows, type) {
    const borderColor = type === 'success' ? 'var(--success)' : 'var(--danger)';
    return `
        <div class="card" style="border-top:4px solid ${borderColor};">
            <h3 class="section-title">${escapeHtml(title)}</h3>
            ${rows.length === 0 ? '<div class="text-muted">Not enough closed trades yet.</div>' : `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th class="text-right">Trades</th>
                            <th class="text-right">Win Rate</th>
                            <th class="text-right">Net PnL</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => {
                            const cls = row.net_pnl > 0 ? 'text-success' : row.net_pnl < 0 ? 'text-danger' : '';
                            return `
                                <tr>
                                    <td class="text-bold">${cleanTicker(row.name)}</td>
                                    <td class="text-right">${row.trades}</td>
                                    <td class="text-right">${formatPct(row.win_rate)}</td>
                                    <td class="text-right text-bold ${cls}">${formatINR(row.net_pnl)}</td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `}
        </div>
    `;
}

function renderGroupTable(title, rows) {
    return `
        <div class="card">
            <h3 class="section-title">${escapeHtml(title)}</h3>
            ${rows.length === 0 ? '<div class="text-muted">No grouped results yet.</div>' : `
                <div style="overflow-x:auto;">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th class="text-right">Trades</th>
                                <th class="text-right">Win Rate</th>
                                <th class="text-right">Net PnL</th>
                                <th class="text-right">Avg R</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows.map(row => {
                                const cls = row.net_pnl > 0 ? 'text-success' : row.net_pnl < 0 ? 'text-danger' : '';
                                return `
                                    <tr>
                                        <td class="text-bold">${escapeHtml(row.name)}</td>
                                        <td class="text-right">${row.trades}</td>
                                        <td class="text-right">${formatPct(row.win_rate)}</td>
                                        <td class="text-right text-bold ${cls}">${formatINR(row.net_pnl)}</td>
                                        <td class="text-right">${formatNum(row.avg_r || 0, 2)}R</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            `}
        </div>
    `;
}

function renderMistakeLog(rows) {
    return `
        <div class="card">
            <h3 class="section-title">Mistake Log</h3>
            ${rows.length === 0 ? '<div class="text-muted">No mistake tags detected yet. Be honest in notes after every trade.</div>' : `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Mistake</th>
                            <th class="text-right">Count</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => `
                            <tr>
                                <td class="text-bold">${escapeHtml(row.mistake)}</td>
                                <td class="text-right text-danger">${row.count}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `}
        </div>
    `;
}

function renderClosedTradesTable(rows) {
    if (rows.length === 0) {
        return '<div class="text-muted">No closed trades yet.</div>';
    }

    return `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Exit Date</th>
                    <th>Symbol</th>
                    <th>Result</th>
                    <th class="text-right">Qty</th>
                    <th class="text-right">Entry</th>
                    <th class="text-right">Exit</th>
                    <th class="text-right">PnL</th>
                    <th class="text-right">Return</th>
                    <th>Source</th>
                    <th>Setup</th>
                    <th class="text-right">Confidence</th>
                    <th class="text-right">R</th>
                </tr>
            </thead>
            <tbody>
                ${rows.map(trade => {
                    const pnlClass = trade.pnl > 0 ? 'text-success' : trade.pnl < 0 ? 'text-danger' : '';
                    const resultType = trade.result === 'WIN' ? 'good' : trade.result === 'LOSS' ? 'bad' : 'neutral';
                    return `
                        <tr>
                            <td>${trade.exit_date}</td>
                            <td class="text-bold">${cleanTicker(trade.ticker)}</td>
                            <td>${verdictBadge(resultType === 'good' ? 'GOOD' : resultType === 'bad' ? 'BAD' : 'WEAK')}</td>
                            <td class="text-right">${trade.quantity}</td>
                            <td class="text-right">${formatINR(trade.entry_price)}</td>
                            <td class="text-right">${formatINR(trade.exit_price)}</td>
                            <td class="text-right text-bold ${pnlClass}">${formatINR(trade.pnl)}</td>
                            <td class="text-right ${pnlClass}">${formatPct(trade.return_pct)}</td>
                            <td>${escapeHtml(trade.source)}</td>
                            <td>${escapeHtml(trade.setup_type)}</td>
                            <td class="text-right">${trade.confidence == null ? '-' : formatPct(trade.confidence)}</td>
                            <td class="text-right">${trade.r_multiple == null ? '-' : formatNum(trade.r_multiple, 2) + 'R'}</td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
}

function renderPaperEquityChart(curve) {
    const chartEl = document.getElementById('paperEquityChart');
    if (!chartEl || !window.LightweightCharts) return;
    if (!curve.length) {
        chartEl.innerHTML = '<div class="text-muted" style="padding:24px;">Close paper trades to draw the equity curve.</div>';
        return;
    }

    const chart = LightweightCharts.createChart(chartEl, {
        layout: { background: { color: 'transparent' }, textColor: '#94A3B8' },
        grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
        timeScale: { borderColor: 'rgba(255,255,255,0.08)' },
        height: 320,
    });

    const seriesFactory = chart.addAreaSeries || chart.addLineSeries;
    const series = seriesFactory.call(chart, {
        lineColor: '#38BDF8',
        topColor: 'rgba(56,189,248,0.25)',
        bottomColor: 'rgba(56,189,248,0.02)',
        lineWidth: 2,
    });

    series.setData(curve.map(row => ({
        time: row.date,
        value: Number(row.cumulative_pnl || 0),
    })));
    chart.timeScale().fitContent();
}
