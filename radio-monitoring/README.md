# Radio Monitoring Toolkit

This folder contains the channel-sounder monitoring pipeline used to collect SDR transmission logs, stream them through Kafka, index them in Elasticsearch, and generate post-test reports.

It is highly recommended to read the docs in the `docs/` folder for a more detailed overview of the architecture, components, and deployment instructions. The following sections provide a quick start guide.

**DISCLAIMER**: Some of the logic and overall pipeline structure may seem overly complex. This is because it was designed specifically with AERPAW's unique experiment environment in mind. It is encouraged to adapt and simplify as needed for your specific use case. Moreover, if you already have an existing Kafka or ELK deployment, you can reuse those components and just adapt the Logstash pipeline and post-processing scripts to fit your data schema.

## Contents

- `channel_sounder/`: orchestration scripts, test configuration, and post-processing tools.
- `kafka/`: Kafka container build assets and config notes.
- `elk/`: Elasticsearch/Logstash/Kibana container build assets and Logstash pipeline config.
- `docs/`: more detailed documentation pages for this subsystem.

## End-to-End Data Flow

1. `channelSounder.py` starts TX/RX on remote nodes through SSH and container commands.
2. Test logs are copied back and published to Kafka topic `channel_sounder_logging`.
3. Logstash consumes from Kafka, parses messages, and writes structured documents to Elasticsearch.
4. `data_processing/` scripts fetch data from Elasticsearch, compare against baseline, and render plots.
5. Optional email summary is sent with attachments.

## Quick Start (Reusable Deployment)

1. Stand up Kafka using instructions in `kafka/README.md`.
2. Stand up ELK using instructions in `elk/README.md`.
3. Create/update Logstash pipeline from `elk/channel_sounder_kafka.config`.
4. Configure `channel_sounder/channelSounder.py` runtime environment variables.
5. Validate test plan with `channel_sounder/testConfig.py`.
6. Run test orchestration with `channel_sounder/channelSounder.py`.
7. Run post-processing with `channel_sounder/postTestTasks.sh`.

## Compatibility Notes For Other Organizations

- In AERPAW, we have a specific set of fixed remote servers (we call them nodes) each with USRP radios that we run this test on. We run the orchestration script on a separate server that can SSH into those nodes and also has network access to the Kafka broker and Elasticsearch instance. The scripts are currently written with this architecture in mind.
- Node addressing and container names are currently represented in Python dictionaries in the channel-sounder scripts and must match your lab inventory.
- No networking configuration is included in this repo, as IP's and hostnames are environment-specific. Ensure that the machine running `channelSounder.py` can SSH into the experiment nodes and that those nodes can reach the Kafka broker and Elasticsearch instance.
- Kafka and Elasticsearch hostnames/ports must be reachable from the machine running orchestration and post-processing.
- Security settings are environment-driven; avoid committing credentials to source.
- If your timezone is not US/Eastern, convert input times accordingly or adapt scripts.

## Validation Checklist

- Kafka broker reachable from orchestration host.
- Logstash can consume `channel_sounder_logging` topic.
- Elasticsearch index `channel_sounder_logging` receives documents.
- `import_data.py` exports CSV rows for a known test window.
- `check_baseline.py check` produces `test_results.csv`.
- `plot_results.py` generates heatmap images without errors.

## Security Recommendations

- Provide credentials using environment variables or CI secret stores.
- Use least-privilege service accounts for Elasticsearch and SSH.
- Replace any static API keys in copied configs before production use.
- Restrict broker and Elasticsearch network exposure.
