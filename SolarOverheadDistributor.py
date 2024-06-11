from builtins import int
import configparser
import datetime
import logging
import operator
import os
import platform
import re
import sys
import threading
import time
import requests  # type: ignore
if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore

# esEss imports
import Globals
from Globals import getFromGlobalStoreValue
import Helper
from Helper import i, c, d, w, e, dbusConnection
from esESSService import esESSService

class SolarOverheadDistributor(esESSService):
   def __init__(self):
      esESSService.__init__(self)
      self.vrmInstanceID = int(self.config['SolarOverheadDistributor']['VRMInstanceID'])
      self.vrmInstanceIDBMS = int(self.config['SolarOverheadDistributor']['VRMInstanceID_ReservationMonitor'])
      self.serviceType = "com.victronenergy.settings"
      self.serviceName = self.serviceType + ".es-ESS.SolarOverheadDistributor_" + str(self.vrmInstanceID)
      self.bmsServiceType = "com.victronenergy.battery"
      self.bmsServiceName = self.bmsServiceType + ".es-ESS.SolarOverheadConsumer_" + str(self.vrmInstanceIDBMS)
      self.lastUpdate = 0
      self._knownSolarOverheadConsumers = { }
      self._knownSolarOverheadConsumersLock = threading.Lock()

   def initDbusService(self):
      self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
      self.dbusBmsService = VeDbusService(self.bmsServiceName, bus=dbusConnection())

      #create management paths
      self.dbusService.add_path('/Mgmt/ProcessName', __file__)
      self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
      self.dbusService.add_path('/Mgmt/Connection', "dbus")
      self.dbusBmsService.add_path('/Mgmt/ProcessName', __file__)
      self.dbusBmsService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
      self.dbusBmsService.add_path('/Mgmt/Connection', "dbus")
    
      # Create mandatory paths
      self.dbusService.add_path('/DeviceInstance', self.vrmInstanceID)
      self.dbusService.add_path('/ProductId', 65535)
      self.dbusService.add_path('/ProductName', "es-ESS SolarOverheadDistributorService") 
      self.dbusService.add_path('/CustomName', "es-ESS SolarOverheadDistributorService") 
      self.dbusService.add_path('/Latency', None)    
      self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
      self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
      self.dbusService.add_path('/Connected', 1)
      self.dbusService.add_path('/Serial', "1337")
      self.dbusService.add_path('/LastUpdateTime', 0)
      self.dbusService.add_path('/LastUpdateDateTime', 0)
      self.dbusBmsService.add_path('/DeviceInstance', self.vrmInstanceIDBMS)
      self.dbusBmsService.add_path('/ProductId', 65535)
      self.dbusBmsService.add_path('/ProductName', "es-ESS SolarOverheadConsumer") 
      self.dbusBmsService.add_path('/CustomName', "Battery Charge Reservation") 
      self.dbusBmsService.add_path('/Latency', None)    
      self.dbusBmsService.add_path('/FirmwareVersion', Globals.currentVersionString)
      self.dbusBmsService.add_path('/HardwareVersion', Globals.currentVersionString)
      self.dbusBmsService.add_path('/Connected', 1)
      self.dbusBmsService.add_path('/Serial', "1337")
    
      self.dbusBmsService.add_path('/Dc/0/Voltage', 0)
      self.dbusBmsService.add_path('/Dc/0/Power', 0)
      self.dbusBmsService.add_path('/Dc/0/Current', 0)
      self.dbusBmsService.add_path('/Soc', 0)

      # Create custom paths
      self.dbusService.add_path('/Calculations/Grid/L1/Power', 0)
      self.dbusService.add_path('/Calculations/Grid/L2/Power', 0)
      self.dbusService.add_path('/Calculations/Grid/L3/Power', 0)
      self.dbusService.add_path('/Calculations/Grid/TotalFeedIn', 0)
      self.dbusService.add_path('/Calculations/Battery/Power', 0)
      self.dbusService.add_path('/Calculations/Battery/Soc', 0)
      self.dbusService.add_path('/Calculations/Battery/Reservation', 0)
      self.dbusService.add_path('/Calculations/OverheadAvailable', 0)
      self.dbusService.add_path('/Calculations/OverheadAssigned', 0)
      self.dbusService.add_path('/Calculations/OverheadRemaining', 0)
    
   def initDbusSubscriptions(self):
      self.gridL1Dbus      = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Grid/L1/Power")
      self.gridL2Dbus      = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Grid/L2/Power")
      self.gridL3Dbus      = self.registerDbusSubscription("com.victronenergy.system", "/Ac/Grid/L3/Power")
      self.batteryPower    = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Power")
      self.batterySoc      = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Soc")
     
   def initMqttSubscriptions(self):
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IsAutomatic', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Consumption', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/CustomName', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IgnoreBatReservation', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/OnKeywordRegex', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Minimum', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/OnUrl', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/OffUrl', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Priority', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IsNPC', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/StatusUrl', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/StepSize', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Request', self.mqttMessageReceived)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/VRMInstanceID', self.mqttMessageReceived)

   def initWorkerThreads(self):
      self.registerWorkerThread(self.updateDistribution, 20000)
      self.registerWorkerThread(self.dumpReservationBms, 2000)
   
   def initFinalize(self):
      #Service is operable already. Need to parse NPC consumer and throw them over to mqtt-based processing. 
   
      for s in self.config.sections():
         if (s.startswith("NPC:")):
            i(self, "Found NPC SolarOverheadConsumer: " + s)
            try:
               #Consumer found. Create Request.
               consumerKey = s.replace("NPC:", "")
               self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/IsNPC".format(Globals.esEssTag, consumerKey), "true",1)
               self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/IsAutomatic".format(Globals.esEssTag, consumerKey), "true",1)

               for (k, v) in self.config.items(s):
                  if (k != "StepSize"):
                     self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/{2}".format(Globals.esEssTag, consumerKey,k), v, 1)

                  #NPC Consumers always have StepSize = request.
                  if (k == "Request"):
                     self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/StepSize".format(Globals.esEssTag, consumerKey), v,1)

            except Exception as ex:
               c(self, "Error parsing NPC-Consumer: " + s + ". Please validate outline requirements.")

   def mqttMessageReceived(self, sub, topic, msg):
      try:
         consumerKeyMo = re.search('es\-ESS/SolarOverheadDistributor/Requests/([^/]+)/', topic)
         if (consumerKeyMo is not None):
            consumerKey = consumerKeyMo.group(1)
            if (not consumerKey in self._knownSolarOverheadConsumers):
               i(self, "New SolarOverhead-Consumer registered: " + consumerKey + ". Creating respective services.")
               with self._knownSolarOverheadConsumersLock:
                  self._knownSolarOverheadConsumers[consumerKey] = SolarOverheadConsumer(consumerKey)

            self._knownSolarOverheadConsumers[consumerKey].setValue(topic, msg)

      except Exception as e:
         c(self, "Exception", exc_info=e)

   def dumpConsumerBms(self):
      try:
         with self._knownSolarOverheadConsumersLock:
            for consumerKey in self._knownSolarOverheadConsumers:
               consumer = self._knownSolarOverheadConsumers[consumerKey]
                  
               if (not consumer.isInitialized):
                  consumer.checkFinalInit(self)

               if (consumer.isInitialized):
                  consumer.dumpFakeBMS()

      except Exception as e:
          e(self, "Error", exc_info = e)

      return True
   
   def dumpReservationBms(self):
      #dump main bms information as well. 
      self.dbusBmsService["/Dc/0/Power"] = 0
      self.dbusBmsService["/CustomName"] = "Battery Charge Reservation: " + str(self.dbusService["/Calculations/Battery/Reservation"]) + "W"

      if (self.dbusService["/Calculations/Battery/Reservation"] > 0 and self.dbusService["/Calculations/Battery/Power"] > 0):
         self.dbusBmsService["/Soc"] = self.dbusService["/Calculations/Battery/Power"] / self.dbusService["/Calculations/Battery/Reservation"] * 100.0
      else:
         self.dbusBmsService["/Soc"] = 0

   def updateDistribution(self):   
    try:
       d(self, "Updating Solar-Overhead distribution")

       with self._knownSolarOverheadConsumersLock:
         # first, check if we have new Overhead consumers to initialize.
         for consumerKey in self._knownSolarOverheadConsumers:
            d(self, "pre-checks on consumer {0}".format(consumerKey))
            consumer = self._knownSolarOverheadConsumers[consumerKey]
            
            if (not consumer.isInitialized):
               consumer.checkFinalInit(self)

               #now initialzed?
               if (consumer.isInitialized):
                  consumer.dumpFakeBMS()

         #query values we need to determine the overhead
         l1Power = self.gridL1Dbus.value
         l2Power = self.gridL2Dbus.value
         l3Power = self.gridL3Dbus.value
         feedIn = min(l1Power + l2Power + l3Power, 0) * -1
         batPower = self.batteryPower.value
         batSoc = self.batterySoc.value
         assignedConsumption = 0

         #TODO: Refactor how publishing works?!
         self.Publish("/Calculations/Grid/L1/Power", l1Power)
         self.Publish("/Calculations/Grid/L2/Power", l2Power)
         self.Publish("/Calculations/Grid/L3/Power", l3Power)
         self.Publish("/Calculations/Grid/TotalFeedIn", feedIn)

         i(self, "L1/L2/L3/Bat/Soc/Feedin is " + str(l1Power) + "/" + str(l2Power) + "/" + str(l3Power) + "/" + str(batPower) + "/" + str(batSoc) + "/" + str(feedIn))

         overheadDistribution = {}
         for consumerKey in self._knownSolarOverheadConsumers:
            consumer = self._knownSolarOverheadConsumers[consumerKey]

            if (consumer.isInitialized and consumer.isAutomatic):
               overheadDistribution[consumerKey] = 0 #initialize with 0
               d(self,"Already Assigned consumption on " + consumer.consumerKey + " (" + str(consumer.vrmInstanceID) +"): " + str(consumer.consumption))
               assignedConsumption += consumer.consumption

            elif (not consumer.isInitialized):
               w(self, "Consumer {0} is not yet initialized.".format(consumerKey))

            elif (not consumer.isAutomatic):
               i(self, "Consumer {0} is not in automatic mode.".format(consumerKey))

         minBatCharge = 0    
         try:
            equation = self.config["SolarOverheadDistributor"]["MinBatteryCharge"]
            equation = equation.replace("SOC", str(batSoc))
            minBatCharge = round(eval(equation))
         except Exception as ex:
            e(self, "Error evaluation MinBatteryCharge-Equation. Using MinBatteryCharge=0.")

         overhead = max(0, feedIn + assignedConsumption + batPower)
         self.Publish("/Calculations/OverheadAvailable",  overhead)
         i("SolarOverheadDistributor","Available Overhead: " + str(overhead) + "W + ("+str(minBatCharge)+"W BatteryReservation, tho.)")

         overheadAssigned = 0

         self.Publish("/Calculations/Battery/Power", batPower)
         self.Publish("/Calculations/Battery/Soc", batSoc)
         self.Publish("/Calculations/Battery/Reservation" ,minBatCharge)

         #Iterate through device requests, and see, how much we can assign. If the overhead available
         #does not change within one iteration, we are done with assigning all available energy. 
         #Either all consumers then are running at maximum, or the remaining overhead doesn't satisfy the
         #need of additional consumers. In that case, the remaining overhead will be consumed by the house battery.
         if (self.config["SolarOverheadDistributor"]["Strategy"] == "RoundRobin"):
            overheadDistribution = self.doRoundRobin(overhead, overheadDistribution, minBatCharge) 
         if (self.config["SolarOverheadDistributor"]["Strategy"] == "TryFullfill"):
            overheadDistribution = self.doTryFullfill(overhead, overheadDistribution, minBatCharge) 

         for consumerKey in self._knownSolarOverheadConsumers:
            consumer = self._knownSolarOverheadConsumers[consumerKey]
            
            if (consumer.isInitialized and consumer.isAutomatic):
               consumer.allowance = overheadDistribution[consumerKey]
               consumer.reportAllowance()
         
         i(self, "New Overhead assigned: " + str(overheadAssigned) + "W")
         self.Publish("/Calculations/OverheadAssigned", overheadAssigned)
         self.Publish("/Calculations/OverheadRemaining", overhead)
         
         #update lastupdate vars
         self.lastUpdate = time.time()   
         self.Publish('/LastUpdateTime', self.lastUpdate)   
         self.Publish('/LastUpdateDateTime', str(datetime.datetime.now()))     
         d(self, "Updating PV-Overhead distribution -> done") 
    except Exception as e:
       c(self, "Exception", exc_info=e)
       
    return True
 
   def doTryFullfill(self, overhead, overheadDistribution, minBatCharge):
      overheadAssigned = 0
     
      for consumerDupe in sorted(self._knownSolarOverheadConsumers.values(), key=operator.attrgetter('priority')): 
         while (True):
            consumerKey = consumerDupe.consumerKey
            overheadBefore = overhead
            consumer = self._knownSolarOverheadConsumers[consumerKey]

            #check, if this consumer is currently allowed to consume. 
            canConsume = 0
            canConsumeReason = "None"

            if (consumer.isInitialized):
               if (consumer.isAutomatic):
                  if (overheadDistribution[consumerKey] > 0 or consumer.minimum == 0):
                     #already consuming minimum or has no minimum.
                     if (consumer.stepSize < (overhead - minBatCharge) and overheadDistribution[consumerKey] < consumer.request):
                        #fits into available overhead
                        canConsume = consumer.stepSize
                        canConsumeReason = "Overhead greater than Stepsize and obey BatChargeReservation"
                     elif (overheadDistribution[consumerKey] >= consumer.request):
                        #cannot consume!
                        canConsume = 0
                        canConsumeReason = "Maximum request assigned."
                     elif (consumer.ignoreBatReservation and overhead > consumer.stepSize and overheadDistribution[consumerKey] < consumer.request):
                        #fits into available overhead
                        canConsume = consumer.stepSize
                        canConsumeReason = "Overhead greater than Stepsize and ignore BatChargeReservation"
                     else:
                        #cannot consume!
                        canConsume = 0
                        canConsumeReason = "Stepsize greater than Overhead."
                  else:
                     #consumer requires minimum and is not yet consuming.
                     if (consumer.minimum < (overhead - minBatCharge) and overheadDistribution[consumerKey] < consumer.request):
                        #fits into available overhead
                        canConsume = consumer.minimum
                        canConsumeReason = "Overhead greater than Minimum and obey BatChargeReservation"
                     elif (overheadDistribution[consumerKey] >= consumer.request):
                        #cannot consume!
                        canConsume = 0
                        canConsumeReason = "Maximum request assigned."
                     elif (consumer.ignoreBatReservation and overhead > consumer.stepSize and overheadDistribution[consumerKey] < consumer.request):
                        #fits into available overhead
                        canConsume = consumer.minimum
                        canConsumeReason = "Overhead greater than Minimum and ignore BatChargeReservation"
                     else:
                        #cannot consume!
                        canConsume = 0
                        canConsumeReason = "Minimum greater than Overhead."

                  d("SolarOverheadDistributor", "Assigning " + str(canConsume) + "W to " + consumerKey + " (" + str(consumer.priority) + ") because: " + canConsumeReason) 
                  overheadDistribution[consumerKey] += canConsume
                  overhead -= canConsume
                  overheadAssigned += canConsume
                  
            if (overheadBefore == overhead):
               break

      return overheadDistribution
  
   def doRoundRobin(self, overhead, overheadDistribution, minBatCharge):
     overheadAssigned = 0
     while (True):
      overheadBefore = overhead

      for consumerDupe in sorted(self._knownSolarOverheadConsumers.values(), key=operator.attrgetter('priority')):   
         consumerKey = consumerDupe.consumerKey        
         consumer = self._knownSolarOverheadConsumers[consumerKey]

         #check, if this consumer is currently allowed to consume. 
         canConsume = 0
         canConsumeReason = "None"

         if (consumer.isInitialized):
            if (consumer.isAutomatic):
               if (overheadDistribution[consumerKey] > 0 or consumer.minimum == 0):
                  #already consuming minimum or has no minimum.
                  if (consumer.stepSize < (overhead - minBatCharge) and overheadDistribution[consumerKey] < consumer.request):
                     #fits into available overhead
                     canConsume = consumer.stepSize
                     canConsumeReason = "Overhead greater than Stepsize and obey BatChargeReservation"
                  elif (overheadDistribution[consumerKey] >= consumer.request):
                     #cannot consume!
                     canConsume = 0
                     canConsumeReason = "Maximum request assigned."
                  elif (consumer.ignoreBatReservation and overhead > consumer.stepSize and overheadDistribution[consumerKey] < consumer.request):
                     #fits into available overhead
                     canConsume = consumer.stepSize
                     canConsumeReason = "Overhead greater than Stepsize and ignore BatChargeReservation"
                  else:
                     #cannot consume!
                     canConsume = 0
                     canConsumeReason = "Stepsize greater than Overhead."
               else:
                  #consumer requires minimum and is not yet consuming.
                  if (consumer.minimum < (overhead - minBatCharge) and overheadDistribution[consumerKey] < consumer.request):
                     #fits into available overhead
                     canConsume = consumer.minimum
                     canConsumeReason = "Overhead greater than Minimum and obey BatChargeReservation"
                  elif (overheadDistribution[consumerKey] >= consumer.request):
                     #cannot consume!
                     canConsume = 0
                     canConsumeReason = "Maximum request assigned."
                  elif (consumer.ignoreBatReservation and overhead > consumer.stepSize and overheadDistribution[consumerKey] < consumer.request):
                     #fits into available overhead
                     canConsume = consumer.minimum
                     canConsumeReason = "Overhead greater than Minimum and ignore BatChargeReservation"
                  else:
                     #cannot consume!
                     canConsume = 0
                     canConsumeReason = "Minimum greater than Overhead."

               d("SolarOverheadDistributor", "Assigning " + str(canConsume) + "W to " + consumerKey + " (" + str(consumer.priority) + ") because: " + canConsumeReason) 
               overheadDistribution[consumerKey] += canConsume
               overhead -= canConsume
               overheadAssigned += canConsume
                  
      if (overheadBefore == overhead):
         break

      return overheadDistribution

   def _handlechangedvalue(self, path, value):
     logging.critical("Someone else updated %s to %s" % (path, value))
     return True # accept the change
  
   def Publish(self, path, value):
      try:
         self.dbusService[path] = value
         self.publishMainMqtt("es-ESS/SolarOverheadDistributor{0}".format(path), value, 1)
      except Exception as e:
       c(self, "Exception", exc_info=e)

