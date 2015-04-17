# TFA KlimaLogg driver for weewx
# $Id: kl.py 1246 2015-02-07 04:40:23Z mwall $
#
# Copyright 2015 Luc Heijst, Matthew Wall
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.
#
# See http://www.gnu.org/licenses/
#
# The driver logic is adapted from the ws28xx driver for LaCrosse 2800 and
# TFA Primus and Opus weather stations.
#
# Thanks to Michael Schulze for making the sensor map dynamic.
#
# Also many thanks to our testers, in special Boris Smeds and Raffael Boesch.
# Without their help we couldn't have written this driver.
#

"""
Classes and functions for interfacing with KlimaLogg weather stations.

TFA makes stations in the KlimaLogg series

KlimaLoggPro is the software provided by TFA.

KlimaLoggPro provides the following weather station settings:

  display contrast: 0-7
  alert: ON|OFF
  DCF time reception: ON|OFF
  time display: 12|24 hour
  temperature display: C|F
  time zones: -12hr ... + 12hr
  recording intervals: 1/5/15/20/30/60 min/2/3/6 hours

KlimaLoggPro 'CurrentWeather' view is updated as data arrive from the
console.  The console sends current weather data approximately every 15
seconds (base station) / 10 seconds extra sensors.

Historical data are updated less frequently - every 15 minutes in the default
configuration.

Apparently the station console determines when data will be sent, and, once
paired (synchronized), the transceiver is always listening.  The station console
sends a broadcast once a day at midnight*.  If the transceiver responds, the
station console may continue to broadcast data, depending on the transceiver
response and the timing of the transceiver response.
* when DCF time reception is OFF

The following information was obtained by logging messages from the kl.py
driver in weewx and by capturing USB messages between KlimaLoggPro 
and the TFA KlimaLogg Pro Weather Station via windows programs 
USBPcap version 1.0.0.7 and Wireshark version win64-1.12.1

Pairing

The transceiver must be paired (synchronized) with a console before it can
receive data.  Each frame sent by the console includes the device identifier
of the transceiver with which it is paired (synchronized).

Synchronizing

When the console and transceiver stop communicating, they can be synchronized
by one of the following methods:

- Push the USB button on the console
- Wait until the next day at 00:00 (console clock)
Note: starting the kl driver automatically initiates synchronisation.

A Current Weather message is received by the transceiver from the
console. After a setState message is received from the driver,
the console and transceiver will have been synchronized.

Timing

Current Weather messages, History messages, getConfig/setConfig messages, and
setTime messages each have their own timing.  Missed History messages - as a
result of bad timing - result in console and transceiver becoming out of sync.

Current Weather

The console periodically sends Current Weather messages, each with the latest
values from the sensors.  The CommModeInterval determines how often the console
will send Current Weather messages.

History

The console records data periodically at an interval defined by the
HistoryInterval parameter.  The factory default setting is 15 minutes.
Each history record contains a timestamp.  Timestamps use the time from the
console clock.  The console can record up to 50,000 history records.

Reading 40,500 history records took 47:04 minutes using this driver on a Synology DS213+ disk station.
An average of 70 ms per history record.

Reading 1501 history records took 204 seconds using this driver on a Raspberry Pi B+
using a uSD card (class > 10 / UHS-I). The DB writing took 734 seconds.
An average of 135 ms per history record. The database storage took 490 ms per history record.

Reading 81 history records took 17 seconds using this driver on a Ubuntu Netbook.
An average of 210 ms per history record. The database storage took 210 ms per history record.

-------------------------------------------------------------------------------

Message Types - version 0.3 (2015-01-17)

The first byte of a message determines the message type.

ID   Type               Length

00   GetFrame           0x111 (273)
d0   SetRX              0x15  (21)
d1   SetTX              0x15  (21)
d5   SetFrame           0x111 (273)
d7   SetState           0x15  (21)
d8   SetPreamblePattern 0x15  (21)
d9   Execute            0x0f  (15)
dc   ReadConfigFlash<   0x15  (21)
dd   ReadConfigFlash>   0x15  (21)
de   GetState           0x0a  (10)
f0   WriteReg           0x05  (5)

In the following sections, some messages are decomposed using the following
structure:

  start   position in message buffer
  hi-lo   data starts on first (hi) or second (lo) nibble
  chars   data length in characters (nibbles)
  rem     remark
  name    variable

-------------------------------------------------------------------------------
1. GetFrame (273 bytes)

Response type:
10: WS SetTime / SetConfig - Data written
20: GetConfig
30: Current Weather
40: Actual / Outstanding History
50: Request Read-History (MEM % > 0)
51: Request First-Time Config
52: Request SetConfig
53: Request SetTime

000:  00 00 07 DevID LI 10 SQ CfgCS xx xx xx xx xx xx xx xx xx  Time/Config written
000:  00 00 7d DevID LI 20 SQ [ConfigData .. .. .. .. .. CfgCS] GetConfig
000:  00 00 e5 DevID LI 30 SQ CfgCS [CurData .. .. .. .. .. ..  Current Weather
000:  00 00 b5 DevID LI 40 SQ CfgCS LateAdr  ThisAdr  [HisData  Outstanding History
000:  00 00 b5 DevID LI 40 SQ CfgCS LateAdr  ThisAdr  [HisData  Actual History
000:  00 00 b5 DevID LI 50 MP CfgCS xx xx xx xx xx xx xx xx xx  Request Read History
000:  00 00 07 f0 f0 ff 51 SQ CfgCS xx xx xx xx xx xx xx xx xx  Request FirstConfig
000:  00 00 07 DevID LI 52 SQ CfgCS xx xx xx xx xx xx xx xx xx  Request SetConfig
000:  00 00 07 DevID LI 53 SQ CfgCS xx xx xx xx xx xx xx xx xx  Request SetTime

00:    messageID
01:    00
02:    Message Length (starting with next byte)
03-04: DeviceID          [devID]
05:    LI = Logger ID / ff (at init)    Logger ID: 0-9 = Logger 1 - logger 10
06:    responseType

Additional bytes all GetFrame messages except Request Read History
07:    SQ = Signal Quality   (in steps of 5)

Additional bytes GetFrame message Request Read History
07:    MP = Memory Percentage not read to server   (in steps of 5)

Additional bytes all GetFrame messages except ReadConfig
08-9:  Config checksum [CfgCS]

Additional bytes Actual / Outstanding History:
10-12: LatestHistoryAddress [LateAdr] 3 bytes (Latest to sent)
       LatestHistoryRecord = (LatestHistoryAddress - 0x07000) / 32 
13-15: ThisHistoryAddress   [ThisAdr] 3 bytes (Outstanding)
       ThisHistoryRecord = (ThisHistoryAddress - 0x070000) / 32

Additional bytes ReadConfig and WriteConfig
Config checksum [CfgCS] (CheckSum = sum of bytes (5-122) + 7)

-------------------------------------------------------------------------------
2. SetRX message (21 bytes)

000:  d0 00 00 00 00 00 00 00 00 00   00 00 00 00 00 00 00 00 00 00
020:  00 
  
00:    messageID
01-20: 00

-------------------------------------------------------------------------------
3. SetTX message (21 bytes)

000: d1 00 00 00 00 00 00 00 00 00   00 00 00 00 00 00 00 00 00 00
020: 00 
  
00:    messageID
01-20: 00

-------------------------------------------------------------------------------
4. SetFrame message (273 bytes)

Action:
00: rtGetHistory     - Ask for History message
01: rtSetTime        - Ask for Send Time to weather station message
02: rtSetConfig      - Ask for Send Config to weather station message
02: rtReqFirstConfig - Ask for Send (First) Config to weather station message
03: rtGetConfig      - Ask for Config message
04: rtGetCurrent     - Ask for Current Weather message
20: Send Config      - Send Config to WS
60: Send Time        - Send Time to WS (works only if station is just initialized)

000:  d5 00 0b DevID LI 00 CfgCS 8ComInt ThisAdr xx xx xx  rtGetHistory
000:  d5 00 0b DevID LI 01 CfgCS 8ComInt ThisAdr xx xx xx  rtReqSetTime
000:  d5 00 0b f0 f0 ff 02 ff ff 8ComInt ThisAdr xx xx xx  rtReqFirstConfig
000:  d5 00 0b DevID LI 02 CfgCS 8ComInt ThisAdr xx xx xx  rtReqSetConfig
000:  d5 00 0b DevID LI 03 CfgCS 8ComInt ThisAdr xx xx xx  rtGetConfig
000:  d5 00 0b DevID LI 04 CfgCS 8ComInt ThisAdr xx xx xx  rtGetCurrent
000:  d5 00 7d DevID LI 20 [ConfigData  .. .. .. .. CfgCS] Send Config
000:  d5 00 0d DevID LI 60 CfgCS [TimeData .. .. .. .. ..  Send Time

All SetFrame messages:
00:    messageID
01:    00
02:    Message length (starting with next byte)
03-04: DeviceID           [DevID]
05:    LI/ff              Logger ID: 0-9 = Logger 1 - logger 10
06:    Action
07-08: Config checksum    [CfgCS]

Additional bytes rtGetCurrent, rtGetHistory, rtSetTime messages:
09hi:    0x80               (meaning unknown, 0.5 byte)
09lo-10: ComInt             [cINT]    1.5 byte
11-13:   ThisHistoryAddress [ThisAdr] 3 bytes (high byte first)

Additional bytes Send Time message:
09:    seconds
10:    minutes
11:    hours
12hi:  day_lo         (low byte)
12lo:  DayOfWeek      (mo=1, tu=2, we=3, th=4, fr=5, sa=6 su=7)
13hi:  month_lo       (low byte)
13lo:  day_hi         (high byte)
14hi:  (year-2000)_lo (low byte)
14lo:  month_hi       (high byte)
15hi:  not used
15lo:  (year-2000)_hi (high byte)

-------------------------------------------------------------------------------
5. SetState message

000:  d7 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00:    messageID
01-14: 00

-------------------------------------------------------------------------------
6. SetPreamblePattern message

000:  d8 aa 00 00 00 00 00 00 00 00 00 00 00 00 00

00:    messageID
01:    ??
02-14: 00

-------------------------------------------------------------------------------
7. Execute message

000:  d9 05 00 00 00 00 00 00 00 00 00 00 00 00 00

00:    messageID
01:    ??
02-14: 00

-------------------------------------------------------------------------------
8. ReadConfigFlash in - receive data

0000: dc 0a 01 f5 00 01 8d 18 01 02 12 01 0d 01 07 ff ff ff ff ff 00 - freq correction
0000: dc 0a 01 f9 01 02 12 01 0d 01 07 ff ff ff ff ff ff ff ff ff 00 - transceiver data

00:    messageID
01:    length
02-03: address

Additional bytes frequency correction
05lo-07hi: frequency correction

Additional bytes transceiver data
05-10:     serial number
09-10:     DeviceID [devID]

-------------------------------------------------------------------------------
9. ReadConfigFlash out - ask for data

000: dd 0a 01 f5 58 d8 34 00 90 10 07 01 08 f2 ee - Ask for freq correction
000: dd 0a 01 f9 cc cc cc cc 56 8d b8 00 5c f2 ee - Ask for transceiver data

00:    messageID
01:    length
02-03: address
04-14: cc

-------------------------------------------------------------------------------
10. GetState message

000:  de 14 00 00 00 00 (between SetPreamblePattern and first de16 message)
000:  de 15 00 00 00 00 Idle message
000:  de 16 00 00 00 00 Normal message
000:  de 0b 00 00 00 00 (detected via USB sniffer)

00:    messageID
01:    stateID
02-05: 00

-------------------------------------------------------------------------------
11. Writereg message

000: f0 08 01 00 00 - AX5051RegisterNames.IFMODE
000: f0 10 01 41 00 - AX5051RegisterNames.MODULATION
000: f0 11 01 07 00 - AX5051RegisterNames.ENCODING
...
000: f0 7b 01 88 00 - AX5051RegisterNames.TXRATEMID 
000: f0 7c 01 23 00 - AX5051RegisterNames.TXRATELO
000: f0 7d 01 35 00 - AX5051RegisterNames.TXDRIVER

00:    messageID
01:    register address
02:    01
03:    AX5051RegisterName
04:    00

-------------------------------------------------------------------------------
12. Current Weather message

Note: if start == x.5: StartOnLowNibble else: StartOnHiNibble
      
start  chars name
0      4  DevID
2      2  LI = Logger ID: 0-9 = Logger 1 - logger 10
3      2  Action
4      2  Quality
5      4  DeviceCS
7      8  Humidity0_MaxDT
11     8  Humidity0_MinDT
15     2  Humidity0_Max
16     2  Humidity0_Min
17     2  Humidity0
18     1  '0'
18.5   8  Temp0_MaxDT
22.5   8  Temp0_MinDT
26.5   3  Temp0_Max
28     3  Temp0_Min
29.5   3  Temp0
31     8  Humidity1_MaxDT
35     8  Humidity1_MinDT
39     2  Humidity1_Max
40     2  Humidity1_Min
41     2  Humidity1
42     1  '0'
42.5   8  Temp1_MaxDT
46.5   8  Temp1_MinDT
50.5   3  Temp1_Max
52     3  Temp1_Min
53.5   3  Temp1
55     8  Humidity2_MaxDT
59     8  Humidity2_MinDT
63     2  Humidity2_Max
64     2  Humidity2_Min
65     2  Humidity2
66     1  '0'
66.5   8  Temp2_MaxDT
70.5   8  Temp2_MinDT
74.5   3  Temp2_Max
76     3  Temp2_Min
77.5   3  Temp2
79     8  Humidity3_MaxDT
83     8  Humidity3_MinDT
87     2  Humidity3_Max
88     2  Humidity3_Min
89     2  Humidity3
90     1  '0'
90.5   8  Temp3_MaxDT
94.5   8  Temp3_MinDT
98.5   3  Temp3_Max
100    3  Temp3_Min
101.5  3  Temp3
103    8  Humidity4_MaxDT
107    8  Humidity4_MinDT
111    2  Humidity4_Max
112    2  Humidity4_Min
113    2  Humidity4
114    1  '0'
114.5  8  Temp4_MaxDT
118.5  8  Temp4_MinDT
122.5  3  Temp4_Max
124    3  Temp4_Min
125.5  3  Temp4
127    8  Humidity5_MaxDT
131    8  Humidity5_MinDT
135    2  Humidity5_Max
136    2  Humidity5_Min
137    2  Humidity5
138    1  '0'
138.5  8  Temp5_MaxDT
142.5  8  Temp5_MinDT
146.5  3  Temp5_Max
148    3  Temp5_Min
149.5  3  Temp5
151    8  Humidity6_MaxDT
155    8  Humidity6_MinDT
159    2  Humidity6_Max
160    2  Humidity6_Min
161    2  Humidity6
162    1  '0'
162.5  8  Temp6_MaxDT
166.5  8  Temp6_MinDT
170.5  3  Temp6_Max
172    3  Temp6_Min
173.5  3  Temp6
175    8  Humidity7_MaxDT
179    8  Humidity7_MinDT
183    2  Humidity7_Max
184    2  Humidity7_Min
185    2  Humidity7
186    1  '0'
186.5  8  Temp7_MaxDT
190.5  8  Temp7_MinDT
194.5  3  Temp7_Max
196    3  Temp7_Min
197.5  3  Temp7
199    8  Humidity8_MaxDT
203    8  Humidity8_MinDT
207    2  Humidity8_Max
208    2  Humidity8_Min
209    2  Humidity8
210    1  '0'
210.5  8  Temp8_MaxDT
214.5  8  Temp8_MinDT
218.5  3  Temp8_Max
220    3  Temp8_Min
221.5  3  Temp8
223    12 AlarmData* ('000000000000')
229    0  end

* AlarmData group 1: xx xx xx xx xx xx 00 00 00 00 00 00
80	0	0	0	0	0	Sensor 8 TX batt low
40	0	0	0	0	0	Sensor 7 TX batt low
20	0	0	0	0	0	Sensor 6 TX batt low
10	0	0	0	0	0	Sensor 5 TX batt low
8	0	0	0	0	0	Sensor 4 TX batt low
4	0	0	0	0	0	Sensor 3 TX batt low
2	0	0	0	0	0	Sensor 2 TX batt low
1	0	0	0	0	0	Sensor 1 TX batt low
0	80	0	0	0	0	KlimaLogg RX batt low
0	40	0	0	0	0
0	20	0	0	0	0
0	10	0	0	0	0
0	8	0	0	0	0	Temp8Min
0	4	0	0	0	0	Temp8Max
0	2	0	0	0	0	Humidity8Min
0	1	0	0	0	0	Humidity8Max
0	0	80	0	0	0	Temp7Min
0	0	40	0	0	0	Temp7Max
0	0	20	0	0	0	Humidity7Min
0	0	10	0	0	0	Humidity7Max
0	0	8	0	0	0	Temp6Min
0	0	4	0	0	0	Temp6Max
0	0	2	0	0	0	Humidity6Min
0	0	1	0	0	0	Humidity6Max
0	0	0	80	0	0	Temp5Min
0	0	0	40	0	0	Temp5Max
0	0	0	20	0	0	Humidity5Min
0	0	0	10	0	0	Humidity5Max ^
0	0	0	8	0	0	Temp4Min
0	0	0	4	0	0	Temp4Max
0	0	0	2	0	0	Humidity4Min
0	0	0	1	0	0	Humidity4Max
0	0	0	0	80	0	Temp3Min
0	0	0	0	40	0	Temp3Max
0	0	0	0	20	0	Humidity3Min
0	0	0	0	10	0	Humidity3Max
0	0	0	0	8	0	Temp2Min
0	0	0	0	4	0	Temp2Max
0	0	0	0	2	0	Humidity2Min
0	0	0	0	1	0	Humidity2Max
0	0	0	0	0	80	Temp1Min v
0	0	0	0	0	40	Temp1Max
0	0	0	0	0	20	Humidity1Min
0	0	0	0	0	10	Humidity1Max
0	0	0	0	0	8	Temp0Min
0	0	0	0	0	4	Temp0Max
0	0	0	0	0	2	Humidity0Min
0	0	0	0	0	1	Humidity0Max

* AlarmData group 2: 00 00 00 00 00 00 xx xx xx xx xx xx
The meaning of these bits is unknown

-------------------------------------------------------------------------------
date conversion: (2013-06-21)
byte1     1 dec: year+=2000+10*byte1 
byte2     3 dec: year+=byte2 
byte3     6 hex: month+=byte3 
byte4     2 dec: day+=10*byte4
byte5     1 dec: day+=byte5 

time conversion: (00:52)
byte1     0 hex: if byte1 >= 10 then hours=10+byte1 else hours=byte1
byte2     5 hex: if byte2 >= 10 then hours+=10; minutes=(byte2-10)*10 else minutes=byte2*10
byte3     2 dec: minutes+=byte3

humidity conversion: (50)
byte1     5 humidity=byte1*10
byte2     0 humidity+=byte2

temp conversion: (23.2)
byte1     6 temp=(byte1*10)-40
byte2     3 temp+=byte2
byte3     2 temp+=(byte3*0.1)
-------------------------------------------------------------------------------

Example of message in hex bytes:

0000   00 00 e5 01 07 00 30 64 1a b1 13 62 10 52 14 91
0010   85 a3 98 32 55 01 49 17 5d 81 41 27 43 87 36 38
0020   56 56 14 a1 87 29 14 91 85 a4 89 38 aa 01 49 17
0030   5d 51 49 23 75 17 44 49 4a aa 14 a1 41 c5 14 91
0040   85 b2 91 40 64 01 49 17 5e 91 4a 22 7b 27 32 50
0050   26 42 14 a2 04 c0 14 91 85 a4 84 38 67 01 49 17
0060   5d 61 4a 22 6c 07 44 50 06 38 14 a2 06 c7 14 91
0070   85 b2 87 41 aa 01 49 17 5d 31 49 19 81 57 40 52
0080   1a aa aa 4a a4 aa aa 4a a4 aa aa aa aa 0a a4 aa
0090   4a aa a4 aa 4a aa aa aa aa aa aa 4a a4 aa aa 4a
00a0   a4 aa aa aa aa 0a a4 aa 4a aa a4 aa 4a aa aa aa
00b0   aa aa aa 4a a4 aa aa 4a a4 aa aa aa aa 0a a4 aa
00c0   4a aa a4 aa 4a aa aa aa aa aa aa 4a a4 aa aa 4a
00d0   a4 aa aa aa aa 0a a4 aa 4a aa a4 aa 4a aa aa aa
00e0   aa aa 00 00 00 00 00 00 39 c0 00 00 00 00 00 00
00f0   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0100   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
0110   00

Example of debug log:

Jan 16 17:45:24  KlimaLogg: RFComm: Temp0=      21.1  _Min= 10.6 (2013-12-06 00:41:00)  _Max= 33.2 (2014-06-10 19:03:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Humidity0=    39  _Min=   26 (2014-12-30 03:58:00)  _Max=   76 (2014-08-04 09:36:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Temp1=      11.8  _Min=-10.4 (2014-12-30 01:38:00)  _Max= 48.2 (2014-04-09 13:23:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Humidity1=    66  _Min=   23 (2014-09-25 00:58:00)  _Max=   95 (2014-11-03 09:52:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Temp2=       8.2  _Min=  5.9 (2014-11-29 08:40:00)  _Max= 27.6 (2014-07-29 19:29:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Humidity2=    67  _Min=   35 (2014-01-31 12:19:00)  _Max=   77 (2014-11-24 13:32:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Temp3=       6.6  _Min=  5.1 (2014-01-29 17:43:00)  _Max= 20.7 (2014-08-03 15:49:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Humidity3=    79  _Min=   58 (2014-01-26 10:24:00)  _Max=   88 (2014-08-04 13:52:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Temp4=      15.6  _Min= 11.9 (2014-10-31 10:01:00)  _Max= 28.2 (2014-11-11 12:10:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Humidity4=    53  _Min=   33 (2014-12-30 08:13:00)  _Max=   73 (2014-11-04 12:01:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Temp5=       8.7  _Min= -2.4 (2014-01-13 03:27:00)  _Max= 41.5 (2014-07-28 15:45:00)
Jan 16 17:45:24  KlimaLogg: RFComm: Humidity5=    71  _Min=   36 (2014-06-09 19:10:00)  _Max=   84 (2014-10-31 13:12:00)

-------------------------------------------------------------------------------
13a. History Message - example with 6 alarm records

Each of the six alarm records can be replaced by a history record.
Note: if start == x.5: StartOnLowNibble else: StartOnHiNibble

start chars name

0      4    DevID
2      2    LI = Logger ID: 0-9 = Logger 1 - logger 10
3      2    Action
4      2    Quality
5      4    DeviceCS
7      6    LatestAddress
10     6    ThisAddress
13     26   Pos6 not used
26     2    Pos6HumidityHi
27     2    pos6HumidityLo
28     2    Pos6Humidity
29     3    Pos6TempHi
30,5   3    pos6TempLo
32     1    '0'
32,5   3    Pos6Temp
34     1    Pos6Alarmdata; 1=Hum Hi Al, 2=Hum Lo Al, 4=Tmp Hi Al, 8=Tmp Lo Al
34,5   1    Pos6Sensor; 0=KLP, 1-8
35     10   Pos6DT
40     2    'ee'
41     26   Pos5 not used
54     2    Pos5HumidityHi
55     2    Pos5HumidityLo
56     2    Pos5Humidity
57     3    Pos5TempHi
58,5   3    Pos5TempLo
60     1    '0'
60,5   3    Pos5Temp
62     1    Pos5Alarmdata; 1=Hum Hi Al, 2=Hum Lo Al, 4=Tmp Hi Al, 8=Tmp Lo Al
62,5   1    Pos5Sensor; 0=KLP, 1-8
63     10   Pos5DT
68     2    'ee'
69     26   Pos4 not used
82     2    Pos4HumidityHi
83     2    Pos4HumidityLo
84     2    Pos4Humidity
85     3    Pos4TempHi
86,5   3    Pos4TempLo
88     1    '0'
88,5   3    Pos4Temp
90     1    Pos4Alarmdata; 1=Hum Hi Al, 2=Hum Lo Al, 4=Tmp Hi Al, 8=Tmp Lo Al
90,5   1    Pos4Sensor; 0=KLP, 1-8
91     10   Pos4DT
96     2    'ee'
97     26   Pos3 not used
110    2    Pos3HumidityHi
111    2    Pos3HumidityLo
112    2    Pos3Humidity
113    3    Pos3TempHi
114,5  3    Pos3TempLo
116    1    '0'
116,5  3    Pos3Temp
118    1    Pos3Alarmdata; 1=Hum Hi Al, 2=Hum Lo Al, 4=Tmp Hi Al, 8=Tmp Lo Al
118,5  1    Pos3Sensor; 0=KLP, 1-8
119    10   Pos3DT
124    2    'ee'
125    26   Pos2 not used
138    2    Pos2HumidityHi
139    2    Pos2HumidityLo
140    2    Pos2Humidity
141    3    Pos2TempHi
142,5  3    Pos2TempLo
144    1    '0'
144,5  3    Pos2Temp
146    1    Pos2Alarmdata; 1=Hum Hi Al, 2=Hum Lo Al, 4=Tmp Hi Al, 8=Tmp Lo Al
146,5  1    Pos2Sensor; 0=KLP, 1-8
147    10   Pos2DT
152    2    'ee'
153    26   Pos1 not used
166    2    Pos1HumidityHi
167    2    Pos1HumidityLo
168    2    Pos1Humidity
169    3    Pos1TempHi
170,5  3    Pos1TempLo
172    1    '0'
172,5  3    Pos1Temp
174    1    Pos1Alarmdata; 1=Hum Hi Al, 2=Hum Lo Al, 4=Tmp Hi Al, 8=Tmp Lo Al
174,5  1    Pos1Sensor; 0=KLP, 1-8
175    10   Pos1DT
180    2    'ee'
181    0    End message

-------------------------------------------------------------------------------
13b. History Message - example with 6 history records

Each of the six history records can be replaced by an alarm record.
Note: if start == x.5: StartOnLowNibble else: StartOnHiNibble

start   chars note  name

0       4     1     DevID
2       2           LI = Logger ID: 0-9 = Logger 1 - logger 10
3       2     2     Action
4       2     3     Quality
5       4     4     DeviceCS
7       6     5     LatestAddress
10      6     6     ThisAddress
13      2     7     Pos6Humidity8
14      2           Pos6Humidity7
15      2           Pos6Humidity6
16      2           Pos6Humidity5
17      2           Pos6Humidity4
18      2           Pos6Humidity3
19      2           Pos6Humidity2
20      2           Pos6Humidity1
21      2           Pos6Humidity0
22      1           '0'
22.5    3           Pos6Temp8
24      3           Pos6Temp7
25.5    3           Pos6Temp6
27      3           Pos6Temp5
28.5    3           Pos6Temp4
30      3           Pos6Temp3
31.5    3           Pos6Temp2
33      3           Pos6Temp1
34.5    3           Pos6Temp0
36     10           Pos6DT
41      2           Pos5Humidity8
42      2           Pos5Humidity7
43      2           Pos5Humidity6
44      2           Pos5Humidity5
45      2           Pos5Humidity4
46      2           Pos5Humidity3
47      2           Pos5Humidity2
48      2           Pos5Humidity1
49      2           Pos5Humidity0
50      1           '0'
50.5    3           Pos5Temp8
52      3           Pos5Temp7
53.5    3           Pos5Temp6
55      3           Pos5Temp5
56.5    3           Pos5Temp4
58      3           Pos5Temp3
59.5    3           Pos5Temp2
61      3           Pos5Temp1
62.5    3           Pos5Temp0
64     10           Pos5DT
69      2           Pos4Humidity8
70      2           Pos4Humidity7
71      2           Pos4Humidity6
72      2           Pos4Humidity5
73      2           Pos4Humidity4
74      2           Pos4Humidity3
75      2           Pos4Humidity2
76      2           Pos4Humidity1
77      2           Pos4Humidity0
78      1           '0'
78.5    3           Pos4Temp8
80      3           Pos4Temp7
81.5    3           Pos4Temp6
83      3           Pos4Temp5
84.5    3           Pos4Temp4
86      3           Pos4Temp3
87.5    3           Pos4Temp2
89      3           Pos4Temp1
90.5    3           Pos4Temp0
92     10           Pos4DT
97      2           Pos3Humidity8
98      2           Pos3Humidity7
99      2           Pos3Humidity6
100     2           Pos3Humidity5
101     2           Pos3Humidity4
102     2           Pos3Humidity3
103     2           Pos3Humidity2
104     2           Pos3Humidity1
105     2           Pos3Humidity0
106     1           '0'
106.5   3           Pos3Temp8
108     3           Pos3Temp7
109.5   3           Pos3Temp6
111     3           Pos3Temp5
112.5   3           Pos3Temp4
114     3           Pos3Temp3
115.5   3           Pos3Temp2
117     3           Pos3Temp1
118.5   3           Pos3Temp0
120    10           Pos3DT
125     2           Pos2Humidity8
126     2           Pos2Humidity7
127     2           Pos2Humidity6
128     2           Pos2Humidity5
129     2           Pos2Humidity4
130     2           Pos2Humidity3
131     2           Pos2Humidity2
132     2           Pos2Humidity1
133     2           Pos2Humidity0
134     1           '0'
134.5   3           Pos2Temp8
136     3           Pos2Temp7
137.5   3           Pos2Temp6
139     3           Pos2Temp5
140.5   3           Pos2Temp4
142     3           Pos2Temp3
143.5   3           Pos2Temp2
145     3           Pos2Temp1
146.5   3           Pos2Temp0
148    10           Pos2DT
153     2     8     Pos1Humidity8
154     2           Pos1Humidity7
155     2           Pos1Humidity6
156     2           Pos1Humidity5
157     2           Pos1Humidity4
158     2           Pos1Humidity3
159     2           Pos1Humidity2
160     2           Pos1Humidity1
161     2           Pos1Humidity0
162     1           '0'
162.5   3           Pos1Temp8
164     3           Pos1Temp7
165.5   3           Pos1Temp6
167     3           Pos1Temp5
168.5   3           Pos1Temp4
170     3           Pos1Temp3
171.5   3           Pos1Temp2
173     3           Pos1Temp1
174.5   3           Pos1Temp0
176    10           Pos1DT
181     0           End message

Notes:

1    DevID - an unique identifier of the USB-transceiver
2    Action
     10 startup message 
     30 weather message
     40 historical message
     51 startup message
     53 startup message
3    Signal quality 0-100%
4    DeviceCS - checksum of device parameter message
5    LatestAddress - address of newest historical record
     History record = (LatestAddres - 0x070000) / 32 
6    ThisAddress - address of actual historical record
     History record = (ThisAddress - 0x070000) / 32
7    Newest record
     Note: up to 6 records can all have the same data as the newest record
8    Eldest record

-------------------------------------------------------------------------------
date conversion: (2013-05-16)
byte1     1 year=2000+(byte1*10) 
byte2     3 year+=byte2
byte3     0 month=byte3*10 
byte4     5 month+=byte4
byte5     1 day=byte5*10
byte6     6 day+=byte6

time conversion: (19:15)
byte7     1 hours=byte7*10
byte8     9 hours+=byte8
byte9     1 minutes=byte9*10
byte10    5 minutes+=byte10

humidity conversion: (50)
byte1     5 humidity=byte1*10
byte2     0 humidity+=byte2

temp conversion: (23.2)
byte1     6 temp=(byte1*10)-40
byte2     3 temp+=byte2
byte3     2 temp+=(byte3*0.1)
-------------------------------------------------------------------------------

Example of a Historical message

0000   00 00 b5 01 07 00 40 64 1a b1 1e 4e 40 07 01 80
0010   aa aa aa aa 50 47 54 51 52 0a aa aa aa aa aa a6
0020   32 64 56 21 62 96 28 13 05 16 19 15 aa aa aa aa
0030   50 46 53 51 51 0a aa aa aa aa aa a6 36 64 86 21
0040   63 06 33 13 05 16 19 00 aa aa aa aa 50 44 54 51
0050   52 0a aa aa aa aa aa a6 38 65 36 21 63 16 36 13
0060   05 16 18 45 aa aa aa aa 49 44 54 51 52 0a aa aa
0070   aa aa aa a6 46 65 76 22 63 36 33 13 05 16 18 30
0080   aa aa aa aa 49 43 55 51 53 0a aa aa aa aa aa a6
0090   46 66 06 22 63 46 29 13 05 16 18 15 aa aa aa aa
00a0   51 43 56 51 54 0a aa aa aa aa aa a6 44 66 56 22
00b0   63 36 28 13 05 16 18 00

Example of a debug log:

Jan 19 17:14:46 RFComm: Pos1DT: 2015-01-19 16:30:00, Pos1Temp0 = 20.3, Pos1Humidity0 = 37.0
Jan 19 17:14:46 RFComm: Pos1Temp 1-8:      7.1, 7.8, 6.6, 16.2, 8.3, 81.1, 81.1, 81.1
Jan 19 17:14:46 RFComm: Pos1Humidity 1-8:  69,  66,  78,  52,  68, 110, 110, 110
Jan 19 17:14:46 RFComm: Pos2DT: 2015-01-19 16:35:00, Pos2Temp0 = 20.3, Pos2Humidity0 = 37.0
Jan 19 17:14:46 RFComm: Pos2Temp 1-8:      7.1, 7.8, 6.6, 16.0, 8.2, 81.1, 81.1, 81.1
Jan 19 17:14:46 RFComm: Pos2Humidity 1-8:  69,  66,  78,  51,  68, 110, 110, 110
Jan 19 17:14:46 RFComm: Pos3DT: 2015-01-19 16:40:00, Pos3Temp0 = 20.4, Pos3Humidity0 = 36.0
Jan 19 17:14:46 RFComm: Pos3Temp 1-8:      7.1, 7.8, 6.6, 16.0, 8.2, 81.1, 81.1, 81.1
Jan 19 17:14:46 RFComm: Pos3Humidity 1-8:  69,  66,  78,  51,  68, 110, 110, 110
Jan 19 17:14:46 RFComm: Pos4DT: 2015-01-19 16:45:00, Pos4Temp0 = 20.4, Pos4Humidity0 = 37.0
Jan 19 17:14:46 RFComm: Pos4Temp 1-8:      7.1, 7.8, 6.6, 16.0, 8.2, 81.1, 81.1, 81.1
Jan 19 17:14:46 RFComm: Pos4Humidity 1-8:  69,  66,  78,  51,  68, 110, 110, 110
Jan 19 17:14:46 RFComm: Pos5DT: 2015-01-19 16:50:00, Pos5Temp0 = 20.4, Pos5Humidity0 = 37.0
Jan 19 17:14:46 RFComm: Pos5Temp 1-8:      7.1, 7.8, 6.6, 16.6, 8.2, 81.1, 81.1, 81.1
Jan 19 17:14:46 RFComm: Pos5Humidity 1-8:  69,  66,  78,  50,  67, 110, 110, 110
Jan 19 17:14:46 RFComm: Pos6DT: 2015-01-19 16:55:00, Pos6Temp0 = 20.4, Pos6Humidity0 = 37.0
Jan 19 17:14:46 RFComm: Pos6Temp 1-8:      7.1, 7.8, 6.6, 17.1, 8.1, 81.1, 81.1, 81.1
Jan 19 17:14:46 RFComm: Pos6Humidity 1-8:  69,  66,  78,  50,  68, 110, 110, 110

-------------------------------------------------------------------------------
14. Set Config Message

Note: if start == x.5: StartOnLowNibble else: StartOnHiNibble

start   chars    name
0        4       DevID
2        2       LI = Logger ID: 0-9 = Logger 1 - logger 10
3        2       Action
4        2       Quality
5        2       Settings 8=? | 0-7=contrast, 8=alert OFF, 4=DCF ON, 2=clock 12h, 1=temp-F
6        2       TimeZone difference with Frankfurt (CET) f4 (-12) =tz -12h, 00=tz 0h, 0c (+12) = tz +12h
7        2       HistoryInterval 0=1 min, 1=5min, 2=10 min, 3=15 min, 4=30 min, 5=60 min, 6=2 hr, 7=3hr, 8=6 hr
8        3       Temp0Max (reverse group 1)
9,5      3       Temp0Min (reverse group 1)
11       3       Temp1Max (reverse group 2)
12,5     3       Temp1Min (reverse group 2)
14       3       Temp2Max (reverse group 3)
15,5     3       Temp2Min (reverse group 3)
17       3       Temp3Max (reverse group 4)
18,5     3       Temp3Min (reverse group 4)
20       3       Temp4Max (reverse group 5)
21,5     3       Temp4Min (reverse group 5)
23       3       Temp5Max (reverse group 6)
24,5     3       Temp5Min (reverse group 6)
26       3       Temp6Max (reverse group 7)
27,5     3       Temp6Min (reverse group 7)
29       3       Temp7Max (reverse group 8)
30,5     3       Temp7Min (reverse group 8)
32       3       Temp8Max (reverse group 9)
33,5     3       Temp8Min (reverse group 9)
35       2       Humidity0Max (reverse group 10)
36       2       Humidity0Min (reverse group 10)
37       2       Humidity1Max (reverse group 11)
38       2       Humidity1Min (reverse group 11)
39       2       Humidity2Max (reverse group 12)
40       2       Humidity2Min (reverse group 12)
41       2       Humidity3Max (reverse group 13)
42       2       Humidity3Min (reverse group 13)
43       2       Humidity4Max (reverse group 14)
44       2       Humidity4Min (reverse group 14)
45       2       Humidity5Max (reverse group 15)
46       2       Humidity5Min (reverse group 15)
47       2       Humidity6Max (reverse group 16)
48       2       Humidity6Min (reverse group 16)
49       2       Humidity7Max (reverse group 17)
50       2       Humidity7Min (reverse group 17)
51       2       Humidity8Max (reverse group 18)
52       2       Humidity8Min (reverse group 18)
53      10       '0000000000' sens0: 8=tmp lo al, 4=tmp hi al, 2=hum lo al, 1=hum hi al; same for sens1-8, 0000
58      16       Description1 (reverse)
66      16       Description2 (reverse)
74      16       Description3 (reverse)
82      16       Description4 (reverse)
90      16       Description5 (reverse)
98      16       Description6 (reverse)
106     16       Description7 (reverse)
114     16       Description8 (reverse)
122      2       '00' (output only) 0000, 1=reset hi-lo values
124      2       outBufCS
125      0       end

Example of a setConfig message:

0000   d5 00 7d 01 07 00 20 64 54 00 00 00 04 80 00 04
0010   80 00 04 80 00 04 80 00 04 80 00 04 80 00 04 80 
0020   00 04 80 00 04 80 20 70 20 70 20 70 20 70 20 70 
0030   20 70 20 70 20 70 20 70 00 00 00 00 00 d2 7f d5 
0040   d3 08 00 00 00 d2 76 b8 07 00 00 00 00 97 7f 71 
0050   00 00 00 00 00 56 4c f4 85 00 00 00 00 00 ff ff 
0060   00 00 00 00 00 00 ff ff 00 00 00 00 00 00 ff ff 
0070   00 00 00 00 00 00 ff ff 00 00 00 00 00 00 1a b1

-------------------------------------------------------------------------------
15. Get Config Message

Note: if start == x.5: StartOnLowNibble else: StartOnHiNibble

start   chars   name
0       4       DevID
2       2       LI = Logger ID: 0-9 = Logger 1 - logger 10
3       2       ResponseType
4       2       Quality
5       2       Settings
6       2       TimeZone
7       2       HistoryInterval
8       3       Temp0Max
9,5     3       Temp0Min
11      3       Temp1Max
12,5    3       Temp1Min
14      3       Temp2Max
15,5    3       Temp2Min
17      3       Temp3Max
18,5    3       Temp3Min
20      3       Temp4Max
21,5    3       Temp4Min
23      3       Temp5Max
24,5    3       Temp5Min
26      3       Temp6Max
27,5    3       Temp6Min
29      3       Temp7Max
30,5    3       Temp7Min
32      3       Temp8Max
33,5    3       Temp8Min
35      2       Humidity0Max
36      2       Humidity0Min
37      2       Humidity1Max
38      2       Humidity1Min
39      2       Humidity2Max
40      2       Humidity2Min
41      2       Humidity3Max
42      2       Humidity3Min
43      2       Humidity4Max
44      2       Humidity4Min
45      2       Humidity5Max
46      2       Humidity5Min
47      2       Humidity6Max
48      2       Humidity6Min
49      2       Humidity7Max
50      2       Humidity7Min
51      2       Humidity8Max
52      2       Humidity8Min
53     10       AlarmSet*
58     16       Description1
66     16       Description2
74     16       Description3
82     16       Description4
90     16       Description5
98     16       Description6
106    16       Description7
114    16       Description8
122     2       ResetHiLo (output only)
124     2       inBufCS
125     0       end

* AlarmSet
Humidity0Max: 00 00 00 00 01
Humidity0Min: 00 00 00 00 02
Temp0Max:     00 00 00 00 04
Temp0Min:     00 00 00 00 08
Humidity1Max: 00 00 00 00 10
Humidity1Min: 00 00 00 00 20
Temp1Max:     00 00 00 00 40
Temp1Min:     00 00 00 00 80
etc, etc

Example of Get Config message

0000   00 00 7d 01 07 00 20 64 54 00 00 80 04 00 80 04
0010   00 80 04 00 80 04 00 80 04 00 80 04 00 80 04 00
0020   80 04 00 80 04 00 70 20 70 20 70 20 70 20 70 20
0030   70 20 70 20 70 20 70 20 00 00 00 00 00 00 00 00
0040   08 d3 d5 7f d2 00 00 00 00 07 b8 76 d2 00 00 00
0050   00 00 71 7f 97 00 00 00 00 85 f4 4c 56 00 00 00
0060   00 00 ff ff 00 00 00 00 00 00 ff ff 00 00 00 00
0070   00 00 ff ff 00 00 00 00 00 00 ff ff 00 00 1a b1
0080   6c

Example of debug log:

Jan 19 17:14:54 RFComm: OutBufCS: 1c33
Jan 19 17:14:54 RFComm: InBufCS:  1c33
Jan 19 17:14:54 RFComm: Settings: 48: contrast: 4, alert: OFF, DCF reception: OFF, time format: 24h temp format: C
Jan 19 17:14:54 RFComm: TimeZone difference with Frankfurt (CET): 00 (tz: 0 hour)
Jan 19 17:14:54 RFComm: HistoryInterval: 01, period=5 minute(s)
Jan 19 17:14:54 RFComm: AlarmSet:      00 00 00 00 00
Jan 19 17:14:54 RFComm: ResetHiLo:     00
Jan 19 17:14:54 RFComm: Sensor0:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor1:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor2:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor3:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor4:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor5:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor6:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor7:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Sensor8:       0.0 - 40.0,  20 -  70
Jan 19 17:14:54 RFComm: Description1:  00 00 00 0f 44 b0 7b 44; SensorText:  GARAGE
Jan 19 17:14:54 RFComm: Description2:  0e 06 31 8c d2 69 5b 45; SensorText:  COLD WIND
Jan 19 17:14:54 RFComm: Description3:  00 00 0c 3c d2 69 5b 45; SensorText:  COLDER
Jan 19 17:14:54 RFComm: Description4:  07 d7 c5 71 d2 e0 7b 08; SensorText:  LIVING ROOM
Jan 19 17:14:54 RFComm: Description5:  00 00 00 00 00 e0 63 18; SensorText:  WIND
Jan 19 17:14:54 RFComm: Description6:  00 00 00 00 00 ff ff 00; SensorText:  (No sensor)
Jan 19 17:14:54 RFComm: Description7:  00 00 00 00 00 ff ff 00; SensorText:  (No sensor)
Jan 19 17:14:54 RFComm: Description8:  00 00 00 00 00 ff ff 00; SensorText:  (No sensor)

-------------------------------------------------------------------------------
HistoryInterval:
Constant  Value Message received at
hi01Min   = 0   00:00, 00:01, 00:02, 00:03 ... 23:59
hi05Min   = 1   00:00, 00:05, 00:10, 00:15 ... 23:55
hi10Min   = 2   00:00, 00:10, 00:20, 00:30 ... 23:50
hi15Min   = 3   00:00, 00:15, 00:30, 00:45 ... 23:45
hi30Min   = 4   00:00, 00:30, 01:00, 01:30 ... 23:30
hi01Std   = 5   00:00, 01:00, 02:00, 03:00 ... 23:00
hi02Std   = 6   00:00, 02:00, 04:00, 06:00 ... 22:00
hi03Std   = 7   00:00, 03:00, 09:00, 12:00 ... 21:00
hi06Std   = 8   00:00, 06:00, 12:00, 18:00

-------------------------------------------------------------------------------
WS SetTime - Send time to WS
Time  d5 00 0d 01 07 00 60 1a b1 25 58 21 04 03 41 01
time sent: Thu 2014-10-30 21:58:25 

-------------------------------------------------------------------------------
ReadConfigFlash data

Ask for frequency correction 
rcfo  0000: dd 0a 01 f5 cc cc cc cc cc cc cc cc cc cc cc
      0000: dd 0a 01 f5 58 d8 34 00 90 10 07 01 08 f2 ee - Ask for freq correction

readConfigFlash frequency correction
rcfi  0000: dc 0a 01 f5 00 01 78 a0 01 02 0a 0c 0c 01 2e ff ff ff ff ff
      0000: dc 0a 01 f5 00 01 8d 18 01 02 12 01 0d 01 07 ff ff ff ff ff 00 - freq correction
frequency correction: 96416 (0x178a0)
adjusted frequency: 910574957 (3646456d)

Ask for transceiver data 
rcfo  0000: dd 0a 01 f9 cc cc cc cc cc cc cc cc cc cc cc
      0000: dd 0a 01 f9 cc cc cc cc 56 8d b8 00 5c f2 ee - Ask for transceiver data 

readConfigFlash serial number and DevID
rcfi  0000: dc 0a 01 f9 01 02 0a 0c 0c 01 2e ff ff ff ff ff ff ff ff ff
      0000: dc 0a 01 f9 01 02 12 01 0d 01 07 ff ff ff ff ff ff ff ff ff 00 - transceiver data
transceiver ID: 302 (0x012e)
transceiver serial: 01021012120146

-------------------------------------------------------------------------------

Program Logic

The RF communication thread uses the following logic to communicate with the
weather station console:

Step 1.  Perform in a while loop getState commands until state 0xde16
         is received.

Step 2.  Perform a getFrame command to read the message data.

Step 3.  Handle the contents of the message. The type of message depends on
         the response type:

  Response type (hex):
  10: WS SetTime / SetConfig - Data written
      confirmation the setTime/setConfig setFrame message has been received
      by the console
  20: GetConfig
      save the contents of the configuration for later use (i.e. a setConfig
      message with one ore more parameters changed)
  30: Current Weather
      handle the weather data of the current weather message
  40: Actual / Outstanding History
      ignore the data of the actual history record when there is no data gap;
      handle the data of a (one) requested history record (note: in step 4 we
      can decide to request another history record).
  50: Request Read-History (MEM % > 0)
      no other action than debug log (the driver will always read history messages when available)
  51: Request First-Time Config
      prepare a setFrame first time message
  52: Request SetConfig
      prepare a setFrame setConfig message
  53: Request SetTime
      prepare a setFrame setTime message

Step 4.  When  you  didn't receive the message in step 3 you asked for (see
         step 5 how to request a certain type of message), decide if you want
         to ignore or handle the received message. Then go to step 5 to
         request for a certain type of message unless the received message
         has response type 51, 52 or 53, then prepare first the setFrame
         message the wireless console asked for.

Step 5.  Decide what kind of message you want to receive next time. The
         request is done via a setFrame message (see step 6).  It is
         not guaranteed that you will receive that kind of message the next
         time but setting the proper timing parameters of firstSleep and
         nextSleep increase the chance you will get the requested type of
         message.

Step 6. The action parameter in the setFrame message sets the type of the
        next to receive message.

  Action (hex):

  00: rtGetHistory - Ask for History message
                     setSleep(FIRST_SLEEP, 0.010)
  01: rtSetTime    - Ask for Send Time to weather station message
                     setSleep(0.075, 0.005)
  02: rtSetConfig  - Ask for Send Config to weather station message
                     setSleep(FIRST_SLEEP, 0.010)
  03: rtGetConfig  - Ask for Config message
                     setSleep(0.400, 0.400)
  04: rtGetCurrent - Ask for Current Weather message
                     setSleep(FIRST_SLEEP, 0.010)
  20: Send Config  - Send Config to WS
                     setSleep(0.075, 0.005)
  60: Send Time    - Send Time to WS
                     setSleep(0.075, 0.005)

  Note: after the Request First-Time Config message (response type = 0x51)
        perform a rtGetConfig with setSleep(0.075,0.005)

Step 7. Perform a setTX command

Step 8. Go to step 1 to wait for state 0xde16 again.
"""

