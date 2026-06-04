# ELK Container Setup (Elasticsearch + Logstash + Kibana)

This folder contains a Docker build for an ELK stack used by channel-sounder monitoring.

## Important Before Reuse

Files in this folder include AERPAW-specific network values and credentials placeholders. For another organization, update:

- Kafka broker address in `channel_sounder_kafka.config`.
- Elasticsearch host and credentials/API key in `channel_sounder_kafka.config`.
- Network host values in `elk.Dockerfile` and/or mounted config files.

Do not publish real API keys or passwords in source control.

## Build

```bash
sudo docker build -t radio-monitoring/elk:8.10.2 -f elk.Dockerfile --network host .
```

## Run Container

```bash
sudo docker run -d --name radio_monitoring_elk --network host radio-monitoring/elk:8.10.2 tail -f /dev/null
sudo docker exec -it radio_monitoring_elk bash
```

## Initial Service Setup (Inside Container)

1. Start Elasticsearch:

```bash
start-elastic
```

2. Enroll Kibana (first-time setup):

- If needed, generate token:

```bash
$ES_HOME/bin/elasticsearch-create-enrollment-token -s kibana
```

- Enroll Kibana:

```bash
$KB_HOME/bin/kibana-setup --enrollment-token <TOKEN>
```

3. Start Kibana and Logstash:

```bash
start-kibana
start-logstash
```

## Configure Logstash Pipeline

Copy `channel_sounder_kafka.config` to:

`/home/elk/logstash/config/pipelines.d/channel_sounder_kafka.config`

Then ensure Logstash pipeline references it (via `pipelines.yml` or default pipeline config).

What this pipeline does:

- Consumes JSON messages from Kafka topic `channel_sounder_logging`.
- Parses `log_content` values into structured metrics.
- Writes documents to Elasticsearch index `channel_sounder_logging`.

## Kibana Graphs
You can import the provided Kibana dashboard from `elk/export.ndjson` to visualize the channel sounder logs. Note that this dashboard is configured for AERPAW's specific node naming and radio configurations and will require adjustments based on your environment.

## Verify

Inside container:

```bash
curl -k https://127.0.0.1:9200
```

From Kibana Dev Tools, check document count:

```json
GET channel_sounder_logging/_count
```

## Operational Notes

- `--network host` is the simplest mode for this stack and avoids extra port mapping complexity.
- For production, pin resource limits and persistent storage mounts.
- Keep certs and secrets external to image when possible.