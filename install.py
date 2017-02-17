# installer for klimalogg
# Copyright 2015 Luc Heijst

from setup import ExtensionInstaller

def loader():
    return KlimaLoggInstaller()

class KlimaLoggInstaller(ExtensionInstaller):
    def __init__(self):
        super(KlimaLoggInstaller, self).__init__(
            version="1.3.1",
            name='klimalogg',
            description='Collect and display KlimaLogg Pro sensor data',
            author="Luc Heijst",
            author_email="ljm.heijst@gmail.com",
            config={
                'StdReport': {
                    'data_binding': 'kl_binding',
                    'kl': {
                        'HTML_ROOT': 'kl',
                        'skin': 'kl'}},
                'StdArchive': {
                    'data_binding': 'kl_binding'},
                'DataBindings': {
                    'kl_binding': {
                        'manager': 'weewx.wxmanager.WXDaySummaryManager',
                        'schema': 'user.kl.schema',
                        'table_name': 'archive',
                        'database': 'kl_sqlite'}},
                'Databases': {
                    'kl_sqlite': {
                        'database_name': 'weewx-kl.sdb',
                        'database_type': 'SQLite'},
                    'kl_mysql': {
                        'database_name': 'weewx-kl',
                        'database_type': 'MySQL'}}},
            files=[('bin/user',
                    ['bin/user/kl.py']),
                   ('skins/kl',
                    ['skins/kl/skin.conf',
                     'skins/kl/index.html.tmpl']),
                   ]
            )
