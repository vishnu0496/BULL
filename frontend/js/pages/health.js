/* ============================================================
   Data Health — Page Module
   ============================================================ */

registerPage('health', async function(container) {
    container.innerHTML = `
        <div class="flex justify-between items-center mb-16">
            <div>
                <h1 class="page-title">Data Health & Sync Diagnostics</h1>
                <p class="page-subtitle" style="margin-bottom:0;">Check SQLite database health, cached rows, and force synchronization.</p>
            </div>
            <button id="bulkSyncBtn" class="btn btn-primary">🔄 Sync All Watchlist Tickers</button>
        </div>

        <div class="mb-16" style="display:flex; gap:10px; flex-wrap:wrap;">
            <button id="vaultRefreshBtn" class="btn btn-secondary">Refresh Data Vault</button>
        </div>

        <div id="healthContent">
            <div class="skeleton-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>
        </div>
    `;

    document.getElementById('bulkSyncBtn').addEventListener('click', bulkSync);
    document.getElementById('vaultRefreshBtn').addEventListener('click', refreshDataVault);
    await loadHealthData();
});

async function loadHealthData() {
    const container = document.getElementById('healthContent');
    try {
        const [health, dataQuality, vault] = await Promise.all([
            API.get('/api/health'),
            API.get('/api/data/health').catch(() => ({ ok: 0, stale: 0, missing: 0, suspicious: 0, total: 0, rows: [] })),
            API.get('/api/data-vault/status').catch(() => ({ verdict: 'ERROR', total_events: 0, recent_events_24h: 0, yahoo_dependency_pct_24h: 0, source_health: [] }))
        ]);
        const densityRows = Array.isArray(health.ticker_density)
            ? health.ticker_density
            : (Array.isArray(health.density) ? health.density : []);
        const latestAge = health.latest_price_age_days;
        const isFresh = health.seeded === true;
        const dataTotal = Number(dataQuality.total || 0);
        const dataWeak = Number(dataQuality.stale || 0) + Number(dataQuality.missing || 0) + Number(dataQuality.suspicious || 0);
        const okRatio = dataTotal > 0 ? Number(dataQuality.ok || 0) / dataTotal : 0;
        const dataBadge = dataTotal === 0
            ? `<span class="badge badge-weak">NO HEALTH RUN</span>`
            : okRatio >= 0.95
                ? `<span class="badge badge-good">DATA OK</span>`
                : okRatio >= 0.8
                    ? `<span class="badge badge-wait">DATA WARNING</span>`
                    : `<span class="badge badge-bad">DATA BAD</span>`;
        const vaultVerdict = vault.verdict || 'UNKNOWN';
        const vaultClass = vaultVerdict === 'ARCHIVING'
            ? 'badge-good'
            : vaultVerdict === 'YAHOO_HEAVY'
                ? 'badge-wait'
                : vaultVerdict === 'EMPTY'
                    ? 'badge-weak'
                    : 'badge-bad';
        const vaultBadge = `<span class="badge ${vaultClass}">${escapeHtml(vaultVerdict)}</span>`;
        const sourceHealthRows = Array.isArray(vault.source_health) ? vault.source_health : [];
        
        let html = `
            ${!isFresh ? `
                <div class="alert alert-danger mb-24">
                    <span>!</span>
                    <div>
                        <strong>Price data is not fresh enough for serious picks.</strong><br>
                        Latest cache age: ${latestAge == null ? 'unknown' : `${latestAge} day(s)`}. Sync before trusting Today's Picks.
                    </div>
                </div>
            ` : ''}
            ${vaultVerdict === 'YAHOO_HEAVY' ? `
                <div class="alert alert-warning mb-24">
                    <span>!</span>
                    <div>
                        <strong>BULL is still too dependent on Yahoo fallback for live quotes.</strong><br>
                        The Data Vault is archiving payloads, but ${Number(vault.yahoo_dependency_pct_24h || 0).toFixed(0)}% of quote events in the last 24 hours came from Yahoo fallback. Intraday confidence is limited until we add a stronger feed.
                    </div>
                </div>
            ` : ''}
            <div class="bento-grid bento-3 mt-24 mb-24">
                <div class="metric-card">
                    <div class="metric-label">Watchlist Symbols</div>
                    <div class="metric-value accent">${health.watchlist_count}</div>
                    <div class="metric-note">Tickers actively tracked</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Cached Price Rows</div>
                    <div class="metric-value success">${health.price_count}</div>
                    <div class="metric-note">Historical EOD candles stored</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Database Size</div>
                    <div class="metric-value warning">${health.file_size_mb.toFixed(2)} MB</div>
                    <div class="metric-note" style="font-size:0.7rem;">${escapeHtml(health.db_path)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Freshness</div>
                    <div class="metric-value ${isFresh ? 'success' : 'danger'}">${latestAge == null ? 'N/A' : `${latestAge}d`}</div>
                    <div class="metric-note">${isFresh ? 'Fresh enough for scanner' : 'Too stale for real picks'}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Feed Health</div>
                    <div class="metric-value">${dataBadge}</div>
                    <div class="metric-note">${dataQuality.ok || 0}/${dataTotal || 0} tickers OK, ${dataWeak} weak</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Private Data Vault</div>
                    <div class="metric-value">${vaultBadge}</div>
                    <div class="metric-note">${vault.recent_events_24h || 0} source payloads archived in 24h</div>
                </div>
            </div>

            <div class="card mb-24">
                <h3 class="section-title">Source Health</h3>
                <p class="text-muted mb-16">This is the truth table for BULL's current data independence. If this says Yahoo-heavy, BULL is not yet Kite-level.</p>
                <div style="overflow-x: auto;">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Source</th>
                                <th>Category</th>
                                <th>Status</th>
                                <th class="text-right">Reliability</th>
                                <th class="text-right">Latency</th>
                                <th>Last Success</th>
                                <th>Error</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sourceHealthRows.length ? sourceHealthRows.map(row => {
                                const status = row.status || 'UNKNOWN';
                                const statusClass = status === 'OK' ? 'badge-good' : 'badge-bad';
                                return `
                                    <tr>
                                        <td class="text-bold">${escapeHtml(row.source || 'unknown')}</td>
                                        <td>${escapeHtml(row.category || 'unknown')}</td>
                                        <td><span class="badge ${statusClass}">${escapeHtml(status)}</span></td>
                                        <td class="text-right">${Number(row.reliability_score || 0).toFixed(0)}/100</td>
                                        <td class="text-right">${Number(row.latency_ms || 0).toFixed(0)} ms</td>
                                        <td>${escapeHtml(row.last_success_at || 'N/A')}</td>
                                        <td>${escapeHtml(row.error || '')}</td>
                                    </tr>
                                `;
                            }).join('') : `
                                <tr>
                                    <td colspan="7" class="text-muted">No Data Vault collection has run yet. Click Refresh Data Vault.</td>
                                </tr>
                            `}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="card">
                <h3 class="section-title">Data Density per Ticker</h3>
                <div style="overflow-x: auto;">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Ticker</th>
                                <th class="text-right">Total Days Cached</th>
                                <th>Last Cache Date</th>
                                <th class="text-right">Last Stored Close</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${densityRows.map(d => {
                                const totalDays = Number(d.total_days ?? d.rows ?? 0);
                                const lastDate = d.last_date ?? d.latest ?? null;
                                const lastClose = d.last_close ?? d.latest_close ?? null;
                                const ageDays = lastDate ? Math.floor((Date.now() - new Date(lastDate).getTime()) / 86400000) : null;
                                const statusBadge = totalDays < 60
                                    ? `<span class="badge badge-bad">INSUFFICIENT DATA</span>`
                                    : ageDays != null && ageDays > 4
                                        ? `<span class="badge badge-bad">STALE</span>`
                                        : `<span class="badge badge-good">READY</span>`;
                                return `
                                    <tr>
                                        <td class="text-bold">${cleanTicker(d.ticker)}</td>
                                        <td class="text-right">${totalDays}</td>
                                        <td>${lastDate || 'N/A'}</td>
                                        <td class="text-right">${lastClose == null ? 'N/A' : formatINR(lastClose)}</td>
                                        <td>${statusBadge}</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        container.innerHTML = html;
    } catch (err) {
        showError(container, err.message);
    }
}