class SolarOverheadConsumer:
  def __init__(self, consumerKey):
     #wait until we have gathered ALL required values.
     #then, the device can be initialized finally.
     self.vrmInstanceID = None
     self.isInitialized = False
     self.dbusService = None
     self.customName = None
     self.minimum = 0
     self.request = 0
     self.stepSize = 0
     self.consumption = 0
     self.priority = 100
     self.allowance = 0
     self.isAutomatic = False
     self.consumerKey = consumerKey
     self.isNPC = False
     self.npcState = False
     self.ignoreBatReservation = False
     self.onUrl = None
     self.offUrl = None
     self.statusUrl = None
     self.onKeywordRegex = None
     
     i(self, "SolarOverheadConsumer created: " + consumerKey + ". Waiting for required values to arrive...")

  def setValue(self, key, value):
     key = key.replace('{0}/SolarOverheadDistributor/Requests/{1}/'.format(Globals.esEssTag, self.consumerKey), "")
     
     d(self, "Setting value '{0}' to '{1}'".format(key, value))

     if (key == "Minimum"):
        self.minimum = float(value)
     elif (key == "Request"):
        self.request = float(value)
     elif (key == "StepSize"):
        self.stepSize = float(value)
     elif (key == "Consumption"):
        self.consumption = float(value)
     elif (key == "IsAutomatic"):
        self.isAutomatic = value.lower() == "true"
     elif (key == "VRMInstanceID"):
        self.vrmInstanceID = int(value)
     elif (key == "Priority"):
        if (value == ""):
          self.priority = 100
        else:
          self.priority = int(value)
     elif (key == "IgnoreBatReservation"):
        self.ignoreBatReservation = value.lower() == "true"
     elif (key == "Allowance"):
        self.allowance = float(value)
     elif (key == "CustomName"):
        self.customName = value
     elif (key == "IsNPC"):
        self.isNPC = value.lower() == "true"
     elif (key == "OnUrl"):
        self.onUrl = value
     elif (key == "OffUrl"):
        self.offUrl = value
     elif (key == "StatusUrl"):
        self.statusUrl = value
     elif (key == "OnKeywordRegex"):
        self.onKeywordRegex = value
    
  def checkFinalInit(self, pods):
     #to create the final instance on DBUS, we need the VRMId at least.
     if (self.vrmInstanceID is not None):
        self.initialize()
     else:
        w(self, "Initialization of consumer {0} not yet possible, VRMInstanceID is missing.".format(self.consumerKey))

  def initialize(self):
     self.serviceType = "com.victronenergy.battery"
     self.serviceName = self.serviceType + ".es-ESS.SolarOverheadConsumer_" + str(self.vrmInstanceID)
     self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
     
     #Mgmt-Infos
     self.dbusService.add_path('/DeviceInstance', self.vrmInstanceID)
     self.dbusService.add_path('/Mgmt/ProcessName', __file__)
     self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
     self.dbusService.add_path('/Mgmt/Connection', "Local DBus Injection")

     # Create the mandatory objects
     self.dbusService.add_path('/ProductId', 65535)
     self.dbusService.add_path('/ProductName', "{0} SolarOverheadConsumer".format(Globals.esEssTag)) 
     self.dbusService.add_path('/CustomName', self.customName) 
     self.dbusService.add_path('/Latency', None)    
     self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
     self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
     self.dbusService.add_path('/Connected', 1)
     self.dbusService.add_path('/Serial', "1337")
     
     self.dbusService.add_path('/Dc/0/Voltage', 0)
     self.dbusService.add_path('/Dc/0/Power', 0)
     self.dbusService.add_path('/Dc/0/Current', 0)
     self.dbusService.add_path('/Soc', 0)
     
     i(self,"Initialization of consumer {0} completed.".format(self.consumerKey))
     self.isInitialized = True

  def dumpFakeBMS(self):
     try:
         self.dbusService["/Dc/0/Power"] = self.consumption

         customName = "Solar Overhead Consumer"
         if (self.customName is not None):
               customName = self.customName

         if (self.isAutomatic):
            customName += " ☼"
         else:
            customName += " ◌"
            
         
         if (self.request is not None and self.isAutomatic):
            customName += " @ {0}W".format(self.request)

         self.dbusService["/CustomName"] = customName
         
         if (self.request > 0):
            self.dbusService["/Soc"] = self.consumption / self.request * 100.0
         else:
            self.dbusService["/Soc"] = 0
     except Exception as ex:
         e(self, "Exception", exc_info=ex)

  def reportAllowance(self):
     self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Allowance".format(Globals.esEssTag, self.consumerKey), self.allowance, 1)
     d(self, "Consumer {0} reporting allowance of {1}W".format(self.consumerKey, self.allowance))

     if (self.isNPC):
        self.npcControl()
        self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Consumption".format(Globals.esEssTag, self.consumerKey), self.consumption, 1)

  def npcControl(self):
      try:
         #invoke npc control! 
         if (self.allowance >= self.request and not self.npcState):
            #turn on!
            d(self, "Turn on NPC-consumer required, calling: " + self.onUrl)
            requests.get(url=self.onUrl)
            self.validateNpcStatus(True)
         elif (self.allowance == 0 and self.npcState):
            #turn off!
            requests.get(url=self.offUrl)
            d(self, "Turn off NPC-consumer required, calling: " + self.offUrl)
            self.validateNpcStatus(False)
      except Exception as ex:
         c(self, "Exception", exc_info=ex)

  def validateNpcStatus(self, should):
      try:
         d(self, "Validating NPC-Consumer state through: " + self.statusUrl + " against: " + str(self.onKeywordRegex))
         status = requests.get(url=self.statusUrl)
         isMatch = re.search(str(self.onKeywordRegex), status.text) is not None
         d(self, "Status is: " + str(isMatch) + " and should be: " + str(should) + ". input text length was " + str(len(status.text)))
         if (isMatch == should):
            self.npcState = isMatch

            if (isMatch):
               self.consumption = self.request
            else:
              self.consumption = 0
      except Exception as ex:
       c(self, "Exception", exc_info=ex)