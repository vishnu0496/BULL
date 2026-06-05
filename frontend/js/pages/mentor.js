/* ============================================================
   Daily Stock Mentor — Page Module
   ============================================================ */

registerPage('mentor', async function(container) {
    container.innerHTML = `
        <h1 class="page-title">Daily Stock Mentor</h1>
        <p class="page-subtitle">Your trading teacher. Every morning, I scan India's top 20 sector leaders and suggest 2 or 3 high-probability swing trades.</p>

        <div id="mentorLesson"></div>
        <div id="mentorPicks" class="mt-24">
            <div class="skeleton-line w-60"></div>
            <div class="skeleton-line w-80"></div>
            <div class="bento-grid bento-3 mt-16">
                <div class="skeleton-card" style="height:420px"></div>
                <div class="skeleton-card" style="height:420px"></div>
                <div class="skeleton-card" style="height:420px"></div>
            </div>
        </div>
    `;

    // Load capital settings for lesson card
    try {
        const settings = await API.get('/api/capital');
        const capital = settings.total_capital || 5000;
        const maxRisk = settings.max_risk_per_trade || 100;

        document.getElementById('mentorLesson').innerHTML = `
            <div class="command-panel wait" style="animation: breathe-amber 4s ease-in-out infinite;">
                <div class="command-title" style="color: var(--accent); font-size: 1.2rem;">📚 Today's Teacher Lesson: The Risk Rule</div>
                <div class="command-subtitle" style="margin-top: 8px;">
                    With your current capital of <strong style="color: var(--text-primary)">${formatINR(capital)}</strong> and risk budget of 
                    <strong style="color: var(--text-primary)">${formatINR(maxRisk)} per trade</strong>, we strictly buy <em>Equity shares</em> (normal stocks). 
                    We do not touch high-leverage F&O because it is too risky for a learning account. 
                    If a suggested trade hits the safety stop-loss, you will lose a maximum of <strong style="color: var(--text-primary)">${formatINR(maxRisk)}</strong>. 
                    This is how we play safe!
                </div>
            </div>
        `;
    } catch (err) {
        document.getElementById('mentorLesson').innerHTML = '';
    }

    // Load mentor picks
    try {
        const picks = await API.get('/api/mentor/picks');
        renderMentorPicks(picks);
    } catch (err) {
        document.getElementById('mentorPicks').innerHTML = `
            <div class="alert alert-danger">
                <span>⚠️</span>
                <div><strong>Failed to load mentor picks</strong><br>${escapeHtml(err.message)}</div>
            </div>
        `;
    }
});

