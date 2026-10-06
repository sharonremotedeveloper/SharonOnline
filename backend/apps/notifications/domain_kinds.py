"""Domain notification kinds for Sharon ESL (Slices N2a-c, N4).

Implements templates for:
- Reminders (N2a): 24h, 1h, 10m, memo 12h, tutor late warning, tutor/student no-shows.
- Booking Lifecycle (N2b): confirmed, cancelled, rescheduled, credit granted/expiring.
- Tutor Governance (N2c): vetting outcome, strike issued, tutor suspended.
- System / Operational (N4): Eskom shield alert, refund processed, payment failed.
"""
from apps.bookings.services.classroom_links import classroom_url
from apps.notifications.registry import EMAIL, IN_APP, Kind, Rendered, register
from apps.notifications.rendering import first_name, local_time, one_line, render_html

# --- Kind Name Constants ---
REMINDER_24H = 'reminder_24h'
REMINDER_1H = 'reminder_1h'
REMINDER_10M = 'reminder_10m'
MEMO_REMINDER_12H = 'memo_reminder_12h'
TUTOR_LATE_WARNING = 'tutor_late_warning'
TEACHER_NO_SHOW = 'teacher_no_show'
STUDENT_NO_SHOW = 'student_no_show'

BOOKING_CONFIRMED = 'booking_confirmed'
BOOKING_CANCELLED = 'booking_cancelled'
BOOKING_RESCHEDULED = 'booking_rescheduled'
CREDIT_GRANTED = 'credit_granted'
CREDIT_EXPIRING = 'credit_expiring'

VETTING_OUTCOME = 'vetting_outcome'
STRIKE_ISSUED = 'strike_issued'
TEACHER_SUSPENDED = 'teacher_suspended'

ESKOM_SHIELD_ALERT = 'eskom_shield_alert'
REFUND_PROCESSED = 'refund_processed'
PAYMENT_FAILED = 'payment_failed'


# --- Helper ---
def _resolve_other_and_url(user, booking):
    other_name = 'your lesson partner'
    url = '/student/classroom'
    if booking:
        role = 'teacher' if getattr(booking, 'teacher_id', None) and getattr(booking.teacher, 'user_id', None) == getattr(user, 'id', None) else 'student'
        url = classroom_url(booking, role)
        if user.pk == getattr(booking, 'student_id', None):
            other = getattr(booking.teacher, 'user', None)
        else:
            other = getattr(booking, 'student', None)
        if other:
            other_name = first_name(other)
    return other_name, url