from datetime import datetime
import random

import StringIO
import sys
import syslog
import threading
import time
import traceback
import usb

import weewx.drivers
import weewx.wxformulas
import weeutil.weeutil

DRIVER_NAME = 'KlimaLogg'
DRIVER_VERSION = '1.0'


def loader(config_dict, _):
    return KlimaLoggDriver(**config_dict[DRIVER_NAME])


def configurator_loader(_):
    return KlimaLoggConfigurator()


def confeditor_loader():
    return KlimaLoggConfEditor()


# flags for enabling/disabling debug verbosity
DEBUG_COMM = 0
DEBUG_CONFIG_DATA = 0
DEBUG_WEATHER_DATA = 0
DEBUG_HISTORY_DATA = 0
DEBUG_DUMP_FORMAT = 'auto'
LIMIT_REC_READ_TO = 0

# map the base sensor and 8 remote sensors to columns in the database schema
WVIEW_SENSOR_MAP = {
    'Temp0': 'inTemp',
    'Humidity0': 'inHumidity',
    'Temp1': 'outTemp',
    'Humidity1': 'outHumidity',
    'Temp2': 'extraTemp1',
    'Humidity2': 'extraHumid1',
    'Temp3': 'extraTemp2',
    'Humidity3': 'extraHumid2',
    'Temp4': 'extraTemp3',
    'Humidity4': 'leafWet1',
    'Temp5': 'soilTemp1',
    'Humidity5': 'soilMoist1',
    'Temp6': 'soilTemp2',
    'Humidity6': 'soilMoist2',
    'Temp7': 'soilTemp3',
    'Humidity7': 'soilMoist3',
    'Temp8': 'soilTemp4',
    'Humidity8': 'soilMoist4',
    'RxCheckPercent': 'rxCheckPercent',
    'BatteryStatus0': 'consBatteryVoltage',
    'BatteryStatus1': 'txBatteryStatus',
    'BatteryStatus2': 'inTempBatteryStatus',
    'BatteryStatus3': 'outTempBatteryStatus',
    'BatteryStatus4': 'windBatteryStatus',
    'BatteryStatus5': 'rainBatteryStatus',
    'BatteryStatus6': 'supplyVoltage',
    'BatteryStatus7': 'referenceVoltage',
    'BatteryStatus8': 'heatingVoltage',
}

