// Baseline Merger JavaScript

let currentMode = 'power';
const POWER_METRICS = ['power_mean', 'power_std'];
const QUALITY_METRICS = ['quality_mean', 'quality_std'];

document.addEventListener('DOMContentLoaded', function() {
    // Upload form
    document.getElementById('upload-form').addEventListener('submit', handleUpload);
    
    // Metric toggle buttons
    document.getElementById('toggle-power').addEventListener('click', () => toggleMetricMode('power'));
    document.getElementById('toggle-quality').addEventListener('click', () => toggleMetricMode('quality'));
    
    // Export button
    document.getElementById('export-btn').addEventListener('click', handleExport);
});

async function handleUpload(e) {
    e.preventDefault();
    
    const formData = new FormData();
    const oldFile = document.querySelector('input[name="old_baseline"]').files[0];
    const newFile = document.querySelector('input[name="new_baseline"]').files[0];
    
    if (!oldFile || !newFile) {
        showStatus('Both files are required', 'error');
        return;
    }
    
    formData.append('old_baseline', oldFile);
    formData.append('new_baseline', newFile);
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Upload failed');
        }
        
        const summary = await response.json();
        showStatus(`✓ Loaded successfully! Old: ${summary.only_old}, New: ${summary.only_new}, Both: ${summary.both}`, 'success');
        
        // Show merge section
        document.getElementById('merge-section').classList.remove('hidden');
        document.getElementById('export-section').classList.remove('hidden');
        
        // Display summary
        document.getElementById('summary-text').innerHTML = `
            <strong>Merge Summary:</strong><br>
            Rows only in old baseline: ${summary.only_old}<br>
            Rows only in new baseline: ${summary.only_new}<br>
            Rows in both (can choose): ${summary.both}<br>
            <strong>Total rows: ${summary.total_rows}</strong>
        `;
        
        // Load and display grids
        await loadAndDisplayGrids(currentMode);
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

async function loadAndDisplayGrids(mode) {
    try {
        const response = await fetch(`/api/grids?mode=${mode}`);
        
        if (!response.ok) {
            throw new Error('Failed to load grids');
        }
        
        const data = await response.json();
        currentMode = mode;
        
        // Clear container
        const container = document.getElementById('grids-container');
        container.innerHTML = '';
        
        // Render each grid
        data.grids.forEach(grid => {
            const gridCard = createGridCard(grid, mode);
            container.appendChild(gridCard);
        });
    } catch (error) {
        showStatus('Error loading grids: ' + error.message, 'error');
    }
}

function createGridCard(grid, mode) {
    const card = document.createElement('div');
    card.className = 'grid-card';
    
    // Header
    const header = document.createElement('div');
    header.className = 'grid-header';
    header.textContent = `Frequency ${grid.frequency} - Prefix ${grid.prefix}`;
    card.appendChild(header);
    
    // Table
    const table = document.createElement('table');
    table.className = 'grid-table';
    
    // Thead
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    [
        'Transmitter (Channel)',
        'Receiver (Channel)',
        ...getMetricsForMode(mode),
        'Status'
    ].forEach(label => {
        const th = document.createElement('th');
        th.textContent = label;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Tbody
    const tbody = document.createElement('tbody');
    grid.rows.forEach((row, idx) => {
        const tr = document.createElement('tr');
        
        // TX/RX keys
        const txTd = document.createElement('td');
        txTd.textContent = row.tx_key;
        tr.appendChild(txTd);
        
        const rxTd = document.createElement('td');
        rxTd.textContent = row.rx_key;
        tr.appendChild(rxTd);
        
        // Metrics
        getMetricsForMode(mode).forEach(metric => {
            const metricData = row.metrics[metric];
            const td = document.createElement('td');
            td.innerHTML = createMetricEditor(
                row.identifier,
                metric,
                metricData,
                mode
            );
            tr.appendChild(td);
        });
        
        // Status
        const statusTd = document.createElement('td');
        statusTd.innerHTML = `<span class="merge-status">${getMergeStatusLabel(row.merge_status)}</span>`;
        tr.appendChild(statusTd);
        
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    
    card.appendChild(table);
    return card;
}

function createMetricEditor(identifier, metric, metricData, mode) {
    const oldVal = metricData.old;
    const newVal = metricData.new;
    const selectedSrc = metricData.selected_source;
    const selectedVal = metricData.selected_value;
    const idToken = encodeIdentifier(identifier);
    
    let html = '<div class="metric-cell">';
    html += `<div class="metric-label">${metric}</div>`;
    
    html += '<div class="metric-values">';
    
    // Old value button
    if (oldVal !== null) {
        html += `<button type="button" class="value-box old ${selectedSrc === 'old' ? 'selected' : ''}" 
                 onclick="selectMetricSource('${idToken}', '${metric}', 'old')">
                 Old: ${oldVal.toFixed(2)}</button>`;
    }
    
    // New value button
    if (newVal !== null) {
        html += `<button type="button" class="value-box new ${selectedSrc === 'new' ? 'selected' : ''}" 
                 onclick="selectMetricSource('${idToken}', '${metric}', 'new')">
                 New: ${newVal.toFixed(2)}</button>`;
    }
    
    // Custom value input
    html += '<div class="selector">';
    html += `<button type="button" class="${selectedSrc === 'custom' ? 'active' : ''}" 
             onclick="selectMetricSource('${idToken}', '${metric}', 'custom')">Custom:</button>`;
    html += `<input type="number" step="0.01" value="${selectedVal || ''}" 
             onchange="updateCustomValue('${idToken}', '${metric}', this.value)">`;
    html += '</div>';
    
    html += '</div>';
    html += '</div>';
    
    return html;
}

function getMetricsForMode(mode) {
    return mode === 'power' ? POWER_METRICS : QUALITY_METRICS;
}

function getMergeStatusLabel(status) {
    switch (status) {
        case 'left_only':
            return 'Only in Old';
        case 'right_only':
            return 'Only in New';
        case 'both':
            return 'In Both';
        default:
            return status;
    }
}

async function selectMetricSource(identifierToken, metric, source, customValue = null) {
    const identifier = decodeIdentifier(identifierToken);
    const payload = {
        identifier: identifier,
        metric: metric,
        source: source
    };
    
    if (source === 'custom' && customValue) {
        payload.custom_value = customValue;
    }
    
    try {
        const response = await fetch('/api/set_metric', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            throw new Error('Failed to update metric');
        }
        
        // Reload grids to reflect change
        await loadAndDisplayGrids(currentMode);
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

function updateCustomValue(identifierToken, metric, value) {
    selectMetricSource(identifierToken, metric, 'custom', value);
}

function encodeIdentifier(identifier) {
    return btoa(unescape(encodeURIComponent(JSON.stringify(identifier))));
}

function decodeIdentifier(token) {
    return JSON.parse(decodeURIComponent(escape(atob(token))));
}

async function toggleMetricMode(mode) {
    // Update button style
    document.getElementById('toggle-power').classList.toggle('active', mode === 'power');
    document.getElementById('toggle-quality').classList.toggle('active', mode === 'quality');
    
    // Reload grids
    await loadAndDisplayGrids(mode);
}

async function handleExport() {
    try {
        const response = await fetch('/api/export');
        
        if (!response.ok) {
            throw new Error('Export failed');
        }
        
        // Create a blob and download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = blob.name || 'merged_baseline.csv';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showStatus('✓ Downloaded successfully!', 'success');
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

function showStatus(message, type) {
    const statusDiv = document.getElementById('upload-status');
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
}
