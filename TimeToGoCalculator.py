
#esEss imports
import Globals
from Helper import i, c, d, w, e, t
from esESSService import esESSService

class TimeToGoCalculator(esESSService):
    def __init__(self):
        esESSService.__init__(self)
        self.capacity   = float(self.config["Common"]["BatteryCapacityInWh"])

    def initDbusService(self):
        pass
    
    def initDbusSubscriptions(self):
        self.powerDbus      = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Power")
        self.socDbus        = self.registerDbusSubscription("com.victronenergy.system", "/Dc/Battery/Soc")
        self.socLimitDbus   = self.registerDbusSubscription("com.victronenergy.system", "/Control/ActiveSocLimit")

    def initMqttSubscriptions(self):
        pass

    def initWorkerThreads(self):
        self.registerWorkerThread(self.updateTimeToGo, int(self.config["TimeToGoCalculator"]["UpdateInterval"]))

    def initFinalize(self):
        pass

    def updateTimeToGo(self):
      try:
        
        power     = self.powerDbus.value
        soc       = self.socDbus.value
        socLimit  = self.socLimitDbus.value
        
        t(self, "{0} / {1} / {2}".format(power, soc, socLimit))

        if (soc == 0):
          w(self, "SoC value of 0 reported. Can't compute time2go.")
          return

        remainingCapacity = (socLimit/100.0) * self.capacity
        missingCapacity = (1 - soc/100.0) * self.capacity  
        currentCapacity = (soc/100.0) * self.capacity
        usableCapacity = currentCapacity - remainingCapacity
        
        t(self, "Capacity: {0}, RemCap: {1}, MisCap: {2}, CurCap: {3}, UsCap: {4}".format(self.capacity, remainingCapacity, missingCapacity, currentCapacity, usableCapacity))

        remaining = None
        if (power < 0):
          remaining = (usableCapacity / power) * 60 * 60 * -1
        elif (power > 0):
          remaining = (missingCapacity / power) * 60 * 60

        #d(self, "=> TimeToGo (s): {0}s".format(remaining))
        
        #Inject calculated value to dbus. 
        if (remaining is not None):
          #TODO: Figure out why dbus publishing is not working :( )
          #self.timeToGoDbus.publish(int(remaining))

          self.publishLocalMqtt("N/{0}/system/0/Dc/Battery/TimeToGo".format(self.config["Common"]["VRMPortalID"]), "{\"value\": " + str(int(remaining)) + "}")
          self.publishMainMqtt("{0}/{1}/TimeToGo".format(Globals.esEssTag, self.__class__.__name__), int(remaining))

      except Exception as e:
        c("TimeToGoCalculator", "Exception catched", exc_info=e)
      
      return True
    
    def handleSigterm(self):
       pass