function renderMentorPicks(picks) {
    const el = document.getElementById('mentorPicks');

    if (!picks || picks.length === 0) {
        el.innerHTML = `
            <div class="alert alert-info">
                <span>📊</span>
                <div>The broader market is currently rangebound or bearish. For safety, I suggest waiting today. Patience is a trader's best friend!</div>
            </div>
        `;
        return;
    }

    const sectionTitle = `<div class="section-title"><span class="icon">🎯</span> Teacher's Picks of the Day</div>`;

    const cards = picks.map((idea, idx) => {
        const sym = cleanTicker(idea.ticker);
        const dec = idea.decision || 'WAIT';
        const conf = idea.confidence_score || 0;
        const winRate = idea.backtest_win_rate || 0;
        const sentLabel = idea.sentiment_label || 'NEUTRAL';
        const sentColor = sentLabel === 'BULLISH' ? 'var(--success)' : sentLabel === 'BEARISH' ? 'var(--danger)' : 'var(--text-secondary)';
        const decColor = dec === 'TRADE' ? 'var(--success)' : 'var(--warning)';
        const statusText = dec === 'TRADE' ? '🟢 Ready to Buy (Trigger Zone)' : '🟡 Watch Triggers';
        const reason = idea.reasons && idea.reasons.length > 0 ? idea.reasons[idea.reasons.length - 1] : 'Setup is technically solid.';

        return `
            <div class="pick-card" data-ticker="${idea.ticker}">
                <div class="pick-header">
                    <div>
                        <span class="pick-ticker">${escapeHtml(sym)}</span>
                        <div class="text-muted" style="font-size:0.75rem; margin-top:2px;">Live: <span class="live-price" data-trigger="${idea.entry_trigger}" style="font-weight:700; color:var(--text-primary)">₹...</span></div>
                    </div>
                    ${decisionBadge(dec)}
                </div>
                <div class="pick-status" style="color: ${decColor}">
                    ${statusText}
                </div>

                <div class="pick-justification">
                    <div class="pick-justification-label">Mentor's Justification</div>
                    <div class="pick-justification-text">${escapeHtml(reason)}</div>
                </div>

                <table class="pick-table">
                    <tr>
                        <td>Buy Trigger</td>
                        <td style="color: var(--text-primary)">${formatINR(idea.entry_trigger)}</td>
                    </tr>
                    <tr>
                        <td>Safety Exit</td>
                        <td style="color: var(--danger)">${formatINR(idea.stop_loss)}</td>
                    </tr>
                    <tr>
                        <td>Profit Goal</td>
                        <td style="color: var(--success)">${formatINR(idea.target_1)}</td>
                    </tr>
                    <tr>
                        <td>Shares to Buy</td>
                        <td>${idea.suggested_quantity || 0}</td>
                    </tr>
                </table>

                <div class="confidence-bar mt-8">
                    <div class="flex justify-between items-center mb-8">
                        <div class="confidence-label tooltip-container" style="margin:0; font-family: monospace; cursor: help;">
                            XGBoost Predictor: Probability of Target
                            <span class="tooltip-indicator">?</span>
                            <span class="tooltip-text">XGBoost is a machine learning ensemble that processes 26 technical indicators (RSI, ATR, RVOL, etc.) to estimate the probability of hitting target before stop-loss.</span>
                        </div>
                        <div style="font-size:1.2rem; font-weight:800; color:${decColor}">${((idea.ml_probability || 0) * 100).toFixed(1)}%</div>
                    </div>
                    
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:12px; background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px;">
                        <div>
                            <div class="tooltip-container" style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase; cursor: help; display: inline-flex; align-items: center; gap: 4px;">
                                Kelly Criterion (Optimal Risk)
                                <span class="tooltip-indicator">?</span>
                                <span class="tooltip-text">Kelly Criterion calculates the optimal fraction of capital to risk per trade to maximize long-term compound growth based on win-rate and risk-reward ratio.</span>
                            </div>
                            <div style="font-size:0.85rem; font-weight:700; color:var(--text-primary);">${((idea.kelly_pct || 0) * 100).toFixed(2)}% of Capital</div>
                        </div>
                        <div>
                            <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase;">ATM Put Hedge Cost</div>
                            <div style="font-size:0.85rem; font-weight:700; color:var(--warning);">${idea.hedge_cost > 0 ? formatINR(idea.hedge_cost) + '/share' : 'None'}</div>
                        </div>
                        <div style="grid-column: span 2;">
                            <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase;">Slippage Adjusted PnL</div>
                            <div style="font-size:0.85rem; font-weight:700; color:${idea.backtest_net_profit > 0 ? 'var(--success)' : 'var(--danger)'};">${formatINR(idea.backtest_net_profit || 0)}</div>
                        </div>
                    </div>

                    <div class="confidence-track">
                        <div class="confidence-fill" style="width: ${Math.min((idea.ml_probability || 0) * 100, 100)}%; background: linear-gradient(90deg, ${decColor} 0%, var(--accent) 100%)"></div>
                    </div>
                </div>

                ${idea.suggested_quantity > 0 ? `
                <button class="btn btn-primary btn-full mt-16" onclick="logMentorTrade('${escapeHtml(idea.ticker)}', ${idea.entry_trigger}, ${idea.suggested_quantity}, '${escapeHtml(idea.target_1)}', '${escapeHtml(idea.stop_loss)}')">
                    📥 Log Practice Trade: ${escapeHtml(sym)}
                </button>
                ` : `
                <button class="btn btn-full mt-16" style="background: rgba(220, 38, 38, 0.1); color: var(--danger); border: 1px solid var(--danger); cursor: not-allowed;" disabled>
                    🛑 Trade Rejected by AI (Zero Edge)
                </button>
                `}
            </div>
        `;
    }).join('');

    el.innerHTML = sectionTitle + `<div class="bento-grid bento-3 mt-16">${cards}</div>`;

    // Animate confidence bars
    setTimeout(() => {
        el.querySelectorAll('.confidence-fill').forEach(bar => {
            bar.style.width = bar.style.width; // trigger reflow
        });
    }, 100);
}

async function logMentorTrade(ticker, price, qty, target, stop) {
    if (qty <= 0) {
        showToast('Cannot log trade. Position size is 0 shares. Check capital settings.', 'error');
        return;
    }

    try {
        const today = new Date().toISOString().split('T')[0];
        await API.post('/api/journal', {
            ticker: ticker,
            trade_date: today,
            action: 'BUY',
            quantity: qty,
            price: price,
            notes: `Logged from Daily Mentor Pick. Target: ${target}, Stop: ${stop}.`
        });
        showToast(`Added ${qty} shares of ${cleanTicker(ticker)} to your practice journal!`, 'success');
    } catch (err) {
        showToast('Failed to log trade: ' + err.message, 'error');
    }
}
