klimalogg - Weewx driver for TFA KlimaLogg Pro
Version 1.1.2
Copyright 2015 Luc Heijst

Klimalogg ia a weewx extension to read data from the KlimaLogg Pro
station and up to 8 thermo/hygro sensors. It saves data to its own database,
then those data can be displayed in weewx reports.  This extension also
includes a sample skin that illustrates how to use the data.

Installation instructions:

1) Install weewx with the Simulator driver

2) Go to the bin directory of the installed weewx package

3) Run the installer for klimalogg:

./wee_extension --install [wherever you've put klimalogg archive 'kl-x.y.z.tar.gz']

4) Replace the simulator driver with the klimalogg driver

./wee_config --reconfigure --driver=user.kl --no-prompt

5) modify weewx.conf

5a) Optionally remove the [Simulator] driver section; it is no longer needed.

[Simulator]
    # This section is for the weewx weather station simulator

    # The time (in seconds) between LOOP packets.
    loop_interval = 2.5

    # The simulator mode can be either 'simulator' or 'generator'.
    # Real-time simulator. Sleep between each LOOP packet.
    mode = simulator
    # Generator.  Emit LOOP packets as fast as possible (useful for testing).
    #mode = generator

    # The start time. If not specified, the default is to use the present time.
    #start = 2011-01-01 00:00

    # The driver to use:
    driver = weewx.drivers.simulator

	##############################################################################

5b)	Change the Standard skin of the [[StandardReport]] section to the kl skin.
	The KlimaLogg is not a 'standard' weather station, so the graphs and reports
	in skin Standard will not work properly, so change this:
			skin = Standard
			NEW_skin = kl
	to this:
			skin = kl

5c) Specify the kl_binding instead of wx_binding.  Klimalogg works best with
    its own schema, not the wview schema that is the default for weewx.  To
    make this happen you must change the data binding in two places, the
    StdReport and StdArchive sections:

	Change in the [StdReport] section the databinding to kl_binding, so change this:
		data_binding = wx_binding
		NEW_data_binding = kl-binding
	to this:
		data_binding = kl-binding

	Change in the [StdArchive] section the databinding to kl_binding, so change this:
		data_binding = wx_binding
		NEW_data_binding = kl-binding
	to this:
		data_binding = kl-binding

5d) Save the contents of weewx.conf

6) restart weewx:

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start
