def read_invoice(user, invoice_id, db):
    invoice = db.invoice(invoice_id)
    if invoice.owner_id != user.id:
        raise PermissionError()
    return invoice
