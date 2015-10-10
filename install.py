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
                'StdReport': {
                    'Klimalogg': {
                        'skin': 'kl',
                        'HTML_ROOT': 'kl'}},
                'DataBindings': {
                    'REPLACE-wx_binding': {
                        'database': 'archive_sqlite',
                        'table_name': 'archive',
                        'schema': 'user.kl.schema'}}},
            files=[('bin/user',
                    ['bin/user/kl.py']),
                   ('skins/kl',
                    ['skins/kl/skin.conf',
                     'skins/kl/index.html.tmpl']),
                   ]
            )
