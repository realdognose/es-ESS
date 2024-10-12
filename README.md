# es-ESS
es-ESS (equinox solutions Energy Storage Systems) is an extension for Victrons VenusOS running on GX-Devices.
es-ESS brings various functions starting with tiny helpers, but also including major functionalities.

es-ESS is structered into individual services and every service can be enabled or disabled. So, only certain
features can be enabled, based on your needs.

Services are marked according to their current development state: 

> :white_check_mark: Production Ready: Feature is finished, tested and fully operable.

> :large_orange_diamond: Release-Candiate-Version: Feature is still undergoing development, but current version is already satisfying.

> :red_circle: Work-in-progress, beta: Feature is a beta, may have bugs or not work at all. Only use if you are a dev and want to contribute.

# About me

I'm a software engineer since about 20 years, pretty new to python, tho. es-ESS is provided free of charge and created during my spare-time after work. 
Feel free to create [issues](https://github.com/realdognose/es-ESS/issues) for questions or bugs, but bear with me that i cannot provide a 24/7 support or guarantee some sort of 8h response time. 
If you are a developer yourself and want to help to improve es-ESS, feel free to do so and create pull requests.

I've switched to a Victron-System some months ago, and immediately digged into customizing it. Lot has been done, Lot is still todo. Since I will run this 
system for at least 10ish years, there will be plenty of updates and/or bugfixes in the future.

# Almost there

equinox-solutions, es-ESS or me are in no way affiliated, sponsored or associated with Victron Energy. Use es-ESS at your own risk, the software is provided
"as is" and may stop working correctly due to system upgrades without notice.

# Table of Contents
- [Setup](#setup) - General setup process and requirements for es-ESS.
- [TimeToGoCalculator](#timetogocalculator) - Tiny helper filling out the `Time to Go` field in VRM, when BMS do not report this value.
- [MqttTemperatures](#mqtttemperatures) - Display various temperature sensors you have on mqtt in VRM.
- [MqttExporter](#mqttexporter) - Export selected values form dbus to your MQTT-Server.
- [FroniusWattpilot](#FroniusWattpilot) - Full integration of Fronius Wattpilot in VRM / cerbo, including bidirectional remote control and improved eco mode.
- [NoBatToEV](#nobattoev) - Avoid discharge of your home-battery when charging your ev with an `ac-out` connected wallbox.
- [Shelly3EMGrid](#shelly3emgrid) - Use a shelly 3 EM as grid meter.
- [ShellyPMInverter](#shellypminverter) - Use a shelly PM (second generation) as meter for any inverter. (Single phased, phase configurable)
- [SolarOverheadDistributor](#solaroverheaddistributor) - Utility to manage and distribute available solar overhead between various consumers.
  - [Scripted-SolarOverheadConsumer](#scripted-solaroverheadconsumer) - Consumers managed by external scripts can to be more complex and join the solar overhead pool.
  - [NPC-SolarOverheadConsumer](#npc-solaroverheadconsumer) - Manage consumers on a simple on/off level, based on available overhead. No programming required.
- [ChargeCurrentReducer](#chargecurrentreducer) - Reduce the battery charge current to your *feel-well-value* without the need to disable DC-Feedin.
- [This and that](#this-and-that) - Various information that doesn't fit elsewhere.
- [F.A.Q](#faq) - Frequently Asked Questions

# Setup
Your system needs to match the following requirements in order to use es-ESS:
- Be an ESS
- Have a mqtt server (or the use builtin one, to minimize system load an external mqtt is recommended)
- Have shell access enabled and know how to use it. (See: https://www.victronenergy.com/live/ccgx:root_access)

Run the following lines of code on your gx device: 

```
wget https://github.com/realdognose/es-ESS/archive/refs/heads/main.zip
unzip main.zip "es-ESS-main/*" -d /data
mv /data/es-ESS-main /data/es-ESS
chmod a+x /data/es-ESS/install.sh
/data/es-ESS/install.sh
rm main.zip
```

`es-ESS` will automatically start - with the default configuration with all services DISABLED. You can now start to modify the file `/data/es-ESS/config.ini` as required. 
I recommend to complete configuration of a single service, then restart and validate functionality. If you rush through the (quite huge) configuration in a single go, and it
is not working at the end, it may become hard to find the error without starting over.

Handy commands to use during configuration and in generall: 

Restart es-ESS (gracefully - config changes require restart!):
```
/data/es-ESS/restart.sh
```

Restart es-ESS (if it won't listen!)
```
/data/es-ESS/kill_me.sh
```

Uninstall es-ESS (to whom it may concern)
```
/data/es-ESS/uninstall.sh
```

Tail current log file (log file rotated daily, 14 days kept, see [logging](#logging) for more details): 
```
tail -f -n 20 /data/log/es-ESS/current.log
```

#### Global Configuration
Configuration of es-ESS is performed through the file `/data/es-ESS/config.ini`. Not all of the Global / Common Values are required, it depends on the combination 
of services that should be active. However, it easiest to setup the common values for every usecase, so you don't have to mind adding / remove values as you enable
or disable certain services. 

| Section                  | Value name           |  Descripion                                                                                            | Type          | Example Value                |
| ------------------------ | ---------------------|------------------------------------------------------------------------------------------------------- | ------------- |------------------------------|
| [Common]                 | LogLevel             | LogLevel to use. See [Logging](#logging) use `INFO` if you are unsure.                                 | String        | INFO                         |  
| [Common]                 | NumberOfThreads      | Number of Threads to use. 3-XX depending on enabled service count.                                     | Integer       | 5                            |
| [Common]                 | ServiceMessageCount  | Number of ServiceMessages to publish on Mqtt. See [Service Messages](#service-messages)                | Integer       | 50                           |
| [Common]                 | ConfigVersion        | Just don't touch this.                                                                                 | Integer       | 1                            |
| [Common]                 | VRMPortalID          | Your VRMPortalID, required to publish/read some values of your local mqtt.                             | String        | VRM0815                      |
| [Common]                 | BatteryCapacityInWh  | Your battery capacity in Watthours.                                                                    | Integer       | 28000                        |
| [Common]                 | BatteryMaxChargeInW  | Your battery maximum charge power in W                                                                 | Integer       | 9000                         |
| [Common]                 | DefaultPowerSetPoint | Default Power Setpoint (W), when using features that manipulte the set point programmatically.         | Integer       | -10                          |
| [Mqtt]                   | Host                 | Hostname / IP of your main-mqtt to work with.                                                          | String        | mqtt.ad.equinox-solutions.de |
| [Mqtt]                   | User                 | Username to connect to your main-mqtt.                                                                 | String        | user                         |
| [Mqtt]                   | Password             | Password to connect to your main-mqtt.                                                                 | String        | secure123!                   |
| [Mqtt]                   | Port                 | Port to connect to your main-mqtt.                                                                     | Integer       | 1833                         |
| [Mqtt]                   | SslEnabled           | Flag, if your main-mqtt is ssl enabled. Note: We kindly ignore Certificate-Checks as of now.           | Boolean       | true                         |
| [Mqtt]                   | LocalSslEnabled      | Flag, if your local / venus-Mqtt is SSL or plain.                                                      | Boolean       | true                         |
| [Services]               | SolarOverheadDistributor  | Flag, if [SolarOverheadDistributor](#solaroverheaddistributor) is enabled.                        | Boolean       | true                         |
| [Services]               | TimeToGoCalculator        | Flag, if [TimeToGoCalculator](#timetogocalculator) is enabled.                                    | Boolean       | true                         |
| [Services]               | FroniusWattpilot          | Flag, if [FroniusWattpilot](#FroniusWattpilot) is enabled.                                        | Boolean       | true                         |
| [Services]               | ChargeCurrentReducer      | Flag, if [ChargeCurrentReducer](#chargecurrentreducer) is enabled.                                | Boolean       | true                         |
| [Services]               | MqttExporter              | Flag, if [MqttExporter](#mqttexporter) is enabled.                                                | Boolean       | true                         |
| [Services]               | MqttTemperature           | Flag, if [MqttTemperatures](#mqtttemperatures) is enabled.                                        | Boolean       | true                         |
| [Services]               | NoBatToEV                 | Flag, if [NoBatToEV](#nobattoev) is enabled.                                                      | Boolean       | true                         |
| [Services]               | Shelly3EMGrid                 | Flag, if [Shelly3EMGrid](#shelly3emgrid) is enabled.                                                      | Boolean       | true                         |
| [Services]               | ShellyPMInverter                 | Flag, if [ShellyPMInverter](#shellypminverter) is enabled.                                                      | Boolean       | true                         |

> :warning: NOTE: I recommend to enable one service after each other and finalize configuration, before enabling another one. Else configuration may become a bit clumsy and error-prone.

# TimeToGoCalculator 

> :white_check_mark: Production Ready

<img align="right" src="https://github.com/realdognose/es-ESS/blob/main/img/TimeToGo.png" /> 

#### Overview

Some BMS - say the majority of them - don't provide values for the `Time to go`-Value visible in VRM. This is an important figure when looking at a dashboard. This helper script 
fills that gap and calculates the time, when BMS don't. Calculation is done in both directions: 

- **When discharging**: Time based on current discharge rate until the active SoC Limit is reached.
- **When charging**: Time based on current charge rate until 100% SoC is reached. 

#### Configuration

TimeToGoCalculatore requires your local mqtt to be enabled, either in plain or ssl mode.<br />
TimeToGoCalculator requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Common]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Common]  | BatteryCapacityInWh  | Your batteries capacity in Wh.  | Integer| 28000 |
| [Mqtt]     | LocalSslEnabled | Flag, if local Mqtt is SSL or plain. | Boolean | true |
| [Services]    | TimeToGoCalculator | Flag, if the service should be enabled or not | Boolean | true |
| [TimeToGoCalculator]  | UpdateInterval |  Time in milliseconds for TimeToGo Calculations. Sometimes the BMS are sending `null` values, so a small value helps to reduce flickering on VRM. But don't exagerate for looking at the dashboard for 10 minutes a day ;-)| Integer  | 1000 |

# MqttTemperatures
> :white_check_mark: Production Ready

### Overview
MqttTemperatures is a streight-forward feature: It allows you to read temperature sensors from your mqtt server and injects them as temperaturesensors in dbus/vrm. (Including the `Pressure` and `Humidity` Fields, if present.)

| Example View |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttTemperature.png"> |

| Example View with Details |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttTemperatureGarden.png"> |

### Configuration
MqttTemperatures requires a few variables to be set in `/data/es-ESS/config.ini`: 


| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Services]    | MqttTemperatures | Flag, if the service should be enabled or not | Boolean | true |
| [MqttTemperature:XYZ]  | VRMInstanceID |  VRMInstanceId to be used on dbus | Integer  | 1000 |
| [MqttTemperature:XYZ]  | CustomName |  Custom name to be used for this sensor | String  | MPPT2 Wiring |
| [MqttTemperature:XYZ]  | Topic |  Topic on Mqtt, delivering the measurement value. | String  | Devices/d1Garden/Sensors/TEMP/Value |
| [MqttTemperature:XYZ]  | TopicHumidity |  Topic on Mqtt, delivering the measurement value for humidity (optional). | String  | Devices/d1Garden/Sensors/HUM/Value |
| [MqttTemperature:XYZ]  | TopicPressure |  Topic on Mqtt, delivering the measurement value for pressure (optional). | String  | Devices/d1Garden/Sensors/PRESSURE/Value |

> :warning: You can create as many `[MqttTemperature:XYZ]` sections as you need, just take care to ensure unique names and VRM-Ids.

| Example Config file with multiple sections added |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttTemperatureExampleConf.png"> |

# MqttExporter

> :white_check_mark: Production Ready

### Overview
Victrons Venus OS / Cerbo Devices have a builtin Mqtt-Server. However, there are some flaws with that: You have to constantly post a Keep-Alive message, in order to keep values beeing published. VRM uses this in order to receive data. On one hand, it is a unnecessary performance-penalty to keep thausands of values up-to-date, just because you want to use 10-12 of them for display purpose. 

Second issue is - according to the forums: while Keep-Alive is enabled, topics are continiously forwarded to the upstream-server, causing bandwith usage, which is bad on metered connections or at least general bandwith pollution. 

So, the MqttExporter has been created. You can define which values should be tracked on dbus, and then be forwarded to your mqtt server for further processing and/or display purpose.

# Configuration

MqttExporter requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Services]    | MqttExporter | Flag, if the service should be enabled or not | Boolean | true 

For every value you want to export, you have to create a additional section, specifying export-conditions. This is quite a bunch of work, but generally only done once. 

Each section needs to match the pattern `[MattExporter:uniqueKey]` where uniqueKey should be an unique identifier.

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [MqttExporter:XXX]  | Service |  Service name, see details bellow | String  | com.victronenergy.system |
| [MqttExporter:XXX]  | DbusKey |  Key of the dbus-value to export | String  | /Ac/Grid/L1/Power |
| [MqttExporter:XXX]  | MqttTopic |  Topic on Mqtt | String  | Grid/Ac/L1/Power |

**Note that dbus-paths start with a "/" and MQTT Topics don't.**

To export values from DBus to your mqtt server, you need to specify 3 variables per export
You can create as many exports as you like, just increase the number of the sections added to the ini file.

### Service name ###
if you want to export from a certain service (like bms) you can use dbus-spy in ssh to figure out the service name to use. 

### Example relation between dbus-spy, config and MQTT ###


<div align="center">
  
| use `dbus-spy` to find the servicename |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter1.png" />|
</div>

<div align="center">

| use `dbus-spy` to find the desired Dbus-keys (right arrow key) |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter2.png" />|
</div>

<div align="center">

| create config entries |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter3.png" />|
</div>

<div align="center">

| Values on MQTT |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporter4.png" />|
</div>

Hint: You can use a trailing `*` on the Mqtt Topic. This will cause the original dbus path to be appended, for example: 

<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporterStar1.png" />

<img src="https://github.com/realdognose/es-ESS/blob/main/img/mqttExporterStar2.png" />

# FroniusWattpilot

> :white_check_mark: Production Ready. 
> Known Issue: When no EV is connected AND Hibernate Mode is enabled, control through VRM doesn't work. Waking up Wattpilot through the "scheduled charge" option isn't helping, wattpilot will immediately go into hibernation again. 

### Overview

When using a Fronius Wattpilot, there are issues with the default ECO-Mode-Charging. Using the native functionality of Wattpilot can't take 
the battery discharge of the victron universe into account, which may lead to Wattpilot not reducing its charge current, and your home battery
is kicking in to supply missing power.

Therefore, a complete integration of Wattpilot has been implemented: 
- Wattpilot is fully controllable through the VRM evcharger functionality.
- es-ESS will take over correct overhead distribution, relying on the builtin [SolarOverheadDistributor](#solaroverheaddistributor) and orchestrate Wattpilot accordingly. Note that you have to enable [SolarOverheadDistributor](#solaroverheaddistributor), else the SolarOverhead-Requests generated by the Wattpilot-Service won't receive clearence and only manual charging is possible.
- All (important) status of Wattpilot will be exposed on dbus / VRM:

| Charging | Phase Switch | Waiting for Sun | Cooldown Information |
|:-------:|:-------:|:-------:|:-------:|
| <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_3phases.png" /> | <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_switching_to_3.png" /> | <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_waitingSun.png" />| <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_start.png" /> <br /> <img src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_stop.png" />| 

<div align="center">

| Full integration |
|:-------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/SolarOverheadConsumers%202.png" />|
| Communication is bidirectional between VRM <-> Wattpilot app for both, auto and manual mode. |
</div>

### Installation
Despite the installation of es-ESS, an additional python module *websocket-client* is required to communicate with Wattpilot. 
The installation is a *one-liner* through *pythons pip* - which in turn might need to be installed first. 
If you have already installed *python pip* on your system, can skip this.

Install *pythong pip*: 
```
opkg update
opkg install python3-pip
```

Install *websocket-client*:
```
python -m pip install websocket-client
```

### Configuration

<img align="right" src="https://github.com/realdognose/es-ESS/blob/main/img/wattpilot_controls.png" /> 

- If Wattpilot is set to `Manual Mode` through the Fronius App, es-ESS will detect this as manual mode, update VRM and don't mess with control at any time. 
- To use Solar-Overhead charging, Wattpilot needs to be set into `ECO` Mode __AND__ The PV-Starting Power has to be set to something that never happens, like 99 kW. This ensures, that Wattpilot is NOT messing with 
control while es-ESS is managing the solar overhead charging.
- `Schduled Charging` in VRM is used to wake up wattpilot when hibernate is enabled (see Table bellow)

__Important:__ es-ESS will not change any settings done in Wattpilot and will use the limits that are configured in wattpilot.

VRM Controls have no option to explicit select 1 or 3 phase charging, therefore the following logic will apply: 

- Selecting 6 - 16A in VRM will cause Wattpilot to charge with 6-16A on a single phase. 
- Selecting 18 - 48A in VRM will cause Wattpilot to charge with 6-16A in three phase mode. 

> :warning: **FAKE-BMS injection**:<br /> This feature is creating FAKE-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

> :warning: **Dependency**:<br /> If you want to enable Solar-Overhead Charging, you need to enable the [SolarOverheadDistributor](#solaroverheaddistributor) as well. (It will be responsible for giving a clearence to Wattpilots charge request)

FroniusWattpilot requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Services]    | FroniusWattpilot | Flag, if the service should be enabled or not | Boolean | true |
| [FroniusWattpilot]  | VRMInstanceID |  VRMInstanceId to be used on dbus | Integer  | 1001 |
| [FroniusWattpilot]  | VRMInstanceID_OverheadRequest |  VRMInstanceId to be used on dbus for the FAKE-BMS | Integer  | 1002 |
| [FroniusWattpilot]  | MinPhaseSwitchSeconds  | Seconds between Phase-Switching  | Integer| 300 |
| [FroniusWattpilot]  | MinOnOffSeconds | Seconds between starting/stopping charging | Integer | 600 |
| [FroniusWattpilot]  | ResetChargedEnergyCounter |  Define when the counters *Charge Time* and *Charged Energy* in VRM should reset. Options: OnDisconnect, OnConnect| String  | OnDisconnect |
| [FroniusWattpilot]  | Position | Position, where the Wattpilot is connected to. Options: 0:=ac-out, 1:=ac-in | Integer  | 0 |
| [FroniusWattpilot]  | Host | hostname / ip of Wattpilot | String  | wallbox.ad.equinox-solutions.de |
| [FroniusWattpilot]  | Username | Username of Wattpilot | String  | User |
| [FroniusWattpilot]  | Password | Password of Wattpilot | String  | Secret123! |
| [FroniusWattpilot]  | HibernateMode | When the car is disconnected, es-ESS will switch into idle mode, stop doing heavy lifting. Connection to wattpilot remains established and VRM control enabled. <br /><br />With hibernate enabled, wattpilot will also be disconnected, and connected every 5 minutes for a car-state-check. This greatly reduces the number of incoming socket messages from wattpilot by about 95% per day, but causes an delay of upto 5 minutes when the car is connected.<br /><br />You can force a wakeup by switching to *Scheduled charging* in VRM at any time. | Boolean  | true |
| [FroniusWattpilot]  | LowPriceCharging | Flag, if es-ESS should control low price charging | Boolean  | true |
| [FroniusWattpilot]  | LowPriceAmps | Amps to use, when low price charging | int  | 48 |

### Low Price Charging. 
Wattpilot supports the function to charge due to cheap grid prices. This works, as long as you are still running a Fronius inverter along with a Fronius Smartmeter. 
If you no longer run a Fronius Smartmeter, Wattpilot basically is not able to use "Eco-Mode" - which also disables the builtin charge functionality when grid prices are low. 

If you still run a Fronius smartmeter, you can use the builtin feature as you are used to. Leave `LowPriceCharging` in the config.ini set to `false`. es-ESS will then detect,
whenever Wattpilot is charging due to cheap prices and NOT take over any control. 

If you are NOT running a Fronius smartmeter anylonger, es-ESS can take over that part as well: Set `LowPriceCharging` in the config.ini to `true` and adjust the value `LowPriceAmps`
accordingly. es-ESS will query wattpilot for it's current configured price limit and the current price - and invoke charging, if the limit is undershot.

The Fronius Wattpilot-Service is able to deal with nested occurences of PV-Overhead-Charging and Low Price Charging, it can start with "10A Solar" (based on allowance) and then switch to the desired 
48A due to cheap grid prices or the other way round.

### Credits
Wattpilot control functionality has been taken from https://github.com/joscha82/wattpilot and modified to extract all variables required for full integration.
All buggy overhead (Home-Assistant / Mqtt) has been removed and some bug fixes have been applied to achieve a stable running Wattpilot-Core. (It seems to be unmaintained
since 2 years, lot of pull-requests are not accepted.)

### F.A.Q.

> The wattpilot app is reporting a different charge time than displayed in VRM?

The wattpilot app is reporting the time since the car has been plugged in. Especially with solar overhead charging, that includes a lot of idle time. es-ESS is tracking only the time the car is actually charging and displaying this time in VRM.

> Sometimes VRM is displaying `Stop charging`, `Start charging` or `Switching phasemode` for a long time? 

Whenever one of the preconfigured Start/Stop- or Phaseswitchtimes are exhausted, es-ESS will display the status until the cooldown is passed, or conditions change again. 
So, whenever a sun shortage requires to stop charging, but you have 250s left on the on/off cooldown, VRM will display `Stop charging` for 250s. This is, so you are aware that - even if there is grid-pull happening - wattpilot is about to stop as soon as conditions allow for it. For more details about the current state, you can review the respective service messages topic on mqtt: `es-ESS/{service}/ServiceMessages/ServiceMessageType.Operational`

# NoBatToEV
> :large_orange_diamond: Release-Candiate-Version: Feature is still undergoing development, but current version is already satisfying.

### Overview

If you have your wallbox connected to the AC-OUT (because you like to be able to charge in emergencies) but generally don't want to discharge your home batteries, *NoBatToEV* is what you need. The service monitors
your ev charge, consumption and available solar - and offloads any overhead-ev-charge that is not covered by solar to the grid. 

| Example |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/nobattoev.png"> |
| With 0 Solar available, basically the whole ev-charge is offloaded to the grid, while the battery only powers the remaining loads.|

| Example 2 |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/nobattoev2.png"> |
| With Solar available, critical loads and EV Charger is covered as good as possible - and the remaining difference is offloaded to the grid.|

Adjusting the Grid-Setpoints of the multiplus is not resulting in a 10W-Precission. Especially with Solar beeing available, the battery will 
naturally switch between charge / discharge as solar changes, until the multiplus have catched up with their new grid set point. 

### Configuration
NoBatToEV requires your gx-local mqtt-server to be enabled, either as plain or ssl.
NoBatToEV requires a few variables to be set in `/data/es-ESS/config.ini`: 


| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Services]    | NoBatToEV   | Flag, if the service should be enabled or not | Boolean | true |
| [Common]     | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Common]     | DefaultPowerSetPoint |  Default Power SetPoint, so it can be restored after ev charge finished. | double | -10 |

> :warning: NOTE: this feature manipulates the grid set point in order to achieve proper offloading of your evs energy demand. Several precautions ensure that the configured default grid set point
> is restored when the service is receiving proper shutdown signals (aka SIGTERM) or any kind of internal error appears. - However, in case of unexpected
> powerlosses of your GX-device, complete Hardware-failure, networking-issues or usage of the `reboot` command on the cerbo that may not be the case.
> I have never expierienced issues with that, hence I can't tell what the multiplus will do, if the cerbo `dies`, while the grid set point is -5000 Watt or something.
> I assume, Worstcase, your multiplus will keep charging your houses battery until there is no more consumer for such a (stuck) grid request.

# Shelly3EMGrid
> :large_orange_diamond: Release-Candiate-Version: Feature is still undergoing development, but current version is already satisfying: NET-Metering is untested so far, need to get hands on a shelly 3EM, fist.

Utilize a Shelly 3 EM as Grid Meter. 

### Configuration

Shelly3EMGrid requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Services]    | Shelly3EMGrid   | Flag, if the service should be enabled or not | Boolean | true |
| [Shelly3EMGrid]     | VRMInstanceID |  InstanceID the Meter should get in VRM | Integer | 47 |
| [Shelly3EMGrid]     | CustomName |  Display Name of the device in VRM | String | Shelly 3EM (Grid) |
| [Shelly3EMGrid]     | PollFrequencyMs |  Intervall in ms to query the Shellies JSON-API | int | 1000 |
| [Shelly3EMGrid]     | Username |  Username of the Shelly | String | User |
| [Shelly3EMGrid]     | Password |  Password of the Shelly | String | JG372FDr |
| [Shelly3EMGrid]     | Host |  IP / Hostname of the Shelly | String | 192.168.136.87 |
| [Shelly3EMGrid]     | Metering | Type of Measurement. See Info bellow. `Default` or `Net` | String | Default

When adjusting the `PollFrequencyMs`, you should check the log file regulary. The Device is polled with exactly `PollFrequencyMs`
Timeout, so requests do not pile up. Whenever there are 3 consecutive timeouts, the dbus service will be feed with `null` values, and 
the device is marked offline, so the overall system notes that it now has to work without grid-meter values.

### Metering
By Default, the Shelly 3EM uses Gross-Metering. Feed-In and Consumption are counted for each phase individually. 

In some countries however (f.e.: Germany, Switzerland, Austria, ... ) Net-Metering is used by the providers. 
Values of each phase are saldated immediately, and then it will be either counted as Feed-In or Grid-Pull.

The Shelly does not support this kind of measurement, so the script can take over this. It therefore needs to 
manually keep track of the momentary values for each phase and manually count. These values are persisted on the cerbo
every 5 minutes, so in case of a unexpected shutdown, they are not lost. 

However, since this requires to count the momentary values and derive a hourly consumption from that values, it 
may be less precise than any other meter. Also flows that happen while the shelly or es-ESS is offline cannot be 
recovered, leading to temporary "gaps" on the consumption/feed-in records.

### Example config

<img src="https://github.com/realdognose/es-ESS/blob/main/img/shelly3emexample.png">

<img src="https://github.com/realdognose/es-ESS/blob/main/img/shelly3emexample2.png">

# ShellyPMInverter
> :white_check_mark: Production Ready. 

Utilize a Shelly PM (any Kind, Generation 3) as a meter to detect PV-Inverter Production. 
Phase on which the inverter is feeding in can be adjusted, mostly usefull for single phased micro inverters without any other
communication possibility. 

### Configuration

ShellyPMInverter requires a few variables to be set in `/data/es-ESS/config.ini`: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Services]    | Shelly3EMGrid   | Flag, if the service should be enabled or not | Boolean | true |

After enabling the service in general, you need to create 1 additional config-section per shelly to use. 
each config Section needs to match the pattern `[ShellyPMInverter:aUniqueKey]` and contain the following values: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [ShellyPMInverter:aUniqueKey]     | VRMInstanceID |  InstanceID the Meter should get in VRM | Integer | 1008 |
| [ShellyPMInverter:aUniqueKey]     | CustomName |  Display Name of the device in VRM | String | HMS-Garage |
| [ShellyPMInverter:aUniqueKey]     | PollFrequencyMs |  Intervall in ms to query the Shellies JSON-API | int | 1000 |
| [ShellyPMInverter:aUniqueKey]     | Username |  Username of the Shelly | String | User |
| [ShellyPMInverter:aUniqueKey]     | Password |  Password of the Shelly | String | JG372FDr |
| [ShellyPMInverter:aUniqueKey]     | Host |  IP / Hostname of the Shelly | String | 192.168.136.87 |
| [ShellyPMInverter:aUniqueKey]     | Phase |  Phase the Shelly / Inverter is connected to. (1-3) | Integer | 2 |
| [ShellyPMInverter:aUniqueKey]     | Position |  Position, the Shelly / Inverter is connected to your multiplus. 0 = ACIN; 1=ACOUT | Integer | 1 |

When adjusting the `PollFrequencyMs`, you should check the log file regulary. The Device is polled with exactly `PollFrequencyMs`
Timeout, so requests do not pile up. Whenever there are 3 consecutive timeouts, the dbus service will be feed with `null` values, and 
the device is marked offline, so the overall system notes that the inverter is currently considered not producing.

Example Configuration:

<img src="https://github.com/realdognose/es-ESS/blob/main/img/pmInverterExample.png">

<img src="https://github.com/realdognose/es-ESS/blob/main/img/pmInverterExample2.png">

<img src="https://github.com/realdognose/es-ESS/blob/main/img/pmInverterExample3.png">

<img src="https://github.com/realdognose/es-ESS/blob/main/img/pmInverterExample4.png">


# SolarOverheadDistributor

> :large_orange_diamond: Release-Candiate-Version

> :warning: This Feature requires a grid-connection and feedin to be enabled. (The amount beeing feed in is used to detect available overhead, when soc reached 100%)

#### Overview
Sometimes you wish to manage multiple consumers based on solar overhead available. If every consumer is deciding on it's own, it can 
lead to a continious up and down on available energy, causing consumers to turn on/off in a uncontrolled, frequent fashion. 

To overcome this problem, the SolarOverheadDistributor has been created. Each consumer can register itself, send a request containing certain parameters - and
SolarOverheadDistributor will determine the total available overhead of the system and calculate allowances for each individual consumer based on preconfigured
priorities. 

A minimum battery reservation can be defined through a SOC-based equation to make sure your home-battery receives the power it needs to fully charge during the day.

Each consumer is represented as a FAKE-BMS in VRM, so you can see where your energy is currently going. 

> :warning: **Fake-BMS injection**:<br /> This feature is creating Fake-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

| Example View |
|:-------------------------:|
|<img src="https://github.com/realdognose/es-ESS/blob/main/img/SolarOverheadConsumers%203.png"> |
| <div align="left">The example shows the view in VRM and presents the following information: <br /><br />- There is a a Battery reservation active (only 250W), because it reached 100% SoC. (Idling at 26W)<br />- The consumer *Pool Filter* is requesting a total of 220W, and due to the current allowance, 205W currently beeing consumed, equaling 92.7% of it's request. <br />- The consumer  *Pool Heater* is requesting a total of 750W, and due to the current allowance, 650W currently beeing consumed, equaling 86.6% of it's request. <br />- The consumer  *Waterplay* is requesting a total of 120W, and due to the current allowance, 120W currently beeing consumed, equaling 100% of it's request. <br />- The consumer  *PV Heater* is requesting a total of 3300W, and due to the current allowance, 1067W currently beeing consumed, equaling 32.3% of it's request. <br /> - The consumer [WattPilot](#FroniusWattpilot) is requesting a total of 11388W, and due to the current allowance, 6073W currently beeing consumed, equaling 53.3% of it's request. <br /> - All Consumers are currently running in automatic mode (listening to distribution), this is indicated through the tiny sun icon: ☼ </div>|

#### General functionality
The SolarOverheadDistributor (re-)distributes power every minute. We have been running tests with more frequent updates, but it turned out that the delay in processing a request/allowance by some consumers is causing issues. 
Also, when consumption changes, the whole ESS itself needs to adapt, adjust battery-usage, grid-meter has to catch up, values have to be re-read and published in dbus and so on. Finally also the sun may have some ups and downs
during ongoing calculations. So we decided to go with a fixed value of 1 minute, which is fast enough to adapt quickly but not causing any issues with consumers going on/off due to delays in processing.

### Usage
Each consumer can create a SolarOverhead-Request, which then will be accepted or not by the SolarOverheadDistributor based on various parameters. The overall request has to be send to the mqtt topic `es-ESS/SolarOverheadDistributor/Requests` where es-ESS will catch up the request, process it and add the `allowance` property to the request.

A request is made out of the following values, where some are mandatory, some optional: 

each key has to be published in the topic `es-ESS/SolarOverheadDistributor/Requests/{consumerIdentifier}/`

| Mqtt-Key             | To be set by Consumer |  Descripion                                                             | Type          | Example Value| Required |
| -------------------- | ----------------------|------------------------------------------------------------------------ | ------------- |--------------| ---------|
|IsAutomatic             | yes                   | Flag, indicating if the consumer is currently in automatic mode         | Boolean       | true         | yes      |
|Consumption           | yes                   | Current consumption of the consumer                                     | Double        | 1234.0       | yes      |
|CustomName            | yes                   | DisplayName on VRM                                                      | String        | My Consumer 1| yes      |
|IgnoreBatReservation  | yes                   | Consumer shall be enabled when there is sufficent solar, despite active Battery Reservation            | Boolean       | true         | no       |
|Request               | yes                   | Total power this consumer would ever need.                              | Double        | 8500.0       | yes      |
|StepSize              | yes                   | StepSize in which the allowance should be generated, until the total requests value is reached. | Double       | 123.0         | yes      |
|Minimum               | yes                   | A miminum power that needs to be assigned as step1. Usefull for EVs that require a minimum start power.    | Double        | 512.0         | no      |
|Priority               | yes                   | Priority compared to other Consumers. defaults to 100    | Integer        | 56         | no      |
|PriorityShift          | yes                   | Priority decrease after an assignment (See example bellow)    | Integer        | 1         | no      |
|VRMInstanceID         | yes                   | The ID the battery monitor should use in VRM                            | Integer       | 1008          | yes     |
|Allowance             | no                    | Allowance in Watts, calculated by SolarOverheadDistributor. Has to be picked up by the consumer.                 | Double        | 768.0         | n/a     |

SolarOverheadDistributor will process these requests and finally publish the result under: `es-ESS/SolarOverheadDistributor/Requests/{consumerIdentifier}/allowance`

- It is important to report back consumption by the consumer. Only then the calculated values are correct, because the consumption of every controlled consumer is *available Budget*.
- Only consumers reporting as automatic will be considered. (So maintain this, when implementing manual overrides, i.e. an unplugged EV should not request overhead-share, else it will receive an allowance and block other consumers with lower priority)

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

> :warning: NOTE: es-ESS will set the allowance for every consumer to 0, when the service is receiving proper shutdown signals (aka SIGTERM) - However, in case of unexpected
> powerlosses of your GX-device, complete Hardware-failure, networking-issues or usage of the `reboot` command on the cerbo that may not be the case.
> To ensure your scripted consumers don't run for an indefinite amount of time, you should not only validate the `allowance` as outlined above, but also the topic
> `es-ESS/$SYS/Status`. This is set to `Online` at startup and set to `Offline` per last-will. So, if your consumers note that es-ESS is going offline - it is
> up to you if they should keep running or stop as well.

### NPC-SolarOverheadConsumer
Some consumers are not controllable in steps or you simply don't want to write scripts for them. To eliminate the need to create multiple on/off-scripts for these consumers, 
the NPC-SolarOverheadConsumer has been introduced. es-ESS can automatically control consumers that can be switched on/off through `http` or `mqtt`.

It can be fully configured in `/data/es-ESS/config.ini` and will be orchestrated by the SolarOverhead-Distributer itself. An example would be our *waterplay* in the front garden. It is connected through a (first-gen, dumb) shelly device, which is at least http-controllable - and I know it consumes roughly 120 Watts AND I want this to run as soon as Solar-Overhead is available, despite any battery reservation. (Doesn't make sence to wait, until the battery reached 90% Soc or more)

The following lines inside `/data/es-ESS/config.ini` can be used to create such an NPC-SolarOverheadConsumer. A config section has to be created, containing
the required request values plus some additional parameters for remote-control. Well, the secion has to be prefixed with `HttpConsumer:` or `MqttConsumer:` to identify it correctly.

the example consumerKey is *waterplay* here.

| Section    | Value name |  Descripion | Type | Example Value|
| ------------------ | ---------|---- | ------------- |--|
| [HttpConsumer:waterplay]    | CustomName |  DisplayName on VRM   |String | Waterplay |
| [HttpConsumer:waterplay]    | IgnoreBatReservation             | Consumer shall be enabled despite active Battery Reservation            | Boolean       | true         |
| [HttpConsumer:waterplay]    | VRMInstanceID                    | The ID the battery monitor should use in VRM                            | Integer       | 1008          | 
| [HttpConsumer:waterplay]    | ~~minimum~~                       | obsolete for on/off NPC-consumers     | ~~Double~~        | ~~0~~|
| [HttpConsumer:waterplay]    | ~~stepSize~~                         | obsolete for on/off NPC-consumers | ~~Double~~       | ~~120.0~~|
| [HttpConsumer:waterplay]    | Request                              | Total power this consumer would ever need.                              | Double        | 120.0       | 
| [HttpConsumer:waterplay]    | OnUrl                              | http(s) url to active the consumer                            | String        | http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/relay/0/?turn=on       | 
| [HttpConsumer:waterplay]    | OffUrl                              | http(s) url to deactive the consumer                               | String        | http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/relay/0/?turn=off      | 
| [HttpConsumer:waterplay]    | StatusUrl                              | http(s) url to determine the current operation state of the consumer                            | String        | http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/status       | 
| [HttpConsumer:waterplay]    | IsOnKeywordRegex                              | If this Regex-Match is positive, the consumer is considered *On* (evaluated against the result of statusUrl)                            | String        | "ison":\s*true      | 
| [HttpConsumer:waterplay]    | PowerUrl                              | http(s) url to determine the current consumption state of the consumer. If left empty, es-ESS will assume `Consumption=Request` while the consumer is switched on.                            | String        | 'http://shellyOneWaterPlayFilter.ad.equinox-solutions.de/status'       | 
| [HttpConsumer:waterplay]    | PowerExtractRegex     | Regex to extract the consumption. Has to have a SINGLE matchgroup.                            | String        | "apower":([^,]+),      | 

If the NPC is mqtt controlled, you need to provide the Topics, instead of the URLs:
| Section    | Value name |  Descripion | Type | Example Value|
| ------------------ | ---------|---- | ------------- |--|
| [MqttConsumer:poolHeater]    | OnTopic               | MqttTopic to activate the consumer                                                                              | String        | Devices/shellyPro2PMPoolControl/IO/Heater/Set       | 
| [MqttConsumer:poolHeater]    | OnValue               | MqttValue to publish on `OnTopic` to activate the consumer                                                      | String        | true      | 
| [MqttConsumer:poolHeater]    | OffTopic              | MqttTopic to deactivate the consumer                                                                            | String        | Devices/shellyPro2PMPoolControl/IO/Heater/Set     | 
| [MqttConsumer:poolHeater]    | OffValue              | MqttValue to publish on `OffTopic` to deactivate the consumer                                                     | String        | false      | 
| [MqttConsumer:poolHeater]    | StatusTopic           | MqttTopic to determine the current operation state of the consumer                                             | String        | Devices/shellyPro2PMPoolControl/IO/Heater/State       | 
| [MqttConsumer:poolHeater]    | IsOnKeywordRegex      | If this Regex-Match is positive, the consumer is considered *On* (evaluated against the Messages on StatusTopic)                            | String / Regex        | true         | 
| [MqttConsumer:poolHeater]    | PowerTopic            | MqttTopic to determine the current consumption state of the consumer. If left empty, es-ESS will assume `Consumption=Request` while the consumer is switched on.                            | String        | Devices/shellyPro2PMPoolControl/IO/Heater/Power       | 
| [MqttConsumer:poolHeater]    | PowerExtractRegex     | Regex to extract the consumption. Has to have a SINGLE matchgroup. (evaluated against the Messages on PowerTopic). Using `(.*)` because it's a well-formated decimal value here.            | String / Regex        | (.*)      | 

Example (Screenshots)

Pool-Filter (via a Shelly Pro2 PM) as http-consumer:

<img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/poolFilterAsHTTP.png">

Pool-Heater (via s Shally Pro2 PM) as mqtt-consumer. (Got my own mqtt/rpc infrastructure, tho)

<img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/poolHeaterAsMqtt.png">

### Configuration
SolarOverheadDistributer requires a few variables to be set in `/data/es-ESS/config.ini`: 

> :warning: **Fake-BMS injection**:<br /> This feature is creating Fake-BMS information on dbus. Make sure to manually select your *actual* BMS unter *Settings > System setup > Battery Monitor* else your ESS may not behave correctly anymore. Don't leave this setting to *Automatic*

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Common]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Services]    | SolarOverheadDistributor | Flag, if the service should be enabled or not | Boolean | true |
| [SolarOverheadDistributor]  | VRMInstanceID |  VRMInstanceId to be used on dbus | Integer  | 1000 |
| [SolarOverheadDistributor]  | VRMInstanceID_ReservationMonitor |  VRMInstanceId to be used on dbus (for the injected Fake-BMS of the active battery reservation) | Integer  | 1001 |
| [SolarOverheadDistributor]  | MinBatteryCharge |  Equation to determine the active battery reservation. Use SOC as keyword to adjust. <br /><br />*You can use any complex arithmetic you like, see example graphs bellow for 3 typical curves* | String  | 5000 - 40 * SOC |

In order to have the FAKE-BMS visible in VRM, you need to go to *Settings -> System Setup -> Battery Measurement* and set the ones you'd like to see to *Visible*:



<div align="center">

| Cerbo Configuration for FAKE-BMS |
|:-----------:|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/cerboSettings.png" /> |
</div>

<div align="center">

| Typically usefull equations for `MinBatCharge` |
|:-----------:|
| Blue := Linear going down, with a maxium of 5400Watts and a minimum of 400W: `5000-50*SOC+400`|
| Green := Enforce battery charge of 3000W upto ~ 90% SoC: `3000/(min(SOC,99)-100)+3000`|
| Red := Just enforce at very low SoC, but 1500W minimum: `(1/(SOC/8)*5000)+1000`|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/socFormula.png"> |
</div>

### Priority Shifting ###
Priority shifting is a powerfull feature allowing you to control your consumers in a sophisticated way. SolarOverheadDistributor will always give away `StepSize` Watts to a single consumer.
Once an assignment has been done, and priority shifting is enabled for this consumer, it's priority for the next distribution round is lowered by the given `PriorityShift` value. (defaults to 0,
if not provided)

i.e.: My EV could consume upto 11.000 Watts, leaving nothing for other consumers. I have a 3*1000 Watt electric heater that should have kinda lower priority, but 
also be considered with energy. 

So, I configured the following Values: 

- EV: Priority `35`, PriorityShift `1`, StepSize: `250`, Minimum: `1365`
- Heater: Priority `40`, PriorityShift `5`, StepSize: `1000`

Now, SolarOverheadDistributor will give away available Energy in the following pattern. 

> :information_source: es-ESS will also add another `0.0001` with every shift performed. This ensures that once two consumers hit the same priority, the priority stays predictable: 
> The consumer received lesser assignments so far will have the higher priority, as illustrated bellow. If you are using the same `Priority` and `PriorityShift` value for all consumers,
> you'll effectively achieve a round-robin distribution.

1) EV +1365 due to priority 35 and minimum start power.
2) EV +250 due to priority 36.0001
3) EV +250 due to priority 37.0002
4) EV +250 due to priority 38.0003
5) EV +250 due to priority 39.0004
6) PV Heater +1000 due to priority 40
7) EV +250 due to priority 40.0005
8) EV +250 due to priority 41.0006
9) EV +250 due to priority 42.0007
10) EV +250 due to priority 43.0008
11) EV +250 due to priority 44.0009
12) PV Heater +1000 due to priority 45.0001
13) EV +250 due to priority 45.0010
14) EV +250 due to priority 46.0011
....

### Nough' said

The SolarOverheadDistributor is a quite a lot of configuration and not something that is fully configured within 10 minutes. But once setup properly, the results are just flawless. 
Here are some graphs of my (not yet published) Dashboard, which shows how well SolarOverheadDistributor is managing consumers of any shape - starting with the tiny waterplay
of 200 Watts, ending at my 11kW EV-Charging station: 

<div align="center">

| Good day :) |
|:-----------:|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/example_overhead2.png" /> |

</div>

<div align="center">

| Not so sunny day, but consumers taking any chance. |
|:-----------:|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/solarOverhead_Gaps.png" /> |

</div>

<div align="center">

| yet another day |
|:-----------:|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/example_overhead1.png" /> |

</div>

# ChargeCurrentReducer

> :red_circle: Work-in-progress, beta: Feature is a beta, may have bugs or not work at all. Only use if you are a dev and want to contribute.

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
| [Common]    | VRMPortalID |  Your portal ID to access values on mqtt / dbus |String | VRM0815 |
| [Services]    | ChargeCurrentReducer | Flag, if the service should be enabled or not | Boolean | true |
| [ChargeCurrentReducer]  | DesiredChargeAmps |  Desired Charge Current in Amps. Your *feel-well-value*.<br /><br />Beside a fixed value, you can use a equation based on SoC as well. The example will reduce the charge current desired by 1A per SoC-Percent, but minimum 30A<br /><br />*This equation is evaluated through pythons eval() function. You can use any complex arithmetic you like.* | String  | max(100 - SOC, 30) |


# This and that

### Logging
es-ESS can log a lot of information helpfull to debug things. For this, the loglevel in the configuration can be adjusted.
The log file is placed in `/data/logs/es-ESS/current.log` and rotated every day at midnight (UTC). A total of 14 log files is kept, then recycled.

> :warning: Having es-ESS running at log level `TRACE` for a long time will produce huge log files and negatively impact system performance. This will log all incoming and outgoing values, we are talking about thausands of lines of log per minute here, depending on enabled services. Rather usefull for development purpose with single service(s) enabled. 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Common]    | LogLevel |  Options: TRACE, DEBUG, APP_DEBUG, INFO, WARNING, ERROR, CRITICAL | String | INFO |

`APP_DEBUG` is a level higher than regular `DEBUG`, so this will surpress Debug messages of third party modules as long as they obey the setup log level.

<div align="center">

| Logrotation to avoid filling up the disk |
|:-----------:|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/logrotate.png" /> |

</div>

### More Configx

Additionally there are the following configuration options available: 

| Section    | Value name |  Descripion | Type | Example Value|
| ---------- | ---------|---- | ------------- |--|
| [Common]    | NumberOfThreads |  Number of threads, es-ESS should use. | int | 5 |
| [Common]    | ServiceMessageCount | Number of service messages published on mqtt | int | 50 |
| [Common]    | ConfigVersion | Current Config Version. DO NOT TOUCH THIS, it is required to update configuration files on new releases. | int | 1 |

### Service Messages
es-ESS also publishes Operational-Messages as well as Errors, Warnings and Critical failures under the `service`-Topic of the serivce. Check these from time to time to ensure proper functionality

<div align="center">

| Service Messages on MQTT |
|:-----------:|
| <img align="center" src="https://github.com/realdognose/es-ESS/blob/main/img/ServiceMessages.png" /> |

</div>


# F.A.Q.

See also the service-specific F.A.Q. at the end of each service-description.