# sensor map when using the kl schema
KL_SENSOR_MAP = {
    'Temp0': 'temp0',
    'Humidity0': 'humidity0',
    'Temp1': 'temp1',
    'Humidity1': 'humidity1',
    'Temp2': 'temp2',
    'Humidity2': 'humidity2',
    'Temp3': 'temp3',
    'Humidity3': 'humidity3',
    'Temp4': 'temp4',
    'Humidity4': 'humidity4',
    'Temp5': 'temp5',
    'Humidity5': 'humidity5',
    'Temp6': 'temp6',
    'Humidity6': 'humidity6',
    'Temp7': 'temp7',
    'Humidity7': 'humidity7',
    'Temp8': 'temp8',
    'Humidity8': 'humidity8',
    'RxCheckPercent': 'rxCheckPercent',
    'BatteryStatus0': 'batteryStatus0',
    'BatteryStatus1': 'batteryStatus1',
    'BatteryStatus2': 'batteryStatus2',
    'BatteryStatus3': 'batteryStatus3',
    'BatteryStatus4': 'batteryStatus4',
    'BatteryStatus5': 'batteryStatus5',
    'BatteryStatus6': 'batteryStatus6',
    'BatteryStatus7': 'batteryStatus7',
    'BatteryStatus8': 'batteryStatus8',
}


# kl schema (user/klschema.py) to use in place of the wview schema (schemas/wview.py)
schema = [('dateTime',             'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
          ('usUnits',              'INTEGER NOT NULL'),
          ('interval',             'INTEGER NOT NULL'),
          ('temp0',                'REAL'),
          ('temp1',                'REAL'),
          ('temp2',                'REAL'),
          ('temp3',                'REAL'),
          ('temp4',                'REAL'),
          ('temp5',                'REAL'),
          ('temp6',                'REAL'),
          ('temp7',                'REAL'),
          ('temp8',                'REAL'),
          ('humidity0',            'REAL'),
          ('humidity1',            'REAL'),
          ('humidity2',            'REAL'),
          ('humidity3',            'REAL'),
          ('humidity4',            'REAL'),
          ('humidity5',            'REAL'),
          ('humidity6',            'REAL'),
          ('humidity7',            'REAL'),
          ('humidity8',            'REAL'),
          ('dewpoint0',            'REAL'),
          ('dewpoint1',            'REAL'),
          ('dewpoint2',            'REAL'),
          ('dewpoint3',            'REAL'),
          ('dewpoint4',            'REAL'),
          ('dewpoint5',            'REAL'),
          ('dewpoint6',            'REAL'),
          ('dewpoint7',            'REAL'),
          ('dewpoint8',            'REAL'),
          ('heatindex0',           'REAL'),
          ('heatindex1',           'REAL'),
          ('heatindex2',           'REAL'),
          ('heatindex3',           'REAL'),
          ('heatindex4',           'REAL'),
          ('heatindex5',           'REAL'),
          ('heatindex6',           'REAL'),
          ('heatindex7',           'REAL'),
          ('heatindex8',           'REAL'),
          ('rxCheckPercent',       'REAL'),
          ('batteryStatus0',       'REAL'),
          ('batteryStatus1',       'REAL'),
          ('batteryStatus2',       'REAL'),
          ('batteryStatus3',       'REAL'),
          ('batteryStatus4',       'REAL'),
          ('batteryStatus5',       'REAL'),
          ('batteryStatus6',       'REAL'),
          ('batteryStatus7',       'REAL'),
          ('batteryStatus8',       'REAL')]


def logmsg(dst, msg):
    syslog.syslog(dst, 'KlimaLogg: %s: %s' %
                  (threading.currentThread().getName(), msg))


def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)


def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)


def logcrt(msg):
    logmsg(syslog.LOG_CRIT, msg)


def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)


def log_traceback(dst=syslog.LOG_INFO, prefix='**** '):
    sfd = StringIO.StringIO()
    traceback.print_exc(file=sfd)
    sfd.seek(0)
    for line in sfd:
        logmsg(dst, prefix + line)
    del sfd


def log_frame(n, buf):
    logdbg('frame length is %d' % n)
    strbuf = ''
    for i in xrange(0, n):
        strbuf += str('%02x ' % buf[i])
        if (i + 1) % 16 == 0:
            logdbg(strbuf)
            strbuf = ''
    if strbuf:
        logdbg(strbuf)


def get_datum_diff(v, np, ofl):
    if abs(np - v) < 0.001 or abs(ofl - v) < 0.001:
        return None
    return v


def calc_checksum(buf, start, end=None):
    if end is None:
        end = len(buf)
    cs = 0
    for i in xrange(start, end):
        cs += buf[i]
    return cs


def get_index(idx):
    if idx < 0:
        return idx + KlimaLoggDriver.max_records
    elif idx >= KlimaLoggDriver.max_records:
        return idx - KlimaLoggDriver.max_records
    return idx


def tstr_to_ts(tstr):
    try:
        return int(time.mktime(time.strptime(tstr, "%Y-%m-%d %H:%M:%S")))
    except (OverflowError, ValueError, TypeError):
        pass
    return None


def bytes_to_addr(a, b, c):
    return (((a << 8) | b) << 8) | c


def addr_to_index(addr):
    return (addr - 0x070000) / 32


def index_to_addr(idx):
    return 32 * idx + 0x070000


def print_dict(data):
    for x in sorted(data.keys()):
        if x == 'dateTime':
            print '%s: %s' % (x, weeutil.weeutil.timestamp_to_string(data[x]))
        else:
            print '%s: %s' % (x, data[x])


class KlimaLoggConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """

[KlimaLogg]
    # This section is for the TFA KlimaLogg series of weather stations.

    # Radio frequency to use between USB transceiver and console: US or EU
    # US uses 915 MHz, EU uses 868.3 MHz.  Default is EU.
    transceiver_frequency = EU

    # The serial number will be used to choose the right Weather Display Transceiver when more than one is present.
    # TIP: when the serial number of a transceiver is not known yet, remove temporary the other transceiver from
    # your server and start the driver without the serial number setting; the serial number and devid will be
    # presented in the debug logging.
    # USB transceiver Kat.Nr.: 30.3175  05/2014
    # serial = 010128031400117  # devid = 0x0075

    # The station model, e.g., 'TFA KlimaLoggPro' or 'TFA KlimaLogg'
    model = TFA KlimaLogg

    # The driver to use:
    driver = weewx.drivers.kl

    # debug flags:
    #  0=no logging; 1=minimum logging; 2=normal logging; 3=detailed logging
    debug_comm = 2
    debug_config_data = 2
    debug_weather_data = 2
    debug_history_data = 2
    debug_dump_format = auto

    # The timing of history and weather messages is set by the timing parameter
    # Do not change this value if you don't know what you are doing!
    # timing = 300  # set a value (in ms) between 100 and 400

    # The catchup mechanism will catchup history records to a maximum of limit_rec_read_to [0 .. 51200]
    # limit_rec_read_to = 3001

    # Sensor texts can have 1-10 upper-case alphanumeric characters;
    #   other allowed characters: space - + ( ) * , . / \ and o (o = lower case O used as degree symbol)
    # Note: You can't preset sensor texts for non-present sensors
    # Example for 5 sensors:
    # sensor_text1 = "5565 BED1"
    # sensor_text2 = "6DDF LAUN"
    # sensor_text3 = "7131 FRID"
    # sensor_text4 = "52F4 BED2"
    # sensor_text5 = "67D7 BATH"

    # The section below is for wview database mapping only; leave this section out for kl mapping
    # -------------------------------------------------------------------------------------------
    # You may change the wview sensor mapping by changing the values in the right
    # column. Be sure you use valid weewx database field names; each field
    # name can be used only once.
    #
    # WARNING: Any change to the sensor mapping should be followed by clearing
    # of the database, otherwise data will be mixed up.
    [[sensor_map]]
        Temp0          = inTemp      # save base station temperature as inTemp
        Humidity0      = inHumidity  # save base station humidity as inHumidity
        Temp1          = outTemp     # save sensor 1 temperature as outTemp
        Humidity1      = outHumidity # save sensor 1 humidity as outHumidity
        Temp2          = extraTemp1
        Humidity2      = extraHumid1
        Temp3          = extraTemp2
        Humidity3      = extraHumid2
        Temp4          = extraTemp3
        Humidity4      = leafWet1
        Temp5          = soilTemp1
        Humidity5      = soilMoist1
        Temp6          = soilTemp2
        Humidity6      = soilMoist2
        Temp7          = soilTemp3
        Humidity7      = soilMoist3
        Temp8          = soilTemp4
        Humidity8      = soilMoist4
        RxCheckPercent = rxCheckPercent
        BatteryStatus0 = consBatteryVoltage
        BatteryStatus1 = txBatteryStatus
        BatteryStatus2 = inTempBatteryStatus
        BatteryStatus3 = outTempBatteryStatus
        BatteryStatus4 = windBatteryStatus
        BatteryStatus5 = rainBatteryStatus
        BatteryStatus6 = supplyVoltage
        BatteryStatus7 = referenceVoltage
        BatteryStatus8 = heatingVoltage

    # The section below is for klimalogg database mapping only; leave this section out for wview mapping
    # -------------------------------------------------------------------------------------------
    [ [sensor_map]]
        Temp0          = temp0
        Temp1          = temp1
        Temp2          = temp2
        Temp3          = temp3
        Temp4          = temp4
        Temp5          = temp5
        Temp6          = temp6
        Temp7          = temp7
        Temp8          = temp8
        Humidity0      = humidity0
        Humidity1      = humidity1
        Humidity2      = humidity2
        Humidity3      = humidity3
        Humidity4      = humidity4
        Humidity5      = humidity5
        Humidity6      = humidity6
        Humidity7      = humidity7
        Humidity8      = humidity8
        Dewpoint0      = dewpoint0
        Dewpoint1      = dewpoint1
        Dewpoint2      = dewpoint2
        Dewpoint3      = dewpoint3
        Dewpoint4      = dewpoint4
        Dewpoint5      = dewpoint5
        Dewpoint6      = dewpoint6
        Dewpoint7      = dewpoint7
        Dewpoint8      = dewpoint8
        Heatindex0     = heatindex0
        Heatindex1     = heatindex1
        Heatindex2     = heatindex2
        Heatindex3     = heatindex3
        Heatindex4     = heatindex4
        Heatindex5     = heatindex5
        Heatindex6     = heatindex6
        Heatindex7     = heatindex7
        Heatindex8     = heatindex8
        RxCheckPercent = rxCheckPercent
        BatteryStatus0 = batteryStatus0
        BatteryStatus1 = batteryStatus1
        BatteryStatus2 = batteryStatus2
        BatteryStatus3 = batteryStatus3
        BatteryStatus4 = batteryStatus4
        BatteryStatus5 = batteryStatus5
        BatteryStatus6 = batteryStatus6
        BatteryStatus7 = batteryStatus7
        BatteryStatus8 = batteryStatus8
    # -------------------------------------------------------------------------------------------
"""

    def prompt_for_settings(self):
        print "Specify the frequency used between the station and the"
        print "transceiver, either 'US' (915 MHz) or 'EU' (868.3 MHz)."
        freq = self._prompt('frequency', 'EU', ['US', 'EU'])
        return {'transceiver_frequency': freq}


