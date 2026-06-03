/* ============================================================
   F&O Desk — Page Module
   ============================================================ */

registerPage('fno', async function(container) {
    container.innerHTML = `
        <div class="flex justify-between items-center mb-16">
            <div>
                <h1 class="page-title">F&O Desk: Statistical Arbitrage</h1>
                <p class="page-subtitle">Market-Neutral Pairs Trading using Z-Score mean reversion.</p>
            </div>
            <span class="badge" style="background: rgba(168, 85, 247, 0.1); color: #a855f7; border: 1px solid #a855f7;">QUANTITATIVE DESK</span>
        </div>

        <div class="command-panel wait mb-24" style="animation: breathe-amber 4s ease-in-out infinite; border-left: 4px solid #a855f7;">
            <div class="command-title" style="color: #a855f7; font-size: 1.2rem;">🧠 Strategy: Pairs Trading (Stat Arb)</div>
            <div class="command-subtitle" style="margin-top: 8px;">
                We track highly correlated stocks. When the spread between them diverges significantly (Z-Score > 2 or < -2), 
                we <strong style="color: var(--danger)">Short</strong> the outperforming stock and <strong style="color: var(--success)">Buy</strong> the underperforming stock. 
                This creates a market-neutral portfolio that profits when the spread reverts to its historical mean.
            </div>
        </div>

        <div id="statArbPicks">
            <h3 class="section-title mt-32"><span class="icon">🔍</span> Scanning Correlated Pairs...</h3>
            <div class="skeleton-line w-60"></div>
            <div class="skeleton-line w-80"></div>
            <div class="bento-grid bento-2 mt-16">
                <div class="skeleton-card" style="height:320px"></div>
                <div class="skeleton-card" style="height:320px"></div>
                <div class="skeleton-card" style="height:320px"></div>
                <div class="skeleton-card" style="height:320px"></div>
            </div>
        </div>
    `;

    // Load mentor picks
    try {
        const pairs = await API.get('/api/pairs');
        renderStatArbPairs(pairs);
    } catch (err) {
        document.getElementById('statArbPicks').innerHTML = `
            <div class="alert alert-danger">
                <span>⚠️</span>
                <div><strong>Failed to load Stat Arb pairs</strong><br>${escapeHtml(err.message)}</div>
            </div>
        `;
    }
});

function renderStatArbPairs(pairs) {
    const el = document.getElementById('statArbPicks');

    if (!pairs || pairs.length === 0) {
        el.innerHTML = `
            <h3 class="section-title mt-32"><span class="icon">📉</span> Active Pair Signals</h3>
            <div class="alert alert-info">
                <span>⚖️</span>
                <div>No active arbitrage opportunities found right now. All tracked spreads are within normal historical bounds (-2 < Z-Score < 2).</div>
            </div>
        `;
        return;
    }

    const sectionTitle = `<h3 class="section-title mt-32"><span class="icon">⚡</span> High-Probability Pair Setups</h3>`;

    const cards = pairs.map((pair, idx) => {
        const tickerA = cleanTicker(pair.tickers[0]);
        const tickerB = cleanTicker(pair.tickers[1]);
        const zScore = parseFloat(pair.z_score || 0);
        const zScoreAbs = Math.abs(zScore);
        const zColor = zScore > 2.0 ? 'var(--danger)' : zScore < -2.0 ? 'var(--success)' : 'var(--warning)';
        
        // Ensure properties exist to prevent undefined issues
        const hedgeRatio = pair.hedge_ratio ? parseFloat(pair.hedge_ratio).toFixed(3) : 'N/A';
        const actionText = pair.signal || 'WAIT';
        const suggestedAction = pair.suggested_action || 'WAIT';
        
        const isTradeable = zScoreAbs >= 2.0;

        return `
            <div class="pick-card" style="border-top: 4px solid #a855f7;">
                <div class="flex justify-between items-center mb-16 pb-16" style="border-bottom: 1px solid var(--border-color);">
                    <div class="flex items-center gap-8">
                        <span style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary);">${escapeHtml(tickerA)}</span>
                        <span style="color: var(--text-muted); font-size: 0.9rem; font-weight: bold;">VS</span>
                        <span style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary);">${escapeHtml(tickerB)}</span>
                    </div>
                    ${isTradeable ? `<span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; font-weight: bold;">${suggestedAction.replace('_', ' ')}</span>` : `<span class="badge">NEUTRAL</span>`}
                </div>

                <div class="flex justify-between items-end mb-16">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Spread Z-Score</div>
                        <div style="font-size: 2rem; font-weight: 900; color: ${zColor}; line-height: 1;">
                            ${zScore > 0 ? '+' : ''}${zScore.toFixed(2)}
                        </div>
                    </div>
                    <div class="text-right">
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Hedge Ratio</div>
                        <div style="font-size: 1.2rem; font-weight: 700; color: var(--text-primary);">
                            ${hedgeRatio}
                        </div>
                    </div>
                </div>
                
                <div class="confidence-bar mt-16 mb-24">
                    <div class="flex justify-between items-center mb-8">
                        <div class="confidence-label" style="margin:0; font-family: monospace;">Divergence Intensity</div>
                        <div style="font-size:0.9rem; font-weight:700; color:${zColor}">${Math.min((zScoreAbs / 4) * 100, 100).toFixed(0)}%</div>
                    </div>
                    <div class="confidence-track" style="background: rgba(255,255,255,0.05); border-radius: 4px; overflow: hidden; height: 8px;">
                        <div class="confidence-fill" style="height: 100%; width: ${Math.min((zScoreAbs / 4) * 100, 100)}%; background: linear-gradient(90deg, #a855f7 0%, ${zColor} 100%); border-radius: 4px; transition: width 1s ease-in-out;"></div>
                    </div>
                </div>

                <div class="p-16 mb-16" style="background: rgba(0,0,0,0.2); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Recommended Action</div>
                    <div style="font-size: 1rem; font-weight: 700; color: ${isTradeable ? 'var(--text-primary)' : 'var(--text-secondary)'};">
                        ${escapeHtml(actionText)}
                    </div>
                </div>

                ${isTradeable ? `
                <button class="btn btn-full" style="background: #a855f7; color: white; border: none; font-weight: bold; box-shadow: 0 4px 14px 0 rgba(168, 85, 247, 0.39);" onclick="logPairTrade('${escapeHtml(tickerA)}', '${escapeHtml(tickerB)}', '${suggestedAction}')">
                    📥 Log Market-Neutral Spread
                </button>
                ` : `
                <button class="btn btn-full" style="background: rgba(255, 255, 255, 0.05); color: var(--text-muted); cursor: not-allowed;" disabled>
                    ⏳ Waiting for Divergence (Z-Score > 2)
                </button>
                `}
            </div>
        `;
    }).join('');

    el.innerHTML = sectionTitle + `<div class="bento-grid bento-2 mt-16">${cards}</div>`;

    // Animate confidence bars
    setTimeout(() => {
        el.querySelectorAll('.confidence-fill').forEach(bar => {
            bar.style.width = bar.style.width; // trigger reflow
        });
    }, 100);
}

async function logPairTrade(tickerA, tickerB, action) {
    // In a real implementation, you'd calculate sizes based on Hedge Ratio and Capital.
    showToast(`Logged Stat Arb setup: ${action} for ${tickerA} / ${tickerB}`, 'success');
}
