# es-ESS
es-ESS (equinox solutions Energy Storage Systems) is an extension for Victrons VenusOS running on GX-Devices.
es-ESS brings various functions starting with tiny helpers, but also including major functionalities.

es-ESS is structered into individual services and every service can be enabled or disabled seperate. So, only certain
features can be enabled, based on your needs.

### Table of Contents
- [Setup](#setup) - General setup process and requirements for es-ESS.
- [MqttExporter](#mqttexporter) - Export selected values form dbus to your MQTT-Server.
- [ChargeCurrentReducer](#chargecurrentreducer) - Reduce the battery charge current to your *feel-well-value* without the need to disable DC-Feedin.
- [FroniusWattpilot](#FroniusWattpilot) - Full integration of Fronius Wattpilot in VRM / cerbo, including bidirectional remote control and improved eco mode.
- [MqttToEVSoc](#mqtttoevsoc) - Tiny helper to read your EV SoC from any mqtt source and insert a FAKE-BMS on cerbo / VRM for display purpose.
- [NoBatToEV](#nobattoev) - Avoid discharge of your home-battery when charging your ev with an `ac-out` connected wallbox.
- [SolarOverheadDistributor](#solaroverheaddistributor) - Utility to manage and distribute available solar overhead between various consumers.
  - [Scripted-SolarOverheadConsumer](#scripted-solaroverheadconsumer) - Consumers managed by external scripts can to be more complex and join the solar overhead pool.
  - [NPC-SolarOverheadConsumer](#npc-solaroverheadconsumer) - Manage consumers on a simple on/off level, based on available overhead. No programming required.
- [TimeToGoCalculator](#timetogocalculator) - Tiny helper filling out the `Time to Go` field in VRM, when BMS do not report this value.
- [This and that](#this-and-that) - Various information that doesn't fit elsewhere.
- [F.A.Q](#faq) - Frequently Asked Questions

# Setup
Your system needs to match the following requirements in order to use es-ESS:
- Be an ESS
- Have a mqtt server (or the use builtin one, to minimize system load an external mqtt is recommended)
- Have shell access enabled and know how to use it. (See: https://www.victronenergy.com/live/ccgx:root_access)

# MqttExporter
Victrons Venus OS / Cerbo Devices have a builtin Mqtt-Server. However, there are some flaws with that: You have to constantly post a Keep-Alive message, in order to keep values beeing published. VRM uses this in order to receive data. On one hand, it is a unnecessary performance-penalty to keep thausands of values up-to-date, just because you want to use 10-12 of them for display purpose. 

Second issue is - according to the forums: while Keep-Alive is enabled, topics are continiously forwarded to the cloud, causing bandwith usage, which is bad on metered connections or at least general bandwith pollution. 

So, the MqttExporter has been created. With a quite easy notation you can define which values should be tracked on dbus, and then be forwarded to your desired mqtt server.

# Configuration

MqttExporter requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Modules]    | MqttExporter | Flag, if the module should be enabled or not | Boolean | true |
| [MqttExporter]  | Export_{whatever}_{x} |  Export definition, see details bellow | String  | com.victronenergy.grid.http_40, /Ac/Power, CerboValues/Grid/Power |

To export values from DBus to your mqtt server, you need to specify 3 variables per value.
You can create as many exports as you like, just increase the number of the keys.
if you wanat to export from a certain service (like bms) you can use dbus-spy in ssh to figure out the service name. 
- Each Key needs to be unique
- Schema: {serviceName}, {DBusPath}, {MqttTarget}
- use a * in the mqtt-path to append the original DBus-Path.

**Note that dbus-Pahts start with a "/" and Mqtt Paths don't.**

All Whitespaces will be trimmed, you can intend values to see any typos easily. 
use dbus-spy on ssh to identify the service name. (right-arrow on selection to dig into available keys.)

Example Relation between dbus-spy, config and mqtt: 

| use `dbus-spy` to find the servicename |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter1.png" />|

| use `dbus-spy` to find the desired dbus-keys (right arrow key) |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter2.png" />|

| create config entries |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter3.png" />|

| Values on MQTT |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter4.png" />|

# ChargeCurrentReducer

> :warning: Work-in-progress, not yet production ready! :warning:

#### Overview
When you are using DC-Coupled Solar-Chargers, DVCC can be used to limit the charge-current of the batteries. If you however
decide to enable Feed-In from DC-Chargers, that limit has no effect. Reason is, that the MPPTs ofc. won't obey the limit anymore, 
because you opted to feed-in excess power, which in turn means the MPPTs have to produce at 100% whenever possible. 

Before any feed-in is happening, the attached batteries will crank up their charge current to consume what's possible. 

Therefore, we designed the ChargeCurrentReducer, which helps to reduce the battery charge current to your *feel-well-value*.
This is achieved by observing the charge current and as soon as the desired charge current is exceeded, the multiplus will be instructed
to start feed-in to the grid in order to reduce the available power on the dc-side and take load away from the batteries.

When the charge current drops bellow the desired value, grid-feedin will be reduced again to leave more power to the batteries. 

> :warning: I am using the wording "Reducer" on purpose. This is __NO__ Limiter. Your batteries, fusing and/or wiring should always be able to withstand
any incoming current from the MPPTs upto their technical limit!

The ChargeCurrentReducer __only__ works in positive directions. If your current solar production can't sustain a desired charge current of 50A, no additional
power will be consumed from grid. The battery will then charge with what is available.

#### Configuration

ChargeCurrentReducer requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Default]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Modules]    | ChargeCurrentReducer | Flag, if the module should be enabled or not | Boolean | true |
| [ChargeCurrentReducer]  | DesiredChargeAmps |  Desired Charge Current in Amps. Your *feel-well-value*.<br /><br />Beside a fixed value, you can use a equation based on SoC as well. The example will reduce the charge current desired by 1A per SoC-Percent, but minimum 30A<br /><br />*This equation is evaluated through pythons eval() function. You can use any complex arithmetic you like.* | String  | max(100 - SOC, 30) |

# FroniusWattpilot
When using a Fronius Wattpilot, there are issues with the default ECO-Mode-Charging. Using the native functionality of Wattpilot can't take 
the battery discharge of the victron universe into account, which may lead to Wattpilot not reducing its charge current, and your home battery
is kicking in to supply missing power.

Therefore, a complete integration of Wattpilot has been implemented: 
- Wattpilot is fully controllable through the VRM evcharger functionality.
- es-ESS will take over correct overhead distribution, relying on the built-in [SolarOverheadDistributor](#solaroverheaddistributor) and orchestrate Wattpilot accordingly.
- All (important) status of Wattpilot will be exposed on dbus / VRM:

| Charging | Phase Switch | Waiting for Sun | Cooldown Information |
|:-------:|:-------:|:-------:|:-------:|
| <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_3phases.png" /> | <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_switching_to_3.png" /> | <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_waitingSun.png" />| <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_start.png" /> <br /> <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_stop.png" />| 

| Full integration |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/SolarOverheadConsumers%202.png" />|
| Communication is bidirectional between VRM <-> Wattpilot app for both, auto and manual mode. |

# Installation
Despite the installation of es-ESS, an additional python module *websocket-client* is required to communicate with Wattpilot. 
The installation is a *one-liner* through *pythons pip* - which in turn might need to be installed first. 
If you have already installed *python pip* on your system, can skip this.

Install *pythong pip*: 
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

> :information_source: Configure Wattpilot in ECO-Mode and a PV-Overhead-Minimum-Startpower of 99kW or something. es-ESS will handle that and start/stop Wattpilot according to available solar overhead. Setting this high start value ensures Wattpilot is not messing with control as well.

> :warning: **FAKE-BMS injection**:<br /> This feature is creating FAKE-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

FroniusWattpilot requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Modules]    | FroniusWattpilot | Flag, if the module should be enabled or not | Boolean | true |
| [FroniusWattpilot]  | VRMInstanceID |  VRMInstanceId to be used on dbus | Integer  | 1001 |
| [FroniusWattpilot]  | VRMInstanceID_OverheadRequest |  VRMInstanceId to be used on dbus for the FAKE-BMS | Integer  | 1002 |
| [FroniusWattpilot]  | MinPhaseSwitchSeconds  | Seconds between Phase-Switching  | Integer| 300 |
| [FroniusWattpilot]  | MinOnOffSeconds | Seconds between starting/stopping charging | Integer | 600 |
| [FroniusWattpilot]  | ResetChargedEnergyCounter |  Define when the counters *Charge Time* and *Charged Energy* in VRM should reset. Options: OnDisconnect, OnConnect| String  | OnDisconnect |
| [FroniusWattpilot]  | Position | Position, where the Wattpilot is connected to. Options: 0:=ac-out, 1:=ac-in | Integer  | 0 |
| [FroniusWattpilot]  | Host | hostname / ip of Wattpilot | String  | wallbox.ad.equinox-solutions.de |
| [FroniusWattpilot]  | Username | Username of Wattpilot | String  | User |
| [FroniusWattpilot]  | Password | Password of Wattpilot | String  | Secret123! |

# Credits
Wattpilot control functionality has been taken from https://github.com/joscha82/wattpilot and modified to extract all variables required for full integration.
All buggy overhead (Home-Assistant / Mqtt) has been removed and some bug fixes have been applied to achieve a stable running Wattpilot-Core. (It seems to be unmaintained
since 2 years)

# MqttToEVSoc
TODO

# NoBatToEV
TODO

# SolarOverheadDistributor
#### Overview
Sometimes you need to manage multiple consumers based on solar overhead available. If every consumer is deciding on it's own, it can 
lead to a continious up and down on available energy, causing consumers to turn on/off in a uncontrolled, frequent fashion. 

To overcome this problem, the SolarOverheadDistributor has been created. Each consumer can register itself, send a request containing certain parameters - and
SolarOverheadDistributor will determine the total available overhead of the system and calculate allowances for each individual consumer. 

A minimum battery reservation can be defined through a SOC-based equation to make sure your home-battery receives the power it needs to fully charge during the day.

Each consumer is represented as a FAKE-BMS in VRM, so you can see where your energy is currently going. 

> :warning: **Fake-BMS injection**:<br /> This feature is creating Fake-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

| Example View |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/SolarOverheadConsumers%203.png"> |
| <div align="left">The example shows the view in VRM and presents the following information: <br /><br />- There is a no Battery reservation active, because it reached 100% SoC<br />- The SolarOverheadConsumer *PV-Heater* is requesting a total of 3300.0W, and due to the current allowance, 0W currently beeing consumed, equaling 0% of it's request. (Idle) <br />- The SolarOverheadConsumer  *Waterplay* is requesting a total of 120W, and due to the current allowance, 120W currently beeing consumed, equaling 100% of it's request. <br />- The SolarOverheadConsumer [WattPilot](#FroniusWattpilot) is requesting a total of 11338W, and due to the current allowance, 7485W currently beeing consumed, equaling 66% of it's request. <br /> - The SolarOverheadConsumer  *Pool Heater* is requesting a total of 3100W, and due to the current allowance, 3037W currently beeing consumed, equaling 98% of it's request. <br /> - All Consumers are currently running in automatic mode (listening to distribution), this is indicated through the tiny sun icon: ☼ </div>|

#### General functionality
The SolarOverheadDistributor (re-)distributes power every minute. We have been running tests with more frequent updates, but it turned out that the delay in processing a request/allowance by some consumers is causing issues. 
Also, when consumption changes, the whole ESS itself needs to adapt, adjust battery-usage, grid-meter has to catch up, values have to be re-read and published in dbus and so on. Finally also the sun may have some ups and downs
during ongoing calculations. So we decided to go with a fixed value of 1 minute, which is fast enough to adapt quickly but not causing any issues with consumers going on/off due to delays in processing.

### Usage
Each consumer is creating a SolarOverhead-Request, which then will be accepted or not by the SolarOverheadDistributor based on various parameters. The overall request has to be send to the venus mqtt inside the `W` Topic, 
where es-ESS will read the request and publish the processing result in it's own topic. 

A request is made out of the following values, where some are mandatory, some optional, some to be not filled out by the consumer: 

*In this table, a consumerKey of `consumer1` has been used. Replace that with an unique identifier for your consumer*
each key has to be published in the topic `W/{VRMPortalID}/esEss/SolarOverheadDistributor/requests/consumer1`
| Mqtt-Key             | To be set by Consumer |  Descripion                                                             | Type          | Example Value| Required |
| -------------------- | ----------------------|------------------------------------------------------------------------ | ------------- |--------------| ---------|
|IsAutomatic             | yes                   | Flag, indicating if the consumer is currently in automatic mode         | Boolean       | true         | yes      |
|Consumption           | yes                   | Current consumption of the consumer                                     | Double        | 1234.0       | yes      |
|CustomName            | yes                   | DisplayName on VRM                                                      | String        | My Consumer 1| yes      |
|IgnoreBatReservation  | yes                   | Consumer shall be enabled despite active Battery Reservation            | Boolean       | true         | no       |
|Request               | yes                   | Total power this consumer would ever need.                              | Double        | 8500.0       | yes      |
|StepSize              | yes                   | StepSize in which the allowance should be generated, until the total requests value is reached. | Double       | 123.0         | yes      |
|Minimum               | yes                   | A miminum power that needs to be assigned as step1. Usefull for EVs.    | Double        | 512.0         | no      |
|Priority               | yes                   | Priority compared to other Consumers. defaults to 100    | Integer        | 56         | no      |
|VRMInstanceID         | yes                   | The ID the battery monitor should use in VRM                            | Integer       | 1008          | yes     |
|Allowance             | no                    | Allowance in Watts, calculated by SolarOverheadDistributor                 | Double        | 768.0         | n/a     |

SolarOverheadDistributor will process these requests and finally publish the result within it's own topic, under: `N/{VRMPortalID/settings/{vRMInstanceIdOfSolarOverheadDistributor}/requests`

- It is important to report back consumption by the consumer. Only then the calculated values are correct.
- Only consumers reporting as automatic will be considered. (So maintain this, when implementing manual overrides)

### Scripted-SolarOverheadConsumer
A Scripted-SolarOverheadConsumer is an external script (Powershell, bash, arduino, php, ...) you are using to control a consumer. This allows the requests to be more precice and granular
than using a NPC-SolarOverheadConsumer (explained later). 

The basic workflow of an external script can be described as follows: 

```
   every x seconds or event based:
      check own environment variables.
      determine suitable request values.
      send request to mqtt server
      process current allowance
      report actual consumer consumption to mqtt.
```

For example, I have an electric water heater (called *PV-Heater*) that can deliver roughly 3500 Watts of total power, about 1150 Watts per phase. The script controlling this consumer
takes various environment conditions into account before creating a request: 

 - If the temperature of my water reservoir is bellow 60°C, a full request of 3500 Watts is created.
 - If the temperature of my water reservoir is between 60°C and 70°C, the maximum request is 2 phases, so roughly 2300 Watts.
 - If the temperature of my water reservoir is between 70°C and 80°C, the maximum request is 1 phase, so roughly 1150 Watts.
 - If the temperature of my water reservoir is above 80°C, no heating is required, so the request will be 0 Watts.
 - If the EV is connected and waiting for charging, the maximum request will be 2 phases, so roughly 2300 Watts.
 - If the co-existing thermic solar system is producing more than 3000W power, no additional electric heating is required, so request is 0 Watts.

After evaluating and creating the proper request, the current allowance is processed, consumer is adjusted based on allowance, and actual consumption is reported back.

### NPC-SolarOverheadConsumer
Some consumers are not controllable in steps, they are simple on/off consumers. Also measuring the actual consumption is not always possible or required, so a fixed known consumption can 
work out as well. To eliminate the need to create multiple on/off-scripts for these consumers, the NPC-SolarOverheadConsumer has been introduced. 

It can be fully configured in `/data/es-ESS/config.ini` and will be orchestrated by the SolarOverhead-Distributer itself - as long as it is able to process http-remote-control requests.
An example would be our *waterplay* in the front garden. It is connected through a shelly device, which is http-controllable - and I know it consumes roughly 120 Watts AND I want this
to run as soon as PV-Overhead is available, despite any battery reservation. (Doesn't make sence to wait on this, until the battery reached 90% Soc or more)

The following lines inside `/data/es-ESS/config.ini` can be used to create such an NPC-SolarOverheadConsumer. A config section has to be created under `[SolarOverheadDistributor]`, containing
the required request values plus some additional parameters for remote-control. Well, the secion has to be prefixed with `NPC:` to identify it correctly.

the example consumerKey is *waterplay* here.

#TODO: Update table bellow.

| Section    | Value name |  Descripion | Type | Example Value|
| ------------------ | ---------|---- | ------------- |--|
| [NPC:waterplay]    | customName |  DisplayName on VRM   |String | Waterplay |
| [NPC:waterplay]    | ignoreBatReservation             | Consumer shall be enabled despite active Battery Reservation            | Boolean       | true         |
| [NPC:waterplay]    | vrmInstanceID                    | The ID the battery monitor should use in VRM                            | Integer       | 1008          | 
| [NPC:waterplay]    | ~~minimum~~                       | obsolete for on/off NPC-consumers     | ~~Double~~        | ~~0~~|
| [NPC:waterplay]    | ~~stepSize~~                         | obsolete for on/off NPC-consumers | ~~Double~~       | ~~120.0~~|
| [NPC:waterplay]    | request                              | Total power this consumer would ever need.                              | Double        | 120.0       | 
| [NPC:waterplay]    | onUrl                              | http(s) url to active the consumer                            | String        | 'http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/relay/0/?turn=on'       | 
| [NPC:waterplay]    | offUrl                              | http(s) url to deactive the consumer                               | String        | 'http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/relay/0/?turn=off'      | 
| [NPC:waterplay]    | statusUrl                              | http(s) url to determine the current operation state of the consumer                            | String        | 'http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/status'       | 
| [NPC:waterplay]    | isOnKeywordRegex                              | If this Regex-Match is positive, the consumer is considered *On* (evaluated against the result of statusUrl)                            | String        | '"ison":\s*true'      | 


#TODO: Update image bellow.
| Example of config section for NPC-SolarOverheadConsumer |
|:-----------:|
| <img src="https://github.com/realdognose/es-ESS/blob/main/img/visual_example_npc.png" /> | 



### Configuration
SolarOverheadDistributer requires a few variables to be set in `/data/es-ESS/config.ini`: 

> :warning: **Fake-BMS injection**:<br /> This feature is creating Fake-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Default]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Modules]    | SolarOverheadDistributor | Flag, if the module should be enabled or not | Boolean | true |
| [SolarOverheadDistributor]  | VRMInstanceID |  VRMInstanceId to be used on dbus | Integer  | 1000 |
| [SolarOverheadDistributor]  | VRMInstanceID_ReservationMonitor |  VRMInstanceId to be used on dbus (for the injected Fake-BMS of the active battery reservation) | Integer  | 1000 |
| [SolarOverheadDistributor]  | MinBatteryCharge |  Equation to determine the active battery reservation. Use SOC as keyword to adjust. <br /><br />*You can use any complex arithmetic you like, see example graphs bellow for 3 typical curves* | String  | 5000 - 40 * SOC |
| [SolarOverheadDistributor]  | Strategy |  Strategy to assign overhead.<br /><br/>**RoundRobin**: available overhead is distributed among every consumer in {StepSize} pieces.<br />**TryFullfill**: Available overhead is assigned based on Priority and only moved to the next consumer if the consumer with the lower priority is running at 100% or can't be assigned more anymore. | String  | TryFullfill |
| [SolarOverheadDistributor]  | UpdateInterval |  Time in milliseconds, how often the overhead should be redistributed. CAUTION: Do not use to small values. Theres a lot in the system happening that needs to catch up. Too small values will lead to imprecise readings of various meter values and lead to wrong calculations. I recommend 60s (60000ms), more frequent distribution doesn't yield better results.  | Integer  | 60000 |

In order to have the FAKE-BMS visible in VRM, you need to go to *Settings -> System Setup -> Battery Measurement* and set the ones you'd like to see to *Visible*:

| Cerbo Configuration for FAKE-BMS |
|:-----------:|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/cerboSettings.png" /> |

| Typically usefull equations for `MinBatCharge` |
|:-----------:|
| Blue := Linear going down, with a maxium of 5400Watts and a minimum of 400W: `5000-50*SOC+400`|
| Green := Enforce battery charge of 3000W upto ~ 90% SoC: `3000/(SOC-100)+3000`|
| Red := Just enforce at very low SoC, but 1500W minimum: `(1/(SOC/8)*5000)+1000`|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/socFormula.png"> |

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
| [DEFAULT]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [DEFAULT]  | BatteryCapacityInWh  | Your batteries capacity in Wh.  | Integer| 28000 |
| [Modules]    | TimeToGoCalculator | Flag, if the module should be enabled or not | Boolean | true |
| [TimeToGoCalculator]  | UpdateInterval |  Time in milli seconds for TimeToGo Calculations. Sometimes the BMS are sending `null` values, so a small value helps to reduce flickering on VRM. But don't exagerate for looking at the dashboard for 10 minutes a day ;-)| Integer  | 1000 |

# This and that

### Logging
es-ESS can log a lot of information helpfull to debug things. For this, the loglevel in the configuration can be adjusted and several (recurring) Log Messages can be surpressed
The log file is placed in `/data/logs/es-ESS/current.log` and rotated every day at midnight. A total of 14 log files is kept, then recycled.

> :warning: Having es-ESS running at log level `DEBUG` for a long time will produce huge log files and negatively impact system performance. Especially with MQTT-Logs enabled.

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [DEFAULT]    | LogLevel |  Options: DEBUG, INFO, WARNING, ERROR, CRITICAL | String | INFO |
| [LogDetails]    | DontLogDebug | Blacklist for method calls that shouldn't even be logged in DEBUG Mode.  | String | es-ESS.onLocalMqttMessage, esESS._dbusValueChanged|

### Various Configuration

Additionally there are the following configuration options available: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [DEFAULT]    | NumberOfThreads |  Number of threads, es-ESS should use. | int | 5 |
| [DEFAULT]    | ServiceMessageCount | Number of service messages published on mqtt | int | 50 |
| [DEFAULT]    | ConfigVersion | Current Config Version. DO NOT TOUCH THIS, it is required to update configuration files on new releases. | int | 1 |
| [Mqtt]    | ThrottlePeriod | Minimum time in ms between two messages on the same topic. Useful to reduce overall network traffic. Intelligent backlog tracking ensures that "the last message" emitted is always published after {ThrottlePeriod} milliseconds. | int | 2000 |

### Service Messages
es-ESS also publishes Operational-Messages as well as Errors, Warnings and Critical failures under the `$SYS`-Topic of es-ESS. Check these from time to time to ensure proper functionality



# F.A.Q.

TODO

