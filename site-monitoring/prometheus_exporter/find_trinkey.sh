#! /bin/bash
# Finds tty device that Adafruit Trinkey belongs to
for dev in /dev/ttyACM*; do

    if udevadm info -a -n "$dev" | grep -qi "Adafruit"; then
        echo "Found Adafruit device at: $dev"
        export DEVICE=$dev
    fi
done

if [ -z "$DEVICE" ]; then
    echo "No Adafruit device found"
fi
