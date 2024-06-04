import json
import platform
import sys
import os
from time import sleep
import paho.mqtt.client as mqtt # type: ignore
from Helper import i, c, d, w, e

# victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService # type: ignore

#es-ESS imports
import Globals
import Helper
from Helper import i, c, d, w, e, dbusConnection

class PVOverheadConsumer:
  def __init__(self, consumerKey):
     #wait until we have gathered ALL required values.
     #then, the device can be initialized finally.
     self.vrmInstanceID = None
     self.initialized = False
     self.dbusService = None
     self.customName = None
     self.minimum = 0
     self.request = 0
     self.stepSize = 0
     self.consumption = 0
     self.allowance = 0
     self.automatic = False
     self.consumerKey = consumerKey
     self.ignoreBatReservation = False
     
     i(self, "PVOverhead Consumer created: " + consumerKey + ". Waiting for required values to arrive...")

  def setValue(self, key, value):
     key = key.replace('/esEss/PVOverheadDistributor/requests/' + self.consumerKey +'/', "")
     
     if (key == "minimum"):
        self.minimum = float(value)
     elif (key == "request"):
        self.request = float(value)
     elif (key == "stepSize"):
        self.stepSize = float(value)
     elif (key == "consumption"):
        self.consumption = float(value)
     elif (key == "automatic"):
        self.automatic = value.lower() == "true"
     elif (key == "vrmInstanceID"):
        self.vrmInstanceID = int(value)
     elif (key == "ignoreBatReservation"):
        self.ignoreBatReservation = value.lower() == "true"
     elif (key == "allowance"):
        self.allowance = float(value)
     elif (key == "customName"):
        self.customName = value
    
  def checkFinalInit(self, pvOverheadDistributionService):
     #to create the final instance on DBUS, we need the VRMId at least.
     if (self.vrmInstanceID is not None):
        self.initialize()
        pvOverheadDistributionService.initializeConsumer(self) 

  def initialize(self):
     self.serviceType = "com.victronenergy.battery"
     self.serviceName = self.serviceType + ".es-ess.pvOverheadConsumer_" + str(self.vrmInstanceID)
     self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
     
     #Mgmt-Infos
     self.dbusService.add_path('/DeviceInstance', self.vrmInstanceID)
     self.dbusService.add_path('/Mgmt/ProcessName', __file__)
     self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
     self.dbusService.add_path('/Mgmt/Connection', "Local DBus Injection")

     # Create the mandatory objects
     self.dbusService.add_path('/ProductId', 65535)
     self.dbusService.add_path('/ProductName', "ES-ESS PVOverheadConsumer") 
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
     
     i(self,"Initialization of consumer completed.")
     self.initialized = True

  def dumpFakeBMS(self):
     d(self, "Dumping Fake-BMS for consumer: " + self.consumerKey)
     self.dbusService["/Dc/0/Power"] = self.consumption

     if (self.customName is not None and self.request is not None):
         self.dbusService["/CustomName"] = self.customName + " [Req.: " + str(self.request) + "W]"

     if (self.request > 0):
        self.dbusService["/Soc"] = self.consumption / self.request * 100.0
     else:
        self.dbusService["/Soc"] = 0

  def dumpRequestValues(self, pods):
    pods.dbusService["/requests/" + self.consumerKey + "/consumption"] = self.consumption
    pods.dbusService["/requests/" + self.consumerKey + "/request"] = self.request
    pods.dbusService["/requests/" + self.consumerKey + "/automatic"] = self.automatic
    pods.dbusService["/requests/" + self.consumerKey + "/customName"] = self.customName
    pods.dbusService["/requests/" + self.consumerKey + "/minimum"] = self.minimum
    pods.dbusService["/requests/" + self.consumerKey + "/stepSize"] = self.stepSize
    pods.dbusService["/requests/" + self.consumerKey + "/allowance"] = self.allowance
    pods.dbusService["/requests/" + self.consumerKey + "/vrmInstanceID"] = self.vrmInstanceID
    pods.dbusService["/requests/" + self.consumerKey + "/ignoreBatReservation"] = self.ignoreBatReservation
