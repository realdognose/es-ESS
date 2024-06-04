
from builtins import int
import configparser
import json
import logging
from math import floor
import os
import platform
import sys
from time import sleep
import time
if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

import paho.mqtt.client as mqtt # type: ignore

# victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService # type: ignore

# esEss imports
import Globals
from Globals import getFromGlobalStoreValue
import Helper
from Helper import i, c, d, w, e, dbusConnection
from Wattpilot import Wattpilot, Event

class FroniusWattpilotService:

    

    def _froniusHandleChangedValue(self, path, value):
        i(self, "User/cerbo/vrm updated " + str(path) + " to " + str(value))

        if (path == "/SetCurrent"):
            self.wattpilot.set_power(value)
        elif (path == "/StartStop"):
            if (value == 0):
                self.wattpilot.set_start_stop(1)
            elif (value == 1):
                #force start
                self.wattpilot.set_start_stop(2)
                
        elif (path == "/Mode"):
            priorMode = self.mode
            self.switchMode(priorMode, value)
       
        self.dumpEvChargerInfo()
        return True

    def wattpilotShellSet(self, key, value):
        self.wattpilotMQTTClient.publish(self.topic + "/properties/" + key + "/set", value, 2)

   # When Mode is switched, different settings needs to be enabled/disabled. 
   # 0 = Manual => User control, only forward commands from VRM to wattpilot and read wattpilotstats.
   # 1 = Automatic => Overhead Mode, disable VRM Control, reject wattpilot changes, register pv overhead observer.
   # 2 = Scheduled => Nightly low-price mode, TODO
    def switchMode(self, fromMode, toMode):
        d("FroniusWattpilotService", "Switching Mode from " + str(fromMode) + " to " + str(toMode))
        self.mode = toMode
        self.dbusService["/Mode"] = toMode
        if (fromMode == 0 and toMode == 1):
            self.autostart = 1

        elif (fromMode == 1 and toMode == 0):
            self.autostart = 0
         
    def _automaticTick(self):
        #if the car is not connected, we can greatly reduce system load.
        #just dump values every 5 minutes then. If car is connected, we need
        #to perform updates every tick.
        if (self.wattpilot.carConnected or self.lastVarDump < (time.time() - 300)):
            self.lastVarDump = time.time()

            try:
                Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/vrmInstanceID", self.config["FroniusWattpilot"]["VRMInstanceID_OverheadRequest"])
                Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/customName", "Wattpilot")
                Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/ignoreBatReservation", "false")
                Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/minimum", 6*230)
                Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/stepSize", 230)
            
                #Create a request for power consumption. 
                if (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode == 1):
                    #Car connected, not charging, automatic mode. Create  a request.
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/automatic", "true")
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/consumption", 0)
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/request", 3*16*230)
                    
                elif (not self.wattpilot.carConnected):
                    #Car not connected, no request
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/consumption", 0)
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/request", 0)

                if (self.mode == 0):
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/automatic", "false")
                elif (self.mode == 1):
                    #Check, if we have an allowance in auto mode? .
                    allowance = getFromGlobalStoreValue(self.allowanceTopic, 0)
                    d(self, "Current Allowance is: " + str(allowance))

                    if (allowance >= 6 * 230):
                        targetAmps = int(floor(max(min(16, allowance / 230), 6)))
                        d(self, "Target Amps that is: " + str(targetAmps))
                        if (self.wattpilot.power > 0):
                            d(self, "Currently charging, adjusting power.")
                            #charging, adjust current
                            self.wattpilot.set_power(targetAmps)
                        else:
                            i(self, "Enough Allowance, but NOT charging, starting.")
                            if (self.lastOnOffTime < (time.time() - self.minimumOnOffSeconds)):
                                self.wattpilot.set_phases(1)
                                self.wattpilot.set_power(targetAmps)
                                self.wattpilot.set_start_stop(2)
                                self.lastOnOffTime = time.time()
                            else:
                                w("Start-Charge delayed due to on/off cooldown.")
                    else:
                        if (self.wattpilot.power):
                            i(self, "NO Allowance, stopping charging.")
                            if (self.lastOnOffTime < (time.time() - self.minimumOnOffSeconds)):
                                #stop charging
                                self.wattpilot.set_start_stop(2)
                                self.lastOnOffTime = time.time()
                            else:
                                w("Stop-Charge delayed due to on/off cooldown.")

                #update UI anyway
                self.dumpEvChargerInfo()            

            except Exception as ex:
                c(self, "Critical Exception logged.", exc_info=ex)

        return True 

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
        self.lastPhaseSwitchTime = 0
        self.lastOnOffTime = 0
        self.minimumOnOffSeconds = int(self.config["FroniusWattpilot"]["MinOnOffSeconds"])
        self.minimumPhaseSwitchSeconds = int(self.config["FroniusWattpilot"]["MinPhaseSwitchSeconds"])
        self.lastVarDump = 0
        self.maxCurrent = 16
        self.mode = 0 #Start in manual mode, switch when initialized.
        self.autostart = 0 

        #register on dbus as EV-Charger.
        self.vrmInstanceID = self.config['FroniusWattpilot']['VRMInstanceID']
        self.serviceType = "com.victronenergy.evcharger"
        self.serviceName = self.serviceType + ".es-ess.FroniusWattpilot_" + self.vrmInstanceID
        i(self, "Registering service as: " + self.serviceName)
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())

        #dump root information about our service and register paths.
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "Local DBus Injection")

        # Create the mandatory objects
        self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
        self.dbusService.add_path('/ProductId', 65535)
        self.dbusService.add_path('/ProductName', "Fronius Wattpilot") 
        self.dbusService.add_path('/CustomName', "Fronius Wattpilot") 
        self.dbusService.add_path('/Latency', None)    
        self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/Connected', 1)
        self.dbusService.add_path('/Serial', "1337")
        self.dbusService.add_path('/LastUpdate', 0)

        self.dbusService.add_path('/Ac/Energy/Forward', 0)
        self.dbusService.add_path('/Ac/L1/Power', 0)
        self.dbusService.add_path('/Ac/L2/Power', 0)
        self.dbusService.add_path('/Ac/L3/Power', 0)
        self.dbusService.add_path('/Ac/Power', 0)
        self.dbusService.add_path('/Current', 0)
        self.dbusService.add_path('/AutoStart', self.autostart, writeable=False)
        self.dbusService.add_path('/SetCurrent', 0, writeable=True, onchangecallback=self._froniusHandleChangedValue)
        self.dbusService.add_path('/Status', 0)
        self.dbusService.add_path('/MaxCurrent', self.maxCurrent)
        self.dbusService.add_path('/Mode', self.mode, writeable=True, onchangecallback=self._froniusHandleChangedValue)
        self.dbusService.add_path('/Position', int(self.config['FroniusWattpilot']['Position'])) #
        self.dbusService.add_path('/Model', "Fronius Wattpilot")
        self.dbusService.add_path('/StartStop', 0, writeable=True, onchangecallback=self._froniusHandleChangedValue)
        self.dbusService.add_path('/ChargingTime', 0)

        self.switchMode(0,1)

        #Create the Wattpilot object and connect. 
        self.wattpilot = Wattpilot(self.config["FroniusWattpilot"]["Host"], self.config["FroniusWattpilot"]["Password"])
        self.wattpilot._auto_reconnect = True
        self.wattpilot._reconnect_interval = 30
        self.wattpilot.connect()
        Helper.waitTimeout(lambda: self.wattpilot.connected, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")

        #subscribe to PV Overhead Allowance topic.  
        self.allowanceTopic = "N/" + self.config["Default"]["VRMPortalID"] + "/settings/" + self.config["PVOverheadDistributor"]["VRMInstanceID"] + "/requests/wattpilot/allowance"
        Globals.mqttClient.subscribe(self.allowanceTopic)

        self.dumpEvChargerInfo()
        gobject.timeout_add(int(5000), self._automaticTick)

    def dumpEvChargerInfo(self):
        #method is called, whenever new information arrive through mqtt. 
        #just dump the information we have.
        self.dbusService["/Ac/L1/Power"] = self.wattpilot.power1 * 1000 if (self.wattpilot.power1 is not None) else 0
        self.dbusService["/Ac/L2/Power"] = self.wattpilot.power2 * 1000 if (self.wattpilot.power2 is not None) else 0
        self.dbusService["/Ac/L3/Power"] = self.wattpilot.power3 * 1000 if (self.wattpilot.power3 is not None) else 0
        self.dbusService["/Ac/Power"] = self.wattpilot.power * 1000 if (self.wattpilot.power is not None) else 0
        self.dbusService["/Current"] = self.wattpilot.amp if (self.wattpilot.amp is not None) else 0

        i(self, "Car connected? " + str(self.wattpilot.carConnected))

        if (self.wattpilot.carConnected and self.wattpilot.power > 0):
            self.dbusService["/Status"] = 2 # charging

        elif (not self.wattpilot.carConnected):
            self.dbusService["/Status"] = 0 # Disconnected

            if (self.config["FroniusWattpilot"]["ResetChargedEnergyCounter"].lower() == "ondisconnect"):
                self.dbusService["/Ac/Energy/Forward"]  = 0.0 #Reset Session Charge Counter.
        
        elif (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode==1):
            self.dbusService["/Status"] = 4 # Waiting Sun.

        elif (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode==0):
            self.dbusService["/Status"] = 1 # Connected/Idle

        if (self.wattpilot.energyCounterSinceStart is not None and self.wattpilot.carConnected):
            self.dbusService["/Ac/Energy/Forward"] = self.wattpilot.energyCounterSinceStart / 1000
        
        elif (self.wattpilot.energyCounterSinceStart is not None and not self.wattpilot.carConnected and self.config["FroniusWattpilot"]["ResetChargedEnergyCounter"].lower() == "onconnect"):
            self.dbusService["/Ac/Energy/Forward"] = self.wattpilot.energyCounterSinceStart / 1000

        else:
            self.dbusService["/Ac/Energy/Forward"] = 0.0
        
        self.dbusService["/MaxCurrent"] = self.maxCurrent
        self.dbusService["/AutoStart"] = self.autostart
        self.dbusService["/SetCurrent"] = self.wattpilot.amp
