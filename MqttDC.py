import os
import platform
import sys
from typing import Dict
import dbus # type: ignore
import dbus.service # type: ignore
import inspect
import pprint
import os
import sys

# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore

# esEss imports
from Helper import i, c, d, w, e, t, dbusConnection
import Globals
from esESSService import esESSService

class MqttDC(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.dcLoads: Dict[str, DCLoad] = {}
        self.forwardedTopicsPastMinute = 0
        
        #Load all topics we should export from DBus to Mqtt and start listening for changes.
        #upon change, export according to the setup rules. 
        try:
            d(self, "Scanning config for dc loads")
            for k in self.config.sections():
                if (k.startswith("MqttDC:")):
                    parts = k.split(':')
                    key = parts[1].strip()
                    valueTopic = self.config[k]["Topic"]
                    voltageTopic = self.config[k]["TopicVoltage"] if "TopicVoltage" in self.config[k] else None
                    currentTopic = self.config[k]["TopicCurrent"] if "TopicCurrent" in self.config[k] else None
                    self.dcLoads[key] = DCLoad(self, key, self.config[k]["CustomName"], valueTopic, currentTopic, voltageTopic, int(self.config[k]["VRMInstanceID"]))

            i(self, "Found {0} DCLoads.".format(len(self.dcLoads)))
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        for (sensor) in self.dcLoads.values():
            sensor.initDbusService()

    def initDbusSubscriptions(self):
        pass
        
    def initWorkerThreads(self):
        pass

    def initMqttSubscriptions(self):
        for sensor in self.dcLoads.values():
            self.registerMqttSubscription(sensor.valueTopic, callback=sensor.onMqttMessage)

            if (sensor.voltageTopic is not None):
                self.registerMqttSubscription(sensor.voltageTopic, callback=sensor.onMqttMessage)

            if (sensor.currentTopic is not None):
                self.registerMqttSubscription(sensor.currentTopic, callback=sensor.onMqttMessage)

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       pass

class DCLoad:
    def __init__(self, rootService, key, customName, valueTopic, currentTopic, voltageTopic, vrmInstanceID):
        self.key = key
        self.customName = customName
        self.valueTopic = valueTopic
        self.currentTopic = currentTopic
        self.voltageTopic = voltageTopic
        self.value = 0.0
        self.voltage = 0.0
        self.current = 0.0
        self.dbusService = None
        self.vrmInstanceID = vrmInstanceID
        self.rootService = rootService
    
    def onMqttMessage(self, client, userdata, msg):
      try:
        messagePlain = str(msg.payload)[2:-1]

        if (messagePlain == ""):
            d(self, "Empty message on topic {0}. Ignoring.".format(msg.topic))
            return

        d(self, "Received message on: " + msg.topic)

        if (msg.topic == self.valueTopic):
            self.value = float(messagePlain)  
        
        if (msg.topic == self.voltageTopic):
            self.voltage = float(messagePlain)      

        if (msg.topic == self.currentTopic):
            self.current = float(messagePlain)      
        
        self.publishOnDbus()
      except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        self.rootService.publishServiceMessage(self.rootService, "Initializing dbus-service for sensor: {0}".format(self.key))
        self.serviceType = "com.victronenergy.dcsystem"
        self.serviceName = self.serviceType + Globals.esEssTagService + "_MqttDC_" + str(self.key)
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection(), register=False)
        
        #Mgmt-Infos
        self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "dbus")

        # Create the mandatory objects
        self.dbusService.add_path('/ProductId', 65535)
        self.dbusService.add_path('/ProductName', "{0} MqttDC".format(Globals.esEssTag)) 
        self.dbusService.add_path('/Latency', None)    
        self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/Connected', 1)
        self.dbusService.add_path('/Serial', "1337")
        
        self.dbusService.add_path('/Dc/0/Voltage', None)
        self.dbusService.add_path('/Dc/0/Current', None)
        self.dbusService.add_path('/Dc/0/Power', None)
        self.dbusService.add_path('/CustomName', self.customName)

        self.dbusService.register()

    def publishOnDbus(self):
        if (self.dbusService is not None):
            self.dbusService["/Dc/0/Power"] = self.value
            self.dbusService["/CustomName"] = self.customName
        
        if (self.voltageTopic is not None):
            self.dbusService["/Dc/0/Voltage"] = self.voltage
        
        if (self.currentTopic is not None):
            self.dbusService["/Dc/0/Current"] = self.current

