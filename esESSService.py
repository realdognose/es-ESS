from enum import Enum
from typing import Dict
import Globals
from Helper import i, c, d, w, e
from abc import ABC, abstractmethod
from Globals import MqttSubscriptionType

#ServiceBase for all Service-Classes.
#Used to orchestrate initialization, dbus and mqtt handling in a central place.
#all relevant service-calls will be triggered by esESS during initialization. 
class esESSService(ABC):
    def __init__(self):
        self.config = Globals.getConfig()
        self._dbusSubscriptions: Dict[str, DbusSubscription] = {}
        self._mqttSubscriptions: Dict[str, MqttSubscription] = {}
        self._workerThreads: list[WorkerThread ]= []

    @abstractmethod
    def initDbusService(self):
        pass

    @abstractmethod
    def initDbusSubscriptions(self):
        pass

    def registerDbusSubscription(self, serviceName, dbusPath, callback=None):
        sub = DbusSubscription(serviceName, dbusPath, callback)
        self._dbusSubscriptions[sub.valueKey] = sub
        return sub

    @abstractmethod
    def initMqttSubscriptions(self):
        pass

    def registerMqttSubscription(self, topic, qos=0, type=MqttSubscriptionType.Main, callback=None):
        sub = MqttSubscription(topic, qos, type, callback)
        self._mqttSubscriptions[sub.topic] = sub
        return sub
    
    @abstractmethod
    def initWorkerThreads(self):
        pass

    def registerWorkerThread(self, thread, interval):
        self._workerThreads.append(WorkerThread(self, thread, interval))

    @abstractmethod
    def initFinalize(self):
        pass

    def publishMainMqtt(self, topic, payload, qos=0, retain=False):
        Globals.esESS.publishMainMqtt(topic, payload, qos, retain)
    
    def publishLocalMqtt(self, topic, payload, qos=0, retain=False):
        Globals.esESS.publishLocalMqtt(topic, payload, qos, retain)

class WorkerThread:
    def __init__(self, service, thread, interval):
        self.thread = thread
        self.interval = interval
        self.future = None
        self.service = service

class DbusSubscription:
    def buildValueKey(serviceName, dbusPath):
        return "{0}{1}".format(".".join(serviceName.split('.')[:3]), dbusPath)
    
    def __init__(self, serviceName, dbusPath, callback=None):
        self.commonServiceName = ".".join(serviceName.split('.')[:3])
        self.serviceName = serviceName
        self.dbusPath = dbusPath
        self.callback = callback
        self.value = None

    @property
    def valueKey(self):
        return DbusSubscription.buildValueKey(self.serviceName, self.dbusPath)
    
    def publish(self, value):
        Globals.esESS.publishDbusValue(self, value)

class MqttSubscription:

    def __init__(self, topic, qos=0, type=MqttSubscriptionType.Main, callback=None):
        self.topic = topic
        self.qos = qos
        self.type = type
        self.callback = callback
        self.value = None
    

    

    