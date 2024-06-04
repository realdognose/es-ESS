#!/bin/bash

# set permissions for script files
chmod a+x /data/dbus-es-ess/restart.sh
chmod 744 /data/dbus-es-ess/restart.sh

chmod a+x /data/dbus-es-ess/uninstall.sh
chmod 744 /data/dbus-es-ess/uninstall.sh

chmod a+x /data/dbus-es-ess/service/run
chmod 755 /data/dbus-es-ess/service/run

# create sym-link to run script in deamon
ln -s /data/dbus-es-ess/service /service/dbus-es-ess

# add install-script to rc.local to be ready for firmware update
filename=/data/rc.local
if [ ! -f $filename ]
then
    touch $filename
    chmod 755 $filename
    echo "#!/bin/bash" >> $filename
    echo >> $filename
fi

grep -qxF '/data/dbus-es-ess/install.sh' $filename || echo '/data/dbus-es-ess/install.sh' >> $filename
