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

class TimeToGoCalculator:
  def __init__(self):
    try:
      self.config = Globals.getConfig()
      self.futureUpdate = None
      i(self, "TimeToGoCalculator initialized.")
      Globals.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "{0} initialized.".format(self.__class__.__name__))
      gobject.timeout_add(int(self.config['TimeToGoCalculator']['UpdateInterval']), self._update)
    except Exception as e:
      c(self, "Exception catched", exc_info=e)

  def _update(self):
    if (self.futureUpdate is None or self.futureUpdate.done()):
      self.futureUpdate = Globals.esESS.threadPool.submit(self._updateThreaded)
    else:
      w(self, "Processing Thread is still running, not submitting another one, to prevent Threadpool from filling up. ")
    
    return True

  def _updateThreaded(self):
    try:
      power = Globals.DbusWrapper.system.Dc.Battery.Power
      soc = Globals.DbusWrapper.system.Dc.Battery.Soc
      socLimit = Globals.DbusWrapper.system.Control.ActiveSocLimit
      capacity = float(self.config["Default"]["BatteryCapacityInWh"])

      #d(self, "Power: {0}, Soc: {1}, socLimit: {2}".format(power, soc, socLimit))

      remainingCapacity = (socLimit/100.0) * capacity
      missingCapacity = (1 - soc/100.0) * capacity  
      currentCapacity = (soc/100.0) * capacity
      usableCapacity = currentCapacity - remainingCapacity
      
      #d(self, "Capacity: {0}, RemCap: {1}, MisCap: {2}, CurCap: {3}, UsCap: {4}".format(capacity, remainingCapacity, missingCapacity, currentCapacity, usableCapacity))

      remaining = None
      if (power < 0):
        remaining = (usableCapacity / power) * 60 * 60 * -1
      elif (power > 0):
        remaining = (missingCapacity / power) * 60 * 60

      #d(self, "=> TimeToGo (s): {0}s".format(remaining))
      
      #Inject calculated value through mqtt, so it will only affect display on vrm.
      Globals.localMqttClient.publish("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/TimeToGo", "{\"value\": " + str(remaining) + "}", 0, False)
      Globals.mqttClient.publish("{0}/{1}/TimeToGo".format(Globals.esEssTag, self.__class__.__name__), remaining)

    except Exception as e:
      c("TimeToGoCalculator", "Exception catched", exc_info=e)
      
    return True
