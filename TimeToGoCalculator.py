import configparser
import os
import time
import paho.mqtt.client as mqtt # type: ignore
import sys
if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

#esEss imports
import Globals
from Globals import getFromGlobalStoreValue
from Helper import i, c, d, w, e
from DBus import DbusC
from esESSService import esESSService

class TimeToGoCalculator(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.capacity   = float(self.config["Default"]["BatteryCapacityInWh"])

    def initDbusService(self):
        pass
    
    def initDbusSubscriptions(self):
        self.powerDbus      = self.registerDbusSubscription("com.victronenergy.battery", "/Dc/0/Power")
        self.socDbus        = self.registerDbusSubscription("com.victronenergy.battery", "/Soc")
        #self.timeToGoDbus   = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/TimeToGo")
        self.activeBMSDbus  = self.registerDbusSubscription("com.victronenergy.system", "/ActiveBmsService", self.activeBMSChanged)
        self.socLimitDbus   = self.registerDbusSubscription("com.victronenergy.system", "/Control/ActiveSocLimit")

    def initMqttSubscriptions(self):
        pass

    def initWorkerThreads(self):
        self.registerWorkerThread(self.updateTimeToGo, int(self.config["TimeToGoCalculator"]["UpdateInterval"]))

    def initFinalize(self):
        pass

    def activeBMSChanged(self, sub):
       #Modify our subscriptions to the precice service instance we need.
       d(self, "Setting active BMS service to {0}".format(sub.value)) 
       self.powerDbus.serviceName = sub.value   
       self.socDbus.serviceName = sub.value

    def updateTimeToGo(self):
      try:
        
        power     = self.powerDbus.value
        soc       = self.socDbus.value
        socLimit  = self.socLimitDbus.value
        
        d(self, "{0} / {1} / {2}".format(power, soc, socLimit))

        remainingCapacity = (socLimit/100.0) * self.capacity
        missingCapacity = (1 - soc/100.0) * self.capacity  
        currentCapacity = (soc/100.0) * self.capacity
        usableCapacity = currentCapacity - remainingCapacity
        
        #d(self, "Capacity: {0}, RemCap: {1}, MisCap: {2}, CurCap: {3}, UsCap: {4}".format(self.capacity, remainingCapacity, missingCapacity, currentCapacity, usableCapacity))

        remaining = None
        if (power < 0):
          remaining = (usableCapacity / power) * 60 * 60 * -1
        elif (power > 0):
          remaining = (missingCapacity / power) * 60 * 60

        #d(self, "=> TimeToGo (s): {0}s".format(remaining))
        
        #Inject calculated value to dbus. 
        if (remaining is not None):
          #TODO: Figure out why dbus publishing is not working :( )
          #self.timeToGoDbus.publish(int(remaining))

          Globals.localMqttClient.publish("N/{0}/system/0/Dc/Battery/TimeToGo".format(self.config["Default"]["VRMPortalID"]), "{\"value\": " + str(int(remaining)) + "}")
          Globals.mqttClient.publish("{0}/{1}/TimeToGo".format(Globals.esEssTag, self.__class__.__name__), int(remaining))

      except Exception as e:
        c("TimeToGoCalculator", "Exception catched", exc_info=e)
      
      return True
