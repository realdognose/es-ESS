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

class MqttTemperature(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.temperatureSensors: Dict[str, TemperatureSensor] = {}
        self.forwardedTopicsPastMinute = 0
        
        #Load all topics we should export from DBus to Mqtt and start listening for changes.
        #upon change, export according to the setup rules. 
        try:
            d(self, "Scanning config for temp sensors")
            for k in self.config.sections():
                if (k.startswith("MqttTemperature:")):
                    parts = k.split(':')
                    key = parts[1].strip()
                    valueTopic = self.config[k]["Topic"]
                    humidityTopic = self.config[k]["TopicHumidity"] if "TopicHumidity" in self.config[k] else None
                    pressureTopic = self.config[k]["TopicPressure"] if "TopicPressure" in self.config[k] else None
                    self.temperatureSensors[key] = TemperatureSensor(self, key, self.config[k]["CustomName"], valueTopic, humidityTopic, pressureTopic, int(self.config[k]["VRMInstanceID"]))

            i(self, "Found {0} TemperatureSensors.".format(len(self.temperatureSensors)))
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        for (sensor) in self.temperatureSensors.values():
            sensor.initDbusService()

    def initDbusSubscriptions(self):
        pass
        
    def initWorkerThreads(self):
        pass

    def initMqttSubscriptions(self):
        for sensor in self.temperatureSensors.values():
            self.registerMqttSubscription(sensor.valueTopic, callback=sensor.onMqttMessage)

            if (sensor.humidityTopic is not None):
                self.registerMqttSubscription(sensor.humidityTopic, callback=sensor.onMqttMessage)

            if (sensor.pressureTopic is not None):
                self.registerMqttSubscription(sensor.pressureTopic, callback=sensor.onMqttMessage)

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       pass

class TemperatureSensor:
    def __init__(self, rootService, key, customName, valueTopic, humidityTopic, pressureTopic, vrmInstanceID):
        self.key = key
        self.customName = customName
        self.valueTopic = valueTopic
        self.humidityTopic = humidityTopic
        self.pressureTopic = pressureTopic
        self.value = 0.0
        self.humidity = 0.0
        self.pressure = 0.0
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
            self.rootService.publishServiceMessage(self.rootService, "New Temperature Value {0} on Sensor {1}".format(self.value, self.key))
        
        if (msg.topic == self.humidityTopic):
            self.humidity = float(messagePlain)      
            self.rootService.publishServiceMessage(self.rootService, "New Humidity Value {0} on Sensor {1}".format(self.humidity, self.key))

        if (msg.topic == self.pressureTopic):
            self.pressure = float(messagePlain)      
            self.rootService.publishServiceMessage(self.rootService, "New Pressure Value {0} on Sensor {1}".format(self.pressure, self.key))
        
        self.publishOnDbus()
      except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        self.rootService.publishServiceMessage(self.rootService, "Initializing dbus-service for sensor: {0}".format(self.key))
        self.serviceType = "com.victronenergy.temperature"
        self.serviceName = self.serviceType + ".esESS.MqttTemperature_" + str(self.vrmInstanceID)
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
        
        #Mgmt-Infos
        self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "dbus")

        # Create the mandatory objects
        self.dbusService.add_path('/ProductId', 65535)
        self.dbusService.add_path('/ProductName', "{0} MqttTemperatureSensor".format(Globals.esEssTag)) 
        self.dbusService.add_path('/Latency', None)    
        self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/Connected', 1)
        self.dbusService.add_path('/Serial', "1337")
        
        self.dbusService.add_path('/Temperature', None)
        self.dbusService.add_path('/Humidity', None)
        self.dbusService.add_path('/Pressure', None)
        self.dbusService.add_path('/TemperatureType', 2) #Generic
        self.dbusService.add_path('/CustomName', self.customName)

    def publishOnDbus(self):
        if (self.dbusService is not None):
            self.dbusService["/Temperature"] = self.value
            self.dbusService["/CustomName"] = self.customName
        
        if (self.humidityTopic is not None):
            self.dbusService["/Humidity"] = self.humidity
        
        if (self.pressureTopic is not None):
            self.dbusService["/Pressure"] = self.pressure

