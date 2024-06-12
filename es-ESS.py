#!/usr/bin/env python
 
# imports
import configparser # for config/ini file
import datetime
from logging.handlers import TimedRotatingFileHandler
import sys
import os
import logging
import threading
import time
from builtins import Exception, int, str
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
from dbus.mainloop.glib import DBusGMainLoop # type: ignore

#esEss imports
import Globals
import Helper
from Globals import MqttSubscriptionType
from Helper import i, c, d, w, e
from esESSService import DbusSubscription, esESSService, WorkerThread, MqttSubscription

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

class esESS:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))   
        self.mainMqttClientConnected = False
        self.localMqttClientConnected = False
        self.mqttThrottlePeriod = int(self.config["Mqtt"]["ThrottlePeriod"])
                
        i(self, "Initializing " + Globals.esEssTag + " (" + Globals.currentVersionString + ")")

        #init core values
        self._services: Dict[str, esESSService] = {}
        self._dbusSubscriptions: Dict[str, list[DbusSubscription]] = {}
        self._mqttSubscriptions: Dict[str, list[MqttSubscription]] = {}
        self._serviceMessageIndex: Dict[str, int] = {}
        self._dbusMonitor: DbusMonitor = None
        
        i(self, "Initializing thread pool with a size of {0}".format(self.config["Default"]["NumberOfThreads"]))
        self.threadPool = ThreadPoolExecutor(int(self.config["Default"]["NumberOfThreads"]))

        if (self.mqttThrottlePeriod > 0):
           self._mainMqttThrottleDictLock = threading.Lock()
           self._mainMqttThrottleDict = { }
           self._localMqttThrottleDictLock = threading.Lock()
           self._localMqttThrottleDict = { }
           self._lastThrottleLog = 0
           self._messageCount = 0
           self._sendCount = 0
           self._lastLocalThrottleLog = 0
           self._localMessageCount = 0
           self._localSendCount = 0
           i(self, "Mqtt-Throttling is enabled to {0}ms".format(self.mqttThrottlePeriod))   

    def configureMqtt(self):
        self.mainMqttClient = mqtt.Client("es-ESS-MQTT-Client")
        self.localMqttClient = mqtt.Client("es-ESS-Local-MQTT-Client")

        i(Globals.esEssTag, "MQTT: Connecting to broker: {0}".format(config["Mqtt"]["Host"]))
        self.mainMqttClient.on_disconnect = self.onMainMqttDisconnect
        self.mainMqttClient.on_connect = self.onMainMqttConnect

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
        self.localMqttClient.on_disconnect = self.onLocalMqttDisconnect
        self.localMqttClient.on_connect = self.onLocalMqttConnect

        self.localMqttClient.connect(
            host="localhost",
            port=1883
        )

        self.localMqttClient.loop_start()

    def onMainMqttConnect(self, client, userdata, flags, rc):
        if rc == 0:
            i(self, "Connected to MQTT broker!")
            self.mainMqttClientConnected = True
        else:
            e(self, "Failed to connect, return code %d\n", rc)
    
    def onLocalMqttConnect(self, client, userdata, flags, rc):
        if rc == 0:
            i(self, "Connected to MQTT broker!")
            self.localMqttClientConnected = True
        else:
            e(self, "Failed to connect, return code %d\n", rc)

    def onMainMqttDisconnect(self, client, userdata, rc):
        c(self, "Mqtt Disconnect. Reconnect not yet implemented ;)")

    def onLocalMqttDisconnect(self, client, userdata, rc):
        c(self, "Mqtt Disconnect. Reconnect not yet implemented ;)")
    
    def _checkAndEnable(self, clazz):
       if (self.config["Services"][clazz].lower()=="true"):
          i(self, "Service {0} is enabled.".format(clazz))
          imp = __import__(clazz)
          class_ = getattr(imp, clazz)
          self._services[clazz] = class_()
       else:
          i(self, "Service {0} is not enabled. Skipping initialization.".format(clazz))   

    def initialize(self):
       self.configureMqtt()

       Helper.waitTimeout(lambda: self.mainMqttClientConnected, 30) or e(self, "Unable to connect to main mqtt wthin 30 seconds...  offline or credentials wrong?")
       Helper.waitTimeout(lambda: self.localMqttClientConnected, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds...offline or credentials wrong?")

       self.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "es-ESS is starting up...")

       self._initializeServices()

       #Finally, do some mqtt reports. 
       if (self.mqttThrottlePeriod > 0):
           self.publishMainMqtt("{0}/$SYS/MqttThrottle/Status", "Enabled")
           self.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "Enabling Mqtt-Throttling.")
       else:
           self.publishMainMqtt("{0}/$SYS/MqttThrottle/Status", "Disabled")

    def _initializeServices(self):
      try:
        #Create Classes, if enabled.
        self.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "Initializing Services.")

        self._checkAndEnable("SolarOverheadDistributor")
        self._checkAndEnable("TimeToGoCalculator")
        self._checkAndEnable("MqttExporter")
        self._checkAndEnable("FroniusWattpilot")
        
        #Init DbusSubscriptions
        dbusSubStructure = {}
        dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}
        for (name, service) in self._services.items():
            self.publishServiceMessage(service, Globals.ServiceMessageType.Operational, "Initializing Dbus-Subscriptions.")
            i(self, "Initializing Dbus-Subscriptions for Service {0}".format(name))
            service.initDbusSubscriptions()

        #Translate subscriptions to dbus sub format.
        for (key, sublist) in self._dbusSubscriptions.items():
            for sub in sublist:
                d(self, "Creating Dbus-Subscriptions for Service {0} on {1} with callback: {2}".format(sub.requestingService.__class__.__name__, sub.valueKey, Helper.formatCallback(sub.callback)))
                
                if (sub.commonServiceName not in dbusSubStructure):
                    dbusSubStructure[sub.commonServiceName] = {}

                if (sub.dbusPath not in dbusSubStructure[sub.commonServiceName]):
                        dbusSubStructure[sub.commonServiceName][sub.dbusPath] = dummy
        
        #Ignore our own services, we don't need them to be scanned. 
        self._dbusMonitor = DbusMonitor(dbusSubStructure, self._dbusValueChanged, ignoreServices=["com.victronenergy.battery.es-ESS", "com.victronenergy.settings.es-ESS"])
    
        #now, that we have subscribed with some generic subscriptions, 
        #we need to elevate these subscriptions to device specific ones,
        #so the get_value command can be used with success.
        for (sn, instance) in self._dbusMonitor.get_service_list().items():
          for (key, sublist) in self._dbusSubscriptions.items():
            for sub in sublist:
               if (sn.startswith(sub.serviceName) and sn != sub.serviceName):
                  d(self, "Elevating {0} of Service {1} to {2}".format(sub.serviceName, sub.requestingService.__class__.__name__, sn))
                  sub.serviceName = sn
      
        #manualy fetch variables one time, then on change is sufficent.
        d(self, "Initializing dbus values for first-use.")
        for (key, sublist) in self._dbusSubscriptions.items():
            for sub in sublist:
              v = self._dbusMonitor.get_value(sub.serviceName, sub.dbusPath, 0)
              sub.value = v
              d(self, "{0}{1}: Value is: {2}".format(sub.serviceName, sub.dbusPath, v))
              
              #process callbacks, if any.
              if (sub.callback is not None):
                  sub.callback(sub)
        
        d(self, "Dbusmonitor initalized.")

        #Init DbusServices of each Service.
        for (name, service) in self._services.items():
            i(self, "Initializing Dbus-Service for Service {0}".format(name))
            self.publishServiceMessage(service, Globals.ServiceMessageType.Operational, "Initializing Dbus-Service.")
            service.initDbusService()

        for (name, service) in self._services.items():
            i(self, "Initializing Mqtt-Subscriptions for Service {0}".format(name))
            self.publishServiceMessage(service, Globals.ServiceMessageType.Operational, "Initializing Mqtt-Subscriptions.")
            service.initMqttSubscriptions()

        for (topic, sublist) in self._mqttSubscriptions.items():
                #TODO: If subList cotanins multiple subscriptions
                #      from different Services, the message_callback_add will fail. 
                #      We then need a wrapper-method, that acts as callback and will 
                #      forward the arrived messages to two or more services. 
            if (len(sublist) > 1):
                e(self, "Multiple subscriptions for topic: {0} - this is currently unsupported.".format(topic))

            for sub in sublist:
                d(self, "Creating Mqtt-Subscriptions for Service {0} on {1} with callback: {2}".format(sub.requestingService.__class__.__name__, sub.topic, Helper.formatCallback(sub.callback)))
                if (sub.type == MqttSubscriptionType.Main):
                    self.mainMqttClient.subscribe(sub.topic, sub.qos)
                    self.mainMqttClient.message_callback_add(sub.topic, sub.callback)
                elif (sub.type == MqttSubscriptionType.Local):
                    self.localMqttClient.subscribe(sub.topic, sub.qos)
                    self.localMqttClient.message_callback_add(sub.topic, sub.callback)

        for (name, service) in self._services.items():
           service.initWorkerThreads()
           for (t) in service._workerThreads:
              i(self, "Scheduling Workerthread {0}".format(Helper.formatCallback(t.thread)))
              self.publishServiceMessage(service, Globals.ServiceMessageType.Operational, "Initializing Worker Thread: {0}".format(Helper.formatCallback(t.thread)))
              gobject.timeout_add(t.interval, self._runThread, t)
      
        #Last round for every service to do some stuff :0)
        for (name, service) in self._services.items():
           d(self, "Finalizing service {0}".format(name))
           self.publishServiceMessage(service, Globals.ServiceMessageType.Operational, "Initializing finished.")
           service.initFinalize()

        i(Globals.esEssTag, "Initialization completed. " + Globals.esEssTag + " (" + Globals.currentVersionString + ") is up and running.")
        self.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "Initializing finished.")

      except Exception as ex:
        c(self, "Exception", exc_info=ex)
    
    def _dbusValueChanged(self, dbusServiceName, dbusPath, dict, changes, deviceInstance):
        try:
          key = DbusSubscription.buildValueKey(dbusServiceName, dbusPath)
          d(self, "Change on dbus for {0} (new value: {1})".format(key, changes['Value'])) 

          for sub in self._dbusSubscriptions[key]:
            #verify serviceinstance. if the subscription is to the more global
            #servicename, we are fine with it.
            if (dbusServiceName.startswith(sub.serviceName)):
              sub.value = changes["Value"]

              if (sub.callback is not None):
                 self.threadPool.submit(sub.callback(sub))

        except Exception as ex:
          c(self, "Exception", exc_info=ex)

    def publishDbusValue(self, sub, value):
       d(self, "Exporting dbus value: {0}{1} => {2}".format(sub.serviceName, sub.dbusPath, value))
       self._dbusMonitor.set_value(sub.serviceName, sub.dbusPath, value)
    
    def _runThread(self, workerThread: WorkerThread):
       d(self, "Running thread: {0}.{1}".format(workerThread.service.__class__.__name__, workerThread.thread.__name__))
       if (workerThread.future is None or workerThread.future.done()):
            self.threadPool.submit(workerThread.thread)
       else:
            w(self, "Thread {0} from {1} is scheduled to run every {2}ms - Future not done, skipping call attempt.".format(workerThread.service.__class__.__name__, workerThread.thread.__name__, workerThread.interval))
       
       return True
    
    def registerDbusSubscription(self, sub):
       if (sub.valueKey not in self._dbusSubscriptions):
          self._dbusSubscriptions[sub.valueKey] = []
       
       self._dbusSubscriptions[sub.valueKey].append(sub)
    
    def registerMqttSubscription(self, sub):
       if (sub.valueKey not in self._mqttSubscriptions):
          self._mqttSubscriptions[sub.valueKey] = []
       
       self._mqttSubscriptions[sub.valueKey].append(sub)

    def publishMainMqtt(self, topic, payload, qos=0, retain=False, forceSend=False):
        
        if (self.mqttThrottlePeriod == 0 or forceSend): 
            self.mainMqttClient.publish(topic, payload, qos, retain)
        else:
           self._messageCount += 1
           #If 2 messages for the same topic are to be published, 
           #delay the second message upto {ThrotllePeriod} milliseconds.
           #replace content as new messages arrive before sending.
           with self._mainMqttThrottleDictLock: 
            if (topic in self._mainMqttThrottleDict):
                self._mainMqttThrottleDict[topic] = (self._mainMqttThrottleDict[topic][0], payload, qos, retain)
            else:
                self._mainMqttThrottleDict[topic] = (time.time(), None, None, None)
                self.mainMqttClient.publish(topic, payload, qos, retain)
                self._sendCount +=1
           
            n = time.time()
            known = 0
            throttled = 0
            for (topic, q) in self._mainMqttThrottleDict.items():
                known +=1
                if (q[0] + self.mqttThrottlePeriod/1000 <= n and q[1] is not None):
                    self.mainMqttClient.publish(topic, q[1], q[2], q[3])
                    self._mainMqttThrottleDict[topic] = (time.time(), None, None, None)
                    self._sendCount +=1
                else:
                   if (q[1] is not None):
                        throttled+=1
            
            if (self._lastThrottleLog + 1 < n):
               self._lastThrottleLog = n
               #i(self, "Throttle-State @{0}: {1} Topics known, {2} throttled, {3} M/s incoming, {4} M/s send!".format(n, known, throttled, self._messageCount, self._sendCount))
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Main/Time".format(Globals.esEssTag), n, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Main/KnownTopics".format(Globals.esEssTag), known, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Main/ThrottledTopics".format(Globals.esEssTag), throttled, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Main/MpsRequested".format(Globals.esEssTag), self._messageCount, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Main/MpsOutgoing".format(Globals.esEssTag), self._sendCount, 0, False, True)
               self._messageCount = 0
               self._sendCount = 0
    
    def publishLocalMqtt(self, topic, payload, qos=0, retain=False, forceSend=False):
        if (self.mqttThrottlePeriod == 0 or forceSend): 
            self.localMqttClient.publish(topic, payload, qos, retain)
    
        else:
           self._localMessageCount += 1
           #If 2 messages for the same topic are to be published, 
           #delay the second message upto {ThrotllePeriod} milliseconds.
           #replace content as new messages arrive before sending.
           with self._localMqttThrottleDictLock: 
            if (topic in self._localMqttThrottleDict):
                self._localMqttThrottleDict[topic] = (self._localMqttThrottleDict[topic][0], payload, qos, retain)
            else:
                self._localMqttThrottleDict[topic] = (time.time(), None, None, None)
                self.localMqttClient.publish(topic, payload, qos, retain)
                self._localSendCount +=1
           
            n = time.time()
            known = 0
            throttled = 0
            for (topic, q) in self._localMqttThrottleDict.items():
                known +=1
                if (q[0] + self.mqttThrottlePeriod/1000 <= n and q[1] is not None):
                    self.localMqttClient.publish(topic, q[1], q[2], q[3])
                    self._localMqttThrottleDict[topic] = (time.time(), None, None, None)
                    self._localSendCount +=1
                else:
                   if (q[1] is not None):
                        throttled+=1
            
            if (self._lastLocalThrottleLog + 1 < n):
               self._lastLocalThrottleLog = n
               #i(self, "Throttle-State @{0}: {1} Topics known, {2} throttled, {3} M/s incoming, {4} M/s send!".format(n, known, throttled, self._localMessageCount, self._localSendCount))
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Local/Time".format(Globals.esEssTag), n, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Local/KnownTopics".format(Globals.esEssTag), known, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Local/ThrottledTopics".format(Globals.esEssTag), throttled, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Local/MpsRequested".format(Globals.esEssTag), self._localMessageCount, 0, False, True)
               self.publishMainMqtt("{0}/$SYS/MqttThrottle/Local/MpsOutgoing".format(Globals.esEssTag), self._localSendCount, 0, False, True)
               self._localMessageCount = 0
               self._localSendCount = 0

    def publishServiceMessage(self, service, type, message):
        serviceName = service.__class__.__name__ if not isinstance(service, str) else service

        key = "{0}{1}".format(serviceName, type)
        if (key not in self._serviceMessageIndex):
           self._serviceMessageIndex[key] = 1
        else:
           self._serviceMessageIndex[key] +=1
        
        if (self._serviceMessageIndex[key] > int(self.config["Default"]["ServiceMessageCount"]) + 1):
           self._serviceMessageIndex[key] = 1

        self.publishMainMqtt("{tag}/$SYS/ServiceMessages/{service}/{type}/Message{id:02d}".format(tag=Globals.esEssTag, service=serviceName, type=type, id=self._serviceMessageIndex[key]), "{0} | {1}".format(str(datetime.datetime.now()), message) , 0, True, True)
        nextOne = self._serviceMessageIndex[key] +1
        if (nextOne > int(self.config["Default"]["ServiceMessageCount"]) + 1):
            nextOne = 1
        
        self.publishMainMqtt("{tag}/$SYS/ServiceMessages/{service}/{type}/Message{id:02d}".format(tag=Globals.esEssTag, service=serviceName, type=type, id=nextOne), "{0} | {1}".format(str(datetime.datetime.now()), "-------------------------") , 0, True, True)

    

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

      i("Main", "-----------------------------------------------------------------------------------------")
      i("Main", "-----------------------------------------------------------------------------------------")
      i("Main", "-----------------------------------------------------------------------------------------")
           
      Globals.esESS = esESS()
      Globals.esESS.initialize()
      
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
