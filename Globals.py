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

#superglobals
currentVersionString="es-ESS 24.6.4.25 b"
esEssTag = "es-ESS"

#Services
esESS = None
solarOverheadDistributor = None
timeToGoCalculator = None
FroniusWattpilot = None
chargeCurrentReducer = None
mqttExporter = None

#Various
logIncomingMqttMessages=True

ServiceMessageType = Enum('ServiceMessageType', ['Operational'])
MqttSubscriptionType = Enum('MqttSubscriptionType', ['Main', 'Local'])

#defs
def getConfig():
   config = configparser.ConfigParser()
   config.optionxform = str
   config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))

   return config
   