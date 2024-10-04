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
        self.pmInverters: Dict[str, ShellyPMInverterDevice] = {}

        try:
            d(self, "Scanning config for shelly pm inverters")
            for k in self.config.sections():
                if (k.startswith("ShellyPMInverter:")):
                    parts = k.split(':')
                    key = parts[1].strip()

                    self.pmInverters[key] = ShellyPMInverterDevice(self, key, self.config[k])

            i(self, "Found {0} Shelly PM Inverters.".format(len(self.pmInverters)))
            
        except Exception as ex:
            c(self, "Exception", exc_info=ex)

    def initDbusService(self):
        for dev in self.pmInverters.values():
            self.publishServiceMessage(self, "Initializing dbus-service for PMInverter: " + dev.key)
            dev.initDbusService()
            
    def initDbusSubscriptions(self):
        pass
        
    def initWorkerThreads(self):
        for dev in self.pmInverters.values():
            self.registerWorkerThread(dev.queryShelly, dev.pollFrequencyMs)

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       pass

class ShellyPMInverterDevice:
    def __init__(self, rootService, key, cfgSection):
        self.key = key
        self.rootService = rootService
        self.customName = cfgSection["CustomName"]
        self.vrmInstanceID = cfgSection["VRMInstanceID"]
        self.customName = cfgSection["CustomName"]
        self.pollFrequencyMs = int(cfgSection["PollFrequencyMs"])
        self.shellyUsername = cfgSection["Username"]
        self.shellyPassword = cfgSection["Password"]
        self.shellyHost = cfgSection["Host"]
        self.shellyPhase = cfgSection["Phase"]
        self.shellyPos = int(cfgSection["Position"])
        self.value = 0.0
        self.humidity = 0.0
        self.pressure = 0.0

    def initDbusService(self):
        self.serviceType = "com.victronenergy.pvinverter"
        self.serviceName = self.serviceType + "." + Globals.esEssTagService + "_ShellyPMInverter_" + self.key
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection(), register=False)
        
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

        self.dbusService.register()
        self.connectionErrors = 0

    def queryShelly(self):
        try:
            URL = "http://%s:%s@%s/rpc/Switch.GetStatus?id=0" % (self.shellyUsername, self.shellyPassword, self.shellyHost)
            URL = URL.replace(":@", "")

            #timeout should be half the poll frequency, so there is time to process.
            meter_r = requests.get(url = URL, timeout=(self.pollFrequencyMs/2000))
            meter_data = meter_r.json()     
        
            # check for Json
            if not meter_data:
                e(self.rootService, "Shelly response is not resolvable to JSON.")
                
            if (meter_data):
                self.dbusService['/Connected'] = 1
                self.dbusService['/StatusCode'] = 7
                self.connectionErrors = 0

                #All good, evaluate and publish on dbus. 
                self.dbusService['/Ac/Power'] = meter_data['apower']
                for x in range(1,4):
                    if (x != self.shellyPhase):
                        self.dbusService['/Ac/L' + str(x) + '/Voltage'] = None
                        self.dbusService['/Ac/L' + str(x) + '/Current'] = None
                        self.dbusService['/Ac/L' + str(x) + '/Power'] = None
                        self.dbusService['/Ac/L' + str(x) + '/Energy/Forward'] = None
                        self.dbusService['/Ac/L' + str(x) + '/Energy/Reverse'] = None
                
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

        except requests.exceptions.Timeout as ex:
            w(self.rootService, "Shelly PM ({0}) did not response fast enough to sustain a poll frequency of {1} ms. Please adjust. After 3 failures, null will be published.".format(self.key, self.pollFrequencyMs))
            self.connectionErrors += 1

            if (self.connectionErrors > 3):
                e(self.rootService, "More than 3 consecutive timeouts. Assuming Shelly {0} PM disconnected.".format(self.key))
                self.publishNone()
        
        except Exception as ex:
            c(self.rootService, "Exception", exc_info=ex)
    
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


