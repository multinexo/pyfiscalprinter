# -*- coding: iso-8859-1 -*-
import logging
import string
import types
import unicodedata

import driver
from generic import PrinterInterface, PrinterException
from math import ceil
from math import floor


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


class EpsonPrinter(PrinterInterface):
    DEBUG = True

    CMD_OPEN_FISCAL_RECEIPT = 0x40
    CMD_OPEN_BILL_TICKET = 0x60
    # CMD_PRINT_TEXT_IN_FISCAL = (0x41, 0x61)
    CMD_PRINT_TEXT_IN_FISCAL = 0x41
    CMD_PRINT_LINE_ITEM = (0x42, 0x62)
    CMD_ADD_PERCEPTION = 0x66
    CMD_PRINT_SUBTOTAL = (0x43, 0x63)
    CMD_ADD_PAYMENT = (0x44, 0x64)
    CMD_CLOSE_FISCAL_RECEIPT = (0x45, 0x65)
    CMD_DAILY_CLOSE = 0x39
    CMD_STATUS_REQUEST = 0x2a

    CMD_AUDIT_BY_DATE = 0x3A
    CMD_AUDIT_BY_CLOSURE = 0x3B

    CMD_OPEN_DRAWER = 0x7b

    CMD_SET_HEADER_TRAILER = 0x5d

    CMD_OPEN_NON_FISCAL_RECEIPT = 0x48
    CMD_PRINT_NON_FISCAL_TEXT = 0x49
    CMD_CLOSE_NON_FISCAL_RECEIPT = 0x4a

    CURRENT_DOC_TICKET = 1
    CURRENT_DOC_BILL_TICKET = 2
    CURRENT_DOC_CREDIT_TICKET = 4
    CURRENT_DOC_NON_FISCAL = 3

    models = ["tickeadoras", "epsonlx300+", "tm-220-af"]

    def __init__(self, deviceFile=None, speed=9600, host=None, port=None, dummy=False, model=None):
        try:
            if dummy:
                self.driver = DummyDriver()
            elif host:
                self.driver = driver.EpsonFiscalDriverProxy(host, port)
            else:
                deviceFile = deviceFile or 0
                self.driver = driver.EpsonFiscalDriver(deviceFile, speed)
        except Exception as e:
            raise FiscalPrinterError("Imposible establecer comunicación.", e)
        if not model:
            self.model = "tickeadoras"
        else:
            self.model = model
        self._currentDocument = None
        self._currentDocumentType = None

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        print "_sendCommand", commandNumber, parameters
        try:
            logging.getLogger().info("sendCommand: SEND|0x%x|%s|%s" % (commandNumber,
                skipStatusErrors and "T" or "F", str(parameters)))
            return self.driver.sendCommand(commandNumber, parameters, skipStatusErrors)
        except driver.PrinterException, e:
            logging.getLogger().error("epsonFiscalDriver.PrinterException: %s" % str(e))
            raise PrinterException("Error de la impresora fiscal: " + str(e))

    def openNonFiscalReceipt(self):
        status = self._sendCommand(self.CMD_OPEN_NON_FISCAL_RECEIPT, [])
        self._currentDocument = self.CURRENT_DOC_NON_FISCAL
        self._currentDocumentType = None
        return status

    def printNonFiscalText(self, text):
        return self._sendCommand(self.CMD_PRINT_NON_FISCAL_TEXT, [formatText(text[:40] or " ")])

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
        self._sendCommand(self.CMD_SET_HEADER_TRAILER, (str(line), text))

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
        if not doc or filter(lambda x: x not in string.digits + "-.", doc or "") or not \
                docType in self.docTypeNames:
            doc, docType = "", ""
        else:
            doc = doc.replace("-", "").replace(".", "")
            docType = self.docTypeNames[docType]
        self._type = type
        # Remito primera linea - Es obligatorio si el cliente no es consumidor final
        if not reference:
            if (isCreditNote or self.ivaTypeMap.get(ivaType, "F") != "F"):
                reference = "-"
            else:
                reference = ""
        if self.model == "epsonlx300+":
            parameters = [isCreditNote and "N" or "F", # Por ahora no soporto ND, que sería "D"
                "C",
                type, # Tipo de FC (A/B/C)
                "1",   # Copias - Ignorado
                "P",   # "P" la impresora imprime la lineas(hoja en blanco) o "F" preimpreso
                "17",   # Tamaño Carac - Ignorado
                "I",   # Responsabilidad en el modo entrenamiento - Ignorado
                self.ivaTypeMap.get(ivaType, "F"),   # Iva Comprador
                formatText(name[:40]), # Nombre
                formatText(name[40:80]), # Segunda parte del nombre - Ignorado
                formatText(docType) or (isCreditNote and "-" or ""),
                 # Tipo de Doc. - Si es NC obligado pongo algo
                doc or (isCreditNote and "-" or ""), # Nro Doc - Si es NC obligado pongo algo
                "N", # No imprime leyenda de BIENES DE USO
                formatText(address[:self.ADDRESS_SIZE] or "-"), # Domicilio
                formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]), # Domicilio 2da linea
                formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]), # Domicilio 3ra linea
                (isCreditNote or self.ivaTypeMap.get(ivaType, "F") != "F") and "-" or "",
                reference, # Remito primera linea - Es obligatorio si el cliente no es consumidor final
                "", # Remito segunda linea
                "C", # No somos una farmacia
                ]
        else:
            parameters = [isCreditNote and "M" or "T", # Ticket NC o Factura
                "C",  # Tipo de Salida - Ignorado
                type, # Tipo de FC (A/B/C)
                "1",   # Copias - Ignorado
                "P",   # Tipo de Hoja - Ignorado
                "17",   # Tamaño Carac - Ignorado
                "E",   # Responsabilidad en el modo entrenamiento - Ignorado
                self.ivaTypeMap.get(ivaType, "F"),   # Iva Comprador
                formatText(name[:40]), # Nombre
                formatText(name[40:80]), # Segunda parte del nombre - Ignorado
                formatText(docType) or (isCreditNote and "-" or ""),
                 # Tipo de Doc. - Si es NC obligado pongo algo
                doc or (isCreditNote and "-" or ""), # Nro Doc - Si es NC obligado pongo algo
                "N", # No imprime leyenda de BIENES DE USO
                formatText(address[:self.ADDRESS_SIZE] or "-"), # Domicilio
                formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]), # Domicilio 2da linea
                formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]), # Domicilio 3ra linea
                (isCreditNote or self.ivaTypeMap.get(ivaType, "F") != "F") and "-" or "0",
                reference, # Remito primera linea - Es obligatorio si el cliente no es consumidor final
                "", # Remito segunda linea
                "C", # No somos una farmacia
                ]
        if isCreditNote:
            self._currentDocument = self.CURRENT_DOC_CREDIT_TICKET
        else:
            self._currentDocument = self.CURRENT_DOC_BILL_TICKET
        # guardo el tipo de FC (A/B/C)
        self._currentDocumentType = type
        return self._sendCommand(self.CMD_OPEN_BILL_TICKET, parameters)

    def _getCommandIndex(self):
        if self._currentDocument == self.CURRENT_DOC_TICKET:
            return 0
        elif self._currentDocument in (self.CURRENT_DOC_BILL_TICKET, self.CURRENT_DOC_CREDIT_TICKET):
            return 1
        elif self._currentDocument == self.CURRENT_DOC_NON_FISCAL:
            return 2
        raise "Invalid currentDocument"

    def openTicket(self, defaultLetter='B'):
        if self.model == "epsonlx300+":
            return self.openBillTicket(defaultLetter, "CONSUMIDOR FINAL", "", None, None,
                self.IVA_TYPE_CONSUMIDOR_FINAL)
        else:
            self._sendCommand(self.CMD_OPEN_FISCAL_RECEIPT, ["C"])
            self._currentDocument = self.CURRENT_DOC_TICKET

    def openDrawer(self):
        self._sendCommand(self.CMD_OPEN_DRAWER, [])

    def closeDocument(self):
        if self._currentDocument == self.CURRENT_DOC_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()], ["T"])
            return reply[2]
        if self._currentDocument == self.CURRENT_DOC_BILL_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()],
                [self.model == "epsonlx300+" and "F" or "T", self._type, "FINAL"])
            del self._type
            return reply[2]
        if self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()],
                [self.model == "epsonlx300+" and "N" or "M", self._type, "FINAL"])
            del self._type
            return reply[2]
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL, ):
            return self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT, ["T"])
        raise NotImplementedError

    def cancelDocument(self):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.CMD_ADD_PAYMENT[self._getCommandIndex()], ["Cancelar", "0", 'C'])
            return status
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL, ):
            self.printNonFiscalText("CANCELADO")
            return self.closeDocument()
        raise NotImplementedError

    def addItem(self, description, quantity, price, iva, discount, discountDescription, negative=False,
                long_description=False, round_up=False):
        if negative:
            sign = 'R'
        else:
            sign = 'M'
        quantityStr = str(int(quantity * 1000))
        if self.model == "epsonlx300+":
            bultosStr = str(int(quantity))
        else:
            # UPDATE: Así estaba ates de actualizar
            # bultosStr = "0" * 5  # No se usa en TM220AF ni TM300AF ni TMU220AF
            bultosStr = "00001" # No se usa en TM220AF ni TM300AF ni TMU220AF
        if self._currentDocumentType != 'A':
            # enviar con el iva incluido
            if self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
                # nota de crédito?
                priceUnitStr = str(int(floor(price * 100)))
            else:
                priceUnitStr = str(int(round(price * 100, 0)))
        else:
            net = price / ((100.0 + iva) / 100.0)
            if round_up:
                net = self.float_round_up(net, 2)
            if self.model == "tm-220-af":
                # enviar sin el iva (factura A)
                priceUnitStr = "%0.4f" % net
            else:
                # enviar sin el iva (factura A)
                if self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
                    # nota de crédito?
                    priceUnitStr = str(int(floor(net * 100)))
                else:
                    priceUnitStr = str(int(round(net * 100, 0)))
        ivaStr = str(int(iva * 100))
        if long_description:
            description = self.truncate_description(description)
        else:
            if type(description) in types.StringTypes:
                description = [description]

        if self._currentDocument in (self.CURRENT_DOC_BILL_TICKET, self.CURRENT_DOC_CREDIT_TICKET):
            if long_description :
                extra_parameters = self.get_extraparameters(description)
                description = '-'
            else:
                extra_parameters = ["", "", ""]
        else:
            extra_parameters = []

        # UPDATE: esto estaba en lugar de los siguientes siguiente "for" e "if" entre líneas 340 y 356
        # if self._getCommandIndex() == 0:
        #     for d in description[:-1]:
        #         self._sendCommand(self.CMD_PRINT_TEXT_IN_FISCAL,
        #                            [formatText(d)[:20]])
        for i, d in enumerate(description[:-1]):
            if self._getCommandIndex() == 0:
                # tickets: enviar descripción complementaria con comando extra:
                if d:
                    self._sendCommand(self.CMD_PRINT_TEXT_IN_FISCAL,
                                       [formatText(d)[:20]])
            else:
                # completar linea descripción complementaria (facturas)
                extraparams[-3 + i] = formatText(d)[:20]
        if self.USAR_IMPUESTOS_INTERNOS and self._currentDocument != self.CURRENT_DOC_TICKET:
            # agregar campos de acrecentamiento RNI e impuestos internos N(9.8)
            extraparams += ["0000", "0" * 17]

        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                          [formatText(description[-1][:20]),
                            quantityStr, priceUnitStr, ivaStr, sign, bultosStr, "0" * 8] + extra_parameters)
        if discount:
            discountStr = str(int(discount * 100))
            self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                [formatText(discountDescription[:20]), "1000",
                  discountStr, ivaStr, 'R', "0", "0"] + extra_parameters)
        return reply

    def addPayment(self, description, payment):
        paymentStr = str(int(payment * 100))
        status = self._sendCommand(self.CMD_ADD_PAYMENT[self._getCommandIndex()],
                                   [formatText(description)[:20], paymentStr, 'T'])
        return status

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un adicional a la FC.
            @param description  Descripción
            @param amount       Importe (sin iva en FC A, sino con IVA)
            @param iva          Porcentaje de Iva
            @param negative True->Descuento, False->Recargo"""
        if negative:
            sign = 'R'
        else:
            sign = 'M'
        quantityStr = "1000"
        bultosStr = "0"
        priceUnit = amount
        if self._currentDocumentType != 'A':
            # enviar con el iva incluido
            if self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
                priceUnitStr = str(int(ceil(priceUnit * 100)))
            else:
                priceUnitStr = str(int(round(priceUnit * 100, 0)))
        else:
            # enviar sin el iva (factura A)
            if self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
                priceUnitStr = str(int(ceil((priceUnit / ((100.0 + iva) / 100)) * 100)))
            else:
                priceUnitStr = str(int(round((priceUnit / ((100.0 + iva) / 100)) * 100, 0)))
        ivaStr = str(int(iva * 100))
        extraparams = self._currentDocument in (self.CURRENT_DOC_BILL_TICKET,
            self.CURRENT_DOC_CREDIT_TICKET) and ["", "", ""] or []
        if self.USAR_IMPUESTOS_INTERNOS and self._currentDocument != self.CURRENT_DOC_TICKET:
            # agregar campos de acrecentamiento RNI e impuestos internos N(9.8)
            extraparams += ["0000", "0" * 17]
        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                          [formatText(description[:20]),
                            quantityStr, priceUnitStr, ivaStr, sign, bultosStr, "0" * 8] + extraparams)
        return reply

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
        reply = self._sendCommand(self.CMD_ADD_PERCEPTION,
                          [formatText(description[:20]), perception] + params)
        return reply

    def subtotal(self, print_text=True, display=False, text="Subtotal"):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.CMD_PRINT_SUBTOTAL[self._getCommandIndex()], ["P" if print_text else "O", text])
            return status
        raise NotImplementedError

    def dailyClose(self, type):
        reply = self._sendCommand(self.CMD_DAILY_CLOSE, [type, "P"])
        return reply[2:]

    def auditByDate(self, date_from, date_to, type):
        reply = self._sendCommand(self.CMD_AUDIT_BY_DATE, [date_from, date_to, type])
        return reply[2:]

    def auditByClosure(self, close_from, close_to, type):
        reply = self._sendCommand(self.CMD_AUDIT_BY_CLOSURE, [close_from, close_to, type])
        return reply[2:]

    def getLastNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
            # La respuesta no es válida. Vuelvo a hacer el pedido y si hay
            # algún error que se reporte como excepción
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[6])
        else:
            return int(reply[4])

    def getLastCreditNoteNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
            # La respuesta no es válida. Vuelvo a hacer el pedido y si hay algún
            # error que se reporte como excepción
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[10])
        else:
            return int(reply[11])

    def cancelAnyDocument(self):
        try:
            self._sendCommand(self.CMD_ADD_PAYMENT[0], ["Cancelar", "0", 'C'])
            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_ADD_PAYMENT[1], ["Cancelar", "0", 'C'])
            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT, ["T"])
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
        print_subtotal = "P" if print_subtotal is True else "N"
        reply = self._sendCommand(self.CMD_PRINT_SUBTOTAL[self._getCommandIndex()], [print_subtotal, "Subtotal"], True)

        if len(reply) < 3:
            # La respuesta no es válida. Vuelvo a hacer el pedido y
            #  si hay algún error que se reporte como excepción
            reply = self._sendCommand(self.CMD_PRINT_SUBTOTAL[self._getCommandIndex()], [print_subtotal, "Subtotal"], False)
        return reply[3:]  # datos útiles

    def getWarnings(self):
        ret = []
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["N"], True)
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
