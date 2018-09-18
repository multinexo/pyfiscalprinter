# -*- coding: iso-8859-1 -*-
import serial
import random
import time
import sys
import SocketServer
import socket
import traceback

def debugEnabled( *args ):
    print >>sys.stderr, " ".join( map(str, args) )

def debugDisabled( *args ):
    pass

debug = debugDisabled

class PrinterException(Exception):
    pass

class UnknownServerError(PrinterException):
    errorNumber = 1

class ComunicationError(PrinterException):
    errorNumber = 2

class PrinterStatusError(PrinterException):
    errorNumber = 3

class FiscalStatusError(PrinterException):
    errorNumber = 4

ServerErrors = [UnknownServerError, ComunicationError, PrinterStatusError, FiscalStatusError]

class ProxyError(PrinterException):
    errorNumber = 5

class EpsonFiscalDriver:
    WAIT_TIME = 10
    RETRIES = 4
    WAIT_CHAR_TIME = 0.1
    NO_REPLY_TRIES = 200

    fiscalStatusErrors = [#(1<<0 + 1<<7, "Memoria Fiscal llena"),
                          (1<<0, "Error en memoria fiscal"),
                          (1<<1, "Error de comprobación en memoria de trabajo"),
                          (1<<2, "Poca batería"),
                          (1<<3, "Comando no reconocido"),
                          (1<<4, "Campo de datos no válido"),
                          (1<<5, "Comando no válido para el estado fiscal"),
                          (1<<6, "Desbordamiento de totales"),
                          (1<<7, "Memoria Fiscal llena"),
                          (1<<8, "Memoria Fiscal casi llena"),
                          (1<<11, "Es necesario hacer un cierre de la jornada fiscal o se superó la cantidad máxima de tickets en una factura."),
                          ]

    printerStatusErrors = [(1<<2, "Error y/o falla de la impresora"),
                          (1<<3, "Impresora fuera de linea"),
##                          (1<<4, "Poco papel para la cinta de auditoría"),
##                          (1<<5, "Poco papel para comprobantes o tickets"),
                          (1<<6, "Buffer de impresora lleno"),
                          (1<<14, "Impresora sin papel"),
                          ]

    def __init__( self, deviceFile, speed = 9600 ):
        self._serialPort = serial.Serial( port = deviceFile, timeout = None, baudrate = speed )
        self._initSequenceNumber()

    def _initSequenceNumber( self ):
        self._sequenceNumber = random.randint( 0x20, 0x7f )

    def _incrementSequenceNumber( self ):
        # Avanzo el número de sequencia, volviendolo a 0x20 si pasó el limite
        self._sequenceNumber += 1
        if self._sequenceNumber > 0x7f:
            self._sequenceNumber = 0x20

    def _write( self, s ):
        if isinstance(s, unicode):
            s = s.encode("latin1")
        debug( "_write", ", ".join( [ "%x" % ord(c) for c in s ] ) )
        self._serialPort.write( s )

    def _read( self, count ):
        ret = self._serialPort.read( count )
        debug( "_read", ", ".join( [ "%x" % ord(c) for c in ret ] ) )
        return ret

    def __del__( self ):
        if hasattr(self, "_serialPort" ):
            try:
                self.close()
            except:
                pass

    def close( self ):
        try:
            self._serialPort.close()
        except:
            pass
        del self._serialPort

    def sendCommand( self, commandNumber, fields, skipStatusErrors = False ):
        message = chr(0x02) + chr( self._sequenceNumber ) + chr(commandNumber)
        if fields:
            message += chr(0x1c)
        message += chr(0x1c).join( fields )
        message += chr(0x03)
        checkSum = sum( [ord(x) for x in message ] )
        checkSumHexa = ("0000" + hex(checkSum)[2:])[-4:].upper()
        message += checkSumHexa
        reply = self._sendMessage( message )
        self._incrementSequenceNumber()
        return self._parseReply( reply, skipStatusErrors )

    def _parseReply( self, reply, skipStatusErrors ):
        r = reply[4:-1] # Saco STX <Nro Seq> <Nro Comando> <Sep> ... ETX
        fields = r.split( chr(28) )
        printerStatus = fields[0]
        fiscalStatus = fields[1]
        if not skipStatusErrors:
            self._parsePrinterStatus( printerStatus )
            self._parseFiscalStatus( fiscalStatus )
        return fields

    def _parsePrinterStatus( self, printerStatus ):
        x = int( printerStatus, 16 )
        for value, message in self.printerStatusErrors:
            if (value & x) == value:
                raise PrinterStatusError, message

    def _parseFiscalStatus( self, fiscalStatus ):
        x = int( fiscalStatus, 16 )
        for value, message in self.fiscalStatusErrors:
            if (value & x) == value:
                raise FiscalStatusError, message

    def _sendMessage( self, message ):
        # Envía el mensaje
        # @return reply Respuesta (sin el checksum)
        self._write( message )
        timeout = time.time() + self.WAIT_TIME
        retries = 0
        while 1:
            if time.time() > timeout:
                raise ComunicationError, "Expiró el tiempo de espera para una respuesta de la impresora. Revise la conexión."
            c = self._read(1)
            if len(c) == 0:
                continue
            if ord(c) in (0x12, 0x14): # DC2 o DC4
                # incrementar timeout
                timeout += self.WAIT_TIME
                continue
            if ord(c) == 0x15: # NAK
                if retries > self.RETRIES:
                    raise ComunicationError, "Falló el envío del comando a la impresora luego de varios reintentos"
                # Reenvío el mensaje
                self._write( message )
                timeout = time.time() + self.WAIT_TIME
                retries +=1
                continue
            if c == chr(0x02):# STX - Comienzo de la respuesta
                reply = c
                noreplyCounter = 0
                while c != chr(0x03): # ETX (Fin de texto)
                    c = self._read(1)
                    if not c:
                        noreplyCounter += 1
                        time.sleep(self.WAIT_CHAR_TIME)
                        if noreplyCounter > self.NO_REPLY_TRIES:
                            raise ComunicationError, "Fallo de comunicación mientras se recibía la respuesta de la impresora."
                    else:
                        noreplyCounter = 0
                        reply += c
                bcc = self._read(4) # Leo BCC
                if not self._checkReplyBCC( reply, bcc ):
                    # Mando un NAK y espero la respuesta de nuevo.
                    self._write( chr(0x15) )
                    timeout = time.time() + self.WAIT_TIME
                    retries += 1
                    if retries > self.RETRIES:
                        raise ComunicationError, "Fallo de comunicación, demasiados paquetes inválidos (bad bcc)."
                    continue
                elif reply[1] != chr( self._sequenceNumber ): # Los número de seq no coinciden
                    # Reenvío el mensaje
                    self._write( message )
                    timeout = time.time() + self.WAIT_TIME
                    retries +=1
                    if retries > self.RETRIES:
                        raise ComunicationError, "Fallo de comunicación, demasiados paquetes inválidos (mal sequence_number)."
                    continue
                else:
                    # Respuesta OK
                    break
        return reply

    def _checkReplyBCC( self, reply, bcc ):
        debug( "reply", reply, [ord(x) for x in reply] )
        checkSum = sum( [ord(x) for x in reply ] )
        debug( "checkSum", checkSum )
        checkSumHexa = ("0000" + hex(checkSum)[2:])[-4:].upper()
        debug( "checkSumHexa", checkSumHexa )
        debug( "bcc", bcc )
        return checkSumHexa == bcc.upper()

