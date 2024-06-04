#!/usr/bin/env python
 
# imports
import configparser # for config/ini file
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

# victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService # type: ignore
import dbus # type: ignore
from dbus.mainloop.glib import DBusGMainLoop # type: ignore

#esEss imports
import Globals
from Globals import getFromGlobalStoreValue
from Helper import i, c, d, w, e
from PVOverheadDitributionService import PVOverheadDistributionService
from TimeToGoCalculator import TimeToGoCalculator
from FroniusWattpilotService import FroniusWattpilotService

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

def configureLogging(config):
  logLevelString = config['Default']['LogLevel']
  logLevel = logging.getLevelName(logLevelString)
  logDir = "/data/log/dbus-es-ess"
  
  if not os.path.exists(logDir):
    os.mkdir(logDir)

  logging.basicConfig(    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                          datefmt='%Y-%m-%d %H:%M:%S',
                          level=logLevel,
                          handlers=[
                              logging.FileHandler(logDir + "/es-ess.log"),
                              logging.StreamHandler()
                          ])
  
  #persist some log flags.
  Globals.logIncomingMqttMessages = config["LogDetails"]["LogIncomingMqttMessages"].lower() == "true"

def enableModules(config):
   #check, which Modules are enabled and create the respective services. 
      #Some services will be created dynamically during runtime as features/devices join. 
      if((config['Modules']['PVOverheadDistributor']).lower() == 'true'):
         pvOverheadServiceVRMId = config['PVOverheadDistributor']['VRMInstanceID']
         i(Globals.esEssTag, 'PVOverheadDistributor-Module is enabled. Initializing service on VRM-ID: ' + pvOverheadServiceVRMId)
         Globals.pvOverheadDistributionService = PVOverheadDistributionService()
      else:
         i(Globals.esEssTag, "PVOverheadDistributor-Module is disabled.")

      if((config['Modules']['TimeToGoCalculator']).lower() == 'true'):
        i(Globals.esEssTag, 'TimeToGoCalculator-Module is enabled.')
        Globals.timeToGoCalculator = TimeToGoCalculator()
      else:
        i(Globals.esEssTag, 'TimeToGoCalculator-Module is disabled.')

      if((config['Modules']['FroniusWattpilot']).lower() == 'true'):
        i(Globals.esEssTag, 'FroniusWattpilot-Module is enabled.')
        Globals.froniusWattpilotService = FroniusWattpilotService()
      else:
         i(Globals.esEssTag, 'FroniusWattpilot-Module is disabled.')

def main():
  # read configuration. TODO: Migrate to UI-Based configuration later.
  config = configparser.ConfigParser()
  config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
  
  configureLogging(config)
  i(Globals.esEssTag, "Startup of " + Globals.esEssTag + " (" + Globals.currentVersionString + ")")

  try:
      # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
      from dbus.mainloop.glib import DBusGMainLoop # type: ignore
      DBusGMainLoop(set_as_default=True)
           
      # MQTT setup
      Globals.configureMqtt(config)
      enableModules(config)

      mainloop = gobject.MainLoop()
      mainloop.run()            
  except Exception as e:
    logging.critical('Error at %s', 'main', exc_info=e)

if __name__ == "__main__":
  main()
