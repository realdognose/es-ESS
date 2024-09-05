import os
import platform
import sys
from typing import Dict
import dbus # type: ignore
import dbus.service # type: ignore
import inspect
import pprint
import requests # type: ignore
import os
import sys

# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore

# esEss imports
from Helper import i, c, d, w, e, t, dbusConnection
import Globals
from esESSService import esESSService

class ShellyPMInverter(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.vrmInstanceID = self.config["ShellyPMInverter"]["VRMInstanceID"]
        self.customName = self.config["ShellyPMInverter"]["CustomName"]
        self.pollFrequencyMs = int(self.config["ShellyPMInverter"]["PollFrequencyMs"])
        self.shellyUsername = self.config["ShellyPMInverter"]["Username"]
        self.shellyPassword = self.config["ShellyPMInverter"]["Password"]
        self.shellyHost = self.config["ShellyPMInverter"]["Host"]
        self.shellyPhase = self.config["ShellyPMInverter"]["Phase"]
        self.shellyPos = int(self.config["ShellyPMInverter"]["Position"])
        self.connectionErrors = 0

    def initDbusService(self):
        self.serviceType = "com.victronenergy.pvinverter"
        self.serviceName = self.serviceType + ".esESS.ShellyPMInverter_" + str(self.vrmInstanceID)
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
        self.publishServiceMessage(self, "Initializing dbus-service")
        
        #Mgmt-Infos
        self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "dbus")

        # Create the mandatory objects
        self.dbusService.add_path('/ProductId', 0xA144)
        self.dbusService.add_path('/DeviceType', 345) 
        self.dbusService.add_path('/Role', "pvinverter")
        self.dbusService.add_path('/ProductName', "{0} ShellyPMInverter".format(Globals.esEssTag)) 
        self.dbusService.add_path('/Latency', None)    
        self.dbusService.add_path('/StatusCode', 7)   
        self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/Connected', 1)
        self.dbusService.add_path('/Position', self.shellyPos)
        self.dbusService.add_path('/Serial', "1337")
        self.dbusService.add_path('/CustomName', self.customName)

        #inverter props
        self.dbusService.add_path('/Ac/Power', None)
        self.dbusService.add_path('/Ac/Energy/Forward', None)
        for x in range(1,4):
            self.dbusService.add_path('/Ac/L' + str(x) + '/Voltage', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Current', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Power', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Energy/Forward', None)
            self.dbusService.add_path('/Ac/L' + str(x) + '/Energy/Reverse', None)

    def initDbusSubscriptions(self):
        pass
        
    def initWorkerThreads(self):
        self.registerWorkerThread(self.queryShelly, self.pollFrequencyMs)

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       pass

    def queryShelly(self):
        try:
            URL = "http://%s:%s@%s/rpc/Switch.GetStatus?id=0" % (self.shellyUsername, self.shellyPassword, self.shellyHost)
            URL = URL.replace(":@", "")
            #d(self, "Polling: " + URL)

            meter_r = requests.get(url = URL, timeout=(self.pollFrequencyMs/1000))
            meter_data = meter_r.json()     
        
            # check for Json
            if not meter_data:
                e(self, "Shelly response is not resolvable to JSON.")
                
            if (meter_data):
                self.dbusService['/Connected'] = 1
                self.dbusService['/StatusCode'] = 7
                self.connectionErrors = 0

                #All good, evaluate and publish on dbus. 
                self.dbusService['/Ac/Power'] = meter_data['apower']
                for x in range(1,4):
                    if (x != self.shellyPhase):
                        self.dbusService['/Ac/L' + str(x) + '/Voltage'] = 0
                        self.dbusService['/Ac/L' + str(x) + '/Current'] = 0
                        self.dbusService['/Ac/L' + str(x) + '/Power'] = 0
                        self.dbusService['/Ac/L' + str(x) + '/Energy/Forward'] = 0
                        self.dbusService['/Ac/L' + str(x) + '/Energy/Reverse'] = 0
                
                self.dbusService['/Ac/L' + self.shellyPhase + '/Voltage'] = meter_data['voltage']
                self.dbusService['/Ac/L' + self.shellyPhase + '/Current'] = meter_data['current']
                self.dbusService['/Ac/L' + self.shellyPhase + '/Power'] = meter_data['apower']
                self.dbusService['/Ac/L' + self.shellyPhase + '/Energy/Forward'] = meter_data['aenergy']['total'] / 1000.0
                self.dbusService['/Ac/L' + self.shellyPhase + '/Energy/Reverse'] = 0

                self.dbusService['/Ac/Power'] = meter_data['apower']
                self.dbusService['/Ac/Energy/Forward'] = meter_data['aenergy']['total'] / 1000.0
            else:
                #publish null values, so it is clear, that we have issues reading the meter and OS can decide how to handle. 
                self.publishNone()

        except Exception as ex:
            w(self, "Shelly PM did not response fast enough to sustain a poll frequency of {1} ms. Please adjust. After 3 failures, null will be published.".format(self.pollFrequencyMs))
            self.connectionErrors += 1
            #c(self, "Exception", exc_info=ex)

            if (self.connectionErrors > 3):
                e(self, "More than 3 consecutive timeouts. Assuming Shelly PM disconnected.")
                self.publishNone()
    
    def publishNone(self):
        self.dbusService["/Connected"] = 0
        self.dbusService['/StatusCode'] = 10
        self.dbusService['/Ac/Power'] = None
        self.dbusService['/Ac/L1/Voltage'] = None
        self.dbusService['/Ac/L2/Voltage'] = None
        self.dbusService['/Ac/L3/Voltage'] = None
        self.dbusService['/Ac/L1/Current'] = None
        self.dbusService['/Ac/L2/Current'] = None
        self.dbusService['/Ac/L3/Current'] = None
        self.dbusService['/Ac/L1/Power'] = None
        self.dbusService['/Ac/L2/Power'] = None
        self.dbusService['/Ac/L3/Power'] = None


