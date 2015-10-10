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

  (you may have to specify the full path to wee_extension, and you may have
   to specify the full path to the kl .tar.gz file)

3) Replace the simulator driver with the klimalogg driver:

  wee_config --reconfigure --driver=user.kl --no-prompt

4) modify weewx.conf

4a) Remove the [[StandardReport]] section.  The KlimaLogg is not a 'standard'
    weather station, so the graphs and reports in skin Standard doesn't make
    sense.

4b) Klimalogg has more sensors than a 'standard' weather station and works
    best with its own database schema.  So replace the wview schema with the
    kl schema in the [wx-binding] section.  Replace this:

        schema = schemas.wview.schema

    with this:

        schema = user.kl.schema

4c) Optionally remove the [Simulator] driver section; it is no longer needed.

6) restart weewx:

sudo /etc/init.d/weewx stop
sudo /etc/init.d/weewx start

This will result in a skin called kl with a single web page that illustrates
how to use the klimalogg data.

Make sure you have installed in your system the used fonts in the kl skin, 
otherwise you may notice funky symbols in the plots like the degrees symbol.
