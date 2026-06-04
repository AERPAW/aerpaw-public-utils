#!/bin/bash
mkfifo /root/Power
mkfifo /root/Quality
mkfifo /root/SNR

cd $PROFILE_DIR"/ProfileScripts/Radio/Helpers"

screen -S rxGRC -dm \
       bash -c "stdbuf -oL -eL ./startchannelsounderRXGRC_v3.sh $1 $2 $3 $4 \
       2>&1 | ts $TS_FORMAT \
       | tee $RESULTS_DIR/$LOG_PREFIX\:radio_channelsounderrxgrc_log.txt"

screen -S power -dm        bash -c "stdbuf -oL -eL od -f -w4 /root/Power\
        2>&1 | ts $TS_FORMAT \
       | tee $RESULTS_DIR/$LOG_PREFIX\:power_log.txt"

screen -S quality -dm        bash -c "stdbuf -oL -eL od -f -w4 /root/Quality\
        2>&1 | ts $TS_FORMAT \
       | tee $RESULTS_DIR/$LOG_PREFIX\:quality_log.txt"

screen -S SNR -dm        bash -c "stdbuf -oL -eL od -f -w4 /root/SNR\
        2>&1 | ts $TS_FORMAT \
       | tee $RESULTS_DIR/$LOG_PREFIX\:snr_log.txt"
