import configparser
import os
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

class TimeToGoCalculator:
   def __init__(self):
     try:
      self.config = Globals.getConfig()

      #subscribe to values we need
      Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Power")
      Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Soc")
      Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Control/ActiveSocLimit")

      # add _update function 'timer'
      gobject.timeout_add(int(self.config['TimeToGoCalculator']['UpdateInterval']), self._update)
      i("TimeToGoCalculator", "TimeToGoCalculator initialized.")
     except Exception as e:
       c("TimeToGoCalculator", "Exception catched", exc_info=e)

   def _update(self):
     try:
      power = float(getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Power", 0))
      soc = float(getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Soc", 0))
      socLimit = float(getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Control/ActiveSocLimit", 0))
      capacity = float(self.config["Default"]["BatteryCapacityInWh"])

      remainingCapacity = (socLimit/100.0) * capacity
      missingCapacity = (1 - soc/100.0) * capacity  
      currentCapacity = (soc/100.0) * capacity
      usableCapacity = currentCapacity - remainingCapacity
      
      #d("TimeToGoCalculator", ": " + str(capacity) + " / "+ str(remainingCapacity) + " / "+ str(missingCapacity) + " / "+ str(currentCapacity) + " / "+ str(usableCapacity))

      if (power < 0):
        remaining = (usableCapacity / power) * 60 * 60 * -1
      elif (power == 0):
        remaining = None
      elif (power > 0):
        remaining = (missingCapacity / power) * 60 * 60

      #d("TimeToGoCalculator", "TimeToGo (s): " + str(remaining))
      Globals.mqttClient.publish("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/TimeToGo", "{\"value\": " + str(remaining) + "}", 0, False)

     except Exception as e:
       c("TimeToGoCalculator", "Exception catched", exc_info=e)
      
     return True
