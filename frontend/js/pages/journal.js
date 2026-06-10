/* ============================================================
   My Trades (Paper Journal) — Page Module
   ============================================================ */

registerPage('journal', async function(container) {
    container.innerHTML = `
        <h1 class="page-title">My Trades</h1>
        <p class="page-subtitle">View your open practice trades and study your trading history.</p>

        <div class="tabs mt-24">
            <button class="tab active" data-tab="open">Open Trades</button>
            <button class="tab" data-tab="history">Closed Trades</button>
            <button class="tab" data-tab="log">Log Manual Trade</button>
        </div>

        <!-- Open Positions Tab (Active default) -->
        <div class="tab-content active" data-tab="open">
            <div class="metric-card mb-24" style="max-width: 300px;">
                <div class="metric-label">Total Money Made / Lost</div>
                <div id="realizedPnlVal" class="metric-value">...</div>
                <div class="metric-note">From all closed trades (includes 0.15% tax/charge friction)</div>
            </div>
            
            <div class="card">
                <h3 class="section-title">Active Holdings</h3>
                <div id="holdingsTableContainer">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                </div>
            </div>
        </div>

        <!-- History Tab -->
        <div class="tab-content" data-tab="history">
            <div class="card">
                <div class="flex justify-between items-center mb-16">
                    <h3 class="section-title" style="margin:0;">Closed Trades</h3>
                    <button class="btn btn-secondary btn-sm" onclick="exportJournalCSV()">Download CSV</button>
                </div>
                <div id="historyTableContainer">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line"></div>
                </div>
            </div>
        </div>

        <!-- Log Trade Tab -->
        <div class="tab-content" data-tab="log">
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
        if (select) {
            select.innerHTML = watchlistData.map(w => `<option value="${w.ticker}">${cleanTicker(w.ticker)}</option>`).join('');
            
            select.addEventListener('change', async (e) => {
                updatePriceHint(e.target.value);
            });
            
            if (watchlistData.length > 0) {
                updatePriceHint(watchlistData[0].ticker);
            }
        }

        // Render Open Positions
        const rp = document.getElementById('realizedPnlVal');
        if (rp) {
            rp.textContent = formatINR(portfolio.total_realized_pnl);
            rp.className = 'metric-value ' + (portfolio.total_realized_pnl > 0 ? 'success' : portfolio.total_realized_pnl < 0 ? 'danger' : '');
        }

        renderHoldings(portfolio.holdings);
        renderHistory(journal);

    } catch (err) {
        showToast('Failed to load journal data: ' + err.message, 'error');
    }
}

async function updatePriceHint(ticker) {
    const hintEl = document.getElementById('journalPriceHint');
    const priceInput = document.getElementById('journalPrice');
    if (!hintEl || !priceInput) return;
    
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
    if (!container) return;
    
    if (!holdings || holdings.length === 0) {
        container.innerHTML = '<div class="text-muted" style="padding: 24px 0; text-align: center;">No open positions. Log a trade from "Today\'s Picks" to start!</div>';
        return;
    }

    let html = `<div class="journal-cards-grid">`;

    holdings.forEach(h => {
        const cleanSymbol = cleanTicker(h.ticker);
        const pnl = h.unrealized_pnl || 0;
        const pnlPct = h.unrealized_pnl_pct || 0;
        const pnlClass = pnl >= 0 ? 'positive' : 'negative';
        const pnlSign = pnl >= 0 ? '+' : '';

        html += `
            <div class="journal-trade-card">
                <div class="journal-card-header">
                    <span class="journal-card-ticker">${escapeHtml(cleanSymbol)}</span>
                    <span class="journal-card-badge open">🟢 OPEN</span>
                </div>
                <div class="journal-card-body">
                    <div class="journal-detail"><strong>Shares:</strong> ${h.shares}</div>
                    <div class="journal-detail"><strong>Average Buy Price:</strong> ${formatINR(h.avg_cost)}</div>
                    <div class="journal-detail"><strong>Current Live Price:</strong> ${formatINR(h.latest_price)}</div>
                    <div class="journal-pnl ${pnlClass}">
                        <strong>P&L:</strong> ${pnlSign}${formatINR(pnl)} (${formatPct(pnlPct)})
                    </div>
                </div>
                <div class="journal-card-actions">
                    <button class="btn btn-danger btn-sm" onclick="closePosition('${h.ticker}', ${h.shares}, ${h.latest_price}, ${h.avg_cost}, ${h.stop_loss})">
                        Close This Trade
                    </button>
                </div>
            </div>
        `;
    });

    html += `</div>`;
    container.innerHTML = html;
}

function getClosedTrades(transactions) {
    const sorted = [...transactions].sort((a, b) => new Date(a.trade_date || a.logged_at) - new Date(b.trade_date || b.logged_at));
    const holdings = {};
    const closedTrades = [];

    sorted.forEach(t => {
        const ticker = t.ticker.toUpperCase();
        const action = t.action.toUpperCase();
        const qty = parseInt(t.quantity, 10);
        const price = parseFloat(t.price);
        const date = t.trade_date;

        if (!holdings[ticker]) {
            holdings[ticker] = [];
        }

        if (action === 'BUY') {
            holdings[ticker].push({ qty: qty, price: price, date: date });
        } else if (action === 'SELL') {
            let sellQty = qty;
            let totalBuyCost = 0;
            let oldestBuyDate = null;

            while (sellQty > 0 && holdings[ticker].length > 0) {
                const oldestBuy = holdings[ticker][0];
                if (!oldestBuyDate) oldestBuyDate = oldestBuy.date;

                if (oldestBuy.qty <= sellQty) {
                    totalBuyCost += oldestBuy.qty * oldestBuy.price;
                    sellQty -= oldestBuy.qty;
                    holdings[ticker].shift();
                } else {
                    totalBuyCost += sellQty * oldestBuy.price;
                    oldestBuy.qty -= sellQty;
                    sellQty = 0;
                }
            }

            const buyCostWithFriction = totalBuyCost * 1.0015;
            const sellValueWithFriction = (qty - sellQty) * price * 0.9985;
            const pnl = sellValueWithFriction - buyCostWithFriction;

            let durationDays = 0;
            if (oldestBuyDate) {
                const buyD = new Date(oldestBuyDate);
                const sellD = new Date(date);
                const diffTime = Math.abs(sellD - buyD);
                durationDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            }

            closedTrades.push({
                ticker: ticker,
                pnl: pnl,
                duration: durationDays,
                qty: qty - sellQty,
                sellPrice: price,
                buyPrice: totalBuyCost / (qty - sellQty),
                date: date
            });
        }
    });

    return closedTrades.reverse();
}

function renderHistory(history) {
    const container = document.getElementById('historyTableContainer');
    if (!container) return;
    
    if (!history || history.length === 0) {
        container.innerHTML = '<div class="text-muted" style="padding: 24px 0; text-align: center;">No trade history.</div>';
        return;
    }

    const closedTrades = getClosedTrades(history);

    if (closedTrades.length === 0) {
        container.innerHTML = '<div class="text-muted" style="padding: 24px 0; text-align: center;">No closed trades yet. Open positions will appear here once closed.</div>';
        return;
    }

    let html = `<div class="journal-cards-grid">`;

    closedTrades.forEach(t => {
        const cleanSymbol = cleanTicker(t.ticker);
        const pnl = t.pnl;
        const isProfit = pnl >= 0;
        const badgeClass = isProfit ? 'profit' : 'loss';
        const badgeText = isProfit ? '✅ PROFIT' : '❌ LOSS';
        const cardClass = isProfit ? 'journal-trade-card--profit' : 'journal-trade-card--loss';
        
        const durationText = t.duration === 0 ? 'Same day' : t.duration === 1 ? '1 day' : `${t.duration} days`;

        html += `
            <div class="journal-trade-card ${cardClass}" style="border-left: 4px solid ${isProfit ? 'var(--success)' : 'var(--danger)'};">
                <div class="journal-card-header">
                    <span class="journal-card-ticker">${escapeHtml(cleanSymbol)}</span>
                    <span class="journal-card-badge ${badgeClass}">${badgeText}</span>
                </div>
                <div class="journal-card-body">
                    <div class="journal-detail"><strong>Shares:</strong> ${t.qty}</div>
                    <div class="journal-detail"><strong>Bought at:</strong> ${formatINR(t.buyPrice)}</div>
                    <div class="journal-detail"><strong>Sold at:</strong> ${formatINR(t.sellPrice)}</div>
                    <div class="journal-detail"><strong>Duration:</strong> ${durationText}</div>
                    <div class="journal-pnl ${isProfit ? 'positive' : 'negative'}">
                        <strong>${isProfit ? 'Made' : 'Lost'}:</strong> ${formatINR(Math.abs(pnl))}
                    </div>
                </div>
            </div>
        `;
    });

    html += `</div>`;
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

window.closePosition = function(ticker, shares, currentPrice, avgCost, stopLoss) {
    window.currentClosePositionData = {
        ticker: ticker,
        shares: shares,
        avgCost: avgCost,
        stopLoss: stopLoss || (avgCost * 0.98),
        pnl: 0,
        rMultiple: 0
    };
    
    document.getElementById('closeShares').textContent = shares;
    document.getElementById('closeTicker').textContent = cleanTicker(ticker);
    document.getElementById('closeExitPrice').value = currentPrice.toFixed(2);
    document.getElementById('closeEntryPrice').textContent = formatINR(avgCost);
    
    document.getElementById('closePositionModal').classList.add('active');
    
    if (typeof calculateClosePnL === 'function') {
        calculateClosePnL();
    }
};
