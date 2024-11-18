import os
import platform
import sys
from typing import Dict
import dbus # type: ignore
import dbus.service # type: ignore
import inspect
import pprint
import time
import os
import sys

# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore

# esEss imports
from Helper import i, c, d, w, e, t, dbusConnection
import Globals
from esESSService import esESSService

class MqttPVInverter(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.mqttPVInverters: Dict[str, MqttPVInverterInstance] = {}
        self.forwardedTopicsPastMinute = 0
        
        #Load all topics we should export from DBus to Mqtt and start listening for changes.
        #upon change, export according to the setup rules. 
        try:
            d(self, "Scanning config for MqttPVInverters")
            for k in self.config.sections():
                if (k.startswith("MqttPVInverter:")):
                    d(self, "Found: " + k)
                    parts = k.split(':')
                    key = parts[1].strip()
                    self.mqttPVInverters[key] = MqttPVInverterInstance(self, key, self.config[k])

            i(self, "Found {0} MqttPVInverters.".format(len(self.mqttPVInverters)))
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        for (inverter) in self.mqttPVInverters.values():
            inverter.initDbusService()

    def initDbusSubscriptions(self):
        pass
        
    def initWorkerThreads(self):
        self.registerWorkerThread(self._checkStale, 5000)
        pass

    def initMqttSubscriptions(self):
        for inverter in self.mqttPVInverters.values():
            self.registerMqttSubscription(inverter.l1VoltageTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l2VoltageTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l3VoltageTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l1PowerTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l2PowerTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l3PowerTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.totalPowerTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l1CurrentTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l2CurrentTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l3CurrentTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l1EnergyForwardedTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l2EnergyForwardedTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.l3EnergyForwardedTopic, callback=inverter.onMqttMessage)
            self.registerMqttSubscription(inverter.totalEnergyForwardedTopic, callback=inverter.onMqttMessage)

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       pass

    def _checkStale(self):
        for (inverter) in self.mqttPVInverters.values():
            if (time.time() - inverter.lastMessageReceived > 5):
                w(self, "PVInverter detected stale: {0}".format(inverter.customName))
                inverter.setStale()

class MqttPVInverterInstance:
    def __init__(self, rootService, key, configValues):
        self.key = key
        self.customName = configValues["CustomName"]
        self.dbusService = None
        self.vrmInstanceID = int(configValues["VRMInstanceID"])
        self.inverterPosition = int(configValues["Position"])
        self.l1VoltageTopic = configValues["L1VoltageTopic"]
        self.l2VoltageTopic = configValues["L2VoltageTopic"]
        self.l3VoltageTopic = configValues["L3VoltageTopic"]
        self.l1PowerTopic = configValues["L1PowerTopic"]
        self.l2PowerTopic = configValues["L2PowerTopic"]
        self.l3PowerTopic = configValues["L3PowerTopic"]
        self.totalPowerTopic = configValues["TotalPowerTopic"]
        self.l1CurrentTopic = configValues["L1CurrentTopic"]
        self.l2CurrentTopic = configValues["L2CurrentTopic"]
        self.l3CurrentTopic = configValues["L3CurrentTopic"]
        self.l1EnergyForwardedTopic = configValues["L1EnergyForwardedTopic"]
        self.l2EnergyForwardedTopic = configValues["L2EnergyForwardedTopic"]
        self.l3EnergyForwardedTopic = configValues["L3EnergyForwardedTopic"]
        self.totalEnergyForwardedTopic = configValues["TotalEnergyForwardedTopic"]
        self.lastMessageReceived = 0
        self.isStale=False
        self.rootService = rootService
    
    def onMqttMessage(self, client, userdata, msg):
      try:
        messagePlain = str(msg.payload)[2:-1]

        if (messagePlain == ""):
            d(self, "Empty message on topic {0}. Ignoring.".format(msg.topic))
            return

        t(self, "Received message on: " + msg.topic)
        self.lastMessageReceived = time.time()
        if (self.isStale):
            self.isStale=False
            self.dbusService['/Connected'] = 1
            self.dbusService['/StatusCode'] = 7
            self.rootService.publishServiceMessage(self.rootService, "Inverter is online: {0} ".format(self.customName))

        #Voltages
        if (msg.topic == self.l1VoltageTopic):
            self.dbusService['/Ac/L1/Voltage'] = float(messagePlain)
        
        elif (msg.topic == self.l2VoltageTopic):
            self.dbusService['/Ac/L2/Voltage'] = float(messagePlain)

        elif (msg.topic == self.l3VoltageTopic):
            self.dbusService['/Ac/L3/Voltage'] = float(messagePlain)

        #Currents
        elif (msg.topic == self.l1CurrentTopic):
            self.dbusService['/Ac/L1/Current'] = float(messagePlain)
        
        elif (msg.topic == self.l2CurrentTopic):
            self.dbusService['/Ac/L2/Current'] = float(messagePlain)

        elif (msg.topic == self.l3CurrentTopic):
            self.dbusService['/Ac/L3/Current'] = float(messagePlain)

        #Powers
        elif (msg.topic == self.l1PowerTopic):
            self.dbusService['/Ac/L1/Power'] = float(messagePlain)
        
        elif (msg.topic == self.l2PowerTopic):
            self.dbusService['/Ac/L2/Power'] = float(messagePlain)

        elif (msg.topic == self.l3PowerTopic):
            self.dbusService['/Ac/L3/Power'] = float(messagePlain)

        #EnergyForwardeds
        elif (msg.topic == self.l1EnergyForwardedTopic):
            self.dbusService['/Ac/L1/Energy/Forward'] = float(messagePlain)
        
        elif (msg.topic == self.l2EnergyForwardedTopic):
            self.dbusService['/Ac/L2/Energy/Forward'] = float(messagePlain)

        elif (msg.topic == self.l3EnergyForwardedTopic):
            self.dbusService['/Ac/L3/Energy/Forward'] = float(messagePlain)

        #Totals
        if (msg.topic == self.totalPowerTopic):
            self.dbusService['/Ac/Power'] = float(messagePlain)

        if (msg.topic == self.totalEnergyForwardedTopic):
            self.dbusService['/Ac/Energy/Forward'] = float(messagePlain)

      except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        self.rootService.publishServiceMessage(self.rootService, "Initializing dbus-service for PVInverter: {0}".format(self.key))
        self.serviceType = "com.victronenergy.pvinverter"
        self.serviceName = self.serviceType + "." + Globals.esEssTagService + "_MqttPVInverter_" + str(self.key)
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection(), register=False)
        
        #Mgmt-Infos
        self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "dbus")

        # Create the mandatory objects
        self.dbusService.add_path('/ProductId', 0xA144)
        self.dbusService.add_path('/DeviceType', 345) 
        self.dbusService.add_path('/Role', "pvinverter")
        self.dbusService.add_path('/ProductName', "{0} MqttPVInverter".format(Globals.esEssTag)) 
        self.dbusService.add_path('/Latency', None)    
        self.dbusService.add_path('/StatusCode', 7)   
        self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/Connected', 1)
        self.dbusService.add_path('/Position', self.inverterPosition)
        self.dbusService.add_path('/Serial', "1337")
        self.dbusService.add_path('/CustomName', self.customName)

        #inverter props
        self.dbusService.add_path('/Ac/Power', 0)
        self.dbusService.add_path('/Ac/Energy/Forward', 0)

        for x in range(1,4):
            self.dbusService.add_path('/Ac/L' + str(x) + '/Voltage', 0)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Current', 0)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Power', 0)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Energy/Forward', 0)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Energy/Reverse', 0)

        self.dbusService.register()
    
    def setStale(self):
        self.isStale=True
        self.dbusService["/Connected"] = 0
        self.dbusService['/StatusCode'] = 10
        self.dbusService['/Ac/Power'] = None
        self.dbusService['/Ac/L1/Voltage'] = None
        self.dbusService['/Ac/L2/Voltage'] = None
        self.dbusService['/Ac/L3/Voltage'] = None
        self.dbusService['/Ac/L1/Current'] = None
        self.dbusService['/Ac/L2/Current'] = None
        self.dbusService['/Ac/L3/Current'] = None
        self.dbusService['/Ac/L1/Power'] = None
        self.dbusService['/Ac/L2/Power'] = None
        self.dbusService['/Ac/L3/Power'] = None

