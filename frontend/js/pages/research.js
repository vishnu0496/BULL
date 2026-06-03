/* ============================================================
   Pre-Market Research Desk — Page Module
   ============================================================ */

registerPage('research', async function(container) {
    container.innerHTML = `
        <h1 class="page-title">Pre-Market Research Desk</h1>
        <p class="page-subtitle">Evaluate watchlist stocks, generate technical buy triggers, and inspect charts offline.</p>

        <div id="researchTopContent">
            <div class="skeleton-header"></div>
            <div class="skeleton-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>
        </div>

        <div class="bento-grid bento-2-1 mt-24" id="researchBentoGrid" style="display: none;">
            <!-- Left Column -->
            <div class="flex-col gap-20">
                <div id="bestOpportunityContainer"></div>
                
                <div class="card">
                    <h3 class="section-title">Stock Chart</h3>
                    <div class="flex justify-between items-center mb-16">
                        <select id="chartSymbolSelect" class="form-select" style="max-width: 200px;"></select>
                    </div>
                    <div id="chartContainer" class="chart-container"></div>
                </div>

                <div class="card">
                    <h3 class="section-title">Watchlist Management</h3>
                    <div class="form-row">
                        <div>
                            <label class="form-label">Add New Symbol</label>
                            <div class="flex gap-8">
                                <input type="text" id="addSymbolInput" class="form-input" placeholder="e.g. RELIANCE">
                                <button class="btn btn-secondary" onclick="addWatchlistSymbol()">Add & Sync</button>
                            </div>
                        </div>
                        <div>
                            <label class="form-label">Remove Symbol</label>
                            <div class="flex gap-8">
                                <select id="removeSymbolSelect" class="form-select"></select>
                                <button class="btn btn-danger" onclick="removeWatchlistSymbol()">Delete</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Right Column -->
            <div class="flex-col gap-20">
                <div class="card" style="height: 100%;">
                    <h3 class="section-title">Watchlist Opportunities</h3>
                    <div id="watchlistList" class="flex-col gap-12 mt-16" style="max-height: 800px; overflow-y: auto; padding-right: 8px;">
                        <!-- Mini cards injected here -->
                    </div>
                </div>
            </div>
        </div>
    `;

    await loadResearchData();
});

async function loadResearchData() {
    try {
        const [regime, capital, watchlist, ideas] = await Promise.all([
            API.get('/api/market/regime'),
            API.get('/api/capital'),
            API.get('/api/watchlist'),
            API.get('/api/ideas')
        ]);

        renderTopContent(regime, capital, watchlist, ideas);
        renderWatchlistList(ideas);
        populateSelectors(watchlist);
        
        document.getElementById('researchBentoGrid').style.display = 'grid';
        
        if (ideas.length > 0) {
            renderBestOpportunity(ideas[0]);
        } else {
            document.getElementById('bestOpportunityContainer').innerHTML = '<div class="card">No setups available.</div>';
        }

        if (watchlist.length > 0) {
            await loadAndRenderChart(watchlist[0].ticker);
            document.getElementById('chartSymbolSelect').value = watchlist[0].ticker;
        }

        // Setup chart selector listener
        document.getElementById('chartSymbolSelect').addEventListener('change', (e) => {
            loadAndRenderChart(e.target.value);
        });

    } catch (err) {
        showError(document.getElementById('researchTopContent'), err.message);
    }
}

function renderTopContent(regime, capital, watchlist, ideas) {
    const bias = regime.market_bias || 'NEUTRAL';
    let commandClass = 'wait';
    let commandTitle = 'WAIT - Market is Neutral';
    let commandText = 'The market lacks clear direction. Preserve capital and wait for a strong trend.';

    if (bias === 'BULLISH') {
        const validTrades = ideas.filter(i => i.decision === 'TRADE').length;
        if (validTrades > 0) {
            commandClass = 'trade';
            commandTitle = 'TRADE - Market is Bullish';
            commandText = `Market conditions are favorable. We have ${validTrades} qualified setups ready.`;
        } else {
            commandClass = 'wait';
            commandTitle = 'WAIT - No Setups';
            commandText = 'Market is Bullish, but no individual stocks meet our strict entry criteria today.';
        }
    } else if (bias === 'BEARISH') {
        commandClass = 'avoid';
        commandTitle = 'NO TRADE - Market is Bearish';
        commandText = 'The broader market is in a downtrend. Cash is the safest position right now. Do not buy dips.';
    }

    const activeSetups = ideas.filter(i => i.decision === 'TRADE').length;
    const totalCapital = capital.total_capital || 0;

    let html = `
        <div class="command-panel ${commandClass} mb-24">
            <div class="command-title" style="color: var(--${commandClass === 'trade' ? 'success' : commandClass === 'avoid' ? 'danger' : 'warning'});">
                TODAY'S COMMAND: ${commandTitle}
            </div>
            <div class="command-subtitle">${escapeHtml(commandText)}</div>
        </div>

        <div class="bento-grid bento-4 mb-24">
            <div class="metric-card">
                <div class="metric-label">Market Bias</div>
                <div class="metric-value ${bias === 'BULLISH' ? 'success' : bias === 'BEARISH' ? 'danger' : 'warning'}">${escapeHtml(bias)}</div>
                <div class="metric-note">Trend: ${regime.trend_score}/100 | Volatility: ${regime.volatility_score}/100</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Capital</div>
                <div class="metric-value">${formatINR(totalCapital)}</div>
                <div class="metric-note">Max Risk: ${formatINR(capital.max_risk_per_trade || 0)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Active Setups</div>
                <div class="metric-value accent">${activeSetups}</div>
                <div class="metric-note">Out of ${ideas.length} scanned stocks</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Watchlist Size</div>
                <div class="metric-value">${watchlist.length}</div>
                <div class="metric-note">Symbols tracked locally</div>
            </div>
        </div>
    `;

    document.getElementById('researchTopContent').innerHTML = html;
}

