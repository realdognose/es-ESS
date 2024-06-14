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
import time

# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore

# esEss imports
import Globals
from Helper import i, c, d, w, e, t, dbusConnection
from esESSService import esESSService

class SolarOverheadDistributor(esESSService):
   def __init__(self):
      esESSService.__init__(self)
      self.vrmInstanceID = int(self.config['SolarOverheadDistributor']['VRMInstanceID'])
      self.vrmInstanceIDBMS = int(self.config['SolarOverheadDistributor']['VRMInstanceID_ReservationMonitor'])
      self.serviceType = "com.victronenergy.settings"
      self.serviceName = self.serviceType + ".esESS.SolarOverheadDistributor_" + str(self.vrmInstanceID)
      self.bmsServiceType = "com.victronenergy.battery"
      self.bmsServiceName = self.bmsServiceType + ".esESS.SolarOverheadBatteryReservation_" + str(self.vrmInstanceIDBMS)
      self.lastUpdate = 0
      self._knownSolarOverheadConsumers: dict[str, SolarOverheadConsumer] = { }
      self._knownSolarOverheadConsumersLock = threading.Lock()

      #TODO: We need a schedule to transfer todays energy to yesterday.

   def initDbusService(self):
      self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
      self.dbusBmsService = VeDbusService(self.bmsServiceName, bus=dbusConnection())

      d(self, "Registering as {0} on dbus.".format(self.serviceName))
      d(self, "Registering as {0} on dbus.".format(self.bmsServiceName))

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
      self.dbusService.add_path('/ProductName', "esESS SolarOverheadDistributorService") 
      self.dbusService.add_path('/CustomName', "esESS SolarOverheadDistributorService") 
      self.dbusService.add_path('/Latency', None)    
      self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
      self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
      self.dbusService.add_path('/Connected', 1)
      self.dbusService.add_path('/Serial', "1337")
      self.dbusService.add_path('/LastUpdateTime', 0)
      self.dbusService.add_path('/LastUpdateDateTime', 0)
      self.dbusBmsService.add_path('/DeviceInstance', self.vrmInstanceIDBMS)
      self.dbusBmsService.add_path('/ProductId', 65535)
      self.dbusBmsService.add_path('/ProductName', "esESS SolarOverheadDistributorBMS") 
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
      self.gridL1Dbus      = self.registerDbusSubscription("com.victronenergy.grid", "/Ac/L1/Power")
      self.gridL2Dbus      = self.registerDbusSubscription("com.victronenergy.grid", "/Ac/L2/Power")
      self.gridL3Dbus      = self.registerDbusSubscription("com.victronenergy.grid", "/Ac/L3/Power")
      self.batteryPower    = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Power")
      self.batterySoc      = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Soc")
     
   def initMqttSubscriptions(self):
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IsAutomatic', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Consumption', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/CustomName', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IgnoreBatReservation', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/OnKeywordRegex', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Minimum', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/OnUrl', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/OffUrl', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Priority', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IsHttpConsumer', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IsMqttConsumer', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/IsScriptedConsumer', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/StatusUrl', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/StepSize', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/Request', callback=self.onMqttMessage)
      self.registerMqttSubscription('es-ESS/SolarOverheadDistributor/Requests/+/VRMInstanceID', callback=self.onMqttMessage)

   def initWorkerThreads(self):
      self.registerWorkerThread(self.updateDistribution, int(self.config["SolarOverheadDistributor"]["UpdateInterval"]))
      self.registerWorkerThread(self.dumpReservationBms, 2000)
      self.registerWorkerThread(self._validateNpcConsumerStates, 15 * 60 * 1000)
      self.registerWorkerThread(self._persistEnergyStats, 5 * 60 * 1000)
      self.registerWorkerThread(self._moveEnergyData, (86400 - time.time() % 86400) * 1000)

   def initFinalize(self):
      #Service is operable already. Need to parse Http/Mqtt consumer and throw them over to mqtt-based processing. 
   
      for s in self.config.sections():
         if (s.startswith("HttpConsumer:")):
            i(self, "Found HttpConsumer: " + s)
            try:
               #Consumer found. Create Request.
               consumerKey = s.replace("HttpConsumer:", "")
               self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/IsHttpConsumer".format(Globals.esEssTag, consumerKey), "true",1)
               self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/IsAutomatic".format(Globals.esEssTag, consumerKey), "true",1)

               for (k, v) in self.config.items(s):
                  #Http Consumers always have StepSize = request.
                  if (k != "StepSize"):
                     self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/{2}".format(Globals.esEssTag, consumerKey,k), v, 1)

                  if (k == "Request"):
                     self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/StepSize".format(Globals.esEssTag, consumerKey), v,1)

            except Exception as ex:
               e(self, "Error parsing HttpConsumer: {0}. Please validate outlined requirements.".format(consumerKey))

         if (s.startswith("MqttConsumer:")):
            i(self, "Found MqttConsumer: " + s)
            try:
               #Consumer found. Create Request.
               consumerKey = s.replace("MqttConsumer:", "")
               self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/IsMqttConsumer".format(Globals.esEssTag, consumerKey), "true",1)
               self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/IsAutomatic".format(Globals.esEssTag, consumerKey), "true",1)

               for (k, v) in self.config.items(s):
                  if (k != "StepSize"):
                     self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/{2}".format(Globals.esEssTag, consumerKey,k), v, 1)

                  #Mqtt Consumers always have StepSize = request.
                  if (k == "Request"):
                     self.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/StepSize".format(Globals.esEssTag, consumerKey), v,1)

            except Exception as ex:
               e(self, "Error parsing MqttConsumer: {0}. Please validate outlined requirements.".format(consumerKey))
  
   def onMqttMessage(self, client, userdata, msg):
      message = str(msg.payload)[2:-1]

      if (message == ""):
         d(self, "Empty message on topic {0}. Ignoring.".format(msg.topic))
         return
      
      try:
         consumerKeyMo = re.search('es\-ESS/SolarOverheadDistributor/Requests/([^/]+)/', msg.topic)
         if (consumerKeyMo is not None):
            consumerKey = consumerKeyMo.group(1)
            if (not consumerKey in self._knownSolarOverheadConsumers):
               i(self, "New SolarOverhead-Consumer registered: " + consumerKey + ". Creating respective services.")

               with self._knownSolarOverheadConsumersLock:
                  self._knownSolarOverheadConsumers[consumerKey] = SolarOverheadConsumer(consumerKey)

            self._knownSolarOverheadConsumers[consumerKey].setValue(msg.topic, message)

      except Exception as ex:
         c(self, "Exception while receiving message '{0}' on topic '{1}'".format(message, msg.topic), exc_info=ex)

   def _moveEnergyData(self):
       #reschedule in 24h.
       self.registerWorkerThread(self._moveEnergyData, 86400)

       with self._knownSolarOverheadConsumersLock:
         for consumerKey in self._knownSolarOverheadConsumers:
            consumer = self._knownSolarOverheadConsumers[consumerKey]
               
            if (not consumer.isInitialized):
               consumer._moveEnergyData()

       #unschedule current timer.
       return False

   def dumpConsumerBms(self):
      try:
         with self._knownSolarOverheadConsumersLock:
            for consumerKey in self._knownSolarOverheadConsumers:
               consumer = self._knownSolarOverheadConsumers[consumerKey]
                  
               if (not consumer.isInitialized):
                  consumer.checkFinalInit(self)

               if (consumer.isInitialized):
                  consumer.dumpFakeBMS()

      except Exception as ex:
          e(self, "Error", exc_info = ex)

      return True
   
   def _validateNpcConsumerStates(self):
      with self._knownSolarOverheadConsumersLock:
         for consumerKey in self._knownSolarOverheadConsumers:            
            try:
               consumer = self._knownSolarOverheadConsumers[consumerKey]

               if (consumer.isInitialized):
                  
                  if (consumer.isHTTPConsumer):
                     consumer.validateHttpStatus(None)
                     consumer.httpControl()
                  
                  elif (consumer.isMqttConsumer):
                     consumer.mqttControl()

            except Exception as ex:
               e(self, "Error validating consumer {0}".format(consumerKey), exc_info = ex)

      return True

   def _persistEnergyStats(self):
      for consumerKey in self._knownSolarOverheadConsumers:
         consumer = self._knownSolarOverheadConsumers[consumerKey]
   
         if (consumer.isInitialized):
            consumer._persistEnergyStats()
   
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
         except ZeroDivisionError as ex:
            e(self, "Error ZeroDivisionError on MinBatteryCharge-Equation. Using MinBatteryCharge=0.", exc_info=ex)
         except Exception as ex:
            e(self, "Error evaluation MinBatteryCharge-Equation. Using MinBatteryCharge=0.", exc_info=ex)

         overhead = max(0, feedIn + assignedConsumption + batPower)
         self.Publish("/Calculations/OverheadAvailable",  overhead)

         self.publishServiceMessage(self,  "Updating distribution. Available Overhead: {0}W, Battery Reservation: {1}W".format(overhead, minBatCharge))
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
               if (Globals.esESS._sigTermInvoked == True):
                  return
               
               consumer.allowance = overheadDistribution[consumerKey]
               consumer.reportAllowance(self)
               overheadAssigned += consumer.allowance
               overhead -= consumer.allowance
               self.publishServiceMessage(self, "Assigned {0}W to {1} ({2})".format(consumer.allowance, consumer.customName, consumerKey))
            elif (not consumer.isInitialized):
               self.publishServiceMessage(self, "{0} ({1}) is not yet initialized.".format(consumer.customName, consumerKey), Globals.ServiceMessageType.Warning)
            elif (not consumer.isAutomatic):
               self.publishServiceMessage(self, "{0} ({1}) is not in automatic mode.".format(consumer.customName, consumerKey))
         
         i(self, "New Overhead assigned: " + str(overheadAssigned) + "W")
         self.Publish("/Calculations/OverheadAssigned", overheadAssigned)
         self.Publish("/Calculations/OverheadRemaining", overhead)

         self.publishServiceMessage(self,  "Assigned: {0}W; Unassigned: {1}W".format(overheadAssigned, overhead))
         
         #update lastupdate vars
         self.lastUpdate = time.time()   
         self.Publish('/LastUpdateTime', self.lastUpdate)   
         self.Publish('/LastUpdateDateTime', str(datetime.datetime.now()))     
         d(self, "Updating PV-Overhead distribution -> done") 
    except Exception as ex:
       c(self, "Exception", exc_info=ex)
       
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
      except Exception as ex:
       c(self, "Exception", exc_info=ex)
   
   def handleSigterm(self):
       self.publishServiceMessage(self, "SIGTERM received, revoking allowance for every consumer and stopping Http/Mqtt consumers.")
       for (key, consumer) in self._knownSolarOverheadConsumers.items():
          consumer.allowance=0
          consumer.reportAllowance(self)
          consumer._persistEnergyStats()
          
          if (consumer.isHttpConsumer):
             consumer.httpControl()
          elif (consumer.isMqttConsumer):
             consumer.mqttControl()

