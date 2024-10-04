import os
import platform
import sys
from typing import Dict
import dbus # type: ignore
import dbus.service # type: ignore
import inspect
import pprint
from time import time
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
        self.metering = self.config["Shelly3EMGrid"]["Metering"]
        self.connectionErrors = 0
        self.energyForwarded = 0
        self.energyReversed = 0
        self.lastMeasurement = time()

        if (self.metering == "Net"):
            #load stored counters, if any. 

            if os.path.isfile("{0}/runtimeData/energyForwarded3EM".format(os.path.dirname(os.path.realpath(__file__)))):
                with open("{0}/runtimeData/energyForwarded3EM".format(os.path.dirname(os.path.realpath(__file__))), 'r') as cfile:
                    self.energyForwarded = float(cfile.read().strip())
                    i(self, "Read stored counter energyForwarded={0}".format(self.energyForwarded))
                
            if os.path.isfile("{0}/runtimeData/energyReversed3EM".format(os.path.dirname(os.path.realpath(__file__)))):    
                with open("{0}/runtimeData/energyReversed3EM".format(os.path.dirname(os.path.realpath(__file__))), 'r') as cfile:
                    self.energyReversed = float(cfile.read().strip())
                    i(self, "Read stored counter energyReversed={0}".format(self.energyReversed))

    def initDbusService(self):
        self.serviceType = "com.victronenergy.grid"
        self.serviceName = self.serviceType + "." + Globals.esEssTagService + "_Shelly3EMGrid"
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection(), register=False)
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

        self.dbusService.register()

    def initDbusSubscriptions(self):
        pass
        
    def initWorkerThreads(self):
        self.registerWorkerThread(self.queryShelly, self.pollFrequencyMs)

        if (self.metering == "Net"):
            self.registerWorkerThread(self.persistCounters, 5 * 60 * 1000);

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       self.persistCounters()

    def queryShelly(self):
        try:
            URL = "http://%s:%s@%s/status" % (self.shellyUsername, self.shellyPassword, self.shellyHost)
            URL = URL.replace(":@", "")
            
            #timeout should be half the poll frequency, so there is time to process.
            meter_r = requests.get(url = URL, timeout=(self.pollFrequencyMs/2000))
            meter_data = meter_r.json()     
        
            # check for Json
            if not meter_data:
                e(self, "Shelly response is not resolvable to JSON.")
                
            if (meter_data):
                self.dbusService['/Connected'] = 1
                self.connectionErrors = 0

                #TODO: Remove after debugging Fake feedin on Phase 2: 
                meter_data['emeters'][1]['power'] -= 300
                meter_data['total_power'] -= 300

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

                if (self.metering == "Default"):
                    self.dbusService['/Ac/L1/Energy/Forward'] = (meter_data['emeters'][0]['total']/1000)
                    self.dbusService['/Ac/L2/Energy/Forward'] = (meter_data['emeters'][1]['total']/1000)
                    self.dbusService['/Ac/L3/Energy/Forward'] = (meter_data['emeters'][2]['total']/1000)
                    self.dbusService['/Ac/L1/Energy/Reverse'] = (meter_data['emeters'][0]['total_returned']/1000) 
                    self.dbusService['/Ac/L2/Energy/Reverse'] = (meter_data['emeters'][1]['total_returned']/1000) 
                    self.dbusService['/Ac/L3/Energy/Reverse'] = (meter_data['emeters'][2]['total_returned']/1000) 

                    self.dbusService['/Ac/Energy/Forward'] = (meter_data['emeters'][0]['total']/1000.0) + (meter_data['emeters'][1]['total']/1000.0) + (meter_data['emeters'][2]['total']/1000.0)
                    self.dbusService['/Ac/Energy/Reverse'] = (meter_data['emeters'][0]['total_returned']/1000.0) + (meter_data['emeters'][1]['total_returned']/1000.0) + (meter_data['emeters'][2]['total_returned']/1000.0)
                else:
                    #Net metering. We use our own counters and keep track of correct saldating. 
                    now = time()
                    duration = (now - self.lastMeasurement) * 1000.0
                    self.lastMeasurement = now

                    if (meter_data['total_power'] >=0):
                        #Consumption
                        self.energyForwarded += meter_data['total_power'] * (duration/(3600.0*1000.0))
                    else:
                        #FeedIn
                        self.energyReversed += (meter_data['total_power'] * -1) * (duration/(3600.0*1000.0))

                    self.dbusService['/Ac/L1/Energy/Forward'] = None
                    self.dbusService['/Ac/L2/Energy/Forward'] = None
                    self.dbusService['/Ac/L3/Energy/Forward'] = None
                    self.dbusService['/Ac/L1/Energy/Reverse'] = None
                    self.dbusService['/Ac/L2/Energy/Reverse'] = None
                    self.dbusService['/Ac/L3/Energy/Reverse'] = None

                    self.dbusService['/Ac/Energy/Forward'] = round(self.energyForwarded / 1000.0, 2)
                    self.dbusService['/Ac/Energy/Reverse'] = round(self.energyReversed / 1000.0, 2)

                    d(self, "Duration: {dur} -> Counters: F/R: {f}/{r}".format(f=self.energyForwarded, r=self.energyReversed, dur=duration))
            else:
                #publish null values, so it is clear, that we have issues reading the meter and OS can decide how to handle. 
                self.publishNone()

        except requests.exceptions.Timeout as ex:
            w(self, "Shelly 3EM did not response fast enough to sustain a poll frequency of {0} ms. Please adjust. After 3 failures, null will be published.".format(self.pollFrequencyMs))
            self.connectionErrors += 1
            #

            if (self.connectionErrors > 3):
                e(self, "More than 3 consecutive timeouts. Assuming Meter disconnected.")
                self.publishNone()
        
        except Exception as ex:
            c(self, "Exception", exc_info=ex)
    
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

    def persistCounters(self):
        i(self, "Saving energy counters to disk. F/R: {0}/{1}".format(self.energyForwarded, self.energyReversed))

        with open("{0}/runtimeData/energyForwarded3EM".format(os.path.dirname(os.path.realpath(__file__))), 'w+') as cfile:
            cfile.write(str(self.energyForwarded))
            
        with open("{0}/runtimeData/energyReversed3EM".format(os.path.dirname(os.path.realpath(__file__))), 'w+') as cfile:
            cfile.write(str(self.energyReversed))




