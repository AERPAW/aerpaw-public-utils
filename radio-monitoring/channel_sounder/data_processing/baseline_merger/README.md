# Baseline Merger Web Application

An interactive Flask web app for merging and editing baseline CSV files. Allows side-by-side comparison of old and new baselines with per-row, per-metric selection and override capabilities.

## Features

- **Upload Two Baselines**: Load an old (reference) baseline and a new (candidate) baseline for comparison
- **Side-by-Side Comparison**: View both old and new data side-by-side for each transmitter-receiver pair
- **Metric Toggle**: Switch between viewing Power (mean/std) and Quality (mean/std) metrics
- **Defaults**: By default, keeps old baseline values
- **Per-Metric Selection**: For each metric, choose to keep old value, new value, or enter a custom value
- **Export**: Download the merged baseline as a CSV file

## Requirements

- Python 3.9+
- Flask 3.1+
- pandas 2.x

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Start the Server

Option 1: Use the launcher script

```bash
./start_baseline_merger.sh
```

Option 2: Manually start

```bash
python3 baseline_merger_app.py
```

The app starts on `http://127.0.0.1:5000`.

### Using the Web Interface

1. **Upload Baselines**
   - Select an "Old Baseline" CSV file (the reference baseline to keep by default)
   - Select a "New Baseline" CSV file (the alternative values to choose from)
   - Click "Load & Merge"

2. **Review Merge Summary**
   - The app shows how many rows are in the old baseline only, new baseline only, or both
   - Rows where values exist in both are editable

3. **Toggle Metrics**
   - Use the "Power" and "Quality" buttons to switch between metric types
   - **Power**: power_mean and power_std
   - **Quality**: quality_mean and quality_std

4. **Edit Values**
   - For each metric in each row:
     - **Old**: Click to select the old baseline value
     - **New**: Click to select the new baseline value (if available)
     - **Custom**: Toggle custom mode and enter a specific value
   - Changes are saved automatically

5. **Export**
   - Click "Download Merged Baseline" to save the merged CSV file

## Baseline CSV Format

The app expects baseline CSV files with the following structure (produced by `compute_baseline_from_es.py`):

### Key Columns (identify a link):
- `transmitter`
- `transmitter_channel`
- `transmitter_serial_number`
- `receiver`
- `receiver_channel`
- `receiver_serial_number`
- `receiver_frequency`

### Metric Columns (values to compare/edit):
- `power_mean` - Mean signal power in dBm
- `power_std` - Standard deviation of power
- `quality_mean` - Mean link quality
- `quality_std` - Standard deviation of quality

### Special Cases:
- Rows with `transmitter = <NA>` are control/background measurements
- Valid dBm power range: -120 to 20 (enforced by downstream baseline checking)

## Example Workflow

```bash
# 1. Take existing baseline (baseline_results.csv)
# Found at /home/aerpawops/channel_sounder/data_processing/baseline_results.csv

# 2. Compute a new baseline (e.g., new test period)
python3 compute_baseline_from_es.py --start-time '2026-04-01 00:00' --end-time '2026-04-08 23:59' --output-file new_baseline.csv

# 3. Start the merger app and load both files
./start_baseline_merger.sh
# Open http://127.0.0.1:5000
# Upload baseline_results.csv and new_baseline.csv

# 4. Review and edit merged values
# - Toggle power/quality as needed
# - Select old/new/custom for each metric

# 5. Export merged baseline
# - Download merged_baseline.csv

# 6. Use the merged baseline with existing tools
## Test data can be downloaded using ../import_data.py
python3 check_baseline.py check --test-file test_data.csv --baseline-file merged_baseline.csv
python3 compare_baselines.py --old-baseline old_baseline.csv --new-baseline merged_baseline.csv --threshold 2.0
python3 plot_results.py --results-file test_results.csv --output-dir ./plots
```

## Developer Info (API Endpoints)

All endpoints return JSON responses.

### POST `/api/upload`
**Request**: Multipart form with `old_baseline` and `new_baseline` files

**Response**:
```json
{
  "total_rows": 1234,
  "only_old": 50,
  "only_new": 30,
  "both": 1154
}
```

### GET `/api/grids?mode={power|quality}`
**Response**: Grid data organized by frequency and prefix

### POST `/api/set_metric`
**Request**:
```json
{
   "identifier": {
      "transmitter": "CC1",
      "transmitter_channel": 0,
      "transmitter_serial_number": "31EABF2",
      "receiver": "CC2",
      "receiver_channel": 1,
      "receiver_serial_number": "31EAC20",
      "receiver_frequency": "3.32G"
   },
  "metric": "power_mean",
  "source": "old|new|custom",
  "custom_value": 99.99
}
```

### POST `/api/export`
**Response**: Binary CSV file (application/csv)

## Implementation Notes

- Built with Flask 3.1+ for Python 3.9+ compatibility
- Uses pandas for CSV manipulation and merging
- Frontend is vanilla JavaScript with CSS Grid for responsive UI
- In-memory state management (no database); session ends when server stops
- All merge operations are non-destructive (original CSVs not modified)
- Null transmitter values (<NA>) are preserved during merge and export

## Troubleshooting

**Port Already in Use**:
```bash
# Kill the existing process on port 5000
lsof -ti :5000 | xargs kill -9

# Or use a different port by editing baseline_merger_app.py:
# Change: app.run(debug=True, host='127.0.0.1', port=5000)
# To:     app.run(debug=True, host='127.0.0.1', port=5001)
```

**File Upload Errors**:
- Ensure both CSV files have the correct baseline format
- Check that key columns are present: transmitter, receiver, transmitter_channel, receiver_channel, transmitter_serial_number, receiver_serial_number, receiver_frequency
- Check that metric columns exist: power_mean, power_std, quality_mean, quality_std

## Files

- `baseline_merger_app.py` - Flask backend application
- `start_baseline_merger.sh` - Launcher script
- `templates/merger.html` - HTML interface template
- `static/style.css` - CSS styling
- `static/merger.js` - JavaScript frontend logic
- `README.md` - This documentation
