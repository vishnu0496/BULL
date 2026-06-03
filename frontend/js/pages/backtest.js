/* ============================================================
   Backtest Lab — Page Module
   ============================================================ */

registerPage('backtest', async function(container) {
    container.innerHTML = `
        <h1 class="page-title">Backtest Lab</h1>
        <p class="page-subtitle">Simulate historical trading performance based on the current algorithm settings to evaluate statistical edge.</p>

        <div class="card" style="max-width: 600px; margin-bottom: 24px;">
            <div class="form-row items-center">
                <div class="form-group" style="margin: 0; flex: 1;">
                    <label class="form-label">Select Stock to Backtest</label>
                    <select id="backtestSymbolSelect" class="form-select"></select>
                </div>
                <button id="runBacktestBtn" class="btn btn-primary" style="margin-top: 22px;">
                    ▶ Run Simulation
                </button>
            </div>
        </div>

        <div id="backtestResults" style="display: none;">
            <div class="bento-grid bento-4 mb-24">
                <div class="metric-card">
                    <div class="metric-label">Net Profit/Loss</div>
                    <div id="btNetProfit" class="metric-value">...</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Win Rate</div>
                    <div id="btWinRate" class="metric-value accent">...</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Total Trades</div>
                    <div id="btTotalTrades" class="metric-value">...</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Win / Avg Loss</div>
                    <div id="btAvgWinLoss" class="metric-value" style="font-size: 1.2rem; margin-top: 6px;">...</div>
                </div>
            </div>

            <div class="card mb-24">
                <h3 class="section-title">Cumulative PnL</h3>
                <div id="pnlChartContainer" class="chart-container" style="height: 350px;"></div>
            </div>

            <div class="card">
                <div class="flex justify-between items-center mb-16">
                    <h3 class="section-title" style="margin:0;">Trade Log</h3>
                    <button class="btn btn-secondary btn-sm" onclick="exportBacktestCSV()">Download CSV</button>
                </div>
                <div id="btTableContainer" style="overflow-x: auto; max-height: 400px;"></div>
            </div>
        </div>
    `;

    try {
        const watchlist = await API.get('/api/watchlist');
        const select = document.getElementById('backtestSymbolSelect');
        const validSymbols = watchlist.filter(w => !w.ticker.startsWith('^'));
        
        select.innerHTML = validSymbols.map(w => `<option value="${w.ticker}">${cleanTicker(w.ticker)}</option>`).join('');

        document.getElementById('runBacktestBtn').addEventListener('click', () => {
            runBacktest(select.value);
        });

    } catch (err) {
        showToast('Failed to load watchlist for backtester.', 'error');
    }
});

let currentBacktestData = null;
let pnlChart = null;
let pnlSeries = null;

