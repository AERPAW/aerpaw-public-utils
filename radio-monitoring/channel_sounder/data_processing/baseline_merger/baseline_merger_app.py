#!/usr/bin/env python3
"""
Baseline Merger Web App

A Flask-based interactive editor for merging two baseline CSV files.
Allows side-by-side comparison and per-row/per-metric selection.
"""

import os
import json
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from io import StringIO, BytesIO
from datetime import datetime
import csv

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# In-memory state for the current merge session
merge_state = {
    'old_baseline': None,
    'new_baseline': None,
    'merged_rows': None,
    'metric_mode': 'power',  # 'power' or 'quality'
}

# Baseline schema constants (match check_baseline.py and compare_baselines.py)
KEY_COLS = [
    'transmitter',
    'transmitter_channel',
    'transmitter_serial_number',
    'receiver',
    'receiver_channel',
    'receiver_serial_number',
    'receiver_frequency',
]

METRIC_COLS = ['power_mean', 'power_std', 'quality_mean', 'quality_std']

POWER_METRICS = ['power_mean', 'power_std']
QUALITY_METRICS = ['quality_mean', 'quality_std']

# Radio type mapping by serial number (from plot_results.py)
RADIO_DICT = {
    'B210': [
        '31EAC18',
        '3235751',
        '3235754',
        '3235724',
        '323576B',
        '31EABF2',
        '31EAC20',
        '31EAC27',
    ],
    'B205': [
        '319B6EC',
        '32332D6',
        '32332D0',
        '32332D4',
        '3233282',
        '31E74C2',
        '319B8F9',
        '3233241',
    ]
}

def get_radio_type(serial_number):
    """Get radio type (B205 or B210) from serial number."""
    if pd.isna(serial_number) or serial_number == '<NA>':
        return 'Unknown'
    for radio_type, serials in RADIO_DICT.items():
        if str(serial_number) in serials:
            return radio_type
    return 'Unknown'


def format_display_key(node_name, channel, serial_number):
    """Render a compact frontend label using node/channel and optional B205/B210 tag."""
    radio_type = get_radio_type(serial_number)
    base = f"({node_name}, {channel})"
    if radio_type in ('B205', 'B210'):
        return f"{base} [{radio_type}]"
    return base


def load_baseline(path: str) -> pd.DataFrame:
    """Load and normalize a baseline CSV file."""
    df = pd.read_csv(path)
    
    # Ensure all key and metric columns exist
    for col in KEY_COLS + METRIC_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    
    # Normalize key columns
    for col in ['transmitter', 'transmitter_serial_number', 'receiver', 'receiver_serial_number', 'receiver_frequency']:
        df[col] = df[col].astype('string').fillna('<NA>')
    
    for col in ['transmitter_channel', 'receiver_channel']:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
    
    for col in METRIC_COLS:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df[KEY_COLS + METRIC_COLS].copy()


