#! /usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
import check_baseline

def plot_adjacency_matrix(input_file, baseline=True):
    # Load the baseline results file
    if baseline:
        df = pd.read_csv(input_file)
    else:
        df = check_baseline.compute_baseline([input_file], output_file=None)

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

            # Group by transmitter-receiver pair and take the mean power value
            df_grouped = df_subset.groupby(
                ["transmitter", "transmitter_channel", "receiver", "receiver_channel"]
            ).agg({"power_mean": "mean"}).reset_index()

            # Pivot the dataframe to create an adjacency matrix for power mean
            adj_matrix_power = df_grouped.pivot(
                index=["transmitter", "transmitter_channel"],
                columns=["receiver", "receiver_channel"],
                values="power_mean"
            )

            adj_matrix_power = adj_matrix_power.sort_index(axis=0).sort_index(axis=1)

            # Plot the adjacency matrix for power
            plt.figure(figsize=(12, 10))
            sns.heatmap(
                adj_matrix_power,
                annot=True,
                fmt=".2f",
                cmap="coolwarm",
                linewidths=0.5,
                linecolor="gray",
                vmin=-60,
                vmax=0,
                xticklabels=adj_matrix_power.columns,
                yticklabels=adj_matrix_power.index
            )

            plt.title(f"Adjacency Matrix of Power Mean (Transmitter → Receiver) - Frequency {freq}, Prefix {prefix}")
            plt.xlabel("(Receiver, Channel)")
            plt.ylabel("(Transmitter, Channel)")
            plt.xticks(rotation=45)
            plt.yticks(rotation=0)

            # Save the plot as an image
            plt.savefig(f"adjacency_matrix_freq_{freq}_prefix_{prefix}.png")
            #plt.show()

def plot_box_plot(input_file, baseline=True):
    # Load the baseline results file
    if baseline:
        df = pd.read_csv(input_file)
    else:
        df = pd.read_csv(input_file)

    # Replace NaN transmitters with "None" for special cases
    df['transmitter'] = df['transmitter'].fillna("None")

    # Get unique frequencies
    frequencies = df["receiver_frequency"].dropna().unique()

    for freq in frequencies:
        # Filter data for the specific frequency
        df_freq = df[df["receiver_frequency"] == freq]

        # Loop for subsets based on transmitter and receiver prefixes
        for prefix in ["CC", "LW"]:
            # Filter data where both transmitter and receiver start with the prefix
            df_subset = df_freq[
                df_freq["transmitter"].str.startswith(prefix) & 
                df_freq["receiver"].str.startswith(prefix)
            ]

            if df_subset.empty:
                continue  # Skip if no data matches the condition

            # Group by transmitter-receiver pair
            unique_transmitters = df_subset.groupby(["transmitter", "transmitter_channel"]).groups.keys
            unique_receivers = df_subset.groupby(["receiver", "receiver_channel"]).groups.keys

            print(unique_transmitters)
            print(unique_receivers)

            fig, axes = plt.subplots(
                len(unique_transmitters), len(unique_receivers),
                figsize=(15, 15), sharex=True, sharey=True
            )

            # Set column titles (receiver and receiver_channel)
            for j, [receiver, receiver_channel] in enumerate(unique_receivers):
                axes[0, j].set_title(f"{receiver}:{receiver_channel}")

            # Set row titles (transmitter and transmitter_channel)
            for i, [transmitter, transmitter_channel] in enumerate(unique_transmitters):
                axes[i, 0].set_ylabel(f"{transmitter}:{transmitter_channel}", rotation=0, labelpad=50)

            for i, [transmitter, transmitter_channel] in enumerate(unique_transmitters):
                for j, [receiver, receiver_channel] in enumerate(unique_receivers):
                    ax = axes[i, j]

                    # Filter data for the specific transmitter-receiver pair
                    pair_data = df_subset[
                        (df_subset["transmitter"] == transmitter) &
                        (df_subset["receiver"] == receiver) &
                        (df_subset["transmitter_channel"] == transmitter_channel) &
                        (df_subset["receiver_channel"] == receiver_channel)
                    ]

                    if not pair_data.empty:
                        # Create a boxplot for raw power values
                        sns.boxplot(
                            data=pair_data,
                            y="power",
                            ax=ax,
                            color="skyblue"
                        )

                    ax.set_ylim(-60, 0)  # Restrict y-axis

            # Add overall labels for rows and columns
            fig.text(0.5, 0.04, "Transmitter:Channel", ha="center", fontsize=12)
            fig.text(0.04, 0.5, "Receiver:Channel", va="center", rotation="vertical", fontsize=12)

            plt.suptitle(f"Box Plot Grid (Transmitter → Receiver) - Frequency {freq}, Prefix {prefix}")
            plt.tight_layout(rect=[0.05, 0.05, 0.95, 0.95])  # Adjust spacing to make subplots closer

            # Save the plot as an image
            plt.savefig(f"box_plot_grid_freq_{freq}_prefix_{prefix}.png")
            #plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-file", help="Path to the baseline CSV file")
    parser.add_argument("--log-file", help="Path to the log file")
    parser.add_argument("--type", required=False, default="heatmap", help="boxplot/heatmap")

    args = parser.parse_args()

    # Ensure only one of the arguments is provided
    if bool(args.baseline_file) == bool(args.log_file):
        parser.error("You must provide exactly one of --baseline-file or --log-file.")

    # Call the function with the appropriate argument
    if args.type == "heatmap":
        if args.baseline_file:
            plot_adjacency_matrix(args.baseline_file, baseline=True)
        else:
            plot_adjacency_matrix(args.log_file, baseline=False)
    elif args.type == "boxplot":
        if args.baseline_file:
            plot_box_plot(args.baseline_file, baseline=True)
        else:
            plot_box_plot(args.log_file, baseline=False)