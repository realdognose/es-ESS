import configparser
import os
import sys

#esEss imports
import Globals
from Helper import i, c, d, w, e
from esESSService import esESSService


class ChargeCurrentReducer(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.defaultPowerSetPoint = float(self.config["ChargeCurrentReducer"]["DefaultPowerSetPoint"])
        self.adjustmentFactor = float(self.config["ChargeCurrentReducer"]["AdjustmentFactor"])
        self.desiredChargeAmps = float(self.config["ChargeCurrentReducer"]["DesiredChargeAmps"])
        self.currentlyDraining = float(0)

    def initDbusService(self):
        pass

    def initDbusSubscriptions(self):
        self.powerDcDbus       = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Power")
        self.currentDcDbus     = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Current")
        self.voltageDbus       = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Voltage")
        self.voltageL1Dbus     = self.registerDbusSubscription("com.victronenergy.grid", "/Ac/L1/Voltage")
        self.voltageL2Dbus     = self.registerDbusSubscription("com.victronenergy.grid", "/Ac/L2/Voltage")
        self.voltageL3Dbus     = self.registerDbusSubscription("com.victronenergy.grid", "/Ac/L3/Voltage")
        self.powerSetPointDbus = self.registerDbusSubscription("com.victronenergy.settings", "/Settings/CGwacs/AcPowerSetPoint")

    def initMqttSubscriptions(self):
        pass
    
    def initWorkerThreads(self):
        self.registerWorkerThread(self._update, 10000)

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
        self.publishLocalMqtt("W/c0619ab4a585/settings/0/Settings/CGwacs/AcPowerSetPoint", "{\"value\": " + str(self.defaultPowerSetPoint) + "}",2,False)
        pass
    
    def _update(self):
        try:
            iDC = self.currentDcDbus.value
            uDC = self.voltageDbus.value
            vAC = (self.voltageL1Dbus.value + self.voltageL2Dbus.value + self.voltageL3Dbus.value) / 3

            d(self, "Battery Stats are {amps}A @ {v}V.".format(amps=iDC, v=uDC))

            #Are we currently draining and need to adjust? 
            if (self.currentlyDraining > 0):
                self._adjustDrainCurrent(iDC, uDC, vAC)
            
            #Do we need to start draining? 
            else:
                if (iDC > self.desiredChargeAmps):
                    d(self, "Starting to drain Amps away from DC-Side.")
                    self._adjustDrainCurrent(iDC, uDC, vAC)
                else:
                    d(self, "All good, there is nothing to do.")

        except Exception as ex:
            c(self, "Exception catched while calculating power-setpoint. Sending default Gridsetpoint to be sure.", exc_info=ex)
            self.publishLocalMqtt("W/c0619ab4a585/settings/0/Settings/CGwacs/AcPowerSetPoint", "{\"value\": " + str(self.defaultPowerSetPoint) + "}",2,False)
      
        return True
    
    def _adjustDrainCurrent(self, iDC, uDC, vAC):
        try:
            drainTarget = (iDC - self.desiredChargeAmps) * self.adjustmentFactor
            d(self, "Going to adjust current draining by: {0}A (DC-Side)".format(drainTarget))

            drainTarget = self.currentlyDraining + drainTarget
            drainTargetAcPower = drainTarget * uDC / 0.97 #Assuming DC-AC Efficency of 97%
            d(self, "New draining Sum: {0}A (DC-Side) - that is {1}W grid feed required on the AC Side.".format(drainTarget, drainTargetAcPower))

            psp = self.powerSetPointDbus.value
            pspNew = min(drainTargetAcPower*-1, self.defaultPowerSetPoint)
            self.currentlyDraining = drainTarget
            drainDelta = pspNew - psp

            d(self, "Current powersetpoint is {0}W, so a new setpoint of {1}W means the delta is: {2}W".format(psp, pspNew, drainDelta))
            self.publishLocalMqtt("W/c0619ab4a585/settings/0/Settings/CGwacs/AcPowerSetPoint", "{\"value\": " + str(pspNew) + "}",1 ,False)
        except Exception as ex:
            c(self, "Exception catched while calculating power-setpoint. Sending default Gridsetpoint to be sure.", exc_info=ex)
            self.publishLocalMqtt("W/c0619ab4a585/settings/0/Settings/CGwacs/AcPowerSetPoint", "{\"value\": " + str(self.defaultPowerSetPoint) + "}",2,False)
      
        return True