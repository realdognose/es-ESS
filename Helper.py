import logging
from builtins import round, str
import sys
import os
import inspect
import threading
from time import sleep

# victron
sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService # type: ignore
import dbus # type: ignore

#es-ESS
import Globals

# Helper defs for logging
logBlackList = []

def i(module, msg, **kwargs):
   if (not isinstance(module, str)):
       module = module.__class__.__name__
   
   func = inspect.currentframe().f_back.f_code
   lineIdentifier = "{0}.{1}".format(module, func.co_name)

   if (lineIdentifier not in logBlackList):
     lineIdentifier = "{0}|{1}".format(threading.currentThread().getName(), lineIdentifier)
     logging.info("[" + lineIdentifier + "] " + msg, **kwargs)

def d(module, msg, **kwargs):
   if (not isinstance(module, str)):
       module = module.__class__.__name__

   func = inspect.currentframe().f_back.f_code
   lineIdentifier = "{0}.{1}".format(module, func.co_name)

   if (lineIdentifier not in logBlackList):
     lineIdentifier = "{0}|{1}".format(threading.currentThread().getName(), lineIdentifier)
     logging.debug("[" + lineIdentifier + "] " + msg, **kwargs)

def w(module, msg, **kwargs):
   if (not isinstance(module, str)):
       module = module.__class__.__name__

   func = inspect.currentframe().f_back.f_code
   lineIdentifier = "{0}|{1}.{2}".format(threading.currentThread().getName(), module, func.co_name)

   Globals.esESS.publishServiceMessage(module, Globals.ServiceMessageType.Warning, "[" + lineIdentifier + "] " + msg)

   logging.warning("[" + lineIdentifier + "] " + msg, **kwargs)

def e(module, msg, **kwargs):
   if (not isinstance(module, str)):
       module = module.__class__.__name__

   func = inspect.currentframe().f_back.f_code
   lineIdentifier = "{0}|{1}.{2}".format(threading.currentThread().getName(), module, func.co_name)

   Globals.esESS.publishServiceMessage(module, Globals.ServiceMessageType.Error, "[" + lineIdentifier + "] " + msg)

   logging.error("[" + lineIdentifier + "] " + msg, **kwargs)

def c(module, msg, **kwargs):
   if (not isinstance(module, str)):
       module = module.__class__.__name__

   func = inspect.currentframe().f_back.f_code
   lineIdentifier = "{0}|{1}.{2}".format(threading.currentThread().getName(), module, func.co_name)

   Globals.esESS.publishServiceMessage(module, Globals.ServiceMessageType.Critical, "[" + lineIdentifier + "] " + msg)

   logging.critical("[" + lineIdentifier + "] " + msg, **kwargs)

#Helper defs for DBus
class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)

class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)
    
def dbusConnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()

#Helper defs for Formats
#formats 
_format_kwh = lambda p, v: (str(round(v, 2)) + ' kWh')
_format_aampere = lambda p, v: (str(round(v, 1)) + ' A')
_format_watt = lambda p, v: (str(round(v, 1)) + ' W')
_format_voltage = lambda p, v: (str(round(v, 1)) + ' V')   
_format_plain = lambda p, v: (str(v))
_format_temp = lambda p, v: (str(round(v, 1)) + ' °C')   

def formatCallback(callback):
    return "[{0}]".format(callback.__qualname__ ) if callback is not None else None


#Frequently usefull stuff
def waitTimeout(lambdaE, timeout):
    t = 0
    within_timeout = True
    while not lambdaE() and t < timeout:
        sleep(1)
        t += 1
    if t >= timeout:
        within_timeout = False
    return within_timeout
