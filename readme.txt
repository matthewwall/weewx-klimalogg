kl - weewx driver for the Klimalogg Pro

The klimalogg hardware supports up to 8 sensors.  You can use either the
default schema (the wview schema), which supports up to 5 temperature sensors
and 4 humidity sensors, or the klimalogg schema, which supports up to 8
temperature sensors and 8 humidity sensors.

The USB transceiver must be paired with the console.  This can be done using
the Windows software that came with the Klimalogg, or it can be done using
weewx (see the 'Pairing' section below) after the driver has been installed.


Installation for using the wview schema:

1) Install the extension:

  setup.py install --extension weewx-kl.tar.gz

2) Start weewx:

  sudo /etc/init.d/weewx start


Instructions for using the klimalogg schema:

1) Install the extension:

  setup.py install --extension weewx-kl.tar.gz

2) Modify weewx.conf to use the klimalogg schema:

2a) uncomment the [[sensor_map]] section for klimalogg schema in [KlimaLogg]

2b) modify the schema parameter in DataBindings:

[DataBindings]
   [[wx_binding]]
       database = archive_sqlite
       table_name = archive
       manager = weewx.wxmanager.WXDaySummaryManager
       schema = user.kl.schema   # use kl schema instead of wview schema

3) Start weewx:

  sudo /etc/init.d/weewx start


Additional configuration options:

Debugging/Diagnostics:

[KlimaLogg]
    ...
    # debug flags:
    # 0=no logging; 1=minimum logging; 2=normal logging; 3=detailed logging
    debug_comm = 2
    debug_config_data = 2
    debug_weather_data = 2
    debug_history_data = 2
    debug_dump_format = auto

WARNING for Raspberry PI owners who use a (micro) SD-card for running linux
and weewx.  When debug logging is enabled (values 1-3) the klimalogg driver
will write LOTS of data to the system log files.  Some SD-cards will be killed
within weeks because of the large amount of data written to the (same parts
of) the card.  Also the skin output files written to the public_html map will
cause wearing of your SD card.

You can overcome this by:
- decrease the log levels when the information is not needed anymore
- move the linux system to a USB-flash drive or an external USB hard disk
   (in the latter case you need a separate power supply for your hard disk)
- move the frequently written parts to a RAM-disk (NOT your weewx database;
   you don't want to loose this data in case of a power fail or system crash!)


Sensor Names:

[KlimaLogg]
    ...
    # Sensor texts can have 1-10 upper-case alphanumeric characters;
    #   other allowed characters: space - + ( ) * , . / \ and o
    #   o is lower case O used as degree symbol
    # Note: You can't preset sensor texts for non-present sensors
    # Example for 5 sensors:
    sensor_text1 = "5565 BED1"
    sensor_text2 = "6DDF LAUN"
    sensor_text3 = "7131 FRID"
    sensor_text4 = "52F4 BED2"
    sensor_text5 = "67D7 BATH"


Pairing:

The USB transceiver and console must be paired.  If this was done using the
Windows program KlimaLoggPro as "Logger Channel 1", then this step is not
necessary.  The weewx driver will try to synchronize with logger channel 1.

The protocol for pairing the transceiver and console looks like this:

1) Push the USB button on the base unit several seconds until you hear a beep

2) Start weewx direct after with command:

sudo /etc/init.d/weewx start

3) You should see a log message like:

"console is paired to device with ID xxxx"


Communication:

After the transceiver and console have been paired, there are three possible
states:

1. The the driver and the USB transceiver are still in communication mode.
On the base unit the indication USB is visible (and not blinking).  This will
happen when you restart weewx within three minutes.  No further actions are
needed; the communication with the driver will start automatically.

2. The driver and the USB transceiver are no longer in communication mode.
On the base unit the indication USB is no longer visible.  This will happen
when you restart weewx after a longer period.

The protocol is as follows:

1) Start weewx with command:

sudo /etc/init.d/weewx start

2) Push once or twice shortly the USB button on your base unit

  If everything is OK you will see each 10 seconds a few log lines like this:

    Dec 18 09:11:02 weewx[30016]: KlimaLogg: RFComm: getFrame: 00 00 d7 00 56 60 64 04 9c 00 00 11 01 41 11 51
    Dec 18 09:11:02 weewx[30016]: KlimaLogg: RFComm: handleCurrentData: sleep=3.71 first=0.3 next=0.01 count=342
    Dec 18 09:11:02 weewx[30016]: KlimaLogg: RFComm: read weather data; ts=1418904662
    Dec 18 09:11:02 weewx[30016]: KlimaLogg: RFComm: setFrame: d5 00 09 00 56 00 04 9c 00 60 36 02 00 00 00 00
    Dec 18 09:11:02 weewx[30016]: KlimaLogg: MainThread: packet 11: ts=1419936058 {'outHumidity': 91, 'dateTime': 1419936058, 'outTemp': 1.3999999999999986, 'inHumidity': 33, 'inTemp': 20.5, 'usUnits': 16}

