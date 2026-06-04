#! /usr/bin/env python3
import pandas as pd
import math
import argparse
import glob
import os

POWER_MIN_VALID = -120
POWER_MAX_VALID = 20

### THIS FUNCTION IS DEPRECATED ###
# Use compute_baseline_from_es.py instead, which computes baseline metrics directly from Elasticsearch API, which is significantly faster.
def compute_baseline(csv_files, output_file="baseline_results.csv"):
    if len(csv_files) == 0:
        print("No CSV files given")
        return

    # Load and concatenate multiple CSV files
    # try to read channel columns as pandas nullable integers (Int64)
    df_list = [
        pd.read_csv(file, dtype={'transmitter_channel': 'Int64', 'receiver_channel': 'Int64'}, na_values=['null', 'None', ''])
        for file in csv_files
    ]
    df = pd.concat(df_list, ignore_index=True)
    
    # Filter rows where either 'power' or 'quality' is defined (non-null)
    df_filtered = df.dropna(subset=['power', 'quality'], how='all')
    
    # Convert power and quality to numeric (if not already)
    df_filtered['power'] = pd.to_numeric(df_filtered['power'], errors='coerce')
    df_filtered['quality'] = pd.to_numeric(df_filtered['quality'], errors='coerce')
    # Ensure channel columns are nullable integers after coercion
    df_filtered['transmitter_channel'] = pd.to_numeric(df_filtered['transmitter_channel'], errors='coerce').astype('Int64')
    df_filtered['receiver_channel'] = pd.to_numeric(df_filtered['receiver_channel'], errors='coerce').astype('Int64')
    
    # Cap extreme dBm values to reasonable range for radio measurements
    # Typical dBm range: -120 (extremely weak) to 20 (max power)
    power_min_valid = POWER_MIN_VALID
    power_max_valid = POWER_MAX_VALID
    original_count = len(df_filtered)
    df_filtered = df_filtered[
        (df_filtered['power'].isna()) | 
        ((df_filtered['power'] >= power_min_valid) & (df_filtered['power'] <= power_max_valid))
    ]
    filtered_count = original_count - len(df_filtered)
    if filtered_count > 0:
        percentage = (filtered_count / original_count) * 100
        print(f"Filtered {filtered_count} out of {original_count} rows ({percentage:.2f}%) with power values outside valid range ({power_min_valid} to {power_max_valid} dBm)")
    
    # Separate special baseline cases where transmitter is null
    df_special = df_filtered[df_filtered['transmitter'].isnull() & df_filtered['transmitter_serial_number'].isnull()]
    df_normal = df_filtered[~(df_filtered['transmitter'].isnull() & df_filtered['transmitter_serial_number'].isnull())]
    
    # Group by transmitter-receiver pair for normal cases
    grouped_normal = df_normal.groupby(['transmitter', 'transmitter_channel', 'transmitter_serial_number', 'receiver', 'receiver_channel', 'receiver_serial_number', 'receiver_frequency'])
    
    # DEBUG: Print specific transmitter-receiver pair (set debug_enabled to True to enable)
    debug_enabled = False  # Set to True to see debug output
    if debug_enabled:
        # Specify the pair you want to inspect
        debug_tx = 'CC2'  # Change this to your transmitter name
        debug_tx_channel = 0  # Change this to your transmitter channel if needed
        debug_rx = 'CC1'  # Change this to your receiver name
        debug_rx_channel = 1  # Change this to your receiver channel if needed
        debug_data = df_normal[
            (df_normal['transmitter'] == debug_tx) & 
            (df_normal['transmitter_channel'] == debug_tx_channel) & 
            (df_normal['receiver'] == debug_rx) & 
            (df_normal['receiver_channel'] == debug_rx_channel)
        ]
        if not debug_data.empty:
            print(f"\n=== DEBUG: Data for {debug_tx} -> {debug_rx} ===")
            print(debug_data[['transmitter', 'transmitter_channel', 'receiver', 'receiver_channel', 'power', 'quality']])
            print(f"Total rows: {len(debug_data)}")
            print(f"Power mean: {debug_data['power'].mean()}")
            print(f"Power std: {debug_data['power'].std()}")
            print(f"\nPower value statistics:")
            print(f"  Min: {debug_data['power'].min()}")
            print(f"  Max: {debug_data['power'].max()}")
            print(f"  Median: {debug_data['power'].median()}")
            print(f"  25th percentile: {debug_data['power'].quantile(0.25)}")
            print(f"  75th percentile: {debug_data['power'].quantile(0.75)}")
            print(f"\nValue counts of unique power values (top 20):")
            print(debug_data['power'].value_counts().head(20))
        else:
            print(f"\n=== DEBUG: No data found for {debug_tx} -> {debug_rx} ===")
    
    # Compute baseline metrics for normal cases
    baseline_normal = grouped_normal.agg(
        power_mean=('power', 'mean'),
        power_std=('power', 'std'),
        quality_mean=('quality', 'mean'),
        quality_std=('quality', 'std')
    ).reset_index()
    
    # Group by receiver only for special baseline cases
    grouped_special = df_special.groupby(['receiver', 'receiver_channel', 'receiver_serial_number', 'receiver_frequency'])
    
    # Compute baseline metrics for special cases
    baseline_special = grouped_special.agg(
        power_mean=('power', 'mean'),
        power_std=('power', 'std'),
        quality_mean=('quality', 'mean'),
        quality_std=('quality', 'std')
    ).reset_index()
    
    # Add null transmitter columns to match format
    baseline_special['transmitter'] = None
    baseline_special['transmitter_serial_number'] = None
    
    # Combine both baseline dataframes
    baseline_df = pd.concat([baseline_normal, baseline_special], ignore_index=True)
    
    # Save the baseline metrics to a CSV file
    if output_file is not None:
        baseline_df.to_csv(output_file, index=False)
        print(f"Baseline metrics saved to {output_file}")

    return baseline_df


