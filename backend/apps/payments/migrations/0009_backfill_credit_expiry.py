from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def give_existing_credits_an_expiry(apps, schema_editor):
    """Credits that predate expiry get the policy's 30 days from the day this ships (D-6), not an instant expiry."""
    CreditBundle = apps.get_model('payments', 'CreditBundle')
    CreditBundle.objects.filter(expires_at__isnull=True).update(expires_at=timezone.now() + timedelta(days=30))


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0008_credit_lots_refunds_ledger_accounts'),
    ]

    operations = [
        migrations.RunPython(give_existing_credits_an_expiry, migrations.RunPython.noop),
    ]
