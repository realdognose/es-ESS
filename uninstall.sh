#!/bin/bash

kill $(pgrep -f 'supervise dbus-es-ess')
chmod a-x /data/dbus-es-ess/service/run
svc -d /service/dbus-es-ess
./restart.sh
