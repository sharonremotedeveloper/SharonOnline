"""Notification kinds: one registered template per kind (slice N1a, docs/NOTIFICATIONS.md §2).

A kind names its category (which decides whether it is mandatory), its channels, a renderer and an example payload builder
(used by the hostile-data template test and the golden-snapshot guard). The renderer gets the recipient, the ids-only
payload and the booking (or None) and fetches anything else it needs itself, so no private text travels in a payload.
"""
import re
from dataclasses import dataclass
from typing import Callable, Optional

EMAIL, IN_APP = 'email', 'in_app'
CHANNELS = frozenset({EMAIL, IN_APP})

# The mandatory set lives in code (plan §3.2): a user preference can never switch off the e-mail of these categories.
# `staff_alert` is added so a staff member cannot mute operational alerts by preference.
MANDATORY_CATEGORIES = frozenset({
    'security', 'payment', 'cancellation', 'refund', 'bank_change', 'strike', 'suspension', 'vetting_outcome',
    'staff_alert',
})
OPTIONAL_CATEGORIES = frozenset({'booking', 'reminder', 'credit', 'account', 'calendar', 'system'})
CATEGORIES = MANDATORY_CATEGORIES | OPTIONAL_CATEGORIES
_NAME = re.compile(r'[a-z][a-z0-9_]{1,63}')


class UnknownKind(KeyError):
    """notify() was called with a kind nobody registered (a programming error)."""


@dataclass(frozen=True)
class Rendered:
    subject: str        # one line, <= 200 characters (rendering.one_line)
    html: str           # built with integrations.services.email.render_html: every value escaped
    text: str
    title: str          # in-app title (one line)
    body: str           # in-app body (plain text; the frontend escapes on display)


@dataclass(frozen=True)
class Kind:
    name: str
    category: str
    channels: frozenset
    render: Callable            # (user, payload: dict, booking | None) -> Rendered
    example: Optional[Callable] = None     # (booking) -> payload, for the template tests / golden snapshot
    # (payload, booking | None) -> aware datetime | None. From that instant on the e-mail is no longer worth sending (a
    # reminder after the lesson started): delivery marks the row `skipped` / `expired` instead of sending or retrying.
    not_after: Optional[Callable] = None

    @property
    def mandatory(self) -> bool:
        return self.category in MANDATORY_CATEGORIES

    @property
    def email_only(self) -> bool:
        return self.channels == frozenset({EMAIL})


_REGISTRY: dict = {}


def register(kind: Kind) -> Kind:
    if not _NAME.fullmatch(kind.name):
        raise ValueError(f'notification kind name {kind.name!r} must be snake_case')
    if kind.name in _REGISTRY:
        raise ValueError(f'notification kind {kind.name!r} is already registered')
    if not kind.channels or not set(kind.channels) <= CHANNELS:
        raise ValueError(f'notification kind {kind.name!r}: channels must be a non-empty subset of {sorted(CHANNELS)}')
    if kind.category not in CATEGORIES:
        raise ValueError(f'notification kind {kind.name!r}: unknown category {kind.category!r}')
    _REGISTRY[kind.name] = kind
    return kind


def get(name: str) -> Kind:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownKind(name) from None


def all_kinds() -> list:
    return list(_REGISTRY.values())