async function refreshDataVault() {
    const btn = document.getElementById('vaultRefreshBtn');
    btn.disabled = true;
    btn.innerText = 'Refreshing...';
    showToast('Refreshing Data Vault from available free sources...', 'info');

    try {
        const result = await API.post('/api/data-vault/refresh?limit=12&include_news=false');
        showToast(`Data Vault refresh ${result.status || 'done'}: ${JSON.stringify(result.counts || {})}`, 'success');
        await loadHealthData();
    } catch (err) {
        showToast('Data Vault refresh failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerText = 'Refresh Data Vault';
    }
}

async function bulkSync() {
    const btn = document.getElementById('bulkSyncBtn');
    btn.disabled = true;
    btn.innerText = 'Syncing... Please wait...';

    showToast('Starting bulk sync. This may take a minute...', 'info');

    try {
        const results = await API.post('/api/sync-all');
        const successCount = results.filter(r => r.success).length;
        const totalRows = results.reduce((sum, r) => sum + (r.rows_synced || 0), 0);
        
        showToast(`Sync complete! Updated ${successCount}/${results.length} tickers, fetching ${totalRows} rows.`, 'success');
        
        // Reload page data
        await loadHealthData();
    } catch (err) {
        showToast('Bulk sync failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerText = '🔄 Sync All Watchlist Tickers';
    }
}