async function runBacktest(ticker) {
    if (!ticker) return;

    const btn = document.getElementById('runBacktestBtn');
    const originalText = btn.innerText;
    btn.innerText = 'Simulating...';
    btn.disabled = true;

    try {
        const results = await API.get(`/api/backtest/${ticker}`);
        currentBacktestData = results;
        
        document.getElementById('backtestResults').style.display = 'block';

        // Render Metrics
        const npEl = document.getElementById('btNetProfit');
        npEl.textContent = formatINR(results.net_profit);
        npEl.className = 'metric-value ' + (results.net_profit > 0 ? 'success' : results.net_profit < 0 ? 'danger' : '');
        
        document.getElementById('btWinRate').textContent = formatPct(results.win_rate * 100);
        document.getElementById('btTotalTrades').textContent = results.total_trades;
        
        document.getElementById('btAvgWinLoss').innerHTML = `
            <span class="text-success">${formatINR(results.avg_win)}</span> / 
            <span class="text-danger">${formatINR(results.avg_loss)}</span>
        `;

        // Render Chart
        renderPnLChart(results.trades_log);

        // Render Table
        renderBacktestTable(results.trades_log);

    } catch (err) {
        showToast('Backtest failed: ' + err.message, 'error');
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

function renderPnLChart(tradesLog) {
    const container = document.getElementById('pnlChartContainer');
    
    if (!tradesLog || tradesLog.length === 0) {
        container.innerHTML = '<div style="padding:20px; color:var(--text-muted); text-align:center;">No trades generated to plot.</div>';
        return;
    }

    container.innerHTML = ''; // Clear old chart

    const chartOptions = {
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#94a3b8',
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
        },
        rightPriceScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            timeVisible: true,
        },
        height: 350
    };

    if (pnlChart) { pnlChart.remove(); }
    pnlChart = LightweightCharts.createChart(container, chartOptions);
    if (typeof pnlChart.addAreaSeries === 'function') {
        pnlSeries = pnlChart.addAreaSeries({
            lineColor: '#38bdf8',
            topColor: 'rgba(56, 189, 248, 0.4)',
            bottomColor: 'rgba(56, 189, 248, 0.0)',
            lineWidth: 2,
        });
    } else {
        pnlSeries = pnlChart.addLineSeries({
            color: '#38bdf8',
            lineWidth: 2,
        });
    }

    let cumulativePnl = 0;
    const chartData = tradesLog.map(t => {
        cumulativePnl += t.pnl;
        return {
            time: t.exit_date.split('T')[0],
            value: cumulativePnl
        };
    }).sort((a, b) => new Date(a.time) - new Date(b.time));

    pnlSeries.setData(chartData);
    pnlChart.timeScale().fitContent();
}

function renderBacktestTable(trades) {
    const container = document.getElementById('btTableContainer');
    
    if (!trades || trades.length === 0) {
        container.innerHTML = '<div class="text-muted">No trades generated.</div>';
        return;
    }

    let html = `
        <table class="data-table">
            <thead style="position: sticky; top: 0; background: var(--bg-surface); z-index: 1;">
                <tr>
                    <th>Entry Date</th>
                    <th>Exit Date</th>
                    <th class="text-right">Entry Price</th>
                    <th class="text-right">Exit Price</th>
                    <th>Exit Reason</th>
                    <th class="text-right">Quantity</th>
                    <th class="text-right">Trade PnL</th>
                </tr>
            </thead>
            <tbody>
    `;

    trades.forEach(t => {
        const pnlColor = t.pnl > 0 ? 'text-success' : t.pnl < 0 ? 'text-danger' : '';
        const reasonBadge = t.type === 'TARGET' 
            ? `<span class="badge badge-success">TARGET HIT</span>` 
            : `<span class="badge badge-danger">STOP LOSS</span>`;

        html += `
            <tr>
                <td>${t.entry_date}</td>
                <td>${t.exit_date}</td>
                <td class="text-right">${formatINR(t.entry_price)}</td>
                <td class="text-right">${formatINR(t.exit_price)}</td>
                <td>${reasonBadge}</td>
                <td class="text-right">${t.quantity}</td>
                <td class="text-right text-bold ${pnlColor}">${formatINR(t.pnl)}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

function exportBacktestCSV() {
    if (!currentBacktestData || !currentBacktestData.trades_log || currentBacktestData.trades_log.length === 0) {
        showToast('No backtest data to export.', 'error');
        return;
    }
    
    const headers = ['Entry Date', 'Exit Date', 'Entry Price', 'Exit Price', 'Exit Reason', 'Quantity', 'Trade PnL'];
    const csvRows = [headers.join(',')];
    
    currentBacktestData.trades_log.forEach(row => {
        csvRows.push([
            row.entry_date,
            row.exit_date,
            row.entry_price,
            row.exit_price,
            row.type,
            row.quantity,
            row.pnl
        ].join(','));
    });
    
    const csvString = csvRows.join('\n');
    const blob = new Blob([csvString], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.setAttribute('hidden', '');
    a.setAttribute('href', url);
    a.setAttribute('download', 'backtest_logs.csv');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}
