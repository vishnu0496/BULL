/* ============================================================
   Daily Stock Mentor — Page Module
   ============================================================ */

// Helper to get IST date string
function getISTDateString() {
    const now = new Date();
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const ist = new Date(utc + (3600000 * 5.5));
    return ist.toISOString().split('T')[0];
}

// Global functions for event handling
window.toggleChecklistItem = function(status, date, index) {
    const key = `morning_checklist_${status}_${date}`;
    let checkedStates = JSON.parse(localStorage.getItem(key) || '{}');
    checkedStates[index] = !checkedStates[index];
    localStorage.setItem(key, JSON.stringify(checkedStates));
    
    // Update UI
    const item = document.querySelector(`.checklist-item[data-status="${status}"][data-index="${index}"]`);
    if (item) {
        const checkbox = item.querySelector('.checklist-checkbox');
        const text = item.querySelector('.checklist-text');
        if (checkedStates[index]) {
            checkbox.classList.add('checked');
            checkbox.textContent = '✓';
            text.classList.add('checked');
        } else {
            checkbox.classList.remove('checked');
            checkbox.textContent = '';
            text.classList.remove('checked');
        }
    }
};

window.logMentorTrade = async function(ticker, price, qty, target, stop) {
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
        
        // Refresh the checklist page to show updated trade stats
        const main = document.getElementById('mainContent');
        if (main && typeof PAGES['mentor'] === 'function') {
            PAGES['mentor'](main);
        }
    } catch (err) {
        showToast('Failed to log trade: ' + err.message, 'error');
    }
};

registerPage('mentor', async function(container) {
    // Render loading skeletons
    container.innerHTML = `
        <h1 class="page-title">Daily Stock Mentor</h1>
        <p class="page-subtitle">Your trading teacher. Every morning, I scan India's top 20 sector leaders and suggest 2 or 3 high-probability swing trades.</p>

        <div id="morningChecklist">
            <div class="skeleton-line w-60"></div>
            <div class="skeleton-line w-80"></div>
            <div class="skeleton-card" style="height:180px; margin-top: 16px;"></div>
        </div>
        
        <div id="mentorPicks" class="mt-24">
            <div class="skeleton-line w-40"></div>
            <div class="bento-grid bento-3 mt-16">
                <div class="skeleton-card" style="height:420px"></div>
                <div class="skeleton-card" style="height:420px"></div>
                <div class="skeleton-card" style="height:420px"></div>
            </div>
        </div>
        
        <div id="mentorLessonContainer" class="mt-24"></div>
    `;

    try {
        // Fetch all required data in parallel
        const [picks, morningStatus, skillGateData, premarket, fii, indices, settings] = await Promise.all([
            API.get('/api/mentor/picks').catch(() => []),
            API.get('/api/morning-status').catch(() => ({ status: 'WEEKEND', open_trade_count: 0, streak_count: 0, hours_left: 0, mins_left: 0, last_trade_days_ago: -1, setup_ticker: null })),
            API.get('/api/universe/skill_gate').catch(() => ({ skill_gate: { level: 'Beginner', score: 0, next_unlock_requirement: '' } })),
            API.get('/api/premarket').catch(() => ({ data: { pre_market_score: 50, classification: 'NEUTRAL' } })),
            API.get('/api/fii/latest').catch(() => ({ data: { fii_net: 0, dii_net: 0 } })),
            API.get('/api/indices').catch(() => ({ items: [] })),
            API.get('/api/capital').catch(() => ({ total_capital: 5000, max_risk_per_trade: 100 }))
        ]);

        const capital = settings.total_capital || 5000;
        const maxRisk = settings.max_risk_per_trade || 100;
        const skillGate = skillGateData.skill_gate || { level: 'Beginner', score: 0, next_unlock_requirement: '' };

        // 1. Render Morning Routine Checklist Card
        renderMorningRoutine(morningStatus, skillGate);

        // 2. Render Main Content Area (Picks or Closed/Bearish States)
        await renderMainContent(picks, morningStatus, premarket, fii, indices, capital, maxRisk);

        // 3. Render Today's Lesson
        await renderLessonCard(capital, maxRisk);

    } catch (err) {
        console.error("Error loading Daily Mentor page:", err);
        showError(container, "Failed to load Daily Mentor: " + err.message);
    }
});

