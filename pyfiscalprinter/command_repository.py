class CommandRepository:
    CMD_EPSON_EXT = {
        'CMD_OPEN_FISCAL_RECEIPT': 0x40,
        'CMD_OPEN_BILL_TICKET': ('0B01|0000', '0D01|0000'),
        'CMD_PRINT_TEXT_IN_FISCAL': 0x41,
        'CMD_PRINT_LINE_ITEM': ('0B02|0000', '0D02|0000'),
        'CMD_ADD_PERCEPTION': 0x66,
        'CMD_PRINT_SUBTOTAL': ('0B03|0000', '0D03|0000'),
        'CMD_ADD_PAYMENT': ('0B05|0000', '0D05|0000'),
        'CMD_CLOSE_FISCAL_RECEIPT': ('0B06|0003', '0D06|0003'),
        'CMD_CANCEL_DOCUMENT': ('0B07|0000', '0D07|0000'),
        'CMD_DAILY_CLOSE': '0801|0000',
        'CMD_TELLER_EXIT': '0802|0001',
        'CMD_STATUS_REQUEST': '0001|0000',
        'CMD_PRINT_DISCOUNT': '0B02|0006',

        'CMD_AUDIT_BY_DATE': 0x3A,
        'CMD_AUDIT_BY_CLOSURE': '0813|0000',

        'CMD_OPEN_DRAWER': 0x7b,

        'CMD_SET_HEADER_TRAILER': '0508|0000',

        'CMD_OPEN_NON_FISCAL_RECEIPT': '0E01|0000',
        'CMD_PRINT_NON_FISCAL_TEXT': '0E02|0000',
        'CMD_CLOSE_NON_FISCAL_RECEIPT': '0E06|0000',

        'CURRENT_DOC_TICKET': 1,
        'CURRENT_DOC_BILL_TICKET': 2,
        'CURRENT_DOC_CREDIT_TICKET': 4,
        'CURRENT_DOC_NON_FISCAL': 3,
    }

    def getCmd(self, model):

        dictionary = {
            'epson_ext': self.CMD_EPSON_EXT,
            'epson': self.CMD_EPSON
        }


        return dictionary[model]
