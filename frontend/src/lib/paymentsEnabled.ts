/** False hides every gateway option (PayPal, PayFast, pack purchases); the backend enforces it with PAYMENTS_ENABLED. */
export const PAYMENTS_ENABLED = process.env.NEXT_PUBLIC_PAYMENTS_ENABLED !== "false";
