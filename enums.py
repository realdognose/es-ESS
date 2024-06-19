# enums we use. 
from enum import Enum


class VrmEvChargerControlMode(Enum):
    Manual = 0
    Auto = 1
    Scheduled = 2

class VrmEvChargerStartStop(Enum):
    Stop = 0
    Start = 1

class VrmEvChargerStatus(Enum):
    Disconnected = 0
    Connected = 1
    Charging = 2
    Charged = 3
    WaitingForSun = 4
    WaitingForRFID = 5
    WaitingForStart = 6
    LowSOC = 7
    GroundTestError = 8
    WeldedContactsTestError = 9
    CPInputTestErrorShorted = 10
    ResidualCurrentDetected = 11
    UndervoltageDetected = 12
    OvervoltageDetected = 13
    OverheatingDetected = 14
    Reserved1 = 15
    Reserved2 = 16
    Reserved3 = 17
    Reserved4 = 18
    Reserved5 = 19
    ChargingLimit = 20
    StartCharging = 21
    SwitchingTo3Phase = 22
    SwitchingTo1Phase = 23
    StopCharging = 24

class WattpilotStartStop(Enum):
    Neutral = 0
    Off = 1
    On = 2

class WattpilotControlMode(Enum):
    Unkown0 = 0
    Unknown1 = 1
    Unknown2 = 2
    Default = 3
    ECO = 4
    NextTrip = 5

class WattpilotModelStatus(Enum):
    NotChargingBecauseNoChargeCtrlData=0
    NotChargingBecauseOvertemperature=1
    NotChargingBecauseAccessControlWait=2
    ChargingBecauseForceStateOn=3
    NotChargingBecauseForceStateOff=4
    NotChargingBecauseScheduler=5
    NotChargingBecauseEnergyLimit=6
    ChargingBecauseAwattarPriceLow=7
    ChargingBecauseAutomaticStopTestLadung=8
    ChargingBecauseAutomaticStopNotEnoughTime=9
    ChargingBecauseAutomaticStop=10
    ChargingBecauseAutomaticStopNoClock=11
    ChargingBecausePvSurplus=12
    ChargingBecauseFallbackGoEDefault=13
    ChargingBecauseFallbackGoEScheduler=14
    ChargingBecauseFallbackDefault=15
    NotChargingBecauseFallbackGoEAwattar=16
    NotChargingBecauseFallbackAwattar=17
    NotChargingBecauseFallbackAutomaticStop=18
    ChargingBecauseCarCompatibilityKeepAlive=19
    ChargingBecauseChargePauseNotAllowed=20
    UNKNOWN21=21
    NotChargingBecauseSimulateUnplugging=22
    NotChargingBecausePhaseSwitch=23
    NotChargingBecauseMinPauseDuration=24