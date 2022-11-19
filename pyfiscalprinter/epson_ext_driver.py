# -*- coding: utf-8 -*-
from driver import EpsonFiscalDriver, FiscalStatusError
import requests
import time
import os

class EpsonFiscalExtDriver(EpsonFiscalDriver):

    def __init__(self, deviceFile, speed=9600):
        connect = True
	print('(EpsonExt) Entre por lo tanto me toma lo que estoy haciendo')
        while connect:
            try:
                os.system("./fiscalproxy --comm-port=1 -p 3000 -l &")
                connect = False
            except Exception as e:
                print("Connection refused by the server..", e)
                time.sleep(5)
                continue

    def _parseReply( self, reply, skipStatusErrors ):
        fields = reply.split('|')
        printerStatus = fields[1]
        fiscalStatus = fields[2]
        #if not skipStatusErrors:
            #self._parsePrinterStatus( printerStatus )
            #self._parseFiscalStatus( fiscalStatus )
        return fields[1:]

    def sendCommand( self, commandNumber, fields, skipStatusErrors = False ):
        message = commandNumber
        for field in fields:
            message = message + '|' + field

        url = 'http://localhost:3000'
        headers = {'Content-Type': 'text/plain'}
	print('Comando: ', message)
        ret = ''
        while ret == '':
            try:
                ret = requests.post(url, message, headers)
                break
            except requests.ConnectionError as e:
                print("Connection refused by the server..", e)
                time.sleep(5)
                print("Was a nice sleep, now let me continue...")
                continue
	print('Respuesta: ', ret.content)
        return self._parseReply( ret.content, skipStatusErrors )