dtypes = {
    'transmitter_channel': 'Int64',
    'receiver_channel': 'Int64',
    'transmitter_serial_number': 'string',
    'receiver_serial_number': 'string',
    'receiver_frequency': 'string',
    'transmitter': 'string',
    'receiver': 'string',
}

# deviation = # of standard deviations within which a data point is considered close enough to not be an outlier
# threshold = % of data that must be outliers in order to consider the data abnormal
def check_baseline(test_file, baseline_file, output_file="test_results.csv", deviation=2, threshold=10):
    # Load test data and baseline
    # read test/baseline and coerce channel columns to nullable integers
    test_df = pd.read_csv(test_file, dtype=dtypes)
    baseline_df = pd.read_csv(baseline_file, dtype=dtypes)

    # Fill NaN values for control group test (no TX)
    test_df['transmitter'] = test_df['transmitter'].fillna("None")
    test_df['transmitter_channel'] = test_df['transmitter_channel'].fillna(-1)
    test_df['transmitter_serial_number'] = test_df['transmitter_serial_number'].fillna("None")
    baseline_df['transmitter'] = baseline_df['transmitter'].fillna("None")
    baseline_df['transmitter_channel'] = baseline_df['transmitter_channel'].fillna(-1)
    baseline_df['transmitter_serial_number'] = baseline_df['transmitter_serial_number'].fillna("None")

    '''
    # Print dtypes
    print("Test DataFrame dtypes:")
    print(test_df.dtypes)
    print("\nBaseline DataFrame dtypes:")
    print(baseline_df.dtypes)
    '''

    # Convert power and quality to numeric
    test_df['power'] = pd.to_numeric(test_df['power'], errors='coerce')
    test_df['quality'] = pd.to_numeric(test_df['quality'], errors='coerce')

    # Keep rows where at least one metric exists; drop only when both are NaN
    test_df = test_df.dropna(subset=['power', 'quality'], how='all')

    # Apply same power limits used in baseline computation
    test_original_count = len(test_df)
    test_df = test_df[
        (test_df['power'].isna()) |
        ((test_df['power'] >= POWER_MIN_VALID) & (test_df['power'] <= POWER_MAX_VALID))
    ]
    test_filtered_count = test_original_count - len(test_df)
    if test_filtered_count > 0:
        test_percentage = (test_filtered_count / test_original_count) * 100
        print(
            f"Filtered {test_filtered_count} out of {test_original_count} test rows "
            f"({test_percentage:.2f}%) with power values outside valid range "
            f"({POWER_MIN_VALID} to {POWER_MAX_VALID} dBm)"
        )

    # Merge test data with baseline (left join so all test rows are kept)
    merged_df = test_df.merge(baseline_df, on=['transmitter', 'transmitter_channel', 'transmitter_serial_number', 'receiver', 'receiver_channel', 'receiver_serial_number', 'receiver_frequency'], how='left')

    # Check for deviations. If baseline mean/std are missing (NaN) the comparison will be NaN -> fill with False
    merged_df['power_outside_baseline'] = (abs(merged_df['power'] - merged_df['power_mean']) > deviation * merged_df['power_std']).fillna(False)
    merged_df['quality_outside_baseline'] = (abs(merged_df['quality'] - merged_df['quality_mean']) > deviation * merged_df['quality_std']).fillna(False)

    # Aggregate results at the group level with percentage-based threshold.
    # Important: group ONLY by identity fields. Previously grouping by baseline columns (power_mean/power_std)
    # caused rows with missing baseline values (NaN) to be dropped, because groupby drops NA keys.
    id_cols = ['transmitter', 'transmitter_channel', 'transmitter_serial_number', 'receiver', 'receiver_channel', 'receiver_serial_number', 'receiver_frequency']
    grouped_results = merged_df.groupby(id_cols).agg(
        power_outlier_count=('power_outside_baseline', 'sum'),
        quality_outlier_count=('quality_outside_baseline', 'sum'),
        power_total_count=('power', 'count'),
        quality_total_count=('quality', 'count'),
        test_power_mean=('power', 'mean'),
        test_power_std=('power', 'std'),
        baseline_power_mean=('power_mean', 'first'),
        baseline_power_std=('power_std', 'first'),
        test_quality_mean=('quality', 'mean'),
        test_quality_std=('quality', 'std'),
        baseline_quality_mean=('quality_mean', 'first'),
        baseline_quality_std=('quality_std', 'first')
    ).reset_index()

    '''
    # DEBUG: print only rows matching the specific test case
    import sys
    cond = (
        (grouped_results['transmitter'] == 'LW4') &
        (grouped_results['transmitter_channel'] == 0) &
        (grouped_results['receiver'] == 'LW2') &
        (grouped_results['receiver_channel'] == 1) &
        (grouped_results['receiver_frequency'] == '3.32G')
    )
    debug_df = grouped_results[cond]
    if debug_df.empty:
        print("No matching rows found")
    else:
        # CSV to stdout (exact CSV lines) and human-readable to stderr
        debug_df.to_csv(sys.stdout, index=False)
        print("\n=== Debug (compact) ===", file=sys.stderr)
        print(debug_df.to_string(index=False), file=sys.stderr)
    '''
    
    grouped_results['power_outlier_percentage'] = (
        grouped_results['power_outlier_count'] /
        grouped_results['power_total_count'].replace(0, pd.NA)
    ) * 100
    grouped_results['quality_outlier_percentage'] = (
        grouped_results['quality_outlier_count'] /
        grouped_results['quality_total_count'].replace(0, pd.NA)
    ) * 100
    grouped_results['power_outlier_percentage'] = grouped_results['power_outlier_percentage'].fillna(0)
    grouped_results['quality_outlier_percentage'] = grouped_results['quality_outlier_percentage'].fillna(0)
    
    grouped_results['power_deviation'] = grouped_results['power_outlier_percentage'] > threshold
    grouped_results['quality_deviation'] = grouped_results['quality_outlier_percentage'] > threshold
    
    # Save results
    grouped_results.to_csv(output_file, index=False)
    print(f"Test results saved to {output_file}")
    return grouped_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute and check baseline metrics for radio test data.")
    subparsers = parser.add_subparsers(dest="command")
    
    # Compute baseline sub-command
    parser_baseline = subparsers.add_parser("compute", help="Compute baseline metrics from multiple CSV files.")
    parser_baseline.add_argument("--folder-path", help="Path to the folder containing radio test CSV files to compute baseline from", required=True)
    parser_baseline.add_argument("--output-file", help="Path to the output file", required=False, default="baseline_results.csv")
    
    # Check baseline sub-command
    parser_check = subparsers.add_parser("check", help="Check test data against baseline metrics.")
    parser_check.add_argument("--test-file", help="Path to the test CSV file", required=True)
    parser_check.add_argument("--baseline-file", help="Path to the baseline CSV file", required=True)
    parser_check.add_argument("--output-file", help="Path to the output file", required=False, default="test_results.csv")
    parser_check.add_argument("--deviation", help="# of standard deviations within which a data point is considered close enough to not be an outlier", type=float, required=False, default=2.0)
    parser_check.add_argument("--threshold", help="%% of data that must be outliers in order to consider the data abnormal", type=float, required=False, default=10.0)
    
    args = parser.parse_args()
    
    if args.command == "compute":
        # Get all CSV files in the folder
        csv_files = glob.glob(os.path.join(args.folder_path, "*.csv"))
        compute_baseline(csv_files, args.output_file)
    elif args.command == "check":
        check_baseline(args.test_file, args.baseline_file, output_file=args.output_file, deviation=args.deviation, threshold=args.threshold)
