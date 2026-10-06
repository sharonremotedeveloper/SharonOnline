"""Task 10.8: receipts. One per successful payment, sequential INV-YYYYMM-XXXXX numbers, owner-only PDF."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.payments.models import CreditPack, CreditPurchase, PaymentTransaction, Receipt
from apps.payments.services import receipts as receipt_service

pytestmark = pytest.mark.django_db

LIST_URL = '/api/v1/payments/receipts/'


def _pdf_url(receipt):
    return f'/api/v1/payments/receipts/{receipt.id}/pdf/'


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _paid_lesson(student=None, **tx_fields):
    student = student or f.make_student()
    booking = f.make_booking(student=student, status='pending_payment')
    return f.make_payment_transaction(booking, **tx_fields)


class TestIssuance:
    def test_receipt_is_issued_when_a_payment_succeeds(self):
        tx = _paid_lesson(amount=Decimal('9.00'), currency='USD')
        receipt = Receipt.objects.get(transaction=tx)
        assert receipt.student_id == tx.booking.student_id
        assert (receipt.currency, receipt.total_amount) == ('USD', Decimal('9.00'))
        assert receipt.subtotal + receipt.tax_amount == receipt.total_amount

    def test_no_receipt_for_a_payment_that_did_not_succeed(self):
        for status in ('initialized', 'pending_capture', 'failed', 'unallocated'):
            tx = _paid_lesson(status=status)
            assert not Receipt.objects.filter(transaction=tx).exists(), status

    def test_a_pending_capture_gets_its_receipt_only_when_it_clears(self):
        tx = _paid_lesson(status=PaymentTransaction.Status.PENDING_CAPTURE)
        tx.status = PaymentTransaction.Status.SUCCESS
        tx.save()
        assert Receipt.objects.filter(transaction=tx).count() == 1

    def test_saving_a_successful_payment_again_does_not_issue_a_second_receipt(self):
        tx = _paid_lesson()
        number = Receipt.objects.get(transaction=tx).receipt_number
        tx.save()
        tx.refresh_from_db()
        tx.save()
        assert list(Receipt.objects.filter(transaction=tx).values_list('receipt_number', flat=True)) == [number]

    def test_credit_pack_purchase_gets_a_receipt_for_the_buyer(self):
        student = f.make_student()
        pack = CreditPack.objects.create(code='r5', name='Five lessons', credits=5, price_usd='40.00', price_zar='700.00',
                                         price_eur='37.00', price_jpy='6000')
        purchase = CreditPurchase.objects.create(user=student, pack=pack, amount=Decimal('700.00'), currency='ZAR',
                                                 fx_rate_to_zar=Decimal('1'))
        tx = PaymentTransaction.objects.create(credit_purchase=purchase, gateway='payfast', gateway_reference='PF-R-1',
                                               amount=Decimal('700.00'), currency='ZAR', status='success')
        receipt = Receipt.objects.get(transaction=tx)
        assert receipt.student_id == student.id
        assert 'Five lessons' in receipt.description

    def test_vat_is_zero_until_a_rate_is_configured_and_then_included_in_the_total(self, settings):
        assert Receipt.objects.get(transaction=_paid_lesson(amount=Decimal('115.00'))).tax_amount == Decimal('0.00')
        settings.PLATFORM_VAT_RATE = Decimal('0.15')
        receipt = Receipt.objects.get(transaction=_paid_lesson(amount=Decimal('115.00')))
        assert (receipt.subtotal, receipt.tax_amount, receipt.total_amount) == (
            Decimal('100.00'), Decimal('15.00'), Decimal('115.00'))


class TestNumbering:
    def test_numbers_are_sequential_within_a_month_and_formatted(self):
        numbers = [Receipt.objects.get(transaction=_paid_lesson()).receipt_number for _ in range(3)]
        prefix = f"INV-{timezone.now():%Y%m}-"
        assert numbers == [f'{prefix}00001', f'{prefix}00002', f'{prefix}00003']

    def test_a_new_month_restarts_the_sequence(self):
        april = timezone.now().replace(year=2027, month=4, day=2)
        may = timezone.now().replace(year=2027, month=5, day=2)
        assert receipt_service.next_receipt_number(april) == 'INV-202704-00001'
        assert receipt_service.next_receipt_number(april) == 'INV-202704-00002'
        assert receipt_service.next_receipt_number(may) == 'INV-202705-00001'

    def test_the_number_is_unique_in_the_database(self):
        first = Receipt.objects.get(transaction=_paid_lesson())
        other = _paid_lesson()
        Receipt.objects.filter(transaction=other).delete()
        with pytest.raises(IntegrityError), transaction.atomic():
            Receipt.objects.create(transaction=other, student=other.booking.student, receipt_number=first.receipt_number,
                                   currency='USD', subtotal=1, tax_amount=0, total_amount=1, description='x')


class TestApi:
    def test_student_lists_only_their_own_receipts(self):
        mine = _paid_lesson()
        _paid_lesson()  # somebody else's
        response = _client(mine.booking.student).get(LIST_URL)
        assert response.status_code == 200
        rows = response.json()
        assert [r['receipt_number'] for r in rows] == [Receipt.objects.get(transaction=mine).receipt_number]
        assert rows[0]['total_amount'] == '9.00' and rows[0]['currency'] == 'USD'
        assert rows[0]['pdf_url'].endswith(f"/receipts/{rows[0]['id']}/pdf/")

    def test_money_is_an_exact_string_in_the_currency_minor_unit(self):
        tx = _paid_lesson(amount=Decimal('1350'), currency='JPY')
        rows = _client(tx.booking.student).get(LIST_URL).json()
        assert rows[0]['total_amount'] == '1350'

    def test_listing_requires_authentication(self):
        assert APIClient().get(LIST_URL).status_code == 401

    def test_owner_streams_a_real_pdf(self):
        tx = _paid_lesson()
        receipt = Receipt.objects.get(transaction=tx)
        response = _client(tx.booking.student).get(_pdf_url(receipt))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert 'attachment' in response['Content-Disposition'] and receipt.receipt_number in response['Content-Disposition']
        assert response['Cache-Control'].startswith('private') and 'no-store' in response['Cache-Control']
        body = b''.join(response.streaming_content) if response.streaming else response.content
        assert body.startswith(b'%PDF-')

    def test_another_student_cannot_read_the_pdf_and_learns_nothing(self):
        receipt = Receipt.objects.get(transaction=_paid_lesson())
        stranger = f.make_student()
        missing = _client(stranger).get(f'/api/v1/payments/receipts/{"00000000-0000-0000-0000-000000000000"}/pdf/')
        denied = _client(stranger).get(_pdf_url(receipt))
        assert denied.status_code == missing.status_code == 404

    def test_a_tutor_cannot_read_a_students_receipt(self):
        tx = _paid_lesson()
        receipt = Receipt.objects.get(transaction=tx)
        assert _client(tx.booking.teacher.user).get(_pdf_url(receipt)).status_code == 404

    def test_pdf_requires_authentication(self):
        receipt = Receipt.objects.get(transaction=_paid_lesson())
        assert APIClient().get(_pdf_url(receipt)).status_code == 401


class TestPdfContent:
    def test_pdf_carries_the_receipt_facts(self):
        tx = _paid_lesson(amount=Decimal('9.00'))
        receipt = Receipt.objects.get(transaction=tx)
        pdf = receipt_service.render_receipt_pdf(receipt)
        assert pdf.startswith(b'%PDF-')
        text = receipt_service.receipt_lines(receipt)
        joined = '\n'.join(text)
        assert receipt.receipt_number in joined
        assert 'USD 9.00' in joined
        assert tx.booking.student.username in joined or tx.booking.student.get_full_name() in joined