class HasarFiscalDriver( EpsonFiscalDriver ):
    fiscalStatusErrors = [(1<<0 + 1<<7, "Memoria Fiscal llena"),
                          (1<<0, "Error en memoria fiscal"),
                          (1<<1, "Error de comprobación en memoria de trabajo"),
                          (1<<2, "Poca batería"),
                          (1<<3, "Comando no reconocido"),
                          (1<<4, "Campo de datos no válido"),
                          (1<<5, "Comando no válido para el estado fiscal"),
                          (1<<6, "Desbordamiento de totales"),
                          (1<<7, "Memoria Fiscal llena"),
                          (1<<8, "Memoria Fiscal casi llena"),
                          (1<<11, "Es necesario hacer un cierre de la jornada fiscal o se superó la cantidad máxima de tickets en una factura."),
                          ]

    printerStatusErrors = [(1<<2, "Error y/o falla de la impresora"),
                          (1<<3, "Impresora fuera de linea"),
##                          (1<<4, "Poco papel para la cinta de auditoría"),
##                          (1<<5, "Poco papel para comprobantes o tickets"),
                          (1<<6, "Buffer de impresora lleno"),
                          (1<<8, "Tapa de impresora abierta"),
                          ]

    ACK = chr(0x06)
    NAK = chr(0x15)
    STATPRN = chr(0xa1)

    def _initSequenceNumber( self ):
        self._sequenceNumber = random.randint( 0x20, 0x7f )
        if self._sequenceNumber % 2:
            self._sequenceNumber -= 1

    def _incrementSequenceNumber( self ):
        # Avanzo el número de sequencia, volviendolo a 0x20 si pasó el limite
        self._sequenceNumber += 2
        if self._sequenceNumber > 0x7f:
            self._sequenceNumber = 0x20

    def _sendAndWaitAck( self, message, count = 0 ):
        if count > 10:
            raise ComunicationError, "Demasiados NAK desde la impresora. Revise la conexión."
        self._write( message )
        timeout = time.time() + self.WAIT_TIME
        while 1:
            if time.time() > timeout:
                raise ComunicationError, "Expiró el tiempo de espera para una respuesta de la impresora. Revise la conexión."
            c = self._read(1)
            if len(c) == 0:
                continue
            if c == self.ACK:
                return True
            if c == self.NAK:
                return self._sendAndWaitAck( message, count + 1 )

    def _sendMessage( self, message ):
        # Envía el mensaje
        # @return reply Respuesta (sin el checksum)
        self._sendAndWaitAck( message )
        timeout = time.time() + self.WAIT_TIME
        retries = 0
        while 1:
            if time.time() > timeout:
                raise ComunicationError, "Expiró el tiempo de espera para una respuesta de la impresora. Revise la conexión."
            c = self._read(1)
            if len(c) == 0:
                continue
            if ord(c) in (0x12, 0x14): # DC2 o DC4
                # incrementar timeout
                timeout += self.WAIT_TIME
                continue
