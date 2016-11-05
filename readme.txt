klimalogg - WeeWX driver for TFA KlimaLogg Pro
Copyright 2016 Luc Heijst

Klimalogg is a weewx extension to read data from the KlimaLogg Pro station
and up to 8 thermo/hygro sensors. It saves data to its own database, then
those data can be displayed in weewx reports.  This extension also includes
a sample skin that illustrates how to use the data.

Installation instructions:

1) Install weewx.  During the install, select Simulator as the weather station

  For the quickest, easiest installation on Debian systems:
  http://weewx.com/apt/

  For detailed instructions:
  http://weewx.com/docs/usersguide.htm

1a) Be sure that weewx is not running

  sudo /etc/init.d/weewx stop

1b) Move aside any existing weewx database, if one exists

  sudo mv /var/lib/weewx/weewx.sdb /var/lib/weewx/weewx.sdb-old

2) Download the klimalogg driver

  wget -O weewx-kl.zip https://github.com/matthewwall/weewx-klimalogg/archive/master.zip

3) Install the klimalogg driver and skin

  sudo wee_extension --install weewx-kl.zip

4) Configure weewx to use the klimalogg driver

  sudo wee_config --reconfigure --driver=user.kl --no-prompt

5) Start weewx:

  sudo /etc/init.d/weewx start


Reading of historical records

When weewx starts, it will attempt to read historical records from the console.
The Klimalogg Pro can store over 50,000 records.  If the logger is full it
can take some time to download the records.  For example, on a Raspberry Pi 1B,
reading 51143 records took 15 hours.  Systems with faster I/O will probably
take considerably less time.


Pairing

The Klimalogg console must be associated with a USB transceiver in a process
called 'pairing'.  To pair the console with the USB transceiver, press the USB
button on the console.


Modifications to the weewx configuration file

Installing this extension will make the following changes to weewx.conf:

Change wx_binding to kl_binding.  Klimalogg works best with its own schema,
not the wview schema that is the default for weewx.  This requires changing
the data binding from wx_binding to kl_binding in two places, the StdReport
and StdArchive sections

Remove the [Simulator] driver section if it exists.

Remove the [[StandardReport]] section of [StdReport] if it exists.  The
KlimaLogg is not a 'standard' weather station, so the graphs and reports
in skin Standard will not work properly.
