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
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

import paho.mqtt.client as mqtt # type: ignore

# victronr
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore
from dbusmonitor import DbusMonitor # type: ignore
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
from MqttExporter import MqttExporter
from esESSService import DbusSubscription, esESSService, WorkerThread

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

class esESS:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))   

        #init core values
        self._services: Dict[str, esESSService] = {}
        self._dbusSubscriptions: Dict[str, list[DbusSubscription]] = {}
        self._dbusMonitor: DbusMonitor = None
        
        i(self, "Initializing thread pool with a size of {0}".format(self.config["Default"]["NumberOfThreads"]))
        self.threadPool = ThreadPoolExecutor(int(self.config["Default"]["NumberOfThreads"]))

        i(Globals.esEssTag, "Initializing " + Globals.esEssTag + " (" + Globals.currentVersionString + ")")

    def _initializeServices(self):
      try:
        #Create Classes
        self._services["TimeToGoCalculator"] = TimeToGoCalculator()

        #Init DbusServices of each Service.
        for (name, service) in self._services.items():
            i(self, "Initializing Dbus-Service for Service {0}".format(name))
            service.initDbusService()

        #Init DbusSubscriptions
        dbusSubStructure = {}
        dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}
        for (name, service) in self._services.items():
            i(self, "Initializing Dbus-Subscriptions for Service {0}".format(name))
            service.initDbusSubscriptions()

            #nothing to to here, callback will handle subscriptions.
            for (key, sub) in service._dbusPaths.items():
                d(self, "Creating Dbus-Subscriptions for Service {0} on {1}{2} with callback: {3}".format(name, sub.serviceName, sub.dbusPath, sub.callback))
                
                if (sub.valueKey not in self._dbusSubscriptions):
                    self._dbusSubscriptions[sub.valueKey] = []
                
                self._dbusSubscriptions[sub.valueKey].append(sub)

                if (sub.commonServiceName not in dbusSubStructure):
                    dbusSubStructure[sub.commonServiceName] = {}

                if (sub.dbusPath not in dbusSubStructure[sub.commonServiceName]):
                     dbusSubStructure[sub.commonServiceName][sub.dbusPath] = dummy
        
        #Ignore our own services, we don't need them to be scanned. 
        self._dbusMonitor = DbusMonitor(dbusSubStructure, self._dbusValueChanged, ignoreServices=["com.victronenergy.battery.es-ESS"])
        
        #manualy fetch variables one time, then on change is sufficent. 
        d(self, "Initializing dbus values for first-use.")
        for (name, service) in self._services.items():
           for (key, sub) in service._dbusPaths.items():
              v = self._dbusMonitor.get_value(sub.commonServiceName, sub.dbusPath, 0)
              sub.value = v
              d(self, "{0}{1}: Value is: {2}".format(sub.commonServiceName, sub.dbusPath, v))
              
              #process callbacks, if any.
              if (sub.callback is not None):
                  sub.callback(sub)
        
        d(self, "Dbusmonitor initalized.")
        

        #TODO: MQTT

        gobject.timeout_add(1000, self.loop)
        for (name, service) in self._services.items():
           service.initWorkerThreads()
           for (t) in service._workerThreads:
              i(self, "Scheduling Workerthread {0}.{1}".format(t.service.__class__.__name__, t.thread.__name__))
              gobject.timeout_add(t.interval, self._runThread, t)
        
      
      except Exception as ex:
        c(self, "Exception", exc_info=ex)
      
                      
            

    
      
      
      
      #legacy modules bellow. 
      
      
      #check, which Modules are enabled and create the respective services. 
      #Some services will be created dynamically during runtime as features/devices join. 
      if((self.config['Modules']['SolarOverheadDistributor']).lower() == 'true'):
        i(Globals.esEssTag, 'SolarOverheadDistributor-Module is enabled.')
        Globals.mqttClient.publish("{0}/$SYS/Modules/SolarOverheadDistributor".format(Globals.esEssTag), "Enabled", 1, True)
        Globals.solarOverheadDistributor = SolarOverheadDistributor()
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

      if((self.config['Modules']['MqttExporter']).lower() == 'true'):
        i(Globals.esEssTag, 'MqttExporter-Module is enabled.')
        Globals.mqttClient.publish("{0}/$SYS/Modules/MqttExporter".format(Globals.esEssTag), "Enabled", 1, True)
        Globals.mqttExporter = MqttExporter()
      else:
        i(Globals.esEssTag, 'MqttExporter-Module is disabled.')
        Globals.mqttClient.publish("{0}/$SYS/Modules/MqttExporter".format(Globals.esEssTag), "Disabled", 1, True)

      i(Globals.esEssTag, "Initialization completed. " + Globals.esEssTag + " (" + Globals.currentVersionString + ") is up and running.")
    
    def _dbusValueChanged(self, dbusServiceName, dbusPath, dict, changes, deviceInstance):
        try:
          key = DbusSubscription.buildValueKey(dbusServiceName, dbusPath)
          d(self, "Change on dbus for {0} (new value: {1})".format(key, changes['Value'])) 

          for sub in self._dbusSubscriptions[key]:
            #verify serviceinstance.
            d(self, "reporting service: {0}, matchService: {1}".format(dbusServiceName, sub.serviceName))
            if (sub.serviceName == dbusServiceName):
              sub.value = changes["Value"]

        except Exception as ex:
          c(self, "Exception", exc_info=ex)

    def publishDbusValue(self, sub, value):
       d(self, "Exporting dbus value: {0}{1} => {2}".format(sub.serviceName, sub.dbusPath, value))
       self._dbusMonitor.set_value(sub.serviceName, sub.dbusPath, value)
    
    def _runThread(self, workerThread: WorkerThread):
       d(self, "Attempting to run thread: {0}.{1}".format(workerThread.service.__class__.__name__, workerThread.thread.__name__))
       if (workerThread.future is None or workerThread.future.done()):
            self.threadPool.submit(workerThread.thread)
       else:
            w(self, "Thread {0} from {1} is scheduled to run every {2}ms - Future not done, skipping call attempt.".format(workerThread.service.__class__.__name__, workerThread.thread.__name__, workerThread.interval))
       
       return True
    
    def loop(self):
       d(self, "Alive...")
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
      Globals.esESS._initializeServices()
      
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
