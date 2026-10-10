# Development test bookings

Development browser testing can confirm a lesson without a payment gateway or a student wallet credit.

## Safety gate

Enable both variables only in the development deployment:

```text
PAYMENTS_ENABLED=false
TEST_BOOKINGS_ENABLED=true
NEXT_PUBLIC_PAYMENTS_ENABLED=false
NEXT_PUBLIC_TEST_BOOKINGS_ENABLED=true
```

The backend endpoint refuses the test path unless payments are disabled and `TEST_BOOKINGS_ENABLED` is explicitly true. The production settings override `TEST_BOOKINGS_ENABLED` to false, so copying the variable into production cannot enable free bookings there.

## Browser flow

1. Sign in as a student and select an approved tutor's future availability slot.
2. On checkout, click **Confirm Test Booking**.
3. The normal reservation lock and booking state transition still run; no payment transaction, wallet debit, or ledger funding row is created.
4. Fulfillment is queued normally, including Daily room provisioning and the confirmation flow.
5. Open the resulting student and tutor classroom URLs during the booking window.

This path is for development/provider E2E testing only. It is not a replacement for validating the real credit and gateway checkout flows.
