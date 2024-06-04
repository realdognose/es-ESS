import json
import threading
from time import sleep
import paho.mqtt.client as mqtt # type: ignore
from Helper import i, c, d, w, e

#superglobals
currentVersionString="es-ESS 0.33b"
esEssTag = "es-ESS"

#Services
pvOverheadDistributionService = None
timeToGoCalculator = None
froniusWattpilotService = None

#Various
mqttClient = mqtt.Client("es-ESS-Client")
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

def configureMqtt(config):
  i(esEssTag, "MQTT client: Connecting to broker localhost")
  mqttClient.on_disconnect = onGlobalMqttDisconnect
  mqttClient.on_connect = onGlobalMqttConnect
  mqttClient.on_message = onGlobalMqttMessage
  
  mqttClient.connect(
      host="localhost",
      port=1883
  )
  mqttClient.loop_start()

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
      if (logIncomingMqttMessages):
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

