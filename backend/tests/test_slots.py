import pytest
from datetime import date, timedelta
from apps.bookings.services.slot_generator import generate_teacher_slots

@pytest.mark.django_db
def test_slot_generator_creates_25_min_slots(teacher_user):
    # Find next Monday
    today = date.today()
    days_until_monday = (0 - today.weekday() + 7) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    slots = generate_teacher_slots(
        teacher=teacher_user,
        start_date=next_monday,
        days_ahead=1,
        viewer_tz_name='Asia/Tokyo'
    )

    # 09:00 to 12:00 SAST is 3 hours. 30 min pacing (25 min lesson + 5 min buffer) = 6 slots
    assert len(slots) == 6
    first_slot = slots[0]
    assert first_slot['status'] == 'available'
    assert first_slot['is_bookable'] is True
    # 09:00 SAST (UTC+2) is 16:00 JST (UTC+9) -> +7 hours offset
    assert first_slot['local_start_time'] == '16:00'
    assert first_slot['local_end_time'] == '16:25'
