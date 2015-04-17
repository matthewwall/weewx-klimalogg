# installer for KlimaLoggPro driver

from setup import ExtensionInstaller

def loader():
    return KlimaLoggInstaller()

class KlimaLoggInstaller(ExtensionInstaller):
    def __init__(self):
        super(KlimaLoggInstaller, self).__init__(
            version="0.29p8",
            name='klimalogg',
            description='driver for KlimaLoggPro',
            author="Hans (Luc) Heijst",
            config={
                'Station': {
                    'station_type': 'KlimaLogg'},
                'KlimaLogg': {
                    'transceiver_frequency': 'EU',
                    'model': 'TFA KlimaLogg', 
                    'driver': 'user.kl',
                    'sensor_map': {
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
                        'Humidity8': 'soilMoist4'
                        }
                    }
                },
            files=[('bin/user', ['bin/user/kl.py'])
                   ]
            )
