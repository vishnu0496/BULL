/* ============================================================
   Paper Journal — Page Module
   ============================================================ */

registerPage('journal', async function(container) {
    container.innerHTML = `
        <h1 class="page-title">Paper Journal</h1>
        <p class="page-subtitle">Log your simulated trades, track open positions, and review your historical performance.</p>

        <div class="tabs mt-24">
            <button class="tab active" data-tab="log">Log New Trade</button>
            <button class="tab" data-tab="open">Open Positions</button>
            <button class="tab" data-tab="history">Trade History</button>
        </div>

        <!-- Log Trade Tab -->
        <div class="tab-content active" data-tab="log">
            <div class="card" style="max-width: 600px;">
                <h3 class="section-title">Record Practice Trade</h3>
                
                <div class="form-group">
                    <label class="form-label">Symbol</label>
                    <select id="journalSymbolSelect" class="form-select"></select>
                    <div id="journalPriceHint" class="form-hint"></div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Action</label>
                        <select id="journalAction" class="form-select">
                            <option value="BUY">BUY</option>
                            <option value="SELL">SELL</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Date</label>
                        <input type="date" id="journalDate" class="form-input">
                    </div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Quantity (Shares)</label>
                        <input type="number" id="journalQty" class="form-input" min="1" value="10">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Price (₹)</label>
                        <input type="number" id="journalPrice" class="form-input" min="0.01" step="0.01">
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">Notes & Reason</label>
                    <textarea id="journalNotes" class="form-textarea" placeholder="Why are you taking this trade? What is your target and stop loss?"></textarea>
                </div>

                <button class="btn btn-primary btn-full mt-16" onclick="submitPaperTrade()">Save Simulated Trade</button>
            </div>
        </div>

        <!-- Open Positions Tab -->
        <div class="tab-content" data-tab="open">
            <div class="metric-card mb-24" style="max-width: 300px;">
                <div class="metric-label">Total Realized PnL</div>
                <div id="realizedPnlVal" class="metric-value">...</div>
                <div class="metric-note">From all closed trades (incl. 0.15% friction)</div>
            </div>
            
            <div class="card">
                <h3 class="section-title">Active Holdings</h3>
                <div id="holdingsTableContainer" style="overflow-x: auto;">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                </div>
            </div>
        </div>

        <!-- History Tab -->
        <div class="tab-content" data-tab="history">
            <div class="card">
                <div class="flex justify-between items-center mb-16">
                    <h3 class="section-title" style="margin:0;">Trade Log</h3>
                    <button class="btn btn-secondary btn-sm" onclick="exportJournalCSV()">Download CSV</button>
                </div>
                <div id="historyTableContainer" style="overflow-x: auto;">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                </div>
            </div>
        </div>
    `;

    initTabs(container);
    
    // Set today's date as default
    document.getElementById('journalDate').value = new Date().toISOString().split('T')[0];

    await loadJournalData();
});

let watchlistData = [];
let journalData = [];

async function loadJournalData() {
    try {
        const [watchlist, portfolio, journal] = await Promise.all([
            API.get('/api/watchlist'),
            API.get('/api/portfolio'),
            API.get('/api/journal')
        ]);

        watchlistData = watchlist.filter(w => !w.ticker.startsWith('^'));
        journalData = journal;

        // Populate select and setup price hint
        const select = document.getElementById('journalSymbolSelect');
        select.innerHTML = watchlistData.map(w => `<option value="${w.ticker}">${cleanTicker(w.ticker)}</option>`).join('');
        
        select.addEventListener('change', async (e) => {
            updatePriceHint(e.target.value);
        });
        
        if (watchlistData.length > 0) {
            updatePriceHint(watchlistData[0].ticker);
        }

        // Render Open Positions
        const rp = document.getElementById('realizedPnlVal');
        rp.textContent = formatINR(portfolio.total_realized_pnl);
        rp.className = 'metric-value ' + (portfolio.total_realized_pnl > 0 ? 'success' : portfolio.total_realized_pnl < 0 ? 'danger' : '');

        renderHoldings(portfolio.holdings);
        renderHistory(journal);

    } catch (err) {
        showToast('Failed to load journal data: ' + err.message, 'error');
    }
}

async function updatePriceHint(ticker) {
    const hintEl = document.getElementById('journalPriceHint');
    const priceInput = document.getElementById('journalPrice');
    
    hintEl.textContent = 'Fetching latest price...';
    try {
        const prices = await API.get(`/api/prices/${ticker}`);
        if (prices && prices.length > 0) {
            const latest = prices[prices.length - 1];
            hintEl.textContent = `Latest stored close: ${formatINR(latest.close)} (on ${latest.date.split('T')[0]})`;
            priceInput.value = latest.close.toFixed(2);
        } else {
            hintEl.textContent = 'No price data available.';
        }
    } catch (err) {
        hintEl.textContent = 'Error fetching price.';
    }
}

