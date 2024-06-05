
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
                Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/minimum", int(floor(self.wattpilot.voltage1 * 6)))
                Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/stepSize", int(floor(self.wattpilot.voltage1))) #assuming all phases are about equal and stepSize is 1 amp.
            
                #Create a request for power consumption. 
                if (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode == 1):
                    #Car connected, not charging, automatic mode. Create  a request.
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/automatic", "true")
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/consumption", 0)
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/request", int(floor(3 * self.wattpilot.ampLimit * self.wattpilot.voltage1)))
                    
                elif (not self.wattpilot.carConnected):
                    #Car not connected, no request
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/consumption", 0)
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/request", 0)

                if (self.mode == 0):
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/automatic", "false")
                elif (self.mode == 1):
                    Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/request", int(floor(3 * self.wattpilot.ampLimit * self.wattpilot.voltage1)))
                    #Check, if we have an allowance in auto mode? .
                    allowance = getFromGlobalStoreValue(self.allowanceTopic, 0)
                    d(self, "Current Allowance is: " + str(allowance))
                    
                    #increment charging time. Tick is 5 seconds, that is precise enough.
                    if (self.wattpilot.power > 0):
                        self.chargingTime += 5

                    if (allowance >= self.wattpilot.voltage1 * 6):
                        targetAmps = int(floor(max(allowance / self.wattpilot.voltage1, 6)))
                        targetAmps = min(self.wattpilot.ampLimit * 3, targetAmps) #obey limits.

                        d(self, "Target Amps that is: " + str(targetAmps))

                        if (self.wattpilot.power > 0):
                            #charging, adjust current
                            d(self, "Currently charging, adjusting power.")
                            self.adjustChargeCurrent(targetAmps)
                        else:
                            i(self, "Enough Allowance, but NOT charging, starting.")
                           
                            onOffCooldownSeconds = self.getOnOffCooldownSeconds()
                            if (onOffCooldownSeconds <= 0):
                                i(self, "START send!")
                                self.wattpilot.set_phases(1)
                                self.currentPhaseMode=1
                                self.wattpilot.set_power(targetAmps)
                                self.wattpilot.set_start_stop(2)
                                self.lastOnOffTime = time.time()
                                self.dbusService["/StartStop"] = 1
                            else:
                                w(self, "Start-Charge delayed due to on/off cooldown: " + str(onOffCooldownSeconds) + "s")
                    else:
                        if (self.wattpilot.power):
                            i(self, "NO Allowance, stopping charging.")
                            onOffCooldownSeconds = self.getOnOffCooldownSeconds()
                            if (onOffCooldownSeconds <= 0):
                                #stop charging
                                i(self, "STOP send!")
                                self.wattpilot.set_start_stop(1)
                                self.lastOnOffTime = time.time()
                                self.dbusService["/StartStop"] = 0
                            else:
                                w(self, "Stop-Charge delayed due to on/off cooldown: " + str(onOffCooldownSeconds) + "s")

                #update UI anyway
                self.dumpEvChargerInfo()            

            except Exception as ex:
                c(self, "Critical Exception logged.", exc_info=ex)

        return True 

    def getOnOffCooldownSeconds(self):
        return max(0, self.lastOnOffTime + self.minimumOnOffSeconds- time.time())
    
    def getPhaseSwitchCooldownSeconds(self):
        return max(0, self.lastPhaseSwitchTime + self.minimumPhaseSwitchSeconds- time.time())

    def adjustChargeCurrent(self, targetAmps):
        desiredPhaseMode = 3 if targetAmps > self.wattpilot.ampLimit else 1
        d(self, "Desired PhaseMode: " + str(desiredPhaseMode))
        
        if (self.currentPhaseMode == desiredPhaseMode):
            targetAmps = int(floor(targetAmps / self.currentPhaseMode))
            #Just adjust, no phasemode change required. 
            i(self, "Adjusting charge current to: " + str(targetAmps))
            self.wattpilot.set_power(targetAmps)

        elif (self.currentPhaseMode != desiredPhaseMode):
            i(self, "Total amps required is: " + str(targetAmps) + ". Hence switching from phasemode " + str(self.currentPhaseMode) + " to " + str(desiredPhaseMode))
            targetAmps = int(floor(targetAmps / desiredPhaseMode))
            i(self, "That'll be " + str(targetAmps) + " on " + str(desiredPhaseMode))

            phaseSwitchCooldownSeconds = self.getPhaseSwitchCooldownSeconds()
            if (phaseSwitchCooldownSeconds <= 0):
                i(self, "Switching to Phase-Mode: " + str(desiredPhaseMode) + ". Send.")
                self.lastPhaseSwitchTime = time.time()
                self.wattpilot.set_phases(desiredPhaseMode)
                self.currentPhaseMode = desiredPhaseMode
                self.wattpilot.set_power(targetAmps)
            else:
                if (self.currentPhaseMode == 1):
                    w(self, "Attempted to switch to Phase-Mode " + str(desiredPhaseMode) + ", but cooldown is active! Using " + str(self.wattpilot.ampLimit) + " Amps on Phase-Mode " + str(self.currentPhaseMode) + " until cooldown is over:" + str(phaseSwitchCooldownSeconds) + "s")
                    self.wattpilot.set_power(self.wattpilot.ampLimit)
                elif (self.currentPhaseMode == 3):
                    w(self, "Attempted to switch to Phase-Mode " + str(desiredPhaseMode) + ", but cooldown is active! Using 6 Amps on Phase-Mode " + str(self.currentPhaseMode) + " until cooldown is over:" + str(phaseSwitchCooldownSeconds) + "s")
                    self.wattpilot.set_power(6)                



    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
        self.lastPhaseSwitchTime = 0
        self.lastOnOffTime = 0
        self.minimumOnOffSeconds = int(self.config["FroniusWattpilot"]["MinOnOffSeconds"])
        self.minimumPhaseSwitchSeconds = int(self.config["FroniusWattpilot"]["MinPhaseSwitchSeconds"])
        self.lastVarDump = 0
        self.chargingTime = 0
        self.currentPhaseMode = 1
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
        self.dbusService.add_path('/Ac/L1/Voltage', 0)
        self.dbusService.add_path('/Ac/L2/Voltage', 0)
        self.dbusService.add_path('/Ac/L3/Voltage', 0)
        self.dbusService.add_path('/Ac/L1/Current', 0)
        self.dbusService.add_path('/Ac/L2/Current', 0)
        self.dbusService.add_path('/Ac/L3/Current', 0)
        self.dbusService.add_path('/Ac/L1/PowerFactor', 0)
        self.dbusService.add_path('/Ac/L2/PowerFactor', 0)
        self.dbusService.add_path('/Ac/L3/PowerFactor', 0)
        self.dbusService.add_path('/ChargingTime', self.chargingTime)
        self.dbusService.add_path('/Ac/Power', 0)
        self.dbusService.add_path('/Current', 0)
        self.dbusService.add_path('/AutoStart', self.autostart, writeable=False)
        self.dbusService.add_path('/SetCurrent', 0, writeable=True, onchangecallback=self._froniusHandleChangedValue)
        self.dbusService.add_path('/Status', 0)
        self.dbusService.add_path('/MaxCurrent', 0)
        self.dbusService.add_path('/Mode', self.mode, writeable=True, onchangecallback=self._froniusHandleChangedValue)
        self.dbusService.add_path('/Position', int(self.config['FroniusWattpilot']['Position'])) #
        self.dbusService.add_path('/Model', "Fronius Wattpilot")
        self.dbusService.add_path('/StartStop', 0, writeable=True, onchangecallback=self._froniusHandleChangedValue)

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
        self.dbusService["/Ac/L1/Voltage"] = self.wattpilot.voltage1  if (self.wattpilot.voltage1 is not None) else 0
        self.dbusService["/Ac/L2/Voltage"] = self.wattpilot.voltage2  if (self.wattpilot.voltage2 is not None) else 0
        self.dbusService["/Ac/L3/Voltage"] = self.wattpilot.voltage3  if (self.wattpilot.voltage3 is not None) else 0
        self.dbusService["/Ac/L1/Current"] = self.wattpilot.amps1  if (self.wattpilot.amps1 is not None and self.wattpilot.power>0) else 0
        self.dbusService["/Ac/L2/Current"] = self.wattpilot.amps2  if (self.wattpilot.amps2 is not None and self.wattpilot.power>0) else 0
        self.dbusService["/Ac/L3/Current"] = self.wattpilot.amps3  if (self.wattpilot.amps3 is not None and self.wattpilot.power>0) else 0
        self.dbusService["/Ac/L1/PowerFactor"] = self.wattpilot.powerFactor1  if (self.wattpilot.powerFactor1 is not None and self.wattpilot.power>0) else 0
        self.dbusService["/Ac/L2/PowerFactor"] = self.wattpilot.powerFactor2  if (self.wattpilot.powerFactor2 is not None and self.wattpilot.power>0) else 0
        self.dbusService["/Ac/L3/PowerFactor"] = self.wattpilot.powerFactor3  if (self.wattpilot.powerFactor3 is not None and self.wattpilot.power>0) else 0
        self.dbusService["/Ac/Power"] = self.wattpilot.power * 1000 if (self.wattpilot.power is not None) else 0
        self.dbusService["/Current"] = self.wattpilot.amp if (self.wattpilot.amp is not None and self.wattpilot.power>0) else 0

        #Also write total power back to pvOverheadDistributor, in case we are in automatic mode. 
        d(self, "Car connected? " + str(self.wattpilot.carConnected))
        if (self.mode == 1):
            Globals.mqttClient.publish("W/" + self.config["Default"]["VRMPortalID"] + "/esEss/PVOverheadDistributor/requests/wattpilot/consumption", self.wattpilot.power * 1000)

        updateStatus = self.dbusService["/Status"]
        if (self.wattpilot.carConnected and self.wattpilot.power > 0):
            updateStatus = 2 # charging

        elif (not self.wattpilot.carConnected):
            updateStatus = 0 # Disconnected

            if (self.config["FroniusWattpilot"]["ResetChargedEnergyCounter"].lower() == "ondisconnect"):
                self.dbusService["/Ac/Energy/Forward"]  = 0.0 #Reset Session Charge Counter.
                self.chargingTime = 0 #Reset ChargingTimeCounter
        
        elif (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode==1):
            updateStatus = 4 # Waiting Sun.

        elif (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode==0):
            updateStatus = 1 # Connected/Idle

        if (self.wattpilot.modelStatus == 23):
            #22 = Switching to 3-phase
            #23 = Switching to 1-phase
            if (self.currentPhaseMode == 1):
                updateStatus = 23
            elif (self.currentPhaseMode == 3):
                updateStatus = 22

        self.dbusService["/Status"] = updateStatus

        if (self.wattpilot.energyCounterSinceStart is not None and self.wattpilot.carConnected):
            self.dbusService["/Ac/Energy/Forward"] = self.wattpilot.energyCounterSinceStart / 1000
        
        elif (self.wattpilot.energyCounterSinceStart is not None and not self.wattpilot.carConnected and self.config["FroniusWattpilot"]["ResetChargedEnergyCounter"].lower() == "onconnect"):
            self.dbusService["/Ac/Energy/Forward"] = self.wattpilot.energyCounterSinceStart / 1000

        else:
            self.dbusService["/Ac/Energy/Forward"] = 0.0
            self.chargingTime = 0
        
        self.dbusService["/MaxCurrent"] = self.wattpilot.ampLimit
        self.dbusService["/AutoStart"] = self.autostart
        self.dbusService["/SetCurrent"] = self.wattpilot.amp
        self.dbusService["/ChargingTime"] = self.chargingTime

        d(self, "Model Status is: " + str(self.wattpilot.modelStatus))