function renderBestOpportunity(idea) {
    const sym = cleanTicker(idea.ticker);
    const dec = idea.decision || 'WAIT';
    
    let html = `
        <div class="card best-opp-card" data-ticker="${idea.ticker}" style="border-left: 4px solid ${dec === 'TRADE' ? 'var(--success)' : 'var(--warning)'}">
            <div class="flex justify-between items-center mb-16">
                <div>
                    <h3 class="section-title" style="margin:0;">Best Watchlist Opportunity</h3>
                    <div style="font-size:1.8rem; font-weight:800; color:var(--text-primary); margin-top:8px;">
                        ${escapeHtml(sym)}
                        <span class="live-price" data-trigger="${idea.entry_trigger}" style="font-size:1.1rem; font-weight:700; color:var(--text-secondary); margin-left:12px;">₹...</span>
                    </div>
                </div>
                <div>${decisionBadge(dec)}</div>
            </div>

            <div class="pick-justification">
                <div class="pick-justification-label">Technical Setup</div>
                <div class="pick-justification-text">
                    ${idea.reasons && idea.reasons.length > 0 ? idea.reasons.map(r => `• ${escapeHtml(r)}`).join('<br>') : 'Setup details not available.'}
                </div>
            </div>

            <table class="data-table mt-16">
                <thead>
                    <tr>
                        <th>Entry Trigger</th>
                        <th>Stop Loss</th>
                        <th>Target</th>
                        <th>Quantity</th>
                        <th>ML Edge (Kelly)</th>
                        <th>Option Protection</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="text-bold">${formatINR(idea.entry_trigger)}</td>
                        <td class="text-danger text-bold">${formatINR(idea.stop_loss)}</td>
                        <td class="text-success text-bold">${formatINR(idea.target_1)}</td>
                        <td class="text-bold">${idea.suggested_quantity || 0}</td>
                        <td class="text-accent text-bold">${((idea.ml_probability || 0) * 100).toFixed(1)}% (${((idea.kelly_pct || 0) * 100).toFixed(1)}%)</td>
                        <td class="text-warning text-bold">${idea.hedge_cost > 0 ? formatINR(idea.hedge_cost) + ' (Strike: ' + idea.hedge_strike + ')' : 'N/A'}</td>
                    </tr>
                </tbody>
            </table>
        </div>
    `;
    
    document.getElementById('bestOpportunityContainer').innerHTML = html;
}

