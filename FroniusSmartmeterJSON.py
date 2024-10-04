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

class FroniusSmartmeterJSON(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.vrmInstanceID = self.config["FroniusSmartmeterJSON"]["VRMInstanceID"]
        self.customName = self.config["FroniusSmartmeterJSON"]["CustomName"]
        self.pollFrequencyMs = int(self.config["FroniusSmartmeterJSON"]["PollFrequencyMs"])
        self.meterHost = self.config["FroniusSmartmeterJSON"]["Host"]
        self.meterID = self.config["FroniusSmartmeterJSON"]["MeterID"]
        self.connectionErrors = 0

    def initDbusService(self):
        self.serviceType = "com.victronenergy.grid"
        self.serviceName = self.serviceType + "." + Globals.esEssTagService + "_FroniusSmartmeterJSON"
        self.dbusService = VeDbusService(self.serviceName, bus=dbusConnection(), register=False)
        self.publishServiceMessage(self, "Initializing dbus-service")
        
        #Mgmt-Infos
        self.dbusService.add_path('/DeviceInstance', int(self.vrmInstanceID))
        self.dbusService.add_path('/Mgmt/ProcessName', __file__)
        self.dbusService.add_path('/Mgmt/ProcessVersion', Globals.currentVersionString + ' on Python ' + platform.python_version())
        self.dbusService.add_path('/Mgmt/Connection', "JSON-API via " + self.meterHost)

        # Create the mandatory objects
        self.dbusService.add_path('/ProductId', 45069)
        self.dbusService.add_path('/DeviceType', 345) 
        self.dbusService.add_path('/Role', "grid")
        self.dbusService.add_path('/Position', 0) 
        self.dbusService.add_path('/ProductName', "{0} FroniusSmartmeterJSON".format(Globals.esEssTag)) 
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
        self.dbusService.add_path('/Ac/L1/PowerFactor', None)
        self.dbusService.add_path('/Ac/L2/PowerFactor', None)
        self.dbusService.add_path('/Ac/L3/PowerFactor', None)
        self.dbusService.add_path('/Ac/Energy/Forward', None)
        self.dbusService.add_path('/Ac/Energy/Reverse', None)
        self.dbusService.add_path('/Ac/Voltage12', None)
        self.dbusService.add_path('/Ac/Voltage23', None)
        self.dbusService.add_path('/Ac/Voltage31', None)

        self.dbusService.register()

    def initDbusSubscriptions(self):
        pass
        
    def initWorkerThreads(self):
        self.registerWorkerThread(self.queryMeter, self.pollFrequencyMs)

    def initMqttSubscriptions(self):
        pass

    def initFinalize(self):
        pass
    
    def handleSigterm(self):
       i(self, "Setting meter to disconnected due to sigterm.")
       self.publishNone()

    def queryMeter(self):
        try:
            URL = "http://%s/solar_api/v1/GetMeterRealtimeData.cgi?Scope=Device&DeviceId=%s&DataCollection=MeterRealtimeData" % (self.meterHost, self.meterID)
        
            #timeout should be half the poll frequency, so there is time to process.
            meter_r = requests.get(url = URL, timeout=(self.pollFrequencyMs/2000))
            meter_data = meter_r.json()     
        
            # check for Json
            if not meter_data:
                e(self, "Response is not resolvable to JSON.")
                self.connError()
                
            if (meter_data and meter_data['Body']['Data']['Enable']==1):
                self.dbusService['/Connected'] = 1
                self.connectionErrors = 0

                #All good, evaluate and publish on dbus. 
                self.dbusService['/Ac/L1/Voltage'] = round(meter_data['Body']['Data']['Voltage_AC_Phase_1'], 4)
                self.dbusService['/Ac/L2/Voltage'] = round(meter_data['Body']['Data']['Voltage_AC_Phase_2'], 4)
                self.dbusService['/Ac/L3/Voltage'] = round(meter_data['Body']['Data']['Voltage_AC_Phase_3'], 4)
                
                self.dbusService['/Ac/L1/Current'] = round(meter_data['Body']['Data']['Current_AC_Phase_1'], 4)
                self.dbusService['/Ac/L2/Current'] = round(meter_data['Body']['Data']['Current_AC_Phase_2'], 4)
                self.dbusService['/Ac/L3/Current'] = round(meter_data['Body']['Data']['Current_AC_Phase_3'], 4)

                self.dbusService['/Ac/L1/PowerFactor'] = round(meter_data['Body']['Data']['PowerFactor_Phase_1'], 4)
                self.dbusService['/Ac/L2/PowerFactor'] = round(meter_data['Body']['Data']['PowerFactor_Phase_2'], 4)
                self.dbusService['/Ac/L3/PowerFactor'] = round(meter_data['Body']['Data']['PowerFactor_Phase_3'], 4)
                
                self.dbusService['/Ac/L1/Power'] = round(meter_data['Body']['Data']['PowerReal_P_Phase_1'], 4)
                self.dbusService['/Ac/L2/Power'] = round(meter_data['Body']['Data']['PowerReal_P_Phase_2'], 4)
                self.dbusService['/Ac/L3/Power'] = round(meter_data['Body']['Data']['PowerReal_P_Phase_3'], 4)
                self.dbusService['/Ac/Power'] = round(meter_data['Body']['Data']['PowerReal_P_Phase_1'] + meter_data['Body']['Data']['PowerReal_P_Phase_2'] + meter_data['Body']['Data']['PowerReal_P_Phase_3'], 4)

                self.dbusService['/Ac/Voltage12'] = round(meter_data['Body']['Data']['Voltage_AC_PhaseToPhase_12'], 4)
                self.dbusService['/Ac/Voltage23'] = round(meter_data['Body']['Data']['Voltage_AC_PhaseToPhase_23'], 4)
                self.dbusService['/Ac/Voltage31'] = round(meter_data['Body']['Data']['Voltage_AC_PhaseToPhase_31'], 4)

                self.dbusService['/Ac/Energy/Forward'] = round(meter_data['Body']['Data']['EnergyReal_WAC_Sum_Consumed'], 4)/1000
                self.dbusService['/Ac/Energy/Reverse'] = round(meter_data['Body']['Data']['EnergyReal_WAC_Sum_Produced'], 4)/1000
            else:
                #publish null values, so it is clear, that we have issues reading the meter and OS can decide how to handle. 
                w(self, "Can't query meter. data object not readable.")
                self.connError()

        except requests.exceptions.Timeout as ex:
            w(self, "Fronius Inverter did not response fast enough to sustain a poll frequency of {0} ms. Please adjust.".format(self.pollFrequencyMs))
            self.connError()

        except Exception as ex:
            c(self, "Exception", exc_info=ex)
            
    def connError(self):
        self.connectionErrors += 1

        if (self.connectionErrors >= 10):
            if (self.connectionErrors % 10 == 0):
                e(self, "Reading meter failed for {0} consecutive tries. Assuming Meter disconnected.".format(self.connectionErrors))
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
        self.dbusService['/Ac/L1/PowerFactor'] = None
        self.dbusService['/Ac/L2/PowerFactor'] = None
        self.dbusService['/Ac/L3/PowerFactor'] = None
        self.dbusService['/Ac/Voltage12'] = None
        self.dbusService['/Ac/Voltage23'] = None
        self.dbusService['/Ac/Voltage31'] = None


