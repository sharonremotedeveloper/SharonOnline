"""
A student whose delivered lesson went unpaid (a pending PayPal payment failed after the lesson, Task 10.2 plan P-3/P-4) has
`User.booking_blocked_reason` set. Every path that creates or pays for a booking refuses with 409 while it is non-empty;
staff clear the field (Django admin -> Users -> "Booking block").
"""


def booking_block_message(user) -> str:
    """'' when the student may book, otherwise the sentence shown to them (it includes the stored reason)."""
    reason = (getattr(user, 'booking_blocked_reason', '') or '').strip()
    return f"New bookings are paused on your account. {reason}" if reason else ''
