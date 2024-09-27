import os
import sys
from typing import Dict
import dbus # type: ignore
import dbus.service # type: ignore
import inspect
import pprint
import datetime
import os
import sys

# esEss imports
from Helper import i, c, d, w, e, t
import Globals
from esESSService import esESSService

class Grid2Bat(esESSService):
    def __init__(self):
        self.updateFrequency = 5000
        self.currentHourConsumption = 0
        now = datetime.datetime.now()
        self.currentHour = now.hour 
        esESSService.__init__(self)

    def initDbusService(self):
        pass

    def initDbusSubscriptions(self):
        self.consumptionL1Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L1/Power")
        self.consumptionL2Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L2/Power")
        self.consumptionL3Dbus  = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Consumption/L3/Power")

    def initWorkerThreads(self):
        #5000 experimental, hardcoded for now. 
        self.registerWorkerThread(self._update, self.updateFrequency)

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       pass

    def _update(self):
        consumption = self.consumptionL1Dbus.value + self.consumptionL2Dbus.value + self.consumptionL3Dbus.value
        now = datetime.datetime.now()

        if (now.hour != self.currentHour):
            self.currentHourConsumption = 0
            self.currentHour = now.hour 

        self.currentHourConsumption += consumption * ((self.updateFrequency / 1000.0) / 3600.0)

        self.publishMainMqtt("{0}/Grid2Bat/ConsumptionTracking/wh_{1}".format(Globals.esEssTag, now.hour), self.currentHourConsumption, 1, True)
        
