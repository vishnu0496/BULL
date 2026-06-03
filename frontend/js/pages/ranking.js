/* ============================================================
   Strategy Ranking Report — Page Module
   ============================================================ */

registerPage('ranking', async function(container) {
    container.innerHTML = `
        <div class="flex justify-between items-center mb-16">
            <div>
                <h1 class="page-title">Strategy Ranking Report</h1>
                <p class="page-subtitle" style="margin-bottom:0;">Automated historical performance ranking of all watchlist stocks.</p>
            </div>
            <button id="refreshRanksBtn" class="btn btn-secondary">♻️ Refresh Strategy Ranks</button>
        </div>

        <div id="rankingContent">
            <div class="skeleton-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>
        </div>
    `;

    document.getElementById('refreshRanksBtn').addEventListener('click', async (e) => {
        const btn = e.target;
        btn.disabled = true;
        btn.innerText = 'Refreshing...';
        await loadRankingData();
        btn.disabled = false;
        btn.innerText = '♻️ Refresh Strategy Ranks';
    });

    await loadRankingData();
});

async function loadRankingData() {
    const container = document.getElementById('rankingContent');
    
    try {
        const verdicts = await API.get('/api/verdicts');
        
        const good = verdicts.filter(v => v.verdict === 'GOOD');
        const bad = verdicts.filter(v => v.verdict === 'BAD');

        let html = `
            <div class="bento-grid bento-2 mb-24 mt-24">
                <div class="card" style="border-top: 4px solid var(--success); background: linear-gradient(135deg, rgba(16,185,129,0.05) 0%, var(--bg-surface) 100%);">
                    <h3 class="section-title"><span class="icon">🟢</span> Trusted Symbols</h3>
                    <p class="text-muted" style="font-size:0.85rem; margin-bottom:12px;">High historical win rate and positive expectancy.</p>
                    <div class="flex gap-8" style="flex-wrap: wrap;">
                        ${good.length > 0 ? good.map(v => `<span class="badge badge-good">${cleanTicker(v.ticker)}</span>`).join('') : '<span class="text-muted">None currently.</span>'}
                    </div>
                </div>
                
                <div class="card" style="border-top: 4px solid var(--danger); background: linear-gradient(135deg, rgba(244,63,94,0.05) 0%, var(--bg-surface) 100%);">
                    <h3 class="section-title"><span class="icon">🔴</span> Do Not Trade List</h3>
                    <p class="text-muted" style="font-size:0.85rem; margin-bottom:12px;">Poor historical edge. Avoid trading these setups.</p>
                    <div class="flex gap-8" style="flex-wrap: wrap;">
                        ${bad.length > 0 ? bad.map(v => `<span class="badge badge-bad">${cleanTicker(v.ticker)}</span>`).join('') : '<span class="text-muted">None currently.</span>'}
                    </div>
                </div>
            </div>

            <div class="card">
                <h3 class="section-title">Full Watchlist Ranking</h3>
                <div style="overflow-x: auto;">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Verdict</th>
                                <th class="text-right">Net PnL</th>
                                <th class="text-right">Win Rate</th>
                                <th class="text-right">Total Trades</th>
                                <th class="text-right">Expectancy</th>
                                <th class="text-right">Avg Win</th>
                                <th class="text-right">Avg Loss</th>
                                <th>Reasoning</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${verdicts.map(v => {
                                const pnlColor = v.net_profit > 0 ? 'text-success' : v.net_profit < 0 ? 'text-danger' : '';
                                return `
                                    <tr>
                                        <td class="text-bold">${cleanTicker(v.ticker)}</td>
                                        <td>${verdictBadge(v.verdict)}</td>
                                        <td class="text-right text-bold ${pnlColor}">${formatINR(v.net_profit)}</td>
                                        <td class="text-right">${formatPct(v.win_rate * 100)}</td>
                                        <td class="text-right">${v.total_trades}</td>
                                        <td class="text-right">${formatINR(v.expectancy)}</td>
                                        <td class="text-right text-success">${formatINR(v.avg_win)}</td>
                                        <td class="text-right text-danger">${formatINR(v.avg_loss)}</td>
                                        <td class="text-muted" style="font-size:0.8rem; white-space:normal; min-width:200px;">${escapeHtml(v.reason)}</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        
        container.innerHTML = html;

    } catch (err) {
        showError(container, err.message);
    }
}
