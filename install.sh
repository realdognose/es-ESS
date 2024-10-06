#!/bin/bash

# set permissions for script files
chmod a+x /data/es-ESS/restart.sh
chmod 744 /data/es-ESS/restart.sh

chmod a+x /data/es-ESS/kill_me.sh
chmod 744 /data/es-ESS/kill_me.sh

chmod a+x /data/es-ESS/uninstall.sh
chmod 744 /data/es-ESS/uninstall.sh

chmod a+x /data/es-ESS/service/run
chmod 755 /data/es-ESS/service/run

# create sym-link to run script in deamon
ln -s /data/es-ESS/service /service/es-ESS

# add install-script to rc.local to be ready for firmware update
filename=/data/rc.local
if [ ! -f $filename ]
then
    touch $filename
    chmod 755 $filename
    echo "#!/bin/bash" >> $filename
    echo >> $filename
fi

grep -qxF '/data/es-ESS/install.sh' $filename || echo '/data/es-ESS/install.sh' >> $filename

#first install? need config.sample to be copied.
configTarget=/data/es-ESS/config.ini
if [ ! -f $configTarget ]
then
    cp /data/es-ESS/config.sample.ini /data/es-ESS/config.ini
fi