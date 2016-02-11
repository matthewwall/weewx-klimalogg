klimalogg - Weewx driver for TFA KlimaLogg Pro
Copyright 2016 Luc Heijst

Klimalogg ia a weewx extension to read data from the KlimaLogg Pro
station and up to 8 thermo/hygro sensors. It saves data to its own database,
then those data can be displayed in weewx reports.  This extension also
includes a sample skin that illustrates how to use the data.

Installation instructions:

1) Install weewx, select Simulator as the weather station

  (follow instructions in the weewx user guide)

2) Download the klimalogg driver

  wget https://github.com/matthewwall/weewx-klimalogg/archive/master.zip

3) Install the klimalogg driver and skin

  wee_extension --install weewx-klimalogg-master.zip

4) Replace the simulator driver with the klimalogg driver

  wee_config --reconfigure --driver=user.kl --no-prompt

5) modify weewx.conf

5a) Specify the kl_binding instead of wx_binding.  Klimalogg works best with
    its own schema, not the wview schema that is the default for weewx.  To
    make this happen you must change the data binding from wx_binding to
    kl_binding in two places, the StdReport and StdArchive sections

    data_binding = kl_binding

5b) Optionally remove the [Simulator] driver section; it is no longer needed.

5c) Optionally remove the [[StandardReport]] section of [StdReport].
    The KlimaLogg is not a 'standard' weather station, so the graphs and
    reports in skin Standard will not work properly.

6) restart weewx:

  sudo /etc/init.d/weewx stop
  sudo /etc/init.d/weewx start
