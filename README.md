# es-ESS
es-ESS (equinox solutions Energy Storage Systems) is an extension for Victrons VenusOS running on GX-Devices.
es-ESS brings various functions starting with tiny helpers, but also including major functionalities.

es-ESS is structered in individual modules and every module can be enabled or disabled independent. So, only certain
features can be enabled, based on your needs.

### Table of Contents
- [Setup](#setup) - General setup progress and requirements for es-ESS
- [ChargeCurrentReducer](#chargecurrentreducer) - Reduce the battery charge current to your *feel-well-value* without the need to disable DC-Feedin.
- [FroniusWattPilot](#froniuswattpilot) - Full integration of Fronius Wattpilot in VRM / cerbo, including bidirectional remote control and improved eco mode.
- [MqttToEVSoc](#mqtttoevsoc) - Tiny helper to read your EV SoC from any mqtt server and insert a Fake-BMS on cerbo / VRM.
- [NoBatToEV](#nobattoev) - Avoid usage of your home-battery when charging your ev with an `ac-out` connected wallbox.
- [PVOverheadDistributor](#pvoverheaddistributor) - Utility to manage and distribute available Solar Overhead between various consumers. (For Power-Users)
- [TimeToGoCalculator](#timetogocalculator) - Tiny helper filling out the `Time to Go` field in VRM, when BMS do not report this value.  

# Setup
Your system needs to match the following requirements in order to use es-ESS
- Be an ESS
- Have the local Mqtt enabled (plain or tls)

# ChargeCurrentReducer
TODO

# FroniusWattPilot
TODO

# MqttToEVSoc
TODO

# NoBatToEV
TODO

# PVOverheadDistributor
TODO

# TimeToGoCalculator

<img align="right" src="https://github.com/realdognose/es-ESS/blob/main/img/TimeToGo.png"> 

#### Overview



Some BMS - say the majority of them - don't provide values for the `Time to go`-Value visible in VRM. This is an important figure when looking at a dashboard. This helper script 
fills that gap and calculates the time, when BMS don't. Calculation is done in both directions: 

- **When discharging**: Time based on current discharge rate until the active SoC Limit is reached.
- **When charging**: Time based on current charge rate until 100% SoC is reached. 





#### Configuration

TimeToGoCalculator requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Default]    | VRMPortalID |  Your portal id to access values on mqtt / dbus |String | VRM0815 |
| [Default]  | BatteryCapacityInWh  | Your batteries capacity in Wh.  | Integer| 28000 |
| [Modules]    | TimeToGoCalculator | Flag, if the module should be enabled or not | Boolean | true |
| [TimeToGoCalculator]  | UpdateInterval |  Time in milli seconds for TimeToGo Calculations. Sometimes the BMS are sending `null` values, so a small value helps to reduce flickering on VRM. But don't exagerate for looking at the dashboard for 10 minutes a day ;-)| Integer  | 1000 |



