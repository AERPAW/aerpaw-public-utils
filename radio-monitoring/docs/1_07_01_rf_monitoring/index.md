# 1.07.01 RF Monitoring (common to Testbed and Sandbox)

This section describes the automated radio front-end health monitoring test that AERPAW uses to track the health of the wireless environment for its fixed nodes. This test is run daily, and the results are used to identify any significant changes in the RF environment that may impact an experiment's performance.

## Overview

The Channel Sounder system performs automated RF health monitoring by executing transmission and reception tests between fixed nodes. A cronjob on `aerpaw-ops-server` runs the test daily at 2 AM EST. Test data is logged to Elasticsearch.

## Running the Channel Sounder Test

### Automated Daily Execution

A cronjob on `aerpaw-ops-server` automatically runs the channel sounder test daily at 2 AM EST using the default configuration.

A cronjob on `aerpaw-ops-server` automatically runs the post-test analysis (`postTestTasks.sh`) daily at 2:45 AM EST.

### Manual Execution

1. Sign in to `aerpawops@aerpaw-ops-server`
2. Run: `~/channel_sounder/channelSounder.py -c </path/to/config.json>`
3. Logs are stored at `/tmp/channelSounder.log` and `/tmp/postTest.log`

### Default Configuration

The default configuration file is located at `/home/aerpawops/channel_sounder/channel_config.json` and includes:
- LW1-5 with 2 channels each on 3.32GHz
- LW3-5 with 2 channels each on 915MHz
- CC1-3 with 2 channels each on 3.32GHz

**IMPORTANT**: The graphs generated in the post-test processing (the one sent in the email) are based on this default configuration. If you run the test with a different configuration, the graphs may not be generated correctly.
The plots in Kibana (see [Channel Sounder Monitoring Dashboard](#channel-health-monitoring-dashboard)) are robust to different configurations but if additional radios other than the default are added, then the graphs' labels need to be modified to add the new transmitter/receiver.

## Configuration File Format

### JSON Structure

The `channelSounder.py` script requires a JSON configuration file that defines test scenarios. The configuration supports multiple test groups, where each group contains chains to be tested sequentially.

**Example Configuration:**
```json
{
  "test_groups": [
    {
      "group_name": "LW1 - LW2 test",
      "test_duration": 20,
      "chains": [
        {
          "node_name": "LW1",
          "serial_number": "31EAC18",
          "transmission_type": "TX",
          "channel": "0",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW1",
          "serial_number": "31EAC18",
          "transmission_type": "TX",
          "channel": "1",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW2",
          "serial_number": "3235751",
          "transmission_type": "RX",
          "channel": "0",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW2",
          "serial_number": "3235751",
          "transmission_type": "RX",
          "channel": "1",
          "frequency": "3.5G"
        }
      ]
    }
  ]
}
```

### Configuration Parameters

#### Test Group Level
- **test_groups**: Array of test group objects (executed sequentially, not concurrently)
- **group_name**: Descriptive name for the test group
- **test_duration**: Duration in seconds for each test (default: 20)
- **chains**: Array of chain objects defining transmitters and receivers for the test

#### Chain Attributes

| Attribute | Description | Example |
|-----------|-------------|---------|
| `node_name` | Node ID | LW1, CC3 |
| `serial_number` | Radio serial number | 31EAC18 |
| `transmission_type` | Either TX (transmit) or RX (receive) | TX, RX |
| `channel` | Channel on which to transmit/receive | 0, 1 |
| `frequency` | Frequency on which to transmit/receive | 3.5G, 900M |

### Test Execution Logic

For each test group, tests occur between every TX chain and every RX chain (excluding pairings with the same node).

#### Test Construction Process

1. **Identify** transmitters (TX) and receivers (RX)
2. **Group receivers** into separate groups to ensure no node appears twice in the same group
   - If a node has multiple receiver chains on different channels, they are placed into separate receiver groups
   - This prevents conflicts where a node receives on multiple channels simultaneously

#### Test Execution Process

1. Transmission starts on the TX chain
2. All receivers in a receiver group start and record data for the specified duration
3. Reception stops for the current receiver group and starts for the next group
4. Process repeats from (2) until all receiver groups have been tested
5. The transmitter remains active across all receiver groups
6. Once all receiver chains for a transmitter have been tested, the transmitter stops
7. Process repeats from (1) for the next transmitter

### Example Test Scenario

**Configuration:**
```json
{
  "test_groups": [
    {
      "group_name": "LW1 transmission test",
      "test_duration": 20,
      "chains": [
        {
          "node_name": "LW1",
          "serial_number": "31EAC18",
          "transmission_type": "TX",
          "channel": "0",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW1",
          "serial_number": "31EAC18",
          "transmission_type": "TX",
          "channel": "1",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW2",
          "serial_number": "3235751",
          "transmission_type": "RX",
          "channel": "0",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW2",
          "serial_number": "3235751",
          "transmission_type": "RX",
          "channel": "1",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW3",
          "serial_number": "3235754",
          "transmission_type": "RX",
          "channel": "0",
          "frequency": "3.5G"
        },
        {
          "node_name": "LW3",
          "serial_number": "3235754",
          "transmission_type": "RX",
          "channel": "1",
          "frequency": "3.5G"
        }
      ]
    }
  ]
}
```

**Resulting Test Matrix:**

Transmitters: LW1 Channel 0, LW1 Channel 1  
Receivers: LW2 Channel 0, LW2 Channel 1, LW3 Channel 0, LW3 Channel 1

**Receiver Grouping:**
- Group 1: LW2 Channel 0, LW3 Channel 0
- Group 2: LW2 Channel 1, LW3 Channel 1

**Tests Executed:**

| Test # | Transmitter (TX) | Receivers (RX) | Duration |
|--------|------------------|----------------|----------|
| 1 | LW1 - Channel 0 | LW2 - Channel 0, LW3 - Channel 0 | 20 sec |
| 2 | LW1 - Channel 0 | LW2 - Channel 1, LW3 - Channel 1 | 20 sec |
| 3 | LW1 - Channel 1 | LW2 - Channel 0, LW3 - Channel 0 | 20 sec |
| 4 | LW1 - Channel 1 | LW2 - Channel 1, LW3 - Channel 1 | 20 sec |


## Viewing Results

Results can be viewed through the Channel Sounder Monitoring dashboard [Kibana Dashboard](./1_07_01_01_channel_sounder_elastic_dashboard/index.md).

## Developer Information

For implementation details and developer information, see [Channel Sounder Monitoring Developer Information](./1_07_01_02_channel_sounder_developer_info/index.md).