async function submitPaperTrade() {
    const ticker = document.getElementById('journalSymbolSelect').value;
    const action = document.getElementById('journalAction').value;
    const date = document.getElementById('journalDate').value;
    const qty = parseInt(document.getElementById('journalQty').value, 10);
    const price = parseFloat(document.getElementById('journalPrice').value);
    const notes = document.getElementById('journalNotes').value;

    if (!ticker || !date || isNaN(qty) || qty <= 0 || isNaN(price) || price <= 0) {
        showToast('Please fill all fields correctly.', 'error');
        return;
    }

    try {
        await API.post('/api/journal', {
            ticker: ticker,
            trade_date: date,
            action: action,
            quantity: qty,
            price: price,
            notes: notes
        });

        showToast('Trade logged successfully.', 'success');
        
        // Reset form
        document.getElementById('journalQty').value = '10';
        document.getElementById('journalNotes').value = '';
        
        // Reload data
        await loadJournalData();
    } catch (err) {
        showToast('Failed to log trade: ' + err.message, 'error');
    }
}

function renderHoldings(holdings) {
    const container = document.getElementById('holdingsTableContainer');
    
    if (!holdings || holdings.length === 0) {
        container.innerHTML = '<div class="text-muted">No open positions.</div>';
        return;
    }

    let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th class="text-right">Shares</th>
                    <th class="text-right">Avg Cost</th>
                    <th class="text-right">Latest Price</th>
                    <th class="text-right">Total Cost</th>
                    <th class="text-right">Current Value</th>
                    <th class="text-right">Unrealized PnL</th>
                    <th class="text-right">PnL %</th>
                    <th class="text-right">Action</th>
                </tr>
            </thead>
            <tbody>
    `;

    holdings.forEach(h => {
        const pnlColor = h.unrealized_pnl > 0 ? 'text-success' : h.unrealized_pnl < 0 ? 'text-danger' : '';
        html += `
            <tr>
                <td class="text-bold">${cleanTicker(h.ticker)}</td>
                <td class="text-right">${h.shares}</td>
                <td class="text-right">${formatINR(h.avg_cost)}</td>
                <td class="text-right">${formatINR(h.latest_price)}</td>
                <td class="text-right">${formatINR(h.total_cost)}</td>
                <td class="text-right">${formatINR(h.current_value)}</td>
                <td class="text-right text-bold ${pnlColor}">${formatINR(h.unrealized_pnl)}</td>
                <td class="text-right text-bold ${pnlColor}">${formatPct(h.unrealized_pnl_pct)}</td>
                <td class="text-right">
                    <button class="btn btn-danger btn-sm" onclick="closePosition('${h.ticker}', ${h.shares}, ${h.latest_price})">Close</button>
                </td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

function renderHistory(history) {
    const container = document.getElementById('historyTableContainer');
    
    if (!history || history.length === 0) {
        container.innerHTML = '<div class="text-muted">No trade history.</div>';
        return;
    }

    let html = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th class="text-right">Quantity</th>
                    <th class="text-right">Price</th>
                    <th>Notes</th>
                </tr>
            </thead>
            <tbody>
    `;

    history.forEach(t => {
        const actionBadge = t.action === 'BUY' 
            ? `<span class="badge" style="background:var(--success-dim); color:var(--success)">BUY</span>`
            : `<span class="badge" style="background:var(--danger-dim); color:var(--danger)">SELL</span>`;
            
        html += `
            <tr>
                <td>${t.trade_date}</td>
                <td class="text-bold">${cleanTicker(t.ticker)}</td>
                <td>${actionBadge}</td>
                <td class="text-right">${t.quantity}</td>
                <td class="text-right">${formatINR(t.price)}</td>
                <td style="white-space: normal; max-width: 300px;">${escapeHtml(t.notes || '')}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
}

function exportJournalCSV() {
    if (!journalData || journalData.length === 0) {
        showToast('No data to export.', 'error');
        return;
    }
    
    const headers = ['ID', 'Ticker', 'Date', 'Action', 'Quantity', 'Price', 'Notes', 'Logged_At'];
    const csvRows = [headers.join(',')];
    
    journalData.forEach(row => {
        const values = [
            row.id,
            row.ticker,
            row.trade_date,
            row.action,
            row.quantity,
            row.price,
            `"${(row.notes || '').replace(/"/g, '""')}"`,
            row.logged_at
        ];
        csvRows.push(values.join(','));
    });
    
    const csvString = csvRows.join('\n');
    const blob = new Blob([csvString], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.setAttribute('hidden', '');
    a.setAttribute('href', url);
    a.setAttribute('download', 'bull_paper_trades.csv');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

window.closePosition = async function(ticker, shares, currentPrice) {
    if (!confirm(`Are you sure you want to close your position in ${cleanTicker(ticker)} by selling all ${shares} shares at ₹${currentPrice.toFixed(2)}?`)) {
        return;
    }
    try {
        const today = new Date().toISOString().split('T')[0];
        await API.post('/api/journal', {
            ticker: ticker,
            trade_date: today,
            action: 'SELL',
            quantity: shares,
            price: currentPrice,
            notes: 'Manually closed position via Active Holdings tab.'
        });
        showToast(`Successfully closed position in ${cleanTicker(ticker)} by selling ${shares} shares.`, 'success');
        await loadJournalData();
    } catch (err) {
        showToast('Failed to close position: ' + err.message, 'error');
    }
};
