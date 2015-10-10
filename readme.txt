klimalogg - Weewx driver for TFA KlimaLogg Pro
Copyright 2015 Luc Heijst

Klimalogg is a weewx extension to read data from the KlimaLogg Pro
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

4a) Specify the kl_binding instead of wx_binding.  Klimalogg works best with
    its own schema, not the wview schema that is the default for weewx.  To
    make this happen you must change the data binding in two places, the
    StdReport and StdArchive sections:

[StdReport]
    ...
    data_binding = kl_binding

[StdArchive]
    ...
    data_binding = kl_binding

4b) Remove the [[StandardReport]] section.  Either remove it completely, or
    comment the section.  The KlimaLogg is not a 'standard' weather station,
    so the graphs and reports in skin Standard will not work properly.

4c) Optionally remove the [Simulator] driver section; it is no longer needed.

5) Restart weewx:

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
