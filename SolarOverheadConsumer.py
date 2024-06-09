import json
import platform
import re
import sys
import os
from time import sleep
import paho.mqtt.client as mqtt # type: ignore
from Helper import i, c, d, w, e
import requests  # type: ignore
# victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService # type: ignore

#es-ESS imports
import Globals
import Helper
from Helper import i, c, d, w, e, dbusConnection

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
     
     i(self, "PVOverhead Consumer created: " + consumerKey + ". Waiting for required values to arrive...")

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
            customName += " (ƒ)"
            
         
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
     Globals.mqttClient.publish("{0}/SolarOverheadDistributor/Requests/{1}/Allowance".format(Globals.esEssTag, self.consumerKey), self.allowance, 1)
     d(self, "Consumer {0} reporting allowance of {1}W".format(self.consumerKey, self.allowance))

     if (self.isNPC):
        self.npcControl()
        Globals.mqttClient.publish("{0}/SolarOverheadDistributor/Requests/{1}/Consumption".format(Globals.esEssTag, self.consumerKey), self.consumption, 1)

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
      
