import configparser
from enum import Enum
import os
#superglobals
currentVersionString="es-ESS 24.6.4.25 b"
esEssTag = "es-ESS"

#RootService
esESS = None

#Enums
ServiceMessageType = Enum('ServiceMessageType', ['Operational', 'Critical', 'Error', 'Warning'])
MqttSubscriptionType = Enum('MqttSubscriptionType', ['Main', 'Local'])

#defs
def getConfig():
   config = configparser.ConfigParser()
   config.optionxform = str
   config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))

   return config
   