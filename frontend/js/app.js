/* ============================================================
   BULL Research Desk — Core SPA Framework
   ============================================================ */

// ── API Client ──
const API = {
    async get(path) {
        try {
            const res = await fetch(path);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.error(`API GET ${path}:`, err);
            throw err;
        }
    },
    async post(path, body = {}) {
        try {
            const res = await fetch(path, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.error(`API POST ${path}:`, err);
            throw err;
        }
    },
    async put(path, body = {}) {
        try {
            const res = await fetch(path, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.error(`API PUT ${path}:`, err);
            throw err;
        }
    },
    async del(path) {
        try {
            const res = await fetch(path, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            console.error(`API DELETE ${path}:`, err);
            throw err;
        }
    }
};

// ── Formatting Utilities ──
function formatINR(value) {
    if (value == null || isNaN(value)) return 'INR 0.00';
    const num = Number(value);
    return 'INR ' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(value) {
    if (value == null || isNaN(value)) return '0.00%';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '';
    return sign + num.toFixed(2) + '%';
}

function formatNum(value, decimals = 2) {
    if (value == null || isNaN(value)) return '0';
    return Number(value).toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function cleanTicker(ticker) {
    if (!ticker) return '';
    if (ticker.startsWith('^')) return ticker;
    return ticker.split('.')[0];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Badge Generator ──
function badge(text, type) {
    return `<span class="badge badge-${type}">${escapeHtml(text)}</span>`;
}

function decisionBadge(decision) {
    const map = { TRADE: 'trade', WAIT: 'wait', REJECT: 'reject' };
    return badge(decision, map[decision] || 'neutral');
}

function verdictBadge(verdict) {
    const map = { GOOD: 'good', WEAK: 'weak', BAD: 'bad' };
    return badge(verdict, map[verdict] || 'neutral');
}

function sentimentBadge(label) {
    const map = { BULLISH: 'bullish', BEARISH: 'bearish', NEUTRAL: 'neutral' };
    return badge(label, map[label] || 'neutral');
}

// ── Toast Notifications ──
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const icons = { success: '✓', error: '✕', info: 'ℹ' };
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 200);
    }, 4000);
}

// ── Loading States ──
function showLoading(container) {
    container.innerHTML = `
        <div class="skeleton-line w-60"></div>
        <div class="skeleton-line w-80"></div>
        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 24px;">
            <div class="skeleton-card"></div>
            <div class="skeleton-card"></div>
            <div class="skeleton-card"></div>
        </div>
    `;
}

function showError(container, message) {
    container.innerHTML = `
        <div class="alert alert-danger">
            <span>⚠️</span>
            <div>
                <strong>Something went wrong</strong><br>
                ${escapeHtml(message)}
            </div>
        </div>
    `;
}

// ── Page Registry ──
const PAGES = {};

function registerPage(name, renderFn) {
    PAGES[name] = renderFn;
}

// ── Router ──
let currentPage = null;

function navigateTo(page) {
    if (currentPage === page) return;
    currentPage = page;

    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });

    // Render page
    const main = document.getElementById('mainContent');
    main.innerHTML = '';
    main.className = 'main-content page-enter';

    if (PAGES[page]) {
        PAGES[page](main);
    } else {
        main.innerHTML = `
            <h1 class="page-title">Page Not Found</h1>
            <p class="page-subtitle">The page "${escapeHtml(page)}" doesn't exist.</p>
        `;
    }

    // Re-trigger animation
    void main.offsetWidth;
}

// ── Tab System ──
function initTabs(container) {
    const tabs = container.querySelectorAll('.tab');
    const contents = container.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            tabs.forEach(t => t.classList.toggle('active', t === tab));
            contents.forEach(c => c.classList.toggle('active', c.dataset.tab === target));
        });
    });
}

// ── Market Status ──
function updateMarketStatus() {
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const day = now.getDay();
    const totalMinutes = hours * 60 + minutes;

    // IST: Market open 9:15 AM (555) to 3:30 PM (930), Mon-Fri
    const isWeekday = day >= 1 && day <= 5;
    const isMarketHours = totalMinutes >= 555 && totalMinutes <= 930;
    const isOpen = isWeekday && isMarketHours;

    document.querySelectorAll('.market-status').forEach(el => {
        const dot = el.querySelector('.status-dot');
        const text = el.querySelector('.status-text');
        if (dot) {
            dot.className = `status-dot ${isOpen ? 'online' : 'offline'}`;
        }
        if (text) {
            text.textContent = isOpen ? 'Market Open' : 'Market Closed';
        }
    });
}

