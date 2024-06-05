# es-ESS
es-ESS (equinox solutions Energy Storage Systems) is an extension for Victrons VenusOS running on GX-Devices.
es-ESS brings various functions starting with tiny helpers, but also including major functionalities.

es-ESS is structered in individual modules and every module can be enabled or disabled independent. So, only certain
features can be enabled, based on your needs.

### Table of Contents
- [Setup](#setup) - General setup process and requirements for es-ESS
- [ChargeCurrentReducer](#chargecurrentreducer) - Reduce the battery charge current to your *feel-well-value* without the need to disable DC-Feedin.
- [FroniusWattPilot](#froniuswattpilot) - Full integration of Fronius Wattpilot in VRM / cerbo, including bidirectional remote control and improved eco mode.
- [MqttToEVSoc](#mqtttoevsoc) - Tiny helper to read your EV SoC from any mqtt server and insert a Fake-BMS on cerbo / VRM.
- [NoBatToEV](#nobattoev) - Avoid usage of your home-battery when charging your ev with an `ac-out` connected wallbox.
- [PVOverheadDistributor](#pvoverheaddistributor) - Utility to manage and distribute available Solar Overhead between various consumers.
  - [Scripted-PVOverheadConsumer](#scripted-pvoverheadconsumer) - Consumers managed by external scripts can to be more complex and join the Solar Overhead Pool.
  - [NPC-PVOverheadConsumer](#npc-pvoverheadconsumer) - Manage consumers on a simple on/off level, based on available overhead.
- [TimeToGoCalculator](#timetogocalculator) - Tiny helper filling out the `Time to Go` field in VRM, when BMS do not report this value.
- [F.A.Q](#faq) - Frequently Asked Questions

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
#### Overview
In a larger system, sometimes you need to manage multiple consumers based on solar overhead available. If every consumer is deciding on it's own, it can 
lead to a continious up and down on available energy, causing consumers to turn on/off in a uncontrolled , frequent fashion. 

To overcome this problem, the PVOverheadDistributor has been created. Each consumer can register itself, send a request containing certain parameters - and
PVOverheadDistributor will determine the total available overhead and calculate allowances for each individual consumer. 

Each consumer is represented as a Fake-BMS in VRM, so you can see immediately where your energy is currently going. 

> :warning: **Fake-BMS injection**:<br /> This feature is creating Fake-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

| Example View |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/PVOverheadConsumers%203.png"> |
| <div align="left">The example shows the view in VRM and presents the following information: <br /><br />- There is a mimimum battery charge reservation of 750W active and that reservation is currently beeing fullfilled with 248.5% <br />- The PVOverheadConsumer *PV-Heater* is requesting a total of 3501.0W, and due to the current allowance, 3318W currently beeing consumed, equaling 94.8% of it's request. <br />- The PVOverheadConsumer  *Waterplay* is requesting a total of 110W, and due to the current allowance, 110W currently beeing consumed, equaling 100% of it's request. <br />- The PVOverheadConsumer *Wattpilot* is requesting a total of 11308W, and due to the current allowance, 2254W currently beeing consumed, equaling 19.9% of it's request. </div>|

#### General functionality
The PVOverheadDistributer re-distributes values every minute. We have been running tests with more frequent updates, but it turned out, that the delay in processing a request/allownance by some consumers is cousing issues. 
Also, when consumption changes, the whole ESS itself needs to adapt, adjust battery-usage, grid-meter has to catch up, values have to be re-read and published in dbus and so on. 

### Usage
Each consumer is creating a PVOverhead-Request, which then will be accepted or not by the PVOverheadDistributor based on various parameters. The overall request is send to the venus mqtt inside the `W` Topic, 
where es-ESS will read the request and publish the processing result (including request data) in it's own topic. 

The request in total is made out of the following values, where some are mandatory, some optional, some to be not filled out by the consumer: 

*In this table, a consumerKey of `consumer1` has been used. Replace that with an unique identifier for your consumer*
each key has to be published in the topic `W/{VRMPortalID/esEss/PVOverheadDistributor/requests/consumer1`
| Mqtt-Key             | To be set by Consumer |  Descripion                                                             | Type          | Example Value| Required |
| -------------------- | ----------------------|------------------------------------------------------------------------ | ------------- |--------------| ---------|
|automatic             | yes                   | Flag, indicating if the consumer is currently in automatic mode         | Boolean       | true         | yes      |
|consumption           | yes                   | Current consumption of the consumer                                     | Double        | 1234.0       | yes      |
|customName            | yes                   | DisplayName on VRM                                                      | String        | My Consumer 1| yes      |
|ignoreBatReservation  | yes                   | Consumer shall be enabled despite active Battery Reservation            | Boolean       | true         | no       |
|request               | yes                   | Total power this consumer would ever need.                              | Double        | 8500.0       | yes      |
|stepSize              | yes                   | StepSize in which the allowance should be generated, until the total requests value is reached. | Double       | 123.0         | yes      |
|minimum               | yes                   | A miminum power that needs to be assigned as step1. Usefull for EVs.    | Double        | 512.0         | no      |
|vrmInstanceID         | yes                   | The ID the battery monitor should use in VRM                            | Integer       | 1008          | yes     |
|allowance             | no                    | Allowance in Watts, calculated by PVOverheadDistributor                 | Double        | 768.0         | n/a     |

PVOverheadDistributer will process these requests and finally publish the result within it's own topic, under: `N/{VRMPortalID/settings/{vRMInstanceIdOfPVOverheadDistributor}/requests`

It is important to report back consumption by the consumer. Only then the calculated values are correct. 

### Configuration

### Scripted-PVOverheadConsumer
TODO

### NPC-PVOverheadConsumer
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
| [Default]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Default]  | BatteryCapacityInWh  | Your batteries capacity in Wh.  | Integer| 28000 |
| [Modules]    | TimeToGoCalculator | Flag, if the module should be enabled or not | Boolean | true |
| [TimeToGoCalculator]  | UpdateInterval |  Time in milli seconds for TimeToGo Calculations. Sometimes the BMS are sending `null` values, so a small value helps to reduce flickering on VRM. But don't exagerate for looking at the dashboard for 10 minutes a day ;-)| Integer  | 1000 |


# F.A.Q.

TODO

