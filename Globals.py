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
mqttClient = mqtt.Client("es-ESS-Mqtt-Client")
localMqttClient = mqtt.Client("es-ESS-Local-Mqtt-Client")
knownSolarOverheadConsumers = {}
knownSolarOverheadConsumersLock = threading.Lock()
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

def configureMqtt(config):
    i(esEssTag, "MQTT client: Connecting to broker: {0}".format(config["Mqtt"]["Host"]))
    mqttClient.on_disconnect = onGlobalMqttDisconnect
    mqttClient.on_connect = onGlobalMqttConnect
    mqttClient.on_message = onGlobalMqttMessage

    if 'User' in config['Mqtt'] and 'Password' in config['Mqtt'] and config['Mqtt']['User'] != '' and config['Mqtt']['Password'] != '':
        mqttClient.username_pw_set(username=config['Mqtt']['User'], password=config['Mqtt']['Password'])

    mqttClient.will_set("es-ESS/$SYS/Status", "Offline", 2, True)

    mqttClient.connect(
        host=config["Mqtt"]["Host"],
        port=int(config["Mqtt"]["Port"])
    )

    mqttClient.loop_start()
    mqttClient.publish("es-ESS/$SYS/Status", "Online", 2, True)
    mqttClient.publish("es-ESS/$SYS/Version", currentVersionString, 2, True)
    mqttClient.publish("es-ESS/$SYS/ConnectionTime", time.time(), 2, True)
    mqttClient.publish("es-ESS/$SYS/ConnectionDateTime", str(datetime.datetime.now()), 2, True)
    mqttClient.publish("es-ESS/$SYS/Github", "https://github.com/realdognose/es-ESS", 2, True)

    #local mqtt
    i(esEssTag, "MQTT client: Connecting to broker: {0}".format("localhost"))
    localMqttClient.on_disconnect = onGlobalMqttDisconnect
    localMqttClient.on_connect = onGlobalMqttConnect
    localMqttClient.on_message = onGlobalMqttMessage

    localMqttClient.connect(
        host="localhost",
        port=1883
    )

    localMqttClient.loop_start()


def onGlobalMqttDisconnect(client, userdata, rc):
    global connected
    w(esEssTag, "MQTT client: Got disconnected")
    if rc != 0:
        w(esEssTag, 'MQTT client: Unexpected MQTT disconnection. Will auto-reconnect')
    else:
        w(esEssTag, 'MQTT client: rc value:' + str(rc))

    while connected == 0:
        try:
            w(esEssTag, "MQTT client: Trying to reconnect")
            client.connect('localhost')
            connected = 1
        except Exception as err:
            e(esEssTag, "MQTT client: Retrying in 15 seconds")
            connected = 0
            sleep(15)

def onGlobalMqttConnect(client, userdata, flags, rc):
    global connected
    if rc == 0:
        i(esEssTag, "MQTT client: Connected to MQTT broker!")
        connected = 1
    else:
        e(esEssTag, "MQTT client: Failed to connect, return code %d\n", rc)

def publishServiceMessage(module, messageKind, message, relatedRawValue=None):
    if (not isinstance(module, str)):
       module = module.__class__.__name__

    if (isinstance(messageKind, ServiceMessageType)):
        messageKind = messageKind.name

    mqttClient.publish("{0}/{1}/ServiceMessages/{2}/Time".format(esEssTag, module, messageKind), time.time(), 1, False)
    mqttClient.publish("{0}/{1}/ServiceMessages/{2}/DateTime".format(esEssTag, module, messageKind), str(datetime.datetime.now()), 1, False)
    mqttClient.publish("{0}/{1}/ServiceMessages/{2}/Message".format(esEssTag, module, messageKind), message, 1, False)

    if (relatedRawValue is not None):
        mqttClient.publish("{0}/{1}/ServiceMessages/{2}/RawValue".format(esEssTag, module, messageKind), relatedRawValue, 1, False)
    

def onGlobalMqttMessage(client, userdata, msg):
    try:
      d(esEssTag, "Received MQTT-Message: {0} => {1}".format(msg.topic, str(msg.payload)[2:-1]))

      #Just forward Messages to their respective service.
      if (msg.topic.find('es-ESS/SolarOverheadDistributor') > -1):
        if (solarOverheadDistributor is not None):
            solarOverheadDistributor.processMqttMessage(msg)
        else:
          w(esEssTag,"SolarOverheadDistributor-Module is not enabled.")
      
    
      #store in global store as well. 
      globalValueStore[msg.topic] = str(msg.payload)[2:-1]
    except Exception as e:
       c(esEssTag, "Exception catched", exc_info=e)

