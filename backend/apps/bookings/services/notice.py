"""
Minimum notice before a lesson (T2, plan 3.5): ONE definition used when a slot is listed (slot_generator), when it is reserved
and when it is paid for (checkout init, PayPal capture, credit redemption), so a hold made inside the window cannot be paid
after the window closed. Provisional setting TUTOR_MIN_NOTICE_MINUTES (plan section 9).
"""
from datetime import datetime, timedelta
from typing import Optional

from django.conf import settings

from apps.common import clock

TOO_CLOSE_CODE = 'too_close_to_start'
TOO_CLOSE_MESSAGE = ('This lesson is too close to its start time to be booked. '
                     'Please choose a later time slot.')


def min_notice() -> timedelta:
    return timedelta(minutes=settings.TUTOR_MIN_NOTICE_MINUTES)


def notice_closed(start_utc: datetime, now: Optional[datetime] = None) -> bool:
    """True when a lesson starting at `start_utc` is no longer bookable: it must start MORE than the notice from now."""
    return start_utc <= (now or clock.now()) + min_notice()