def merge_baselines(old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """Outer merge two baseline dataframes on key columns."""
    merged = old_df.merge(
        new_df,
        on=KEY_COLS,
        how='outer',
        suffixes=('_old', '_new'),
        indicator=True
    )
    
    # Initialize selection state: default to keeping old values
    for metric in METRIC_COLS:
        old_col = f'{metric}_old'
        new_col = f'{metric}_new'
        selected_col = f'{metric}_selected_source'  # 'old', 'new', or 'custom'
        selected_val_col = f'{metric}_selected_value'
        
        merged[selected_col] = 'old'  # Default to old
        merged[selected_val_col] = merged[old_col]
    
    return merged


@app.route('/')
def index():
    """Serve the main editor page."""
    return render_template('merger.html')


@app.route('/api/upload', methods=['POST'])
def upload_baselines():
    """Handle baseline CSV file uploads."""
    files = request.files
    
    if 'old_baseline' not in files or 'new_baseline' not in files:
        return jsonify({'error': 'Both old and new baseline files required'}), 400
    
    try:
        old_file = files['old_baseline']
        new_file = files['new_baseline']
        
        # Load baselines
        old_baseline = load_baseline(old_file.stream)
        new_baseline = load_baseline(new_file.stream)
        
        # Store in session state
        merge_state['old_baseline'] = old_baseline
        merge_state['new_baseline'] = new_baseline
        merge_state['merged_rows'] = merge_baselines(old_baseline, new_baseline)
        
        # Prepare summary for frontend
        merged = merge_state['merged_rows']
        summary = {
            'total_rows': len(merged),
            'only_old': int((merged['_merge'] == 'left_only').sum()),
            'only_new': int((merged['_merge'] == 'right_only').sum()),
            'both': int((merged['_merge'] == 'both').sum()),
        }
        
        return jsonify(summary), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/grids', methods=['GET'])
def get_grids():
    """Get grouped grid data for display."""
    if merge_state['merged_rows'] is None:
        return jsonify({'error': 'No baseline loaded'}), 400
    
    metric_mode = request.args.get('mode', 'power')
    merged = merge_state['merged_rows']
    
    # Get unique frequencies
    frequencies = merged['receiver_frequency'].dropna().unique()
    
    grids = []
    for freq in frequencies:
        df_freq = merged[merged['receiver_frequency'] == freq]
        
        # For now, group by receiver prefix (CC, LW)
        for prefix in ['CC', 'LW']:
            df_subset = df_freq[
                df_freq['receiver'].astype(str).str.startswith(prefix)
            ]
            
            if df_subset.empty:
                continue
            
            # Create grid structure: group by transmitter and receiver with channels
            grid_data = {
                'frequency': str(freq),
                'prefix': prefix,
                'rows': []
            }
            
            # Group by transmitter and receiver for grid layout
            for _, row in df_subset.iterrows():
                tx_key = format_display_key(
                    row['transmitter'],
                    row['transmitter_channel'],
                    row['transmitter_serial_number'],
                )
                rx_key = format_display_key(
                    row['receiver'],
                    row['receiver_channel'],
                    row['receiver_serial_number'],
                )
                
                metrics = {}
                for metric in POWER_METRICS if metric_mode == 'power' else QUALITY_METRICS:
                    old_val = row.get(f'{metric}_old')
                    new_val = row.get(f'{metric}_new')
                    selected_src = row.get(f'{metric}_selected_source', 'old')
                    selected_val = row.get(f'{metric}_selected_value')
                    
                    metrics[metric] = {
                        'old': None if pd.isna(old_val) else float(old_val),
                        'new': None if pd.isna(new_val) else float(new_val),
                        'selected_source': selected_src,
                        'selected_value': None if pd.isna(selected_val) else float(selected_val),
                    }
                
                grid_data['rows'].append({
                    'tx_key': tx_key,
                    'rx_key': rx_key,
                    'metrics': metrics,
                    'merge_status': row['_merge'],
                    'identifier': {
                        'transmitter': row['transmitter'],
                        'transmitter_channel': None if pd.isna(row['transmitter_channel']) else int(row['transmitter_channel']),
                        'transmitter_serial_number': row['transmitter_serial_number'],
                        'receiver': row['receiver'],
                        'receiver_channel': None if pd.isna(row['receiver_channel']) else int(row['receiver_channel']),
                        'receiver_serial_number': row['receiver_serial_number'],
                        'receiver_frequency': row['receiver_frequency'],
                    },
                })
            
            grids.append(grid_data)
    
    return jsonify({'grids': grids, 'mode': metric_mode}), 200


@app.route('/api/set_metric', methods=['POST'])
def set_metric():
    """Update a single metric selection for a row."""
    data = request.get_json()
    
    if merge_state['merged_rows'] is None:
        return jsonify({'error': 'No baseline loaded'}), 400
    
    try:
        identifier = data.get('identifier')
        metric = data.get('metric')
        source = data.get('source')  # 'old', 'new', or 'custom'
        custom_value = data.get('custom_value')  # Only if source == 'custom'
        
        merged = merge_state['merged_rows']
        
        if not identifier:
            return jsonify({'error': 'Missing row identifier in request'}), 400

        rx_name = identifier.get('receiver')
        rx_channel = identifier.get('receiver_channel')
        rx_serial = identifier.get('receiver_serial_number')
        tx_name = identifier.get('transmitter')
        tx_channel = identifier.get('transmitter_channel')
        tx_serial = identifier.get('transmitter_serial_number')
        frequency = identifier.get('receiver_frequency')

        if metric not in METRIC_COLS:
            return jsonify({'error': f'Invalid metric: {metric}'}), 400
        if source not in ('old', 'new', 'custom'):
            return jsonify({'error': f'Invalid source: {source}'}), 400

        rx_channel = pd.to_numeric(pd.Series([rx_channel]), errors='coerce').astype('Int64').iloc[0]
        tx_channel = pd.to_numeric(pd.Series([tx_channel]), errors='coerce').astype('Int64').iloc[0]
        
        mask = (
            (merged['receiver'] == rx_name) &
            (merged['receiver_channel'] == rx_channel) &
            (merged['receiver_serial_number'] == rx_serial) &
            (merged['transmitter'] == tx_name) &
            (merged['transmitter_channel'] == tx_channel) &
            (merged['transmitter_serial_number'] == tx_serial) &
            (merged['receiver_frequency'] == frequency)
        )
        
        if not mask.any():
            return jsonify({'error': 'Row not found'}), 404
        
        idx = merged[mask].index[0]
        
        # Update selection
        merged.loc[idx, f'{metric}_selected_source'] = source
        
        if source == 'custom':
            merged.loc[idx, f'{metric}_selected_value'] = float(custom_value)
        else:
            # Use old or new value
            val = merged.loc[idx, f'{metric}_{source}']
            merged.loc[idx, f'{metric}_selected_value'] = val
        
        return jsonify({'success': True}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/toggle_mode', methods=['POST'])
def toggle_mode():
    """Toggle between power and quality metric modes."""
    data = request.get_json()
    mode = data.get('mode')  # 'power' or 'quality'
    
    if mode not in ['power', 'quality']:
        return jsonify({'error': 'Invalid mode'}), 400
    
    merge_state['metric_mode'] = mode
    return jsonify({'mode': mode}), 200


@app.route('/api/export', methods=['GET'])
def export_merged():
    """Export the merged baseline as a CSV file."""
    if merge_state['merged_rows'] is None:
        return jsonify({'error': 'No baseline loaded'}), 400
    
    try:
        merged = merge_state['merged_rows']
        
        # Build output dataframe with selected values
        output_df = merged[KEY_COLS].copy()
        
        for metric in METRIC_COLS:
            # Use selected_value if available, otherwise old
            col_name = f'{metric}_selected_value'
            fallback_name = f'{metric}_old'
            if col_name in merged.columns:
                output_df[metric] = merged[col_name]
            elif fallback_name in merged.columns:
                output_df[metric] = merged[fallback_name]
            else:
                output_df[metric] = pd.NA
        
        # Remove the <NA> markers and restore nulls where appropriate
        for col in ['transmitter', 'transmitter_serial_number']:
            output_df[col] = output_df[col].replace('<NA>', pd.NA)
        
        # Write to CSV buffer
        csv_buffer = StringIO()
        output_df.to_csv(csv_buffer, index=False)
        csv_content = csv_buffer.getvalue()
        
        # Convert to BytesIO for sending
        byte_buffer = BytesIO(csv_content.encode('utf-8'))
        
        # Return as downloadable
        return send_file(
            byte_buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'merged_baseline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
