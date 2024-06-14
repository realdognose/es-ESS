
from builtins import int
from math import floor
import os
import platform
import sys
import time

import paho.mqtt.client as mqtt # type: ignore

# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore

# esEss imports
import Globals
import Helper
from Helper import i, c, d, w, e, dbusConnection
from Wattpilot import Wattpilot, Event
from esESSService import esESSService

class FroniusWattpilot (esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.vrmInstanceID = self.config['FroniusWattpilot']['VRMInstanceID']
        self.serviceType = "com.victronenergy.evcharger"
        self.serviceName = self.serviceType + ".es-ESS.FroniusWattpilot_" + self.vrmInstanceID
        self.minimumOnOffSeconds = int(self.config["FroniusWattpilot"]["MinOnOffSeconds"])
        self.minimumPhaseSwitchSeconds = int(self.config["FroniusWattpilot"]["MinPhaseSwitchSeconds"])
        self.wattpilot = None
        self.allowance = 0
        self.lastPhaseSwitchTime = 0
        self.lastOnOffTime = 0
        self.lastVarDump = 0
        self.chargingTime = 0
        self.currentPhaseMode = 1 # will be detected later
        self.mode = 0 # will be detected later
        self.autostart = 0 
        self.isIdleMode = False
        self.isHibernateEnabled = self.config["FroniusWattpilot"]["HibernateMode"].lower() == "true"
        self.tempStatusOverride = None
        self.mqttAllowanceTopic = 'es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Allowance'

    def initDbusService(self):
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())

        #dump root information about our service and register paths.
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "dbus")

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
        self.dbusService.add_path('/Ac/PowerPercent', 0)
        self.dbusService.add_path('/Ac/PowerMax', 0)
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

    def initDbusSubscriptions(self):
        pass

    def initMqttSubscriptions(self):
        self.registerMqttSubscription(self.mqttAllowanceTopic, callback=self.onMqttMessage)

    def initWorkerThreads(self):
        self.registerWorkerThread(self._update, 5000)

    def initFinalize(self):
        #Create the Wattpilot object and connect. 
        self.wattpilot = Wattpilot(self.config["FroniusWattpilot"]["Host"], self.config["FroniusWattpilot"]["Password"])
        self.wattpilot._auto_reconnect = True
        self.wattpilot._reconnect_interval = 30
        self.wattpilot.connect()
        
        #Wait for some information to arrive. 
        Helper.waitTimeout(lambda: self.wattpilot.connected, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds... Wattpilot offline or credentials wrong?")
        Helper.waitTimeout(lambda: self.wattpilot.power1 is not None, 30) 
        Helper.waitTimeout(lambda: self.wattpilot.power2 is not None, 30) 
        Helper.waitTimeout(lambda: self.wattpilot.power3 is not None, 30) 
        Helper.waitTimeout(lambda: self.wattpilot.carConnected is not None, 30) 
        Helper.waitTimeout(lambda: self.wattpilot.mode is not None, 30) 

        #determine current modes.
        if (self.wattpilot.mode == "Eco"):
            self.autostart = 1
            self.mode = 1
            self.publishServiceMessage(self, "Mode determined as: auto")
        else:
            self.autostart = 0
            self.mode = 0
            self.publishServiceMessage(self, "Mode determined as: manual")

        #Adetermine the current phase mode. 
        #if the car is charging, we can do that by looking at the phase power. 
        #if the car is not charging, we can simply force it to be 3 phases, until determined 
        #otherwise. 
        if (self.wattpilot.carConnected and self.wattpilot.power2 > 0):
            self.currentPhaseMode = 2
            self.publishServiceMessage(self, "Currently charging on 3 phases.")
        elif (self.wattpilot.carConnected and self.wattpilot.power1 > 0):
            self.currentPhaseMode = 1
            self.publishServiceMessage(self, "Currently charging on 1 phase.")
        else:
            self.publishServiceMessage(self, "Currently not charging. Negiotiating 1 phase for startup.")
            self.currentPhaseMode = 1
            self.wattpilot.set_phases(1)

        self.dumpEvChargerInfo()

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

   # When Mode is switched, different settings needs to be enabled/disabled. 
   # 0 = Manual => User control, only forward commands from VRM to wattpilot and read wattpilotstats.
   # 1 = Automatic => Overhead Mode, disable VRM Control, reject wattpilot changes, register pv overhead observer.
   # 2 = Scheduled => Nightly low-price mode, TODO
    def switchMode(self, fromMode, toMode):
        d("FroniusWattpilot", "Switching Mode from {0} to {1}.".format(fromMode, toMode))
        self.publishServiceMessage(self, "Switching Mode from {0} to {1}.".format(fromMode, toMode))
        self.mode = toMode
        self.dbusService["/Mode"] = toMode
        if (fromMode == 0 and toMode == 1):
            self.autostart = 1
            self.wattpilot.set_mode(4) #eco

        elif (fromMode == 1 and toMode == 0):
            self.autostart = 0
            self.wattpilot.set_mode(3) #normal
         
    def _update(self):
        #if the car is not connected, we can greatly reduce system load.
        #just dump values every 5 minutes then. If car is connected, we need
        #to perform updates every tick.
        self.tempStatusOverride = None
        if (self.wattpilot.carConnected or not self.isIdleMode or (self.lastVarDump < (time.time() - 300)) or self.mode==0):
            self.lastVarDump = time.time()

            #switch idle mode to reduce load, when not required.
            skipIdleCheck = False
            if (not self.isIdleMode and not self.wattpilot.carConnected):
                self.publishServiceMessage(self, "Car no longer connected. Switching to Idle-Mode.")
                if (self.isHibernateEnabled):
                    self.publishServiceMessage(self, "Hibernate is enabled. Disconnecting from wattpilot.")
                    self.wattpilot._auto_reconnect=False
                    self.wattpilot.disconnect()

            elif (self.isIdleMode):
                if (self.wattpilot.connected and self.wattpilot.carConnected):
                    self.publishServiceMessage(self, "Car connected. Switching to Operation-Mode.")
                elif (not self.wattpilot.connected):
                    self.publishServiceMessage(self, "Connecting to wattpilot to verify car status.")
                    self.wattpilot.connect()
                    self.wattpilot._auto_reconnect=True
                    self.isIdleMode=False
                    skipIdleCheck=True
                    
            if (not skipIdleCheck):                    
                self.isIdleMode = not self.wattpilot.carConnected

            try:
                self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/VRMInstanceID", self.config["FroniusWattpilot"]["VRMInstanceID_OverheadRequest"])
                self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/IsScriptedConsumer", "true")
                
                if (self.wattpilot.power > 0 and self.currentPhaseMode == 1):
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/CustomName", "Wattpilot (1)")
                elif (self.wattpilot.power > 0 and self.currentPhaseMode == 3):
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/CustomName", "Wattpilot (3)")
                else:
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/CustomName", "Wattpilot")
                
                self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/IgnoreBatReservation", "false")
                self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Minimum", int(floor(self.wattpilot.voltage1 * 6)))
                self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/StepSize", int(floor(self.wattpilot.voltage1))) #assuming all phases are about equal and stepSize is 1 amp.
            
                #Create a request for power consumption. 
                if (self.wattpilot.carConnected and self.wattpilot.power == 0 and self.mode == 1):
                    #Car connected, not charging, automatic mode. Create  a request.
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/IsAutomatic", "true")
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Consumption", 0)
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Request", int(floor(3 * self.wattpilot.ampLimit * self.wattpilot.voltage1)))
                    
                elif (not self.wattpilot.carConnected):
                    #Car not connected, no request
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Consumption", 0)
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Request", 0)

                if (self.mode == 0):
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/IsAutomatic", "false")
                elif (self.mode == 1 and self.wattpilot.carConnected):
                    self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Request", int(floor(3 * self.wattpilot.ampLimit * self.wattpilot.voltage1)))

                    #Check, if we have an allowance in auto mode? .
                    d(self, "Current allowance is {0}W".format(self.allowance))

                    #increment charging time. Tick is 5 seconds, that is precise enough.
                    if (self.wattpilot.power > 0):
                        self.chargingTime += 5

                    if (self.allowance >= self.wattpilot.voltage1 * 6):
                        targetAmps = int(floor(max(self.allowance / self.wattpilot.voltage1, 6)))
                        targetAmps = min(self.wattpilot.ampLimit * 3, targetAmps) #obey limits.

                        d(self, "Target Amps that is: {0}A".format(targetAmps))
                        self.publishServiceMessage(self, "Current allowance is {0}W, that's {1}A".format(self.allowance, targetAmps))

                        if (self.wattpilot.power > 0):
                            #charging, adjust current
                            self.adjustChargeCurrent(targetAmps)
                        else:
                            #Make sure, we are not phase-switching right now. 
                            if (self.wattpilot.modelStatus != 22 and self.tempStatusOverride != 21):
                                i(self, "Enough Allowance, but NOT charging, starting.")
                                self.publishServiceMessage(self, "Starting to charge.")
                                onOffCooldownSeconds = self.getOnOffCooldownSeconds()
                                if (onOffCooldownSeconds <= 0):
                                    i(self, "START send!")
                                    self.wattpilot.set_phases(1)
                                    self.currentPhaseMode=1
                                    self.wattpilot.set_power(targetAmps)
                                    self.wattpilot.set_start_stop(2)
                                    self.lastOnOffTime = time.time()
                                    self.dbusService["/StartStop"] = 1
                                    self.tempStatusOverride = 22
                                else:
                                    i(self, )
                                    self.publishServiceMessage(self, "Start-Charge delayed due to on/off cooldown: {0}s".format(onOffCooldownSeconds))
                                    self.tempStatusOverride = 23
                    else:
                        if (self.wattpilot.power):
                            i(self, "NO Allowance, stopping charging.")
                            self.publishServiceMessage(self, "Stopping to charge.")
                            onOffCooldownSeconds = self.getOnOffCooldownSeconds()
                            if (onOffCooldownSeconds <= 0):
                                #stop charging
                                i(self, "STOP send!")
                                self.wattpilot.set_start_stop(1)
                                self.lastOnOffTime = time.time()
                                self.dbusService["/StartStop"] = 0
                                self.tempStatusOverride = 24
                            else:
                                i(self, "Stop-Charge delayed due to on/off cooldown: {0}s".format(onOffCooldownSeconds))
                                self.publishServiceMessage(self, "Stop-Charge delayed due to on/off cooldown: {0}s".format(onOffCooldownSeconds))
                                self.tempStatusOverride = 24

                #update UI anyway
                self.dumpEvChargerInfo()            

            except Exception as ex:
                c(self, "Critical Exception logged.", exc_info=ex)

        return True 

    def onMqttMessage(self, client, userdata, msg):
      try:
         message = str(msg.payload)[2:-1]

         if (msg.topic == self.mqttAllowanceTopic):
             self.allowance = float(message)

      except Exception as e:
         c(self, "Exception", exc_info=e)

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
            i(self, "Total amps required is: {0}. Hence switching from phasemode {1} to {2}".format(targetAmps, self.currentPhaseMode, desiredPhaseMode))
            targetAmps = int(floor(targetAmps / desiredPhaseMode))
            i(self, "That'll be {0}A on PhaseMode {1}".format(targetAmps, desiredPhaseMode))

            phaseSwitchCooldownSeconds = self.getPhaseSwitchCooldownSeconds()
            if (phaseSwitchCooldownSeconds <= 0):
                i(self, "Switching to Phase-Mode: {0}. Send.".format(desiredPhaseMode))
                self.publishServiceMessage(self, "Switching to Phase-Mode: {0}. Send.".format(desiredPhaseMode))
                self.lastPhaseSwitchTime = time.time()
                self.wattpilot.set_phases(desiredPhaseMode)
                self.currentPhaseMode = desiredPhaseMode
                self.wattpilot.set_power(targetAmps)
            else:
                if (self.currentPhaseMode == 1):
                    i(self, "Attempted to switch to Phase-Mode {0}, but cooldown is active! Using {1}A on Phase-Mode {2} until cooldown is over in {3}s".format(desiredPhaseMode, self.wattpilot.ampLimit, self.currentPhaseMode, phaseSwitchCooldownSeconds))
                    self.publishServiceMessage(self, "Attempted to switch to Phase-Mode {0}, but cooldown is active! Using {1}A on Phase-Mode {2} until cooldown is over in {3}s".format(desiredPhaseMode, self.wattpilot.ampLimit, self.currentPhaseMode, phaseSwitchCooldownSeconds))
                    self.wattpilot.set_power(self.wattpilot.ampLimit)
                    self.tempStatusOverride = 21
                elif (self.currentPhaseMode == 3):
                    i(self, "Attempted to switch to Phase-Mode {0}, but cooldown is active! Using 6A on Phase-Mode {1} until cooldown is over in {2}s".format(desiredPhaseMode, self.currentPhaseMode, phaseSwitchCooldownSeconds))
                    self.publishServiceMessage(self, "Attempted to switch to Phase-Mode {0}, but cooldown is active! Using 6A on Phase-Mode {1} until cooldown is over in {2}s".format(desiredPhaseMode, self.currentPhaseMode, phaseSwitchCooldownSeconds))
                    self.wattpilot.set_power(6)       
                    self.tempStatusOverride = 22         

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
        self.Publish("/Ac/PowerPercent", (self.wattpilot.power * 1000) / (3 * self.wattpilot.ampLimit * self.wattpilot.voltage1) if (self.wattpilot.power is not None) else 0)
        self.Publish("/Ac/PowerMax", (3 * self.wattpilot.ampLimit * self.wattpilot.voltage1))
        self.Publish("/Current", (self.wattpilot.amps1 + self.wattpilot.amps2 + self.wattpilot.amps3) if (self.wattpilot.amp is not None and self.wattpilot.power>0) else 0)
        self.Publish("/Mode", self.mode)

        #Also write total power back to SolarOverheadDistributor 
        self.publishMainMqtt("es-ESS/SolarOverheadDistributor/Requests/Wattpilot/Consumption", self.wattpilot.power * 1000)

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

        #Start/Stop Cooldown?
        if (self.tempStatusOverride is not None):
            updateStatus = self.tempStatusOverride

        #Finally, cooldown display may be overwritten by a phase switch atempt. 
        if (self.wattpilot.modelStatus == 23):
            #22 = Switching to 3-phase
            #23 = Switching to 1-phase
            if (self.currentPhaseMode == 1):
                updateStatus = 22
            elif (self.currentPhaseMode == 3):
                updateStatus = 23

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

    def Publish(self, path, value):
        self.dbusService[path] = value
        self.publishMainMqtt("es-ESS/FroniusWattpilot{0}".format(path), value, 0)

    def handleSigterm(self):
       self.publishServiceMessage(self, "SIGTERM received, sending STOP-command to wattpilot, despite any state.")
       if (self.wattpilot is not None and self.wattpilot.connected) :
        self.wattpilot.set_start_stop(1)
        self.wattpilot._auto_reconnect = False
        self.wattpilot.disconnect()