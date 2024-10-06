#!/usr/bin/env python
 
# imports
import configparser # for config/ini file
import datetime
from logging.handlers import TimedRotatingFileHandler
import signal
import sys
import os
import logging
import threading
import time
from builtins import Exception, int, str
from concurrent.futures import ThreadPoolExecutor
from typing import Dict
import ssl

if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

import paho.mqtt.client as mqtt # type: ignore

# victronr
sys.path.insert(1, '/data/es-ESS/velib_python-master')
from vedbus import VeDbusService # type: ignore
from dbusmonitor import DbusMonitor # type: ignore
from dbus.mainloop.glib import DBusGMainLoop # type: ignore

#esEss imports
import Globals
import Helper
from Globals import MqttSubscriptionType
from Helper import i, c, d, w, e, t
from esESSService import DbusSubscription, esESSService, WorkerThread, MqttSubscription

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

class esESS:
    def __init__(self):
        #First thing to do is check, if the current configuration matches the desired version.
        #if not, upgrade to most recent version, save changes and reload configuration file. 
        self._validateConfiguration()
        
        self._sigTermInvoked=False   
        self.mainMqttClientConnected = False
        self.localMqttClientConnected = False
        self.mqttThrottlePeriod = int(self.config["Mqtt"]["ThrottlePeriod"]) or 0
        
        i(self, "Initializing " + Globals.esEssTag + " (" + Globals.currentVersionString + ")")

        #init core values
        self._services: Dict[str, esESSService] = {}
        self._dbusSubscriptions: Dict[str, list[DbusSubscription]] = {}
        self._mqttSubscriptions: Dict[str, list[MqttSubscription]] = {}
        self._serviceMessageIndex: Dict[str, int] = {}
        self._dbusMonitor: DbusMonitor = None
        self._gridSetPointRequests: Dict[str, float] = {}
        self._gridSetPointDefault = float(self.config["Common"]["DefaultPowerSetPoint"])
        self._gridSetPointCurrent = -99999 #use a unreal number at first, so es-ESS will detect a change upon restart and guarantee to set default GSP.
        self._threadExecutionsMinute = 0
        
        i(self, "Initializing thread pool with a size of {0}".format(self.config["Common"]["NumberOfThreads"]))
        self.threadPool = ThreadPoolExecutor(int(self.config["Common"]["NumberOfThreads"]), "TPt")

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

        if (self.config["Mqtt"]["SslEnabled"].lower() == "true"):
            i(self, "Connecting to broker: {0}://{1}:{2}".format("tcp-ssl", config["Mqtt"]["Host"], config["Mqtt"]["Port"]))
            self.mainMqttClient.tls_set(cert_reqs=ssl.CERT_NONE)
            self.mainMqttClient.tls_insecure_set(True)
            self.mainMqttClient.connect(
                host=config["Mqtt"]["Host"],
                port=int(config["Mqtt"]["Port"])
            )
            
        else:
            i(self, "Connecting to broker: {0}://{1}:{2}".format("tcp", config["Mqtt"]["Host"], config["Mqtt"]["Port"]))
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
        self.localMqttClient.on_disconnect = self.onLocalMqttDisconnect
        self.localMqttClient.on_connect = self.onLocalMqttConnect

        if (self.config["Mqtt"]["LocalSslEnabled"].lower() == "true"):
            i(self, "Connecting to broker: {0}://{1}:{2}".format("tcp-ssl", "localhost", 8883))
            self.localMqttClient.tls_set(cert_reqs=ssl.CERT_NONE)
            self.localMqttClient.tls_insecure_set(True)
            #TODO: After a system reboot, es-ESS is starting faster than the local mqtt, which might lead to connection issues. 
            #      Either loop in a try/error, or sth.
            #      Similiar issues might occur for the dbus service, if devices are not yet registered?
            self.localMqttClient.connect(
                host="localhost",
                port=8883
            )
            
        else:
            i(self, "Connecting to broker: {0}://{1}:{2}".format("tcp", "localhost", 1883))
            self.localMqttClient.connect(
                host="localhost",
                port=1883
            )

        self.localMqttClient.loop_start()

    def onMainMqttConnect(self, client, userdata, flags, rc):
        if rc == 0:
            i(self, "Connected to MQTT broker!")
            self.mainMqttClientConnected = True

            #Check, if we need to subscribe again.
            for (key, sublist) in self._mqttSubscriptions.items():
                for sub in sublist:
                    d(self, "Creating Mqtt-Subscriptions for Service {0} on {1} with callback: {2}".format(sub.requestingService.__class__.__name__, sub.topic, Helper.formatCallback(sub.callback)))
                    if (sub.type == MqttSubscriptionType.Main):
                        self.mainMqttClient.subscribe(sub.topic, sub.qos)
                        self.mainMqttClient.message_callback_add(sub.topic, sub.callback)
        else:
            e(self, "Failed to connect, return code %d\n", rc)
    
    def onLocalMqttConnect(self, client, userdata, flags, rc):
        if rc == 0:
            i(self, "Connected to MQTT broker!")
            self.localMqttClientConnected = True
            
            #Check, if we need to subscribe again.
            for (key, sublist) in self._mqttSubscriptions.items():
                for sub in sublist:
                    d(self, "Creating Mqtt-Subscriptions for Service {0} on {1} with callback: {2}".format(sub.requestingService.__class__.__name__, sub.topic, Helper.formatCallback(sub.callback)))
                    if (sub.type == MqttSubscriptionType.Local):
                        self.mainMqttClient.subscribe(sub.topic, sub.qos)
                        self.mainMqttClient.message_callback_add(sub.topic, sub.callback)
        else:
            e(self, "Failed to connect, return code %d\n", rc)

    def onMainMqttDisconnect(self, client, userdata, rc):
        w(self, "Mqtt Disconnect.")

        if (self.mainMqttClient.reconnect):
            i(self, "Waiting for automatic reconnect.")
        else:
            w(self, "Automatic reconnect is disabled.")

    def onLocalMqttDisconnect(self, client, userdata, rc):
        w(self, "Mqtt Disconnect.")

        if (self.localMqttClient.reconnect):
            i(self, "Waiting for automatic reconnect.")
        else:
            w(self, "Automatic reconnect is disabled.")

    
    def _checkAndEnable(self, clazz):
       if (self.config["Services"][clazz].lower()=="true"):
          i(self, "Service {0} is enabled.".format(clazz))
          imp = __import__(clazz)
          class_ = getattr(imp, clazz)
          self._services[clazz] = class_()
       else:
          i(self, "Service {0} is not enabled. Skipping initialization.".format(clazz))  

       self.publishMainMqtt("{0}/{1}".format(Globals.esEssTag, clazz), "Enabled" if self.config["Services"][clazz].lower()=="true" else "Disabled") 

    def _validateConfiguration(self):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        #TODO: Validate config exists, else use sample?
        self.config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
        loadedVersion = int(self.config["Common"]["ConfigVersion"])

        #Version upgrades to be berformed. A User may skip versions during the upgrade process, so 
        #make sure each change is applied incrementally. 
        version = 2
        if (loadedVersion < version):
            self._backupConfig()
            i(self, "Upgrading configuration to v{0}".format(version))
            self.config["Common"]["ConfigVersion"] = "{0}".format(version)

            #Version 2 introduced Shelly3EMGrid and ShellyPMInverter
            self.config["Services"]["Shelly3EMGrid"] = "false"
            self.config["Services"]["ShellyPMInverter"] = "false"
            
        version = 3
        if (loadedVersion < version):
            self._backupConfig()
            i(self, "Upgrading configuration to v{0}".format(version))
            self.config["Common"]["ConfigVersion"] = "{0}".format(version)

            #Strategy of SolarOverheadDistributor is obsolete.
            self.config.remove_option("SolarOverheadDistributor", "Strategy")

        version = 4
        if (loadedVersion < version):
            self._backupConfig()
            i(self, "Upgrading configuration to v{0}".format(version))
            self.config["Common"]["ConfigVersion"] = "{0}".format(version)

            #Introducing MqttDC
            #Create Service Control Flag, individual Entries are to be created by user.
            self.config["Services"]["MqttDC"] = "false"

        #All required configuration changes applied. Save new file, create a backup of the existing configuration. 
        if (loadedVersion < int(self.config["Common"]["ConfigVersion"])):
            with open("{0}/config.ini".format(os.path.dirname(os.path.realpath(__file__))), 'w') as configfile:
                self.config.write(configfile)
            
        else:
            i(self, "Running on most recent configuration file version: v{0}".format(loadedVersion))

    def _backupConfig(self):
        i(self, "Creating configuration v{0} backup file.".format(self.config["Common"]["ConfigVersion"]))
        with open("{0}/config.ini.v{1}.backup".format(os.path.dirname(os.path.realpath(__file__)), self.config["Common"]["ConfigVersion"]), 'w') as configfile:
            self.config.write(configfile)

    def initialize(self):
       self.configureMqtt()

       Helper.waitTimeout(lambda: self.mainMqttClientConnected, 30) or e(self, "Unable to connect to main mqtt wthin 30 seconds...  offline or credentials wrong?")
       Helper.waitTimeout(lambda: self.localMqttClientConnected, 30) or e(self, "Unable to connect to wattpilot wthin 30 seconds...offline or credentials wrong?")

       self.publishServiceMessage(self,  "es-ESS is starting up...")

       gobject.timeout_add(60000, self._signOfLive)
       
       self._initializeServices()

       #Finally, do some mqtt reports. 
       if (self.mqttThrottlePeriod > 0):
           self.publishMainMqtt("{0}/$SYS/MqttThrottle/Status".format(Globals.esEssTag), "Enabled")
           self.publishServiceMessage(self, "Enabling Mqtt-Throttling.")
       else:
           self.publishMainMqtt("{0}/$SYS/MqttThrottle/Status", "Disabled")

    def _initializeServices(self):
        try:
            #Create Classes, if enabled.
            self.publishServiceMessage(self, "Initializing Services.")

            self._checkAndEnable("SolarOverheadDistributor")
            self._checkAndEnable("TimeToGoCalculator")
            self._checkAndEnable("FroniusSmartmeterJSON")
            self._checkAndEnable("MqttExporter")
            self._checkAndEnable("FroniusWattpilot")
            self._checkAndEnable("MqttTemperature")
            self._checkAndEnable("NoBatToEV")
            self._checkAndEnable("Shelly3EMGrid")
            self._checkAndEnable("ShellyPMInverter")
            
            #work in progress, but onhold.
            #self._checkAndEnable("Grid2Bat")
            #self._checkAndEnable("MqttDC")
            #self._checkAndEnable("ChargeCurrentReducer")
            #self._checkAndEnable("FroniusSmartmeterRS485")

            #Init DbusSubscriptions
            dbusSubStructure = {}
            dummy = {'code': None, 'whenToLog': 'configChange', 'accessLevel': None}
            for (name, service) in self._services.items():
                self.publishServiceMessage(service, "Initializing Dbus-Subscriptions.")
                i(self, "Initializing Dbus-Subscriptions for Service {0}".format(name))
                service.initDbusSubscriptions()

            #Init own subscriptions. 
            self.timezoneDbus = DbusSubscription(self, "com.victronenergy.settings", "/Settings/System/TimeZone", self._timeZoneChanged)
            self.registerDbusSubscription(self.timezoneDbus)

            #Translate subscriptions to dbus sub format.
            for (key, sublist) in self._dbusSubscriptions.items():
                for sub in sublist:
                    (self, "Creating Dbus-Subscriptions for Service {0} on {1} with callback: {2}".format(sub.requestingService.__class__.__name__, sub.valueKey, Helper.formatCallback(sub.callback)))
                
                    if (sub.commonServiceName not in dbusSubStructure):
                        dbusSubStructure[sub.commonServiceName] = {}

                    if (sub.dbusPath not in dbusSubStructure[sub.commonServiceName]):
                        dbusSubStructure[sub.commonServiceName][sub.dbusPath] = dummy
        
            #Ignore our own services, we don't need them to be scanned. 
            ignoreServices=["com.victronenergy.battery.esESS", 
                            "com.victronenergy.settings.esESS", 
                            "com.victronenergy.temperature.esESS",
                            "com.victronenergy.grid.esESS"]
        
            #Initialize dbus on a seperate thred, so our services currently initializing can
            #respond to service calls during monitoring.
            self._dbusMonitor = DbusMonitor(dbusSubStructure, self._dbusValueChanged, ignoreServices=ignoreServices)
    
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
                self.publishServiceMessage(service, "Initializing Dbus-Service.")
                service.initDbusService()

            for (name, service) in self._services.items():
                i(self, "Initializing Mqtt-Subscriptions for Service {0}".format(name))
                self.publishServiceMessage(service, "Initializing Mqtt-Subscriptions.")
                service.initMqttSubscriptions()               

            for (name, service) in self._services.items():
                service.initWorkerThreads()             

            #own worker threads.
            self.registerWorkerThread(WorkerThread(self, self._manageGridSetPoint, 5000, False))
      
            #Last round for every service to do some stuff :0)
            for (name, service) in self._services.items():
                d(self, "Finalizing service {0}".format(name))
                self.publishServiceMessage(service, "Initializing finished.")
                service.initFinalize()

            i(Globals.esEssTag, "Initialization completed. " + Globals.esEssTag + " (" + Globals.currentVersionString + ") is up and running.")
            self.publishServiceMessage(self, "Initializing finished.")

        except Exception as ex:
            c(self, "Exception", exc_info=ex)
    
    def _timeZoneChanged(self, sub):
        self.publishServiceMessage(self, "Timezone detected as '{0}'".format(sub.value))
        Globals.userTimezone = sub.value

    def _dbusValueChanged(self, dbusServiceName, dbusPath, dict, changes, deviceInstance):
        try:
            key = DbusSubscription.buildValueKey(dbusServiceName, dbusPath)
            t(self, "Change on dbus for {0} (new value: {1})".format(key, changes['Value'])) 

            for sub in self._dbusSubscriptions[key]:
                #verify serviceinstance. if the subscription is to the more global
                #servicename, we are fine with it.
                if (dbusServiceName.startswith(sub.serviceName)):
                    sub.value = changes["Value"]

                if (sub.callback is not None):
                    self.threadPool.submit(sub.callback(sub))

        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def publishDbusValue(self, sub:DbusSubscription, value):
        d(self, "Exporting dbus value: {0}{1} => {2}".format(sub.serviceName, sub.dbusPath, value))
        self._dbusMonitor.set_value(sub.serviceName, sub.dbusPath, value)
    
    def _runThread(self, workerThread: WorkerThread):
        try:
            if (self._sigTermInvoked):
                return False
        
            t(self, "Running thread: {0}".format(Helper.formatCallback(workerThread.thread)))
            if (workerThread.future is None or workerThread.future.done()):
                self._threadExecutionsMinute+=1
                workerThread.future = self.threadPool.submit(workerThread.thread)
            else:
                w(self, "Thread {0} from {1} is scheduled to run every {2}ms - Future not done, skipping call attempt. Consider lowering the execution-frequency".format(workerThread.thread.__name__,workerThread.service.__class__.__name__, workerThread.interval))
        
            if (workerThread.onlyOnce):
                return False
        
            return True
        
        except Exception as ex:
            c(self, "Exception", exc_info=ex)
    
    def _signOfLive(self):
        self.publishServiceMessage(self, "Executed {0} threads in the past minute.".format(self._threadExecutionsMinute))
        self._threadExecutionsMinute = 0
        return True
    
    def _manageGridSetPoint(self):
        try:
            if (self._sigTermInvoked):
                return
            
            gsp = self._gridSetPointDefault

            for (k,v) in self._gridSetPointRequests.items():
                if (v is not None):
                    d(self, "Grid Set Point request of {0} is {1}".format(k,v))
                    gsp += v
            
            #only publish, if there is a change in current GSP.
            if (gsp != self._gridSetPointCurrent):
                d(self, "Combined all GSP-Requests, new GSP is: {0}".format(gsp))
                self._gridSetPointCurrent = gsp
                self.publishLocalMqtt("W/{0}/settings/0/Settings/CGwacs/AcPowerSetPoint".format(self.config["Common"]["VRMPortalID"]), "{\"value\": " + str(gsp) + "}", 1 ,False)

        except Exception as ex:
            c(self, "Exception in grid set point control. Trying to restore default GSP.", exc_info=ex)

            #exception is bad, try to set default gsp. 
            self.publishLocalMqtt("W/{0}/settings/0/Settings/CGwacs/AcPowerSetPoint".format(self.config["Common"]["VRMPortalID"]), "{\"value\": " + str(self._gridSetPointDefault) + "}", 1 ,False)


    def registerDbusSubscription(self, sub:DbusSubscription):
        if (sub.valueKey not in self._dbusSubscriptions):
            self._dbusSubscriptions[sub.valueKey] = []
       
        self._dbusSubscriptions[sub.valueKey].append(sub)

    def registerGridSetPointRequest(self, service:esESSService, request:float):
        self._gridSetPointRequests[service.__class__.__name__] = request
    
    def revokeGridSetPointRequest(self, service:esESSService):
        self.registerGridSetPointRequest(service, None)
    
    def registerMqttSubscription(self, sub:MqttSubscription):
        if (sub.valueKey not in self._mqttSubscriptions):
            self._mqttSubscriptions[sub.valueKey] = []
       
        self._mqttSubscriptions[sub.valueKey].append(sub)

        d(self, "Creating Mqtt-Subscriptions for Service {0} on {1} with callback: {2}".format(sub.requestingService.__class__.__name__, sub.topic, Helper.formatCallback(sub.callback)))
        if (sub.type == MqttSubscriptionType.Main):
            self.mainMqttClient.subscribe(sub.topic, sub.qos)
            self.mainMqttClient.message_callback_add(sub.topic, sub.callback)
        elif (sub.type == MqttSubscriptionType.Local):
            self.localMqttClient.subscribe(sub.topic, sub.qos)
            self.localMqttClient.message_callback_add(sub.topic, sub.callback)

    def registerWorkerThread(self, t:WorkerThread):
        i(self, "Scheduling Workerthread {0}".format(Helper.formatCallback(t.thread)))
        self.publishServiceMessage(t.service, "Initializing Worker Thread: {0}".format(Helper.formatCallback(t.thread)))
        gobject.timeout_add(t.interval, self._runThread, t)

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

    def publishServiceMessage(self, service, message, type=Globals.ServiceMessageType.Operational):
        #Na, that's annoying - for now ;)
        #if (type == Globals.ServiceMessageType.Operational):
        #   i(service, "Service Message: {0}".format(message))

        if (not self.mainMqttClient.is_connected):
           w(self, "Mqtt not connected, ignoring sending attempt.")
           return

        serviceName = service.__class__.__name__ if not isinstance(service, str) else service
        serviceName = serviceName if not isinstance(service, esESS) else "$SYS"
        serviceName = "$SYS" if serviceName=="esESS" else serviceName

        key = "{0}{1}".format(serviceName, type)
        if (key not in self._serviceMessageIndex):
           self._serviceMessageIndex[key] = 1
        else:
           self._serviceMessageIndex[key] +=1
        
        if (self._serviceMessageIndex[key] > int(self.config["Common"]["ServiceMessageCount"]) + 1):
           self._serviceMessageIndex[key] = 1

        if (type == Globals.ServiceMessageType.Operational):
            i(self, "ServiceMessage: {0}".format(message))

        self.publishMainMqtt("{tag}/{service}/ServiceMessages/{type}/Message{id:02d}".format(tag=Globals.esEssTag, service=serviceName, type=type, id=self._serviceMessageIndex[key]), "{0} | {1}".format(Globals.getUserTime(), message) , 0, True, True)
        nextOne = self._serviceMessageIndex[key] +1
        if (nextOne > int(self.config["Common"]["ServiceMessageCount"]) + 1):
            nextOne = 1
        
        #self.publishMainMqtt("{tag}/{service}ServiceMessages/{type}/Message{id:02d}".format(tag=Globals.esEssTag, service=serviceName, type=type, id=nextOne), "{0} | {1}".format(Globals.getUserTime(), "-------------------------") , 0, True, True)

    def handleSigterm(self, signum, frame):
        self.publishServiceMessage(self, "SIGTERM received. Shuting down services gracefully.")

        #set flag, so dbus handler stops forwarding new messages, threads are no longer started, etc.
        self._sigTermInvoked=True

        #restore default grid set point
        i(self, "Restoring default power set point of {0}W due to SIGTERM received.".format(self._gridSetPointDefault))
        self.publishLocalMqtt("W/{0}/settings/0/Settings/CGwacs/AcPowerSetPoint".format(self.config["Common"]["VRMPortalID"]), "{\"value\": " + str(self._gridSetPointDefault) + "}", 1 ,False)

        #unsubscribe any mqtt sub, so we no longer receive new messages. 
        for sublist in self._mqttSubscriptions.values():
            for sub in sublist:
                d(self, "Unsubscribing from Mqtt-Subscriptions for Service {0} on {1} with callback: {2}".format(sub.requestingService.__class__.__name__, sub.topic, Helper.formatCallback(sub.callback)))
                if (sub.type == MqttSubscriptionType.Main):
                    self.mainMqttClient.unsubscribe(sub.topic)
                elif (sub.type == MqttSubscriptionType.Local):
                    self.localMqttClient.unsubscribe(sub.topic)
        
        #dbusmonitor has no disconnect method, so we just stop forwarding the messages in the global handler. 

        #tell each service to clean up as well.
        for service in self._services.values():
           try:
               service.handleSigterm()
           except Exception as ex:
               c(self, "Exception during handleSigTerm on service {0}".format(service.__class__.__name__), exc_info=ex)
           i(self, "Service {0} is in safe exit state.".format(service.__class__.__name__))

        #finally, clean up internally.
        #disconnect from mqtts
        self.mainMqttClient.reconnect = False
        self.localMqttClient.reconnect = False
        self.mainMqttClient.disconnect()
        self.localMqttClient.disconnect()   

        i(self, "Cleaned up. Bye.")
        sys.exit(0)       

