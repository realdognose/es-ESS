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
from DBus import DbusC

class TimeToGoCalculator:
  def __init__(self):
    try:
      self.config = Globals.getConfig()

      # add _update function 'timer'
      gobject.timeout_add(int(self.config['TimeToGoCalculator']['UpdateInterval']), self._update)
      i(self, "TimeToGoCalculator initialized.")
    except Exception as e:
      c(self, "Exception catched", exc_info=e)

  def _update(self):
    try:
      c
      power = Globals.DbusWrapper.system.Dc.Battery.Power
      soc = Globals.DbusWrapper.system.Dc.Battery.Soc
      socLimit = Globals.DbusWrapper.system.Control.ActiveSocLimit
      capacity = float(self.config["Default"]["BatteryCapacityInWh"])

      d(self, "Power: {0}, Soc: {1}, socLimit: {2}".format(power, soc, socLimit))

      remainingCapacity = (socLimit/100.0) * capacity
      missingCapacity = (1 - soc/100.0) * capacity  
      currentCapacity = (soc/100.0) * capacity
      usableCapacity = currentCapacity - remainingCapacity
      
      d(self, "Capacity: {0}, RemCap: {1}, MisCap: {2}, CurCap: {3}, UsCap: {4}".format(capacity, remainingCapacity, missingCapacity, currentCapacity, usableCapacity))

      remaining = None
      if (power < 0):
        remaining = (usableCapacity / power) * 60 * 60 * -1
      elif (power > 0):
        remaining = (missingCapacity / power) * 60 * 60

      d(self, "=> TimeToGo (s): {0}s".format(remaining))

      #Inject calculated value through mqtt, so it will only affect display on vrm.
      Globals.mqttClient.publish("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/TimeToGo", "{\"value\": " + str(remaining) + "}", 0, False)

    except Exception as e:
      c("TimeToGoCalculator", "Exception catched", exc_info=e)
      
    return True
