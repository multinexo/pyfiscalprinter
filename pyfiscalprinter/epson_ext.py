# -*- coding: iso-8859-1 -*-
import logging
import string
import types
import unicodedata

import driver
from epson_ext_driver import EpsonFiscalExtDriver
from generic import PrinterInterface, PrinterException
from math import ceil
from math import floor
from command_repository import CommandRepository

class FiscalPrinterError(Exception):
    pass


class FileDriver:

    def __init__(self, filename):
        self.filename = filename
        self.file = open(filename, "w")

    def sendCommand(self, command, parameters):
        self.file.write("Command: %d, Parameters: %s\n" % (command, parameters))
        return ["BLA", "BLA", "BLA", "BLA", "BLA", "BLA", "BLA", "BLA", ]

    def close(self):
        self.file.close()


def formatText(text):
    asciiText = unicodedata.normalize('NFKD', unicode(text)).encode('ASCII', 'ignore')
    asciiText = asciiText.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return asciiText


class DummyDriver:

    def __init__(self):
        try:
            self.number = int(raw_input("Ingrese el número de la última factura: "))
        except EOFError:
            # iniciar desde 0 (ejecutando sin stdin)
            self.number = 0

    def close(self):
        pass

    def sendCommand(self, commandNumber, parameters, skipStatusErrors):

        return ["00", "00", "", "", str(self.number), "", str(self.number)] + [str(self.number)] * 11


