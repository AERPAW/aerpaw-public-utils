#! /usr/bin/env python3

import argparse
import csv
import os
from datetime import datetime
import pytz
from elasticsearch import Elasticsearch

# Function to convert EST time to UTC
def convert_est_to_utc(est_time_str):
    est = pytz.timezone("America/New_York")
    utc = pytz.utc
    est_time = datetime.strptime(est_time_str, "%Y-%m-%d %H:%M")
    est_time = est.localize(est_time)  # Localize to EST timezone
    return est_time.astimezone(utc).isoformat()

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Fetch data from Elasticsearch within a time range.")
parser.add_argument("--start-time", required=True, help="Start time in EST (format: YYYY-MM-DD HH:MM)")
parser.add_argument("--end-time", required=True, help="End time in EST (format: YYYY-MM-DD HH:MM)")
parser.add_argument("--output-file", required=True, help="CSV file to download data to")
parser.add_argument("--cert-file", required=False, default="./http_ca.crt", help="CRT file of CA for Elasticsearch")
parser.add_argument("--host", required=False, default="https://192.168.60.201:9200", help="Elasticsearch host URL")
parser.add_argument("--username", required=False, default=None, help="Elasticsearch username")
parser.add_argument("--password", required=False, default=None, help="Elasticsearch password")
parser.add_argument("--index", required=False, default="channel_sounder_logging", help="Elasticsearch index")
args = parser.parse_args()

# Convert times from EST to UTC
start_time_utc = convert_est_to_utc(args.start_time)
end_time_utc = convert_est_to_utc(args.end_time)

username = args.username or os.environ.get("ES_USERNAME")
password = args.password or os.environ.get("ES_PASSWORD")

# Connect to Elasticsearch
es_kwargs = {
    "hosts": [args.host],
    "ca_certs": args.cert_file,
}
if username and password:
    es_kwargs["basic_auth"] = (username, password)

es = Elasticsearch(**es_kwargs)

index_name = args.index
scroll_time = "2m"  # Keep scroll context open for 2 minutes
batch_size = 1000   # Number of documents per batch

# Define time range for Feb 25, 2:00 AM to 2:30 AM (UTC format)
query = {
    "_source": {
        "excludes": ["event", "@version", "byte_number", "log_content", "tags", "log_timestamp"]
    },
    "query": {
        "bool": {
            "filter": [
                {
                    "range": {
                        "@timestamp": {
                            "gte": start_time_utc,  # 2:00 AM EST → 07:00 AM UTC
                            "lte": end_time_utc,   # 2:30 AM EST → 07:30 AM UTC
                        }
                    }
                },
                {
                    "terms": {
                        "log_type": ["power_log", "quality_log", "snr_log"]
                    }
                }
            ]
        }
    }
}

# Start scrolling search
response = es.search(index=index_name, body=query, scroll=scroll_time, size=batch_size)

scroll_id = response["_scroll_id"]
hits = response["hits"]["hits"]

# Extract field names from the first document
if hits:
    fieldnames = set(hits[0]["_source"].keys()).union(['power', 'quality', 'snr', 'tags'])
else:
    print("No data found for the given time range.")
    exit()

# Open CSV file and write header
with open(args.output_file, mode="w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()

    # Write initial batch
    for hit in hits:
        writer.writerow(hit["_source"])

    # Scroll through remaining data
    while len(hits) > 0:
        response = es.scroll(scroll_id=scroll_id, scroll=scroll_time)
        hits = response["hits"]["hits"]

        for hit in hits:
            writer.writerow(hit["_source"])

        scroll_id = response["_scroll_id"]  # Update scroll ID

# Clear the scroll context
es.clear_scroll(scroll_id=scroll_id)

print(f"Export completed: {args.output_file}")
