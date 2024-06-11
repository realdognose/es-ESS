import configparser
import datetime
from enum import Enum
import json
import os
import sys
import threading
from time import sleep
import time
import paho.mqtt.client as mqtt # type: ignore
from Helper import i, c, d, w, e
# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService,VeDbusItemExport, VeDbusItemImport # type: ignore
import dbus # type: ignore
from dbus.mainloop.glib import DBusGMainLoop # type: ignore

from DBus import DbusC

#superglobals
currentVersionString="es-ESS 24.6.4.25 b"
esEssTag = "es-ESS"
DbusWrapper = DbusC()

#VEBus Value exports
#VeDb_W_system_0_Dc_Battery_TimeToGo = VeDbusItemExport(dbusConn, 'com.victronenergy.system', "/system/0/Dc/Battery/TimeToGo")

#Services
esESS = None
solarOverheadDistributor = None
timeToGoCalculator = None
FroniusWattpilot = None
chargeCurrentReducer = None
mqttExporter = None

#Various

globalValueStore = {}
logIncomingMqttMessages=True

ServiceMessageType = Enum('ServiceMessageType', ['Operational', 'Info', 'Error', 'Warning'])

#defs
def getFromGlobalStoreValue(key, default):
  if (key in globalValueStore):
     d(esEssTag, "Global Mqtt-Store contains {0}. Returning stored value {1}.".format(key, globalValueStore[key]))
     return globalValueStore[key]
  
  d(esEssTag, "Global Mqtt-Store doesn't contain {0}. Returning default value {1}".format(key, default))
  return default

def getConfig():
   config = configparser.ConfigParser()
   config.optionxform = str
   config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))

   return config



def publishServiceMessage(module, messageKind, message, relatedRawValue=None):
    pass
   