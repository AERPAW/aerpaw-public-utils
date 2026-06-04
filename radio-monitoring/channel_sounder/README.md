# Channel Sounder Orchestration

This directory contains the main orchestration and operational scripts for running pairwise channel-sounder tests and publishing logs into the Kafka -> ELK pipeline.

## What Runs Where

- Backplane/orchestrator host:
  - `channelSounder.py`: main test runner and Kafka publisher.
  - `postTestTasks.sh`: post-processing pipeline wrapper.
  - `data_processing/`: baseline checks, plotting, and reporting.
  - `testConfig.py`: dry-run test plan printer.
  - `resetNodes.py`: cleanup helper for stuck node/container state.
- M-VM experiment container:
  - `startexperimentTX.sh`: launches transmitter flowgraph.
  - `startexperimentRX.sh`: launches receiver flowgraph.

## Prerequisites

- Python 3.8+ on orchestrator host.
- Python packages on orchestrator host:
  - `paramiko`
  - `kafka-python`
  - plus data-processing dependencies listed in `data_processing/README.md`.
- SSH access from orchestrator host to all node management IPs.
- Remote user must be able to run docker commands via `sudo`.
- Kafka reachable from orchestrator host.
- Logstash configured to consume topic `channel_sounder_logging`.

## Runtime Configuration

`channelSounder.py` supports the following environment variables:

- `CS_KAFKA_SERVERS`: comma-separated Kafka brokers. Default: `192.168.60.202:9092`.
- `CS_SSH_USER`: SSH username for node access. Default: `aerpawops`.
- `CS_SSH_KEY`: path to SSH private key. Default: `~/.ssh/id_rsa`.
- `CS_SUDO_PASSWORD`: optional sudo password for remote commands.

Node inventory file
-------------------

Node inventory is externalized into `nodes.json` located alongside these scripts:

- `radio-monitoring/channel_sounder/nodes.json`

Use the environment variable `CS_NODES_FILE` to point to an alternate JSON file. The expected format is a simple mapping of node short name to `[management_ip, container_name]`:

```json
{
  "LW1": ["152.14.188.131", "M-VM-LW1"],
  "LW2": ["152.14.188.132", "M-VM-LW2"]
}
```

The inventory file is required. If the file is missing or cannot be parsed, the orchestrator will exit with an error. Ensure `nodes.json` is present or set `CS_NODES_FILE` to a valid JSON file before running `channelSounder.py`.

Important:
- Node names, management IPs, and container names are defined in `channelSounder.py` (`nodes` dictionary). Update these to your environment.
- Test matrix is configured in JSON files such as `channel_config.json` and `small_chain.json`.

## Main Commands

Validate test config before execution:

```bash
./testConfig.py --config ./channel_config.json
```

Run channel sounding test plan:

```bash
CS_SSH_USER=myuser \
CS_SSH_KEY=/home/myuser/.ssh/id_ed25519 \
CS_KAFKA_SERVERS=10.0.0.20:9092 \
./channelSounder.py --config ./channel_config.json
```

Run post-test processing for current day:

```bash
./postTestTasks.sh
```

Run post-test processing for a specific date without email:

```bash
./postTestTasks.sh --date 2026-06-01 --nomail --keepdata
```

## postTestTasks.sh Behavior

`postTestTasks.sh` runs this sequence:

1. Downloads data from Elasticsearch via `data_processing/import_data.py`.
2. Compares data against baseline via `data_processing/check_baseline.py`.
3. Generates heatmaps via `data_processing/plot_results.py`.
4. Optionally emails results via `data_processing/send_email.py`.

Email is attempted only when both environment variables are set:

- `GMAIL_ADDRESS`
- `GMAIL_APP_PW`

If either is missing, email step is skipped safely.

## Common Issues

- No logs in Elasticsearch:
  - Verify Kafka topic receives messages.
  - Verify Logstash pipeline is loaded and running.
- Receivers/transmitters fail to start:
  - Confirm container names in `nodes` map.
  - Confirm `startexperimentTX.sh` and `startexperimentRX.sh` exist inside container at `/root/`.
- SSH works but sudo commands fail:
  - Set `CS_SUDO_PASSWORD` or configure passwordless sudo for docker commands.

## Files

- `channel_config.json`: example full test plan.
- `small_chain.json`: minimal debug test plan.
- `ProfileScripts/`: GNU Radio helper scripts referenced by start scripts.
- `SDR_control/`: generated/managed GNU Radio flowgraph files.

## If you don't have M-VM experiment containers

AERPAW uses pre-built experiment containers to run experiments as well as this channel sounder test. You can provide an equivalent runtime through:

- Lightweight container: build a container that contains GNU Radio, the `ProfileScripts/` tree, `screen`, and the `startexperiment*.sh` wrappers at `/root/`. Ensure that this container has access to the USRP devices.

Minimal example Dockerfile (experiment VM image):

```dockerfile
FROM ubuntu:22.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip gnuradio screen git wget ca-certificates
# Copy ProfileScripts and helper scripts into image (build-time)
COPY ProfileScripts /root/ProfileScripts
COPY SDR_control /root/SDR_control
COPY startexperimentTX.sh startexperimentRX.sh /root/
RUN chmod +x /root/startexperiment*.sh /root/ProfileScripts/Radio/Samples/*.sh /root/ProfileScripts/Radio/Helpers/*.sh
VOLUME /root/Results
CMD ["/bin/bash"]
```

Build and run (example):

```bash
docker build -t experiment-vm:latest .
docker run -d --name M-VM-LW1 -v /path/on/host/results:/root/Results --cap-add=NET_ADMIN experiment-vm:latest tail -f /dev/null
docker exec -it M-VM-LW1 bash
```

Notes:

- `startexperimentTX.sh` and `startexperimentRX.sh` are expected to exist in `/root/` inside the experiment container and be executable.
- `screen` is used by the start scripts to run GNU Radio flowgraphs in detached sessions; ensure it is installed.

## Script call chain and GNU Radio files

The start/stop scripts form a small call-chain. Understanding this helps when porting or testing without full AERPAW infrastructure:

- `startexperimentTX.sh` / `startexperimentRX.sh` (located in the root of the M-VM container) — these are thin wrappers executed by `channelSounder.py` via `docker exec`.
- They `cd` into `ProfileScripts/` and call one of the sample launchers under `ProfileScripts/Radio/Samples/` (for example `startGNURadio-ChannelSounder-TX_v3.sh`).
- The sample scripts call helper scripts under `ProfileScripts/Radio/Helpers/` to prepare parameters and environment.
- Helpers ultimately invoke Python/GNU Radio runtime scripts located in `SDR_control/Channel_Sounderv4/` such as `CSTX_noGUI.py`, `CSRX_noGUI.py`, and other generated `epy_block` scripts.

To test locally inside the experiment container you can run (example):

```bash
cd /root/ProfileScripts
./Radio/Samples/startGNURadio-ChannelSounder-TX_v3.sh <serial_number> <frequency> <channel> <gain_tx>
```

And for receiver:

```bash
./Radio/Samples/startGNURadio-ChannelSounder-RX_v3.sh <transmitter_name> <receiver_name> <serial_number> <frequency> <channel> <gain_rx>
```

If the GNU Radio scripts fail to start, check:

- That `python3` environment has the `gnuradio` modules available (install from apt or use PyBOMBS/conda where appropriate).
- That the sample/helper scripts have executable permissions.
- That `/root/Results` exists and is writable by the process started by the scripts.

