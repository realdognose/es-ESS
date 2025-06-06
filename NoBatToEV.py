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
from Helper import i, c, d, w, e, t
import Globals
from esESSService import esESSService

class NoBatToEV(esESSService):
    def __init__(self):
        esESSService.__init__(self)

    def initDbusService(self):
        pass

    def initDbusSubscriptions(self):
        if (not "FroniusWattpilot" in Globals.esESS._services):
            self.evChargerPowerDbus = self.registerDbusSubscription("com.victronenergy.evcharger", "/Ac/Power")
        
        self.consumptionL1Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L1/Power")
        self.consumptionL2Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L2/Power")
        self.consumptionL3Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L3/Power")
        
        self.pvOnGensetL1Dbus   = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnGenset/L1/Power")
        self.pvOnGensetL2Dbus   = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnGenset/L2/Power")
        self.pvOnGensetL3Dbus   = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnGenset/L3/Power")

        self.pvOnGridL1Dbus     = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnGrid/L1/Power")
        self.pvOnGridL2Dbus     = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnGrid/L2/Power")
        self.pvOnGridL3Dbus     = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnGrid/L3/Power")

        self.pvOnOutputL1Dbus   = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnOutput/L1/Power")
        self.pvOnOutputL2Dbus   = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnOutput/L2/Power")
        self.pvOnOutputL3Dbus   = self.registerDbusSubscription("com.victronenergy.system", "/Ac/PvOnOutput/L3/Power")

        self.pvOnDcDbus         = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Pv/Power")
        self.noPhasesDbus       = self.registerDbusSubscription("com.victronenergy.system", "/Ac/ActiveIn/NumberOfPhases")

        self.relayState = None
        self.relayStateUsage = int(self.config["NoBatToEV"]["UseRelay"])
        i(self, "Relay state usage is set to: {}".format(self.relayStateUsage))
        if (self.relayStateUsage > -1):
            self.relayState = self.registerDbusSubscription("com.victronenergy.system", "/Relay/{}/State".format(self.relayStateUsage))
        
    def initWorkerThreads(self):
        self.registerWorkerThread(self._update, 2000)

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       self.revokeGridSetPointRequest()

    def enabled(self):
        if self.relayStateUsage > -1:
            if self.relayState is not None:
                return self.relayState.value
            else:
                return False
        else:
            return True

    def _update(self):
        if (self.noPhasesDbus.value is not None and self.noPhasesDbus.value > 0):
            if self.enabled():
                if (not "FroniusWattpilot" in Globals.esESS._services):
                    evPower = self.evChargerPowerDbus.value
                else:
                    evPower = (Globals.esESS._services["FroniusWattpilot"].wattpilot.power1 + Globals.esESS._services["FroniusWattpilot"].wattpilot.power2 + Globals.esESS._services["FroniusWattpilot"].wattpilot.power3)*1000

                consumption = self.consumptionL1Dbus.value + self.consumptionL2Dbus.value + self.consumptionL3Dbus.value
                pvAvailable = self.pvOnGensetL1Dbus.value + self.pvOnGensetL2Dbus.value + self.pvOnGensetL3Dbus.value
                pvAvailable += self.pvOnGridL1Dbus.value + self.pvOnGridL2Dbus.value + self.pvOnGridL3Dbus.value
                pvAvailable += self.pvOnOutputL1Dbus.value + self.pvOnOutputL2Dbus.value + self.pvOnOutputL3Dbus.value
                pvAvailable += self.pvOnDcDbus.value

                d(self, "EV Charge is {ev}W, Consumption is {con}W and available Pv is {pv}W.".format(ev=evPower, con=consumption, pv=pvAvailable))

                if (evPower > 0):
                    if (consumption >= pvAvailable):
                        #offload the share of EV charge that is NOT PV covered to the grid. 
                        rawConsumption = consumption - evPower
                        remainingPv = max(0, pvAvailable - rawConsumption)
                        delta = evPower - remainingPv

                        d(self, "So, raw consumption is {0}W, remainingPV is {1}W, we therefore offload {2}W to the grid.".format(rawConsumption, remainingPv, delta))

                        self.registerGridSetPointRequest(delta)
                    else:
                        self.revokeGridSetPointRequest()
                else:
                    self.revokeGridSetPointRequest()
            else:
                self.revokeGridSetPointRequest()
                d(self, "NoBatToEV is disabled due to relay state.")
        else:
            w(self, "Grid-Loss detected. Not doing anything.")
            self.revokeGridSetPointRequest()
