/* ============================================================
   Capital Settings — Page Module
   ============================================================ */

registerPage('settings', async function(container) {
    container.innerHTML = `
        <h1 class="page-title">Capital Settings</h1>
        <p class="page-subtitle">Configure your trading parameters, risk limits, and API keys.</p>

        <div id="settingsContent">
            <div class="skeleton-card" style="height: 500px;"></div>
        </div>
    `;

    try {
        const settings = await API.get('/api/capital');
        const mount = document.getElementById('settingsContent');
        if (!mount) return;
        renderSettingsForm(settings, mount);
    } catch (err) {
        const mount = document.getElementById('settingsContent');
        if (mount) showError(mount, err.message);
    }
});

function renderSettingsForm(s, mount = document.getElementById('settingsContent')) {
    if (!mount) return;
    const isConfigured = (field) => s[`${field}_configured`] === true || s[`${field}_status`] === 'CONFIGURED';
    const credentialPlaceholder = (field) => isConfigured(field) ? 'Configured' : '';
    const kiteConfigured = isConfigured('kite_api_key') && isConfigured('kite_api_secret') && isConfigured('kite_request_token');
    const kiteBadge = kiteConfigured 
        ? `<span class="badge" style="background: rgba(56,189,248,0.1); color: var(--accent); border: 1px solid rgba(56,189,248,0.2);">CONFIGURED</span>`
        : `<span class="badge badge-neutral">PENDING</span>`;

    const riskRatio = (s.max_risk_per_trade / s.total_capital) * 100;
    const riskAlert = riskRatio > 5 
        ? `<div class="alert alert-warning mt-16"><span>⚠️</span><div>Your risk per trade is <strong>${riskRatio.toFixed(1)}%</strong> of total capital. This is considered highly aggressive. Professional traders recommend 1-2%.</div></div>`
        : `<div class="alert alert-success mt-16"><span>✓</span><div>Your risk per trade is <strong>${riskRatio.toFixed(1)}%</strong> of total capital, which is within safe bounds (under 5%).</div></div>`;

    mount.innerHTML = `
        <div class="bento-grid bento-2-1">
            <div class="card">
                <h3 class="section-title">Configuration Parameters</h3>
                
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Total Trading Capital (₹)</label>
                        <input type="number" id="setCapital" class="form-input" value="${s.total_capital}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Maximum Risk Per Trade (₹)</label>
                        <input type="number" id="setRisk" class="form-input" value="${s.max_risk_per_trade}">
                    </div>
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Maximum Trades Per Day</label>
                        <input type="range" id="setTrades" min="1" max="10" value="${s.max_trades_per_day}" style="width:100%; margin-top:8px;">
                        <div class="text-right text-muted mt-8" id="setTradesVal">${s.max_trades_per_day}</div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Experience Level</label>
                        <select id="setExp" class="form-select">
                            <option value="BEGINNER" ${s.experience_level === 'BEGINNER' ? 'selected' : ''}>BEGINNER</option>
                            <option value="INTERMEDIATE" ${s.experience_level === 'INTERMEDIATE' ? 'selected' : ''}>INTERMEDIATE</option>
                            <option value="ADVANCED" ${s.experience_level === 'ADVANCED' ? 'selected' : ''}>ADVANCED</option>
                        </select>
                    </div>
                </div>

                <div class="form-group mt-16">
                    <label class="form-label">Allow Option Suggestions (F&O)</label>
                    <div class="flex items-center gap-8 mt-8">
                        <input type="checkbox" id="setOptions" disabled ${s.allow_options ? 'checked' : ''}>
                        <span class="text-muted" style="font-size:0.85rem;">Disabled for safety during paper trading phase.</span>
                    </div>
                </div>

                <div class="form-group mt-16">
                    <label class="form-label" style="display: flex; align-items: center; gap: 8px;">
                        <span>Autopilot Autotrading (Simulated Broker)</span>
                        <span class="badge" style="background: rgba(239, 68, 68, 0.1); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.2); font-size: 0.7rem; padding: 2px 6px;">DISABLED</span>
                    </label>
                    <div class="flex items-center gap-8 mt-8">
                        <input type="checkbox" id="setAutopilot" disabled>
                        <span class="text-muted" style="font-size:0.85rem;">Autonomous execution is disabled. All trades must be logged manually.</span>
                    </div>
                </div>

                <hr style="border:0; border-top:1px solid var(--border-subtle); margin: 32px 0;">

                <h3 class="section-title">API Connections</h3>
                
                <div class="form-group">
                    <label class="form-label">Google Gemini API Key</label>
                    <input type="password" id="setGemini" class="form-input" value="" placeholder="${credentialPlaceholder('gemini_api_key')}">
                    <div class="form-hint">Required for AI News Sentiment Analysis. (Keep secure)</div>
                </div>
                
                <h3 class="section-title mt-32"><span class="icon">🔗</span> Enterprise API Integration</h3>
                
                <div class="form-group mt-16">
                    <label class="form-label">Dhan Client ID</label>
                    <input type="text" id="setDhanClientId" class="form-input" value="" placeholder="${credentialPlaceholder('dhan_client_id') || 'e.g. 1100000001'}">
                    <div class="form-hint">Your 10-digit Dhan ID for DhanHQ API.</div>
                </div>

                <div class="form-group">
                    <label class="form-label">Dhan Access Token</label>
                    <input type="password" id="setDhanAccessToken" class="form-input" value="" placeholder="${credentialPlaceholder('dhan_access_token')}">
                    <div class="form-hint">Generate from web.dhan.co -> DhanHQ APIs. Provides real-time Market Data.</div>
                </div>

                <div class="flex items-center justify-between mt-24 mb-16">
                    <div style="font-size: 1rem; font-weight: 700; color: var(--text-primary);">Zerodha Kite Connect</div>
                    ${kiteBadge}
                </div>

                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label">Kite Connect API Key</label>
                        <input type="text" id="setKiteKey" class="form-input" value="" placeholder="${credentialPlaceholder('kite_api_key')}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Kite Connect API Secret</label>
                        <input type="password" id="setKiteSecret" class="form-input" value="" placeholder="${credentialPlaceholder('kite_api_secret')}">
                    </div>
                </div>

                <div class="form-group">
                    <label class="form-label">Kite Request Token (Daily Login)</label>
                    <input type="text" id="setKiteToken" class="form-input" value="" placeholder="${credentialPlaceholder('kite_request_token')}">
                </div>

                <button class="btn btn-primary mt-24" style="width: 100%;" onclick="saveSettings()">Save Configuration Settings</button>
            </div>

            <div>
                <div class="card" style="background: rgba(15, 23, 42, 0.4);">
                    <h3 class="section-title">Risk Advisory</h3>
                    ${riskAlert}
                </div>
            </div>
        </div>
    `;

    document.getElementById('setTrades').addEventListener('input', (e) => {
        document.getElementById('setTradesVal').textContent = e.target.value;
    });
}

