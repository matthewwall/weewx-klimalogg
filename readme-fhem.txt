1) Install weewx and the klimalogg driver

2) The skin output file "fhem.txt" must go to the public_html\fhem folder of
   your webserver.

3) The add_to_fhem.cfg is a configuration file for FHEM's module HTTPMOD. 
   This file contains the configuration examples for current values only;
   for min/max values, heatindex and dewpoint values use similar syntax
   for setting readingXXExpr /readingXXName / readingXXRegex.

Thanks to Steffen for sorting this out and sharing the fhem files with us.
