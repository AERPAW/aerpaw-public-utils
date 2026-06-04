#!/bin/bash
cd $PROFILE_DIR"/ProfileScripts/Radio/Helpers"

screen -S txGRC -dm \
       bash -c "stdbuf -oL -eL ./startchannelsounderTXGRC_v3.sh $1 $2 $3 $4 \
       2>&1 | ts $TS_FORMAT \
       | tee $RESULTS_DIR/$LOG_PREFIX\:radio_channelsoundertxgrc_log.txt"
