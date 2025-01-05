import configparser
from datetime import datetime
from enum import Enum
import os
from Helper import d,w,e,i,t
#superglobals
esEssTag = "es-ESS"
esEssTagService = "esESS"
currentVersion = "25.01.05"
currentVersionString="{0} {1} beta".format(esEssTag, currentVersion)

#will be updated at startup
userTimezone = "UTC"

#RootService
esESS = None

#Enums
ServiceMessageType = Enum('ServiceMessageType', ['Operational', 'Critical', 'Error', 'Warning'])
MqttSubscriptionType = Enum('MqttSubscriptionType', ['Main', 'Local'])

def getUserTime():
   usertime = os.popen('TZ=":{0}" date +"%Y-%m-%d %H:%M:%S"'.format(userTimezone)).read()
   #d("Globals", "User time is: {0}".format(usertime))
   return usertime.strip()

#defs
def getConfig():
   config = configparser.ConfigParser()
   config.optionxform = str
   config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))

   return config
   