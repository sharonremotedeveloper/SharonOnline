"""
The bank file for a payout batch (slice P1b). This is the ONLY module that decrypts tutor bank details for payment: a test in
tests/test_payout_batches.py fails if another module starts importing the decryptor (the masking serializer is the one
older, read-only exception).
"""
import csv
import io

from apps.payments.services.payout_crypto import decrypt_payout_payload

HEADER = ['Beneficiary Name', 'Account Number', 'Branch Code', 'Account Type', 'Bank', 'Amount (ZAR)',
          'Beneficiary Reference', 'Own Reference']
_FORMULA_STARTS = ('=', '+', '-', '@', '\t', '\r')


def defuse(cell: str) -> str:
    """A spreadsheet runs a cell that starts with = + - @ as a formula. Prefix an apostrophe so it is read as text."""
    text = str(cell)
    return "'" + text if text.lstrip().startswith(_FORMULA_STARTS) else text


def build_csv(batch, lines) -> str:
    """One row per line, in a layout South African bank bulk-payment screens accept (all banks use universal branch codes)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(HEADER)
    for line in lines:
        account = line.teacher.user.payout_account
        payload = decrypt_payout_payload(account.encrypted_payload, account.key_version)
        writer.writerow([defuse(cell) for cell in (
            payload['account_holder_name'], payload['account_number'], payload['branch_code'], payload['account_type'],
            payload['bank_name'], f'{line.amount_zar:.2f}', 'Sharon ESL payout', f'{batch.batch_reference}-{str(line.id)[:8]}')])
    return out.getvalue()
