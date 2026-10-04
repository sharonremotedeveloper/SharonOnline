"""
Layer-0 integration contract (F0 x N1c): the fulfilment e-mail step driven through the REAL unified sender and its REAL
error classes (F0 re-review m5: `classify_failure` had only been tested against a stand-in). Resend's HTTP answer is
the only fake (`resend` fixture in conftest.py); Zoom is mocked at the client.
"""
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.integrations.tasks import dispatch_booking_fulfillment, retry_fulfillment_dispatches_task
from apps.integrations.zoom import zoom_client
from apps.payments.models import FulfillmentDispatch
from test_f0_fulfilment_probe import NEW_MEETING, confirmed
from test_send_email import FakeResponse

FD = FulfillmentDispatch.Status
St = FulfillmentDispatch.StepState


@pytest.mark.django_db
class TestFulfilmentEmailStepAgainstTheRealSender:
    def test_a_sent_confirmation_completes_the_dispatch(self, resend, teacher_user, student_user):
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING):
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.email_state) == (FD.SUCCEEDED, St.DONE)
        assert len(resend.calls) == 1 and resend.calls[0].headers['Idempotency-Key'].startswith(f'booking-confirmed:{b.id}:')

    def test_a_rejected_confirmation_is_terminal_without_a_second_room(self, resend, teacher_user, student_user):
        resend.response = FakeResponse(422, {'name': 'validation_error'})
        b = confirmed(teacher_user, student_user)
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING) as create:
            dispatch_booking_fulfillment(str(b.id))
            FulfillmentDispatch.objects.filter(booking=b).update(next_retry_at=timezone.now() - timedelta(seconds=1))
            assert retry_fulfillment_dispatches_task()['redispatched_count'] == 0
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.zoom_state, d.email_state) == (FD.FAILED, St.DONE, St.FAILED)
        assert create.call_count == 1 and len(resend.calls) == 1

    def test_a_rate_limited_confirmation_waits_for_retry_after(self, resend, teacher_user, student_user, settings):
        settings.FULFILLMENT_RETRY_SECONDS = 30
        resend.response = FakeResponse(429, {'name': 'rate_limit_exceeded'}, headers={'Retry-After': '900'})
        b = confirmed(teacher_user, student_user)
        before = timezone.now()
        with mock.patch.object(zoom_client, 'create_meeting', return_value=NEW_MEETING):
            dispatch_booking_fulfillment(str(b.id))
        d = FulfillmentDispatch.objects.get(booking=b)
        assert (d.status, d.email_state) == (FD.RETRYABLE, St.FAILED) and not d.email_completed
        assert d.next_retry_at >= before + timedelta(seconds=899)