function renderWatchlistList(ideas) {
    const container = document.getElementById('watchlistList');
    let html = '';

    ideas.forEach(idea => {
        const sym = cleanTicker(idea.ticker);
        const dec = idea.decision || 'WAIT';
        
        html += `
            <div class="metric-card flex justify-between items-center watchlist-card" data-ticker="${idea.ticker}" style="padding: 12px 16px; margin-bottom: 0;">
                <div>
                    <div class="text-bold" style="font-size: 1.1rem;">${escapeHtml(sym)}</div>
                    <div class="text-muted" style="font-size: 0.8rem;">
                        Live: <span class="live-price" data-trigger="${idea.entry_trigger}" style="font-weight: 700; color: var(--text-primary);">₹...</span> |
                        Buy: ${formatINR(idea.entry_trigger)}
                    </div>
                </div>
                <div>${decisionBadge(dec)}</div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function populateSelectors(watchlist) {
    const addSelect = document.getElementById('removeSymbolSelect');
    const chartSelect = document.getElementById('chartSymbolSelect');
    
    let options = '';
    watchlist.forEach(w => {
        if (!w.ticker.startsWith('^')) {
            options += `<option value="${w.ticker}">${cleanTicker(w.ticker)}</option>`;
        }
    });
    
    addSelect.innerHTML = options;
    chartSelect.innerHTML = options;
}

let currentChart = null;
let candlestickSeries = null;
let sma20Series = null;
let sma50Series = null;

async function loadAndRenderChart(ticker) {
    const container = document.getElementById('chartContainer');
    container.innerHTML = '<div style="padding:20px; color:var(--text-muted); text-align:center;">Loading chart data...</div>';

    try {
        const prices = await API.get(`/api/prices/${ticker}`);
        if (!prices || prices.length === 0) {
            container.innerHTML = '<div style="padding:20px; color:var(--text-muted); text-align:center;">No data available for chart.</div>';
            return;
        }

        container.innerHTML = ''; // clear loading text

        const chartOptions = {
            layout: {
                background: { type: 'solid', color: 'transparent' },
                textColor: '#94a3b8',
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: 'rgba(255, 255, 255, 0.1)',
            },
            timeScale: {
                borderColor: 'rgba(255, 255, 255, 0.1)',
                timeVisible: true,
            },
            height: 400
        };

        if (currentChart) {
            currentChart.remove();
        }

        currentChart = LightweightCharts.createChart(container, chartOptions);

        candlestickSeries = currentChart.addCandlestickSeries({
            upColor: '#10b981',
            downColor: '#f43f5e',
            borderVisible: false,
            wickUpColor: '#10b981',
            wickDownColor: '#f43f5e'
        });

        const candleData = prices.map(p => ({
            time: p.date.split('T')[0],
            open: p.open,
            high: p.high,
            low: p.low,
            close: p.close
        })).sort((a, b) => new Date(a.time) - new Date(b.time));
        
        // Take last 126 days (approx 6 months)
        const recentData = candleData.slice(-126);
        candlestickSeries.setData(recentData);

        // Simple SMA calculation for chart display
        sma20Series = currentChart.addLineSeries({ color: '#f59e0b', lineWidth: 1, title: 'SMA 20' });
        sma50Series = currentChart.addLineSeries({ color: '#38bdf8', lineWidth: 1, title: 'SMA 50' });
        
        function calculateSMA(data, period) {
            const sma = [];
            for (let i = period - 1; i < data.length; i++) {
                let sum = 0;
                for (let j = 0; j < period; j++) {
                    sum += data[i - j].close;
                }
                sma.push({ time: data[i].time, value: sum / period });
            }
            return sma;
        }

        sma20Series.setData(calculateSMA(recentData, 20));
        sma50Series.setData(calculateSMA(recentData, 50));

        currentChart.timeScale().fitContent();

        // Handle resize
        new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== container) { return; }
            const newRect = entries[0].contentRect;
            currentChart.applyOptions({ height: newRect.height, width: newRect.width });
        }).observe(container);

    } catch (err) {
        container.innerHTML = `<div style="padding:20px; color:var(--danger); text-align:center;">Error loading chart: ${escapeHtml(err.message)}</div>`;
    }
}

async function addWatchlistSymbol() {
    const input = document.getElementById('addSymbolInput');
    const ticker = input.value.trim().toUpperCase();
    if (!ticker) return;
    
    let fullTicker = ticker;
    if (!fullTicker.endsWith('.NS') && !fullTicker.startsWith('^')) {
        fullTicker += '.NS';
    }

    try {
        const btn = input.nextElementSibling;
        const originalText = btn.innerText;
        btn.innerText = 'Syncing...';
        btn.disabled = true;

        const res = await API.post('/api/watchlist', { ticker: fullTicker });
        
        if (res.success) {
            showToast(`Added and synced ${fullTicker}. Loaded ${res.rows_synced} rows.`, 'success');
            input.value = '';
            await loadResearchData(); // Reload page data
        } else {
            showToast(res.error || 'Failed to sync ticker', 'error');
        }
        
        btn.innerText = originalText;
        btn.disabled = false;
    } catch (err) {
        showToast(err.message, 'error');
        const btn = input.nextElementSibling;
        btn.innerText = 'Add & Sync';
        btn.disabled = false;
    }
}

async function removeWatchlistSymbol() {
    const select = document.getElementById('removeSymbolSelect');
    const ticker = select.value;
    if (!ticker) return;

    if (!confirm(`Are you sure you want to remove ${cleanTicker(ticker)} and all its historical data?`)) return;

    try {
        const res = await API.del(`/api/watchlist/${ticker}`);
        if (res.success) {
            showToast(`Removed ${cleanTicker(ticker)} from watchlist.`, 'success');
            await loadResearchData(); // Reload page data
        } else {
            showToast(res.error || 'Failed to remove ticker', 'error');
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}
