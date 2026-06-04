#! /usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.colors import Normalize, ListedColormap
import seaborn as sns
import numpy as np
import argparse
import os

def plot_heatmap_with_outliers(input_file, output_dir):
    # Load the test results file
    df = pd.read_csv(input_file)

    # Replace NaN transmitters with "None" for special cases
    df['transmitter'] = df['transmitter'].fillna("None")
    df['transmitter_channel'] = df['transmitter_channel'].fillna("None")

    # Get unique frequencies
    frequencies = df["receiver_frequency"].dropna().unique()

    for freq in frequencies:
        # Filter data for the specific frequency
        df_freq = df[df["receiver_frequency"] == freq]

        # Loop for subsets based on transmitter and receiver prefixes
        for prefix in ["CC", "LW"]:
            # Filter data where receiver start with the prefix
            df_subset = df_freq[
                df_freq["receiver"].str.startswith(prefix)
            ]

            if df_subset.empty:
                continue  # Skip if no data matches the condition

            # Group by transmitter-receiver pair and calculate mean power and outlier percentage
            df_grouped = df_subset.groupby(
                ["transmitter", "transmitter_channel", "receiver", "receiver_channel", "test_power_mean", "baseline_power_mean"]
            ).agg({
                "power_outlier_percentage": "mean",
                "power_deviation": "mean"
            }).reset_index()

            # Pivot the dataframe to create an adjacency matrix for power_mean
            adj_matrix_test_power = df_grouped.pivot(
                index=["transmitter", "transmitter_channel"],
                columns=["receiver", "receiver_channel"],
                values="test_power_mean"
            )

            # Pivot the dataframe to create an adjacency matrix for baseline power
            adj_matrix_baseline_power = df_grouped.pivot(
                index=["transmitter", "transmitter_channel"],
                columns=["receiver", "receiver_channel"],
                values="baseline_power_mean"
            )

            # Pivot the dataframe to create an adjacency matrix for outlier percentage
            adj_matrix_outliers = df_grouped.pivot(
                index=["transmitter", "transmitter_channel"],
                columns=["receiver", "receiver_channel"],
                values="power_outlier_percentage"
            )

            # Sort the rows and columns alphabetically
            adj_matrix_test_power = adj_matrix_test_power.sort_index(axis=0).sort_index(axis=1)
            adj_matrix_baseline_power = adj_matrix_baseline_power.sort_index(axis=0).sort_index(axis=1)
            adj_matrix_outliers = adj_matrix_outliers.sort_index(axis=0).sort_index(axis=1)

            # Plot the heatmap
            fig = plt.figure(figsize=(14, 10), dpi=175)
            # Since we are manually plotting the colors later, use a white colormap for the heatmap background
            white_cmap = ListedColormap(["white"])
            ax = sns.heatmap(
                adj_matrix_test_power,
                annot=False,  # Disable annotations since we'll add custom ones
                cmap=white_cmap,
                cbar=False, # Also disable colorbar because we'll add custom ones
                linewidths=0.8,
                linecolor="gray",
                xticklabels=adj_matrix_test_power.columns,
                yticklabels=adj_matrix_test_power.index,
            )

            # Add a colorbar for outlier percentage and power measurements
            norm = Normalize(vmin=0, vmax=100)  # Scale from 0% to 100%
            sm = plt.cm.ScalarMappable(cmap="RdYlGn_r", norm=norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=plt.gca(), orientation="vertical", pad=0.02)
            cbar.set_label("Outlier Percentage (%)", fontsize=12)
            cbar.ax.tick_params(labelsize=10)

            norm = Normalize(vmin=-60, vmax=0)  # Scale from -60 dBm to 0 dBm
            sm = plt.cm.ScalarMappable(cmap="magma", norm=norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=plt.gca(), orientation="vertical", pad=0.02)
            cbar.set_label("Power Measurement (dBm)", fontsize=12)
            cbar.ax.tick_params(labelsize=10)

            # Overlay rectangles for test_mean and baseline_mean values
            # Use the index/column MultiIndex to detect same-node (transmitter == receiver)
            row_labels = list(adj_matrix_test_power.index)      # list of (transmitter, transmitter_channel)
            col_labels = list(adj_matrix_test_power.columns)    # list of (receiver, receiver_channel)

            # Compute scalable font size
            nrows, ncols = adj_matrix_test_power.shape
            bbox = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
            width, height = bbox.width * fig.dpi, bbox.height * fig.dpi
            cell_height = height / nrows
            cell_width = width / ncols
            font_size_base = min(cell_height, cell_width)

            for (i, j), val in np.ndenumerate(adj_matrix_test_power.values):
                # get corresponding labels
                row_label = row_labels[i]
                col_label = col_labels[j]
                transmitter_name = row_label[0]
                receiver_name = col_label[0]

                # If same node (name match) gray out full square and skip other annotations
                x, y = j, i
                if transmitter_name == receiver_name:
                    plt.gca().add_patch(plt.Rectangle(
                        (x + 0.02, y + 0.02), 0.96, 0.96,
                        color="lightgray", alpha=1.0, zorder=3
                    ))
                    continue

                baseline_val = adj_matrix_baseline_power.values[i, j] if not np.isnan(adj_matrix_baseline_power.values[i, j]) else 0
                outlier_percentage = adj_matrix_outliers.values[i, j] if not np.isnan(adj_matrix_outliers.values[i, j]) else 0
                if not np.isnan(val):  # Only plot for valid values
                    # Plot the top half rectangle for the test_mean value
                    plt.gca().add_patch(plt.Rectangle(
                        (x + 0.02, y + 0.02), 0.96, 0.46,  # x, y, width, height
                        color=plt.cm.magma((val - (-60)) / (0 - (-60))), alpha=1.0
                    ))
                    # Add text annotation for test_mean
                    plt.text(
                        x + 0.5, y + 0.23, f"{val:.1f}",
                        ha="center", va="center", fontsize=font_size_base * 0.1, color="white"
                    ).set_path_effects([
                        path_effects.Stroke(linewidth=1, foreground='black'),
                        path_effects.Normal()
                    ])

                    # Plot the bottom half rectangle for the baseline_mean value
                    plt.gca().add_patch(plt.Rectangle(
                        (x + 0.02, y + 0.02 + 0.5), 0.96, 0.47,  # x, y, width, height
                        color=plt.cm.magma((baseline_val - (-60)) / (0 - (-60))), alpha=1.0
                    ))
                    # Add text annotation for baseline_mean
                    plt.text(
                        x + 0.5, y + 0.77, f"{baseline_val:.1f}",
                        ha="center", va="center", fontsize=font_size_base * 0.1, color="white"
                    ).set_path_effects([
                        path_effects.Stroke(linewidth=1, foreground='black'),
                        path_effects.Normal()
                    ])

                    # Add a circle in the middle of the square for outlier_percentage
                    circle_color = plt.cm.RdYlGn(1 - outlier_percentage / 100)  # Scale color: 0% green, 100% red
                    plt.gca().add_patch(plt.Circle(
                        (x + 0.5, y + 0.5), 0.15,  # Constant radius
                        color=circle_color, alpha=1.0
                    ))
                    # Add text annotation for outlier_percentage inside the circle
                    text = plt.text(
                        x + 0.5, y + 0.5, f"{outlier_percentage:.1f}%",
                        ha="center", va="center", fontsize=font_size_base * 0.04, color="black"
                    )

            plt.title(f"Heatmap with Split Squares (Transmitter → Receiver) - Frequency {freq}, Prefix {prefix}\nTop Half - Test Power Mean, Bottom Half - Baseline Power Mean")
            plt.xlabel("(Receiver, Channel)")
            plt.ylabel("(Transmitter, Channel)")
            plt.xticks(rotation=45)
            plt.yticks(rotation=0)

            # Save the plot as an image
            filename = f"heatmap_split_squares_freq_{freq}_prefix_{prefix}.png"
            plt.savefig(os.path.join(output_dir, filename))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-file", help="Path to the test results CSV file", required=True)
    parser.add_argument("--output-dir", help="Directory to save the plots to", required=True)

    args = parser.parse_args()
    plot_heatmap_with_outliers(args.results_file, args.output_dir)
