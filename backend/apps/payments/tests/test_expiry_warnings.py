import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.payments.models import CreditBundle
from apps.payments.tasks import warn_expiring_credits_task, expire_stale_student_credits, expire_credits_task
from apps.notifications.models import Notification, NotificationLog

User = get_user_model()


@pytest.mark.django_db
class TestCreditExpiryWarnings:
    def test_alias_compatibility(self):
        """Verifies specification alias compatibility."""
        assert expire_stale_student_credits is expire_credits_task
        assert NotificationLog is Notification

    def test_warn_expiring_credits_within_7_days(self):
        """Credits expiring within 7 days trigger an idempotent notification."""
        user = User.objects.create_user(
            username='student_expiring@test.com',
            email='student_expiring@test.com',
            role='student',
        )
        now = timezone.now()

        # Bundle 1: Expiring in 4 days -> should trigger warning
        b1 = CreditBundle.objects.create(
            user=user,
            pack_name='5-Lesson Pack',
            total_credits=5,
            remaining_credits=3,
            amount_paid=Decimal('45.00'),
            currency='USD',
            expires_at=now + timedelta(days=4),
        )

        # Bundle 2: Expiring in 15 days -> should NOT trigger warning
        CreditBundle.objects.create(
            user=user,
            pack_name='10-Lesson Pack',
            total_credits=10,
            remaining_credits=10,
            amount_paid=Decimal('90.00'),
            currency='USD',
            expires_at=now + timedelta(days=15),
        )

        # Bundle 3: Already expired -> should NOT trigger warning
        CreditBundle.objects.create(
            user=user,
            pack_name='5-Lesson Pack',
            total_credits=5,
            remaining_credits=2,
            amount_paid=Decimal('45.00'),
            currency='USD',
            expires_at=now - timedelta(days=1),
        )

        # Bundle 4: 0 credits remaining -> should NOT trigger warning
        CreditBundle.objects.create(
            user=user,
            pack_name='5-Lesson Pack',
            total_credits=5,
            remaining_credits=0,
            amount_paid=Decimal('45.00'),
            currency='USD',
            expires_at=now + timedelta(days=3),
        )

        # Run task
        res = warn_expiring_credits_task()
        assert res['warned_count'] == 1

        # Check notification
        notif = Notification.objects.filter(user=user, kind='credit_expiring').first()
        assert notif is not None
        assert notif.idempotency_key == f'credit_expiry_7d:{b1.id}'
        assert notif.payload['credits'] == 3
        assert notif.payload['days_remaining'] == 7

        # Idempotency check: Re-running within the same window must not create duplicates
        res2 = warn_expiring_credits_task()
        assert res2['warned_count'] == 0
        assert Notification.objects.filter(user=user, kind='credit_expiring').count() == 1
