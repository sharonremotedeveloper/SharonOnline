"""
Task 10.8: receipts.

`issue_receipt(tx)` is idempotent and is called from one place, the `post_save` hook in `apps/payments/signals.py`, so
every path that marks a PaymentTransaction SUCCESS (webhook, PayPal capture, grace clearance, reconciliation, credit
purchase) gets a receipt without each of them remembering to ask. The PDF is rendered on demand from the stored row.
"""
import io
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.payments.models import PaymentTransaction, Receipt, ReceiptSequence
from apps.payments.services.pricing import quantize_money

PLATFORM_NAME = 'Sharon Online ESL'


def next_receipt_number(now=None) -> str:
    """INV-YYYYMM-XXXXX, gap-free per month (the counter row is locked until the issuing transaction ends)."""
    period = (now or timezone.now()).strftime('%Y%m')
    with transaction.atomic():
        ReceiptSequence.objects.get_or_create(period=period)
        sequence = ReceiptSequence.objects.select_for_update().get(period=period)
        sequence.last_number += 1
        sequence.save(update_fields=['last_number'])
    return f'INV-{period}-{sequence.last_number:05d}'


def _split_tax(total: Decimal, currency: str) -> tuple[Decimal, Decimal]:
    """Prices are VAT-inclusive: tax = total * rate / (1 + rate). Rate 0 (D-12 pending) gives tax 0."""
    rate = Decimal(str(getattr(settings, 'PLATFORM_VAT_RATE', 0) or 0))
    tax = quantize_money(total * rate / (1 + rate), currency) if rate > 0 else Decimal('0')
    return total - tax, tax


def _describe(tx: PaymentTransaction) -> tuple[object, str]:
    """(the paying student, what was bought)."""
    if tx.credit_purchase_id:
        purchase = tx.credit_purchase
        return purchase.user, f'{purchase.pack.name} ({purchase.pack.credits} lesson credits)'
    booking = tx.booking
    teacher = booking.teacher.user
    when = booking.start_time_utc.strftime('%d %b %Y %H:%M UTC')
    return booking.student, f'25-minute ESL lesson with {teacher.get_full_name() or teacher.username}, {when}'


def issue_receipt(tx: PaymentTransaction) -> Receipt | None:
    """The receipt for a successful payment; None for any other status. Safe to call repeatedly."""
    if tx.status != PaymentTransaction.Status.SUCCESS:
        return None
    existing = Receipt.objects.filter(transaction=tx).first()
    if existing is not None:
        return existing
    student, description = _describe(tx)
    total = quantize_money(tx.amount, tx.currency)
    subtotal, tax = _split_tax(total, tx.currency)
    return Receipt.objects.create(
        transaction=tx, student=student, receipt_number=next_receipt_number(), currency=tx.currency,
        subtotal=subtotal, tax_amount=tax, total_amount=total, description=description[:255],
    )


def receipt_lines(receipt: Receipt) -> list[str]:
    """The human-readable body of the PDF (kept separate so the content is testable without parsing a PDF)."""
    tx = receipt.transaction
    student = receipt.student
    paid_at = tx.updated_at or receipt.created_at
    vat = f'VAT included: {receipt.currency} {_money(receipt.tax_amount, receipt.currency)}'
    return [
        f'Receipt {receipt.receipt_number}',
        f'Issued: {receipt.created_at:%d %b %Y}',
        f'Paid: {paid_at:%d %b %Y %H:%M UTC} via {tx.get_gateway_display()}',
        f'Billed to: {student.get_full_name() or student.username}',
        receipt.description,
        f'Subtotal: {receipt.currency} {_money(receipt.subtotal, receipt.currency)}',
        vat,
        f'Total paid: {receipt.currency} {_money(receipt.total_amount, receipt.currency)}',
        f'Payment reference: {tx.gateway_reference}',
        'VAT registration details to be confirmed.',
    ]


def _money(amount, currency: str) -> str:
    return str(quantize_money(amount, currency))


def render_receipt_pdf(receipt: Receipt) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=True)
    width, height = A4
    pdf.setTitle(f'Receipt {receipt.receipt_number}')
    pdf.setFillColorRGB(0.12, 0.25, 0.45)
    pdf.rect(0, height - 28 * mm, width, 28 * mm, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont('Helvetica-Bold', 20)
    pdf.drawString(20 * mm, height - 18 * mm, PLATFORM_NAME)
    pdf.setFillColorRGB(0, 0, 0)
    y = height - 45 * mm
    for index, line in enumerate(receipt_lines(receipt)):
        pdf.setFont('Helvetica-Bold' if index in (0, 7) else 'Helvetica', 12 if index else 16)
        pdf.drawString(20 * mm, y, line)
        y -= 9 * mm
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
