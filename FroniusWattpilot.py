
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

class FroniusWattpilot:

    def _froniusHandleChangedValue(self, path, value):
        i(self, "User/cerbo/vrm updated " + str(path) + " to " + str(value))

        if (path == "/SetCurrent"):
            #Value coming in needs to be cut in third, due to missing 3 phases option on vrm!
            #except value is smaller than single phase maximum! 
            ampPerPhase = int(floor(value/3.0)) if value > self.wattpilot.ampLimit else value

            if (value > self.wattpilot.ampLimit):
                self.wattpilot.set_phases(2)
                self.currentPhaseMode = 2
            else:
                self.wattpilot.set_phases(1)
                self.currentPhaseMode = 1

            self.wattpilot.set_power(ampPerPhase)
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
        d("FroniusWattpilot", "Switching Mode from " + str(fromMode) + " to " + str(toMode))
        self.mode = toMode
        self.dbusService["/Mode"] = toMode
        if (fromMode == 0 and toMode == 1):
            self.autostart = 1
            self.wattpilot.set_mode(4) #eco


        elif (fromMode == 1 and toMode == 0):
            self.autostart = 0
            self.wattpilot.set_mode(3) #normal
         
    def _automaticTick(self):
        #if the car is not connected, we can greatly reduce system load.
        #just dump values every 5 minutes then. If car is connected, we need
        #to perform updates every tick.
        self.tempStatusOverride = None
        if (self.wattpilot.carConnected or not self.isIdleMode or (self.lastVarDump < (time.time() - 300)) or self.mode==0):
            self.lastVarDump = time.time()

            #switch idle mode to reduce load, when not required.
            self.isIdleMode = not self.wattpilot.carConnected

            try:
                Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/VRMInstanceID", self.config["FroniusWattpilot"]["VRMInstanceID_OverheadRequest"])
                
                if (self.wattpilot.power > 0 and self.currentPhaseMode == 1):
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/CustomName", "Wattpilot (1)")
                elif (self.wattpilot.power > 0 and self.currentPhaseMode == 3):
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/CustomName", "Wattpilot (3)")
                else:
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/CustomName", "Wattpilot")
                
                Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/IgnoreBatReservation", "false")
                Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Minimum", int(floor(self.wattpilot.voltage1 * 6)))
                Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/StepSize", int(floor(self.wattpilot.voltage1))) #assuming all phases are about equal and stepSize is 1 amp.
            
                #Create a request for power consumption. 
                if (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode == 1):
                    #Car connected, not charging, automatic mode. Create  a request.
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/IsAutomatic", "true")
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Consumption", 0)
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Request", int(floor(3 * self.wattpilot.ampLimit * self.wattpilot.voltage1)))
                    
                elif (not self.wattpilot.carConnected):
                    #Car not connected, no request
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Consumption", 0)
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Request", 0)

                if (self.mode == 0):
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/IsAutomatic", "false")
                elif (self.mode == 1 and self.wattpilot.carConnected):
                    Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Request", int(floor(3 * self.wattpilot.ampLimit * self.wattpilot.voltage1)))
                    #Check, if we have an allowance in auto mode? .
                    allowance = getFromGlobalStoreValue(self.allowanceTopic, 0)
                    
                    #increment charging time. Tick is 5 seconds, that is precise enough.
                    if (self.wattpilot.power > 0):
                        self.chargingTime += 5

                    if (allowance >= self.wattpilot.voltage1 * 6):
                        targetAmps = int(floor(max(allowance / self.wattpilot.voltage1, 6)))
                        targetAmps = min(self.wattpilot.ampLimit * 3, targetAmps) #obey limits.

                        d(self, "Target Amps that is: {0}A".format(targetAmps))

                        if (self.wattpilot.power > 0):
                            #charging, adjust current
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
                                self.tempStatusOverride = 21
                            else:
                                w(self, "Start-Charge delayed due to on/off cooldown: {0}s".format(onOffCooldownSeconds))
                                self.tempStatusOverride = 21
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
                                self.tempStatusOverride = 24
                            else:
                                w(self, "Stop-Charge delayed due to on/off cooldown: {0}s".format(onOffCooldownSeconds))
                                self.tempStatusOverride = 24

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
        d(self, "Desired PhaseMode: {0}".format(desiredPhaseMode))
        
        if (self.currentPhaseMode == desiredPhaseMode):
            targetAmps = int(floor(targetAmps / self.currentPhaseMode))
            #Just adjust, no phasemode change required. 
            i(self, "Adjusting charge current to: {0}A".format(targetAmps))
            self.wattpilot.set_power(targetAmps)

        elif (self.currentPhaseMode != desiredPhaseMode):
            i(self, "Total amps required is: {0}}. Hence switching from phasemode {1} to {2}".format(targetAmps, self.currentPhaseMode, desiredPhaseMode))
            targetAmps = int(floor(targetAmps / desiredPhaseMode))
            i(self, "That'll be {0}A on PhaseMode {1}".format(targetAmps, desiredPhaseMode))

            phaseSwitchCooldownSeconds = self.getPhaseSwitchCooldownSeconds()
            if (phaseSwitchCooldownSeconds <= 0):
                i(self, "Switching to Phase-Mode: {0}. Send.".format(desiredPhaseMode))
                self.lastPhaseSwitchTime = time.time()
                self.wattpilot.set_phases(desiredPhaseMode)
                self.currentPhaseMode = desiredPhaseMode
                self.wattpilot.set_power(targetAmps)
            else:
                if (self.currentPhaseMode == 1):
                    w(self, "Attempted to switch to Phase-Mode {0}, but cooldown is active! Using {1}A on Phase-Mode {2} until cooldown is over in {3}s".format(desiredPhaseMode, self.wattpilot.ampLimit, self.currentPhaseMode, phaseSwitchCooldownSeconds))
                    self.wattpilot.set_power(self.wattpilot.ampLimit)
                elif (self.currentPhaseMode == 3):
                    w(self, "Attempted to switch to Phase-Mode {0}, but cooldown is active! Using 6A on Phase-Mode {1} until cooldown is over in {2}s".format(desiredPhaseMode, self.currentPhaseMode, phaseSwitchCooldownSeconds))
                    self.wattpilot.set_power(6)                



    def __init__(self):
        self.config = Globals.getConfig()
        self.lastPhaseSwitchTime = 0
        self.lastOnOffTime = 0
        self.minimumOnOffSeconds = int(self.config["FroniusWattpilot"]["MinOnOffSeconds"])
        self.minimumPhaseSwitchSeconds = int(self.config["FroniusWattpilot"]["MinPhaseSwitchSeconds"])
        self.lastVarDump = 0
        self.chargingTime = 0
        self.currentPhaseMode = 1
        self.mode = 0 #Start in manual mode, switch when initialized.
        self.autostart = 0 
        self.isIdleMode = False
        self.tempStatusOverride = None

        #register on dbus as EV-Charger.
        self.vrmInstanceID = self.config['FroniusWattpilot']['VRMInstanceID']
        self.serviceType = "com.victronenergy.evcharger"
        self.serviceName = self.serviceType + ".es-ESS.FroniusWattpilot_" + self.vrmInstanceID
        i(self, "Registering service as: {0}".format(self.serviceName))
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

        #Additional Stuff, not required by definition
        self.dbusService.add_path('/CarState', None)
        self.dbusService.add_path('/PhaseMode', None)

        #TODO: Detect, if the charger is setup for manual or automatic mode?
        #self.switchMode(0,1)

        #Create the Wattpilot object and connect. 
        self.wattpilot = Wattpilot(self.config["FroniusWattpilot"]["Host"], self.config["FroniusWattpilot"]["Password"])
        self.wattpilot._auto_reconnect = True
        self.wattpilot._reconnect_interval = 30
        self.wattpilot.connect()
        Helper.waitTimeout(lambda: self.wattpilot.connected, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")

        #Wait for some information to arrive. 
        Helper.waitTimeout(lambda: self.wattpilot.power1 is not None, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")
        Helper.waitTimeout(lambda: self.wattpilot.power2 is not None, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")
        Helper.waitTimeout(lambda: self.wattpilot.power3 is not None, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")
        Helper.waitTimeout(lambda: self.wattpilot.carConnected is not None, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")
        Helper.waitTimeout(lambda: self.wattpilot.mode is not None, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")

        if (self.wattpilot.mode == "Eco"):
            self.autostart = 1
            self.mode = 1
        else:
            self.autostart = 0
            self.mode = 0

        #After init, we need to determine the current phase mode. 
        #if the car is charging, we can do that by looking at the phase power. 
        #if the car is not charging, we can simply force it to be 3 phases, until determined 
        # otherwise. 
        if (self.wattpilot.carConnected and self.wattpilot.power2 > 0):
            self.currentPhaseMode = 2
        elif (self.wattpilot.carConnected and self.wattpilot.power1 > 0):
            self.currentPhaseMode = 1
        else:
            #TODO let user pick default phase mode. 
            self.currentPhaseMode = 2
            self.wattpilot.set_phases(2)

        #subscribe to PV Overhead Allowance topic.  
        self.allowanceTopic = "es-ESS/Requests/Wattpilot/Allowance"
        Globals.mqttClient.subscribe(self.allowanceTopic)

        self.dumpEvChargerInfo()
        gobject.timeout_add(int(5000), self._automaticTick)
        Globals.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "{0} initialized.".format(self.__class__.__name__))

    def dumpEvChargerInfo(self):
        #method is called, whenever new information arrive through mqtt. 
        #just dump the information we have.
        self.Publish("/Ac/L1/Power", self.wattpilot.power1 * 1000 if (self.wattpilot.power1 is not None) else 0)
        self.Publish("/Ac/L2/Power", self.wattpilot.power2 * 1000 if (self.wattpilot.power2 is not None) else 0)
        self.Publish("/Ac/L3/Power", self.wattpilot.power3 * 1000 if (self.wattpilot.power3 is not None) else 0)
        self.Publish("/Ac/L1/Voltage", self.wattpilot.voltage1  if (self.wattpilot.voltage1 is not None) else 0)
        self.Publish("/Ac/L2/Voltage", self.wattpilot.voltage2  if (self.wattpilot.voltage2 is not None) else 0)
        self.Publish("/Ac/L3/Voltage", self.wattpilot.voltage3  if (self.wattpilot.voltage3 is not None) else 0)
        self.Publish("/Ac/L1/Current", self.wattpilot.amps1  if (self.wattpilot.amps1 is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Ac/L2/Current", self.wattpilot.amps2  if (self.wattpilot.amps2 is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Ac/L3/Current", self.wattpilot.amps3  if (self.wattpilot.amps3 is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Ac/L1/PowerFactor", self.wattpilot.powerFactor1  if (self.wattpilot.powerFactor1 is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Ac/L2/PowerFactor", self.wattpilot.powerFactor2  if (self.wattpilot.powerFactor2 is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Ac/L3/PowerFactor", self.wattpilot.powerFactor3  if (self.wattpilot.powerFactor3 is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Ac/Power", self.wattpilot.power * 1000 if (self.wattpilot.power is not None) else 0)
        self.Publish("/Current", (self.wattpilot.amps1 + self.wattpilot.amps2 + self.wattpilot.amps3) if (self.wattpilot.amp is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Mode", self.mode)

        #Also write total power back to SolarOverheadDistributor, in case we are in automatic mode. 
        if (self.mode == 1):
            Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Consumption", self.wattpilot.power * 1000)

        updateStatus = self.dbusService["/Status"]
        if (self.wattpilot.carConnected and self.wattpilot.power > 0):
            updateStatus = 2 # charging

        elif (not self.wattpilot.carConnected):
            updateStatus = 0 # Disconnected

            if (self.config["FroniusWattpilot"]["ResetChargedEnergyCounter"].lower() == "ondisconnect"):
                self.Publish("/Ac/Energy/Forward", 0.0) #Reset Session Charge Counter.
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

        #Start/Stop Cooldown?
        if (self.tempStatusOverride is not None):
            updateStatus = self.tempStatusOverride

        self.Publish("/Status", updateStatus)

        if (self.wattpilot.energyCounterSinceStart is not None and self.wattpilot.carConnected):
            self.Publish("/Ac/Energy/Forward", self.wattpilot.energyCounterSinceStart / 1000)
        
        elif (self.wattpilot.energyCounterSinceStart is not None and not self.wattpilot.carConnected and self.config["FroniusWattpilot"]["ResetChargedEnergyCounter"].lower() == "onconnect"):
            self.Publish("/Ac/Energy/Forward", self.wattpilot.energyCounterSinceStart / 1000)

        else:
            self.Publish("/Ac/Energy/Forward", 0.0)
            self.chargingTime = 0
        
        self.Publish("/AutoStart", self.autostart)

        if (self.currentPhaseMode == 2):
            self.Publish("/SetCurrent", self.wattpilot.amp * 3)
            self.Publish("/MaxCurrent", self.wattpilot.ampLimit * 3)
        else:
            self.Publish("/SetCurrent", self.wattpilot.amp)
            self.Publish("/MaxCurrent", self.wattpilot.ampLimit )

        self.Publish("/ChargingTime", self.chargingTime)
        self.Publish("/CarState", self.wattpilot.carConnected)
        self.Publish("/PhaseMode", self.currentPhaseMode)

        #d(self, "Model Status is: {0}".format(self.wattpilot.modelStatus))

    def Publish(self, path, value):
        self.dbusService[path] = value
        Globals.mqttClient.publish("es-ESS/FroniusWattpilot{0}".format(path), value, 0)