class KlimaLoggConfigurator(weewx.drivers.AbstractConfigurator):
    def add_options(self, parser):
        super(KlimaLoggConfigurator, self).add_options(parser)
        parser.add_option("--check-transceiver", dest="check",
                          action="store_true",
                          help="check USB transceiver")
        parser.add_option("--pair", dest="pair", action="store_true",
                          help="synchronize the USB transceiver with station console")
        parser.add_option("--current", dest="current", action="store_true",
                          help="get the current weather conditions")
        parser.add_option("--history", dest="nrecords", type=int, metavar="N",
                          help="display N history records")
        parser.add_option("--history-since", dest="recmin",
                          type=int, metavar="N",
                          help="display history records since N minutes ago")
        parser.add_option("--maxtries", dest="maxtries", type=int,
                          help="maximum number of retries, 0 indicates no max")

    def do_options(self, options, parser, config_dict, prompt):
        maxtries = 3 if options.maxtries is None else int(options.maxtries)
        self.station = KlimaLoggDriver(**config_dict[DRIVER_NAME])
        if options.check:
            self.check_transceiver(maxtries)
        elif options.pair:
            self.pair(maxtries)
        elif options.interval is not None:
            self.set_interval(maxtries, options.interval, prompt)
        elif options.current:
            self.show_current(maxtries)
        elif options.nrecords is not None:
            self.show_history(maxtries, count=options.nrecords)
        elif options.recmin is not None:
            ts = int(time.time()) - options.recmin * 60
            self.show_history(maxtries, ts=ts)
        else:
            self.show_info(maxtries)
        self.station.closePort()

    def check_transceiver(self, maxtries):
        """See if the transceiver is installed and operational."""
        print 'Checking for transceiver...'
        ntries = 0
        while ntries < maxtries:
            ntries += 1
            if self.station.transceiver_is_present():
                print 'Transceiver is present'
                sn = self.station.get_transceiver_serial()
                print 'serial: %s' % sn
                tid = self.station.get_transceiver_id()
                print 'id: %d (0x%04x)' % (tid, tid)
                break
            print 'Not found (attempt %d of %d) ...' % (ntries, maxtries)
            time.sleep(5)
        else:
            print 'Transceiver not responding.'

    def pair(self, maxtries):
        """Pair the transceiver with the station console."""
        print 'Pairing transceiver with console...'
        maxwait = 90  # how long to wait between button presses, in seconds
        ntries = 0
        while ntries < maxtries or maxtries == 0:
            if self.station.transceiver_is_paired():
                print 'Transceiver is paired (synchronized) to console'
                break
            ntries += 1
            msg = 'Press and hold the [v] key until "PC" appears'
            if maxtries > 0:
                msg += ' (attempt %d of %d)' % (ntries, maxtries)
            else:
                msg += ' (attempt %d)' % ntries
            print msg
            now = start_ts = int(time.time())
            while (now - start_ts < maxwait and
                   not self.station.transceiver_is_paired()):
                time.sleep(5)
                now = int(time.time())
        else:
            print 'Transceiver not paired (synchronized) to console.'

    def get_interval(self, maxtries):
        cfg = self.get_config(maxtries)
        if cfg is None:
            return None
        return history_intervals.get(cfg['history_interval'])

    def get_config(self, maxtries):
        start_ts = None
        ntries = 0
        while ntries < maxtries or maxtries == 0:
            cfg = self.station.get_config()
            if cfg is not None:
                return cfg
            ntries += 1
            if start_ts is None:
                start_ts = int(time.time())
            else:
                dur = int(time.time()) - start_ts
                print 'No data after %d seconds (press USB to start communication)' % dur
            time.sleep(30)
        return None

    @staticmethod
    def set_interval(maxtries, interval, prompt):
        """Set the station archive interval"""
        print 'This feature is not yet implemented'

    def show_info(self, maxtries):
        """Query the station then display the settings."""
        print 'Querying the station for the configuration...'
        cfg = self.get_config(maxtries)
        if cfg is not None:
            print_dict(cfg)

    def show_current(self, maxtries):
        """Get current weather observation."""
        print 'Querying the station for current weather data...'
        start_ts = None
        ntries = 0
        while ntries < maxtries or maxtries == 0:
            packet = self.station.get_observation()
            if packet is not None:
                print_dict(packet)
                break
            ntries += 1
            if start_ts is None:
                start_ts = int(time.time())
            else:
                dur = int(time.time()) - start_ts
                print 'No data after %d seconds (press USB to start communication)' % dur
            time.sleep(30)

    def show_history(self, maxtries, ts=0, count=0):
        """Display the indicated number of records or the records since the 
        specified timestamp (local time, in seconds)"""
        print "Querying the station for historical records..."
        ntries = 0
        last_n = nrem = None
        last_ts = int(time.time())
        self.station.start_caching_history(since_ts=ts, num_rec=count)
        while nrem is None or nrem > 0:
            if ntries >= maxtries:
                print 'Giving up after %d tries' % ntries
                break
            time.sleep(30)
            ntries += 1
            now = int(time.time())
            n = self.station.get_num_history_scanned()
            if n == last_n:
                dur = now - last_ts
                print 'No data after %d seconds (press USB to start communication)' % dur
            else:
                ntries = 0
                last_ts = now
            last_n = n
            nrem = self.station.get_uncached_history_count()
            ni = self.station.get_next_history_index()
            li = self.station.get_latest_history_index()
            msg = "  scanned %s records: current=%s latest=%s remaining=%s\r" % (n, ni, li, nrem)
            sys.stdout.write(msg)
            sys.stdout.flush()
        self.station.stop_caching_history()
        records = self.station.get_history_cache_records()
        self.station.clear_history_cache()
        print
        print 'Found %d records' % len(records)
        for r in records:
            print r


class KlimaLoggDriver(weewx.drivers.AbstractDevice):
    """Driver for TFA KlimaLogg stations."""

    # maximum number of history records
    # record number range: 0-51199
    # address range: 0x070000-0x1fffe0
    max_records = 51200

    def __init__(self, **stn_dict):
        """Initialize the station object.

        model: Which station model is this?
        [Optional. Default is 'TFA KlimaLogg Pro']

        transceiver_frequency: Frequency for transceiver-to-console.  Specify
        either US or EU.
        [Required. Default is EU]

        polling_interval: How often to sample the USB interface for data.
        [Optional. Default is 10 seconds]

        comm_interval: Communications mode interval
        [Optional.  Default is 8]

        serial: The transceiver serial number.  If there are multiple
        devices with the same vendor and product IDs on the bus, each will
        have a unique serial number.  Use the serial number to indicate which
        transceiver should be used.
        [Optional. Default is None]
        """

        self.vendor_id = stn_dict.get('vendor_id', 0x6666)
        self.product_id = stn_dict.get('product_id', 0x5555)
        self.model = stn_dict.get('model', 'TFA KlimaLogg')
        self.polling_interval = int(stn_dict.get('polling_interval', 10))
        self.comm_interval = int(stn_dict.get('comm_interval', 8))
        self.frequency = stn_dict.get('transceiver_frequency', 'EU')
        self.config_serial = stn_dict.get('serial', None)
        self.sensor_map = stn_dict.get('sensor_map', KL_SENSOR_MAP)

        if self.sensor_map['Temp0'] == 'temp0':
            logdbg('database schema is kl-schema')
        else:
            logdbg('database schema is wview-schema')

        global LIMIT_REC_READ_TO
        LIMIT_REC_READ_TO = int(stn_dict.get('limit_rec_read_to', 3001))

        now = int(time.time())
        self._service = None
        self._last_obs_ts = None
        self._last_nodata_log_ts = now
        self._nodata_interval = 300  # how often to check for no data
        self._last_contact_log_ts = now
        self._nocontact_interval = 300  # how often to check for no contact
        self._log_interval = 600  # how often to log
        self._packet_count = 0
        self._empty_packet_count = 0

        global DEBUG_COMM
        DEBUG_COMM = int(stn_dict.get('debug_comm', 1))
        global DEBUG_CONFIG_DATA
        DEBUG_CONFIG_DATA = int(stn_dict.get('debug_config_data', 1))
        global DEBUG_WEATHER_DATA
        DEBUG_WEATHER_DATA = int(stn_dict.get('debug_weather_data', 1))
        global DEBUG_HISTORY_DATA
        DEBUG_HISTORY_DATA = int(stn_dict.get('debug_history_data', 1))
        global DEBUG_DUMP_FORMAT
        DEBUG_DUMP_FORMAT = stn_dict.get('debug_dump_format', 'auto')

        timing = int(stn_dict.get('timing', 300))
        self.first_sleep = float(timing)/1000

        self.values = dict()
        for i in range(1, 9):
            self.values['sensor_text%d' % i] = stn_dict.get('sensor_text%d' % i, None)

        loginf('driver version is %s' % DRIVER_VERSION)
        loginf('frequency is %s' % self.frequency)
        loginf('timing is %s ms (%0.3f s)' % (timing, self.first_sleep))

        self.startUp()

    @property
    def hardware_name(self):
        return self.model

    # this is invoked by StdEngine as it shuts down
    def closePort(self):
        self.shutDown()

    def genLoopPackets(self):
        """Generator function that continuously returns decoded packets."""
        while True:
            self._packet_count += 1
            now = int(time.time() + 0.5)
            packet = self.get_observation()
            if packet is not None:
                ts = packet['dateTime']
                if DEBUG_WEATHER_DATA > 0:
                    logdbg('genLoopPackets: packet_count=%s: ts=%s packet=%s' %
                           (self._packet_count, ts, packet))
                if self._last_obs_ts is None or self._last_obs_ts != ts:
                    self._last_obs_ts = ts
                    self._empty_packet_count = 0
                    self._last_nodata_log_ts = now
                    self._last_contact_log_ts = now
                else:
                    self._empty_packet_count += 1
                    if DEBUG_WEATHER_DATA > 0 and self._empty_packet_count > 1:
                        logdbg("genLoopPackets: timestamp unchanged, set to empty packet; count: %s" % self._empty_packet_count)
                    packet = None
            else:
                self._empty_packet_count += 1
                if DEBUG_WEATHER_DATA > 0 and self._empty_packet_count > 1:
                    logdbg("genLoopPackets: empty packet; count; %s" % self._empty_packet_count)

            # if no new weather data, return an empty packet
            if packet is None:
                if DEBUG_WEATHER_DATA > 0:
                    logdbg("packet_count=%s empty_count=%s" %
                           (self._packet_count, self._empty_packet_count))
                if self._empty_packet_count >= 30:  # 30 * 10 s = 300 s
                    if DEBUG_WEATHER_DATA > 0:
                        msg = "Restarting communication after %d empty packets" % self._empty_packet_count
                        logdbg(msg)
                        raise weewx.WeeWxIOError('%s; press [USB] to start communication' % msg)
                packet = {'usUnits': weewx.METRIC, 'dateTime': now}
                # if no new weather data for awhile, log it
                if (self._last_obs_ts is None or
                    now - self._last_obs_ts > self._nodata_interval):
                    if now - self._last_nodata_log_ts > self._log_interval:
                        msg = 'no new weather data'
                        if self._last_obs_ts is not None:
                            msg += ' after %d seconds' % (
                                now - self._last_obs_ts)
                        loginf(msg)
                        self._last_nodata_log_ts = now

            # if no contact with console for awhile, log it
            ts = self.get_last_contact()
            if ts is None or now - ts > self._nocontact_interval:
                if now - self._last_contact_log_ts > self._log_interval:
                    msg = 'no contact with console'
                    if ts is not None:
                        msg += ' after %d seconds' % (now - ts)
                    msg += ': press [USB] to start communication'
                    loginf(msg)
                    self._last_contact_log_ts = now

            yield packet
            time.sleep(self.polling_interval)                    

    def genStartupRecords(self, ts):
        loginf('Scanning historical records')
        self.clear_wait_at_start()  # let rf communication start
        maxtries = 1445  # once per day at 00:00 the communication starts automatically ???
        ntries = 0
        last_n = nrem = None
        last_ts = int(time.time())
        self.start_caching_history(since_ts=ts)
        while nrem is None or nrem > 0:
            if ntries >= maxtries:
                logerr('No historical data after %d tries' % ntries)
                return
            time.sleep(60)
            ntries += 1
            now = int(time.time())
            n = self.get_num_history_scanned()
            if n == last_n:
                dur = now - last_ts
                loginf('No data after %d seconds (press USB to start communication)' % dur)
            else:
                ntries = 0
                last_ts = now
            last_n = n
            nrem = self.get_uncached_history_count()
            ni = self.get_next_history_index()
            li = self.get_latest_history_index()
            loginf("Scanned %s records: current=%s latest=%s remaining=%s" %
                   (n, ni, li, nrem))
        self.stop_caching_history()
        records = self.get_history_cache_records()
        self.clear_history_cache()
        loginf('Found %d historical records' % len(records))
        last_ts = None
        for r in records:
            this_ts = r['dateTime']
            if last_ts is not None and this_ts is not None:
                rec = dict()
                rec['usUnits'] = weewx.METRIC
                rec['dateTime'] = this_ts
                rec['interval'] = (this_ts - last_ts) / 60
                for k in self.SENSOR_KEYS:
                    if k in self.sensor_map and k in r:
                        if k.startswith('Temp'):
                            x = get_datum_diff(r[k],
                                               SensorLimits.temperature_NP,
                                               SensorLimits.temperature_OFL)
                        elif k.startswith('Humidity'):
                            x = get_datum_diff(r[k],
                                               SensorLimits.humidity_NP,
                                               SensorLimits.humidity_OFL)
                        else:
                            x = r[k]
                        rec[self.sensor_map[k]] = x
                if self.sensor_map['Temp0'] == 'temp0':
                    for y in range(0, 9):
                        rec['dewpoint%d' % y] = weewx.wxformulas.dewpointC(rec['temp%d' % y], rec['humidity%d' % y])
                        rec['heatindex%d' % y] = weewx.wxformulas.heatindexC(rec['temp%d' % y], rec['humidity%d' % y])
                yield rec
            last_ts = this_ts

    def startUp(self):
        if self._service is not None:
            return
        self._service = CommunicationService(self.first_sleep, self.values)
        self._service.setup(self.frequency, self.comm_interval,
                            self.vendor_id, self.product_id, self.config_serial)
        self._service.startRFThread()

    def shutDown(self):
        self._service.stopRFThread()
        self._service.teardown()
        self._service = None

    def transceiver_is_present(self):
        return self._service.getTransceiverPresent()

    def transceiver_is_paired(self):
        return self._service.getDeviceRegistered()

    def get_transceiver_serial(self):
        return self._service.getTransceiverSerNo()

    def get_transceiver_id(self):
        return self._service.getDeviceID()

    def get_last_contact(self):
        return self._service.getLastStat().last_seen_ts

    SENSOR_KEYS = ['Temp0', 'Humidity0',
                   'Temp1', 'Humidity1',
                   'Temp2', 'Humidity2',
                   'Temp3', 'Humidity3',
                   'Temp4', 'Humidity4',
                   'Temp5', 'Humidity5',
                   'Temp6', 'Humidity6',
                   'Temp7', 'Humidity7',
                   'Temp8', 'Humidity8']

    def get_observation(self):
        data = self._service.getCurrentData()
        ts = data.values['timestamp']
        if ts is None:
            return None

        # add elements required for weewx LOOP packets
        packet = {'usUnits': weewx.METRIC, 'dateTime': ts}

        # extract the values from the data object
        for k in self.SENSOR_KEYS:
            if k in self.sensor_map and k in data.values:
                if k.startswith('Temp'):
                    x = get_datum_diff(data.values[k],
                                       SensorLimits.temperature_NP,
                                       SensorLimits.temperature_OFL)
                elif k.startswith('Humidity'):
                    x = get_datum_diff(data.values[k],
                                       SensorLimits.humidity_NP,
                                       SensorLimits.humidity_OFL)
                else:
                    x = data.values[k]
                packet[self.sensor_map[k]] = x
        # Signal quality
        packet[self.sensor_map['RxCheckPercent']] = data.values['SignalQuality']
        # battery low stati
        packet[self.sensor_map['BatteryStatus0']] = 1 if data.values['AlarmData'][1] ^ 0x80 == 0 else 0
        bitmask = 1
        for y in range(1, 9):
            packet[self.sensor_map['BatteryStatus%d' % y]] = 1 if data.values['AlarmData'][0] ^ bitmask == 0 else 0
            bitmask <<= 1
        # dewpoints and heatindexes only for klschema
        if self.sensor_map['Temp0'] == 'temp0':
            for y in range(0, 9):
                packet['dewpoint%d' % y] = weewx.wxformulas.dewpointC(packet['temp%d' % y], packet['humidity%d' % y])
                packet['heatindex%d' % y] = weewx.wxformulas.heatindexC(packet['temp%d' % y], packet['humidity%d' % y])

        return packet

    def get_config(self):
        logdbg('get station configuration')
        cfg = self._service.getConfigData().asDict()
        cs = cfg.get('checksum_out')
        if cs is None or cs == 0:
            return None
        return cfg

    def start_caching_history(self, since_ts=0, num_rec=0):
        self._service.startCachingHistory(since_ts, num_rec)

    def stop_caching_history(self):
        self._service.stopCachingHistory()

    def get_uncached_history_count(self):
        return self._service.getUncachedHistoryCount()

    def get_next_history_index(self):
        return self._service.getNextHistoryIndex()

    def get_latest_history_index(self):
        return self._service.getLatestHistoryIndex()

    def get_num_history_scanned(self):
        return self._service.getNumHistoryScanned()

    def get_history_cache_records(self):
        return self._service.getHistoryCacheRecords()

    def clear_history_cache(self):
        self._service.clearHistoryCache()

    def clear_wait_at_start(self):
        self._service.clearWaitAtStart()

    def set_interval(self, interval):
        # FIXME: set the archive interval
        pass

# The following classes and methods are adapted from the implementation by
# eddie de pieri, which is in turn based on the HeavyWeather implementation.


class BadResponse(Exception):
    """raised when unexpected data found in frame buffer"""
    pass


class UnknownDeviceId(Exception):
    """raised when unknown device ID found in frame buffer"""
    pass


class DataWritten(Exception):
    """raised when message 'data written' in frame buffer"""
    pass


ACTION_GET_HISTORY = 0x00
ACTION_REQ_SET_TIME = 0x01
ACTION_REQ_SET_CONFIG = 0x02
ACTION_GET_CONFIG = 0x03
ACTION_GET_CURRENT = 0x04
ACTION_SEND_CONFIG = 0x20
ACTION_SEND_TIME = 0x60

RESPONSE_DATA_WRITTEN = 0x10
RESPONSE_GET_CONFIG = 0x20
RESPONSE_GET_CURRENT = 0x30
RESPONSE_GET_HISTORY = 0x40
RESPONSE_REQUEST = 0x50  # the group of all 0x5x requests
RESPONSE_REQ_READ_HISTORY = 0x50
RESPONSE_REQ_FIRST_CONFIG = 0x51
RESPONSE_REQ_SET_CONFIG = 0x52
RESPONSE_REQ_SET_TIME = 0x53

HI_01MIN = 0
HI_05MIN = 1
HI_10MIN = 2
HI_15MIN = 3
HI_30MIN = 4
HI_01STD = 5
HI_02STD = 6
HI_03STD = 7
HI_06STD = 8

history_intervals = {
    HI_01MIN: 1,
    HI_05MIN: 5,
    HI_10MIN: 10,
    HI_15MIN: 15,
    HI_30MIN: 30,
    HI_01STD: 60,
    HI_02STD: 120,
    HI_03STD: 180,
    HI_06STD: 360,
    }

LOGGER_1 = 0
LOGGER_2 = 1
LOGGER_3 = 2
LOGGER_4 = 3
LOGGER_5 = 4
LOGGER_6 = 5
LOGGER_7 = 6
LOGGER_8 = 7
LOGGER_9 = 8
LOGGER_10 = 9

# frequency standards and their associated transmission frequencies
frequencies = {
    'US': 905000000,
    'EU': 868300000,
}


# NP - not present
# OFL - outside factory limits
class SensorLimits:
    temperature_offset = 40.0
    temperature_NP = 81.1
    temperature_OFL = 136.0
    humidity_NP = 110.0
    humidity_OFL = 121.0


