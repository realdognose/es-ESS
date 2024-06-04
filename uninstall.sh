#!/bin/bash

kill $(pgrep -f 'supervise es-ESS')
chmod a-x /data/es-ESS/service/run
svc -d /service/es-ESS
./restart.sh