class EpsonExtPrinter(PrinterInterface):
    DEBUG = True

    command_repository = CommandRepository()
    commands = {}

    models = ["tickeadoras", "epsonlx300+", "tm-220-af"]

    def __init__(self, deviceFile=None, speed=9600, host=None, port=None, dummy=False, model=None):
        try:
            if dummy:
                self.driver = DummyDriver()
            elif host:
                self.driver = driver.EpsonFiscalDriverProxy(host, port)
            else:
                deviceFile = deviceFile or 0
                # self.driver = driver.EpsonFiscalDriver(deviceFile, speed)
                self.driver = EpsonFiscalExtDriver(deviceFile, speed)
                self.commands = self.command_repository.getCmd("epson_ext")
        except Exception as e:
            raise FiscalPrinterError("Imposible establecer comunicación.", e)
        if not model:
            self.model = "tickeadoras"
        else:
            self.model = model
        self.model = 'tm-t900fa'
        self._currentDocument = None
        self._currentDocumentType = None

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        return self.driver.sendCommand(commandNumber, parameters, skipStatusErrors)

    def openNonFiscalReceipt(self):
        status = self._sendCommand(self.commands['CMD_OPEN_NON_FISCAL_RECEIPT'], [])
        self._currentDocument = self.commands['CURRENT_DOC_NON_FISCAL']
        self._currentDocumentType = None
        return status

    def printNonFiscalText(self, text):
        return self._sendCommand(self.commands['CMD_PRINT_NON_FISCAL_TEXT'], [formatText(text[:40] or " ")])

    ivaTypeMap = {
        PrinterInterface.IVA_TYPE_RESPONSABLE_INSCRIPTO: 'I',
        PrinterInterface.IVA_TYPE_RESPONSABLE_NO_INSCRIPTO: 'R',
        PrinterInterface.IVA_TYPE_EXENTO: 'E',
        PrinterInterface.IVA_TYPE_NO_RESPONSABLE: 'N',
        PrinterInterface.IVA_TYPE_CONSUMIDOR_FINAL: 'F',
        PrinterInterface.IVA_TYPE_RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO: 'R',
        PrinterInterface.IVA_TYPE_RESPONSABLE_MONOTRIBUTO: 'M',
        PrinterInterface.IVA_TYPE_MONOTRIBUTISTA_SOCIAL: 'M',
        PrinterInterface.IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL: 'F',
        PrinterInterface.IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL: 'F',
        PrinterInterface.IVA_TYPE_NO_CATEGORIZADO: 'F',
    }

    ADDRESS_SIZE = 30
    USAR_IMPUESTOS_INTERNOS = False

    def _setHeaderTrailer(self, line, text):
        self._sendCommand(self.commands['CMD_SET_HEADER_TRAILER'], (str(line), text))

    def setHeader(self, header=None):
        "Establecer encabezados"
        if not header:
            header = []
        line = 3
        for text in (header + [chr(0x7f)]*3)[:3]: # Agrego chr(0x7f) (DEL) al final para limpiar las
                                                  # líneas no utilizadas
            self._setHeaderTrailer(line, text)
            line += 1

    def setTrailer(self, trailer=None):
        "Establecer pie"
        if not trailer:
            trailer = []
        line = 11
        for text in (trailer + [chr(0x7f)] * 9)[:9]:
            self._setHeaderTrailer(line, text)
            line += 1

    # UPDATE: La línea comentada está como la teníamos antes de actualizar
    # def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference="NC"):
    def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference=""):
        return self._openBillCreditTicket(type, name, address, doc, docType, ivaType, isCreditNote=True, reference=reference)

    def openBillTicket(self, type, name, address, doc, docType, ivaType):
        return self._openBillCreditTicket(type, name, address, doc, docType, ivaType, isCreditNote=False)

    def _openBillCreditTicket(self, type, name, address, doc, docType, ivaType, isCreditNote,
            reference=None):
        self._type = type

        parameters = [
            formatText(name[:40]),
            formatText(name[40:80]),
            formatText(address),  # Domicilio
            formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]),  # Domicilio 2da linea
            formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]),
            self.docTypeNamesEpsonExt[docType],
            doc,
            self.ivaTypeMap.get(ivaType, "F"),
            "",
            "",
            "",
            ""
        ]

        if isCreditNote:
            self._currentDocument = self.commands['CURRENT_DOC_CREDIT_TICKET']
        else:
            self._currentDocument = self.commands['CURRENT_DOC_BILL_TICKET']

        # guardo el tipo de FC (A/B/C)
        self._currentDocumentType = type
        return self._sendCommand(self.commands['CMD_OPEN_BILL_TICKET'][self._getCommandIndex()], parameters)

    def _getCommandIndex(self):
        if self._currentDocument == self.commands['CURRENT_DOC_BILL_TICKET']:
            return 0
        elif self._currentDocument  == self.commands['CURRENT_DOC_CREDIT_TICKET']:
            return 1

    def openTicket(self, defaultLetter='B'):
        self._sendCommand(self.commands['CMD_OPEN_FISCAL_RECEIPT'], [])
        self._currentDocument = self.commands['CURRENT_DOC_TICKET']

    def openDrawer(self):
        self._sendCommand(self.commands['CMD_OPEN_DRAWER'], [])

    def closeDocument(self):
        if self._currentDocument == self.commands['CURRENT_DOC_BILL_TICKET']:
            parameters = [
                "",
                "",
                "",
                "",
                "",
                "",
            ]
            reply = self._sendCommand(self.commands['CMD_CLOSE_FISCAL_RECEIPT'][self._getCommandIndex()], parameters)
            return reply[2]
        if self._currentDocument == self.commands['CURRENT_DOC_CREDIT_TICKET']:
            parameters = [
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
            reply = self._sendCommand(self.commands['CMD_CLOSE_FISCAL_RECEIPT'][self._getCommandIndex()], parameters)
            return reply[2]

    def cancelDocument(self):
        if self._currentDocument in (self.commands.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.commands.CMD_ADD_PAYMENT[self._getCommandIndex()], ["Cancelar", "0", 'C'])
            return status
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL, ):
            self.printNonFiscalText("CANCELADO")
            return self.closeDocument()
        raise NotImplementedError

    def addItem(self, description, quantity, price, iva, discount, discountDescription, negative=False,
                long_description=False, round_up=False):
        quantityStr = str(int(quantity * 10000))
        ivaStr = str(int(iva * 100))
        codigo_frente_iva = "7"
        if self._currentDocumentType != 'A':
            ivaStr = '0000'
            codigo_frente_iva = "1"
            # enviar con el iva incluido
            if self._currentDocument == self.commands['CURRENT_DOC_CREDIT_TICKET']:
                # nota de crédito?
                priceUnitStr = str(int(floor(price * 10000)))
            else:
                priceUnitStr = str(int(round(price * 10000, 0)))
        else:
            net = price / ((100.0 + iva) / 100.0)
            if round_up:
                net = self.float_round_up(net, 2)
            # enviar sin el iva (factura A)
            if self._currentDocument == self.commands['CURRENT_DOC_CREDIT_TICKET']:
                # nota de crédito?
                priceUnitStr = str(int(floor(net * 10000)))
            else:
                priceUnitStr = str(int(round(net * 10000, 0)))

        parameters = [
            "",
            "",
            "",
            "",
            description,
            quantityStr,
            priceUnitStr,
            ivaStr,
            "",
            "",
            "",
            "0001",
            "",
            "0",
            codigo_frente_iva,
        ]

        reply = self._sendCommand(self.commands['CMD_PRINT_LINE_ITEM'][self._getCommandIndex()], parameters)
        if discount:
            discountStr = str(int(discount * 10000))
            parameters = [
                "",
                "",
                "",
                "",
                formatText(discountDescription[:20]),
                "10000",
                discountStr,
                ivaStr,
                "",
                "",
                "",
                "0001",
                "",
                "0",
                codigo_frente_iva,
            ]
            self._sendCommand(self.commands['CMD_PRINT_DISCOUNT'][self._getCommandIndex()], parameters)
        return reply

    def addPayment(self, description, payment):
        paymentStr = str(int(payment * 10000))
        parameters = [
            formatText(description)[:20],
            "",
            "",
            "",
            "",
            "1",
            paymentStr
        ]
        status = self._sendCommand(self.commands['CMD_ADD_PAYMENT'][self._getCommandIndex()], parameters)
        return status

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un adicional a la FC.
            @param description  Descripción
            @param amount       Importe (sin iva en FC A, sino con IVA)
            @param iva          Porcentaje de Iva
            @param negative True->Descuento, False->Recargo"""
        quantityStr = "10000"
        priceUnit = amount
        ivaStr = str(int(iva * 100))
        codigo_frente_iva = "7"
        command = self.commands['CMD_PRINT_LINE_ITEM'][self._getCommandIndex()]

        if negative:
            command = self.commands['CMD_PRINT_DISCOUNT']

        if self._currentDocumentType != 'A':
            ivaStr = '0000'
            codigo_frente_iva = "1"
            # enviar con el iva incluido
            if self._currentDocument == self.commands['CURRENT_DOC_CREDIT_TICKET']:
                priceUnitStr = str(int(ceil(priceUnit * 10000)))
            else:
                priceUnitStr = str(int(round(priceUnit * 10000, 0)))
        else:
            # enviar sin el iva (factura A)
            if self._currentDocument == self.commands['CURRENT_DOC_CREDIT_TICKET']:
                priceUnitStr = str(int(ceil((priceUnit / ((100.0 + iva) / 100)) * 10000)))
            else:
                priceUnitStr = str(int(round((priceUnit / ((100.0 + iva) / 100)) * 10000, 0)))

        parameters = [
            "",
            "",
            "",
            "",
            description,
            quantityStr,
            priceUnitStr,
            ivaStr,
            "",
            "",
            "",
            "0001",
            "",
            "0",
            codigo_frente_iva,
        ]

        return self._sendCommand(command, parameters)

    def addTax(self, tax_id, description, amount, rate=None):
        """Agrega un otros tributos (i.e. percepción) a la FC.
            @param description  Descripción
            @param amount       Importe
            @param iva          Porcentaje de Iva (si corresponde)
            @param tax_id       Código de Impuesto (ver 2da Generación)
        """
        if tax_id in (5, 7, 8, 9):
            perception = 'O'        # 0x4F  Otro tipo de Percepción (cod 9)
        elif tax_id in (6, ):
            if rate and self.model == "epsonlx300+":
                perception = 'T'    # 0x54  Percepción de IVA a una tasa de IVA (cod 6)
            else:
                perception = 'I'    # 0x49  Percepción Global de IVA
        else:
            raise NotImplementedError("El código de impuesto no está implementado")

        amountStr = str(int(round(amount * 100, 0)))
        ivaStr = str(int(rate * 100)) if rate is not None else ""
        if perception == 'T' and self.model == "epsonlx300+":
            params = [ivaStr, amountStr]
        else:
            # En tiqueteadors (TMU220AF) no se envia tasa:
            params = [amountStr]
        reply = self._sendCommand(self.commands.CMD_ADD_PERCEPTION,
                          [formatText(description[:20]), perception] + params)
        return reply

    def subtotal(self, print_text=True, display=False, text="Subtotal"):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.commands.CURRENT_DOC_BILL_TICKET,
                self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.commands.CMD_PRINT_SUBTOTAL[self._getCommandIndex()], ["P" if print_text else "O", text])
            return status
        raise NotImplementedError

    def getStatus(self,status, printer):
        reply = self._sendCommand('020A|0000', [])
        response = [
            reply[1],
            reply[0],
            "0",
            "0",
            "0",
            "0",
        ]
        return status(response, printer)

    def dailyClose(self, type):
        tique_a = self._sendCommand('080A|0000', ["82"])
        tique = self._sendCommand('080A|0000', ["83"])
        tique_b = self._sendCommand('080A|0000', ["81"])
        nota_credito_a = self._sendCommand('080A|0000', ["112"])
        nota_credito_b = self._sendCommand('080A|0000', ["113"])
        nota_credito_c = self._sendCommand('080A|0000', ["114"])
        if type == 'Z':
            reply = self._sendCommand(self.commands['CMD_DAILY_CLOSE'], [])
        if type == 'X':
            reply = self._sendCommand(self.commands['CMD_TELLER_EXIT'], [])

        try:
            receipt_number = reply[2]
        except Exception as e:
            receipt_number = "null"

        if receipt_number == "null":
            response = []
        else:
            receipt_number = reply[2]
            response = [
                str(receipt_number).zfill(8),
                int(tique_a[9]) + int(tique[9]) + int(tique_b[9]) + int(nota_credito_a[9]) + int(
                    nota_credito_b[9]) + int(nota_credito_c[9]),
                tique[8],
                "0",
                tique_a[8],
                tique_b[8],
                "0",
                float(tique_a[10]) + float(tique_b[10]),
                float(tique_a[11]) + float(tique_b[11]),
                "0",
                "0",
                "0",
                "0",
                int(nota_credito_a[8]) + int(nota_credito_b[8]) + int(nota_credito_c[8]),
                float(nota_credito_a[10]) + float(nota_credito_b[10]) + float(nota_credito_c[10]),
                float(nota_credito_a[11]) + float(nota_credito_b[11]) + float(nota_credito_c[11]),
            ]

        return response

    def auditByDate(self, date_from, date_to, type):
        reply = self._sendCommand(self.commands.CMD_AUDIT_BY_DATE, [date_from, date_to, type])
        return reply[2:]

    def auditByClosure(self, close_from, close_to, type):
        reply = self._sendCommand(self.commands['CMD_AUDIT_BY_CLOSURE'], [close_from, close_to])
        return reply[2:]

    def getLastNumber(self, letter):
        reply = self._sendCommand(self.commands.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
            # La respuesta no es válida. Vuelvo a hacer el pedido y si hay
            # algún error que se reporte como excepción
            reply = self._sendCommand(self.commands.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[6])
        else:
            return int(reply[4])

    def getLastCreditNoteNumber(self, letter):
        reply = self._sendCommand(self.commands.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
            # La respuesta no es válida. Vuelvo a hacer el pedido y si hay algún
            # error que se reporte como excepción
            reply = self._sendCommand(self.commands.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[10])
        else:
            return int(reply[11])

    def cancelAnyDocument(self):

        try:
            self._sendCommand(self.commands['CMD_CANCEL_DOCUMENT'][self._getCommandIndex()], [])
            return True
        except:
            pass
        return False

    def getSubtotal(self, print_subtotal=True):
        """
        01  Estado del impresor fiscal
        02  Estado del controlador fiscal
        03  Sin uso
        04  cantidad de items de línea
        05  Total de mercadería o total a pagar (nnnnn.nn)
        06  Total de impuesto IVA (nnnnnnnnnn.nn)
        07  Total pago (nnnnnnnnnn.nn)
        08  Total de Impuestos Internos Porcentuales (nnnnnnnnnn.nn)
        09  Total de Impuestos Internos Fijos (nnnnnnnnnn.nn)
        10  Monto Neto o Total facturado sin Impuestos (nnnnnnnnnn.nn)
        """
        reply = self._sendCommand(self.commands['CMD_PRINT_SUBTOTAL'][self._getCommandIndex()], [])
        return reply[2:]  # datos útiles

    def getWarnings(self):
        ret = []
        reply = self._sendCommand(self.commands.CMD_STATUS_REQUEST, ["N"], True)
        printerStatus = reply[0]
        x = int(printerStatus, 16)
        if ((1 << 4) & x) == (1 << 4):
            ret.append("Poco papel para la cinta de auditoría")
        if ((1 << 5) & x) == (1 << 5):
            ret.append("Poco papel para comprobantes o tickets")
        return ret

    def __del__(self):
        try:
            self.close()
        except:
            pass

    def close(self):
        self.driver.close()
        self.driver = None

    def truncate_description(self, product_name):
        """
        Divide la descripción en array de n strings
        """
        text = formatText(product_name[:78])
        n = 26
        description = [text[i:i+n] for i in range(0, len(text), n)]

        return description

    def get_extraparameters(self, description):
        """
        Prepara el array de parámetros extras
        """

        extraparamenters = ['', '', '']

        for d in description:
            extraparamenters.append(d)
            extraparamenters = extraparamenters[1:]

        return extraparamenters

    def float_round_up(self, num, places = 0):
        return ceil(num * (10**places)) / float(10**places)