class SolarOverheadConsumer:
  def __init__(self, consumerKey):
     self.runtimeData = configparser.ConfigParser()
     self.runtimeData.optionxform = str
     self.runtimeData.read("{0}/runtimeData/energy_{1}.ini".format(os.path.dirname(os.path.realpath(__file__)), consumerKey))
     self.energyToday = self._initEnergyTracking("energyToday", 0)
     self.energyYesterday = self._initEnergyTracking("energyYesterday", 0)
     self.energyTotal = self._initEnergyTracking("energyTotal", 0)
     self.runtimeToday = self._initEnergyTracking("runtimeToday", 0)
     self.runtimeYesterday = self._initEnergyTracking("runtimeYesterday", 0)
     self.runtimeTotal = self._initEnergyTracking("runtimeTotal", 0)

     #wait until we have gathered ALL required values.
     #then, the device can be initialized finally.
     self.lastEnergyCheckpoint = time.time()
     self.isInitialized = False
     self.vrmInstanceID = None
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
     self.ignoreBatReservation = False
     self.isScriptedConsumer = None

     #NPC specific values.
     self.npcState = False #accounts for both, Http and Mqtt.
     self.onKeywordRegex = None #accounts for both, Http and Mqtt.
     self.powerExtractRegex = None #accounts for both, Http and Mqtt.

     #Http specific
     self.isHttpConsumer = False
     self.onUrl = None
     self.offUrl = None
     self.powerUrl = None
     self.statusUrl = None

     #Mqtt specific
     self.isMqttConsumer = False
     self.onTopic = None
     self.onTopicValue = None
     self.offTopic = None
     self.offTopicValue = None
     self.powerTopic = None
     self.statusTopic = None
     
     i(self, "SolarOverheadConsumer created: " + consumerKey + ". Waiting for required values to arrive...")

  def _persistEnergyStats(self):
     try:
         d(self, "Persisting runtime data for {0}".format(self.consumerKey))
         
         self.runtimeData.set("Energy","energyToday",str(self.energyToday))
         self.runtimeData.set("Energy","energyYesterday",str(self.energyYesterday))
         self.runtimeData.set("Energy","energyTotal",str(self.energyTotal))
         self.runtimeData.set("Energy","runtimeToday",str(self.runtimeToday))
         self.runtimeData.set("Energy","runtimeYesterday",str(self.runtimeYesterday))
         self.runtimeData.set("Energy","runtimeTotal",str(self.runtimeTotal))

         with open("{0}/runtimeData/energy_{1}.ini".format(os.path.dirname(os.path.realpath(__file__)), self.consumerKey), 'w+') as cfile:
            t(self, "File open for w+: {0}/runtimeData/energy_{1}.ini".format(os.path.dirname(os.path.realpath(__file__)), self.consumerKey))
            self.runtimeData.write(cfile)
            cfile.flush()

     except OSError as ex2:
         e(self, "Exception while trying to persist runtime data: {0}".format(ex2))
     except Exception as ex:
         e(self, "Exception while trying to persist runtime data.", exc_info=ex)

  def _initEnergyTracking(self, key, default):
     if ("Energy" not in self.runtimeData.sections()):
         self.runtimeData.add_section("Energy")
         return default
        
     if (key not in self.runtimeData["Energy"]):
        return default
     
     return float(self.runtimeData["Energy"][key])
     
  def setValue(self, key, value):
     key = key.replace('{0}/SolarOverheadDistributor/Requests/{1}/'.format(Globals.esEssTag, self.consumerKey), "")
     
     t(self, "Setting value '{0}' to '{1}'".format(key, value))

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
     elif (key == "IsHttpConsumer"):
        self.isHttpConsumer = value.lower() == "true"
     elif (key == "IsMqttConsumer"):
        self.isMqttConsumer = value.lower() == "true"
     elif (key == "IsScriptedConsumer"):
        self.isScriptedConsumer = value.lower() == "true"
     elif (key == "OnUrl"):
        self.onUrl = value
     elif (key == "OffUrl"):
        self.offUrl = value
     elif (key == "PowerUrl"):
        self.powerUrl = value
     elif (key == "StatusUrl"):
        self.statusUrl = value
     elif (key == "OnKeywordRegex"):
        self.onKeywordRegex = value

     #TODO: Delta publishing of only changed value.
     self.dumpFakeBMS()
    
  def checkFinalInit(self, sod:SolarOverheadDistributor):
      #to create the final instance on DBUS and finally init everything, we need different sets of variables.
      #all consumers need the vrmInstanceId.
      r = self._checkAttrSet("vrmInstanceID", "VRMInstanceID", sod)
      
      #Values arriving through mqtt may be delayed, so VRMInstanceId may arrive
      #Before the IsHttpConsumer or IsMqttConsumer Flag. Thus, if VRM Id is already
      #present, we have to wait some seconds here, to give more values the chance to arrive. 
      #TODO is this a real world problem? Verify.
      if (self.isHttpConsumer):
         r &= self._checkAttrSet("onUrl", "OnUrl", sod)
         r &= self._checkAttrSet("offUrl", "OffUrl", sod)
         r &= self._checkAttrSet("statusUrl", "StatusUrl", sod)
         r &= self._checkAttrSet("onKeywordRegex", "OnKeywordRegex", sod)

      elif (self.isMqttConsumer):
         r &= self._checkAttrSet("onTopic", "OnTopic", sod)
         r &= self._checkAttrSet("onTopicValue", "OnTopicValue", sod)
         r &= self._checkAttrSet("offTopic", "OffTopic", sod)
         r &= self._checkAttrSet("offTopicValue", "OffTopicValue", sod)
         r &= self._checkAttrSet("statusTopic", "statusTopic", sod)
         r &= self._checkAttrSet("onKeywordRegex", "OnKeywordRegex", sod)
      
      else:
         #choice needs to be confirmed through IsScriptedConsumer.
         r &= self._checkAttrSet("isScriptedConsumer", "IsScriptedConsumer", sod)

      if r:
         self.initialize(sod)
         
  def _checkAttrSet(self, propName, displayName, sod:SolarOverheadDistributor):
     if (getattr(self, propName) is not None):
        return True
     
     sod.publishServiceMessage(sod, "Value required is not set: {0}".format(displayName))
     w(self, "Value required is not set: {0}".format(displayName))

     return False

  def initialize(self, sod:SolarOverheadDistributor):
     self.serviceType = "com.victronenergy.battery"
     self.serviceName = self.serviceType + ".esESS.SolarOverheadConsumer_" + str(self.vrmInstanceID)
     self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
     
     #Mgmt-Infos
     self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
     self.dbusService.add_path('/Mgmt/ProcessName', __file__)
     self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
     self.dbusService.add_path('/Mgmt/Connection', "dbus")

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
     
     type ="ScriptedConsumer"
     if (self.isHttpConsumer):
       type = "HttpConsumer"
     if (self.isMqttConsumer):
       type = "MqttConsumer"
     
     sod.publishServiceMessage(sod, "Consumer {0} ({1}) initialized as: {2}".format(self.customName, self.consumerKey, type))
     self.isInitialized = True

     if (self.isHttpConsumer):
         self.validateHttpStatus(None)

     if (self.isMqttConsumer):
         self.validateMqttStatus(None)

  def dumpFakeBMS(self):
     try:
         if (self.dbusService is None):
            return
         
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

  def reportAllowance(self, sod):
     sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Allowance".format(Globals.esEssTag, self.consumerKey), self.allowance, 1)
     
     #calculate current consumption, before dumping new/changed allowance.
     self.calculateEnergy(sod)

     d(self, "Consumer {0} reporting allowance of {1}W".format(self.consumerKey, self.allowance))

     if (self.isHttpConsumer):
        self.httpControl()
        sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Consumption".format(Globals.esEssTag, self.consumerKey), self.consumption, 1)
     
     if (self.isMqttConsumer):
        self.mqttControl()
        sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Consumption".format(Globals.esEssTag, self.consumerKey), self.consumption, 1)
      
     #report Energy values.
     sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Energy/runtimeToday".format(Globals.esEssTag, self.consumerKey), self.runtimeToday, 1, True)
     sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Energy/runtimeYesterday".format(Globals.esEssTag, self.consumerKey), self.runtimeYesterday, 1, True)
     sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Energy/runtimeTotal".format(Globals.esEssTag, self.consumerKey), self.runtimeTotal, 1, True)
     sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Energy/energyToday".format(Globals.esEssTag, self.consumerKey), self.energyTotal, 1, True)
     sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Energy/energyYesterday".format(Globals.esEssTag, self.consumerKey), self.energyYesterday, 1, True)
     sod.publishMainMqtt("{0}/SolarOverheadDistributor/Requests/{1}/Energy/energyTotal".format(Globals.esEssTag, self.consumerKey), self.energyTotal, 1, True)  

  def httpControl(self):
      try:
         #invoke http control! 
         if (self.allowance >= self.request and not self.npcState):
            #turn on!
            d(self, "Turn on HttpConsumer required, calling: " + self.onUrl)
            requests.get(url=self.onUrl)
            self.validateHttpStatus(True)
         elif (self.allowance == 0 and self.npcState):
            #turn off!
            requests.get(url=self.offUrl)
            d(self, "Turn off HttpConsumer required, calling: " + self.offUrl)
            self.validateHttpStatus(False)
      except Exception as ex:
         c(self, "Exception", exc_info=ex)

  def mqttControl(self):
      #TODO: Implement
      pass

  def validateHttpStatus(self, should):
      try:
         d(self, "Validating HttpConsumer {0} state through: {1} against: {2}".format(self.consumerKey, self.statusUrl,self.onKeywordRegex))
         status = requests.get(url=self.statusUrl)
         isMatch = re.search(str(self.onKeywordRegex), status.text) is not None
         self.validateNpcStatus(isMatch, should)

      except Exception as ex:
       c(self, "Exception", exc_info=ex)

  def validateNpcStatus(self, isValue, shouldValue):
     d(self, "Status is: {0} and should be: {1}.".format(isValue, shouldValue))
         
     self.npcState = isValue

     if (isValue):
         self.consumption = self.fetchNpcPower()
     else:
         self.consumption = 0

  def fetchNpcPower(self):
      if (self.isHttpConsumer and self.powerUrl is not None and self.powerExtractRegex is not None):
         #TODO: fetch power
         pass

      if (self.isMqttConsumer and self.powerTopic is not None and self.powerExtractRegex is not None):
         #mqtt values should have been arrived and be parsed already.
         return self.consumption
      
      #else ammend request=consumption
      d(self, "NPC {0} has no power metering, assuming request=consumption.".format(self.consumerKey))
      return self.request

  def calculateEnergy(self, sod):
     duration = time.time() - self.lastEnergyCheckpoint
     self.lastEnergyCheckpoint = time.time()

     if (self.consumption > 0):
        self.runtimeToday += duration
        self.energyToday += duration / 3600.0 * self.consumption
        self.runtimeTotal += duration
        self.energyTotal += duration / 3600.0 * self.consumption

  def _moveEnergyData(self):
     self.runtimeYesterday = self.runtimeToday
     self.energyYesterday = self.energyToday

     self.energyToday = 0
     self.runtimeToday = 0

     self._persistEnergyStats()
     
   
  