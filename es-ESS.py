#!/usr/bin/env python
 
# imports
import configparser # for config/ini file
import datetime
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
        
        i(self, "Initializing " + Globals.esEssTag + " (" + Globals.currentVersionString + ")")

        #init core values
        self._services: Dict[str, esESSService] = {}
        self._dbusSubscriptions: Dict[str, list[DbusSubscription]] = {}
        self._dbusMonitor: DbusMonitor = None
        
        i(self, "Initializing thread pool with a size of {0}".format(self.config["Default"]["NumberOfThreads"]))
        self.threadPool = ThreadPoolExecutor(int(self.config["Default"]["NumberOfThreads"]))
        self.configureMqtt()

    def configureMqtt(self):
        self.mainMqttClient = mqtt.Client("es-ESS-MQTT-Client")
        self.localMqttClient = mqtt.Client("es-ESS-Local-MQTT-Client")

        i(Globals.esEssTag, "MQTT: Connecting to broker: {0}".format(config["Mqtt"]["Host"]))
        self.mainMqttClient.on_disconnect = self.onMainMqttDisconnect
        self.mainMqttClient.on_connect = self.onMainMqttConnect
        self.mainMqttClient.on_message = self.onMainMqttMessage

        if 'User' in config['Mqtt'] and 'Password' in config['Mqtt'] and config['Mqtt']['User'] != '' and config['Mqtt']['Password'] != '':
            self.mainMqttClient.username_pw_set(username=config['Mqtt']['User'], password=config['Mqtt']['Password'])

        self.mainMqttClient.will_set("es-ESS/$SYS/Status", "Offline", 2, True)

        self.mainMqttClient.connect(
            host=config["Mqtt"]["Host"],
            port=int(config["Mqtt"]["Port"])
        )

        self.mainMqttClient.loop_start()
        self.mainMqttClient.publish("es-ESS/$SYS/Status", "Online", 2, True)
        self.mainMqttClient.publish("es-ESS/$SYS/Version", Globals.currentVersionString, 2, True)
        self.mainMqttClient.publish("es-ESS/$SYS/ConnectionTime", time.time(), 2, True)
        self.mainMqttClient.publish("es-ESS/$SYS/ConnectionDateTime", str(datetime.datetime.now()), 2, True)
        self.mainMqttClient.publish("es-ESS/$SYS/Github", "https://github.com/realdognose/es-ESS", 2, True)

        #local mqtt
        i(self, "Connecting to broker: {0}".format("localhost"))
        self.localMqttClient.on_disconnect = onLocalMqttDisconnect
        self.localMqttClient.on_connect = onLocalMqttConnect
        self.localMqttClient.on_message = onLocalMqttMessage

        self.localMqttClient.connect(
            host="localhost",
            port=1883
        )

        self.localMqttClient.loop_start()

    def onMainMqttConnect(self, client, userdata, flags, rc):
        if rc == 0:
            i(self, "Connected to MQTT broker!")
        else:
            e(self, "Failed to connect, return code %d\n", rc)
    
    def onLocalMqttConnect(self, client, userdata, flags, rc):
        if rc == 0:
            i(self, "Connected to MQTT broker!")
        else:
            e(self, "Failed to connect, return code %d\n", rc)

    def onMainMqttDisconnect(self, client, userdata, rc):
        c(self, "Mqtt Disconnect. Reconnect not yet implemented ;)")

    def onLocalMqttDisconnect(self, client, userdata, rc):
        c(self, "Mqtt Disconnect. Reconnect not yet implemented ;)")
    
    def onMainMqttMessage(self, client, userdata, msg):
        try:
          value =  str(msg.payload)[2:-1]
          d(self, "Received MQTT-Message: {0} => {1}".format(msg.topic, value))

          for sub in self._mqttSubscriptions[msg.topic]:
            sub.value = value # only makes sence for non-wildcard topics, but convinient to access last value. 

            if (sub.callback is not None):
                 sub.callback(sub, msg.topic, value)

        except Exception as e:
          c(self, "Exception catched", exc_info=e)
   
    def onLocalMqttMessage(self, client, userdata, msg):
        try:
          d(self, "Received MQTT-Message: {0} => {1}".format(msg.topic, str(msg.payload)[2:-1]))

          #TODO: Check for service subscriptions.
          #TODO: Update Subscription object. 
        except Exception as e:
          c(self, "Exception catched", exc_info=e)

    def _checkAndEnable(self, clazz):
       if (self.config["Services"][clazz].lower()=="true"):
          i(self, "Service {0} is enabled.".format(clazz))
          imp = __import__(clazz)
          class_ = getattr(imp, clazz)
          self._services[clazz] = class_()
       else:
          i(self, "Service {0} is not enabled. Skipping initialization.".format(clazz))   

    def _initializeServices(self):
      try:
        #Create Classes, if enabled.
        self._checkAndEnable("SolarOverheadDistributor")
        self._checkAndEnable("TimeToGoCalculator")
        
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
            for (key, sub) in service._dbusSubscriptions.items():
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
           for (key, sub) in service._dbusSubscriptions.items():
              v = self._dbusMonitor.get_value(sub.commonServiceName, sub.dbusPath, 0)
              sub.value = v
              d(self, "{0}{1}: Value is: {2}".format(sub.commonServiceName, sub.dbusPath, v))
              
              #process callbacks, if any.
              if (sub.callback is not None):
                  sub.callback(sub)
        
        d(self, "Dbusmonitor initalized.")

        for (name, service) in self._services.items():
            i(self, "Initializing Mqtt-Subscriptions for Service {0}".format(name))
            service.initMqttSubscriptions()

            for (topic, sub) in service._mqttSubscriptions.items():
                d(self, "Creating Mqtt-Subscriptions for Service {0} on {1} with callback: {2}".format(name, sub.topic, sub.callback))
                
                if (sub.valueKey not in self._mqttSubscriptions):
                    self._mqttSubscriptions[sub.topic] = []
                
                self._mqttSubscriptions[sub.topic].append(sub)

        gobject.timeout_add(1000, self.loop)
        for (name, service) in self._services.items():
           service.initWorkerThreads()
           for (t) in service._workerThreads:
              i(self, "Scheduling Workerthread {0}.{1}".format(t.service.__class__.__name__, t.thread.__name__))
              gobject.timeout_add(t.interval, self._runThread, t)
      
        i(Globals.esEssTag, "Initialization completed. " + Globals.esEssTag + " (" + Globals.currentVersionString + ") is up and running.")

      except Exception as ex:
        c(self, "Exception", exc_info=ex)
    
    def _dbusValueChanged(self, dbusServiceName, dbusPath, dict, changes, deviceInstance):
        try:
          key = DbusSubscription.buildValueKey(dbusServiceName, dbusPath)
          d(self, "Change on dbus for {0} (new value: {1})".format(key, changes['Value'])) 

          for sub in self._dbusSubscriptions[key]:
            #verify serviceinstance.
            d(self, "reporting service: {0}, matchService: {1}".format(dbusServiceName, sub.serviceName))
            if (sub.serviceName == dbusServiceName):
              sub.value = changes["Value"]

              if (sub.callback is not None):
                 sub.callback(sub)

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
    
    def publishMainMqtt(self, topic, payload, qos=0, retain=False):
       #TODO: Add throttling here. 
       self.mainMqttClient.publish(topic, payload, qos, retain)
    
    def publishLocalMqtt(self, topic, payload, qos=0, retain=False):
       #TODO: Add throttling here. 
       self.localMqttClient.publish(topic, payload, qos, retain)
    

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