3. The driver and the USB transceiver are no longer in communication mode. On
the base unit the indication USB is blinking and the KlimaLogg Pro does not
react on a push of the USB button.  This will happen when the Klimalogg Pro
has an internal error.

The protocol is as follows:

1) Stop weewx with command:

sudo /etc/init.d/weewx stop

2) Open the battery cover of the base station and remove the middle battery.
After a battery is removed it is normal that random symbol segments appear on
the display.

3) Wait until all symbol segments on the screen are faded out.  Most of the
time this takes a few seconds but occasionally it can take several minutes
before all symbol segments are faded out, so be patient!

4) Reinsert the middle battery when the screen is blank and place the battery
cover. You will hear a beep when the base station is started.

Initially the date and time will start on 01-01-2010 00:00:00 (when the the
timezone is set to 0 h).

The base station will now search for external sensors and try to receive the
DCF time signal for three minutes. During this period the base station will
not react on a push of the USB button.

5) You can start weewx in the meantime with the command:

sudo /etc/init.d/weewx start

After three minutes (the display wiil show 00:03:00 or later) you can push
the USB button shortly.

The communication with weewx should start immediately. When everything is OK,
the USB indication willl show steady and weewx has set the date and time of
the base station to the date and time of the server.


Features:

* Date/time setting of the KlimaLogg Pro after a reboot of the KlimaLogg
  base station

The KlimaLogg Pro is not programmed to set the internal clock of the base
station by the klimalogg driver of weewx although there is a communication
protocol to send the date and time to the station. The only exception is when
the base unit is reboot (batteries out and in and the date time on the base
unit is reset to 01-01-2010 00:00:00). Then at startup of weewx the servers
date and time are written to the KlimaLogg base station.


* Alarm 'INDOOR Humidity Lo' set when the data and time of the KlimaLogg Pro
  differs too much from the server

As a workaround -for the date/time setting not working properly- the driver
checks the date and time of a new received history record against the date
and time of the server.

When a time difference of more than 300 s (5 min) is found the driver will
set the 'LOW AL RH' value to 99 % and switch the alarmfunction ON which will
trigger the 'INDOOR Humidity Lo' alarm.

This will give an alarmsound on the base station (if AlertSound is set to ON).

The alarm will be reset by the driver when a history message is received with
a date and time which differs less than 300 s from the servers date and time.


* History recording interval set to 5 minutes

The history values are used by weewx at startup to catchup missed data. Data
will be missed in case of a power fail and/or a communication loss with the
the weewx driver.

To avoid gaps in the generated graphs it is adviced to have a history interval
which is less or the same as the archive interval (default 300 s).

That's why the driver will set the recording interval to 5 minutes when the
recording interval of the base unit is 10 minutes or more (the default factory
setting is 15 minutes).

Note: A recording interval of 1 minute is not changed.


* Catchup of missed archive data at startup of weewx

At startup of weewx the driver will read the date and time of the most recent
registration in the weewx database. When needed, missed archive records are
catchupped with the data of the history records of KlimaLogg's base station.
The station can hold upto 50,200 history records.

Note: the signal quality value of the base station and the battery low alarm
data bits are not written to the archive records and thus cannot be catchupped.


* Configuration parameters are read when changed

The driver will read the configuration parameters and alarmbits of the
KlimaLogg Pro station when changed.

Note: the configuration parameters will be only sent to the debug log file
when parameter 'debug_config_data' is set to  2 or higher.


* Alarms are read when set

When an alarm is set a history message is received with 1-6 alarm records.

The alarmdata is sent to the debug log file when parameter 'debug_history_data'
is set to  2 or higher.

Note: there will be no alarm record (and logging) when the alarm is reset.


* Special timing when two or more devices with a Weather Direct Light Wireless
  USB transceiver of La CrosseTechnology are working in close distance

When for instance both a KlimaLogg Pro station and a ws28xx type weather
station like a TFA Opus, are operational in close distance the radio signals
of one station will be received by the other station.

If a time-critical message of the other station is detected  the klimalogg
driver will pause a short time to avoid the 'interception' of such a message
a second time.

Other received messages of the othes staion are just discarded. This
functionality will become active when the serial number of the own USB
transceiver is set in the [KlimaLogg] section of weewx.conf.
