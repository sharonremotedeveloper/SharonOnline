"""The kinds N1a ships: the staff alert and one sample kind that exercises the machinery (real events: N2a-c, N4).

How to add a kind: docs/NOTIFICATIONS.md §2.6.
"""
from apps.notifications.registry import EMAIL, IN_APP, Kind, Rendered, register
from apps.notifications.rendering import first_name, local_time, one_line, render_html

ADMIN_ALERT = 'admin_alert'
SAMPLE_LESSON_NOTICE = 'sample_lesson_notice'

# Staff alert codes -> title. The payload carries ids and short codes only; the renderer lists them.
ALERT_TITLES = {
    'fulfilment_failed': 'Lesson fulfilment failed (no classroom / calendar / confirmation)',
    'fulfilment_needs_attention': 'Lesson fulfilment still failing at the attempt cap',
    'orphaned_calendar_event': 'Orphaned tutor calendar event must be deleted by hand',
    'lesson_disputed_without_verdict': 'Lesson disputed without an attendance verdict',
    'notification_failed': 'A notification e-mail could not be delivered',
    'vetting_submitted': 'A tutor submitted their application for review',
    'tutor_late': 'Tutor is 5+ minutes late for scheduled lesson',
}


def _render_admin_alert(user, payload, booking):
    alert = str(payload.get('alert', ''))
    title = one_line(ALERT_TITLES.get(alert, 'Staff alert'))
    details = [(str(k), str(v)) for k, v in payload.items() if k != 'alert']
    text_lines = [f'{k}: {v}' for k, v in details]
    items = ''.join(render_html('<li>{k}: <code>{v}</code></li>', k=k, v=v) for k, v in details)
    html = render_html('<p>{title}</p>', title=title) + f'<ul>{items}</ul>' + render_html(
        '<p>Alert code: <code>{alert}</code>. See docs/RUNBOOK_NOTIFICATIONS.md.</p>', alert=alert)
    text = '\n'.join([title, *text_lines, f'Alert code: {alert}. See docs/RUNBOOK_NOTIFICATIONS.md.'])
    return Rendered(subject=one_line(f'[Sharon admin] {title}'), html=html, text=text, title=title,
                    body='\n'.join(text_lines))


def _example_admin_alert(booking):
    return {'alert': 'fulfilment_failed', 'booking_id': str(booking.pk), 'step': 'room'}


def _render_sample(user, payload, booking):
    """'Your lesson with X on <local time>': the other party's first name, escaped; the time in the recipient's zone."""
    other = booking.teacher.user if user.pk == booking.student_id else booking.student
    when = local_time(booking.start_time_utc, user)
    name, other_name = first_name(user), first_name(other)
    title = one_line(f'Lesson with {other_name}')
    text = f'Hi {name},\n\nYour lesson with {other_name} is on {when}.\n'
    html = render_html('<p>Hi {name},</p><p>Your lesson with {other} is on {when}.</p>', name=name, other=other_name,
                       when=when)
    return Rendered(subject=one_line(f'Your lesson with {other_name}'), html=html, text=text, title=title,
                    body=f'Your lesson with {other_name} is on {when}.')


def _example_sample(booking):
    return {'booking_id': str(booking.pk)}


register(Kind(ADMIN_ALERT, 'staff_alert', frozenset({EMAIL, IN_APP}), _render_admin_alert, _example_admin_alert))
register(Kind(SAMPLE_LESSON_NOTICE, 'booking', frozenset({EMAIL, IN_APP}), _render_sample, _example_sample))


# --- Payout kinds (Package A, slices P1b/P1c): payloads carry ids only; amounts are read from the tutor's own line. -------------
PAYOUT_PAID = 'payout_paid'
PAYOUT_RETURNED = 'payout_returned'
BANK_DETAILS_CHANGED = 'bank_details_changed'
_NO_LINE = '00000000-0000-4000-8000-000000000000'


def _payout_line(user, payload):
    """The tutor's OWN payout line, or None (a stranger's id, a deleted row, an example payload): nothing else is shown."""
    from apps.admin_api.models import PayoutBatchLine
    return (PayoutBatchLine.objects.select_related('batch').filter(pk=str(payload.get('line_id', _NO_LINE)),
                                                                    teacher__user=user).first())


def _payout_message(user, payload, *, subject, headline, detail):
    from apps.common.money import money_str
    line = _payout_line(user, payload)
    amount = f'R{money_str(line.amount_zar, "ZAR")}' if line else 'your payout'
    ref = f' (batch {line.batch.batch_reference})' if line else ''
    name = first_name(user)
    body = f'{headline.format(amount=amount)}{ref}. {detail}'
    text = f'Hi {name},\n\n{body}\n'
    html = render_html('<p>Hi {name},</p><p>{body}</p>', name=name, body=body)
    return Rendered(subject=one_line(subject), html=html, text=text, title=one_line(subject), body=body)


def _render_payout_paid(user, payload, booking):
    return _payout_message(
        user, payload, subject='Your Sharon ESL payout was sent',
        headline='We have paid {amount} to your bank account',
        detail='It can take up to two working days to show. The statement is in your earnings wallet.')


def _render_payout_returned(user, payload, booking):
    return _payout_message(
        user, payload, subject='Your Sharon ESL payout was returned by the bank',
        headline='The bank returned {amount}',
        detail='The money is back in your earnings balance. Check your bank details in payout settings; it is paid again in the next run.')


def _render_bank_details_changed(user, payload, booking):
    name = first_name(user)
    body = ('Your payout bank details were created or changed. Payouts are held for 72 hours after a change. '
            'If this was not you, change your password and contact support now.')
    return Rendered(subject='Your Sharon ESL payout bank details changed',
                    html=render_html('<p>Hi {name},</p><p>{body}</p>', name=name, body=body),
                    text=f'Hi {name},\n\n{body}\n', title='Payout bank details changed', body=body)


def _example_payout(booking):
    return {'line_id': _NO_LINE}


def _example_bank_change(booking):
    return {'tutor_id': str(booking.teacher.user_id)}


register(Kind(PAYOUT_PAID, 'payment', frozenset({EMAIL, IN_APP}), _render_payout_paid, _example_payout))
register(Kind(PAYOUT_RETURNED, 'payment', frozenset({EMAIL, IN_APP}), _render_payout_returned, _example_payout))
register(Kind(BANK_DETAILS_CHANGED, 'bank_change', frozenset({EMAIL, IN_APP}), _render_bank_details_changed,
              _example_bank_change))