class Decode(object):

    CHARMAP = (' ', '1', '2', '3', '4', '5', '6', '7', '8', '9',
               '0', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I',
               'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S',
               'T', 'U', 'V', 'W', 'X', 'Y', 'Z', '-', '+', '(',
               ')', 'o', '*', ',', '/', '\\', ' ', '.', ' ', ' ',
               ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ',
               ' ', ' ', ' ', '@')

    CHARSTR = "!1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ-+()o*,/\ ."

    @staticmethod
    def toCharacters3_2(buf, start, startOnHiNibble):
        """read 3 (4 bits) nibbles, presentation as 2 (6 bit) characters"""
        if startOnHiNibble:
            idx1 = ((buf[start+1] >> 2) & 0x3C) + ((buf[start] >> 2) & 0x3)
            idx2 = ((buf[start] << 4) & 0x30) + ((buf[start] >> 4) & 0xF)
        else:
            idx1 = ((buf[start+1] << 2) & 0x3C) + ((buf[start+1] >> 6) & 0x3)
            idx2 = (buf[start+1] & 0x30) + (buf[start] & 0xF)
        return Decode.CHARMAP[idx1] + Decode.CHARMAP[idx2]

    @staticmethod
    def isOFL2(buf, start, startOnHiNibble):
        if startOnHiNibble:
            result = ((buf[start + 0] >>  4) == 15 or
                      (buf[start + 0] & 0xF) == 15)
        else:
            result = ((buf[start + 0] & 0xF) == 15 or
                      (buf[start + 1] >>  4) == 15)
        return result

    @staticmethod
    def isOFL3(buf, start, startOnHiNibble):
        if startOnHiNibble:
            result = ((buf[start + 0] >>  4) == 15 or
                      (buf[start + 0] & 0xF) == 15 or
                      (buf[start + 1] >>  4) == 15)
        else:
            result = ((buf[start + 0] & 0xF) == 15 or
                      (buf[start + 1] >>  4) == 15 or
                      (buf[start + 1] & 0xF) == 15)
        return result

    @staticmethod
    def isOFL5(buf, start, startOnHiNibble):
        if startOnHiNibble:
            result = ((buf[start + 0] >>  4) == 15 or
                      (buf[start + 0] & 0xF) == 15 or
                      (buf[start + 1] >>  4) == 15 or
                      (buf[start + 1] & 0xF) == 15 or
                      (buf[start + 2] >>  4) == 15)
        else:
            result = ((buf[start + 0] & 0xF) == 15 or
                      (buf[start + 1] >>  4) == 15 or
                      (buf[start + 1] & 0xF) == 15 or
                      (buf[start + 2] >>  4) == 15 or
                      (buf[start + 2] & 0xF) == 15)
        return result

    @staticmethod
    def isErr2(buf, start, startOnHiNibble):
        if startOnHiNibble:
            result = ((buf[start + 0] >>  4) >= 10 and
                      (buf[start + 0] >>  4) != 15 or
                      (buf[start + 0] & 0xF) >= 10 and
                      (buf[start + 0] & 0xF) != 15)
        else:
            result = ((buf[start + 0] & 0xF) >= 10 and
                      (buf[start + 0] & 0xF) != 15 or
                      (buf[start + 1] >>  4) >= 10 and
                      (buf[start + 1] >>  4) != 15)
        return result
        
    @staticmethod
    def isErr3(buf, start, startOnHiNibble):
        if startOnHiNibble:
            result = ((buf[start + 0] >>  4) >= 10 and
                      (buf[start + 0] >>  4) != 15 or
                      (buf[start + 0] & 0xF) >= 10 and
                      (buf[start + 0] & 0xF) != 15 or
                      (buf[start + 1] >>  4) >= 10 and
                      (buf[start + 1] >>  4) != 15)
        else:
            result = ((buf[start + 0] & 0xF) >= 10 and
                      (buf[start + 0] & 0xF) != 15 or
                      (buf[start + 1] >>  4) >= 10 and
                      (buf[start + 1] >>  4) != 15 or
                      (buf[start + 1] & 0xF) >= 10 and
                      (buf[start + 1] & 0xF) != 15)
        return result
        
    @staticmethod
    def isErr5(buf, start, startOnHiNibble):
        if startOnHiNibble:
            result = ((buf[start + 0] >>  4) >= 10 and
                      (buf[start + 0] >>  4) != 15 or
                      (buf[start + 0] & 0xF) >= 10 and
                      (buf[start + 0] & 0xF) != 15 or
                      (buf[start + 1] >>  4) >= 10 and
                      (buf[start + 1] >>  4) != 15 or
                      (buf[start + 1] & 0xF) >= 10 and
                      (buf[start + 1] & 0xF) != 15 or
                      (buf[start + 2] >>  4) >= 10 and
                      (buf[start + 2] >>  4) != 15)
        else:
            result = ((buf[start + 0] & 0xF) >= 10 and
                      (buf[start + 0] & 0xF) != 15 or
                      (buf[start + 1] >>  4) >= 10 and
                      (buf[start + 1] >>  4) != 15 or
                      (buf[start + 1] & 0xF) >= 10 and
                      (buf[start + 1] & 0xF) != 15 or
                      (buf[start + 2] >>  4) >= 10 and
                      (buf[start + 2] >>  4) != 15 or
                      (buf[start + 2] & 0xF) >= 10 and
                      (buf[start + 2] & 0xF) != 15)
        return result

    @staticmethod
    def isErr8(buf, start, startOnHiNibble):
        if startOnHiNibble:
            result = ((buf[start + 0] >>  4) == 10 and
                      (buf[start + 0] & 0xF) == 10 and
                      (buf[start + 1] >>  4) == 4  and
                      (buf[start + 1] & 0xF) == 10 and
                      (buf[start + 2] >>  4) == 10 and
                      (buf[start + 2] & 0xF) == 4  and
                      (buf[start + 3] >>  4) == 10 and
                      (buf[start + 3] & 0xF) == 10)
        else:
            result = ((buf[start + 0] & 0xF) == 10 and
                      (buf[start + 1] >>  4) == 10 and
                      (buf[start + 1] & 0xF) == 4  and
                      (buf[start + 2] >>  4) == 10 and
                      (buf[start + 2] & 0xF) == 10 and
                      (buf[start + 3] >>  4) == 4  and
                      (buf[start + 3] & 0xF) == 10 and
                      (buf[start + 4] >>  4) == 10)
        return result

    @staticmethod
    def toInt_1(buf, start, startOnHiNibble):
        """read 1 nibble"""
        if startOnHiNibble:
            rawpre = (buf[start] >> 4)
        else:
            rawpre = (buf[start] & 0xF)
        return rawpre

    @staticmethod
    def toInt_2(buf, start, startOnHiNibble):
        """read 2 nibbles"""
        if startOnHiNibble:
            rawpre = (buf[start] >> 4) * 10 + (buf[start+0] & 0xF) * 1
        else:
            rawpre = (buf[start] & 0xF) * 10 + (buf[start+1] >> 4) * 1
        return rawpre

    @staticmethod
    def toDateTime10(buf, start, startOnHiNibble, label):
        """read 10 nibbles, presentation as DateTime"""
        result = None
        if (Decode.isErr2(buf, start+0, startOnHiNibble) or
            Decode.isErr2(buf, start+1, startOnHiNibble) or
            Decode.isErr2(buf, start+2, startOnHiNibble) or
            Decode.isErr2(buf, start+3, startOnHiNibble) or
            Decode.isErr2(buf, start+4, startOnHiNibble)):
            logerr('ToDateTime: bogus date for %s: error status in buffer' %
                   label)
        else:
            year    = Decode.toInt_2(buf, start+0, startOnHiNibble) + 2000
            month   = Decode.toInt_2(buf, start+1, startOnHiNibble)
            days    = Decode.toInt_2(buf, start+2, startOnHiNibble)
            hours   = Decode.toInt_2(buf, start+3, startOnHiNibble)
            minutes = Decode.toInt_2(buf, start+4, startOnHiNibble)
            try:
                result = datetime(year, month, days, hours, minutes)
            except ValueError:
                logerr(('ToDateTime: bogus date for %s:'
                        ' bad date conversion from'
                        ' %s %s %s %s %s') %
                       (label, minutes, hours, days, month, year))
        if result is None:
            # FIXME: use None instead of a really old date to indicate invalid
            result = datetime(1900, 01, 01, 00, 00)
        return result

    @staticmethod
    def toDateTime8(buf, start, startOnHiNibble, label):
        """read 8 nibbles, presentation as DateTime"""
        result = None
        if Decode.isErr8(buf, start+0, startOnHiNibble):
            logerr('ToDateTime: %s: no valid date' % label)
        else:
            if startOnHiNibble:
                year  = Decode.toInt_2(buf, start+0, 1) + 2000
                month = Decode.toInt_1(buf, start+1, 1)
                days  = Decode.toInt_2(buf, start+1, 0)
                tim1  = Decode.toInt_1(buf, start+2, 0)
                tim2  = Decode.toInt_1(buf, start+3, 1)
                tim3  = Decode.toInt_1(buf, start+3, 0)
            else:
                year  = Decode.toInt_2(buf, start+0, 0) + 2000
                month = Decode.toInt_1(buf, start+1, 0)
                days  = Decode.toInt_2(buf, start+2, 1)
                tim1  = Decode.toInt_1(buf, start+3, 1)
                tim2  = Decode.toInt_1(buf, start+3, 0)
                tim3  = Decode.toInt_1(buf, start+4, 1)
            if tim1 >= 10:
                hours = tim1 + 10
            else:
                hours = tim1
            if tim2 >= 10:
                hours += 10
                minutes = (tim2-10) * 10
            else:
                minutes = tim2 * 10
            minutes += tim3
            try:
                result = datetime(year, month, days, hours, minutes)
            except ValueError:
                logerr(('ToDateTime: bogus date for %s:'
                        ' bad date conversion from'
                        ' %s %s %s %s %s') %
                        (label, minutes, hours, days, month, year))
        if result is None:
            # FIXME: use None instead of a really old date to indicate invalid
            result = datetime(1900, 01, 01, 00, 00)
        return result

    @staticmethod
    def toHumidity_2_0(buf, start, startOnHiNibble):
        """read 2 nibbles, presentation with 0 decimal"""
        if Decode.isErr2(buf, start, startOnHiNibble):
            result = SensorLimits.humidity_NP
        elif Decode.isOFL2(buf, start, startOnHiNibble):
            result = SensorLimits.humidity_OFL
        else:
            result = Decode.toInt_2(buf, start, startOnHiNibble)
        return result

    @staticmethod
    def toTemperature_3_1(buf, start, startOnHiNibble):
        """read 3 nibbles, presentation with 1 decimal; units of degree C"""
        if Decode.isErr3(buf, start, startOnHiNibble):
            result = SensorLimits.temperature_NP
        elif Decode.isOFL3(buf, start, startOnHiNibble):
            result = SensorLimits.temperature_OFL
        else:
            if startOnHiNibble:
                rawtemp = (buf[start] >> 4) * 10 \
                    + (buf[start + 0] & 0xF) * 1 \
                    + (buf[start + 1] >> 4) * 0.1
            else:
                rawtemp = (buf[start] & 0xF) * 10 \
                    + (buf[start + 1] >> 4) * 1 \
                    + (buf[start + 1] & 0xF) * 0.1
            result = rawtemp - SensorLimits.temperature_offset
        return result


class CurrentData(object):

    BUFMAP = {0: ( 26, 28, 29, 18, 22, 15, 16, 17,  7, 11),
              1: ( 50, 52, 53, 42, 46, 39, 40, 41, 31, 35),
              2: ( 74, 76, 77, 66, 70, 63, 64, 65, 55, 59),
              3: ( 98,100,101, 90, 94, 87, 88, 89, 79, 83),
              4: (122,124,125,114,118,111,112,113,103,107),
              5: (146,148,149,138,142,135,136,137,127,131),
              6: (170,172,173,162,166,159,160,161,151,155),
              7: (194,196,197,186,190,183,184,185,175,179),
              8: (218,220,221,210,214,207,208,209,199,203)}

    def __init__(self):
        self.values = dict()
        self.values['timestamp'] = None
        self.values['SignalQuality'] = None
        for i in range(0, 9):
            self.values['Temp%d' % i] = SensorLimits.temperature_NP
            self.values['Temp%dMax' % i] = SensorLimits.temperature_NP
            self.values['Temp%dMaxDT'] = None
            self.values['Temp%dMin' % i] = SensorLimits.temperature_NP
            self.values['Temp%dMinDT'] = None
            self.values['Humidity%d' % i] = SensorLimits.humidity_NP
            self.values['Humidity%dMax' % i] = SensorLimits.humidity_NP
            self.values['Humidity%dMaxDT'] = None
            self.values['Humidity%dMin' % i] = SensorLimits.humidity_NP
            self.values['Humidity%dMinDT'] = None

    def read(self, buf):
        values = dict()
        values['timestamp'] = int(time.time() + 0.5)
        values['SignalQuality'] = buf[4] & 0x7F
        for x in range(0, 9):
            lbl = 'Temp%s' % x
            values[lbl + 'Max'] = Decode.toTemperature_3_1(buf, self.BUFMAP[x][0], 0)
            values[lbl + 'Min'] = Decode.toTemperature_3_1(buf, self.BUFMAP[x][1], 1)
            values[lbl] = Decode.toTemperature_3_1(buf, self.BUFMAP[x][2], 0)
            values[lbl + 'MaxDT'] = None if values[lbl + 'Max'] == SensorLimits.temperature_NP or values[lbl + 'Max'] == SensorLimits.temperature_OFL else Decode.toDateTime8(buf, self.BUFMAP[x][3], 0, lbl + 'Max')
            values[lbl + 'MinDT'] = None if values[lbl + 'Min'] == SensorLimits.temperature_NP or values[lbl + 'Min'] == SensorLimits.temperature_OFL else Decode.toDateTime8(buf, self.BUFMAP[x][4], 0, lbl + 'Min')
            lbl = 'Humidity%s' % x
            values[lbl + 'Max'] = Decode.toHumidity_2_0(buf, self.BUFMAP[x][5], 1)
            values[lbl + 'Min'] = Decode.toHumidity_2_0(buf, self.BUFMAP[x][6], 1)
            values[lbl] = Decode.toHumidity_2_0(buf, self.BUFMAP[x][7], 1)
            values[lbl + 'MaxDT'] = None if values[lbl + 'Max'] == SensorLimits.humidity_NP or values[lbl + 'Max'] == SensorLimits.humidity_OFL else Decode.toDateTime8(buf, self.BUFMAP[x][8], 1, lbl + 'Max')
            values[lbl + 'MinDT'] = None if values[lbl + 'Min'] == SensorLimits.humidity_NP or values[lbl + 'Min'] == SensorLimits.humidity_OFL else Decode.toDateTime8(buf, self.BUFMAP[x][9], 1, lbl + 'Min')
        values['AlarmData'] = buf[223:223+12]
        self.values = values

    def toLog(self):
        logdbg("timestamp: %s" % self.values['timestamp'])
        logdbg("SignalQuality: %3.0f " % self.values['SignalQuality'])
        for x in range(0, 9):
            if self.values['Temp%d' % x] != SensorLimits.temperature_NP:
                logdbg("Temp%d:     %5.1f   Min: %5.1f (%s)   Max: %5.1f (%s)" %
                       (x, self.values['Temp%s' % x],
                        self.values['Temp%sMin' % x],
                        self.values['Temp%sMinDT' % x],
                        self.values['Temp%sMax' % x],
                        self.values['Temp%sMaxDT' % x]))
            if self.values['Humidity%d' % x] != SensorLimits.humidity_NP:
                logdbg("Humidity%d: %5.0f   Min: %5.0f (%s)   Max: %5.0f (%s)" %
                       (x, self.values['Humidity%s' % x],
                        self.values['Humidity%sMin' % x],
                        self.values['Humidity%sMinDT' % x],
                        self.values['Humidity%sMax' % x],
                        self.values['Humidity%sMaxDT' % x]))
        byte_str = ' '.join(['%02x' % x for x in self.values['AlarmData']])
        logdbg('AlarmData: %s' % byte_str)


class StationConfig(object):

    BUFMAP = {0: ( 8, 11, 14, 17, 20, 23, 26, 29, 32),
              1: ( 9, 12, 15, 18, 21, 24, 27, 30, 33),
              2: (35, 37, 39, 41, 43, 45, 47, 49, 51),
              3: (36, 38, 40, 42, 44, 46, 48, 50, 52),
              4: (58, 66, 74, 82, 90, 98,106,114)}

    def __init__(self):
        self.values = dict()
        self.set_values = dict()
        self.read_config_sensor_texts = True
        self.values['InBufCS'] = 0  # checksum of received config
        self.values['OutBufCS'] = 0  # calculated checksum from outbuf config
        self.values['Settings'] = 0
        self.values['TimeZone'] = 0
        self.values['HistoryInterval'] = 0
        self.values['AlarmSet'] = [0] * 5
        self.values['ResetHiLo'] = 0
        for i in range(0, 9):
            self.values['Temp%dMax' % i] = SensorLimits.temperature_NP
            self.values['Temp%dMin' % i] = SensorLimits.temperature_NP
            self.values['Humidity%dMax' % i] = SensorLimits.humidity_NP
            self.values['Humidity%dMin' % i] = SensorLimits.humidity_NP
        for i in range(1, 9):
            self.values['Description%d' % i] = [0] * 8
            self.values['SensorText%d' % i] = ''
            self.set_values['Description%d' % i] = [0] * 8
            self.set_values['SensorText%d' % i] = ''
    
    def getOutBufCS(self):
        return self.values['OutBufCS']
             
    def getInBufCS(self):
        return self.values['InBufCS']

    def setAlarmClockOffset(self):
        # set Humidity Lo alarm of station when stations clock is too way off
        self.values['Humidity0Min'] = 99
        self.values['AlarmSet'][4] = (self.values['AlarmSet'][4] & 0xfd) + 0x2

    def resetAlarmClockOffset(self):
        # reset Humidity Lo alarm of station when stations clock is within margins
        self.values['Humidity0Min'] = 20
        self.values['AlarmSet'][4] = (self.values['AlarmSet'][4] & 0xfd)

    def setSensorText(self, values):
        # test if config is read and sensor texts are not set before
        if self.values['InBufCS'] != 0 and self.read_config_sensor_texts:
            self.read_config_sensor_texts = False
            # Use the sensor_text settings in weewx.conf to preset the sensor texts
            for x in range(1, 9):
                txt = [0] * 8
                lbl = 'sensor_text%d' % x
                self.set_values['SensorText%d' % x] = values[lbl]
                sensor_text = self.set_values['SensorText%d' % x]
                if sensor_text is not None:
                    if len(sensor_text) > 10:
                        logerr('Config sensor_text%d: "%s" has more than 10 characters' % (x, sensor_text))
                    else:
                        text_ok = True
                        for y in range(0, len(sensor_text)):
                            if Decode.CHARSTR.find(sensor_text[y:y+1]) <= 0:
                                text_ok = False
                                logerr('Config sensor_text%d: "%s" contains not-allowd charachter %s on pos %s' %
                                       (x, sensor_text, sensor_text[y:y+1], y+1))
                        if text_ok:
                            padded_sensor_text = sensor_text.ljust(10, '!')
                        else:
                            sensor_text = None
                if sensor_text is not None:
                    if self.values['SensorText%s' % x] == '(No sensor)':
                        logerr('Config sensor_text%d: "%s" not allowed for non present sensor' % (x, sensor_text))
                    else:
                        logdbg('Config sensor_text%d: "%s"' % (x, sensor_text))
                        txt = [0] * 8
                        # just for clarity we didn't 'optimize' the code below
                        # translate 10 characters of 6 bits into 8 bytes of 8 bits
                        char_id1 = Decode.CHARSTR.find(padded_sensor_text[0:1])
                        char_id2 = Decode.CHARSTR.find(padded_sensor_text[1:2])
                        char_id3 = Decode.CHARSTR.find(padded_sensor_text[2:3])
                        char_id4 = Decode.CHARSTR.find(padded_sensor_text[3:4])
                        char_id5 = Decode.CHARSTR.find(padded_sensor_text[4:5])
                        char_id6 = Decode.CHARSTR.find(padded_sensor_text[5:6])
                        char_id7 = Decode.CHARSTR.find(padded_sensor_text[6:7])
                        char_id8 = Decode.CHARSTR.find(padded_sensor_text[7:8])
                        char_id9 = Decode.CHARSTR.find(padded_sensor_text[8:9])
                        char_id10 = Decode.CHARSTR.find(padded_sensor_text[9:10])
                        txt[7] = ((char_id1 << 6) & 0xC0) + (char_id2 & 0x30) + ((char_id1 >> 2) & 0x0F)
                        txt[6] = ((char_id3 << 2) & 0xF0) + (char_id2 & 0x0F)
                        txt[5] = ((char_id4 << 4) & 0xF0) + ((char_id3 << 2) & 0x0C) + ((char_id4 >> 4) & 0x03)
                        txt[4] = ((char_id5 << 6) & 0xC0) + (char_id6 & 0x30) + ((char_id5 >> 2) & 0x0F)
                        txt[3] = ((char_id7 << 2) & 0xF0) + (char_id6 & 0x0F)
                        txt[2] = ((char_id8 << 4) & 0xF0) + ((char_id7 << 2) & 0x0C) + ((char_id8 >> 4) & 0x03)
                        txt[1] = ((char_id9 << 6) & 0xC0) + (char_id10 & 0x30) + ((char_id9 >> 2) & 0x0F)
                        txt[0] = (char_id10 & 0x0F)
                        # copy the results to the outputbuffer data
                        self.values['Description%d' % x] = txt
                        self.values['SensorText%d' % x] = sensor_text.ljust(10)

    @staticmethod
    def reverseByteOrder(buf, start, count):
        """reverse count bytes in buf beginning at start"""
        for i in xrange(0, count >> 1):
            tmp = buf[start + i]
            buf[start + i] = buf[start + count - i - 1]
            buf[start + count - i - 1] = tmp
    
    @staticmethod
    def parse_0(number, buf, start, startOnHiNibble, numbytes):
        """Parse 3-digit number with 0 decimals, insert into buf"""
        num = int(number)
        nbuf = [0] * 3
        for i in xrange(3-numbytes, 3):
            nbuf[i] = num % 10
            num //= 10
        if startOnHiNibble:
            buf[0+start] = nbuf[2]*16 + nbuf[1]
            if numbytes > 2:
                buf[1+start] = nbuf[0]*16 + (buf[2+start] & 0x0F)
        else:
            buf[0+start] = (buf[0+start] & 0xF0) + nbuf[2]
            if numbytes > 2:
                buf[1+start] = nbuf[1]*16 + nbuf[0]

    @staticmethod
    def parse_1(number, buf, start, startOnHiNibble, numbytes):
        """Parse 3 digit number with 1 decimal, insert into buf"""
        StationConfig.parse_0(number*10.0, buf, start, startOnHiNibble, numbytes)

    def read(self, buf):
        values = dict()
        values['Settings'] = buf[5]
        values['TimeZone'] = buf[6]
        values['HistoryInterval'] = buf[7] & 0xF
        for x in range(0, 9):
            lbl = 'Temp%s' % x
            values[lbl + 'Max'] = Decode.toTemperature_3_1(buf, self.BUFMAP[0][x], 1)
            values[lbl + 'Min'] = Decode.toTemperature_3_1(buf, self.BUFMAP[1][x], 0)
            lbl = 'Humidity%s' % x
            values[lbl + 'Max'] = Decode.toHumidity_2_0(buf, self.BUFMAP[2][x], 1)
            values[lbl + 'Min'] = Decode.toHumidity_2_0(buf, self.BUFMAP[3][x], 1)
        values['AlarmSet'] = buf[53:53+5]
        for x in range(1, 9):
            values['Description%s' % x] = buf[self.BUFMAP[4][x-1]:self.BUFMAP[4][x-1]+8]
            txt1 = Decode.toCharacters3_2(buf, self.BUFMAP[4][x-1]+6, 0)
            txt2 = Decode.toCharacters3_2(buf, self.BUFMAP[4][x-1]+5, 1)
            txt3 = Decode.toCharacters3_2(buf, self.BUFMAP[4][x-1]+3, 0)
            txt4 = Decode.toCharacters3_2(buf, self.BUFMAP[4][x-1]+2, 1)
            txt5 = Decode.toCharacters3_2(buf, self.BUFMAP[4][x-1], 0)
            sensor_txt = txt1 + txt2 + txt3 + txt4 + txt5
            if sensor_txt == ' E@@      ':
                values['SensorText%s' % x] = '(No sensor)'
            else:
                values['SensorText%s' % x] = sensor_txt
        values['ResetHiLo'] = buf[122]
        values['InBufCS'] = (buf[123] << 8) | buf[124]
        # checksum is not calculated for ResetHiLo (Output only)
        values['OutBufCS'] = calc_checksum(buf, 5, end=122) + 7
        self.values = values

    # FIXME: this has side effects that should be removed
    # FIXME: self.values['HistoryInterval']
    # FIXME: self.values['OutBufCS']
    def testConfigChanged(self):
        """see if configuration has changed"""
        newbuf = [0] * 125
        # Set historyInterval to 5 minutes if > 5 minutes (default: 15 minutes)
        if self.values['HistoryInterval'] > HI_05MIN:
            logdbg('change HistoryInterval to 5 minutes')
            self.values['HistoryInterval'] = HI_05MIN
        newbuf[5] = self.values['Settings']
        newbuf[6] = self.values['TimeZone']
        newbuf[7] = self.values['HistoryInterval']
        for x in range(0, 9):
            lbl = 'Temp%s' % x
            self.parse_1(self.values[lbl + 'Max'] + SensorLimits.temperature_offset, newbuf, self.BUFMAP[0][x], 1, 3)
            self.parse_1(self.values[lbl + 'Min'] + SensorLimits.temperature_offset, newbuf, self.BUFMAP[1][x], 0, 3)
            self.reverseByteOrder(newbuf, self.BUFMAP[0][x], 3)  # Temp
            lbl = 'Humidity%s' % x
            self.parse_0(self.values[lbl + 'Max'], newbuf, self.BUFMAP[2][x], 1, 2)
            self.parse_0(self.values[lbl + 'Min'], newbuf, self.BUFMAP[3][x], 1, 2)
            self.reverseByteOrder(newbuf, self.BUFMAP[2][x], 2)  # Humidity
        # insert reverse self.values['AlarmSet'] into newbuf
        rev = self.values['AlarmSet'][::-1]
        for y in range(0, 5):
            newbuf[53+y] = rev[y]
        # insert reverse self.values['Description%d'] into newbuf
        for x in range(1, 9):
            rev = self.values['Description%d' % x][::-1]
            for y in range(0, 8):
                newbuf[self.BUFMAP[4][x-1]+y] = rev[y]
        newbuf[122] = self.values['ResetHiLo']
        # checksum is not calculated for ResetHiLo (Output only)
        self.values['OutBufCS'] = calc_checksum(newbuf, 5, end=122) + 7
        newbuf[123] = (self.values['OutBufCS'] >> 8) & 0xFF
        newbuf[124] = (self.values['OutBufCS'] >> 0) & 0xFF
        if self.values['OutBufCS'] == self.values['InBufCS']:
            if DEBUG_CONFIG_DATA > 2:
                logdbg('checksum not changed: OutBufCS=%04x' %
                       self.values['OutBufCS'])
            changed = 0
        else:
            if DEBUG_CONFIG_DATA > 0:
                logdbg('checksum changed: OutBufCS=%04x InBufCS=%04x ' % 
                       (self.values['OutBufCS'], self.values['InBufCS']))
            if self.values['InBufCS'] != 0 and DEBUG_CONFIG_DATA > 1:
                self.toLog()
            changed = 1
        return changed, newbuf

    def toLog(self):
        contrast = (int(self.values['Settings']) >> 4) & 0x0F
        alert = 'ON' if int(self.values['Settings']) & 0x8 == 0 else 'OFF'
        dcf_recep = 'OFF' if int(self.values['Settings']) & 0x4 == 0 else 'ON'
        time_form = '24h' if int(self.values['Settings']) & 0x2 == 0 else '12h'
        temp_form = 'C' if int(self.values['Settings']) & 0x1 == 0 else 'F'
        time_zone = self.values['TimeZone'] if int(self.values['TimeZone']) <= 12 else int(self.values['TimeZone'])-256
        history_interval = history_intervals.get(self.values['HistoryInterval'])
        logdbg('OutBufCS: %04x' % self.values['OutBufCS'])
        logdbg('InBufCS:  %04x' % self.values['InBufCS'])
        logdbg('Settings: %02x: contrast: %s, alert: %s, DCF reception: %s, time format: %s, temp format: %s' %
               (self.values['Settings'], contrast, alert, dcf_recep, time_form, temp_form))
        logdbg('TimeZone difference with Frankfurt (CET): %02x (tz: %s hour)' % (self.values['TimeZone'], time_zone))
        logdbg('HistoryInterval: %02x, period: %s minute(s)' % (self.values['HistoryInterval'], history_interval))
        byte_str = ' '.join(['%02x' % x for x in self.values['AlarmSet']])
        logdbg('AlarmSet:     %s' % byte_str)
        logdbg('ResetHiLo:    %02x' % self.values['ResetHiLo'])
        for x in range(0, 9):
            logdbg('Sensor%d:      %3.1f - %3.1f, %3.0f - %3.0f' %
                   (x,
                    self.values['Temp%dMin' % x], 
                    self.values['Temp%dMax' % x],
                    self.values['Humidity%dMin' % x],
                    self.values['Humidity%dMax' % x]))
        for x in range(1, 9):
            byte_str = ' '.join(['%02x' % y for y in self.values['Description%d' % x]])
            logdbg('Description%d: %s; SensorText%d: %s' % (x, byte_str, x, self.values['SensorText%s' % x]))

    def asDict(self):
        return {'checksum_in': self.values['InBufCS'],
                'checksum_out': self.values['OutBufCS'],
                'settings': self.values['Settings'],
                'history_interval': self.values['HistoryInterval']}


