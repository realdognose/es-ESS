import os
import sys
from typing import Dict
import dbus # type: ignore
import dbus.service # type: ignore
import inspect
import pprint
import os
import sys

# esEss imports
from Helper import i, c, d, w, e
import Globals
from esESSService import esESSService

class MqttExporter(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.topicExports: Dict[str, TopicExport] = {}
        self.forwardedTopicsPastMinute = 0
        
        #Load all topics we should export from DBus to Mqtt and start listening for changes.
        #upon change, export according to the setup rules. 
        try:
            d(self, "Scanning config for export requests")

            for k in self.config.sections():
                if (k.startswith("MqttExporter:")):
                    service = self.config[k]["Service"]
                    dbuskey = self.config[k]["DbusKey"]
                    mqttTopic = self.config[k]["MqttTopic"] 
                    key = service + dbuskey
                    self.topicExports[key] = TopicExport(service, dbuskey, mqttTopic)

            i(self, "Found {0} export requests.".format(len(self.topicExports)))
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        pass

    def initDbusSubscriptions(self):
        for topicExport in self.topicExports.values():
            self.registerDbusSubscription(topicExport.service, topicExport.source, self._dbusValueChanged)
        
    def initWorkerThreads(self):
        self.registerWorkerThread(self._signOfLife, 60000)

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass

    def _dbusValueChanged(self, sub):
        key = "{0}{1}".format(sub.serviceName, sub.dbusPath)
        if key in self.topicExports:
            self.publishMainMqtt(self.topicExports[key].target, sub.value, 0, True)
        else:
            key = "{0}{1}".format(sub.commonServiceName, sub.dbusPath)
            self.publishMainMqtt(self.topicExports[key].target, sub.value, 0, True)

        self.forwardedTopicsPastMinute += 1

    def _signOfLife(self):
        self.publishServiceMessage(self, "Forwarded {0} Dbus-Messages in the past minute.".format(self.forwardedTopicsPastMinute))
        self.forwardedTopicsPastMinute = 0
    
    def handleSigterm(self):
       pass

class TopicExport:
    def __init__(self, service, source, target):
        self.commonService = ".".join(service.split('.')[:3])
        self.service = service
        self.source = source
        if (target.endswith("*")):
            self.target = target.replace('*', '') + source
        else:
            self.target = target