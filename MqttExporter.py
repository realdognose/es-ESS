import os
import sys
from typing import Dict
import dbus # type: ignore
import dbus.service # type: ignore
import inspect
import pprint
import os
import sys
if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

# esEss imports
import Globals
from Helper import i, c, d, w, e
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from dbusmonitor import DbusMonitor # type: ignore
from esESSService import esESSService

class MqttExporter(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.topicExports: Dict[str, TopicExport] = {}
        
        #Load all topics we should export from DBus to Mqtt and start listening for changes.
        #upon change, export according to the setup rules. 
        try:
            d(self, "Scanning config for export requests")
            for (k, v) in self.config.items("MqttExporter"):
                if (k.startswith("Export_")):
                    parts = v.split(',')
                    key = parts[0].strip() + parts[1].strip()
                    self.topicExports[key] = TopicExport(parts[0].strip(), parts[1].strip(), parts[2].strip())

            i(self, "Found {0} export requests.".format(len(self.topicExports)))
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        pass

    def initDbusSubscriptions(self):
        for (key, topicExport) in self.topicExports.items():
            self.registerDbusSubscription(topicExport.service, topicExport.source, self._dbusValueChanged)
        
    def initWorkerThreads(self):
        pass

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass

    def _dbusValueChanged(self, sub):
        key = "{0}{1}".format(sub.serviceName, sub.dbusPath)
        #d(self, "Change on dbus for {0} (new value: {1})".format(key, str(sub.value)))
        self.publishMainMqtt(self.topicExports[key].target, sub.value, 0, True)

class TopicExport:
    def __init__(self, service, source, target):
        self.commonService = ".".join(service.split('.')[:3])
        self.service = service
        self.source = source
        if (target.endswith("*")):
            self.target = target.replace('*', '') + source
        else:
            self.target = target