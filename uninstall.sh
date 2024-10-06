#!/bin/bash

chmod a-x /data/es-ESS/service/run
kill -s 9 $(pgrep -f 'python /data/es-ESS/es-ESS.py')
rm -r /data/es-ESS

grep -v "/data/es-ESS/install.sh" /data/rc.local >> /data/temp.local
mv /data/temp.local /data/rc.local
chmod 755 /data/rc.local