##            if ord(c) == self.NAK: # NAK
##                if retries > self.RETRIES:
##                    raise ComunicationError, "Falló el envío del comando a la impresora luego de varios reintentos"
##                # Reenvío el mensaje
##                self._write( message )
##                timeout = time.time() + self.WAIT_TIME
##                retries +=1
##                continue
            if c == chr(0x02):# STX - Comienzo de la respuesta
                reply = c
                noreplyCounter = 0
                while c != chr(0x03): # ETX (Fin de texto)
                    c = self._read(1)
                    if not c:
                        noreplyCounter += 1
                        time.sleep(self.WAIT_CHAR_TIME)
                        if noreplyCounter > self.NO_REPLY_TRIES:
                            raise ComunicationError, "Fallo de comunicación mientras se recibía la respuesta de la impresora."
                    else:
                        noreplyCounter = 0
                        reply += c
                bcc = self._read(4) # Leo BCC
                if not self._checkReplyBCC( reply, bcc ):
                    # Mando un NAK y espero la respuesta de nuevo.
                    self._write( self.NAK )
                    timeout = time.time() + self.WAIT_TIME
                    retries += 1
                    if retries > self.RETRIES:
                        raise ComunicationError, "Fallo de comunicación, demasiados paquetes inválidos (bad bcc)."
                    continue
                elif reply[1] != chr( self._sequenceNumber ): # Los número de seq no coinciden
                    # Reenvío el mensaje
                    self._write( self.ACK )
                    self._sendAndWaitAck( message )
                    timeout = time.time() + self.WAIT_TIME
                    retries +=1
                    if retries > self.RETRIES:
                        raise ComunicationError, "Fallo de comunicación, demasiados paquetes inválidos (bad sequenceNumber)."
                    continue
                else:
                    # Respuesta OK
                    self._write( self.ACK )
                    break
        return reply

class DummyDriver:
    def close(self):
        pass

    def sendCommand(self, commandNumber, parameters, skipStatusErrors):
        print commandNumber, parameters, skipStatusErrors
        number = random.randint(0, 99999999)
        return ["00", "00"] + [str(number)] * 11

class EpsonFiscalDriverProxy:
    def __init__( self, host, port, timeout = 60.0, connectOnEveryCommand = False ):
        self.connectOnEveryCommand = connectOnEveryCommand
        self.timeout = timeout
        self.host = host
        self.port = port
        if not connectOnEveryCommand:
            self._connect()

    def _connect(self):
        self.socket = socket.socket()
        self.socket.settimeout( self.timeout )
        try:
            self.socket.connect( (self.host, self.port ) )
        except socket.error, e:
            raise ProxyError( "Error conectandose a la impresora remota: %s." % str(e) )
        self.socketFile = self.socket.makefile( "rw", 1 )

    def sendCommand( self, commandNumber, fields, skipStatusErrors = False ):
        if self.connectOnEveryCommand:
            self._connect()
            try:
                ret = self._sendCommand(commandNumber, fields, skipStatusErrors)
            finally:
                self.close()
        else:
            ret = self._sendCommand(commandNumber, fields, skipStatusErrors)
        return ret

    def _sendCommand( self, commandNumber, fields, skipStatusErrors = False ):
        commandStr = "0x" + ("00" + hex(commandNumber)[2:])[-2:].upper()
        self.socketFile.write( "SEND|%s|%s|%s\n" % (commandStr, skipStatusErrors and "T" or "F",
                                              fields) )
        reply = self.socketFile.readline()
        if reply[:5] == "REPLY":
            return eval( reply[7:] )
        elif reply[:5] == "ERROR":
            errorNum = int(reply[7:9])
            errorClass = filter( lambda x: x.errorNumber == errorNum, ServerErrors )
            if errorClass:
                raise errorClass[0]( reply[10:] )
            else:
                raise ProxyError( "Código de error desconocido: %s." % reply[7:] )
        else:
            raise ProxyError( "Respuesta no válida del servidor: %s." % reply )

    def close( self ):
        try:
            self.socket.close()
            del self.socket
        except:
            pass

    def __del__( self ):
        self.close()


