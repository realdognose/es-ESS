from builtins import int
import configparser
import logging
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
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService # type: ignore

# esEss imports
import Globals
from Globals import getFromGlobalStoreValue
import Helper
from Helper import i, c, d, w, e, dbusConnection
from PVOVerheadConsumer import PVOverheadConsumer

class PVOverheadDistributionService:
  def __init__(self):
    self.config = configparser.ConfigParser()
    self.config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))

    #register the root service. device specific service will be registered as they are 
    #discovered during runtime.
    self.vrmInstanceID = int(self.config['PVOverheadDistributor']['VRMInstanceID'])
    self.vrmInstanceIDBMS = int(self.config['PVOverheadDistributor']['VRMInstanceID_ReservationMonitor'])
    self.serviceType = "com.victronenergy.settings"
    self.serviceName = self.serviceType + ".es-ess.pvOverheadDistributor_" + str(self.vrmInstanceID)
    i("PVOverheadDistributor","Registering service as: " + self.serviceName)
    self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())

    #dump root information about our service and register paths.
    self.dbusService.add_path('/Mgmt/ProcessName', __file__)
    self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
    self.dbusService.add_path('/Mgmt/Connection', "Local DBus Injection")

    # Create the mandatory objects
    self.dbusService.add_path('/DeviceInstance', self.vrmInstanceID)
    self.dbusService.add_path('/ProductId', 65535)
    self.dbusService.add_path('/ProductName', "ES-ESS PVOverheadService") 
    self.dbusService.add_path('/CustomName', "ES-ESS PVOverheadService") 
    self.dbusService.add_path('/Latency', None)    
    self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
    self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
    self.dbusService.add_path('/Connected', 1)
    self.dbusService.add_path('/Serial', "1337")
    self.dbusService.add_path('/LastUpdate', 0)

    self.dbusService.add_path('/calculations/gridL1', 0)
    self.dbusService.add_path('/calculations/gridL2', 0)
    self.dbusService.add_path('/calculations/gridL3', 0)
    self.dbusService.add_path('/calculations/gridTotalFeedIn', 0)

    self.dbusService.add_path('/calculations/batCharge', 0)
    self.dbusService.add_path('/calculations/batSoc', 0)
    self.dbusService.add_path('/calculations/batReservation', 0)
    
    self.dbusService.add_path('/calculations/overheadAvailable', 0)
    self.dbusService.add_path('/calculations/overheadAssigned', 0)
    self.dbusService.add_path('/calculations/overheadRemaining', 0)

    #Create a Fake-BMS to outline batteryChargeLimit, if active.
    self.bmsServiceType = "com.victronenergy.battery"
    self.bmsServiceName = self.bmsServiceType + ".es-ess.pvOverheadConsumer_" + str(self.vrmInstanceIDBMS)
    self.dbusBmsService = VeDbusService(self.bmsServiceName, bus=dbusConnection())
    
    #Mgmt-Infos
    self.dbusBmsService.add_path('/DeviceInstance', self.vrmInstanceIDBMS)
    self.dbusBmsService.add_path('/Mgmt/ProcessName', __file__)
    self.dbusBmsService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
    self.dbusBmsService.add_path('/Mgmt/Connection', "Local DBus Injection")

    # Create the mandatory objects
    self.dbusBmsService.add_path('/ProductId', 65535)
    self.dbusBmsService.add_path('/ProductName', "ES-ESS PVOverheadConsumer") 
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
    self.requestTopic = 'W/' + self.config["Default"]["VRMPortalID"] + '/esEss/PVOverheadDistributor/requests/#'
    i("PVOverheadDistributor","Subscribing to pvOverheadRequest-Topic: " + self.requestTopic)
    Globals.mqttClient.subscribe(self.requestTopic)

    #Also subscribe to values we need to determine the actual overhead. 
    #(So we don't need to do dbus imports)
    #TODO: Move subscripions to a centralized method, as other ESS Modules may need as well, plus reconnect / resub needs to be done. 
    Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Ac/Grid/L1/Power")
    Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Ac/Grid/L2/Power")
    Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Ac/Grid/L3/Power")
    Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Power")
    Globals.mqttClient.subscribe("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Soc")

    # last update
    self.lastUpdate = 0
 
    # Updates.
    gobject.timeout_add(int(5000), self._updateDbus)
    gobject.timeout_add(int(self.config['PVOverheadDistributor']['UpdateInterval']), self._update)

  def initializeConsumer(self, pvOverheadConsumer):
     # also extend PVOVerheadDistributers dbus paths accordingly.
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/request', None) 
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/consumption', None)
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/automatic', 'false')
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/ignoreBatReservation', 'false')
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/stepSize', None)
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/customName', None)
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/minimum', None)
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/allowance', None)
     self.dbusService.add_path('/requests/' + pvOverheadConsumer.consumerKey + '/vrmInstanceID', None)

     d("PVOverheadDistributor","Init of request topic done for: " + pvOverheadConsumer.consumerKey)

  def processMqttMessage(self, msg):
    topicCleaned = msg.topic.replace('W/' + self.config["Default"]["VRMPortalID"], "")
    consumerKeyMo = re.search('esEss/PVOverheadDistributor/requests/([^/]+)/', topicCleaned)
    if (consumerKeyMo is not None):
      consumerKey = consumerKeyMo.group(1)
      with Globals.knownPVOverheadConsumersLock:
         if (not consumerKey in Globals.knownPVOverheadConsumers):
            i("PVOverheadDistributor","New PVOverhead-Consumer registered: " + consumerKey + ". Creating respective services.")
            Globals.knownPVOverheadConsumers[consumerKey] = PVOverheadConsumer(consumerKey)

         Globals.knownPVOverheadConsumers[consumerKey].setValue(topicCleaned, str(msg.payload)[2:-1])
     
  def _updateDbus(self):
      try:
         with Globals.knownPVOverheadConsumersLock:
            for consumerKey in Globals.knownPVOverheadConsumers:
               consumer = Globals.knownPVOverheadConsumers[consumerKey]
                  
               if (not consumer.initialized):
                  consumer.checkFinalInit(self)

               if (consumer.initialized):
                  #Update consumer values.
                  consumer.dumpFakeBMS()
                  consumer.dumpRequestValues(self)

            #dump main bms information as well. 
            self.dbusBmsService["/Dc/0/Power"] = 0
            self.dbusBmsService["/CustomName"] = "Battery Charge Reservation: " + str(self.dbusService["/calculations/batReservation"]) + "W"

            if (self.dbusService["/calculations/batReservation"] > 0 and self.dbusService["/calculations/batCharge"] > 0):
               self.dbusBmsService["/Soc"] = self.dbusService["/calculations/batCharge"] / self.dbusService["/calculations/batReservation"] * 100.0
            else:
               self.dbusBmsService["/Soc"] = 0

      except Exception as e:
          logging.critical('Error at %s', '_updateDbus', exc_info=e)

      return True
        
  
  def _update(self):   
    try:
       # Each client is registering for pvOverheadShare. Topic structure: 
       #
       #  requests/clientKey/name             : name/key of the client.
       #  requests/clientKey/customName       : customName of the client, for display purpose. 
       #  requests/clientKey/request          : power requested by this client, watts. 
       #  requests/clientKey/minimum          : minimum power that needs to be assigned for startup, i.e. starting an ev charger.
       #  requests/clientKey/stepSize         : increment amount as more overhead becomes available.
       #  requests/clientKey/consumption      : actual client consumption, to determine available overhead
       #  requests/clientKey/automatic        : flag indicating wether this client is currently running in automatic mode.
       #
       d("PVOverheadDistributor", "Updating PV-Overhead distribution")

       with Globals.knownPVOverheadConsumersLock:
         # first, check if we have new Overhead consumers to initialize.
         for consumerKey in Globals.knownPVOverheadConsumers:
            consumer = Globals.knownPVOverheadConsumers[consumerKey]
            
            if (not consumer.initialized):
               consumer.checkFinalInit(self)

            if (consumer.initialized):
               #Update consumer values.
               consumer.dumpFakeBMS()
               consumer.dumpRequestValues(self)

         #query values we need to determine the overhead
         l1Power = getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Ac/Grid/L1/Power", 0)
         l2Power = getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Ac/Grid/L2/Power", 0)
         l3Power = getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Ac/Grid/L3/Power", 0) 
         feedIn = min(l1Power + l2Power + l3Power, 0) * -1
         batPower = getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Power", 0) 
         batSoc = getFromGlobalStoreValue("N/" + self.config["Default"]["VRMPortalID"] + "/system/0/Dc/Battery/Soc", 0)
         assignedConsumption = 0

         self.dbusService["/calculations/gridL1"] = l1Power
         self.dbusService["/calculations/gridL2"] = l2Power
         self.dbusService["/calculations/gridL3"] = l3Power
         self.dbusService["/calculations/gridTotalFeedIn"] = feedIn

         i("PVOverheadDistributor","L1/L2/L3/Bat/Soc/Feedin is " + str(l1Power) + "/" + str(l2Power) + "/" + str(l3Power) + "/" + str(batPower) + "/" + str(batSoc) + "/" + str(feedIn))

         overheadDistribution = {}
         for consumerKey in Globals.knownPVOverheadConsumers:
            consumer = Globals.knownPVOverheadConsumers[consumerKey]

            if (consumer.initialized and consumer.automatic):
               overheadDistribution[consumerKey] = 0 #initialize with 0
               d("PVOverheadDistributor","Already Assigned consumption on " + consumer.consumerKey + " (" + str(consumer.vrmInstanceID) +"): " + str(consumer.consumption))
               assignedConsumption += consumer.consumption

         minBatCharge = 0    
         try:
            if (batSoc < 100):
               equation = self.config["PVOverheadDistributor"]["MinBatteryCharge"]
               equation = equation.replace("SOC", str(batSoc))
               minBatCharge = eval(equation)
         except Exception as ex:
            e("PVOverheadDistributor","Error evaluation MinBatteryCharge-Equation. Using MinBatteryCharge=0.")

         overhead = max(0, feedIn + assignedConsumption + batPower)
         self.dbusService["/calculations/overheadAvailable"] = overhead
         i("PVOverheadDistributor","Available Overhead: " + str(overhead) + "W + ("+str(minBatCharge)+"W BatteryReservation, tho.)")

         overheadAssigned = 0

         self.dbusService["/calculations/batCharge"] = batPower
         self.dbusService["/calculations/batSoc"] = batSoc
         self.dbusService["/calculations/batReservation"] = minBatCharge

         #Iterate through device requests, and see, how much we can assign. If the overhead available
         #does not change within one iteration, we are done with assigning all available energy. 
         #Either all consumers then are running at maximum, or the remaining overhead doesn't satisfy the
         #need of additional consumers. In that case, the remaining overhead will be consumed by the house battery. 
         while (True):
            overheadBefore = overhead

            for consumerKey in Globals.knownPVOverheadConsumers:           
               consumer = Globals.knownPVOverheadConsumers[consumerKey]

               #check, if this consumer is currently allowed to consume. 
               canConsume = 0
               canConsumeReason = "None"

               if (consumer.initialized):
                  if (consumer.automatic):
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

                     d("PVOverheadDistributor", "Assigning " + str(canConsume) + "W to " + consumerKey + " because: " + canConsumeReason) 
                     overheadDistribution[consumerKey] += canConsume
                     overhead -= canConsume
                     overheadAssigned += canConsume
                        
            if (overheadBefore == overhead):
               break
         
         for consumerKey in Globals.knownPVOverheadConsumers:
            consumer = Globals.knownPVOverheadConsumers[consumerKey]
            
            if (consumer.initialized and consumer.automatic):
               consumer.allowance = overheadDistribution[consumerKey]
               consumer.dumpRequestValues(self)
         
         i("PVOverheadDistributor", "New Overhead assigned: " + str(overheadAssigned) + "W")
         self.dbusService["/calculations/overheadAssigned"] = overheadAssigned
         self.dbusService["/calculations/overheadRemaining"] = overhead
         

         #update lastupdate vars
         self.lastUpdate = time.time()   
         self.dbusService['/LastUpdate'] = self.lastUpdate           
    except Exception as e:
       logging.critical('Error at %s', '_update', exc_info=e)
       
    # return true, otherwise add_timeout will be removed from GObject - see docs http://library.isr.ist.utl.pt/docs/pygtk2reference/gobject-functions.html#function-gobject--timeout-add
    return True
 
  def _handlechangedvalue(self, path, value):
    logging.critical("Someone else updated %s to %s" % (path, value))
    return True # accept the change
