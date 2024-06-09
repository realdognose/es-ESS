#!/usr/bin/env python
 
# imports
import configparser # for config/ini file
from logging.handlers import TimedRotatingFileHandler
import sys
import os
import re
import platform 
import logging
import json
import time
from time import sleep
from builtins import Exception, abs, eval, float, hasattr, int, max, min, round, str

if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

import paho.mqtt.client as mqtt # type: ignore

# victronr
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService # type: ignore
import dbus # type: ignore
from dbus.mainloop.glib import DBusGMainLoop # type: ignore

#esEss imports
import Globals
from Globals import getFromGlobalStoreValue
from Helper import i, c, d, w, e, logBlackList
from SolarOverheadDistributor import SolarOverheadDistributor
from TimeToGoCalculator import TimeToGoCalculator
from FroniusWattpilot import FroniusWattpilot
from ChargeCurrentReducer import ChargeCurrentReducer

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

class esESS:
  def __init__(self):
    self.config = configparser.ConfigParser()
    self.config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))   
    self.keepAliveTopic = "R/" + self.config["Default"]["VRMPortalID"] + "/keepalive"

    i(Globals.esEssTag, "Initializing " + Globals.esEssTag + " (" + Globals.currentVersionString + ")")
    self.enableModules()
    gobject.timeout_add(int(15000), self.keepAliveLoop)

  def enableModules(self):
   #check, which Modules are enabled and create the respective services. 
      #Some services will be created dynamically during runtime as features/devices join. 
      if((self.config['Modules']['SolarOverheadDistributor']).lower() == 'true'):
         i(Globals.esEssTag, 'SolarOverheadDistributor-Module is enabled.')
         Globals.mqttClient.publish("{0}/$SYS/Modules/SolarOverheadDistributor".format(Globals.esEssTag), "Enabled", 1, True)
         Globals.pvOverhadDistributor = SolarOverheadDistributor()
      else:
         i(Globals.esEssTag, "SolarOverheadDistributor-Module is disabled.")
         Globals.mqttClient.publish("{0}/e$SYS/Modules/SolarOverheadDistributor".format(Globals.esEssTag), "Disabled", 1, True)

      if((self.config['Modules']['TimeToGoCalculator']).lower() == 'true'):
        i(Globals.esEssTag, 'TimeToGoCalculator-Module is enabled.')
        Globals.mqttClient.publish("{0}/$SYS/Modules/TimeToGoCalculator".format(Globals.esEssTag), "Enabled", 1, True)
        Globals.timeToGoCalculator = TimeToGoCalculator()
      else:
        i(Globals.esEssTag, 'TimeToGoCalculator-Module is disabled.')
        Globals.mqttClient.publish("{0}/$SYS/Modules/TimeToGoCalculator".format(Globals.esEssTag), "Disabled", 1, True)

      if((self.config['Modules']['FroniusWattpilot']).lower() == 'true'):
        i(Globals.esEssTag, 'FroniusWattpilot-Module is enabled.')
        Globals.mqttClient.publish("{0}/$SYS/Modules/FroniusWattpilot".format(Globals.esEssTag), "Enabled", 1, True)
        Globals.FroniusWattpilot = FroniusWattpilot()
      else:
         i(Globals.esEssTag, 'FroniusWattpilot-Module is disabled.')
         Globals.mqttClient.publish("{0}/$SYS/Modules/FroniusWattpilot".format(Globals.esEssTag), "Disabled", 1, True)

      if((self.config['Modules']['ChargeCurrentReducer']).lower() == 'true'):
        i(Globals.esEssTag, 'ChargeCurrentReducer-Module is enabled.')
        Globals.mqttClient.publish("{0}/$SYS/Modules/ChargeCurrentReducer".format(Globals.esEssTag), "Enabled", 1, True)
        Globals.chargeCurrentReducer = ChargeCurrentReducer()
      else:
         i(Globals.esEssTag, 'ChargeCurrentReducer-Module is disabled.')
         Globals.mqttClient.publish("{0}/$SYS/Modules/ChargeCurrentReducer".format(Globals.esEssTag), "Disabled", 1, True)

  def keepAliveLoop(self):
      Globals.mqttClient.publish(self.keepAliveTopic, "")
      return True
  
def configureLogging(config):
  logLevelString = config['Default']['LogLevel']
  logLevel = logging.getLevelName(logLevelString)
  logDir = "/data/log/es-ESS"
  
  if not os.path.exists(logDir):
    os.mkdir(logDir)

  logging.basicConfig(format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                      datefmt='%Y-%m-%d %H:%M:%S',
                      level=logLevel,
                      handlers=[
                        TimedRotatingFileHandler(logDir + "/current.log", when="midnight", interval=1, backupCount=14),
                        logging.StreamHandler()
                      ])
  
  import Helper
  #persist some log flags.
  blacklistString = config["LogDetails"]["DontLogDebug"]
  Helper.logBlackList = [x.strip() for x in blacklistString.split(',')] # type: ignore
  

def main(config):
  
  try:
      # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
      from dbus.mainloop.glib import DBusGMainLoop # type: ignore
      DBusGMainLoop(set_as_default=True)
           
      # MQTT setup
      Globals.configureMqtt(config)
      Globals.esESS = esESS()
      
      mainloop = gobject.MainLoop()
      mainloop.run()            
  except Exception as e:
    c("Main", "Exception", exc_info=e)

if __name__ == "__main__":
  # read configuration. TODO: Migrate to UI-Based configuration later.
  config = configparser.ConfigParser()
  config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
  
  configureLogging(config)

  try:
    main(config)
  except Exception as uncoughtException:
     c("UNCOUGHT", "Uncought exception, main() dieded.", exc_info=uncoughtException)
