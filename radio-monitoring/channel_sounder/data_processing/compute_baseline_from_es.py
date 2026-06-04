#! /usr/bin/env python3

import argparse
import math
import os
from datetime import datetime

import pandas as pd
import pytz
from elasticsearch import Elasticsearch

POWER_MIN_VALID = -120
POWER_MAX_VALID = 20


def convert_est_to_utc(est_time_str: str) -> str:
    est = pytz.timezone("America/New_York")
    utc = pytz.utc
    est_time = datetime.strptime(est_time_str, "%Y-%m-%d %H:%M")
    est_time = est.localize(est_time)
    return est_time.astimezone(utc).isoformat()

# Elasticsearch uses population std, but we want sample std.
def to_sample_std(pop_std, count):
    if pop_std is None or count is None or count <= 1:
        return None
    return pop_std * math.sqrt(count / (count - 1))


def build_base_query(start_time_utc: str, end_time_utc: str):
    return {
        "bool": {
            "filter": [
                {
                    "range": {
                        "@timestamp": {
                            "gte": start_time_utc,
                            "lte": end_time_utc,
                        }
                    }
                },
                {
                    "terms": {
                        "log_type": ["power_log", "quality_log", "snr_log"]
                    }
                },
                {
                    "bool": {
                        "should": [
                            {"exists": {"field": "power"}},
                            {"exists": {"field": "quality"}}
                        ],
                        "minimum_should_match": 1
                    }
                },
                {
                    "bool": {
                        "should": [
                            {"bool": {"must_not": {"exists": {"field": "power"}}}},
                            {"range": {"power": {"gte": POWER_MIN_VALID, "lte": POWER_MAX_VALID}}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            ]
        }
    }


def get_index_properties(es: Elasticsearch, index_name: str):
    mapping = es.indices.get_mapping(index=index_name)
    first_index = next(iter(mapping.keys()))
    return mapping[first_index].get("mappings", {}).get("properties", {})

# If a field is a 'text' field, it cannot be used for aggregations. Need to use its '.keyword' subfield.
def resolve_agg_field(properties, field_name: str):
    field_info = properties.get(field_name, {})
    field_type = field_info.get("type")

    if field_type in ("text", "match_only_text"):
        sub_fields = field_info.get("fields", {})
        if "keyword" in sub_fields:
            return f"{field_name}.keyword"

        for sub_name, sub_info in sub_fields.items():
            if sub_info.get("type") == "keyword":
                return f"{field_name}.{sub_name}"

    return field_name


def fetch_grouped_metrics(es: Elasticsearch, index_name: str, query, sources):
    rows = []
    after_key = None

    while True:
        composite = {
            "size": 1000,
            "sources": sources,
        }
        if after_key is not None:
            composite["after"] = after_key

        body = {
            "size": 0,
            "query": query,
            "aggs": {
                "groups": {
                    "composite": composite,
                    "aggs": {
                        "power_stats": {"extended_stats": {"field": "power"}},
                        "quality_stats": {"extended_stats": {"field": "quality"}}
                    }
                }
            }
        }

        response = es.search(index=index_name, body=body)
        buckets = response["aggregations"]["groups"]["buckets"]

        for bucket in buckets:
            key = bucket["key"]
            power_stats = bucket["power_stats"]
            quality_stats = bucket["quality_stats"]

            row = {
                **key,
                "power_mean": power_stats.get("avg"),
                "power_std": to_sample_std(power_stats.get("std_deviation"), power_stats.get("count")),
                "quality_mean": quality_stats.get("avg"),
                "quality_std": to_sample_std(quality_stats.get("std_deviation"), quality_stats.get("count")),
            }
            rows.append(row)

        after_key = response["aggregations"]["groups"].get("after_key")
        if not after_key:
            break

    return rows


def compute_baseline_from_es(es, index_name, start_time_utc, end_time_utc):
    base_query = build_base_query(start_time_utc, end_time_utc)
    properties = get_index_properties(es, index_name)

    group_fields = [
        "transmitter",
        "transmitter_channel",
        "transmitter_serial_number",
        "receiver",
        "receiver_channel",
        "receiver_serial_number",
        "receiver_frequency",
    ]
    agg_fields = {field: resolve_agg_field(properties, field) for field in group_fields}

    # Normal case: Both transmitter and receiver exist (not control group)
    normal_query = {
        "bool": {
            "must": [base_query],
            "should": [
                {"exists": {"field": "transmitter"}},
                {"exists": {"field": "transmitter_serial_number"}}
            ],
            "minimum_should_match": 1
        }
    }

    normal_sources = [
        {"transmitter": {"terms": {"field": agg_fields["transmitter"]}}},
        {"transmitter_channel": {"terms": {"field": agg_fields["transmitter_channel"]}}},
        {"transmitter_serial_number": {"terms": {"field": agg_fields["transmitter_serial_number"]}}},
        {"receiver": {"terms": {"field": agg_fields["receiver"]}}},
        {"receiver_channel": {"terms": {"field": agg_fields["receiver_channel"]}}},
        {"receiver_serial_number": {"terms": {"field": agg_fields["receiver_serial_number"]}}},
        {"receiver_frequency": {"terms": {"field": agg_fields["receiver_frequency"]}}},
    ]

    normal_rows = fetch_grouped_metrics(es, index_name, normal_query, normal_sources)

    # Control case: No transmitter, only receiver (control groups)
    control_query = {
        "bool": {
            "must": [base_query],
            "must_not": [
                {"exists": {"field": "transmitter"}},
                {"exists": {"field": "transmitter_serial_number"}}
            ]
        }
    }

    control_sources = [
        {"receiver": {"terms": {"field": agg_fields["receiver"]}}},
        {"receiver_channel": {"terms": {"field": agg_fields["receiver_channel"]}}},
        {"receiver_serial_number": {"terms": {"field": agg_fields["receiver_serial_number"]}}},
        {"receiver_frequency": {"terms": {"field": agg_fields["receiver_frequency"]}}},
    ]

    control_rows = fetch_grouped_metrics(es, index_name, control_query, control_sources)

    # Match existing baseline shape for control rows
    for row in control_rows:
        row["transmitter"] = None
        row["transmitter_channel"] = None
        row["transmitter_serial_number"] = None

    baseline_df = pd.DataFrame(normal_rows + control_rows)

    expected_cols = [
        "transmitter",
        "transmitter_channel",
        "transmitter_serial_number",
        "receiver",
        "receiver_channel",
        "receiver_serial_number",
        "receiver_frequency",
        "power_mean",
        "power_std",
        "quality_mean",
        "quality_std",
    ]

    for col in expected_cols:
        if col not in baseline_df.columns:
            baseline_df[col] = None

    baseline_df = baseline_df[expected_cols]
    return baseline_df


def main():
    parser = argparse.ArgumentParser(
        description="Compute baseline metrics directly from Elasticsearch (no raw CSV export needed)."
    )
    parser.add_argument("--start-time", required=True, help="Start time in EST (format: YYYY-MM-DD HH:MM)")
    parser.add_argument("--end-time", required=True, help="End time in EST (format: YYYY-MM-DD HH:MM)")
    parser.add_argument("--output-file", required=False, default="baseline_results.csv", help="Output baseline CSV")
    parser.add_argument("--host", required=False, default="https://192.168.60.201:9200", help="Elasticsearch host URL")
    parser.add_argument("--username", required=False, default=None, help="Elasticsearch username")
    parser.add_argument("--password", required=False, default=None, help="Elasticsearch password")
    parser.add_argument("--cert-file", required=False, default="./http_ca.crt", help="CA cert path")
    parser.add_argument("--index", required=False, default="channel_sounder_logging", help="Elasticsearch index")

    args = parser.parse_args()

    start_time_utc = convert_est_to_utc(args.start_time)
    end_time_utc = convert_est_to_utc(args.end_time)

    username = args.username or os.environ.get("ES_USERNAME")
    password = args.password or os.environ.get("ES_PASSWORD")

    es_kwargs = {
        "hosts": [args.host],
        "ca_certs": args.cert_file,
    }
    if username and password:
        es_kwargs["basic_auth"] = (username, password)

    es = Elasticsearch(**es_kwargs)

    baseline_df = compute_baseline_from_es(
        es=es,
        index_name=args.index,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
    )

    baseline_df.to_csv(args.output_file, index=False)
    print(f"Baseline metrics saved to {args.output_file}")
    print(f"Total baseline groups: {len(baseline_df)}")


if __name__ == "__main__":
    main()
