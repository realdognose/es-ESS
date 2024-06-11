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
from Helper import i, c, d, w, e

class ChargeCurrentReducer:
  def __init__(self):
    try:
      self.config = Globals.getConfig()

      # add _update function 'timer'
      gobject.timeout_add(2500, self._update)
      i(self, "ChargeCurrentReducer initialized.")
      Globals.publishServiceMessage(self, Globals.ServiceMessageType.Operational, "{0} initialized.".format(self.__class__.__name__))
    except Exception as e:
      c("TimeToGoCalculator", "Exception catched", exc_info=e)

  def _update(self):
    try:
      iDC = Globals.DbusWrapper.system.Dc.Battery.Current
      soc = Globals.DbusWrapper.system.Dc.Battery.Soc
      pGrid = Globals.DbusWrapper.ttys4.Ac.ActiveIn.L1.P + Globals.DbusWrapper.ttys4.Ac.ActiveIn.L2.P +Globals.DbusWrapper.ttys4.Ac.ActiveIn.L3.P 
      uGrid = (Globals.DbusWrapper.ttys4.Ac.ActiveIn.L1.V + Globals.DbusWrapper.ttys4.Ac.ActiveIn.L2.V +Globals.DbusWrapper.ttys4.Ac.ActiveIn.L3.V) / 3
      uDC = Globals.DbusWrapper.system.Dc.Battery.Voltage

      limitEquationRaw = self.config["ChargeCurrentReducer"]["DesiredChargeAmps"]
      defaultPowerSetPoint = float(self.config["ChargeCurrentReducer"]["DefaultPowerSetPoint"])
      factor = float(self.config["ChargeCurrentReducer"]["AdjustmentAggressivity"])
      limitEquation = limitEquationRaw.replace("SOC", str(soc))
      
      try:
        desiredChargeAmps = eval(limitEquation)
      except NameError as ex:
          e(self,"Error evaluation MinBatteryCharge-Equation. Not touching anything :-(")
          Globals.publishServiceMessage(self, Globals.ServiceMessageType.Error, "Error evaluation MinBatteryCharge-Equation. Check formula for valid python syntax.", limitEquationRaw)
          #TODO: Ensure Default Setpoint.
          return

      if (desiredChargeAmps < 0):
         w(self, "Desired ChargeAmps is negative... Not touching anything ;-)")
         Globals.publishServiceMessage(self, Globals.ServiceMessageType.Error, "Error evaluation MinBatteryCharge-Equation. Negative Result. Check formula for logic.", limitEquationRaw)
         #TODO: Ensure Default Setpoint.
         return

      iDrainDC = iDC - desiredChargeAmps
      pDrainDC = iDrainDC * uDC
      acDcEfficency = 0.97
      pDrainAC = pDrainDC * acDcEfficency
      iDrainAC = pDrainAC / uGrid

      d(self, "----------------")
      d(self, "Limit equation is: {0} and with a SoC of {1} that results in a desiredChargeCurrent of {2}A".format(limitEquationRaw, soc, desiredChargeAmps))
      d(self, "Current charge current is {0}A.".format(iDC))
      d(self, "We want a reduction by {0} Amp on the DC Side ({1}V) - that's {2}W (DC-Side))".format(iDrainDC, uDC, pDrainDC))
      d(self, "We want a reduction by {0} Amp on the AC Side ({1}V) - that's {2}W (AC-Side))".format(iDrainAC, uGrid, pDrainAC))
      newpDrainAc = pDrainAC * factor
      d(self, "Smoothness Factor is {0}, so changing feedin by {1}W".format(factor, newpDrainAc))
      newSetPoint = (pGrid - pDrainAC)
      d(self, "Current feedin is {0}W, we want {1}W, but not charging from grid.".format(pGrid, newSetPoint))
      newSetPoint = min(newSetPoint, defaultPowerSetPoint)
      d(self, "So, Final setpoint (after logic checks): {0}W".format(newSetPoint))
        
      Globals.localMqttClient.publish("W/c0619ab4a585/settings/0/Settings/CGwacs/AcPowerSetPoint", "{\"value\": " + str(newSetPoint) + "}", 0, False)

    except Exception as ex:
      c(self, "Exception catched", exc_info=ex)
      
    return True