def configureLogging(config):

  logDir = "/data/log/es-ESS"
  
  if not os.path.exists(logDir):
    os.mkdir(logDir)

  logLevelTrace = 9
  logLevelApp = 11

  def trace(msg, **kwargs):
     if logging.getLogger().isEnabledFor(logLevelTrace):
        logging.log(logLevelTrace, msg, **kwargs)

  def appDebug(msg, **kwargs):
     if logging.getLogger().isEnabledFor(logLevelApp):
        logging.log(logLevelApp, msg, **kwargs)
  
  logging.addLevelName(logLevelTrace, "TRACE")
  logging.addLevelName(logLevelApp, "APP_DEBUG")

  logging.appDebug = appDebug
  logging.Logger.appDebug = appDebug

  logging.trace = trace
  logging.Logger.trace = trace

  logLevelString = config["Common"]['LogLevel']
  logLevel = logging.getLevelName(logLevelString)

  logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)s %(message)s',
                      datefmt='%Y-%m-%d %H:%M:%S',
                      level=logLevel,
                      handlers=[
                        TimedRotatingFileHandler(logDir + "/current.log", when="midnight", interval=1, backupCount=14),
                        logging.StreamHandler()
                      ])
  

  import Helper
  #persist some log flags.
  

def main(config):
  
  try:
      # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
      from dbus.mainloop.glib import DBusGMainLoop # type: ignore
      DBusGMainLoop(set_as_default=True)

      i("Main", "-----------------------------------------------------------------------------------------")
      i("Main", "-----------------------------------------------------------------------------------------")
      i("Main", "-----------------------------------------------------------------------------------------")
           
      Globals.esESS = esESS()
      for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, Globals.esESS.handleSigterm)

      Globals.esESS.initialize()
      
      mainloop = gobject.MainLoop()
      mainloop.run()            
  except Exception as e:
    c("Main", "Exception", exc_info=e)

    sys.exit(0)    

if __name__ == "__main__":
  # read configuration. TODO: Migrate to UI-Based configuration later.
  config = configparser.ConfigParser()
  config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
  
  configureLogging(config)

  try:
    main(config)
  except Exception as uncoughtException:
     c("UNCOUGHT", "Uncought exception, main() dieded.", exc_info=uncoughtException)
