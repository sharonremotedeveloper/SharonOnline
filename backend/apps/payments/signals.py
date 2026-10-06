from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PaymentTransaction


@receiver(post_save, sender=PaymentTransaction, dispatch_uid='payments.issue_receipt')
def issue_receipt_on_success(sender, instance, **kwargs):
    """Task 10.8: the one place a receipt is issued. Runs inside the saving transaction, so no payment without its receipt."""
    from .services.receipts import issue_receipt
    issue_receipt(instance)