class HistoryData(object):

    BUFMAPHIS = {1: (176,
                     (174,173,171,170,168,167,165,164,162),
                     (161,160,159,158,157,156,155,154,153)),
                 2: (148,
                     (146,145,143,142,140,139,137,136,134),
                     (133,132,131,130,129,128,127,126,125)),
                 3: (120,
                     (118,117,115,114,112,111,109,108,106),
                     (105,104,103,102,101,100, 99, 98, 97)),
                 4: ( 92,
                     ( 90, 89, 87, 86, 84, 83, 81, 80, 78),
                     ( 77, 76, 75, 74, 73, 72, 71, 70, 69)),
                 5: ( 64,
                     ( 62, 61, 59, 58, 56, 55, 53, 52, 50),
                     ( 49, 48, 47, 46, 45, 44, 43, 42, 41)),
                 6: ( 36,
                     ( 34, 33, 31, 30, 28, 27, 25, 24, 22),
                     ( 21, 20, 19, 18, 17, 16, 15, 14, 13))}

    BUFMAPALA = {1: (180,175,174,172,170,169,168,167,166),
                 2: (152,147,146,144,142,141,140,139,138),
                 3: (124,119,118,116,114,113,112,111,110),
                 4: ( 96, 91, 90, 88, 86, 85, 84, 83, 82),
                 5: ( 68, 63, 62, 60, 58, 57, 56, 55, 54),
                 6: ( 40, 35, 34, 32, 30, 29, 28, 27, 26)}

    def __init__(self):
        self.values = {}
        for i in range(1, 7):
            self.values['Pos%dAlarm' % i] = 0
            self.values['Pos%dDT' % i] = datetime(1900, 01, 01, 00, 00)
            self.values['Pos%dHumidityHi' % i] = SensorLimits.humidity_NP
            self.values['Pos%dHumidityLo' % i] = SensorLimits.humidity_NP
            self.values['Pos%dHumidity' % i] = SensorLimits.humidity_NP
            self.values['Pos%dTempHi' % i] = SensorLimits.temperature_NP
            self.values['Pos%dTempLo' % i] = SensorLimits.temperature_NP
            self.values['Pos%dTemp' % i] = SensorLimits.temperature_NP
            self.values['Pos%dAlarmdata' % i] = 0
            self.values['Pos%dSensor' % i] = 0
            for j in range(0, 9):
                self.values['Pos%dTemp%d' % (i, j)] = SensorLimits.temperature_NP
                self.values['Pos%dHumidity%d' % (i, j)] = SensorLimits.humidity_NP

    def read(self, buf):
        values = {}
        for i in range(1, 7):
            values['Pos%dAlarm' % i] = 1 if buf[self.BUFMAPALA[i][0]] == 0xee else 0
            if values['Pos%dAlarm' % i] == 0:
                # History record
                values['Pos%dDT' % i] = Decode.toDateTime10(
                    buf, self.BUFMAPHIS[i][0], 1, 'HistoryData%d' % i)
                for j in range(0, 9):
                    values['Pos%dTemp%d' % (i, j)] = Decode.toTemperature_3_1(
                        buf, self.BUFMAPHIS[i][1][j], j%2)
                    values['Pos%dHumidity%d' % (i, j)] = Decode.toHumidity_2_0(
                        buf, self.BUFMAPHIS[i][2][j], 1)
            else:
                # Alarm record
                values['Pos%dDT' % i] = Decode.toDateTime10(
                    buf, self.BUFMAPALA[i][1], 1, 'HistoryData%d' % i)
                values['Pos%dHumidityHi' % i] = Decode.toHumidity_2_0(
                    buf, self.BUFMAPALA[i][8], 1)
                values['Pos%dHumidityLo' % i] = Decode.toHumidity_2_0(
                    buf, self.BUFMAPALA[i][7], 1)
                values['Pos%dHumidity' % i] = Decode.toHumidity_2_0(
                    buf, self.BUFMAPALA[i][6], 1)
                values['Pos%dTempHi' % i] = Decode.toTemperature_3_1(
                    buf, self.BUFMAPALA[i][5], 1)
                values['Pos%dTempLo' % i] = Decode.toTemperature_3_1(
                    buf, self.BUFMAPALA[i][4], 0)
                values['Pos%dTemp' % i] = Decode.toTemperature_3_1(
                    buf, self.BUFMAPALA[i][3], 0)
                values['Pos%dAlarmdata' % i] = (buf[self.BUFMAPALA[i][2]] >> 4) & 0xf
                values['Pos%dSensor' % i] = buf[self.BUFMAPALA[i][2]] & 0xf
        self.values = values

    def toLog(self):
        last_ts = None
        for i in range(1, 7):
            if self.values['Pos%dAlarm' % i] == 0:
                # History record
                if self.values['Pos%dDT' % i] != last_ts:
                    logdbg("Pos%dDT %s, Pos%dTemp0: %3.1f, Pos%sHumidity0: %3.1f" %
                           (i, self.values['Pos%dDT' % i],
                            i, self.values['Pos%dTemp0' % i],
                            i, self.values['Pos%dHumidity0' % i]))
                    logdbg("Pos%dTemp 1-8:      %3.1f, %3.1f, %3.1f, %3.1f, %3.1f, %3.1f, %3.1f, %3.1f" %
                           (i,
                            self.values['Pos%dTemp1' % i],
                            self.values['Pos%dTemp2' % i],
                            self.values['Pos%dTemp3' % i],
                            self.values['Pos%dTemp4' % i],
                            self.values['Pos%dTemp5' % i],
                            self.values['Pos%dTemp6' % i],
                            self.values['Pos%dTemp7' % i],
                            self.values['Pos%dTemp8' % i]))
                    logdbg("Pos%dHumidity 1-8: %3.0f, %3.0f, %3.0f, %3.0f, %3.0f, %3.0f, %3.0f, %3.0f" %
                           (i,
                            self.values['Pos%dHumidity1' % i],
                            self.values['Pos%dHumidity2' % i],
                            self.values['Pos%dHumidity3' % i],
                            self.values['Pos%dHumidity4' % i],
                            self.values['Pos%dHumidity5' % i],
                            self.values['Pos%dHumidity6' % i],
                            self.values['Pos%dHumidity7' % i],
                            self.values['Pos%dHumidity8' % i]))
                last_ts = self.values['Pos%dDT' % i]
            else:
                # Alarm record
                if self.values['Pos%dAlarmdata' % i] & 0x1:
                    logdbg('Alarm=%01x: Humidity%d: %3.0f above/reached Hi-limit (%3.0f) on %s' %
                        (self.values['Pos%dAlarmdata' % i],
                         self.values['Pos%dSensor' % i],
                         self.values['Pos%dHumidity' % i],
                         self.values['Pos%dHumidityHi' % i],
                         self.values['Pos%dDT' % i]))
                if self.values['Pos%dAlarmdata' % i] & 0x2:
                    logdbg('Alarm=%01x: Humidity%d: %3.0f below/reached Lo-limit (%3.0f) on %s' %
                        (self.values['Pos%dAlarmdata' % i],
                         self.values['Pos%dSensor' % i],
                         self.values['Pos%dHumidity' % i],
                         self.values['Pos%dHumidityLo' % i],
                         self.values['Pos%dDT' % i]))
                if self.values['Pos%dAlarmdata' % i] & 0x4:
                    logdbg('Alarm=%01x: Temp%d: %3.1f above/reached Hi-limit (%3.1f) on %s' %
                        (self.values['Pos%dAlarmdata' % i],
                         self.values['Pos%dSensor' % i],
                         self.values['Pos%dTemp' % i],
                         self.values['Pos%dTempHi' % i],
                         self.values['Pos%dDT' % i]))
                if self.values['Pos%dAlarmdata' % i] & 0x8:
                    logdbg('Alarm=%01x: Temp%d: %3.1f below/reached Lo-limit(%3.1f) on %s' %
                        (self.values['Pos%dAlarmdata' % i],
                         self.values['Pos%dSensor' % i],
                         self.values['Pos%dTemp' % i],
                         self.values['Pos%dTempLo' % i],
                         self.values['Pos%dDT' % i]))

    def asDict(self, x=1):
        """emit historical data as a dict with weewx conventions"""
        data = {'dateTime': tstr_to_ts(str(self.values['Pos%dDT' % x]))}
        for y in range(0, 9):
            data['Temp%d' % y] = self.values['Pos%dTemp%d' % (x, y)]
            data['Humidity%d' % y] = self.values['Pos%dHumidity%d' % (x, y)]
        return data


class HistoryCache:
    def __init__(self):
        self.wait_at_start = 1
        self.clear_records()

    def clear_records(self):
        self.since_ts = 0
        self.num_rec = 0
        self.start_index = None
        self.next_index = None
        self.records = []
        self.num_outstanding_records = None
        self.num_scanned = 0
        self.last_ts = 0


class TransceiverSettings(object): 
    def __init__(self):
        self.serial_number = None
        self.device_id = None


class LastStat(object):
    def __init__(self):
        self.last_link_quality = None
        self.last_history_index = None
        self.latest_history_index = None
        self.last_seen_ts = None
        self.last_weather_ts = 0
        self.last_history_ts = 0
        self.last_config_ts = 0

    def update(self, seen_ts=None, quality=None,
               weather_ts=None, history_ts=None, config_ts=None):
        if DEBUG_COMM > 1:
            logdbg('LastStat: seen=%s quality=%s weather=%s history=%s config=%s' %
                   (seen_ts, quality, weather_ts, history_ts, config_ts))
        if seen_ts is not None:
            self.last_seen_ts = seen_ts
        if quality is not None:
            self.last_link_quality = quality
        if weather_ts is not None:
            self.last_weather_ts = weather_ts
        if history_ts is not None:
            self.last_history_ts = history_ts
        if config_ts is not None:
            self.last_config_ts = config_ts


class Transceiver(object):
    """USB dongle abstraction"""

    def __init__(self):
        self.devh = None
        self.timeout = 1000
        self.last_dump = None

    def open(self, vid, pid, serial):
        device = Transceiver._find_device(vid, pid, serial)
        if device is None:
            logcrt('Cannot find USB device with Vendor=0x%04x ProdID=0x%04x Serial=%s' % 
                   (vid, pid, serial))
            raise weewx.WeeWxIOError('Unable to find transceiver on USB')
        self.devh = self._open_device(device)

    def close(self):
        Transceiver._close_device(self.devh)
        self.devh = None

    @staticmethod
    def _find_device(vid, pid, serial):
        for bus in usb.busses():
            for dev in bus.devices:
                if dev.idVendor == vid and dev.idProduct == pid:
                    if serial is None:
                        loginf('found transceiver at bus=%s device=%s' %
                               (bus.dirname, dev.filename))
                        return dev
                    else:
                        sn = Transceiver._read_serial(dev)
                        if str(serial) == sn:
                            loginf('found transceiver at bus=%s device=%s serial=%s' %
                                   (bus.dirname, dev.filename, sn))
                            return dev
                        else:
                            loginf('skipping transceiver with serial %s (looking for %s)' %
                                   (sn, serial))
        return None

    @staticmethod
    def _read_serial(dev):
        handle = None
        try:
            # see if we can read the serial without claiming the interface.
            # we do not want to disrupt any process that might already be
            # using the device.
            handle = Transceiver._open_device(dev)
            buf = Transceiver.readCfg(handle, 0x1F9, 7)
            if buf:
                return ''.join(['%02d' % x for x in buf[0:7]])
        except usb.USBError, e:
            logerr("cannot read serial number: %s" % e)
        finally:
            # if we claimed the interface, we must release it
            Transceiver._close_device(handle)
            # FIXME: not sure whether we must delete the handle
