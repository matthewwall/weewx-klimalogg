klimalogg - Weewx driver for TFA KlimaLogg Pro
Copyright 2015 Luc Heijst

Klimalogg ia a weewx extension to read data from the KlimaLogg Pro
station and up to 8 thermo/hygro sensors. It saves data to its own database,
then those data can be displayed in weewx reports.  This extension also
includes a sample skin that illustrates how to use the data.

Installation instructions:

1) Install weewx with the Simulator driver

2) Run the installer for klimalogg:

  wee_extension --install kl-x.y.z.tar.gz

3) Replace the simulator driver with the klimalogg driver:

  wee_config --reconfigure --driver=user.kl --no-prompt

4) Modify weewx.conf:

4a) Remove the [[StandardReport]] section.  Either remove it completely, or
    comment the section.  The KlimaLogg is not a 'standard' weather station,
    so the graphs and reports in skin Standard will not work properly.

4b) Optionally remove the [Simulator] driver section; it is no longer needed.

5) Restart weewx:

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
