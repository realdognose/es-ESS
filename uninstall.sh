#!/bin/bash

chmod a-x /data/es-ESS/service/run
kill -s 9 $(pgrep -f 'python /data/es-ESS/es-ESS.py')
rm -r /data/es-ESS
