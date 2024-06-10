import os
import sys
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

class MqttExporter:
    def __init__(self):
        self.config = Globals.getConfig()
        self.futureUpdateMqtt = None
        self.topicExports = {}
        
        #Load all topics we should export from DBus to Mqtt and start listening for changes.
        #upon change, export according to the setup rules. 
        try:
            d(self, "Scanning config for export requests")
            for (k, v) in self.config.items("MqttExporter"):
                if (k.startswith("Export_")):
                    parts = v.split(',')
                    key = parts[0].strip() + "_" + parts[1].strip()
                    self.topicExports[key] = TopicExport(parts[0].strip(), parts[1].strip(), parts[2].strip())

            i(self, "Found {0} export requests.".format(len(self.topicExports)))

            gobject.timeout_add(10000, self._finishInit)
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def _finishInit(self):
        Globals.esESS.threadPool.submit(self.__initThreaded)
        i(self, "MqttExporter initialized.")
        return False

    def __initThreaded(self):
        #Fire up dbusmonitor 
        dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}
        monitorList = {}
        for (key, topicExport) in self.topicExports.items():
            if (topicExport.commonService not in monitorList):
                monitorList[topicExport.commonService] = {}
            
            d(self, "Starting to Monitor {0}{1} for export to {2}".format(topicExport.service, topicExport.source, topicExport.target))
            monitorList[topicExport.commonService][topicExport.source] = dummy
        
        self.monitor = DbusMonitor(monitorList, self.__dbusValueChanged)

    def __dbusValueChanged(self, dbusServiceName, dbusPath, dict, changes, deviceInstance):
        key = dbusServiceName + "_" + dbusPath
        #d(self, "Change on dbus for {0} (new value: {1})".format(key, str(changes['Value'])))
        #d(self, "Desired export target: {0}".format(self.topicExports[key].target))
        if (key in self.topicExports):
            Globals.mqttClient.publish(self.topicExports[key].target, str(changes['Value']), 0, True)

class TopicExport:
    def __init__(self, service, source, target):
        self.commonService = ".".join(service.split('.')[:3])
        self.service = service
        self.source = source
        if (target.endswith("*")):
            self.target = target.replace('*', '') + source
        else:
            self.target = target