# --- N2a: Reminders ---
def _render_reminder_24h(user, payload, booking):
    other_name, url = _resolve_other_and_url(user, booking)
    name = first_name(user)
    when = local_time(booking.start_time_utc, user) if booking else 'your scheduled time'
    title = one_line('Upcoming lesson in 24 hours')
    subject = one_line(f'Reminder: Your lesson with {other_name} is in 24 hours')
    body = f'Your lesson with {other_name} is scheduled for {when}. Review your materials and verify your time zone.'
    text = (f'Hi {name},\n\nYour lesson with {other_name} is in 24 hours on {when}.\n\n'
            f'Classroom: {url}\n\nPlease check your microphone and camera before class.')
    html = render_html(
        '<p>Hi {name},</p><p>Your lesson with {other} is in 24 hours on <strong>{when}</strong>.</p>'
        '<p><a href="{url}">Go to Classroom</a></p><p>Please check your microphone and camera before class.</p>',
        name=name, other=other_name, when=when, url=url
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_reminder_1h(user, payload, booking):
    other_name, url = _resolve_other_and_url(user, booking)
    name = first_name(user)
    when = local_time(booking.start_time_utc, user) if booking else 'in 1 hour'
    title = one_line('Lesson starting in 1 hour')
    subject = one_line(f'Reminder: Your lesson with {other_name} starts in 1 hour')
    body = f'Your lesson with {other_name} begins at {when}. Please complete the WebRTC hardware check.'
    text = (f'Hi {name},\n\nYour lesson with {other_name} starts in 1 hour at {when}.\n\n'
            f'Classroom: {url}\n\nPlease ensure your audio and video are working properly.')
    html = render_html(
        '<p>Hi {name},</p><p>Your lesson with {other} starts in 1 hour at <strong>{when}</strong>.</p>'
        '<p><a href="{url}">Open Classroom Preview</a></p>'
        '<p>Please test your WebRTC audio and video before class starts.</p>',
        name=name, other=other_name, when=when, url=url
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_reminder_10m(user, payload, booking):
    other_name, url = _resolve_other_and_url(user, booking)
    name = first_name(user)
    title = one_line('Classroom is open (starts in 10 minutes)')
    subject = one_line(f'Classroom Open: Your lesson with {other_name} starts in 10 minutes')
    body = f'Your lesson with {other_name} is starting in 10 minutes. Click to join the classroom now.'
    text = f'Hi {name},\n\nYour lesson with {other_name} begins in 10 minutes.\n\nJoin now: {url}'
    html = render_html(
        '<p>Hi {name},</p><p>Your lesson with {other} starts in 10 minutes.</p>'
        '<p><a href="{url}">Join Classroom Now</a></p>',
        name=name, other=other_name, url=url
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_memo_reminder_12h(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    title = one_line('Lesson memo due within 12 hours')
    subject = one_line('Action Required: Please submit lesson memo')
    body = f'12 hours have passed since lesson {bid}. Please submit the lesson memo before the 24-hour deadline to avoid an SLA breach.'
    text = (f'Hi {name},\n\n12 hours have elapsed since lesson {bid}.\n\n'
            f'Please submit your student feedback memo within the next 12 hours to maintain SLA compliance.')
    html = render_html(
        '<p>Hi {name},</p><p>12 hours have elapsed since lesson <code>{bid}</code>.</p>'
        '<p>Please submit your student feedback memo within the next 12 hours to maintain SLA compliance.</p>',
        name=name, bid=bid
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_tutor_late_warning(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    title = one_line('Tutor delay notice')
    subject = one_line('Lesson Update: Your tutor is delayed')
    body = f'Your tutor has not yet connected for lesson {bid}. Our team is monitoring the room.'
    text = (f'Hi {name},\n\nYour tutor has not yet joined lesson {bid}. '
            f'If the tutor cannot attend within 10 minutes, the lesson will be cancelled with full restitution.')
    html = render_html(
        '<p>Hi {name},</p><p>Your tutor has not joined lesson <code>{bid}</code> yet.</p>'
        '<p>If the tutor cannot attend within 10 minutes, the session will be marked no-show and your account will receive full restitution.</p>',
        name=name, bid=bid
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_teacher_no_show(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    is_tutor = bool(booking and getattr(booking, 'teacher_id', None) and getattr(booking.teacher, 'user_id', None) == getattr(user, 'id', None))
    title = one_line('Tutor no-show recorded')
    if is_tutor:
        subject = one_line('Important: Lesson marked as Tutor No-Show')
        body = f'Lesson {bid} was marked as tutor no-show. An SLA strike has been recorded on your profile.'
        text = f'Hi {name},\n\nYou were marked as absent for lesson {bid}. An SLA strike has been issued in accordance with platform policies.'
        html = render_html(
            '<p>Hi {name},</p><p>You were marked absent for lesson <code>{bid}</code>.</p>'
            '<p>An SLA strike has been issued on your profile in accordance with platform policies.</p>',
            name=name, bid=bid
        )
    else:
        subject = one_line('Notice: Tutor No-Show and Compensation')
        body = f'Your tutor was absent for lesson {bid}. Your payment has been refunded and 1 apology credit was added to your wallet.'
        text = f'Hi {name},\n\nYour tutor was absent for lesson {bid}.\n\nYou have been issued a 100% refund and 1 bonus lesson credit has been added to your wallet.'
        html = render_html(
            '<p>Hi {name},</p><p>Your tutor was absent for lesson <code>{bid}</code>.</p>'
            '<p>You have been issued a 100% refund and 1 bonus lesson credit has been added to your wallet.</p>',
            name=name, bid=bid
        )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_student_no_show(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    is_student = bool(booking and getattr(booking, 'student_id', None) == getattr(user, 'id', None))
    title = one_line('Student no-show recorded')
    if is_student:
        subject = one_line('Notice: Student No-Show Recorded')
        body = f'You were marked absent for lesson {bid}. Lesson fee has been forfeited.'
        text = f'Hi {name},\n\nYou did not attend your lesson {bid}. In accordance with cancellation policies, the lesson fee is forfeited.'
        html = render_html(
            '<p>Hi {name},</p><p>You did not attend lesson <code>{bid}</code>.</p>'
            '<p>In accordance with platform policies, the lesson fee is forfeited.</p>',
            name=name, bid=bid
        )
    else:
        subject = one_line('Lesson Update: Student No-Show')
        body = f'The student was absent for lesson {bid}. Your lesson compensation will be credited normally.'
        text = f'Hi {name},\n\nThe student was absent for lesson {bid}. Your lesson compensation will be disbursed normally.'
        html = render_html(
            '<p>Hi {name},</p><p>The student did not attend lesson <code>{bid}</code>.</p>'
            '<p>Your full tutor compensation will be disbursed normally.</p>',
            name=name, bid=bid
        )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


# --- N2b: Booking Lifecycle ---
def _render_booking_confirmed(user, payload, booking):
    name = first_name(user)
    other_name, url = _resolve_other_and_url(user, booking)
    when = local_time(booking.start_time_utc, user) if booking else 'your scheduled time'
    title = one_line('Lesson confirmed')
    subject = one_line(f'Confirmed: Your lesson with {other_name}')
    body = f'Your 25-minute lesson with {other_name} is confirmed for {when}.'
    text = f'Hi {name},\n\nYour lesson with {other_name} is locked in for {when}.\n\nClassroom: {url}\n\nSee you in class!'
    html = render_html(
        '<p>Hi {name},</p><p>Your 25-minute lesson with <strong>{other}</strong> is locked in for <strong>{when}</strong>.</p>'
        '<p><a href="{url}">Launch Classroom</a></p>',
        name=name, other=other_name, when=when, url=url
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_booking_cancelled(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    cancelled_by = str(payload.get('cancelled_by') or 'student')
    outcome = str(payload.get('refund_outcome') or '')
    when = local_time(booking.start_time_utc, user) if booking else 'the scheduled time'
    title = one_line('Lesson cancelled')
    subject = one_line('Notice: Your lesson has been cancelled')
    body = f'Lesson {bid} on {when} was cancelled.'
    refund_msg = ('A refund has been initiated to your original payment method.'
                  if outcome == 'full_refund' else
                  ('The lesson fee was forfeited per policy.' if outcome == 'fee_forfeited'
                   else 'Please check your account for details.'))
    text = f'Hi {name},\n\nLesson {bid} on {when} was cancelled by {cancelled_by}.\n\n{refund_msg}'
    html = render_html(
        '<p>Hi {name},</p><p>Lesson <code>{bid}</code> on <strong>{when}</strong> was cancelled by {cancelled_by}.</p><p>{refund_msg}</p>',
        name=name, bid=bid, when=when, cancelled_by=cancelled_by, refund_msg=refund_msg
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_booking_rescheduled(user, payload, booking):
    name = first_name(user)
    other_name, url = _resolve_other_and_url(user, booking)
    when = local_time(booking.start_time_utc, user) if booking else 'the new time'
    title = one_line('Lesson rescheduled')
    subject = one_line(f'Rescheduled: Your lesson with {other_name}')
    body = f'Your lesson with {other_name} has been rescheduled to {when}.'
    text = f'Hi {name},\n\nYour lesson with {other_name} was rescheduled to {when}.\n\nClassroom: {url}'
    html = render_html(
        '<p>Hi {name},</p><p>Your lesson with <strong>{other}</strong> was rescheduled to <strong>{when}</strong>.</p>'
        '<p><a href="{url}">Launch Classroom</a></p>',
        name=name, other=other_name, when=when, url=url
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_credit_granted(user, payload, booking):
    name = first_name(user)
    credits = str(payload.get('credits', 1))
    reason = str(payload.get('reason', 'bonus'))
    title = one_line('Lesson credits added')
    subject = one_line(f'{credits} credit(s) added to your wallet')
    body = f'{credits} credit(s) have been added to your Sharon ESL wallet (reason: {reason}).'
    text = f'Hi {name},\n\n{credits} lesson credit(s) were added to your Sharon ESL wallet for {reason}.'
    html = render_html(
        '<p>Hi {name},</p><p><strong>{credits}</strong> lesson credit(s) have been credited to your wallet (reason: {reason}).</p>',
        name=name, credits=credits, reason=reason
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_credit_expiring(user, payload, booking):
    name = first_name(user)
    credits = str(payload.get('credits', 1))
    days = str(payload.get('days_remaining', 7))
    title = one_line('Credits expiring soon')
    subject = one_line(f'Reminder: Your Sharon ESL credits expire in {days} days')
    body = f'{credits} lesson credit(s) in your wallet will expire in {days} days. Book your lessons soon!'
    text = f'Hi {name},\n\nYou have {credits} lesson credit(s) that will expire in {days} days. Please book your lessons before expiry.'
    html = render_html(
        '<p>Hi {name},</p><p>You have <strong>{credits}</strong> lesson credit(s) that will expire in {days} days.</p>'
        '<p>Please book your lessons before expiry.</p>',
        name=name, credits=credits, days=days
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


# --- N2c: Tutor Governance ---
def _render_vetting_outcome(user, payload, booking):
    name = first_name(user)
    status = str(payload.get('status', 'approved'))
    title = one_line('Application status update')
    if status == 'approved':
        subject = one_line('Welcome! Your Sharon ESL tutor application has been approved')
        body = 'Congratulations! Your tutor application was approved. You can now configure your schedule and accept bookings.'
        text = f'Hi {name},\n\nCongratulations! Your tutor application on Sharon ESL has been approved. You can now set your teaching availability.'
        html = render_html(
            '<p>Hi {name},</p><p>Congratulations! Your tutor application has been <strong>approved</strong>.</p>'
            '<p>You can now log in, configure your availability, and accept student bookings.</p>',
            name=name
        )
    elif status == 'changes_requested':
        subject = one_line('Action Required: Changes requested on your tutor application')
        body = 'The review team requested adjustments to your application materials. Please check your dashboard.'
        text = f'Hi {name},\n\nOur review team requested changes to your tutor application. Please review the feedback on your dashboard and re-submit.'
        html = render_html(
            '<p>Hi {name},</p><p>Our review team requested changes to your application materials.</p>'
            '<p>Please sign in to view the requested adjustments and resubmit.</p>',
            name=name
        )
    else:
        subject = one_line('Update regarding your Sharon ESL tutor application')
        body = 'Thank you for applying. We are unable to proceed with your application at this time.'
        text = f'Hi {name},\n\nThank you for your interest in Sharon ESL. We are unable to move forward with your application at this time.'
        html = render_html(
            '<p>Hi {name},</p><p>Thank you for applying to Sharon ESL. We are unable to move forward with your application at this time.</p>',
            name=name
        )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_strike_issued(user, payload, booking):
    name = first_name(user)
    kind = str(payload.get('strike_kind', 'sla'))
    total = str(payload.get('total_strikes', 1))
    title = one_line('SLA strike recorded')
    subject = one_line('Important: An SLA strike was recorded on your tutor account')
    body = f'A strike ({kind}) was recorded. You have {total} active strike(s) within the 90-day window (threshold: 3).'
    text = (f'Hi {name},\n\nAn SLA strike ({kind}) was recorded on your account. '
            f'You now have {total} active strike(s). Accumulating 3 strikes within 90 days results in account suspension.')
    html = render_html(
        '<p>Hi {name},</p><p>An SLA strike (<code>{kind}</code>) was recorded on your account.</p>'
        '<p>You now have <strong>{total}</strong> active strike(s). Accumulating 3 strikes results in account suspension.</p>',
        name=name, kind=kind, total=total
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_teacher_suspended(user, payload, booking):
    name = first_name(user)
    reason = str(payload.get('reason', 'policy'))
    title = one_line('Tutor account suspended')
    subject = one_line('Important Notice: Your Sharon ESL tutor account has been suspended')
    body = f'Your tutor account has been suspended (reason: {reason}). Please contact support for assistance.'
    text = f'Hi {name},\n\nYour tutor account has been suspended due to: {reason}.\n\nPlease contact support if you believe this is in error.'
    html = render_html(
        '<p>Hi {name},</p><p>Your tutor account has been suspended due to: <strong>{reason}</strong>.</p>'
        '<p>Please contact support if you need assistance or wish to appeal.</p>',
        name=name, reason=reason
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


# --- N4: Operational & Financial ---
def _render_eskom_shield_alert(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    area = str(payload.get('area_name') or 'your area')
    when = local_time(booking.start_time_utc, user) if booking else 'your lesson time'
    title = one_line('Power Guard load-shedding alert')
    subject = one_line('Power Guard Alert: Potential Outage Overlap')
    body = f'An Eskom outage reported for {area} overlaps lesson {bid} on {when}.'
    text = (f'Hi {name},\n\nPower Guard detected an Eskom load-shedding outage window for {area} '
            f'overlapping your upcoming lesson on {when}.\n\nPlease verify your power backup connectivity.')
    html = render_html(
        '<p>Hi {name},</p><p>Power Guard detected a load-shedding outage for <strong>{area}</strong> '
        'overlapping your lesson on <strong>{when}</strong>.</p><p>Please ensure backup power and internet are ready.</p>',
        name=name, area=area, when=when
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_refund_processed(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    amount = str(payload.get('amount') or '')
    currency = str(payload.get('currency') or 'USD')
    amt_str = f'{amount} {currency}'.strip()
    title = one_line('Refund processed')
    subject = one_line('Refund Processed: Sharon ESL')
    body = f'A refund of {amt_str} for lesson {bid} has been processed.'
    text = f'Hi {name},\n\nA refund of {amt_str} for lesson {bid} has been processed to your original payment method.'
    html = render_html(
        '<p>Hi {name},</p><p>A refund of <strong>{amt}</strong> for lesson <code>{bid}</code> '
        'has been processed to your original payment method.</p>',
        name=name, amt=amt_str, bid=bid
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


def _render_payment_failed(user, payload, booking):
    name = first_name(user)
    bid = str(payload.get('booking_id') or (booking.pk if booking else ''))
    title = one_line('Payment unsuccessful')
    subject = one_line('Payment Failed: Lesson Reservation')
    body = f'Payment could not be processed for lesson {bid}. The reservation hold has been released.'
    text = (f'Hi {name},\n\nWe could not process payment for lesson {bid}. '
            'The provisional reservation has expired. Please retry with a valid payment method.')
    html = render_html(
        '<p>Hi {name},</p><p>We were unable to process the payment for lesson <code>{bid}</code>.</p>'
        '<p>The reservation hold has expired. Please book again with a valid payment method.</p>',
        name=name, bid=bid
    )
    return Rendered(subject=subject, html=html, text=text, title=title, body=body)


# --- Example Builders ---
def _ex_booking(booking):
    return {'booking_id': str(booking.pk)}


def _ex_booking_cancelled(booking):
    return {'booking_id': str(booking.pk), 'cancelled_by': 'student', 'refund_outcome': 'full_refund'}


def _ex_credit_granted(booking):
    return {'credits': 1, 'reason': 'bonus'}


def _ex_credit_expiring(booking):
    return {'credits': 1, 'days_remaining': 7}


def _ex_vetting(booking):
    return {'status': 'approved'}


def _ex_strike(booking):
    return {'strike_kind': 'no_show', 'total_strikes': 1}


def _ex_suspended(booking):
    return {'reason': 'strike_limit'}


def _ex_eskom(booking):
    return {'booking_id': str(booking.pk), 'area_name': 'Cape Town Area 7'}


def _ex_refund(booking):
    return {'booking_id': str(booking.pk), 'amount': '25.00', 'currency': 'USD'}


def _not_after_start(payload, booking):
    return booking.start_time_utc if booking else None


# --- Registration ---
register(Kind(REMINDER_24H, 'reminder', frozenset({EMAIL, IN_APP}), _render_reminder_24h, _ex_booking, not_after=_not_after_start))
register(Kind(REMINDER_1H, 'reminder', frozenset({EMAIL, IN_APP}), _render_reminder_1h, _ex_booking, not_after=_not_after_start))
register(Kind(REMINDER_10M, 'reminder', frozenset({EMAIL, IN_APP}), _render_reminder_10m, _ex_booking, not_after=_not_after_start))
register(Kind(MEMO_REMINDER_12H, 'reminder', frozenset({EMAIL, IN_APP}), _render_memo_reminder_12h, _ex_booking))
register(Kind(TUTOR_LATE_WARNING, 'reminder', frozenset({EMAIL, IN_APP}), _render_tutor_late_warning, _ex_booking))
register(Kind(TEACHER_NO_SHOW, 'strike', frozenset({EMAIL, IN_APP}), _render_teacher_no_show, _ex_booking))
register(Kind(STUDENT_NO_SHOW, 'cancellation', frozenset({EMAIL, IN_APP}), _render_student_no_show, _ex_booking))

register(Kind(BOOKING_CONFIRMED, 'booking', frozenset({EMAIL, IN_APP}), _render_booking_confirmed, _ex_booking))
register(Kind(BOOKING_CANCELLED, 'cancellation', frozenset({EMAIL, IN_APP}), _render_booking_cancelled, _ex_booking_cancelled))
register(Kind(BOOKING_RESCHEDULED, 'booking', frozenset({EMAIL, IN_APP}), _render_booking_rescheduled, _ex_booking))
register(Kind(CREDIT_GRANTED, 'credit', frozenset({EMAIL, IN_APP}), _render_credit_granted, _ex_credit_granted))
register(Kind(CREDIT_EXPIRING, 'credit', frozenset({EMAIL, IN_APP}), _render_credit_expiring, _ex_credit_expiring))

register(Kind(VETTING_OUTCOME, 'vetting_outcome', frozenset({EMAIL, IN_APP}), _render_vetting_outcome, _ex_vetting))
register(Kind(STRIKE_ISSUED, 'strike', frozenset({EMAIL, IN_APP}), _render_strike_issued, _ex_strike))
register(Kind(TEACHER_SUSPENDED, 'suspension', frozenset({EMAIL, IN_APP}), _render_teacher_suspended, _ex_suspended))

register(Kind(ESKOM_SHIELD_ALERT, 'system', frozenset({EMAIL, IN_APP}), _render_eskom_shield_alert, _ex_eskom))
register(Kind(REFUND_PROCESSED, 'refund', frozenset({EMAIL, IN_APP}), _render_refund_processed, _ex_refund))
register(Kind(PAYMENT_FAILED, 'payment', frozenset({EMAIL, IN_APP}), _render_payment_failed, _ex_booking))
