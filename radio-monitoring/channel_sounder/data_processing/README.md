# Channel Sounder Data Processing

This directory contains utilities that transform channel-sounder logs into baseline comparisons and visual reports.

## Dependencies

Install required Python packages in your virtual environment:

```bash
pip install pandas matplotlib seaborn elasticsearch pytz tabulate
```

For email reporting, set environment variables:

- `GMAIL_ADDRESS`
- `GMAIL_APP_PW`

## Typical Workflow

1. Export test-window logs from Elasticsearch (`import_data.py`).
2. Compare exported logs against a baseline (`check_baseline.py check`).
3. Render heatmap images (`plot_results.py`).
4. Optionally email outputs (`send_email.py`).

For baseline creation and maintenance:

1. Build baseline from many CSV files (`check_baseline.py baseline`) or directly from Elasticsearch (`compute_baseline_from_es.py`).
2. Compare old/new baseline files (`compare_baselines.py`).
3. Optionally curate baseline values with `baseline_merger/`.

## Script Reference

### `import_data.py`

Fetch channel-sounder logs from Elasticsearch and save to CSV.

Usage:

```bash
./import_data.py \
  --start-time "2026-06-01 00:00" \
  --end-time "2026-06-01 23:59" \
  --output-file temp_today_data.csv \
  --host https://10.0.0.50:9200 \
  --index channel_sounder_logging \
  --cert-file ./http_ca.crt
```

Options:

- `--start-time` / `--end-time`: interpreted as US/Eastern time (`YYYY-MM-DD HH:MM`).
- `--output-file`: output CSV path.
- `--host`: Elasticsearch URL.
- `--index`: Elasticsearch index name.
- `--cert-file`: CA certificate file.
- `--username` / `--password`: optional auth overrides.

If `--username` and `--password` are omitted, environment variables `ES_USERNAME` and `ES_PASSWORD` are used when present.

### `check_baseline.py`

Contains two subcommands:

- Baseline computation from local CSV set.
- Baseline check of one test CSV against a baseline CSV.

Baseline computation:

```bash
./check_baseline.py baseline --folder-path ./historical_csv --output-file baseline_results.csv
```

Baseline check:

```bash
./check_baseline.py check \
  --test-file temp_today_data.csv \
  --baseline-file baseline_results.csv \
  --output-file test_results.csv \
  --deviation 2 \
  --threshold 10
```

### `compute_baseline_from_es.py`

Compute baseline metrics directly from Elasticsearch aggregations.

```bash
./compute_baseline_from_es.py \
  --start-time "2026-05-01 00:00" \
  --end-time "2026-05-31 23:59" \
  --output-file baseline_results.csv \
  --host https://10.0.0.50:9200 \
  --index channel_sounder_logging \
  --cert-file ./http_ca.crt
```

`--username` and `--password` are optional and may be provided by `ES_USERNAME` and `ES_PASSWORD` environment variables.

### `compare_baselines.py`

Highlight rows where baseline metrics changed by more than a threshold.

```bash
./compare_baselines.py --old-baseline baseline_old.csv --new-baseline baseline_new.csv --threshold 2.0
```

### `plot_results.py`

Generate split-cell heatmaps from `check_baseline.py check` output.

```bash
./plot_results.py --results-file test_results.csv --output-dir ./plots
```

Cell layout:

- Top half: test mean power.
- Bottom half: baseline mean power.
- Circle overlay: outlier percentage.

### `plot_single_dataset.py`

Debug/inspection plots for one dataset (baseline or raw log).

```bash
./plot_single_dataset.py --baseline-file baseline_results.csv --type heatmap
```

or

```bash
./plot_single_dataset.py --log-file temp_today_data.csv --type boxplot
```

### `send_email.py`

Send report email with attachments.

```bash
./send_email.py \
  --recipients recipients.txt \
  --debug-msg "manual rerun" \
  ./plots/power_heatmap_*.png test_results.csv
```

The attached CSV should be a baseline-check results file so alert/OK status can be derived from `power_deviation` fields.

## Troubleshooting

- Empty CSV export:
  - Confirm time window and timezone assumptions.
  - Confirm index contains documents in selected window.
- SSL/auth failures:
  - Validate `--cert-file`, username/password, and host URL.
- No plots generated:
  - Confirm `test_results.csv` has expected columns from baseline-check output.