def runServer( printerType, fileIn, fileOut, deviceFile, speed = 9600 ):
    if printerType == "Epson":
        p = EpsonFiscalDriver( deviceFile, speed )
    elif printerType == "Dummy":
        p = DummyDriver()
    else:
        p = HasarFiscalDriver( deviceFile, speed )
#    p = EpsonFiscalDriverProxy( 'localhost', 12345 )
    while 1:
        commandLine = fileIn.readline()
        if not commandLine:
            break
        # Formato de comandos:
        #  SEND|0x42|F|["asdasd", "sdfs", "sdfsd"]
        #  012345678901234567890....
        send = commandLine[0:4]
        if send != "SEND":
            continue
        commandNumber = int(commandLine[5:9][2:], 16)
        skipStatusErrors = commandLine[10:11]
        skipStatusErrors = skipStatusErrors == "T" and True or False
        parameters = eval(commandLine[12:].strip())
        try:
            reply = p.sendCommand( commandNumber, parameters, skipStatusErrors )
        except PrinterException, e:
            fileOut.write( "ERROR: %02d %s\n" % (e.errorNumber, str(e)) )
        except Exception, e:
            fileOut.write( "ERROR: %02d %s\n" % (1, str(e)) )
        else:
            fileOut.write( "REPLY: %s\n" % reply )
        fileOut.flush()
    p.close()

class ReusableTCPServer(SocketServer.TCPServer):
    def server_bind(self):
        """Override server_bind to set socket options."""
        self.socket.setsockopt(socket.SOL_SOCKET,
            socket.SO_REUSEADDR, 1)
        return SocketServer.TCPServer.server_bind(self)


def socketServer(printerType, host, port, deviceFile, speed, timeout = 60, returnServer=False):
    class Handler( SocketServer.StreamRequestHandler ):
        rbufsize = 1
        wbufsize = 1
        def handle( self ):
            #self.connection.settimeout( timeout )
            return runServer( printerType, self.rfile, self.wfile, deviceFile, speed )

    server = ReusableTCPServer( (host, port), Handler )
    if returnServer:
    	return server
    server.serve_forever()


if __name__ == "__main__":
    from optparse import OptionParser
    parser = OptionParser( usage = "usage: \n  %prog ..." )

    parser.add_option( "-d", "--deviceFile", action = "store", type = "string",
                       dest = "deviceFile",
                       default = "/dev/ttyS0",
                       help = "Archivo de dispositivo del puerto serie para comunicar con la impresora." )
    parser.add_option( "-D", "--debug", action = "store_true",
                       dest = "debug",
                       default = False,
                       help = "Habilita salida de debug a stderr." )
    parser.add_option( "-s", "--speed", action = "store", type = "string",
                       dest = "speed", default = "9600",
                       help = "Velocidad de transferencia con el puerto serie." )
    parser.add_option( "-p", "--port", action = "store", type = "string",
                       dest = "port", default = None,
                       help = "Puerto donde escucha el server, si no se indica, la comunicación es por la entrada y salida estándar" )
    parser.add_option( "-i", "--ip", action = "store", type = "string",
                       dest = "ip", default = "",
                       help = "IP o Host donde escucha el server, si no se indica, la comunicación es por la entrada y salida estándar" )
    parser.add_option( "-t", "--printertype", action = "store", type = "string",
                       dest = "printerType", default = "Epson",
                       help = "Tipo de impresora. Hasar o Epson o Dummy. Default: Epson" )
    parser.add_option( "-T", "--timeout", action = "store", type = "string",
                       dest = "timeout", default = "60",
                       help = "Tiempo de espera antes de cancelar la conexión (en segundos). Default: 60 segundos" )
    (opts, args) = parser.parse_args()

    if opts.debug:
        debug = debugEnabled
    if opts.port:
        ret = socketServer( opts.printerType, opts.ip, int(opts.port), opts.deviceFile, int(opts.speed), int(opts.timeout) )
    else:
        ret = runServer( opts.printerType, sys.stdin, sys.stdout, opts.deviceFile, int(opts.speed) )
    sys.exit( ret )


# Formato de los comandos para enviar (tanto por socket como por linea de comandos):
# SEND|0x2a|F|["N"]
# Envía el comando 0x2a, El "F" es para skipStatusErrors, y los parámetros del comando: ["N"]
