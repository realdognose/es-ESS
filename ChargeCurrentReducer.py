import configparser
import os
import paho.mqtt.client as mqtt # type: ignore
import sys
if sys.version_info.major == 2:
    import gobject # type: ignore
else:
    from gi.repository import GLib as gobject # type: ignore

#esEss imports
import Globals
from Globals import getFromGlobalStoreValue
from Helper import i, c, d, w, e
from DBus import DbusC

class ChargeCurrentReducer:
  def __init__(self):
    try:
      self.config = Globals.getConfig()

      # add _update function 'timer'
      gobject.timeout_add(5000, self._update)
      i(self, "ChargeCurrentReducer initialized.")
    except Exception as e:
      c("TimeToGoCalculator", "Exception catched", exc_info=e)

  def _update(self):
    try:
      iDC = Globals.DbusWrapper.system.Dc.Battery.Current
      soc = Globals.DbusWrapper.system.Dc.Battery.Soc
      powerSetpoint = Globals.DbusWrapper.Settings.CGwacs.AcPowerSetPoint
      pGrid = Globals.DbusWrapper.ttys4.Ac.ActiveIn.L1.P + Globals.DbusWrapper.ttys4.Ac.ActiveIn.L2.P +Globals.DbusWrapper.ttys4.Ac.ActiveIn.L3.P 
      uGrid = (Globals.DbusWrapper.ttys4.Ac.ActiveIn.L1.V + Globals.DbusWrapper.ttys4.Ac.ActiveIn.L2.V +Globals.DbusWrapper.ttys4.Ac.ActiveIn.L3.V) / 3
      uDC = Globals.DbusWrapper.system.Dc.Battery.Voltage
      acConsumption = Globals.DbusWrapper.system.Ac.Consumption.L1.Power + Globals.DbusWrapper.system.Ac.Consumption.L2.Power + Globals.DbusWrapper.system.Ac.Consumption.L3.Power
      acPV = Globals.DbusWrapper.system.Ac.PvOnOutput.L1.Power + Globals.DbusWrapper.system.Ac.PvOnOutput.L3.Power + Globals.DbusWrapper.system.Ac.PvOnOutput.L3.Power
      #TODO: PV ON AC needs to be considered as well.

      limitEquationRaw = self.config["ChargeCurrentReducer"]["DesiredChargeAmps"]
      defaultPowerSetPoint = float(self.config["ChargeCurrentReducer"]["DefaultPowerSetPoint"])
      limitEquation = limitEquationRaw.replace("SOC", str(soc))
      
      try:
        desiredChargeAmps = eval(limitEquation)
      except Exception as ex:
          e(self,"Error evaluation MinBatteryCharge-Equation. Not touching anything :-(")
          #TODO: Ensure Default Setpoint.
          return

      if (desiredChargeAmps < 0):
         w(self, "Desired ChargeAmps is negative... Not touching anything ;-)")
         #TODO: Ensure Default Setpoint.
         return

      iDrainDC = max(0, iDC - desiredChargeAmps)
      pDrainDC = iDrainDC * uDC
      acDcEfficency = 0.97
      pDrainAC = pDrainDC * acDcEfficency
      iDrainAC = pDrainAC / uGrid

      d(self, "----------------")
      d(self, "Limit equation is: {0} and with a SoC of {1} that results in a desiredChargeCurrent of {2}A".format(limitEquationRaw, soc, desiredChargeAmps))
      d(self, "Current charge current is {0}A and grid is: {1}".format(iDC, pGrid))
      d(self, "We want a reduction by {0} Amp on the DC Side ({1}V) - that's {2}W (DC-Side))".format(iDrainDC, uDC, pDrainDC))
      d(self, "We want a reduction by {0} Amp on the AC Side ({1}V) - that's {2}W (AC-Side))".format(iDrainAC, uGrid, pDrainAC))
      pDrainAC -= acConsumption
      d(self, "But we have {0}W consumption - so reduction shall be {1}W!".format(acConsumption, pDrainAC))
      pDrainAC += acPV
      d(self, "But we have {0}W PV on Output - so reduction shall be {1}W!".format(acPV, pDrainAC))
      
      newSetPoint = defaultPowerSetPoint

      newSetPoint = (powerSetpoint - pDrainAC) / 2
      d(self, "Current setpoint is {0}W, so we meet in the middle :0) - New Setpoint: {1}W".format(powerSetpoint, newSetPoint))
      newSetPoint = min(newSetPoint, defaultPowerSetPoint)
        
      
      #Globals.mqttClient.publish("W/c0619ab4a585/settings/0/Settings/CGwacs/AcPowerSetPoint", "{\"value\": " + str(newSetPoint) + "}", 0, False)

    except Exception as e:
      c(self, "Exception catched", exc_info=e)
      
    return True
