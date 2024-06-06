import configparser
import datetime
import json
import os
import sys
import threading
from time import sleep
import paho.mqtt.client as mqtt # type: ignore
from Helper import i, c, d, w, e
# victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
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
pvOverheadDistributionService = None
timeToGoCalculator = None
FroniusWattpilot = None
chargeCurrentReducer = None

#Various
mqttClient = mqtt.Client("es-ESS-Mqtt-Client")
knownPVOverheadConsumers = {}
knownPVOverheadConsumersLock = threading.Lock()
globalValueStore = {}
logIncomingMqttMessages=True

#defs
def getFromGlobalStoreValue(key, default):
  if (key in globalValueStore):
     jsonObject = json.loads(globalValueStore[key])
     if (jsonObject is not None):
        return jsonObject["value"]
  
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

  mqttClient.will_set("es-ESS/$SYS/status", "Offline", 2, True)

  mqttClient.connect(
      host=config["Mqtt"]["Host"],
      port=int(config["Mqtt"]["Port"])
  )

  mqttClient.loop_start()
  mqttClient.publish("es-ESS/$SYS/status", "Online", 2, True)
  mqttClient.publish("es-ESS/$SYS/version", currentVersionString, 2, True)
  mqttClient.publish("es-ESS/$SYS/connectionTime", str(datetime.datetime.now()), 2, True)
  mqttClient.publish("es-ESS/$SYS/github", "https://github.com/realdognose/es-ESS", 2, True)

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

def onGlobalMqttMessage(client, userdata, msg):
    try:
      d(esEssTag,'Received MQTT-Message: ' + msg.topic + ' => ' + str(msg.payload)[2:-1])

      #Just forward Messages to their respective service.
      if (msg.topic.find('esEss/PVOverheadDistributor') > -1):
        if (pvOverheadDistributionService is not None):
            pvOverheadDistributionService.processMqttMessage(msg)
        else:
          w(esEssTag,"PVOverheadDistributor-Module is not enabled.")
      else:
        #Not a dedicated service message. Store in globalValueStore, a service might have requested that value for observation. 
        globalValueStore[msg.topic] = str(msg.payload)[2:-1]
    except Exception as e:
       c(esEssTag, "Exception catched", exc_info=e)

