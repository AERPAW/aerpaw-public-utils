#! /bin/bash
set -e  # script exits immediately on any command failure

# Usage: ./postTestTasks.sh [--date YYYY-MM-DD] [--nomail] [--keepdata]
usage() {
	echo "Usage: ./postTestTasks.sh [--date YYYY-MM-DD] [--nomail] [--keepdata] [--debug-msg 'msg']"
	exit 1
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
	case "$1" in
		--date)
			shift
			[[ -z "$1" ]] && echo "Error: --date requires a value" && usage
			DATE="$1"
			;;
		--nomail)
			NOMAIL=true
			;;
		--keepdata)
			KEEPDATA=true
			;;
		--debug-msg)
			shift
			[[ -z "$1" ]] && echo "Error: --debug-msg requires a value" && usage
			DEBUG_MSG="$1"
			;;
		-*)
			usage
			;;
	esac
	shift
done


YYYY_MM_DD=${DATE:-$(date +%F)}
echo "$YYYY_MM_DD"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DATA_DIR=$SCRIPT_DIR/data_processing

$DATA_DIR/import_data.py --start-time "$YYYY_MM_DD 00:00" --end-time "$YYYY_MM_DD 23:59" --output-file $DATA_DIR/temp_today_data.csv --cert-file $DATA_DIR/http_ca.crt

$DATA_DIR/check_baseline.py check --test-file $DATA_DIR/temp_today_data.csv --baseline-file $DATA_DIR/baseline_results.csv --output-file $DATA_DIR/temp_test_results.csv --deviation 2 --threshold 50.0

$DATA_DIR/plot_results.py --results-file $DATA_DIR/temp_test_results.csv --output-dir $DATA_DIR

if [[ -z $NOMAIL ]]; then
	if [[ -z "${GMAIL_ADDRESS:-}" || -z "${GMAIL_APP_PW:-}" ]]; then
		echo "Skipping sending email: GMAIL_ADDRESS and/or GMAIL_APP_PW not set"
	else
		$DATA_DIR/send_email.py --recipients $DATA_DIR/recipients.txt --debug-msg "${DEBUG_MSG:-''}" $DATA_DIR/power_heatmap_*.png $DATA_DIR/temp_test_results.csv
	fi
else
	echo "Skipping sending email"
fi

if [[ -z $KEEPDATA ]]; then
	rm -f $DATA_DIR/temp_today_data.csv $DATA_DIR/temp_test_results.csv $DATA_DIR/power_heatmap_*.png
fi
