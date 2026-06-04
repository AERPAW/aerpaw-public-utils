# Kafka Container Setup

This folder provides a Docker build for Apache Kafka (KRaft mode) used by the radio-monitoring pipeline.

## Important Before Reuse

`kafka.Dockerfile` currently includes static host-specific values in `server.properties` edits.
Update these for your environment:

- `controller.quorum.voters`
- `advertised.listeners`
- any bind/listener values required by your network

## Build

```bash
sudo docker build -t radio-monitoring/kafka:3.5.1 -f kafka.Dockerfile --network host .
```

## Run

```bash
sudo docker run -d --name radio_monitoring_kafka --network host radio-monitoring/kafka:3.5.1 tail -f /dev/null
sudo docker exec -it radio_monitoring_kafka bash
```

## Start Kafka (Inside Container)

```bash
start-kafka
```

Useful aliases in the container:

- `ktopics`: topic management helper.
- `kwriter`: produce test messages.
- `kreader`: consume messages.
- `stop-kafka`: stop broker.

## Create Topic

```bash
ktopics --create --topic channel_sounder_logging --partitions 3 --replication-factor 1
```

## Validate Broker

List topics:

```bash
ktopics --list
```

Write and read a test message:

```bash
echo '{"ping":"ok"}' | kwriter --topic channel_sounder_logging
kreader --topic channel_sounder_logging --from-beginning --max-messages 1
```

## Operational Notes

- Keep Kafka data on persistent volume in production.
- Verify `advertised.listeners` is reachable from the orchestrator and Logstash hosts.
- If using TLS/SASL, add corresponding broker and client configuration.