async function saveSettings() {
    const capital = parseFloat(document.getElementById('setCapital').value);
    const risk = parseFloat(document.getElementById('setRisk').value);
    const trades = parseInt(document.getElementById('setTrades').value, 10);
    const exp = document.getElementById('setExp').value;
    const gemini = document.getElementById('setGemini').value.trim();
    const dhanClientId = document.getElementById('setDhanClientId').value.trim();
    const dhanAccessToken = document.getElementById('setDhanAccessToken').value.trim();
    const kiteKey = document.getElementById('setKiteKey').value;
    const kiteSecret = document.getElementById('setKiteSecret').value;
    const kiteToken = document.getElementById('setKiteToken').value;
    const autopilot = document.getElementById('setAutopilot').checked ? 1 : 0;

    if (isNaN(capital) || capital < 100) { showToast('Capital must be at least 100', 'error'); return; }
    if (isNaN(risk) || risk < 10) { showToast('Risk must be at least 10', 'error'); return; }
    if (risk > capital) { showToast('Risk cannot exceed total capital', 'error'); return; }

    try {
        const body = {
            total_capital: capital,
            max_risk_per_trade: risk,
            max_trades_per_day: trades,
            allow_options: 0,
            experience_level: exp,
            gemini_api_key: gemini,
            dhan_client_id: dhanClientId,
            dhan_access_token: dhanAccessToken,
            kite_api_key: kiteKey,
            kite_api_secret: kiteSecret,
            kite_request_token: kiteToken,
            autopilot: autopilot
        };
        
        await API.put('/api/capital', body);
        showToast('Settings saved successfully.', 'success');
        
        // Reload to update risk advisory
        const settings = await API.get('/api/capital');
        renderSettingsForm(settings);

    } catch (err) {
        showToast('Failed to save settings: ' + err.message, 'error');
    }
}