// ── Initialization ──
document.addEventListener('DOMContentLoaded', () => {
    // Sidebar Hamburger Menu & Backdrop
    const sidebar = document.getElementById('sidebar');
    const hamburgerBtn = document.getElementById('hamburgerBtn');
    const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');

    if (hamburgerBtn && sidebar && sidebarBackdrop) {
        hamburgerBtn.addEventListener('click', () => {
            sidebar.classList.add('mobile-open');
            sidebarBackdrop.classList.add('active');
        });
    }

    const closeSidebar = () => {
        if (sidebar && sidebarBackdrop) {
            sidebar.classList.remove('mobile-open');
            sidebarBackdrop.classList.remove('active');
        }
    };

    if (sidebarCloseBtn) {
        sidebarCloseBtn.addEventListener('click', closeSidebar);
    }
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', closeSidebar);
    }

    // Setup nav clicks
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            window.location.hash = page;
            closeSidebar();
        });
    });

    // Top Bar Mobile Expansion
    const macroTickerBar = document.getElementById('macroTickerBar');
    const topbarNiftyItem = document.getElementById('topbarNiftyItem');
    if (topbarNiftyItem && macroTickerBar) {
        topbarNiftyItem.addEventListener('click', (e) => {
            if (window.innerWidth <= 768) {
                macroTickerBar.classList.toggle('expanded');
            }
        });
    }

    // Explore Section Toggle
    const exploreToggleBtn = document.getElementById('exploreToggleBtn');
    const exploreSection = document.getElementById('exploreSection');
    const exploreToggleText = document.getElementById('exploreToggleText');

    if (exploreToggleBtn && exploreSection && exploreToggleText) {
        // Restore state
        const isCollapsed = localStorage.getItem('exploreSectionCollapsed') !== 'false';
        if (isCollapsed) {
            exploreSection.classList.remove('expanded');
            exploreSection.classList.add('collapsed');
            exploreToggleText.textContent = '▼ More tools';
        } else {
            exploreSection.classList.remove('collapsed');
            exploreSection.classList.add('expanded');
            exploreToggleText.textContent = '▲ Less tools';
        }

        exploreToggleBtn.addEventListener('click', () => {
            const currentlyCollapsed = exploreSection.classList.contains('collapsed');
            if (currentlyCollapsed) {
                exploreSection.classList.remove('collapsed');
                exploreSection.classList.add('expanded');
                exploreToggleText.textContent = '▲ Less tools';
                localStorage.setItem('exploreSectionCollapsed', 'false');
            } else {
                exploreSection.classList.remove('expanded');
                exploreSection.classList.add('collapsed');
                exploreToggleText.textContent = '▼ More tools';
                localStorage.setItem('exploreSectionCollapsed', 'true');
            }
        });
    }

    // Hash-based routing
    function handleRoute() {
        const hash = window.location.hash.slice(1) || 'mentor';
        navigateTo(hash);
    }

    window.addEventListener('hashchange', handleRoute);
    handleRoute();

    // Market status
    updateMarketStatus();
    setInterval(updateMarketStatus, 60000);

    // Live Macro Regime Poller (Intraday High Frequency)
    async function checkMacroRegime() {
        try {
            const regime = await API.get('/api/market/live-regime');
            const bannerId = 'macroShockBanner';
            let banner = document.getElementById(bannerId);
            
            if (regime.sentiment === 'BEARISH_SHOCK') {
                if (!banner) {
                    banner = document.createElement('div');
                    banner.id = bannerId;
                    banner.style.cssText = 'background: rgba(220, 38, 38, 0.9); color: white; padding: 12px; text-align: center; font-weight: bold; position: sticky; top: 0; z-index: 9999; display: flex; justify-content: center; align-items: center; gap: 8px; backdrop-filter: blur(8px);';
                    document.body.insertBefore(banner, document.body.firstChild);
                    
                    // Auto-refresh the mentor page to show rejected trades
                    if (currentPage === 'mentor' && typeof renderMentorPicks === 'function') {
                        API.get('/api/mentor/picks').then(picks => renderMentorPicks(picks));
                    }
                }
                banner.innerHTML = `<span>🚨</span> <span>MACRO SHOCK DETECTED: ${escapeHtml(regime.reason)} All Long trades aborted.</span>`;
            } else {
                if (banner) {
                    banner.remove();
                    if (currentPage === 'mentor' && typeof renderMentorPicks === 'function') {
                        API.get('/api/mentor/picks').then(picks => renderMentorPicks(picks));
                    }
                }
            }

            // Fetch and update BULL Score
            const marketRegime = await API.get('/api/market/regime').catch(() => ({ trend_score: 50 }));
            const bullScore = marketRegime.trend_score || 50;
            const scoreValEl = document.getElementById('topbarBullScore');
            if (scoreValEl) {
                scoreValEl.textContent = `${bullScore}/100`;
                if (bullScore >= 65) {
                    scoreValEl.style.color = 'var(--success)';
                } else if (bullScore <= 35) {
                    scoreValEl.style.color = 'var(--danger)';
                } else {
                    scoreValEl.style.color = 'var(--warning)';
                }
            }
        } catch (e) {
            console.error('Failed to poll macro regime/BULL score', e);
        }
    }

    checkMacroRegime();
    setInterval(checkMacroRegime, 60000);

    // Live Price Stream Connection (SSE)
    let priceSource = null;
    let isUserScrolling = false;
    let scrollIdleTimer = null;

    window.addEventListener('scroll', () => {
        isUserScrolling = true;
        clearTimeout(scrollIdleTimer);
        scrollIdleTimer = setTimeout(() => {
            isUserScrolling = false;
        }, 180);
    }, { passive: true });
    
    // Live Indices Stream Connection (SSE)
    let indicesSource = null;
    function connectIndicesStream() {
        if (indicesSource) {
            indicesSource.close();
        }
        indicesSource = new EventSource('/api/indices/stream');
        indicesSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (data.items) {
                    const nifty = data.items.find(item => item.id === 'NIFTY');
                    if (nifty) {
                        const niftyVal = document.getElementById('macroNifty');
                        const niftyDesc = document.getElementById('macroNiftyDesc');
                        if (niftyVal) {
                            const changeClass = nifty.change_percent >= 0 ? 'up' : 'down';
                            const changeSign = nifty.change_percent >= 0 ? '▲' : '▼';
                            niftyVal.innerHTML = `₹${nifty.value.toLocaleString('en-IN', {minimumFractionDigits: 2})} <span class="macro-ticker-change ${changeClass}">${changeSign}${Math.abs(nifty.change_percent).toFixed(2)}%</span>`;
                            if (niftyDesc) {
                                if (window.innerWidth <= 768) {
                                    niftyDesc.textContent = "Tap to view full metrics";
                                } else {
                                    niftyDesc.textContent = nifty.change_percent >= 0 
                                        ? "Nifty rising → market mood is positive today."
                                        : "Nifty falling → market mood is cautious today.";
                                }
                            }
                        }
                    }
                }
            } catch (e) {
                console.error('Error parsing live index data:', e);
            }
        };
        indicesSource.onerror = function() {
            indicesSource.close();
            indicesSource = null;
            setTimeout(connectIndicesStream, 5000);
        };
    }
    connectIndicesStream();

    function connectPriceStream() {
        if (priceSource) {
            priceSource.close();
        }
        
        priceSource = new EventSource('/api/prices/stream');
        
        priceSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                
                // Handle macro updates
                if (data.type === 'macro') {
                    // Update Crude Oil
                    const crudeVal = document.getElementById('macroCrude');
                    const crudeDesc = document.getElementById('macroCrudeDesc');
                    if (crudeVal && data.crude_oil) {
                        const val = data.crude_oil;
                        const changeClass = val.change_pct >= 0 ? 'up' : 'down';
                        const changeSign = val.change_pct >= 0 ? '▲' : '▼';
                        crudeVal.innerHTML = `$${val.price.toFixed(2)} <span class="macro-ticker-change ${changeClass}">${changeSign}${Math.abs(val.change_pct).toFixed(2)}%</span>`;
                        if (crudeDesc) {
                            crudeDesc.textContent = val.change_pct < 0 
                                ? "Oil down → good for India. Petrol/diesel may get cheaper." 
                                : "Oil up → bad for India. Inflation risk. Avoid aviation stocks.";
                        }
                    }
                    
                    // Update USD/INR
                    const usdInrVal = document.getElementById('macroUsdInr');
                    const usdInrDesc = document.getElementById('macroUsdInrDesc');
                    if (usdInrVal && data.usd_inr) {
                        const val = data.usd_inr;
                        const changeClass = val.change_pct >= 0 ? 'up' : 'down';
                        const changeSign = val.change_pct >= 0 ? '▲' : '▼';
                        usdInrVal.innerHTML = `₹${val.price.toFixed(2)} <span class="macro-ticker-change ${changeClass}">${changeSign}${Math.abs(val.change_pct).toFixed(2)}%</span>`;
                        if (usdInrDesc) {
                            usdInrDesc.textContent = val.change_pct < 0 
                                ? "Rupee strong → IT stocks may fall (they earn in dollars)" 
                                : "Rupee weak → IT stocks may rise, imports get expensive";
                        }
                    }
                    
                    // Update US 10Y Yield
                    const us10yVal = document.getElementById('macroUs10y');
                    const us10yDesc = document.getElementById('macroUs10yDesc');
                    if (us10yVal && data.us_10y_yield) {
                        const val = data.us_10y_yield;
                        const changeClass = val.change_pct >= 0 ? 'up' : 'down';
                        const changeSign = val.change_pct >= 0 ? '▲' : '▼';
                        us10yVal.innerHTML = `${val.price.toFixed(2)}% <span class="macro-ticker-change ${changeClass}">${changeSign}${Math.abs(val.change_pct).toFixed(2)}%</span>`;
                        if (us10yDesc) {
                            us10yDesc.textContent = val.change_pct >= 0 
                                ? "US yields up → foreign money may leave India. Watch for FII selling." 
                                : "US yields down → good for Indian markets. FII may buy.";
                        }
                    }
                    
                    // Update Geopolitical Risk
                    const riskVal = document.getElementById('macroRisk');
                    const riskDesc = document.getElementById('macroRiskDesc');
                    if (riskVal && data.global_risk) {
                        const val = data.global_risk;
                        let badgeType = 'neutral';
                        if (val.level === 'HIGH') badgeType = 'danger';
                        else if (val.level === 'LOW') badgeType = 'success';
                        
                        riskVal.innerHTML = `<span class="badge badge-${badgeType}" style="padding: 2px 6px; font-size: 0.65rem;">${val.level}</span>`;
                        if (riskDesc) {
                            riskDesc.textContent = `What this means: ${val.reason}`;
                        }
                    }
                    return;
                }
                
                // Handle stock price updates
                const ticker = data.ticker;
                const price = data.price;
                if (!ticker) return;
                if (isUserScrolling) return;
                const isSimulatedPrice = data.is_simulated === true || data.not_real_market_data === true;
                
                // Find all live price spans in the document
                const selector = `[data-ticker="${ticker}"] .live-price`;
                const elements = document.querySelectorAll(selector);
                elements.forEach(el => {
                    const prevPrice = parseFloat(el.getAttribute('data-price') || '0');
                    el.textContent = '₹' + price.toFixed(2);
                    el.setAttribute('data-price', price);
                    
                    // Gap-Up Protection: Flag trades where live price exceeds entry trigger by >1.5%
                    if (isSimulatedPrice) {
                        el.setAttribute('title', 'Simulated tick generated from stored end-of-day data. Not real market data.');
                    }

                    const entryTrigger = parseFloat(el.getAttribute('data-trigger') || '0');
                    if (!isSimulatedPrice && entryTrigger > 0 && price > entryTrigger * 1.015) {
                        const card = el.closest('.watchlist-card') || el.closest('.pick-card') || el.closest('.best-opp-card');
                        if (card) {
                            const badgeEl = card.querySelector('.badge');
                            if (badgeEl && (badgeEl.textContent === 'TRADE' || badgeEl.textContent === 'Ready to Buy')) {
                                badgeEl.textContent = 'GAP-UP AVOID';
                                badgeEl.className = 'badge badge-reject';
                                badgeEl.style.cssText = 'background: rgba(244, 63, 94, 0.12); color: var(--danger); border: 1px solid rgba(244, 63, 94, 0.2);';
                            }

                            // Update mentor page status if present
                            const statusEl = card.querySelector('.pick-status');
                            if (statusEl) {
                                statusEl.textContent = '🛑 Avoid (Price Gapped Up)';
                                statusEl.style.color = 'var(--danger)';
                            }

                            // Disable Log Trade button if present
                            const btn = card.querySelector('button');
                            if (btn && !btn.disabled) {
                                btn.textContent = '🛑 Avoid (Price Gapped Up)';
                                btn.disabled = true;
                                btn.style.background = 'rgba(220, 38, 38, 0.1)';
                                btn.style.color = 'var(--danger)';
                                btn.style.border = '1px solid var(--danger)';
                                btn.style.cursor = 'not-allowed';
                            }
                        }
                    }
                    
                    // Flash effect (green for up, red for down)
                    if (prevPrice > 0) {
                        if (price > prevPrice) {
                            el.style.color = '#10b981'; // green
                            setTimeout(() => { el.style.color = ''; }, 300);
                        } else if (price < prevPrice) {
                            el.style.color = '#f43f5e'; // red
                            setTimeout(() => { el.style.color = ''; }, 300);
                        }
                    }
                });
            } catch (e) {
                console.error('Error parsing live price data:', e);
            }
        };
        
        priceSource.onerror = function(err) {
            console.warn('Price stream disconnected; reconnecting in 5s...', err);
            priceSource.close();
            setTimeout(connectPriceStream, 5000);
        };
    }
    
    connectPriceStream();
});
