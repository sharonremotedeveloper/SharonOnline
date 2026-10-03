"""Plain-wording messages for a pending PayPal payment that failed (Task 10.2 failure runbook, plan P-4)."""
from django.conf import settings
from django.utils.html import escape

from apps.common.money import money_str


def _amount(tx) -> str:
    return f"{money_str(tx.amount, tx.currency)} {tx.currency}"


def _lesson(tx) -> str:
    booking = tx.booking if tx.booking_id else None
    if booking is None:
        return ''
    return f"{booking.start_time_utc:%A %d %B %Y at %H:%M} UTC"


# kind -> what happened, in words a student can act on
def _body_lines(tx, kind: str) -> list[str]:
    amount, lesson = _amount(tx), _lesson(tx)
    if kind == 'cancelled':
        return [f"PayPal could not complete your payment of {amount} for the lesson on {lesson}.",
                "Because the payment did not go through, that lesson has been cancelled and its time is free again.",
                "We have not collected any money from you for it. If you would still like a lesson, you are welcome to book again."]
    if kind == 'absorbed':
        return [f"Your lesson on {lesson} took place, but PayPal could not complete your payment of {amount}.",
                "Please get in touch so that we can settle this together. Until it is sorted out we have paused new bookings on your account.",
                "Reply to this e-mail or contact support and we will help you."]
    if kind == 'pack':
        return [f"PayPal could not complete your payment of {amount} for your lesson credits.",
                "No credits were added to your account and you have not been charged by us. You are welcome to try again."]
    if kind == 'already_cancelled':
        return [f"PayPal could not complete your payment of {amount} for the lesson on {lesson}.",
                "You had already cancelled that lesson, so nothing further is needed and you have not been charged by us."]
    return [f"PayPal could not complete your payment of {amount} for the lesson on {lesson}.",
            "Your booking was not confirmed. If you would still like a lesson, you are welcome to book again with another payment method."]


def ticket_subject_and_message(tx, kind: str) -> tuple[str, str]:
    subject = f"Payment problem: {_amount(tx)}"
    message = "\n".join(_body_lines(tx, kind) + [
        "", f"(Opened automatically. Outcome: {kind}. PayPal reference {tx.gateway_reference}; pending reason {tx.pending_reason or 'n/a'}.)"])
    return subject, message


def student_email(user, tx, kind: str, ticket_id: str) -> tuple[str, str, str]:
    """(subject, html, text) of the e-mail the student receives."""
    name = user.first_name or user.username
    lines = _body_lines(tx, kind)
    support = settings.SUPPORT_TO_EMAIL
    ticket = f"Support request #{ticket_id[:8]} has been opened for you; you can reply to this e-mail or write to {support}."
    text = f"Hi {name},\n\n" + "\n\n".join(lines) + f"\n\n{ticket}\n\nSharon Online"
    html = (f"<p>Hi {escape(name)},</p>" + "".join(f"<p>{escape(line)}</p>" for line in lines)
            + f"<p>{escape(ticket)}</p><p>Sharon Online</p>")
    return "There was a problem with your payment", html, text
