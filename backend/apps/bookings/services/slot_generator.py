from datetime import datetime, date, time, timedelta
import pytz
from django.db.models import Q
from django.utils import timezone
from apps.teachers.models import TeacherProfile, TeacherAvailability
from apps.bookings.models import Booking
from apps.bookings.services.holds import live_hold_q
from apps.bookings.services.lock_service import is_slot_locked

LESSON_DURATION_MINUTES = 25
BUFFER_MINUTES = 5
SLOT_STEP_MINUTES = LESSON_DURATION_MINUTES + BUFFER_MINUTES  # 30-minute pacing

# Only these two statuses leave the time free; every other outcome (paid, taught, no-show, disputed, interrupted...)
# has consumed it. Unpaid PENDING_PAYMENT bookings count while their hold is live (services.holds.live_hold_q).
FREE_STATUSES = (Booking.Status.PENDING_PAYMENT, Booking.Status.CANCELLED)

def generate_teacher_slots(
    teacher: TeacherProfile,
    start_date: date = None,
    days_ahead: int = 7,
    viewer_tz_name: str = 'UTC'
) -> list:
    """
    Projects a teacher's recurring availability into concrete 25-minute UTC slots,
    annotated with local viewer time and booking/lock availability.
    """
    now_utc = timezone.now()
    if start_date is None:
        start_date = timezone.localdate(now_utc)

    # Resolve timezones
    teacher_tz_str = teacher.user.timezone or 'Africa/Johannesburg'
    try:
        teacher_tz = pytz.timezone(teacher_tz_str)
    except pytz.UnknownTimeZoneError:
        teacher_tz = pytz.timezone('Africa/Johannesburg')

    try:
        viewer_tz = pytz.timezone(viewer_tz_name or 'UTC')
    except pytz.UnknownTimeZoneError:
        viewer_tz = pytz.UTC

    # Query recurring availabilities
    availabilities = list(teacher.availabilities.filter(is_active=True))
    if not availabilities:
        return []

    # Calculate date range
    end_date = start_date + timedelta(days=days_ahead)
    range_start_utc = datetime.combine(start_date, time.min).replace(tzinfo=pytz.UTC)
    range_end_utc = datetime.combine(end_date, time.max).replace(tzinfo=pytz.UTC)

    # Everything that occupies this tutor's time in the window, found by OVERLAP (not exact start), so an off-grid
    # booking blocks every slot it touches. Live unpaid holds are 'reserved'; everything else is 'booked'.
    occupying = Booking.objects.filter(
        teacher=teacher, start_time_utc__lte=range_end_utc, end_time_utc__gte=range_start_utc,
    ).filter(~Q(status__in=FREE_STATUSES) | live_hold_q(now_utc)).values_list('start_time_utc', 'end_time_utc', 'status')
    booked_spans = [(s, e) for s, e, st in occupying if st != Booking.Status.PENDING_PAYMENT]
    held_spans = [(s, e) for s, e, st in occupying if st == Booking.Status.PENDING_PAYMENT]

    def overlaps(spans, start, end):
        return any(s < end and e > start for s, e in spans)

    generated_slots = []
    seen_starts = set()

    for day_offset in range(days_ahead):
        current_date = start_date + timedelta(days=day_offset)
        weekday = current_date.weekday()  # 0=Monday, 6=Sunday

        matching_availabilities = [a for a in availabilities if a.day_of_week == weekday]

        for avail in matching_availabilities:
            # Construct start and end datetimes in teacher timezone
            start_naive = datetime.combine(current_date, avail.start_time)
            end_naive = datetime.combine(current_date, avail.end_time)

            start_localized = teacher_tz.localize(start_naive)
            end_localized = teacher_tz.localize(end_naive)

            cursor = start_localized
            while cursor + timedelta(minutes=LESSON_DURATION_MINUTES) <= end_localized:
                slot_start_utc = cursor.astimezone(pytz.UTC)
                slot_end_utc = (cursor + timedelta(minutes=LESSON_DURATION_MINUTES)).astimezone(pytz.UTC)

                # Skip past slots (must be at least 10 minutes in the future)
                iso_utc = slot_start_utc.isoformat()
                if slot_start_utc > now_utc + timedelta(minutes=10) and iso_utc not in seen_starts:
                    seen_starts.add(iso_utc)  # overlapping availability rows must not list one slot twice
                    is_booked = overlaps(booked_spans, slot_start_utc, slot_end_utc)
                    is_locked = overlaps(held_spans, slot_start_utc, slot_end_utc) or is_slot_locked(str(teacher.id), iso_utc)

                    # Determine status
                    if is_booked:
                        slot_status = 'booked'
                        bookable = False
                    elif is_locked:
                        slot_status = 'reserved'
                        bookable = False
                    else:
                        slot_status = 'available'
                        bookable = True

                    # Localized for student viewer
                    viewer_start = slot_start_utc.astimezone(viewer_tz)
                    viewer_end = slot_end_utc.astimezone(viewer_tz)

                    generated_slots.append({
                        "start_time_utc": iso_utc,
                        "end_time_utc": slot_end_utc.isoformat(),
                        "local_date": viewer_start.strftime("%Y-%m-%d"),
                        "local_start_time": viewer_start.strftime("%H:%M"),
                        "local_end_time": viewer_end.strftime("%H:%M"),
                        "viewer_timezone": viewer_tz.zone,
                        "status": slot_status,
                        "is_bookable": bookable
                    })

                cursor += timedelta(minutes=SLOT_STEP_MINUTES)

    # Sort slots chronologically
    generated_slots.sort(key=lambda s: s["start_time_utc"])
    return generated_slots
