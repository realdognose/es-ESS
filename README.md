# dbus-fronius-hybrid-battery-visualisation

The original Implementation of Victrons Fronius Readout shows all Fronius inverters as PV-Inverters. Unfortunately the attached Battery is not visible.

So, I wrote my own script, that addresses this issue and creates a dbus-based Battery-Management System based on the JSON-API of the fronius inverter. 

- Disable the internal scanning for PV-Inverters and remove the original entry created by victron, else they appear twice.
- Under Settings / System Setup / Battery Measurements make sure to enable the virtual BMS to be displayed in VRM as well. 

(There is currently PV Output of the second inverter as well, so the battery discharge & the PV Output don't match, but they do)
![image](https://github.com/realdognose/dbus-fronius-hybrid-battery-visualisation/blob/main/img/BatteryAdd.png)

![image](https://github.com/realdognose/dbus-fronius-hybrid-battery-visualisation/blob/main/img/BatterySys.png)

# Script Installation.

```
wget https://github.com/realdognose/dbus-fronius-hybrid-battery-visualisation/archive/refs/heads/main.zip
unzip main.zip "dbus-fronius-hybrid-battery-visualisation-main/*" -d /data
mv /data/dbus-fronius-hybrid-battery-visualisation-main /data/dbus-fronius-hybrid-battery-visualisation
chmod a+x /data/dbus-fronius-hybrid-battery-visualisation/install.sh
/data/dbus-fronius-hybrid-battery-visualisation/install.sh
rm main.zip
```

⚠️ Check configuration after that - because service is already installed an running and with wrong connection data you will spam the log-file
### Stop service
```
svc -d /service/dbus-fronius-hybrid-battery-visualisation
```
### Start service
```
svc -u /service/dbus-fronius-hybrid-battery-visualisation
```
### Reload data
```
/data/dbus-fronius-hybrid-battery-visualisation/restart.sh
```
### View log file
```
cat /data/dbus-fronius-hybrid-battery-visualisation/current.log
```
### Change config.ini
Within the project there is a file `/data/dbus-fronius-hybrid-battery-visualisation/config.ini` - just change the values - most important is the host and HybridID in section "ONPREMISE". More details bellow
and comments in the config file:

Afther change the config file execute restart.sh to reload new settings 

| Section    | Config vlaue | Explanation |
| ---------- | ------------- | ------------- |
| DEFAULT    | AccessType | Fixed value 'OnPremise' |
| DEFAULT    | SignOfLifeLog  | Time in minutes how often a status is added to the log-file `current.log` with log-level INFO |
| ONPREMISE  | Host | IP or hostname of on-premise Fronis Meter web-interface |
| ONPREMISE  | HybridID  | Your HybridDevice ID
| ONPREMISE  | intervalMs  | Interval time in ms to get data from Fronius
---

# original description

forked from: smart meter readout repository at: 
https://github.com/ayasystems/dbus-fronius-smart-meter

For another hacky solution around running ESS as subgrid, see 
https://github.com/realdognose/dbus-fronius-smart-meter-with-phase1-injection