#            if handle is not None:
#                del handle
        return None

    @staticmethod
    def _open_device(dev, interface=0):
        handle = dev.open()
        if not handle:
            raise weewx.WeeWxIOError('Open USB device failed')

        loginf('manufacturer: %s' % handle.getString(dev.iManufacturer, 30))
        loginf('product: %s' % handle.getString(dev.iProduct, 30))
        loginf('interface: %d' % interface)

        # be sure kernel does not claim the interface
        try:
            handle.detachKernelDriver(interface)
        except usb.USBError:
            pass

        # attempt to claim the interface
        try:
            logdbg('claiming USB interface %d' % interface)
            handle.claimInterface(interface)
            handle.setAltInterface(interface)
        except usb.USBError, e:
            Transceiver._close_device(handle)
            logcrt('Unable to claim USB interface %s: %s' % (interface, e))
            raise weewx.WeeWxIOError(e)

        # FIXME: check return values
        usbWait = 0.05
        handle.getDescriptor(0x1, 0, 0x12)
        time.sleep(usbWait)
        handle.getDescriptor(0x2, 0, 0x9)
        time.sleep(usbWait)
        handle.getDescriptor(0x2, 0, 0x22)
        time.sleep(usbWait)
        handle.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                          0xa, [], 0x0, 0x0, 1000)
        time.sleep(usbWait)
        handle.getDescriptor(0x22, 0, 0x2a9)
        time.sleep(usbWait)
        return handle

    @staticmethod
    def _close_device(handle):
        if handle is not None:
            try:
                logdbg('releasing USB interface')
                handle.releaseInterface()
            except usb.USBError:
                pass

    def setTX(self):
        buf = [0] * 0x15
        buf[0] = 0xD1
        if DEBUG_COMM > 1:
            self.dump('setTX', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d1,
                             index=0x0000000,
                             timeout=self.timeout)

    def setRX(self):
        buf = [0] * 0x15
        buf[0] = 0xD0
        if DEBUG_COMM > 1:
            self.dump('setRX', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d0,
                             index=0x0000000,
                             timeout=self.timeout)

    def getState(self):
        buf = self.devh.controlMsg(
            requestType=usb.TYPE_CLASS | usb.RECIP_INTERFACE | usb.ENDPOINT_IN,
            request=usb.REQ_CLEAR_FEATURE,
            buffer=0x0a,
            value=0x00003de,
            index=0x0000000,
            timeout=self.timeout)
        if DEBUG_COMM > 1:
            self.dump('getState', buf, fmt=DEBUG_DUMP_FORMAT)
        return buf[1:3]

    def readConfigFlash(self, addr, nbytes):
        new_data = [0] * 0x15
        while nbytes:
            buf= [0xcc] * 0x0f  # 0x15
            buf[0] = 0xdd
            buf[1] = 0x0a
            buf[2] = (addr >> 8) & 0xFF
            buf[3] = (addr >> 0) & 0xFF
            if DEBUG_COMM > 1:
                self.dump('readCfgFlash>', buf, fmt=DEBUG_DUMP_FORMAT)
            self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                                 request=0x0000009,
                                 buffer=buf,
                                 value=0x00003dd,
                                 index=0x0000000,
                                 timeout=self.timeout)
            buf = self.devh.controlMsg(
                usb.TYPE_CLASS | usb.RECIP_INTERFACE | usb.ENDPOINT_IN,
                request=usb.REQ_CLEAR_FEATURE,
                buffer=0x15,
                value=0x00003dc,
                index=0x0000000,
                timeout=self.timeout)
            new_data = [0] * 0x15
            if nbytes < 16:
                for i in xrange(0, nbytes):
                    new_data[i] = buf[i + 4]
                nbytes = 0
            else:
                for i in xrange(0, 16):
                    new_data[i] = buf[i+4]
                nbytes -= 16
                addr += 16
            if DEBUG_COMM > 1:
                self.dump('readCfgFlash<', buf, fmt=DEBUG_DUMP_FORMAT)
        return new_data

    def setState(self, state):
        buf = [0] * 0x15
        buf[0] = 0xd7
        buf[1] = state
        if DEBUG_COMM > 1:
            self.dump('setState', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d7,
                             index=0x0000000,
                             timeout=self.timeout)

    def setFrame(self, nbytes, data):
        buf = [0] * 0x111
        buf[0] = 0xd5
        buf[1] = nbytes >> 8
        buf[2] = nbytes
        for i in xrange(0, nbytes):
            buf[i+3] = data[i]
        if DEBUG_COMM == 1:
            self.dump('setFrame', buf, 'short')
        elif DEBUG_COMM > 1:
            self.dump('setFrame', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d5,
                             index=0x0000000,
                             timeout=self.timeout)

    def getFrame(self):
        buf = self.devh.controlMsg(
            usb.TYPE_CLASS | usb.RECIP_INTERFACE | usb.ENDPOINT_IN,
            request=usb.REQ_CLEAR_FEATURE,
            buffer=0x111,
            value=0x00003d6,
            index=0x0000000,
            timeout=self.timeout)
        data= [0] * 0x131
        nbytes = (buf[1] << 8 | buf[2]) & 0x1ff
        for i in xrange(0, nbytes):
            data[i] = buf[i+3]
        if DEBUG_COMM == 1:
            self.dump('getFrame', buf, 'short')
        elif DEBUG_COMM > 1:
            self.dump('getFrame', buf, fmt=DEBUG_DUMP_FORMAT)
        return nbytes, data

    def writeReg(self, regAddr, data):
        buf = [0] * 0x05
        buf[0] = 0xf0
        buf[1] = regAddr & 0x7F
        buf[2] = 0x01
        buf[3] = data
        buf[4] = 0x00
        if DEBUG_COMM > 1:
            self.dump('writeReg', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003f0,
                             index=0x0000000,
                             timeout=self.timeout)

    def execute(self, command):
        buf = [0] * 0x0f  # 0x15
        buf[0] = 0xd9
        buf[1] = command
        if DEBUG_COMM > 1:
            self.dump('execute', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d9,
                             index=0x0000000,
                             timeout=self.timeout)

    def setPreamblePattern(self, pattern):
        buf = [0] * 0x15
        buf[0] = 0xd8
        buf[1] = pattern
        if DEBUG_COMM > 1:
            self.dump('setPreamble', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d8,
                             index=0x0000000,
                             timeout=self.timeout)

    # three formats, long, short, auto.  short shows only the first 16 bytes.
    # long shows the full length of the buffer.  auto shows the message length
    # as indicated by the length in the message itself for setFrame and
    # getFrame, or the first 16 bytes for any other message.
    def dump(self, cmd, buf, fmt='auto', length=301):
        strbuf = ''
        if fmt == 'auto':
            if buf[0] in [0xd5, 0x00]:
                msglen = buf[2] + 3        # use msg length for set/get frame
            else:
                msglen = 16                # otherwise do same as short format
        elif fmt == 'short':
            msglen = 16
        else:
            msglen = length                # dedicated 'long' length
        for i, x in enumerate(buf):
            strbuf += str('%02x ' % x)
            if (i + 1) % 16 == 0:
                self.dumpstr(cmd, strbuf)
                strbuf = ''
            if msglen is not None and i + 1 >= msglen:
                break
        if strbuf:
            self.dumpstr(cmd, strbuf)

    # filter output that we do not care about, pad the command string.
    def dumpstr(self, cmd, strbuf):
        pad = ' ' * (15 - len(cmd))
        # de15 is idle, de14 is intermediate
        if strbuf in ['de 15 00 00 00 00 ', 'de 14 00 00 00 00 ']:
            if strbuf != self.last_dump or DEBUG_COMM > 2:
                logdbg('%s: %s%s' % (cmd, pad, strbuf))
            self.last_dump = strbuf
        else:
            logdbg('%s: %s%s' % (cmd, pad, strbuf))
            self.last_dump = None

    @staticmethod
    def readCfg(handle, addr, nbytes, timeout=1000):
        new_data= [0] * 0x15
        while nbytes:
            buf = [0xcc] * 0x0f  # 0x15
            buf[0] = 0xdd
            buf[1] = 0x0a
            buf[2] = (addr >> 8) & 0xFF
            buf[3] = (addr >> 0) & 0xFF
            handle.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                              request=0x0000009,
                              buffer=buf,
                              value=0x00003dd,
                              index=0x0000000,
                              timeout=timeout)
            buf = handle.controlMsg(
                usb.TYPE_CLASS | usb.RECIP_INTERFACE | usb.ENDPOINT_IN,
                request=usb.REQ_CLEAR_FEATURE,
                buffer=0x15,
                value=0x00003dc,
                index=0x0000000,
                timeout=timeout)
            new_data = [0] * 0x15
            if nbytes < 16:
                for i in xrange(0, nbytes):
                    new_data[i] = buf[i+4]
                nbytes = 0
            else:
                for i in xrange(0, 16):
                    new_data[i] = buf[i+4]
                nbytes -= 16
                addr += 16
        return new_data


class AX5051RegisterNames:
    REVISION     = 0x0
    SCRATCH      = 0x1
    POWERMODE    = 0x2
    XTALOSC      = 0x3
    FIFOCTRL     = 0x4
    FIFODATA     = 0x5
    IRQMASK      = 0x6
    IFMODE       = 0x8
    PINCFG1      = 0x0C
    PINCFG2      = 0x0D
    MODULATION   = 0x10
    ENCODING     = 0x11
    FRAMING      = 0x12
    CRCINIT3     = 0x14
    CRCINIT2     = 0x15
    CRCINIT1     = 0x16
    CRCINIT0     = 0x17
    FREQ3        = 0x20
    FREQ2        = 0x21
    FREQ1        = 0x22
    FREQ0        = 0x23
    FSKDEV2      = 0x25
    FSKDEV1      = 0x26
    FSKDEV0      = 0x27
    IFFREQHI     = 0x28
    IFFREQLO     = 0x29
    PLLLOOP      = 0x2C
    PLLRANGING   = 0x2D
    PLLRNGCLK    = 0x2E
    TXPWR        = 0x30
    TXRATEHI     = 0x31
    TXRATEMID    = 0x32
    TXRATELO     = 0x33
    MODMISC      = 0x34
    FIFOCONTROL2 = 0x37
    ADCMISC      = 0x38
    AGCTARGET    = 0x39
    AGCATTACK    = 0x3A
    AGCDECAY     = 0x3B
    AGCCOUNTER   = 0x3C
    CICDEC       = 0x3F
    DATARATEHI   = 0x40
    DATARATELO   = 0x41
    TMGGAINHI    = 0x42
    TMGGAINLO    = 0x43
    PHASEGAIN    = 0x44
    FREQGAIN     = 0x45
    FREQGAIN2    = 0x46
    AMPLGAIN     = 0x47
    TRKFREQHI    = 0x4C
    TRKFREQLO    = 0x4D
    XTALCAP      = 0x4F
    SPAREOUT     = 0x60
    TESTOBS      = 0x68
    APEOVER      = 0x70
    TMMUX        = 0x71
    PLLVCOI      = 0x72
    PLLCPEN      = 0x73
    PLLRNGMISC   = 0x74
    AGCMANUAL    = 0x78
    ADCDCLEVEL   = 0x79
    RFMISC       = 0x7A
    TXDRIVER     = 0x7B
    REF          = 0x7C
    RXMISC       = 0x7D


