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

        <div id="healthContent">
            <div class="skeleton-grid">
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
                <div class="skeleton-card"></div>
            </div>
        </div>
    `;

    document.getElementById('bulkSyncBtn').addEventListener('click', bulkSync);
    await loadHealthData();
});

async function loadHealthData() {
    const container = document.getElementById('healthContent');
    try {
        const health = await API.get('/api/health');
        const densityRows = Array.isArray(health.ticker_density)
            ? health.ticker_density
            : (Array.isArray(health.density) ? health.density : []);
        
        let html = `
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
                                const statusBadge = totalDays >= 60 
                                    ? `<span class="badge badge-good">SUFFICIENT</span>`
                                    : `<span class="badge badge-bad">INSUFFICIENT DATA</span>`;
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
