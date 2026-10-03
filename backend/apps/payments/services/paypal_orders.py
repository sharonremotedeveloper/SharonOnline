"""Creating the PayPal order for a checkout (Task 10.2). The order id is stored on our transaction."""
from apps.payments.gateways import paypal
from apps.payments.models import PaymentTransaction


def create_checkout_order(tx: PaymentTransaction, description: str) -> str:
    """
    Create the PayPal Order for `tx` at exactly tx.amount/tx.currency and remember its id. The request id is derived
    from our reference, so a retried create returns the same order instead of a second one.
    """
    order = paypal.create_order(
        reference=tx.merchant_reference, amount=tx.amount, currency=tx.currency, description=description,
        request_id=f'order-{tx.merchant_reference}')
    order_id = order.get('id')
    if not order_id or not isinstance(order_id, str):
        raise paypal.PayPalError('PayPal did not return an order id.')
    tx.gateway_order_id = order_id
    tx.save(update_fields=['gateway_order_id', 'updated_at'])
    return order_id
