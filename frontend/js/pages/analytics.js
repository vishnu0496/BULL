/* ============================================================
   My Results (Paper Trade Analytics) - Page Module
   ============================================================ */

registerPage('analytics', async function(container) {
    container.innerHTML = `
        <div class="flex justify-between items-center mb-16">
            <div>
                <h1 class="page-title">My Results</h1>
                <p class="page-subtitle" style="margin-bottom:0;">Track whether you are making progress and learning the rules.</p>
            </div>
            <button id="refreshAnalyticsBtn" class="btn btn-secondary">Refresh Results</button>
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

function getMonthlyPnL(closedTrades) {
    const monthly = {};
    (closedTrades || []).forEach(t => {
        const date = new Date(t.exit_date);
        const monthKey = date.toLocaleString('default', { month: 'short', year: 'numeric' }); // e.g. "Jun 2026"
        if (!monthly[monthKey]) monthly[monthKey] = 0;
        monthly[monthKey] += t.pnl;
    });
    return monthly;
}

function renderPaperAnalytics(container, data) {
    const summary = data.summary || {};
    const hasTrades = (summary.total_closed_trades || 0) > 0;
    
    // Calculate trades to unlock next level (target 20 trades)
    const tradesNeeded = Math.max(0, 20 - summary.total_closed_trades);
    
    // Determine plain English verdict
    let verdictText = '';
    if (summary.total_closed_trades === 0) {
        verdictText = "Start logging trades to see your performance verdict!";
    } else if (summary.net_pnl > 0 && summary.win_rate >= 50) {
        verdictText = "You are doing <strong>WELL</strong>! Keep following the rules.";
    } else if (summary.net_pnl > -500 && summary.net_pnl <= 0) {
        verdictText = "You are doing <strong>OK</strong>. Minimize small mistakes to become profitable.";
    } else {
        verdictText = "<strong>Keep practicing!</strong> Study the school lessons and focus on stop loss rules.";
    }

    // Monthly P&L calculation
    const monthlyPnL = getMonthlyPnL(data.closed_trades || []);
    const months = Object.keys(monthlyPnL).reverse(); // Show oldest to newest
    
    // Generate monthly bars
    const maxVal = Math.max(...Object.values(monthlyPnL).map(Math.abs), 1);
    const monthlyHtml = months.map(m => {
        const val = monthlyPnL[m];
        const isPositive = val >= 0;
        const heightPct = Math.max(5, Math.min(100, (Math.abs(val) / maxVal) * 100));
        
        return `
            <div style="display: flex; flex-direction: column; align-items: center; gap: 8px; flex: 1; min-width: 50px;">
                <div style="font-size: 0.75rem; font-weight: 700; color: ${isPositive ? 'var(--success)' : 'var(--danger)'};">
                    ${isPositive ? '+' : ''}₹${Math.round(val)}
                </div>
                <div style="height: 100px; display: flex; align-items: ${isPositive ? 'flex-end' : 'flex-start'}; width: 20px; background: rgba(255,255,255,0.02); border-radius: 4px;">
                    <div style="height: ${heightPct}%; width: 100%; background: ${isPositive ? 'var(--success)' : 'var(--danger)'}; border-radius: 4px;"></div>
                </div>
                <div style="font-size: 0.72rem; color: var(--text-muted); text-align: center;">${m}</div>
            </div>
        `;
    }).join('');

    if (!hasTrades) {
        container.innerHTML = `
            <div class="alert alert-warning" style="margin-bottom: 24px;">
                <span>⚠️</span>
                <div>
                    <strong>No closed practice trades yet.</strong><br>
                    Once you close your first trade, your performance charts and results summary will appear here.
                </div>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="results-summary-card">
            <div class="results-summary-title">My Performance Summary</div>
            <div class="results-summary-row">
                <span class="results-summary-label">Total Trades Logged</span>
                <span class="results-summary-value big">${summary.total_closed_trades || 0}</span>
            </div>
            <div class="results-summary-row">
                <span class="results-summary-label">Winning Trades</span>
                <span class="results-summary-value" style="color: var(--success);">${summary.winning_trades || 0}</span>
            </div>
            <div class="results-summary-row">
                <span class="results-summary-label">Losing Trades</span>
                <span class="results-summary-value" style="color: var(--danger);">${summary.losing_trades || 0}</span>
            </div>
            <div class="results-summary-row">
                <span class="results-summary-label">Total Money Made</span>
                <span class="results-summary-value" style="color: var(--success);">${formatINR(summary.avg_win * summary.winning_trades)}</span>
            </div>
            <div class="results-summary-row">
                <span class="results-summary-label">Total Money Lost</span>
                <span class="results-summary-value" style="color: var(--danger);">${formatINR(Math.abs(summary.avg_loss * summary.losing_trades))}</span>
            </div>
            <div class="results-summary-row">
                <span class="results-summary-label">Net Profit / Loss</span>
                <span class="results-summary-value big ${summary.net_pnl >= 0 ? 'positive' : 'negative'}">${summary.net_pnl >= 0 ? '+' : ''}${formatINR(summary.net_pnl || 0)}</span>
            </div>
            <div class="results-summary-row">
                <span class="results-summary-label">Trades to Unlock Next Level</span>
                <span class="results-summary-value">${tradesNeeded}</span>
            </div>
            <div class="results-summary-verdict">
                Verdict: ${verdictText}
            </div>
        </div>

        <div class="bento-grid bento-2 mb-24">
            <div class="card">
                <h3 class="section-title">Did you make or lose money each month?</h3>
                <div style="display: flex; justify-content: space-around; align-items: flex-end; gap: 12px; height: 140px; margin-top: 24px; padding-bottom: 8px; overflow-x: auto;">
                    ${monthlyHtml || '<div class="text-muted" style="width:100%; text-align:center;">No trade history yet.</div>'}
                </div>
            </div>
            
            <div class="card">
                <h3 class="section-title">How often does BULL get it right?</h3>
                <div style="margin: 32px 0 20px;">
                    <div style="display: flex; justify-content: space-between; font-size: 1.1rem; font-weight: 700; margin-bottom: 8px;">
                        <span>Win Rate</span>
                        <span style="color: var(--success);">${summary.win_rate.toFixed(1)}%</span>
                    </div>
                    <div style="background: rgba(255,255,255,0.05); height: 16px; border-radius: 8px; overflow: hidden;">
                        <div style="background: linear-gradient(90deg, var(--success), var(--accent)); height: 100%; width: ${summary.win_rate}%; transition: width 1s ease-in-out;"></div>
                    </div>
                    <div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 12px; text-align: center;">
                        ${summary.winning_trades} winning trades vs ${summary.losing_trades} losing trades.
                    </div>
                </div>
            </div>
        </div>
    `;
}