function renderMorningRoutine(morningStatus, skillGate) {
    const el = document.getElementById('morningChecklist');
    if (!el) return;

    const status = morningStatus.status || 'WEEKEND';
    const streak = morningStatus.streak_count || 0;
    const daysSinceLastTrade = morningStatus.last_trade_days_ago;
    const openTrades = morningStatus.open_trade_count || 0;

    let title = '';
    let emoji = '';
    let subtitle = '';
    let items = [];

    if (status === 'BEFORE_MARKET') {
        emoji = '🌅';
        title = 'Morning Routine: Get Ready for the Open';
        const hours = morningStatus.hours_left || 0;
        const mins = morningStatus.mins_left || 0;
        subtitle = `Next session starts in ${hours}h ${mins}m. Take 5 minutes to prepare.`;
        items = [
            'Check overnight global markets (Brent Crude, USD/INR)',
            'Read FII/DII flow sentiment',
            'Check today\'s scheduled earnings calendar',
            'Formulate a watch plan'
        ];
    } else if (status === 'OPEN') {
        emoji = '⚡';
        title = 'Live Session: Execution Mode';
        const hours = morningStatus.hours_left || 0;
        const mins = morningStatus.mins_left || 0;
        subtitle = `Session ends in ${hours}h ${mins}m. Watch triggers closely.`;
        items = [
            'Check live index trend (Nifty 50)',
            'Check if setups are in trigger zone',
            'Verify position sizing rules before buying',
            'Set stop-loss immediately after logging'
        ];
    } else if (status === 'AFTER_MARKET') {
        emoji = '🌇';
        title = 'Evening Review: Journal & Learn';
        subtitle = 'Market closed for the day. See you tomorrow!';
        items = [
            'Log any pending manual trades in journal',
            'Review performance metrics and equity curve',
            'Check next day\'s earnings announcements',
            'Read the educational lesson of the day'
        ];
    } else {
        // WEEKEND
        emoji = '☕';
        title = 'Weekend Warmup: Review & Study';
        subtitle = 'Enjoy the break! Markets reopen on Monday.';
        items = [
            'Review all closed trades from this week',
            'Study 2 lessons in Market School',
            'Check sector rotation trends',
            'Relax and recharge for the upcoming week'
        ];
    }

    const istDate = getISTDateString();
    const key = `morning_checklist_${status}_${istDate}`;
    const checkedStates = JSON.parse(localStorage.getItem(key) || '{}');

    const checklistHtml = items.map((item, idx) => {
        const isChecked = !!checkedStates[idx];
        return `
            <div class="checklist-item" data-status="${status}" data-index="${idx}" onclick="toggleChecklistItem('${status}', '${istDate}', ${idx})">
                <div class="checklist-checkbox ${isChecked ? 'checked' : ''}">${isChecked ? '✓' : ''}</div>
                <span class="checklist-text ${isChecked ? 'checked' : ''}">${escapeHtml(item)}</span>
            </div>
        `;
    }).join('');

    el.innerHTML = `
        <div class="beginner-card">
            <div class="beginner-card-header">
                <span style="font-size: 1.5rem; line-height: 1;">${emoji}</span>
                <div>
                    <div style="font-size: 1.1rem; font-weight: 800;">${title}</div>
                    <div style="font-size: 0.8rem; font-weight: normal; color: var(--text-muted); margin-top: 4px;">
                        ${subtitle}
                    </div>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr; gap: 20px; margin-top: 16px;">
                <!-- Column 1: Checklist -->
                <div>
                    <div style="font-size: 0.85rem; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Your Mentor Checklist</div>
                    <div>
                        ${checklistHtml}
                    </div>
                </div>
                
                <!-- Column 2: Stats & Skill Gate -->
                <div style="border-top: 1px solid var(--border-subtle); padding-top: 16px;">
                    <div style="display: flex; gap: 24px; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 12px; flex-wrap: wrap;">
                        <div>🔥 Streak: <strong>${streak > 0 ? streak + ' day' + (streak !== 1 ? 's' : '') : 'No active streak'}</strong></div>
                        <div>📅 Last Trade: <strong>${daysSinceLastTrade >= 0 ? (daysSinceLastTrade === 0 ? 'Today' : daysSinceLastTrade === 1 ? 'Yesterday' : `${daysSinceLastTrade} days ago`) : 'None yet'}</strong></div>
                        <div>💼 Active Trades: <strong>${openTrades}</strong></div>
                    </div>
                    
                    <div class="skill-gate-container" style="margin-top: 8px; padding: 12px;">
                        <div class="skill-gate-header">
                            <span>BULL Skill Gate: <strong>${skillGate.level}</strong></span>
                            <span>Score: <strong>${skillGate.score}/100</strong></span>
                        </div>
                        <div class="skill-gate-track">
                            <div class="skill-gate-fill" style="width: ${skillGate.score}%"></div>
                        </div>
                        <div class="skill-gate-hint">${skillGate.next_unlock_requirement}</div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

async function renderMainContent(picks, morningStatus, premarket, fii, indices, capital, maxRisk) {
    const el = document.getElementById('mentorPicks');
    if (!el) return;

    const status = morningStatus.status || 'WEEKEND';

    // 1. Weekend / Holiday Closed State
    if (status === 'WEEKEND') {
        const closedCardHtml = `
            <div class="beginner-card" style="border-left: 4px solid var(--warning); margin-bottom: 24px;">
                <div class="beginner-card-header" style="color: var(--warning); margin-bottom: 8px;">
                    <span>📅</span> MARKET IS CLOSED TODAY
                </div>
                <div class="beginner-card-body" style="font-size: 0.95rem; line-height: 1.5;">
                    The stock market is closed on weekends and national holidays. Markets will reopen on the next working day (Monday to Friday) at 9:15 AM.
                </div>
                <div class="beginner-card-footer" style="margin-top: 16px;">
                    <a href="#school" class="btn btn-primary" style="display: inline-flex; align-items: center; justify-content: center; text-decoration: none; min-height: 44px;">📚 Go to Market School</a>
                    <a href="#trades" class="btn" style="display: inline-flex; align-items: center; justify-content: center; text-decoration: none; border: 1px solid var(--border-default); min-height: 44px;">📝 Review My Practice Trades</a>
                </div>
            </div>
        `;
        const tradesHtml = await renderLast3Trades();
        el.innerHTML = closedCardHtml + tradesHtml;
        return;
    }

    // 2. Open but Bearish / Rangebound Stance (picks empty)
    if (!picks || picks.length === 0) {
        const bearishCardHtml = `
            <div class="beginner-card" style="border-left: 4px solid var(--danger); margin-bottom: 24px;">
                <div class="beginner-card-header" style="color: var(--danger); margin-bottom: 8px;">
                    <span>🛡️</span> DEFENSIVE MODE ACTIVE (BEARISH MARKET)
                </div>
                <div class="beginner-card-body" style="font-size: 0.95rem; line-height: 1.5;">
                    The market is currently showing bearish signals. It's safer to sit on cash and wait for better opportunities. Patience is a key trading skill.
                </div>
                <div class="beginner-card-footer" style="margin-top: 16px;">
                    <button class="btn btn-primary" style="min-height: 44px;" onclick="document.getElementById('mentorLessonCard').scrollIntoView({ behavior: 'smooth' })">📚 Read Today's Lesson</button>
                    <a href="#sectors" class="btn" style="display: inline-flex; align-items: center; justify-content: center; text-decoration: none; border: 1px solid var(--border-default); min-height: 44px;">📈 Check Sector Rankings</a>
                </div>
            </div>
        `;
        const tradesHtml = await renderLast3Trades();
        el.innerHTML = bearishCardHtml + tradesHtml;
        return;
    }

    // 3. Trade Recommendations Loaded (Bullish/Selective Session)
    const vixItem = indices.items ? indices.items.find(item => item.id === 'INDIA_VIX') : null;
    const vixValue = vixItem ? Number(vixItem.value) : 15.0;

    const overallVerdictHtml = `
        <div class="verdict-why-card" style="margin-bottom: 24px;">
            <div class="verdict-why-title" style="font-size: 0.95rem; font-weight: 800; color: var(--text-primary);">
                <span>🔍</span> Why is BULL recommending this market stance today?
            </div>
            <ul class="verdict-why-list" style="margin-top: 8px;">
                <li><strong>Pre-market Score:</strong> ${premarket.data?.pre_market_score || 50} (${premarket.data?.classification || 'NEUTRAL'}) — indicating ${ (premarket.data?.pre_market_score || 50) >= 60 ? 'strong overnight global markets and supportive pre-open flows' : (premarket.data?.pre_market_score || 50) <= 40 ? 'weakness in overnight global markets and global pressures' : 'flat global markets and mixed pre-open sentiment'}.</li>
                <li><strong>Foreign Investors (FII):</strong> FIIs were ${ (fii.data?.fii_net || 0) >= 0 ? 'net buyers' : 'net sellers' } yesterday with a net flow of ${ fii.data ? formatINR(Math.abs(fii.data.fii_net) * 10000000).replace('INR ', '') + ' Cr' : '0 Cr' }. ${(fii.data?.fii_net || 0) >= 0 ? 'This adds buying pressure to Indian markets.' : 'This puts downward pressure on Indian markets.'}</li>
                <li><strong>Market Fear (India VIX):</strong> India VIX is at ${vixValue.toFixed(2)} ${vixValue > 18 ? '(HIGH FEAR - expect wild price swings)' : vixValue > 14 ? '(MODERATE VOLATILITY)' : '(LOW FEAR - calm market conditions)'}.</li>
            </ul>
        </div>
    `;

    const sectionTitle = `<div class="section-title"><span class="icon">🎯</span> Teacher's Picks of the Day</div>`;

    const cards = picks.map((idea) => {
        const sym = cleanTicker(idea.ticker);
        const dec = idea.decision || 'WAIT';
        const decColor = dec === 'TRADE' ? 'var(--success)' : 'var(--warning)';
        const statusText = dec === 'TRADE' ? '🟢 Ready to Buy (Trigger Zone)' : '🟡 Watch Triggers';

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

                <!-- Why did BULL say this stock-specific reasoning -->
                <div class="verdict-why-card" style="margin-top: 16px; padding: 12px;">
                    <div class="verdict-why-title" style="font-size: 0.78rem; font-weight: 700; text-transform: uppercase; color: var(--text-primary);">
                        <span>🧠</span> Why did BULL select ${escapeHtml(sym)}?
                    </div>
                    <ul class="verdict-why-list" style="margin-top: 6px; font-size: 0.8rem;">
                        <li><strong>Breakout Setup:</strong> Triggers if price crosses above ₹${formatNum(idea.entry_trigger)} (previous day high / resistance level).</li>
                        <li><strong>Confidence:</strong> AI model predicts a ${((idea.ml_probability || 0) * 100).toFixed(1)}% chance of hitting the profit goal before hitting the stop loss.</li>
                        <li><strong>Kelly Edge:</strong> Math formula suggests risking ${((idea.kelly_pct || 0) * 100).toFixed(2)}% of capital for optimal growth.</li>
                    </ul>
                    <div class="verdict-why-action" style="font-size: 0.78rem; padding-top: 8px; margin-top: 6px;">
                        🛡️ <strong>Plan:</strong> Buy ${idea.suggested_quantity} shares if price crosses ₹${formatNum(idea.entry_trigger)}. Maximum possible loss is capped at <strong>${formatINR(idea.max_loss)}</strong>.
                    </div>
                </div>

                ${idea.suggested_quantity > 0 ? `
                <button class="btn btn-primary btn-full mt-16" style="min-height: 44px;" onclick="logMentorTrade('${escapeHtml(idea.ticker)}', ${idea.entry_trigger}, ${idea.suggested_quantity}, '${escapeHtml(idea.target_1)}', '${escapeHtml(idea.stop_loss)}')">
                    📥 Log Practice Trade: ${escapeHtml(sym)}
                </button>
                ` : `
                <button class="btn btn-full mt-16" style="background: rgba(220, 38, 38, 0.1); color: var(--danger); border: 1px solid var(--danger); cursor: not-allowed; min-height: 44px;" disabled>
                    🛑 Trade Rejected by AI (Zero Edge)
                </button>
                `}
            </div>
        `;
    }).join('');

    el.innerHTML = overallVerdictHtml + sectionTitle + `<div class="bento-grid bento-3 mt-16">${cards}</div>`;

    // Animate confidence bars
    setTimeout(() => {
        el.querySelectorAll('.confidence-fill').forEach(bar => {
            bar.style.width = bar.style.width; // trigger reflow
        });
    }, 100);
}

async function renderLast3Trades() {
    let trades = [];
    let winRate = 0.0;
    let netPnL = 0.0;

    try {
        const res = await API.get('/api/journal');
        trades = Array.isArray(res) ? res : (res.trades || []);
    } catch (e) {
        console.warn("Failed to fetch trades for sub-panel", e);
    }

    const closedTrades = trades.filter(t => t.status === 'CLOSED');
    if (closedTrades.length > 0) {
        const wins = closedTrades.filter(t => (t.pnl || 0) > 0);
        winRate = (wins.length / closedTrades.length) * 100;
        netPnL = closedTrades.reduce((acc, t) => acc + (t.pnl || 0), 0);
    }

    const last3 = trades.slice(-3).reverse();

    const tableRows = last3.map(t => {
        const ticker = cleanTicker(t.ticker);
        const isClosed = t.status === 'CLOSED';
        const pnlColor = t.pnl > 0 ? 'var(--success)' : t.pnl < 0 ? 'var(--danger)' : 'var(--text-secondary)';
        const dateStr = (t.trade_date || t.entry_time || '').split('T')[0];
        const price = t.price || t.entry_price || 0;
        return `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03); font-size: 0.85rem;">
                <td style="padding: 10px 0; font-weight: 700; color: var(--text-primary);">${escapeHtml(ticker)}</td>
                <td style="padding: 10px 0; color: var(--text-secondary);">${escapeHtml(dateStr)}</td>
                <td style="padding: 10px 0; color: var(--text-secondary);">${formatINR(price)}</td>
                <td style="padding: 10px 0; color: var(--text-secondary);">${t.quantity}</td>
                <td style="padding: 10px 0;">
                    <span class="badge badge-${isClosed ? 'neutral' : 'trade'}" style="padding: 2px 6px; font-size: 0.65rem;">${isClosed ? 'CLOSED' : 'OPEN'}</span>
                </td>
                <td style="padding: 10px 0; text-align: right; font-weight: 700; color: ${pnlColor};">${isClosed ? formatINR(t.pnl) : '—'}</td>
            </tr>
        `;
    }).join('');

    return `
        <div class="beginner-card" style="margin-top: 24px;">
            <div class="beginner-card-header" style="margin-bottom: 12px;">
                <span>📝</span> Last 3 Practice Trades Logged
            </div>
            <div class="beginner-card-body">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 20px;">
                    <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: 8px; border: 1px solid var(--border-subtle)">
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">Win Rate (90d)</div>
                        <div style="font-size: 1.25rem; font-weight: 800; color: var(--text-primary); margin-top: 4px;">${winRate.toFixed(1)}%</div>
                    </div>
                    <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: 8px; border: 1px solid var(--border-subtle)">
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">Net PnL</div>
                        <div style="font-size: 1.25rem; font-weight: 800; color: ${netPnL >= 0 ? 'var(--success)' : 'var(--danger)'}; margin-top: 4px;">${formatINR(netPnL)}</div>
                    </div>
                    <div style="background: rgba(255,255,255,0.02); padding: 12px; border-radius: 8px; border: 1px solid var(--border-subtle)">
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">Total Trades</div>
                        <div style="font-size: 1.25rem; font-weight: 800; color: var(--text-primary); margin-top: 4px;">${trades.length}</div>
                    </div>
                </div>
                
                ${last3.length === 0 ? `
                    <div style="text-align: center; color: var(--text-muted); padding: 16px; font-style: italic;">
                        No practice trades logged yet. Use the daily picks during market hours to make your first trade!
                    </div>
                ` : `
                    <div style="overflow-x: auto;">
                        <table class="pick-table" style="width: 100%; border-collapse: collapse; min-width: 500px;">
                            <thead>
                                <tr style="border-bottom: 1px solid var(--border-subtle); text-align: left; font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em;">
                                    <th style="padding: 8px 0;">Ticker</th>
                                    <th style="padding: 8px 0;">Date</th>
                                    <th style="padding: 8px 0;">Price</th>
                                    <th style="padding: 8px 0;">Qty</th>
                                    <th style="padding: 8px 0;">Status</th>
                                    <th style="padding: 8px 0; text-align: right;">PnL</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${tableRows}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        </div>
    `;
}

async function renderLessonCard(capital, maxRisk) {
    const el = document.getElementById('mentorLessonContainer');
    if (!el) return;

    try {
        const lesson = await API.get('/api/daily-lesson');

        el.innerHTML = `
            <div id="mentorLessonCard" class="beginner-card" style="margin-top: 24px; border-left: 4px solid var(--accent);">
                <div class="beginner-card-header" style="color: var(--accent); margin-bottom: 8px;">
                    <span style="font-size: 1.3rem;">${escapeHtml(lesson.emoji || '📚')}</span> Today's Lesson: ${escapeHtml(lesson.title)}
                </div>
                <div class="beginner-card-body" style="font-size: 0.92rem; line-height: 1.6; color: var(--text-secondary);">
                    ${escapeHtml(lesson.body)}
                </div>
            </div>

            <div class="command-panel wait" style="animation: breathe-amber 4s ease-in-out infinite; margin-top: 16px;">
                <div class="command-title" style="color: var(--accent); font-size: 1.05rem;">🛡️ Your Personal Risk Rules</div>
                <div class="command-subtitle" style="margin-top: 6px; font-size: 0.82rem; line-height: 1.5; color: var(--text-secondary);">
                    With your current capital of <strong style="color: var(--text-primary)">${formatINR(capital)}</strong> and risk budget of 
                    <strong style="color: var(--text-primary)">${formatINR(maxRisk)} per trade</strong>, we strictly buy <em>Equity shares</em> (normal stocks). 
                    We do not touch high-leverage F&O because it is too risky for a learning account. 
                    If a suggested trade hits the safety stop-loss, you will lose a maximum of <strong style="color: var(--text-primary)">${formatINR(maxRisk)}</strong>.
                </div>
            </div>
        `;
    } catch (err) {
        console.warn("Failed to load daily lesson", err);
        el.innerHTML = '';
    }
}
