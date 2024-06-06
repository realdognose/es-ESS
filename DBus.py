
import configparser
import json
import os
import sys
import threading
import dbus # type: ignore
from dbus.mainloop.glib import DBusGMainLoop # type: ignore
from time import sleep
import paho.mqtt.client as mqtt # type: ignore
from Helper import i, c, d, w, e

# victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService,VeDbusItemExport, VeDbusItemImport # type: ignore

class DbusC:
    def __init__(self):
        try:
            DBusGMainLoop(set_as_default=True)
            #Connect to the sessionbus or SystemBus
            dbusConn = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()
            
            self.Settings = DbusC.SettingsC(dbusConn)
            self.system = DbusC.systemC(dbusConn)
            self.ttys4 = DbusC.ttys4C(dbusConn)
        except Exception as e:
            c(self, "Exception during dbus init", exc_info=e)
    
    class SettingsC:
        def __init__(self, dbusConn):
            self.CGwacs = DbusC.SettingsC.CGwacsC(dbusConn)

        class CGwacsC:
            def __init__(self, dbusConn):
                self._AcPowerSetPoint = VeDbusItemImport(dbusConn, 'com.victronenergy.settings', '/Settings/CGwacs/AcPowerSetPoint')    

            @property
            def AcPowerSetPoint(self): return float(self._AcPowerSetPoint.get_value())

    class systemC:
        def __init__(self, dbusConn):
            self.Ac = DbusC.systemC.AcC(dbusConn)
            self.Control = DbusC.systemC.ControlC(dbusConn)
            self.Dc = DbusC.systemC.DcC(dbusConn)
            
        class AcC:
            def __init__(self, dbusConn):
                self.Consumption = DbusC.systemC.AcC.ConsumptionC(dbusConn)
                self.PvOnOutput = DbusC.systemC.AcC.PvOnOutputC(dbusConn)

            class ConsumptionC:
                def __init__(self, dbusConn):
                    self.L1 = DbusC.systemC.AcC.ConsumptionC.L1C(dbusConn)
                    self.L2 = DbusC.systemC.AcC.ConsumptionC.L2C(dbusConn)
                    self.L3 = DbusC.systemC.AcC.ConsumptionC.L3C(dbusConn)

                class L1C:
                    def __init__(self, dbusConn):
                        self._Current = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/Consumption/L1/Current')   
                        self._Power = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/Consumption/L1/Power')   

                    @property
                    def Current(self): return float(self._Current.get_value()) 

                    @property
                    def Power(self): return float(self._Power.get_value()) 

                class L2C:
                    def __init__(self, dbusConn):
                        self._Current = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/Consumption/L2/Current')   
                        self._Power = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/Consumption/L2/Power')   

                    @property
                    def Current(self): return float(self._Current.get_value()) 

                    @property
                    def Power(self): return float(self._Power.get_value()) 

                class L3C:
                    def __init__(self, dbusConn):
                        self._Current = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/Consumption/L3/Current')   
                        self._Power = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/Consumption/L3/Power')   

                    @property
                    def Current(self): return float(self._Current.get_value()) 

                    @property
                    def Power(self): return float(self._Power.get_value()) 
            
            class PvOnOutputC:
                def __init__(self, dbusConn):
                    self.L1 = DbusC.systemC.AcC.PvOnOutputC.L1C(dbusConn)
                    self.L2 = DbusC.systemC.AcC.PvOnOutputC.L2C(dbusConn)
                    self.L3 = DbusC.systemC.AcC.PvOnOutputC.L3C(dbusConn)

                class L1C:
                    def __init__(self, dbusConn):
                        self._Current = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/PvOnOutput/L1/Current')   
                        self._Power = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/PvOnOutput/L1/Power')   

                    @property
                    def Current(self): return float(self._Current.get_value()) 

                    @property
                    def Power(self): return float(self._Power.get_value()) 

                class L2C:
                    def __init__(self, dbusConn):
                        self._Current = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/PvOnOutput/L2/Current')   
                        self._Power = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/PvOnOutput/L2/Power')   

                    @property
                    def Current(self): return float(self._Current.get_value()) 

                    @property
                    def Power(self): return float(self._Power.get_value()) 

                class L3C:
                    def __init__(self, dbusConn):
                        self._Current = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/PvOnOutput/L3/Current')   
                        self._Power = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Ac/PvOnOutput/L3/Power')   

                    @property
                    def Current(self): return float(self._Current.get_value()) 

                    @property
                    def Power(self): return float(self._Power.get_value()) 

        class ControlC:
                def __init__(self, dbusConn):
                    self. _ActiveSocLimit = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Control/ActiveSocLimit')    

                @property
                def ActiveSocLimit(self): return float(self._ActiveSocLimit.get_value())

        class DcC:
            def __init__(self, dbusConn):
                self.Battery = DbusC.systemC.DcC.BatteryC(dbusConn)

            class BatteryC:
                def __init__(self, dbusConn):
                    self._Current = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Dc/Battery/Current')                       
                    self._Power = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Dc/Battery/Power')    
                    self._Soc = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Dc/Battery/Soc')                       
                    self._Voltage = VeDbusItemImport(dbusConn, 'com.victronenergy.system', '/Dc/Battery/Voltage')                       

                @property
                def Current(self): return float(self._Current.get_value())                    

                @property
                def Power(self): return float(self._Power.get_value())
                
                @property
                def Soc(self): return float(self._Soc.get_value())

                @property
                def Voltage(self): return float(self._Voltage.get_value())

    class ttys4C:
        def __init__(self, dbusConn):
            self.Ac = DbusC.ttys4C.AcC(dbusConn)
        
        class AcC:
            def __init__(self, dbusConn):
                self.ActiveIn = DbusC.ttys4C.AcC.ActiveInC(dbusConn)

            class ActiveInC:
                def __init__(self, dbusConn):
                    self.L1 = DbusC.ttys4C.AcC.ActiveInC.L1C(dbusConn)
                    self.L2 = DbusC.ttys4C.AcC.ActiveInC.L2C(dbusConn)
                    self.L3 = DbusC.ttys4C.AcC.ActiveInC.L3C(dbusConn)

                class L1C:
                    def __init__(self, dbusConn):
                        self._F = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L1/F')   
                        self._I = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L1/I')    
                        self._P = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L1/P')  
                        self._S = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L1/S')   
                        self._V = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L1/V')   

                    @property
                    def F(self): return float(self._F.get_value()) 

                    @property
                    def I(self): return float(self._I.get_value()) 

                    @property
                    def P(self): return float(self._P.get_value()) 

                    @property
                    def S(self): return float(self._S.get_value()) 

                    @property
                    def V(self): return float(self._V.get_value()) 

                class L2C:
                    def __init__(self, dbusConn):
                        self._F = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L2/F')   
                        self._I = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L2/I')    
                        self._P = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L2/P')  
                        self._S = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L2/S')   
                        self._V = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L2/V')   

                    @property
                    def F(self): return float(self._F.get_value()) 

                    @property
                    def I(self): return float(self._I.get_value()) 

                    @property
                    def P(self): return float(self._P.get_value()) 

                    @property
                    def S(self): return float(self._S.get_value()) 

                    @property
                    def V(self): return float(self._V.get_value()) 

                class L3C:
                    def __init__(self, dbusConn):
                        self._F = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L3/F')   
                        self._I = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L3/I')    
                        self._P = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L3/P')  
                        self._S = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L3/S')   
                        self._V = VeDbusItemImport(dbusConn, 'com.victronenergy.vebus.ttyS4', '/Ac/ActiveIn/L3/V')   

                    @property
                    def F(self): return float(self._F.get_value()) 

                    @property
                    def I(self): return float(self._I.get_value()) 

                    @property
                    def P(self): return float(self._P.get_value()) 

                    @property
                    def S(self): return float(self._S.get_value()) 

                    @property
                    def V(self): return float(self._V.get_value()) 

    

                
    
    
    
    
    
    
    
    
    
    
    
    #VEBus Value imports
    #VeDb_R_system_0_Dc_Battery_Power = 
    #VeDb_R_system_0_Dc_Battery_Soc= VeDbusItemImport(dbusConn, 'com.victronenergy.system',  "/Dc/Battery/Soc")
    #VeDb_R_system_0_Control_ActiveSocLimit = VeDbusItemImport(dbusConn, 'com.victronenergy.system', "/Control/ActiveSocLimit"
#