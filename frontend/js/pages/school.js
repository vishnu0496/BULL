/* ============================================================
   Market School — Page Module
   ============================================================ */

registerPage('school', async function(container) {
    container.innerHTML = `
        <h1 class="page-title">Market School</h1>
        <p class="page-subtitle">Educational resources to understand markets, technical analysis, and options trading.</p>

        <div class="tabs mt-24">
            <button class="tab active" data-tab="markets">📦 Markets & Products</button>
            <button class="tab" data-tab="technical">🎯 Technical Analysis</button>
            <button class="tab" data-tab="options">⚖️ Options Dictionary</button>
        </div>

        <div class="tab-content active" data-tab="markets">
            <div class="bento-grid bento-2">
                <div class="school-card">
                    <div class="school-term">Stock / Equity</div>
                    <div class="school-definition">A slice of ownership in a company. If you buy a share of Reliance, you own a tiny piece of Reliance.</div>
                    <div class="school-example">Example: Buying 10 shares of TATAMOTORS at ₹1000 each.</div>
                </div>
                <div class="school-card">
                    <div class="school-term">Nifty 50 / Index</div>
                    <div class="school-definition">A basket of the top 50 biggest companies in India. It acts as a thermometer for the entire stock market.</div>
                    <div class="school-example">Example: If Nifty goes up, it means most big companies had a good day.</div>
                </div>
                <div class="school-card">
                    <div class="school-term">IPO (Initial Public Offering)</div>
                    <div class="school-definition">When a private company sells its shares to the general public for the very first time.</div>
                </div>
                <div class="school-card">
                    <div class="school-term">Mutual Fund</div>
                    <div class="school-definition">A pool of money from many investors managed by a professional who buys a mix of stocks or bonds.</div>
                </div>
                <div class="school-card span-2">
                    <div class="school-term">ETF (Exchange Traded Fund)</div>
                    <div class="school-definition">Like a mutual fund, but it trades on the stock market like a regular stock (e.g., NIFTYBEES).</div>
                </div>
            </div>
        </div>

        <div class="tab-content" data-tab="technical">
            <div class="bento-grid bento-2">
                <div class="flex-col gap-12">
                    <div class="school-card" style="border-left-color: var(--success);">
                        <div class="school-term">Bullish</div>
                        <div class="school-definition">An expectation that prices will go UP. (Bulls strike upwards with their horns).</div>
                    </div>
                    <div class="school-card" style="border-left-color: var(--accent);">
                        <div class="school-term">Entry / Trigger Price</div>
                        <div class="school-definition">The exact price level where you should buy the stock because it confirms a breakout.</div>
                    </div>
                    <div class="school-card" style="border-left-color: var(--danger);">
                        <div class="school-term">Stop-Loss (Safety Exit)</div>
                        <div class="school-definition">An automatic exit price set BELOW your buying price. It cuts your losses before they get too big if the trade goes wrong.</div>
                        <div class="school-example">Always respect your stop-loss. It is your shield.</div>
                    </div>
                </div>
                <div class="flex-col gap-12">
                    <div class="school-card" style="border-left-color: var(--danger);">
                        <div class="school-term">Bearish</div>
                        <div class="school-definition">An expectation that prices will go DOWN. (Bears swipe downwards with their paws).</div>
                    </div>
                    <div class="school-card" style="border-left-color: var(--success);">
                        <div class="school-term">Target / Profit Goal</div>
                        <div class="school-definition">The price level where you plan to sell and collect your profits.</div>
                    </div>
                    <div class="school-card" style="border-left-color: var(--warning);">
                        <div class="school-term">Risk Management</div>
                        <div class="school-definition">Never risking more than 1-2% of your total capital on a single trade. If you have ₹10,000, your max loss per trade should be ₹100-200.</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="tab-content" data-tab="options">
            <div class="alert alert-warning mb-24">
                <span>⚠️</span>
                <div>Options (F&O) are highly leveraged instruments. 90% of retail traders lose money in Options. Learn thoroughly before trading them with real money.</div>
            </div>
            
            <div class="bento-grid bento-3">
                <div class="school-card">
                    <div class="school-term">Call Option (CE)</div>
                    <div class="school-definition">A contract that makes money if the underlying stock goes UP.</div>
                </div>
                <div class="school-card">
                    <div class="school-term">Put Option (PE)</div>
                    <div class="school-definition">A contract that makes money if the underlying stock goes DOWN.</div>
                </div>
                <div class="school-card">
                    <div class="school-term">Premium</div>
                    <div class="school-definition">The price you pay to buy the option contract. This is your maximum risk.</div>
                </div>
                <div class="school-card">
                    <div class="school-term">Lot Size</div>
                    <div class="school-definition">Options cannot be bought in single shares. They are bought in fixed lots (e.g., Nifty lot size is 25).</div>
                </div>
                <div class="school-card">
                    <div class="school-term">Expiry</div>
                    <div class="school-definition">Options have a shelf life. They expire every Thursday (for Nifty) or month-end (for stocks).</div>
                </div>
                <div class="school-card">
                    <div class="school-term">Time Decay (Theta)</div>
                    <div class="school-definition">Options lose value every single day just by holding them, like a melting ice cube.</div>
                </div>
            </div>
        </div>
    `;

    initTabs(container);
});