class CommunicationService(object):

    def __init__(self, first_sleep, values):
        logdbg('CommunicationService.init')

        self.first_sleep = first_sleep
        self.values = values
        self.reg_names = dict()
        self.hid = Transceiver()
        self.transceiver_settings = TransceiverSettings()
        self.last_stat = LastStat()
        self.station_config = StationConfig()
        self.current = CurrentData()
        self.comm_mode_interval = 8
        self.config_serial = None  # the serial number given in weewx.conf
        self.transceiver_present = False
        self.registered_device_id = None

        self.firstSleep = 1
        self.nextSleep = 1
        self.pollCount = 0

        self.running = False
        self.child = None
        self.thread_wait = 60.0  # seconds

        self.command = None
        self.history_cache = HistoryCache()
        self.ts_last_rec = 0
        self.records_appended = 0
        self.records_skipped = 0

    def buildFirstConfigFrame(self, cs):
        logdbg('buildFirstConfigFrame: cs=%04x' % cs)
        newlen = 11
        newbuf = [0] * newlen
        historyAddress = 0x010700
        newbuf[0] = 0xF0
        newbuf[1] = 0xF0
        newbuf[2] = 0xFF
        newbuf[3] = ACTION_GET_CONFIG
        newbuf[4] = 0xFF
        newbuf[5] = 0xFF
        newbuf[6] = 0x80  # TODO: not known what this means; (we don't use the high part of self.comm_mode_interval here)
        newbuf[7] = self.comm_mode_interval & 0xFF
        newbuf[8] = (historyAddress >> 16) & 0xFF
        newbuf[9] = (historyAddress >> 8) & 0xFF
        newbuf[10] = (historyAddress >> 0) & 0xFF
        return newlen, newbuf

    def buildConfigFrame(self, buf):
        logdbg("buildConfigFrame")
        changed, cfgbuf = self.station_config.testConfigChanged()
        if changed:
            newlen = 125  # 0x7D
            newbuf = [0] * newlen
            newbuf[0] = buf[0]
            newbuf[1] = buf[1]
            newbuf[2] = LOGGER_1
            newbuf[3] = ACTION_SEND_CONFIG # 0x20 # change this value if we won't store config
            newbuf[4] = buf[4]
            for i in xrange(5, newlen):
                newbuf[i] = cfgbuf[i]
            if DEBUG_CONFIG_DATA > 2:
                self.hid.dump('OutBuf', newbuf, fmt='long', length=newlen)
        else:  # current config not up to date; do not write yet
            newlen = 0
            newbuf = [0]
        return newlen, newbuf

    @staticmethod
    def buildTimeFrame(buf, cs):
        logdbg("buildTimeFrame: cs=%04x" % cs)

        tm = time.localtime()

        # d5 00 0d 01 07 00 60 1a b1 25 58 21 04 03 41 01 
        #           0  1  2  3  4  5  6  7  8  9 10 11 12
        newlen = 13
        newbuf = [0] * newlen
        newbuf[0] = buf[0]
        newbuf[1] = buf[1]
        newbuf[2] = LOGGER_1
        newbuf[3] = ACTION_SEND_TIME  # 0x60
        newbuf[4] = (cs >> 8) & 0xFF
        newbuf[5] = (cs >> 0) & 0xFF
        newbuf[6] = (tm[5] % 10) + 0x10 * (tm[5] // 10)  # sec
        newbuf[7] = (tm[4] % 10) + 0x10 * (tm[4] // 10)  # min
        newbuf[8] = (tm[3] % 10) + 0x10 * (tm[3] // 10)  # hour
        # mo=0, tu=1, we=2, th=3, fr=4, sa=5, su=6  # DayOfWeek format of ws28xx devices
        # mo=1, tu=2, we=3, th=4, fr=5, sa=6, su=7  # DayOfWeek format of klimalogg devices
        DayOfWeek = tm[6]+1       # py  from 1 - 7 - 1=Mon
        newbuf[9]  = DayOfWeek % 10 + 0x10 * (tm[2] % 10)           # day_lo   + DoW
        newbuf[10] = (tm[2] // 10)  + 0x10 * (tm[1] % 10)           # month_lo + day_hi
        newbuf[11] = (tm[1] // 10)  + 0x10 * ((tm[0] - 2000) % 10)  # year-lo  + month-hi
        newbuf[12] = (tm[0] - 2000) // 10                           # not used + year-hi
        return newlen, newbuf

    def buildACKFrame(self, buf, action, cs, hidx=None):
        if DEBUG_COMM > 1:
            logdbg("buildACKFrame: action=%x cs=%04x historyIndex=%s" %
                   (action, cs, hidx))

        comInt = self.comm_mode_interval

        # When last weather is stale, change action to get current weather
        # This is only needed during long periods of history data catchup
        if self.command == ACTION_GET_HISTORY:
            now = int(time.time())
            age = now - self.last_stat.last_weather_ts
            # Morphing action only with GetHistory requests, 
            # and stale data after a period of twice the CommModeInterval,
            # but not with init GetHistory requests (0xF0)
            if (action == ACTION_GET_HISTORY and
                age >= (comInt +1) * 2 and buf[1] != 0xF0):
                if DEBUG_COMM > 0:
                    logdbg('buildACKFrame: morphing action'
                           ' from %d to 5 (age=%s)' % (action, age))
                action = ACTION_GET_CURRENT

        if hidx is None:
            if self.last_stat.latest_history_index is not None:
                hidx = self.last_stat.latest_history_index
        if hidx is None or hidx < 0 or hidx >= KlimaLoggDriver.max_records:
            haddr = 0xffffff
        else:
            haddr = index_to_addr(hidx)
        if DEBUG_COMM > 1:
            logdbg('buildACKFrame: idx: %s addr: 0x%04x' % (hidx, haddr))

        # d5 00 0b f0 f0 ff 03 ff ff 80 03 01 07 00
        #           0  1  2  3  4  5  6  7  8  9 10
        newlen = 11
        newbuf = [0] * newlen
        newbuf[0] = buf[0]
        newbuf[1] = buf[1]
        newbuf[2] = LOGGER_1
        newbuf[3] = action & 0xF
        newbuf[4] = (cs >> 8) & 0xFF
        newbuf[5] = (cs >> 0) & 0xFF
        newbuf[6] = 0x80  # TODO: not known what this means
        newbuf[7] = comInt & 0xFF
        newbuf[8] = (haddr >> 16) & 0xFF
        newbuf[9] = (haddr >> 8) & 0xFF
        newbuf[10] = (haddr >> 0) & 0xFF
        return newlen, newbuf

    def handleConfig(self, length, buf):
        logdbg('handleConfig: %s' % self.timing())
        if DEBUG_CONFIG_DATA > 2:
            self.hid.dump('InBuf', buf, fmt='long', length=length)
        self.station_config.read(buf)
        if DEBUG_CONFIG_DATA > 1:
            self.station_config.toLog()
        now = int(time.time())
        self.last_stat.update(seen_ts=now,
                              quality=(buf[4] & 0x7f), 
                              config_ts=now)
        cs = buf[124] | (buf[123] << 8)
        self.setSleep(self.first_sleep, 0.010)
        return self.buildACKFrame(buf, ACTION_GET_HISTORY, cs)

    def handleCurrentData(self, length, buf):
        if DEBUG_WEATHER_DATA > 0:
            logdbg('handleCurrentData: %s' % self.timing())

        now = int(time.time())

        # update the weather data cache if stale
        age = now - self.last_stat.last_weather_ts
        if age >= self.comm_mode_interval:
            if DEBUG_WEATHER_DATA > 2:
                self.hid.dump('CurWea', buf, fmt='long', length=length)
            data = CurrentData()
            data.read(buf)
            self.current = data
            if DEBUG_WEATHER_DATA > 1:
                data.toLog()
        else:
            if DEBUG_WEATHER_DATA > 1:
                logdbg('new weather data within %s; skip data; ts=%s' % 
                       (age, now))

        # update the connection cache
        self.last_stat.update(seen_ts=now,
                              quality=(buf[4] & 0x7f),
                              weather_ts=now)

        cs = buf[6] | (buf[5] << 8)
        self.station_config.setSensorText(self.values)
        changed, cfgbuf = self.station_config.testConfigChanged()
        inBufCS = self.station_config.getInBufCS()
        if inBufCS == 0 or inBufCS != cs:
            # request for a get config
            logdbg('handleCurrentData: inBufCS of station does not match')
            self.setSleep(self.first_sleep, 0.010)
            newlen, newbuf = self.buildACKFrame(buf, ACTION_GET_CONFIG, cs)
        elif changed:
            # Request for a set config
            logdbg('handleCurrentData: outBufCS of station changed')
            self.setSleep(self.first_sleep, 0.010)
            newlen, newbuf = self.buildACKFrame(buf, ACTION_REQ_SET_CONFIG, cs)
        else:
            # Request for either a history message or a current weather message
            # In general we don't use ACTION_GET_CURRENT to ask for a current
            # weather  message; they also come when requested for
            # ACTION_GET_HISTORY. This we learned from the Heavy Weather Pro
            # messages (via USB sniffer).
            self.setSleep(self.first_sleep, 0.010)
            newlen, newbuf = self.buildACKFrame(buf, ACTION_GET_HISTORY, cs)
        return newlen, newbuf

    # timestamp of record with time 'None'
    TS_1900 = tstr_to_ts(str(datetime(1900, 01, 01, 00, 00)))

    # initially the clock of the KlimaLogg station starts at 1-jan-2010,
    # so skip all records elder than 1-jul-2010
    # eldest valid timestamp for history record
    TS_2010_07 = tstr_to_ts(str(datetime(2010, 07, 01, 00, 00)))

    def handleHistoryData(self, length, buf):
        if DEBUG_HISTORY_DATA > 0:
            logdbg('handleHistoryData: %s' % self.timing())

        now = int(time.time())
        self.last_stat.update(seen_ts=now,
                              quality=(buf[4] & 0x7f),
                              history_ts=now)

        data = HistoryData()
        data.read(buf)
        if DEBUG_HISTORY_DATA > 1:
            data.toLog()

        cs = buf[6] | (buf[5] << 8)
        latestAddr = bytes_to_addr(buf[7], buf[8], buf[9])
        thisAddr = bytes_to_addr(buf[10], buf[11], buf[12])
        latestIndex = addr_to_index(latestAddr)
        thisIndex = addr_to_index(thisAddr)

        tsPos1 = tstr_to_ts(str(data.values['Pos1DT']))
        tsPos2 = tstr_to_ts(str(data.values['Pos2DT']))
        tsPos6 = tstr_to_ts(str(data.values['Pos6DT']))
        if tsPos1 == self.TS_1900:
            # the first history record has date-time 1900-01-01 00:00:00
            # use the time difference with the second message
            tsFirstRec = tsPos2
        else:
            tsFirstRec = tsPos1
        if tsFirstRec is None or tsFirstRec == self.TS_1900:
            timeDiff = 0
        else:
            timeDiff = abs(now - tsFirstRec)

        # FIXME: what if we do not have config data yet?
        cfg = self.getConfigData().asDict()
        dcfOn = 'OFF' if int(cfg['settings']) & 0x4 == 0 else 'ON'

        # check for an actual history record (tsPos1 == tsPos2) with valid
        # timestamp (tsPos1 != TS_1900)
        # Take in account that communication might be stalled for 3 minutes during DCF reception and sensor scanning
        # if history date/time differs more than 5 min from now then
        # reqSetTime and initiate alarm
        if data.values['Pos1Alarm'] == 0 and data.values['Pos6Alarm'] == 0:
            # both records are history records
            if tsPos1 == tsPos6 and tsPos1 != self.TS_1900:
                if timeDiff > 300:
                    self.station_config.setAlarmClockOffset()  # set Humidity0Min value to 99
                    logerr('ERROR: DCF: %s; dateTime history record %s differs %s seconds from dateTime server; please check and set set the clock of your station' %
                           (dcfOn, thisIndex, timeDiff))
                    logerr('ERROR: tsPos1: %s, tsPos2: %s' % (tsPos1, tsPos6))
                else:
                    self.station_config.resetAlarmClockOffset()  # set Humidity0Min value to 20
                    if timeDiff > 30:
                        logdbg('DCF = %s; dateTime history record %s differs %s seconds from dateTime server' %
                               (dcfOn, thisIndex, timeDiff))

        # initially the first buffer presented is 6, in fact it starts at 0,
        # which has date None, so we start at 1
        if thisIndex == 6 and latestIndex > 12:
            thisIndex = 1
        nrec = get_index(latestIndex - thisIndex)
        logdbg('handleHistoryData: time=%s this=%d (0x%04x) latest=%d (0x%04x) nrec=%d' %
               (data.values['Pos1DT'],
                thisIndex, thisAddr, latestIndex, latestAddr, nrec))

        # track the latest history index
        self.last_stat.last_history_index = thisIndex
        self.last_stat.latest_history_index = latestIndex

        nextIndex = None
        if self.command == ACTION_GET_HISTORY:
            if self.history_cache.start_index is None:
                if self.history_cache.num_rec > 0:
                    loginf('handleHistoryData: request for %s records' %
                           self.history_cache.num_rec)
                    nreq = self.history_cache.num_rec
                else:
                    if self.history_cache.since_ts > 0:
                        loginf('handleHistoryData: request records since %s' %
                               weeutil.weeutil.timestamp_to_string(self.history_cache.since_ts))
                        span = int(time.time()) - self.history_cache.since_ts
                        if cfg['history_interval'] is not None:
                            arcint = 60 * history_intervals.get(cfg['history_interval'])
                        else:
                            arcint = 60 * 15  # use the typical history interval of 15 min if interval not known yet
                        # FIXME: this assumes a constant archive interval for
                        # all records in the station history
                        nreq = int(span / arcint) + 5  # FIXME: punt 5
                        if nreq > nrec:
                            loginf('handleHistoryData: too many records requested (%d), clipping to number stored (%d)' %
                                  (nreq, nrec))
                            nreq = nrec
                    else:
                        loginf('handleHistoryData: no start date known (empty database), use number stored (%d)' % nrec)
                        nreq = nrec
                # Workaround for nrec up to 50,000; limit this number to limit_rec_read
                if nreq > LIMIT_REC_READ_TO:
                    nreq = LIMIT_REC_READ_TO
                    logdbg('Number of history records to catch up limited to: %s' % nreq)
                if nreq >= KlimaLoggDriver.max_records:
                    nrec = KlimaLoggDriver.max_records-1
                idx = get_index(latestIndex - nreq)
                self.history_cache.start_index = idx
                self.history_cache.next_index = idx
                self.last_stat.last_history_index = idx
                self.history_cache.num_outstanding_records = nreq
                logdbg('handleHistoryData: start_index=%s'
                       ' num_outstanding_records=%s' % (idx, nreq))
                nextIndex = idx
                self.records_appended = 0
                self.records_skipped = 0
                self.ts_last_rec = 0
            elif self.history_cache.next_index is not None:

                # thisIndex should be the 1-6 record(s) after next_index (note: index cycles after 51199 to 0)
                indexRequested = self.history_cache.next_index
                # check if thisIndex is within the range expected
                thisIndexOk = False
                if indexRequested + 6 < KlimaLoggDriver.max_records:
                    # indexRequested 0 .. 51193
                    if indexRequested + 1 <= thisIndex <= indexRequested + 6:
                        thisIndexOk = True
                elif indexRequested == (KlimaLoggDriver.max_records -1):
                    # indexRequested = 51199
                    if 0 <= thisIndex <= 5:
                        thisIndexOk = True
                elif thisIndex > indexRequested or thisIndex <= (indexRequested + 6 - KlimaLoggDriver.max_records):
                    # indexRequested 51194 .. 51198 and thisIndex is within one of two ranges
                    thisIndexOk = True

                if thisIndexOk:
                    # get the next 1-6 history record(s)
                    for x in range(1, 7):
                        if data.values['Pos%dAlarm' % x] == 0:
                            # History record
                            tsCurrentRec = tstr_to_ts(str(data.values['Pos%dDT' % x]))
                            # skip records which are too old or elder than requested
                            if tsCurrentRec >= self.TS_2010_07 and tsCurrentRec >= self.history_cache.since_ts:
                                # skip records with dateTime in the future
                                if tsCurrentRec > (now + 300):
                                    logdbg('handleHistoryData: skipped record at Pos%d tsCurrentRec=%s DT is in the future' %
                                          (x, weeutil.weeutil.timestamp_to_string(tsCurrentRec)))
                                    self.records_skipped += 1
                                # Check if two records in a row with the same ts
                                elif tsCurrentRec == self.ts_last_rec:
                                    logdbg('handleHistoryData: skipped record at Pos%d tsCurrentRec=%s DT is the same' %
                                           (x, weeutil.weeutil.timestamp_to_string(tsCurrentRec)))
                                    self.records_skipped += 1
                                # Check if this record elder than previous good record
                                elif tsCurrentRec < self.ts_last_rec:
                                    logdbg('handleHistoryData: skipped record at Pos%d tsCurrentRec=%s DT is in the past' %
                                           (x, weeutil.weeutil.timestamp_to_string(tsCurrentRec)))
                                    self.records_skipped += 1
                                # Check if this record more than 1 day newer than previous good record
                                elif self.ts_last_rec != 0 and tsCurrentRec > self.ts_last_rec + 86400:
                                    logdbg('handleHistoryData: skipped record at Pos%d tsCurrentRec=%s DT has too big diff' %
                                           (x, weeutil.weeutil.timestamp_to_string(tsCurrentRec)))
                                    self.records_skipped += 1
                                else:
                                    # append good record to the history
                                    logdbg('handleHistoryData:  append record at Pos%d tsCurrentRec=%s' %
                                           (x, weeutil.weeutil.timestamp_to_string(tsCurrentRec)))
                                    self.history_cache.records.append(data.asDict(x))
                                    self.records_appended += 1
                                    # save only TS of good records
                                    self.ts_last_rec = tsCurrentRec
                            # Check if this record is too old or has no date
                            elif tsCurrentRec < self.TS_2010_07:
                                logerr('handleHistoryData: skippd record at Pos%d tsCurrentRec=None DT is too old' % x)
                                self.records_skipped += 1
                            else:
                                # this record is elder than the requested start dateTime
                                logdbg('handleHistoryData: skipped record at Pos%d tsCurrentRec=%s < %s' %
                                       (x, weeutil.weeutil.timestamp_to_string(tsCurrentRec),
                                        weeutil.weeutil.timestamp_to_string(self.history_cache.since_ts)))
                                self.records_skipped += 1
                        self.history_cache.next_index = thisIndex
                else:
                    loginf('handleHistoryData: index mismatch: indexRequested: %s, thisIndex: %s' %
                           (indexRequested, thisIndex))
                nextIndex = self.history_cache.next_index
            self.history_cache.num_scanned += 1
            self.history_cache.num_outstanding_records = nrec
            logdbg('handleHistoryData: records appended=%s, records skipped=%s, next=%s' %
                   (self.records_appended, self.records_skipped, nextIndex))

        self.setSleep(self.first_sleep, 0.010)
        newlen, newbuf = self.buildACKFrame(buf, ACTION_GET_HISTORY, cs, nextIndex)
        return newlen, newbuf

    def handleNextAction(self, length, buf):
        self.last_stat.update(seen_ts=int(time.time()),
                              quality=(buf[4] & 0x7f))
        cs = buf[6] | (buf[5] << 8)
        resp = buf[3]
        if resp == RESPONSE_REQ_READ_HISTORY:
            memPerc = buf[4]
            logdbg('handleNextAction: %02x (MEM percentage not read to server: %s)' % (resp, memPerc))
            self.setSleep(0.075, 0.005)
            newlen = length
            newbuf = buf
        elif resp == RESPONSE_REQ_FIRST_CONFIG:
            logdbg('handleNextAction: %02x (first-time config)' % resp)
            self.setSleep(0.075, 0.005)
            newlen, newbuf = self.buildFirstConfigFrame(cs)
        elif resp == RESPONSE_REQ_SET_CONFIG:
            logdbg('handleNextAction: %02x (set config data)' % resp)
            self.setSleep(0.075, 0.005)
            newlen, newbuf = self.buildConfigFrame(buf)
        elif resp == RESPONSE_REQ_SET_TIME:
            logdbg('handleNextAction: %02x (set time data)' % resp)
            self.setSleep(0.075, 0.005)
            newlen, newbuf = self.buildTimeFrame(buf, cs)
        else:
            logdbg('handleNextAction: %02x' % resp)
            self.setSleep(self.first_sleep, 0.010)
            newlen, newbuf = self.buildACKFrame(buf, ACTION_GET_HISTORY, cs)
        return newlen, newbuf

    def generateResponse(self, length, buf):
        if DEBUG_COMM > 1:
            logdbg('generateResponse: %s' % self.timing())
        if length == 0:
            raise BadResponse('zero length buffer')

        bufferID = (buf[0] << 8) | buf[1]
        respType = (buf[3] & 0xF0)
        if DEBUG_COMM > 1:
            logdbg("generateResponse: id=%04x resp=%x length=%x" %
                   (bufferID, respType, length))
        deviceID = self.getDeviceID()

        if bufferID == 0xF0F0:
            loginf('generateResponse: console not paired (synchronized), attempting to pair to 0x%04x' % deviceID)
            newlen, newbuf = self.buildACKFrame(buf, ACTION_GET_CONFIG, deviceID, 0xFFFF)
        elif bufferID == deviceID:
            self.set_registered_device_id(bufferID)  # the station and transceiver are paired now
            if respType == RESPONSE_DATA_WRITTEN:
                if length == 0x07:  # 7
                    self.hid.setRX()
                    raise DataWritten()
                else:
                    raise BadResponse('len=%x resp=%x' % (length, respType))
            elif respType == RESPONSE_GET_CONFIG:
                if length == 0x7D:  # 125
                    newlen, newbuf = self.handleConfig(length, buf)
                else:
                    raise BadResponse('len=%x resp=%x' % (length, respType))
            elif respType == RESPONSE_GET_CURRENT:
                if length == 0xE5:  # 229
                    newlen, newbuf = self.handleCurrentData(length, buf)
                else:
                    raise BadResponse('len=%x resp=%x' % (length, respType))
            elif respType == RESPONSE_GET_HISTORY:
                if length == 0xB5:  # 181
                    newlen, newbuf = self.handleHistoryData(length, buf)
                else:
                    raise BadResponse('len=%x resp=%x' % (length, respType))
            elif respType == RESPONSE_REQUEST:
                if length == 0x07:  # 7
                    newlen, newbuf = self.handleNextAction(length, buf)
                    self.hid.setState(0)
                else:
                    raise BadResponse('len=%x resp=%x' % (length, respType))
            else:
                raise BadResponse('unexpected response type %x' % respType)
        else:
            # Note: the following code is meant for a ws28xx model weather station used together with a KlimaLogg Pro
            # or two ws28xx model weather stations or two klimalogg pro stations working together
            # We don't want to intercept any non-current weather message of the other station twice to avoid a stall
            # of the other stattions communication, so we wait 400 ms to let the other station read the message.
            # When no second transceiver is present (and thus no serial is given in weewx.conf) we don't come here
            if self.config_serial is not None and (
                    length == 0x7d or length == 0xb5 or length == 0x07 or
                    length == 0x30 or length == 0x1e or length == 0x06):
                logerr('generateResponse: intercepted message from device %04x with length: %02x; wait 400 ms' % (bufferID, length))
                self.setSleep(0.400, 0.010)
            else:
                self.setSleep(0.075, 0.005)
            raise UnknownDeviceId('unexpected device ID (id=%04x)' % bufferID)
        return newlen, newbuf

    def configureRegisterNames(self):
        self.reg_names[AX5051RegisterNames.IFMODE]     = 0x00
        self.reg_names[AX5051RegisterNames.MODULATION] = 0x41  # fsk
        self.reg_names[AX5051RegisterNames.ENCODING]   = 0x07
        self.reg_names[AX5051RegisterNames.FRAMING]    = 0x84  # 1000:0100 ##?hdlc? |1000 010 0
        self.reg_names[AX5051RegisterNames.CRCINIT3]   = 0xff
        self.reg_names[AX5051RegisterNames.CRCINIT2]   = 0xff
        self.reg_names[AX5051RegisterNames.CRCINIT1]   = 0xff
        self.reg_names[AX5051RegisterNames.CRCINIT0]   = 0xff
        self.reg_names[AX5051RegisterNames.FREQ3]      = 0x38
        self.reg_names[AX5051RegisterNames.FREQ2]      = 0x90
        self.reg_names[AX5051RegisterNames.FREQ1]      = 0x00
        self.reg_names[AX5051RegisterNames.FREQ0]      = 0x01
        self.reg_names[AX5051RegisterNames.PLLLOOP]    = 0x1d
        self.reg_names[AX5051RegisterNames.PLLRANGING] = 0x08
        self.reg_names[AX5051RegisterNames.PLLRNGCLK]  = 0x03
        self.reg_names[AX5051RegisterNames.MODMISC]    = 0x03
        self.reg_names[AX5051RegisterNames.SPAREOUT]   = 0x00
        self.reg_names[AX5051RegisterNames.TESTOBS]    = 0x00
        self.reg_names[AX5051RegisterNames.APEOVER]    = 0x00
        self.reg_names[AX5051RegisterNames.TMMUX]      = 0x00
        self.reg_names[AX5051RegisterNames.PLLVCOI]    = 0x01
        self.reg_names[AX5051RegisterNames.PLLCPEN]    = 0x01
        self.reg_names[AX5051RegisterNames.RFMISC]     = 0xb0
        self.reg_names[AX5051RegisterNames.REF]        = 0x23
        self.reg_names[AX5051RegisterNames.IFFREQHI]   = 0x20
        self.reg_names[AX5051RegisterNames.IFFREQLO]   = 0x00
        self.reg_names[AX5051RegisterNames.ADCMISC]    = 0x01
        self.reg_names[AX5051RegisterNames.AGCTARGET]  = 0x0e
        self.reg_names[AX5051RegisterNames.AGCATTACK]  = 0x11
        self.reg_names[AX5051RegisterNames.AGCDECAY]   = 0x0e
        self.reg_names[AX5051RegisterNames.CICDEC]     = 0x3f
        self.reg_names[AX5051RegisterNames.DATARATEHI] = 0x19
        self.reg_names[AX5051RegisterNames.DATARATELO] = 0x66
        self.reg_names[AX5051RegisterNames.TMGGAINHI]  = 0x01
        self.reg_names[AX5051RegisterNames.TMGGAINLO]  = 0x96
        self.reg_names[AX5051RegisterNames.PHASEGAIN]  = 0x03
        self.reg_names[AX5051RegisterNames.FREQGAIN]   = 0x04
        self.reg_names[AX5051RegisterNames.FREQGAIN2]  = 0x0a
        self.reg_names[AX5051RegisterNames.AMPLGAIN]   = 0x06
        self.reg_names[AX5051RegisterNames.AGCMANUAL]  = 0x00
        self.reg_names[AX5051RegisterNames.ADCDCLEVEL] = 0x10
        self.reg_names[AX5051RegisterNames.RXMISC]     = 0x35
        self.reg_names[AX5051RegisterNames.FSKDEV2]    = 0x00
        self.reg_names[AX5051RegisterNames.FSKDEV1]    = 0x31
        self.reg_names[AX5051RegisterNames.FSKDEV0]    = 0x27
        self.reg_names[AX5051RegisterNames.TXPWR]      = 0x03
        self.reg_names[AX5051RegisterNames.TXRATEHI]   = 0x00
        self.reg_names[AX5051RegisterNames.TXRATEMID]  = 0x51
        self.reg_names[AX5051RegisterNames.TXRATELO]   = 0xec
        self.reg_names[AX5051RegisterNames.TXDRIVER]   = 0x88

    def initTransceiver(self, frequency_standard):
        self.configureRegisterNames()

        # calculate the frequency then set frequency registers
        logdbg('frequency standard: %s' % frequency_standard)
        freq = frequencies.get(frequency_standard, frequencies['EU'])
        loginf('base frequency: %d' % freq)
        freqVal = long(freq / 16000000.0 * 16777216.0)
        corVec = self.hid.readConfigFlash(0x1F5, 4)
        corVal = corVec[0] << 8
        corVal |= corVec[1]
        corVal <<= 8
        corVal |= corVec[2]
        corVal <<= 8
        corVal |= corVec[3]
        loginf('frequency correction: %d (0x%x)' % (corVal, corVal))
        freqVal += corVal
        if not (freqVal % 2):
            freqVal += 1
        loginf('adjusted frequency: %d (0x%x)' % (freqVal, freqVal))
        self.reg_names[AX5051RegisterNames.FREQ3] = (freqVal >> 24) & 0xFF
        self.reg_names[AX5051RegisterNames.FREQ2] = (freqVal >> 16) & 0xFF
        self.reg_names[AX5051RegisterNames.FREQ1] = (freqVal >> 8)  & 0xFF
        self.reg_names[AX5051RegisterNames.FREQ0] = (freqVal >> 0)  & 0xFF
        logdbg('frequency registers: %x %x %x %x' % (
            self.reg_names[AX5051RegisterNames.FREQ3],
            self.reg_names[AX5051RegisterNames.FREQ2],
            self.reg_names[AX5051RegisterNames.FREQ1],
            self.reg_names[AX5051RegisterNames.FREQ0]))

        # figure out the transceiver id
        buf = self.hid.readConfigFlash(0x1F9, 7)
        tid = (buf[5] << 8) + buf[6]
        loginf('transceiver identifier: %d (0x%04x)' % (tid, tid))
        self.transceiver_settings.device_id = tid

        # figure out the transceiver serial number
        sn = ''.join(['%02d' % x for x in buf[0:7]])
        loginf('transceiver serial: %s' % sn)
        self.transceiver_settings.serial_number = sn

        for r in self.reg_names:
            self.hid.writeReg(r, self.reg_names[r])

    def setup(self, frequency_standard, comm_interval,
              vendor_id, product_id, serial):
        loginf("comm_interval is %s" % comm_interval)
        self.comm_mode_interval = comm_interval
        self.config_serial = serial  # the serial number given in weewx.conf
        self.hid.open(vendor_id, product_id, serial)
        self.initTransceiver(frequency_standard)
        self.transceiver_present = True

    def teardown(self):
        self.transceiver_present = False
        self.hid.close()

    def getTransceiverPresent(self):
        return self.transceiver_present

    def set_registered_device_id(self, val):
        if val != self.registered_device_id:
            loginf("console is paired (synchronized) to device with ID %04x" % val)
        self.registered_device_id = val

    def getDeviceRegistered(self):
        if (self.registered_device_id is None or
            self.transceiver_settings.device_id is None or
            self.registered_device_id != self.transceiver_settings.device_id):
            return False
        return True

    def getDeviceID(self):
        return self.transceiver_settings.device_id

    def getTransceiverSerNo(self):
        return self.transceiver_settings.serial_number

    # FIXME: make this thread-safe
    def getCurrentData(self):
        return self.current

    # FIXME: make this thread-safe
    def getLastStat(self):
        return self.last_stat

    # FIXME: make this thread-safe
    def getConfigData(self):
        return self.station_config

    def startCachingHistory(self, since_ts=0, num_rec=0):
        self.history_cache.clear_records()
        if since_ts is None:
            since_ts = 0
        self.history_cache.since_ts = since_ts
        if num_rec > KlimaLoggDriver.max_records - 2:
            num_rec = KlimaLoggDriver.max_records - 2
        self.history_cache.num_rec = num_rec
        self.command = ACTION_GET_HISTORY

    def stopCachingHistory(self):
        self.command = None

    def getUncachedHistoryCount(self):
        return self.history_cache.num_outstanding_records

    def getNextHistoryIndex(self):
        return self.history_cache.next_index

    def getNumHistoryScanned(self):
        return self.history_cache.num_scanned

    def getLatestHistoryIndex(self):
        return self.last_stat.latest_history_index

    def getHistoryCacheRecords(self):
        return self.history_cache.records

    def clearHistoryCache(self):
        self.history_cache.clear_records()

    def clearWaitAtStart(self):
        self.history_cache.wait_at_start = 0

    def startRFThread(self):
        if self.child is not None:
            return
        logdbg('startRFThread: spawning RF thread')
        self.running = True
        self.child = threading.Thread(target=self.doRF)
        self.child.setName('RFComm')
        self.child.setDaemon(True)
        self.child.start()

    def stopRFThread(self):
        self.running = False
        logdbg('stopRFThread: waiting for RF thread to terminate')
        self.child.join(self.thread_wait)
        if self.child.isAlive():
            logerr('unable to terminate RF thread after %d seconds' %
                   self.thread_wait)
        else:
            self.child = None

    def isRunning(self):
        return self.running

    def doRF(self):
        try:
            logdbg('setting up rf communication')
            self.doRFSetup()
            # wait for genStartupRecords to start
            while self.history_cache.wait_at_start == 1:
                time.sleep(1)
            logdbg("starting rf communication; press USB button shortly if communication won't start")
            while self.running:
                self.doRFCommunication()
        except Exception, e:
            logerr('exception in doRF: %s' % e)
            if weewx.debug:
                log_traceback(dst=syslog.LOG_ERR)
            self.running = False
            raise
        finally:
            logdbg('stopping rf communication')

    # it is probably not necessary to have two setPreamblePattern invocations.
    # however, HeavyWeatherPro seems to do it this way on a first time config.
    # doing it this way makes configuration easier during a factory reset and
    # when re-establishing communication with the station sensors.
    def doRFSetup(self):
        self.hid.execute(5)
        self.hid.setPreamblePattern(0xaa)
        self.hid.setState(0)
        time.sleep(1)
        self.hid.setRX()

        self.hid.setPreamblePattern(0xaa)
        self.hid.setState(0x1e)
        time.sleep(1)
        self.hid.setRX()
        self.setSleep(0.075, 0.005)

    def doRFCommunication(self):
        time.sleep(self.firstSleep)
        self.pollCount = 0
        while self.running:
            statebuf = [0] * 2
            try:
                statebuf = self.hid.getState()
            except Exception, e:
                logerr('getState failed: %s' % e)
                time.sleep(5)
                pass
            self.pollCount += 1
            if statebuf[0] == 0x16:
                break
            time.sleep(self.nextSleep)
        else:
            return

        framelen, framebuf = self.hid.getFrame()
        try:
            framelen, framebuf = self.generateResponse(framelen, framebuf)
            self.hid.setFrame(framelen, framebuf)
            self.hid.setTX()
        except DataWritten:
            logdbg('SetTime/SetConfig data written')
            self.hid.setRX()
        except BadResponse, e:
            logerr('generateResponse failed: %s' % e)
            self.hid.setRX()
        except UnknownDeviceId, e:
            if self.config_serial is None:
                logerr("%s; use parameter 'serial' if more than one USB transceiver present" % e)
            self.hid.setRX()

    # these are for diagnostics and debugging
    def setSleep(self, firstsleep, nextsleep):
        self.firstSleep = firstsleep
        self.nextSleep = nextsleep

    def timing(self):
        s = self.firstSleep + self.nextSleep * (self.pollCount - 1)
        return 'sleep=%s first=%s next=%s count=%s' % (
            s, self.firstSleep, self.nextSleep, self.pollCount)

