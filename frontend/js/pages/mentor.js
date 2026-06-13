/* ============================================================
   Today's Picks (Daily Stock Mentor) — Page Module
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

// Global function to allow other parts of the app (like app.js or index.html) to request page refresh
window.renderMentorPicks = function() {
    const main = document.getElementById('mainContent');
    if (main && currentPage === 'mentor') {
        PAGES['mentor'](main);
    }
};

registerPage('mentor', async function(container) {
    // Render loading skeletons
    container.innerHTML = `
        <h1 class="page-title">Today's Picks</h1>
        <p class="page-subtitle">BULL scans the market and delivers high-probability trade setups in plain English.</p>

        <div id="morningChecklist">
            <div class="skeleton-line w-60"></div>
            <div class="skeleton-line w-80"></div>
            <div class="skeleton-card" style="height:180px; margin-top: 16px;"></div>
        </div>
        
        <div id="mentorPicks" class="mt-24">
            <div class="skeleton-line w-40"></div>
            <div class="bento-grid bento-3 mt-16">
                <div class="skeleton-card" style="height:320px"></div>
                <div class="skeleton-card" style="height:320px"></div>
                <div class="skeleton-card" style="height:320px"></div>
            </div>
        </div>
        
        <div id="mentorLessonContainer" class="mt-24"></div>
    `;

    try {
        // Fetch all required data in parallel
        const [picks, morningStatus, skillGateData, premarket, fii, indices, settings, regime] = await Promise.all([
            API.get('/api/mentor/picks').catch(() => []),
            API.get('/api/morning-status').catch(() => ({ status: 'WEEKEND', open_trade_count: 0, streak_count: 0, hours_left: 0, mins_left: 0, last_trade_days_ago: -1, setup_ticker: null })),
            API.get('/api/universe/skill_gate').catch(() => ({ skill_gate: { level: 'Beginner', score: 0, next_unlock_requirement: '' } })),
            API.get('/api/premarket').catch(() => ({ data: { pre_market_score: 50, classification: 'NEUTRAL' } })),
            API.get('/api/fii/latest').catch(() => ({ data: { fii_net: 0, dii_net: 0 } })),
            API.get('/api/indices').catch(() => ({ items: [] })),
            API.get('/api/capital').catch(() => ({ total_capital: 5000, max_risk_per_trade: 100 })),
            API.get('/api/market/regime').catch(() => ({ market_bias: 'NEUTRAL', trend_score: 50, reasons: [] }))
        ]);

        const capital = settings.total_capital || 5000;
        const maxRisk = settings.max_risk_per_trade || 100;
        const skillGate = skillGateData.skill_gate || { level: 'Beginner', score: 0, next_unlock_requirement: '' };

        // 1. Render Morning Routine Checklist Card
        renderMorningRoutine(morningStatus, skillGate);

        // 2. Render Main Content Area (3 states)
        await renderMainContent(picks, morningStatus, premarket, fii, indices, capital, maxRisk, regime);

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
            'Check Nifty 50 market trend',
            'Look for global market news',
            'Prepare your maximum risk per trade budget'
        ];
    } else if (status === 'OPEN') {
        emoji = '⚡';
        title = 'Live Session: Active Trading';
        const hours = morningStatus.hours_left || 0;
        const mins = morningStatus.mins_left || 0;
        subtitle = `Session ends in ${hours}h ${mins}m. Watch triggers closely.`;
        items = [
            'Check if Nifty 50 is rising or falling',
            'See if today\'s picks cross their Buy Trigger',
            'Log trades directly into your practice journal'
        ];
    } else if (status === 'AFTER_MARKET') {
        emoji = '🌇';
        title = 'Evening Review: Check Results & Learn';
        subtitle = 'Market closed for the day. See you tomorrow!';
        items = [
            'Verify all your simulated trades are logged correctly',
            'Check your net results in My Results tab',
            'Read the educational lesson of the day below'
        ];
    } else {
        // WEEKEND
        emoji = '☕';
        title = 'Weekend Review: Rest & Study';
        subtitle = 'Enjoy the weekend! Markets reopen on Monday.';
        items = [
            'Review your closed trades from this week',
            'Check your long-term success metrics',
            'Relax and prepare for next week\'s opportunities'
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
                    <div style="font-size: 0.85rem; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Your Trading Routine</div>
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
                            <span>BULL Level: <strong>${skillGate.level}</strong></span>
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

async function renderMainContent(picks, morningStatus, premarket, fii, indices, capital, maxRisk, regime) {
    const el = document.getElementById('mentorPicks');
    if (!el) return;

    const status = morningStatus.status || 'WEEKEND';
    const isMarketClosed = status === 'WEEKEND' || status === 'AFTER_MARKET';
    
    // Filter picks where decision is TRADE
    const tradePicks = (picks || []).filter(p => p.decision === 'TRADE');
    const rankedCandidates = (picks || []).filter(p => p.decision !== 'REJECT').slice(0, 3);

    // State 3 — Market closed
    if (isMarketClosed) {
        const nextInfo = status === 'BEFORE_MARKET' 
            ? `Market opens in <strong>${morningStatus.hours_left || 0}h ${morningStatus.mins_left || 0}m</strong>.` 
            : `Market is closed. We will scan and post new picks on the next trading day at 9:15 AM IST.`;
        const shortlistHtml = renderOpportunityShortlist(
            rankedCandidates,
            'Next Session Watchlist',
            'These are the best current candidates from BULL. Do not buy them automatically; wait for the trigger and fresh market data.',
            maxRisk,
            false
        );

        el.innerHTML = `
            <div class="bull-state-card">
                <span class="state-emoji">☕</span>
                <h2 class="state-title">Market is Closed</h2>
                <div class="state-body">
                    <p>BULL builds a fresh conditional trade plan before the next session and tracks triggers during market hours.</p>
                    <p><strong>Next Session:</strong> ${nextInfo}</p>
                    <p style="margin-top: 12px;">Use this time to review your open positions, analyze your results, or learn new concepts in Market School.</p>
                </div>
                <div class="state-footer">
                    Fresh conditional scans resume before the next trading session.
                </div>
            </div>
            ${shortlistHtml}
        `;
        return;
    }

    // State 2 — Bearish / no trades found
    if (tradePicks.length === 0) {
        const regimeReasons = (regime.reasons || ["Market trend is currently weak.", "Volatility is high."])
            .map(r => `<li>${escapeHtml(r)}</li>`).join('');
        const shortlistHtml = renderOpportunityShortlist(
            rankedCandidates,
            'Best Stocks To Watch',
            'No active buy signal passed the full checklist, but these are the top ranked candidates to track for a trigger.',
            maxRisk,
            false
        );

        el.innerHTML = `
            <div class="bull-state-card">
                <span class="state-emoji">😴</span>
                <h2 class="state-title">No Active Trades Yet</h2>
                <div class="state-body">
                    <p>BULL has scanned the market and decided it is safer to sit in cash for now. Here is why:</p>
                    <ul>
                        ${regimeReasons}
                    </ul>
                    <p style="margin-top: 12px;">Use the shortlist below for paper-trading observation only. A stock becomes actionable only after it crosses the buy trigger with fresh data.</p>
                </div>
                <div class="state-footer">
                    No trigger means no trade.
                </div>
            </div>
            ${shortlistHtml}
        `;
        return;
    }

    // State 1 — TRADE picks found
    const sectionLabel = status === 'BEFORE_MARKET' ? 'Pre-Market Conditional Setups' : "Today's Conditional Setups";
    const sectionTitle = `<h3 class="section-title" style="margin-top:24px;"><span class="icon">*</span> ${sectionLabel}</h3>`;
    const cards = tradePicks.map((idea) => {
        const sym = cleanTicker(idea.ticker);
        const stopLoss = idea.stop_loss || 0;
        const entryTrigger = idea.entry_trigger || 0;
        
        const riskPerShare = Math.abs(entryTrigger - stopLoss);
        let qty = idea.suggested_quantity || 1;
        if (riskPerShare > 0) {
            qty = Math.max(1, Math.floor(maxRisk / riskPerShare));
        }
        
        const actualMaxLoss = riskPerShare * qty;

        // Clean plain English reasons
        const cleanReasons = (idea.reasons || []).filter(r => !r.includes("AI Sentiment Override"));
        if (cleanReasons.length === 0) {
            cleanReasons.push(`${sym} is in a strong sector and showing good buying volume.`);
            cleanReasons.push(`AI model estimates a high probability of hitting the profit target.`);
        }
        const reasonsHtml = cleanReasons.map(r => `<div class="pick-reason-item">${escapeHtml(r)}</div>`).join('');

        return `
            <div class="bull-pick-card" data-ticker="${idea.ticker}">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
                    <div>
                        <div class="pick-ticker-name">${escapeHtml(sym)}</div>
                        <div class="pick-sector">${escapeHtml(idea.sector || 'Nifty Leader')}</div>
                    </div>
                    <div style="font-size: 0.82rem; color: var(--text-muted); text-align: right;">
                        Live: <span class="live-price" data-trigger="${entryTrigger}" style="font-weight: 700; color: var(--text-primary)">INR ...</span>
                    </div>
                </div>

                <div class="pick-levels">
                    <div class="pick-level-item">
                        <div class="pick-level-label">Buy Trigger</div>
                        <div class="pick-level-value" style="color: var(--accent);">INR ${formatNum(entryTrigger)}</div>
                    </div>
                    <div class="pick-level-item">
                        <div class="pick-level-label">Safety Stop Loss</div>
                        <div class="pick-level-value" style="color: var(--danger);">INR ${formatNum(stopLoss)}</div>
                    </div>
                    <div class="pick-level-item">
                        <div class="pick-level-label">Profit Target</div>
                        <div class="pick-level-value" style="color: var(--success);">INR ${formatNum(idea.target_1 || idea.target)}</div>
                    </div>
                    <div class="pick-level-item">
                        <div class="pick-level-label">Maximum Loss</div>
                        <div class="pick-level-value" style="color: var(--danger);">INR ${formatNum(actualMaxLoss)}</div>
                    </div>
                </div>

                <div class="pick-reasons">
                    <div class="pick-reasons-title">Why BULL recommends this stock:</div>
                    ${reasonsHtml}
                </div>

                <button class="pick-log-btn" onclick="logTradeFromPick('${escapeHtml(idea.ticker)}', ${entryTrigger}, ${idea.target_1 || idea.target}, ${stopLoss}, ${qty})">
                    Log This Trade
                </button>
            </div>
        `;
    }).join('');

    el.innerHTML = sectionTitle + `<div class="bento-grid bento-3 mt-16">${cards}</div>`;
}

function renderOpportunityShortlist(picks, title, note, maxRisk, allowLog) {
    if (!Array.isArray(picks) || picks.length === 0) {
        return '';
    }

    const cards = picks.map((idea, index) => {
        const sym = cleanTicker(idea.ticker);
        const entryTrigger = Number(idea.entry_trigger || 0);
        const stopLoss = Number(idea.stop_loss || 0);
        const target = Number(idea.target_1 || idea.target || 0);
        const riskPerShare = Math.abs(entryTrigger - stopLoss);
        let qty = Number(idea.suggested_quantity || 0);
        if (riskPerShare > 0 && maxRisk > 0) {
            qty = Math.floor(maxRisk / riskPerShare);
        }
        const actualMaxLoss = riskPerShare * Math.max(qty, 0);
        const reasonItems = (idea.reasons || ['Ranked by BULL technical scanner.'])
            .filter(reason => /Historical edge|Sector overlay|News filter|Conditional long|Blocked/i.test(reason))
            .slice(-4);
        const reasonsHtml = (reasonItems.length ? reasonItems : ['Ranked by BULL technical scanner.'])
            .map(reason => `<div class="pick-reason-item">${escapeHtml(reason)}</div>`)
            .join('');
        const decision = idea.decision || 'WAIT';
        const canLog = allowLog && decision === 'TRADE' && qty > 0;
        const buttonHtml = canLog
            ? `<button class="pick-log-btn" onclick="logTradeFromPick('${escapeHtml(idea.ticker)}', ${entryTrigger}, ${target}, ${stopLoss}, ${qty})">Log This Trade</button>`
            : `<button class="pick-log-btn" disabled style="opacity:0.55; cursor:not-allowed;">Watch Only</button>`;

        return `
            <div class="bull-pick-card" data-ticker="${escapeHtml(idea.ticker)}">
                <div style="display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:18px;">
                    <div>
                        <div class="pick-sector">Rank #${index + 1} / ${escapeHtml(idea.sector || 'Unknown sector')}</div>
                        <div class="pick-ticker-name">${escapeHtml(sym)}</div>
                    </div>
                    ${decisionBadge(decision)}
                </div>
                <div class="pick-levels">
                    <div class="pick-level-item">
                        <div class="pick-level-label">Buy Trigger</div>
                        <div class="pick-level-value" style="color: var(--accent);">INR ${formatNum(entryTrigger)}</div>
                    </div>
                    <div class="pick-level-item">
                        <div class="pick-level-label">Stop Loss</div>
                        <div class="pick-level-value" style="color: var(--danger);">INR ${formatNum(stopLoss)}</div>
                    </div>
                    <div class="pick-level-item">
                        <div class="pick-level-label">Target</div>
                        <div class="pick-level-value" style="color: var(--success);">INR ${formatNum(target)}</div>
                    </div>
                    <div class="pick-level-item">
                        <div class="pick-level-label">Max Loss</div>
                        <div class="pick-level-value" style="color: var(--danger);">INR ${formatNum(actualMaxLoss)}</div>
                    </div>
                </div>
                <div class="pick-reasons">
                    <div class="pick-reasons-title">Why this made the shortlist:</div>
                    ${reasonsHtml}
                </div>
                ${buttonHtml}
            </div>
        `;
    }).join('');

    return `
        <h3 class="section-title" style="margin-top:24px;"><span class="icon">*</span> ${escapeHtml(title)}</h3>
        <p class="page-subtitle" style="margin-bottom: 12px;">${escapeHtml(note)}</p>
        <div class="bento-grid bento-3 mt-16">${cards}</div>
    `;
}

async function renderLessonCard(capital, maxRisk) {
    const el = document.getElementById('mentorLessonContainer');
    if (!el) return;

    try {
        const lesson = await API.get('/api/daily-lesson');

        el.innerHTML = `
            <div id="mentorLessonCard" class="bull-lesson-card">
                <span class="lesson-emoji">${escapeHtml(lesson.emoji || '📚')}</span>
                <div class="lesson-title">Today's Lesson: ${escapeHtml(lesson.title)}</div>
                <div class="lesson-body">
                    ${escapeHtml(lesson.body)}
                </div>
            </div>
        `;
    } catch (err) {
        console.warn("Failed to load daily lesson", err);
        el.innerHTML = '';
    }
}
