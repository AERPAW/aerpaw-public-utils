#! /usr/bin/env python3

import argparse
import pandas as pd

KEY_COLS = [
    "transmitter",
    "transmitter_channel",
    "transmitter_serial_number",
    "receiver",
    "receiver_channel",
    "receiver_serial_number",
    "receiver_frequency",
]

METRIC_COLS = ["power_mean", "power_std", "quality_mean", "quality_std"]


def load_baseline(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    for col in KEY_COLS + METRIC_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    # Normalize key columns so special rows (blank TX fields) line up consistently
    for col in ["transmitter", "transmitter_serial_number", "receiver", "receiver_serial_number", "receiver_frequency"]:
        df[col] = df[col].astype("string").fillna("<NA>")

    for col in ["transmitter_channel", "receiver_channel"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in METRIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[KEY_COLS + METRIC_COLS].copy()


def compare_baselines(old_path: str, new_path: str) -> pd.DataFrame:
    old_df = load_baseline(old_path)
    new_df = load_baseline(new_path)

    merged = old_df.merge(new_df, on=KEY_COLS, how="outer", suffixes=("_old", "_new"), indicator=True)

    for metric in METRIC_COLS:
        old_col = f"{metric}_old"
        new_col = f"{metric}_new"
        delta_col = f"{metric}_delta"
        pct_col = f"{metric}_pct_change"

        merged[delta_col] = merged[new_col] - merged[old_col]
        merged[pct_col] = (merged[delta_col] / merged[old_col].replace(0, pd.NA)) * 100

    return merged


def main():
    parser = argparse.ArgumentParser(description="Compare two baseline CSV files and compute per-group metric deltas.")
    parser.add_argument("--old-baseline", required=True, help="Path to baseline A (reference/older)")
    parser.add_argument("--new-baseline", required=True, help="Path to baseline B (candidate/newer)")
    parser.add_argument(
        "--threshold",
        type=float,
        required=True,
        help="Absolute delta threshold. Print rows where any metric change exceeds this value.",
    )
    args = parser.parse_args()

    comparison_df = compare_baselines(args.old_baseline, args.new_baseline)

    only_old = (comparison_df["_merge"] == "left_only").sum()
    only_new = (comparison_df["_merge"] == "right_only").sum()
    both = (comparison_df["_merge"] == "both").sum()

    print(f"Matched groups: {both}")
    print(f"Only in old baseline: {only_old}")
    print(f"Only in new baseline: {only_new}")

    matched_df = comparison_df[comparison_df["_merge"] == "both"].copy()
    delta_cols = [f"{metric}_delta" for metric in METRIC_COLS]
    abs_delta_cols = [f"abs_{col}" for col in delta_cols]

    for delta_col, abs_col in zip(delta_cols, abs_delta_cols):
        matched_df[abs_col] = matched_df[delta_col].abs()

    change_mask = False
    for abs_col in abs_delta_cols:
        change_mask = change_mask | (matched_df[abs_col] > args.threshold)

    changed_df = matched_df[change_mask].copy()

    print(f"\nThreshold: {args.threshold}")
    print(f"Changed rows above threshold: {len(changed_df)}")

    if changed_df.empty:
        print("No rows exceeded threshold.")
        return

    display_cols = (
        KEY_COLS
        + delta_cols
        + [f"{metric}_old" for metric in METRIC_COLS]
        + [f"{metric}_new" for metric in METRIC_COLS]
    )

    changed_df["max_abs_delta"] = changed_df[abs_delta_cols].max(axis=1)
    changed_df = changed_df.sort_values("max_abs_delta", ascending=False)
    print("\nRows where any metric change exceeds threshold:")
    print(changed_df[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()
