kl - weewx driver for the Klimalogg Pro

The klimalogg hardware supports up to 8 sensors.  You can use either the
default schema (the wview schema), which supports up to 5 temperature sensors
and 4 humidity sensors, or the klimalogg schema, which supports up to 8
temperature sensors and 8 humidity sensors.


Installation for using the wview schema:

1) Install the extension:

  setup.py install --extension weewx-kl.tar.gz

2) Start weewx:

  sudo /etc/init.d/weewx start


Instructions for using the klimalogg schema:

1) Install the extension:

  setup.py install --extension weewx-kl.tar.gz

2) Modify weewx.conf to use the klimalogg schema:

[DataBindings]
   [[wx_binding]]
       database = archive_sqlite
       table_name = archive
       manager = weewx.wxmanager.WXDaySummaryManager
       schema = user.kl.schema   # use kl schema instead of wview schema

3) Start weewx:

  sudo /etc/init.d/weewx start
