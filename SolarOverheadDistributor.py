from builtins import int
import configparser
import datetime
import logging
import operator
import os
import platform
import re
import sys
import time
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
from SolarOverheadConsumer import SolarOverheadConsumer

class SolarOverheadDistributor:
  def __init__(self):
    self.config = Globals.getConfig()
    self.futureUpdate = None
    self.futureUpdateValues = None
    
    #register the root service. device specific service will be registered as they are 
    #discovered during runtime.
    self.vrmInstanceID = int(self.config['SolarOverheadDistributor']['VRMInstanceID'])
    self.vrmInstanceIDBMS = int(self.config['SolarOverheadDistributor']['VRMInstanceID_ReservationMonitor'])
    self.serviceType = "com.victronenergy.settings"
    self.serviceName = self.serviceType + ".es-ESS.SolarOverheadDistributor_" + str(self.vrmInstanceID)
    i("SolarOverheadDistributor","Registering service as: " + self.serviceName)
    self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())

    #dump root information about our service and register paths.
    self.dbusService.add_path('/Mgmt/ProcessName', __file__)
    self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
    self.dbusService.add_path('/Mgmt/Connection', "Local DBus Injection")

    # Create the mandatory objects
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

    #Create a Fake-BMS to outline batteryChargeLimit, if active.
    self.bmsServiceType = "com.victronenergy.battery"
    self.bmsServiceName = self.bmsServiceType + ".es-ESS.SolarOverheadConsumer_" + str(self.vrmInstanceIDBMS)
    self.dbusBmsService = VeDbusService(self.bmsServiceName, bus=dbusConnection())
    
    #Mgmt-Infos
    self.dbusBmsService.add_path('/DeviceInstance', self.vrmInstanceIDBMS)
    self.dbusBmsService.add_path('/Mgmt/ProcessName', __file__)
    self.dbusBmsService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
    self.dbusBmsService.add_path('/Mgmt/Connection', "Local DBus Injection")

    # Create the mandatory objects
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

    #register for overhead topic on mqtt.
    self.requestTopics = ['es-ESS/SolarOverheadDistributor/Requests/+/IsAutomatic', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/Consumption', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/CustomName', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/IgnoreBatReservation', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/OnKeywordRegex', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/Minimum', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/OnUrl', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/OffUrl', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/Priority',
                          'es-ESS/SolarOverheadDistributor/Requests/+/IsNPC', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/StatusUrl', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/StepSize', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/Request', 
                          'es-ESS/SolarOverheadDistributor/Requests/+/VRMInstanceID']
    
    for x in self.requestTopics: Globals.mqttClient.subscribe(x)

    #Check, if we need any NPC-Consumers to be created.
    #they will be fully orchestrated by SolarOverheadDistributor without external MQTT Requests.
    for s in self.config.sections():
      if (s.startswith("NPC:")):
         i(self, "Found NPC SolarOverheadConsumer: " + s)
         try:
            #Consumer found. Create Request.
            consumerKey = s.replace("NPC:", "")
            Globals.mqttClient.publish("{0}/SolarOverheadDistributor/Requests/{1}/IsNPC".format(Globals.esEssTag, consumerKey), "true",1)
            Globals.mqttClient.publish("{0}/SolarOverheadDistributor/Requests/{1}/IsAutomatic".format(Globals.esEssTag, consumerKey), "true",1)
            for (k, v) in self.config.items(s):
               if (k != "StepSize"):
                  Globals.mqttClient.publish("{0}/SolarOverheadDistributor/Requests/{1}/{2}".format(Globals.esEssTag, consumerKey,k), v,1)

               #NPC Consumers always have StepSize = request.
               if (k == "Request"):
                  Globals.mqttClient.publish("{0}/SolarOverheadDistributor/Requests/{1}/StepSize".format(Globals.esEssTag, consumerKey), v,1)

         except Exception as ex:
            c(self, "Error parsing NPC-Consumer: " + s + ". Please validate outline requirements.")
        
    # last update
    self.lastUpdate = 0
 
    Globals.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "{0} initialized.".format(self.__class__.__name__))

    # Updates.
    gobject.timeout_add(5000, self._updateValues)
    gobject.timeout_add(60000, self._update)

  def processMqttMessage(self, msg):
    try:
      consumerKeyMo = re.search('es\-ESS/SolarOverheadDistributor/Requests/([^/]+)/', msg.topic)
      if (consumerKeyMo is not None):
         consumerKey = consumerKeyMo.group(1)
         if (not consumerKey in Globals.knownSolarOverheadConsumers):
            i("SolarOverheadDistributor","New SolarOverhead-Consumer registered: " + consumerKey + ". Creating respective services.")
            with Globals.knownSolarOverheadConsumersLock:
               Globals.knownSolarOverheadConsumers[consumerKey] = SolarOverheadConsumer(consumerKey)

         Globals.knownSolarOverheadConsumers[consumerKey].setValue(msg.topic, str(msg.payload)[2:-1])

    except Exception as e:
       c(self, "Exception", exc_info=e)
     
  def _updateValues(self):
    if (self.futureUpdateValues is None or self.futureUpdateValues.done()):
      self.futureUpdateValues = Globals.esESS.threadPool.submit(self._updateValuesThreaded)
    else:
      w(self, "Processing Thread is still running, not submitting another one, to prevent Threadpool from filling up. ")
   
    return True

  def _updateValuesThreaded(self):
      try:
         with Globals.knownSolarOverheadConsumersLock:
            for consumerKey in Globals.knownSolarOverheadConsumers:
               consumer = Globals.knownSolarOverheadConsumers[consumerKey]
                  
               if (not consumer.isInitialized):
                  consumer.checkFinalInit(self)

               if (consumer.isInitialized):
                  #Update consumer values.
                  consumer.dumpFakeBMS()

            #dump main bms information as well. 
            self.dbusBmsService["/Dc/0/Power"] = 0
            self.dbusBmsService["/CustomName"] = "Battery Charge Reservation: " + str(self.dbusService["/Calculations/Battery/Reservation"]) + "W"

            if (self.dbusService["/Calculations/Battery/Reservation"] > 0 and self.dbusService["/Calculations/Battery/Power"] > 0):
               self.dbusBmsService["/Soc"] = self.dbusService["/Calculations/Battery/Power"] / self.dbusService["/Calculations/Battery/Reservation"] * 100.0
            else:
               self.dbusBmsService["/Soc"] = 0

      except Exception as e:
          e(self, "Error", exc_info = e)

      return True
        
  def _update(self):
     if (self.futureUpdate is None or self.futureUpdate.done()):
        self.futureUpdate = Globals.esESS.threadPool.submit(self._updateThreaded)
     else:
         w(self, "Processing Thread is still running, not submitting another one, to prevent threadpool from filling up. ")
     return True

  def _updateThreaded(self):   
    try:
       d("SolarOverheadDistributor", "Updating Solar-Overhead distribution")

       with Globals.knownSolarOverheadConsumersLock:

         # first, check if we have new Overhead consumers to initialize.
         for consumerKey in Globals.knownSolarOverheadConsumers:
            d(self, "pre-checks on consumer {0}".format(consumerKey))
            consumer = Globals.knownSolarOverheadConsumers[consumerKey]
            
            if (not consumer.isInitialized):
               consumer.checkFinalInit(self)

            if (consumer.isInitialized):
               #Update consumer values.
               consumer.dumpFakeBMS()

         #query values we need to determine the overhead
         l1Power = Globals.DbusWrapper.system.Ac.Grid.L1.Power
         l2Power = Globals.DbusWrapper.system.Ac.Grid.L2.Power
         l3Power = Globals.DbusWrapper.system.Ac.Grid.L3.Power

         feedIn = min(l1Power + l2Power + l3Power, 0) * -1
         batPower = Globals.DbusWrapper.system.Dc.Battery.Power
         batSoc = Globals.DbusWrapper.system.Dc.Battery.Soc
         assignedConsumption = 0

         self.Publish("/Calculations/Grid/L1/Power", l1Power)
         self.Publish("/Calculations/Grid/L2/Power", l2Power)
         self.Publish("/Calculations/Grid/L3/Power", l3Power)
         self.Publish("/Calculations/Grid/TotalFeedIn", feedIn)

         i("SolarOverheadDistributor","L1/L2/L3/Bat/Soc/Feedin is " + str(l1Power) + "/" + str(l2Power) + "/" + str(l3Power) + "/" + str(batPower) + "/" + str(batSoc) + "/" + str(feedIn))

         overheadDistribution = {}
         for consumerKey in Globals.knownSolarOverheadConsumers:
            consumer = Globals.knownSolarOverheadConsumers[consumerKey]

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
            if (batSoc < 100):
               equation = self.config["SolarOverheadDistributor"]["MinBatteryCharge"]
               equation = equation.replace("SOC", str(batSoc))
               minBatCharge = eval(equation)
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

         for consumerKey in Globals.knownSolarOverheadConsumers:
            consumer = Globals.knownSolarOverheadConsumers[consumerKey]
            
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
       
    # return true, otherwise add_timeout will be removed from GObject - see docs http://library.isr.ist.utl.pt/docs/pygtk2reference/gobject-functions.html#function-gobject--timeout-add
    return True
 
  def doTryFullfill(self, overhead, overheadDistribution, minBatCharge):
      overheadAssigned = 0
     
      for consumerDupe in sorted(Globals.knownSolarOverheadConsumers.values(), key=operator.attrgetter('priority')): 
         while (True):
            consumerKey = consumerDupe.consumerKey
            overheadBefore = overhead
            consumer = Globals.knownSolarOverheadConsumers[consumerKey]

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

      for consumerDupe in sorted(Globals.knownSolarOverheadConsumers.values(), key=operator.attrgetter('priority')):   
         consumerKey = consumerDupe.consumerKey        
         consumer = Globals.knownSolarOverheadConsumers[consumerKey]

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
         Globals.mqttClient.publish("es-ESS/SolarOverheadDistributor{0}".format(path), value, 1)
      except Exception as e:
       c(self, "Exception", exc_info=e)
