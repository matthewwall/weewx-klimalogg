# $Id: install.py 1175 2014-12-07 15:34:39Z mwall $
# installer for klimalogg
# Copyright 2015 Luc Heijst

from setup import ExtensionInstaller

def loader():
    return KlimaLoggInstaller()

class KlimaLoggInstaller(ExtensionInstaller):
    def __init__(self):
        super(KlimaLoggInstaller, self).__init__(
            version="1.1.2",
            name='klimalogg',
            description='Collect and display KlimaLogg Pro sensor data with kl skin',
            author="Luc Heijst",
            author_email="ljm.heijst@gmail.com",
            config={
                'StdArchive': {
                    'data_binding': 'kl_binding'},
                'StdReport': {
                    'data_binding': 'kl_binding',
                    'Klimalogg': {
                        'skin': 'kl',
                        'HTML_ROOT': 'kl'}},
                'DataBindings': {
                    'kl_binding': {
                        'database': 'kl_archive_sqlite',
                        'table_name': 'archive',
                        'manager': 'weewx.wxmanager.WXDaySummaryManager',
                        'schema': 'user.kl.schema'}},
                'Databases': {
                    'kl_archive_sqlite': {
                        'database_name': 'kl.sdb',
                        'database_type': 'SQLite'}}},
            files=[('bin/user',
                    ['bin/user/kl.py']),
                   ('skins/kl',
                    ['skins/kl/skin.conf',
                     'skins/kl/index.html.tmpl']),
                   ]
            )
