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

class Shelly3EMGrid(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.vrmInstanceID = self.config["Shelly3EMGrid"]["VRMInstanceID"]
        self.customName = self.config["Shelly3EMGrid"]["CustomName"]
        self.pollFrequencyMs = int(self.config["Shelly3EMGrid"]["PollFrequencyMs"])
        self.shellyUsername = self.config["Shelly3EMGrid"]["Username"]
        self.shellyPassword = self.config["Shelly3EMGrid"]["Password"]
        self.shellyHost = self.config["Shelly3EMGrid"]["Host"]
        self.connectionErrors = 0

    def initDbusService(self):
        self.serviceType = "com.victronenergy.grid"
        self.serviceName = self.serviceType + ".esESS.Shelly3EMGrid_" + str(self.vrmInstanceID)
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection())
        self.publishServiceMessage(self, "Initializing dbus-service")
        
        #Mgmt-Infos
        self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "dbus")

        # Create the mandatory objects
        self.dbusService.add_path('/ProductId', 45069)
        self.dbusService.add_path('/DeviceType', 345) 
        self.dbusService.add_path('/Role', "grid")
        self.dbusService.add_path('/Position', 0) 
        self.dbusService.add_path('/ProductName', "{0} Shelly3EMGrid".format(Globals.esEssTag)) 
        self.dbusService.add_path('/Latency', None)    
        self.dbusService.add_path('/FirmwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/HardwareVersion', Globals.currentVersionString)
        self.dbusService.add_path('/Connected', 1)
        self.dbusService.add_path('/Serial', "1337")
        self.dbusService.add_path('/CustomName', self.customName)

        #grid props
        self.dbusService.add_path('/Ac/Power', None)
        self.dbusService.add_path('/Ac/L1/Voltage', None)
        self.dbusService.add_path('/Ac/L2/Voltage', None)
        self.dbusService.add_path('/Ac/L3/Voltage', None)
        self.dbusService.add_path('/Ac/L1/Current', None)
        self.dbusService.add_path('/Ac/L2/Current', None)
        self.dbusService.add_path('/Ac/L3/Current', None)
        self.dbusService.add_path('/Ac/L1/Power', None)
        self.dbusService.add_path('/Ac/L2/Power', None)
        self.dbusService.add_path('/Ac/L3/Power', None)
        self.dbusService.add_path('/Ac/L1/Energy/Forward', None)
        self.dbusService.add_path('/Ac/L2/Energy/Forward', None)
        self.dbusService.add_path('/Ac/L3/Energy/Forward', None)
        self.dbusService.add_path('/Ac/L1/Energy/Reverse', None)
        self.dbusService.add_path('/Ac/L2/Energy/Reverse', None)
        self.dbusService.add_path('/Ac/L3/Energy/Reverse', None)
        self.dbusService.add_path('/Ac/Energy/Forward', None)
        self.dbusService.add_path('/Ac/Energy/Reverse', None)

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
            URL = "http://%s:%s@%s/status" % (self.shellyUsername, self.shellyPassword, self.shellyHost)
            URL = URL.replace(":@", "")
            #d(self, "Polling: " + URL)

            meter_r = requests.get(url = URL, timeout=(self.pollFrequencyMs/1000))
            meter_data = meter_r.json()     
        
            # check for Json
            if not meter_data:
                e(self, "Shelly response is not resolvable to JSON.")
                
            if (meter_data):
                self.dbusService['/Connected'] = 1
                self.connectionErrors = 0

                #All good, evaluate and publish on dbus. 
                self.dbusService['/Ac/Power'] = meter_data['total_power']
                self.dbusService['/Ac/L1/Voltage'] = meter_data['emeters'][0]['voltage']
                self.dbusService['/Ac/L2/Voltage'] = meter_data['emeters'][1]['voltage']
                self.dbusService['/Ac/L3/Voltage'] = meter_data['emeters'][2]['voltage']
                self.dbusService['/Ac/L1/Current'] = meter_data['emeters'][0]['current']
                self.dbusService['/Ac/L2/Current'] = meter_data['emeters'][1]['current']
                self.dbusService['/Ac/L3/Current'] = meter_data['emeters'][2]['current']
                self.dbusService['/Ac/L1/Power'] = meter_data['emeters'][0]['power']
                self.dbusService['/Ac/L2/Power'] = meter_data['emeters'][1]['power']
                self.dbusService['/Ac/L3/Power'] = meter_data['emeters'][2]['power']
                self.dbusService['/Ac/L1/Energy/Forward'] = (meter_data['emeters'][0]['total']/1000)
                self.dbusService['/Ac/L2/Energy/Forward'] = (meter_data['emeters'][1]['total']/1000)
                self.dbusService['/Ac/L3/Energy/Forward'] = (meter_data['emeters'][2]['total']/1000)
                self.dbusService['/Ac/L1/Energy/Reverse'] = (meter_data['emeters'][0]['total_returned']/1000) 
                self.dbusService['/Ac/L2/Energy/Reverse'] = (meter_data['emeters'][1]['total_returned']/1000) 
                self.dbusService['/Ac/L3/Energy/Reverse'] = (meter_data['emeters'][2]['total_returned']/1000) 

                self.dbusService['/Ac/Energy/Forward'] = (meter_data['emeters'][0]['total']/1000) + (meter_data['emeters'][1]['total']/1000) + (meter_data['emeters'][2]['total']/1000)
                self.dbusService['/Ac/Energy/Reverse'] = (meter_data['emeters'][0]['total_returned']/1000) + (meter_data['emeters'][1]['total_returned']/1000) + (meter_data['emeters'][2]['total_returned']/1000)
            else:
                #publish null values, so it is clear, that we have issues reading the meter and OS can decide how to handle. 
                self.publishNone()

        except Exception as ex:
            w(self, "Shelly 3EM did not response fast enough to sustain a poll frequency of {1} ms. Please adjust. After 3 failures, null will be published.".format(self.pollFrequencyMs))
            self.connectionErrors += 1
            #c(self, "Exception", exc_info=ex)

            if (self.connectionErrors > 3):
                e(self, "More than 3 consecutive timeouts. Assuming Meter disconnected.")
                self.publishNone()
    
    def publishNone(self):
        self.dbusService["/Connected"] = 0
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


