# es-ESS
es-ESS (equinox solutions Energy Storage Systems) is an extension for Victrons VenusOS running on GX-Devices.
es-ESS brings various functions starting with tiny helpers, but also including major functionalities.

es-ESS is structered in individual modules and every module can be enabled or disabled independent. So, only certain
features can be enabled, based on your needs.

### Table of Contents
- [Setup](#setup) - General setup process and requirements for es-ESS
- [ChargeCurrentReducer](#chargecurrentreducer) - Reduce the battery charge current to your *feel-well-value* without the need to disable DC-Feedin.
- [FroniusWattPilotService](#froniuswattpilotservice) - Full integration of Fronius Wattpilot in VRM / cerbo, including bidirectional remote control and improved eco mode.
- [MqttToEVSoc](#mqtttoevsoc) - Tiny helper to read your EV SoC from any mqtt server and insert a Fake-BMS on cerbo / VRM.
- [NoBatToEV](#nobattoev) - Avoid usage of your home-battery when charging your ev with an `ac-out` connected wallbox.
- [PVOverheadDistributor](#pvoverheaddistributor) - Utility to manage and distribute available Solar Overhead between various consumers.
  - [Scripted-PVOverheadConsumer](#scripted-pvoverheadconsumer) - Consumers managed by external scripts can to be more complex and join the Solar Overhead Pool.
  - [NPC-PVOverheadConsumer](#npc-pvoverheadconsumer) - Manage consumers on a simple on/off level, based on available overhead.
- [TimeToGoCalculator](#timetogocalculator) - Tiny helper filling out the `Time to Go` field in VRM, when BMS do not report this value.
- [This and that](#this-and-that) - Various information that doesn't fit elsewhere
- [F.A.Q](#faq) - Frequently Asked Questions

# Setup
Your system needs to match the following requirements in order to use es-ESS
- Be an ESS
- Have the local Mqtt enabled (plain or tls)

# ChargeCurrentReducer
TODO

# FroniusWattPilotService
When using a system combined with a Fronius Wattpilot, there are issues with PVOverhead charging. Using the native functionality of Wattpilot can't take 
the battery discharge of the victron universe into account, which may lead to a constant "solar charge" which in fact is draining your battery. 

Therefore, a complete integration of Wattpilot has been implemented: 
- Wattpilot is fully controllable through VRM Switches.
- es-ESS will take over correct overhead distribution, relying on the build-in PVOverhead Distributor and orchestrate Wattpilot accordingly.
- All (important) Status of Wattpilot will be exposed on dbus / VRM:

| Charging | Phase Switch | Waiting for Sun | Cooldown |
|:-------:|:-------:|:-------:|:-------:|
| <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_3phases.png" /> | <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_switching_to_3.png" /> | <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_waitingSun.png" />| <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_stop.png" /> | 

| Full integration |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/PVOverheadConsumers%202.png" />|
| Communication is bidirectional between VRM <-> Wattpilot App for both, Auto- and manual mode. |

# Installation
Despite the installation of es-ESS, an additional python module *websocket-client* is required to communicate with the wattpilot. 

if you have already installed `python pip` on your system, can skip the installation ofc. 

Install pip: 
```
opkg update
opkg list | grep pip
opkg install python3-pip
```

Install *websocket-client*:
```
python -m pip install websocket-client
```

# Configuration

> :information_source: Configure the wattpilot itself in ECO-Mode and a PV-Overhead-Minimum-Startpower of 99kW. es-ESS will handle that, but this avoids the car starting to charge everytime when plugged in.

> :information_source: Setup Maximum-Charge-Currents in wattpilot as used to.

> :warning: **Fake-BMS injection**:<br /> This feature is creating Fake-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

FroniusWattpilotService requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Default]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [FroniusWattpilot]  | VRMInstanceID |  VRMInstanceId to be used on dbus | Integer  | 1001 |
| [FroniusWattpilot]  | VRMInstanceID_OverheadRequest |  VRMInstanceId to be used on dbus for the FAKE-bms. | Integer  | 1002 |
| [FroniusWattpilot]  | MinPhaseSwitchSeconds  | Seconds between Phase-Switching  | Integer| 300 |
| [FroniusWattpilot]  | MinOnOffSeconds | Seconds between starting/stopping charging | Integer | 600 |
| [FroniusWattpilot]  | ResetChargedEnergyCounter |  Define when the counters *Charge Time* and *Charged Energy* in VRM should reset. Options: OnDisconnect, OnConnect| String  | OnDisconnect |
| [FroniusWattpilot]  | Position | Position, where the wattpilot is connected to. Options: 0:=ac-out, 1:=ac-in | Integer  | 0 |
| [FroniusWattpilot]  | Host | hostname / ip of wattpilot | String  | wallbox.ad.equinox-solutions.de |
| [FroniusWattpilot]  | Username | Username of wattpilot | String  | User |
| [FroniusWattpilot]  | Password | Password of wattpilot | String  | Secret123! |

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

### Scripted-PVOverheadConsumer
A Scripted PVOverheadConsumer is an external script (Powershell, bash, arduino, php, ...) you are using to control a consumer. This allows the requests to be more precice and granular
than using a NPC-PVOverheadConsumer (explained later). 

The basic workflow of an external script can be described like this: 

```
   every x seconds:
      check own environment variables.
      determine suitable request values.
      send request to mqtt server
      process current allowance
      report actual consumer consumption to mqtt.
```

For example, I have an electric water heater (called *PV-Heater*) that can deliver roughly 3500 Watts of total power, about 1150 Watts per Phase. The Script controlling this consumer
takes various environment conditions into account before creating a request: 

 - If the temperature of my water reservoir is bellow 60°C, a full request of 3500 Watts is created.
 - If the temperature of my water reservoir is between 60°C and 70°C, the maximum request is 2 phases, so roughly 2300 Watts
 - If the temperature of my water reservoir is between 70°C and 80°C, the maximum request is 1 phase, so roughly 1150 Watts
 - If the temperature of my water reservoir is above 80°C, no heating is required, so the request will be 0 watts.
 - If the EV is connected and waiting for charging, the maximum request shall be 2 phases, so roughly 2300 Watts
 - If the co-existing thermic solar system is producing more than 3000W Power, no additional electric heating is required, so request 0 Watts.

After evaluating and creating the proper request, the current allowance is processed, consumer is adjusted based on allowance, and actual consumption is reported back.

### NPC-PVOverheadConsumer
Some consumers are not controllable in steps, they are simple on/off consumers. Also measuring the actual consumption is not always possible, so a fixed known consumption can 
work out as well. To eliminate the need to create multiple on/off-scripts for these consumers, the NPC-PVOverheadConsumer has been introduced. 

It can be fully configured in `/data/es-ESS/config.ini` and will be orchestrated by the PVOVerhead-Distributer itself - as long as it is able to process http-remote-control requests.
An example would be our *waterplay* in the front garden. It is connected through a shelly device, which is http-controllable - and I know it consumes roughly 120 Watts AND I want this
to run as soon as PV-Overhead is available, despite any battery reservation. (Doesn't make sence to wait on this, until the battery reached 90% Soc or more)

The following lines inside `/data/es-ESS/config.ini` can be used to create such an NPC-PVOverheadConsumer. A config section has to be created under `[PVOverheadDistributor]`, containing
the required request values plus some additional parameters for remote-control. Well, the secion has to be prefixed with `NPC:` to identify it correctly.

the example consumerKey is *waterplay* here.

| Section    | Value name |  Descripion | Type | Example Value|
| ------------------ | ---------|---- | ------------- |--|
| [NPC:waterplay]    | customName |  DisplayName on VRM   |String | Waterplay |
| [NPC:waterplay]    | ignoreBatReservation             | Consumer shall be enabled despite active Battery Reservation            | Boolean       | true         |
| [NPC:waterplay]    | vrmInstanceID                    | The ID the battery monitor should use in VRM                            | Integer       | 1008          | 
| [NPC:waterplay]    | minimum                       | A miminum power that needs to be assigned as step1.     | Double        | 0|
| [NPC:waterplay]    | stepSize                         | StepSize in which the allowance should be generated, until the total requests value is reached. | Double       | 120.0|
| [NPC:waterplay]    | request                              | Total power this consumer would ever need.                              | Double        | 120.0       | 
| [NPC:waterplay]    | onUrl                              | http(s) url to active the consumer                            | String        | 'http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/relay/0/?turn=on'       | 
| [NPC:waterplay]    | offUrl                              | http(s) url to deactive the consumer                               | String        | 'http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/relay/0/?turn=off'      | 
| [NPC:waterplay]    | statusUrl                              | http(s) url to determine the current operation state of the consumer                            | String        | 'http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/status'       | 
| [NPC:waterplay]    | isOnKeywordRegex                              | If this Regex-Match is positive, the consumer is considered *On* (evaluated against the result of statusUrl)                            | String        | '"ison":\s*true'      | 


### Configuration
PVOVerheadDistributer requires a few variables to be set in `/data/es-ESS/config.ini`: 

> :warning: **Fake-BMS injection**:<br /> This feature is creating Fake-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Default]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Modules]    | PVOVerheadDistributor | Flag, if the module should be enabled or not | Boolean | true |
| [PVOverheadDistributor]  | VRMInstanceID |  VRMInstanceId to be used on dbus | Integer  | 1000 |
| [PVOverheadDistributor]  | VRMInstanceID_ReservationMonitor |  VRMInstanceId to be used on dbus (for the injected Fake-BMS of the active battery reservation) | Integer  | 1000 |
| [PVOverheadDistributor]  | MinBatteryCharge |  Equation to determine the active battery reservation. Use SOC as keyword to adjust. <br /><br />The example will maximum reserve 5000W, for every percent of SoC reached 40 watts are released. Mimimum of 1040 Watts will be reached at 99% Soc, until SoC is 100%<br /><br />*This equation is evaluated through pythons eval() function. You can use any complex arithmetic you like.* | String  | 5000 - 40 * SOC |

In order to have the FAKE-BMS visible in VRM, you need to go to *Settings -> System Setup -> Battery Measurement* and set the ones you'd like to see to *Visible*:

| Cerbo Configuration for FAKE-BMS |
|:-----------:|
| <img width="441" height="1" src="" /><br /><img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/cerboSettings.png" /> |


# TimeToGoCalculator

<img align="right" src="https://github.com/realdognose/es-ESS/blob/main/img/TimeToGo.png" /> 

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

# This and that

### Logging
es-ESS can log a lot of information helpfull to debug things. For this, the loglevel in the configuration can be adjusted and several (recurring) Log Messages can be surpressed
The log file is placed in `/data/logs/es-ESS/current.log` and rotated every day at midnight. A total of 14 log files is kept, then recycled.

> :warning: Having es-ESS running at log level `DEBUG` for a long time will produce huge log files and negatively impact system performance. Especially with MQTT-Logs enabled.

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Default]    | LogLevel |  Options: DEBUG, INFO, WARNING, ERROR, CRITICAL | String | INFO |
| [LogDetails]    | LogIncomingMqttMessages | Log messages received by mqtt | Boolean | true |

# F.A.Q.

TODO

