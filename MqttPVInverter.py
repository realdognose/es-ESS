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

            self.enableZeroFeedin = self.config["MqttPvInverter"]["EnableZeroFeedin"].lower() == "true"
            self.enablePvShutdown = self.config["MqttPvInverter"]["EnablePvShutdown"].lower() == "true"
            self.zeroFeedinScaleStep = float(self.config["MqttPvInverter"]["ZeroFeedinScaleStep"])
            self.zeroFeedinDistance = float(self.config["MqttPvInverter"]["ZeroFeedinDistance"])
            self.zeroFeedinStartSoc = float(self.config["MqttPvInverter"]["ZeroFeedinStartSoc"])

            if self.enableZeroFeedin:
                i(self, "Enabling ZeroFeedin through DTU")
                for key, inv in self.mqttPVInverters.items():
                    inv.throttle = 1.0 / len(self.mqttPVInverters)
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        for (inverter) in self.mqttPVInverters.values():
            inverter.initDbusService()

    def initDbusSubscriptions(self):
        #Need consumption to scale on for ZeroFeedin, when battery is fully charged.
        self.consumptionL1Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L1/Power")
        self.consumptionL2Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L2/Power")
        self.consumptionL3Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L3/Power")

        #TODO: Need Grid Connected Value to determine if we are actually grid connected. 
        self.noPhasesDbus       = self.registerDbusSubscription("com.victronenergy.system", "/Ac/ActiveIn/NumberOfPhases")
        self.socDbus            = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Soc")

        #Need PV Disabled Value to eventually shutdown inverters completly. 
        self.pvDisabled         = self.registerDbusSubscription("com.victronenergy.system", "/Pv/Disabled")
        
    def initWorkerThreads(self):
        self.registerWorkerThread(self._checkStale, 5000)

        if self.enableZeroFeedin:
            self.registerWorkerThread(self._dtuZeroFeedin, 10000)

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
    
    def _dtuZeroFeedin(self):
        try:
            #Check on-grid, else Frequency shifting will control the inverters.
            if self.noPhasesDbus.value is not None and self.socDbus.value is not None and self.socDbus.value >= self.zeroFeedinStartSoc:
                consumption = self.consumptionL1Dbus.value + self.consumptionL2Dbus.value + self.consumptionL3Dbus.value
                target = max(consumption - self.zeroFeedinDistance, 0)

                actual = {key: inv.total_power for key, inv in self.mqttPVInverters.items()}
                total = sum(actual.values())
                error = target - total

                i(self, "Consumption is {}W, with a distance of {}W, we are targeting for {}W inverter power.".format(consumption, self.zeroFeedinDistance, target))

                #Adjust proportionally
                for key, inv in self.mqttPVInverters.items():
                    #Only adjust if this inverter is producing
                    if actual[key] > 0 and inv.dtuControlTopic is not None:
                        share = actual[key] / total if total > 0 else 1.0/len(self.mqttPVInverters)
                        t = inv.throttle
                        c = share * (error / target)
                        if c >= 0:
                            t += min(self.zeroFeedinScaleStep, c)
                        else:
                            t -= min(self.zeroFeedinScaleStep, c * -1)

                        t = min(max(t, 0.0), 1.0)  # Clamp to 0..1
                        inv.throttle = t
            else:
                for key, inv in self.mqttPVInverters.items():
                    inv.throttle = 1.0
        except Exception as ex:
            c(self, "Exception during zero feedin calculation", exc_info=ex)

class MqttPVInverterInstance:
    def __init__(self, rootService:MqttPVInverter, key, configValues):
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
        self.dtuControlTopic = configValues["DtuControlTopic"] if "DtuControlTopic" in configValues else None
        self.lastMessageReceived = 0
        self.isStale=False
        self.rootService:MqttPVInverter = rootService
        self.l1power = 0 
        self.l2power = 0
        self.l3power = 0
        self._throttle:float = 1
    
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
            self.l1power = float(messagePlain)
            self.dbusService['/Ac/L1/Power'] = float(messagePlain)
        
        elif (msg.topic == self.l2PowerTopic):
            self.l2power = float(messagePlain)
            self.dbusService['/Ac/L2/Power'] = float(messagePlain)

        elif (msg.topic == self.l3PowerTopic):
            self.l3power = float(messagePlain)
            self.dbusService['/Ac/L3/Power'] = float(messagePlain)

        #EnergyForwardeds
        elif (msg.topic == self.l1EnergyForwardedTopic):
            if messagePlain != "" and round(float(messagePlain)) != 0:
                self.dbusService['/Ac/L1/Energy/Forward'] = float(messagePlain)
        
        elif (msg.topic == self.l2EnergyForwardedTopic):
            if messagePlain != "" and round(float(messagePlain)) != 0:
                self.dbusService['/Ac/L2/Energy/Forward'] = float(messagePlain)

        elif (msg.topic == self.l3EnergyForwardedTopic):
            if messagePlain != "" and round(float(messagePlain)) != 0:
                self.dbusService['/Ac/L3/Energy/Forward'] = float(messagePlain)

        #Totals
        if (msg.topic == self.totalPowerTopic):
            self.dbusService['/Ac/Power'] = float(messagePlain)

        if (msg.topic == self.totalEnergyForwardedTopic):
            if messagePlain != "" and round(float(messagePlain)) != 0:
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
        self.dbusService.add_path('/Ac/Power', None)
        self.dbusService.add_path('/Ac/Energy/Forward', None)

        for x in range(1,4):
            self.dbusService.add_path('/Ac/L' + str(x) + '/Voltage', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Current', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Power', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Energy/Forward', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Energy/Reverse', None)

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

    @property
    def total_power(self) -> float:
        return self.l1power + self.l2power + self.l3power

    @property
    def throttle(self) -> float:
        return self._throttle
    
    @throttle.setter
    def throttle(self, v):
        self._throttle = v

        if self.dtuControlTopic is not None:
            i(self, "Setting limit for {} to {}%".format(self.customName, v*100))
            self.rootService.publishMainMqtt(self.dtuControlTopic + "/cmd/limit_nonpersistent_relative", v * 100)