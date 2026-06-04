#!/usr/bin/env python3

import os
import time
import socket
import serial

DEVICE = os.getenv("DEVICE", "/dev/trinkey")
BAUD = int(os.getenv("BAUD", "115200"))
with open("/etc/hostname") as f:
    HOST = f.read().strip()

PROM_FILE = "/var/lib/node_exporter/textfile_collector/sht4x.prom"

def write_metrics(temp, hum):
    tmp_file = PROM_FILE + ".tmp"

    with open(tmp_file, "w") as f:
        f.write(f'sht4x_temperature_celsius{{host="{HOST}"}} {temp}\n')
        f.write(f'sht4x_humidity_percent{{host="{HOST}"}} {hum}\n')

    os.replace(tmp_file, PROM_FILE)

def main():
    while True:
        try:
            with serial.Serial(DEVICE, BAUD, timeout=2) as ser:
                print(f"[INFO] Connected to {DEVICE}")

                while True:
                    line = ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue

                    print(line)

                    try:
                        parts = line.split(",")

                        if len(parts) < 3:
                            continue

                        temp = parts[1].strip()
                        hum = parts[2].strip()

                        write_metrics(temp, hum)

                        print(
                            time.strftime("%Y-%m-%d %H:%M:%S"),
                            f"[INFO] Temperature: {temp} C, Humidity: {hum}%"
                        )

                    except Exception as e:
                        print(f"[WARN] Parse error: {e}")

        except serial.SerialException as e:
            print(f"[ERROR] Serial disconnected: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
