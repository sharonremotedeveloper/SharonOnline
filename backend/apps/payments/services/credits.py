from django.db import transaction
from django.db.models import F

from apps.payments.models import CreditBundle


def grant_credit(user, *, credits: int = 1, pack_name: str = 'Lesson Credit') -> CreditBundle:
    """
    Add `credits` lesson credits to the user's wallet and return the bundle that received them.

    The single way to grant credits: it never crashes for a student who owns several bundles (the old
    `get_or_create(user=...)` raised MultipleObjectsReturned), keeps `remaining <= total`, and uses F() updates so
    concurrent grants cannot overwrite each other. Call it inside the transaction that justifies the grant.
    """
    if credits < 1:
        raise ValueError("credits must be >= 1")
    with transaction.atomic():
        bundle = CreditBundle.objects.select_for_update().filter(user=user).order_by('-created_at').first()
        if bundle is None:
            return CreditBundle.objects.create(user=user, pack_name=pack_name, total_credits=credits,
                                               remaining_credits=credits, amount_paid=0, currency='USD')
        CreditBundle.objects.filter(pk=bundle.pk).update(
            total_credits=F('total_credits') + credits, remaining_credits=F('remaining_credits') + credits)
        bundle.refresh_from_db()
        return bundle
