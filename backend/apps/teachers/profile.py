"""
The tutor's own profile (slice T1c, `GET|PATCH /api/v1/teachers/me/`; docs/TUTOR_STATUS_MACHINE.md §8).

Field classes (every concrete TeacherProfile field is in exactly one; tests/test_t1c_tutor_profile.py checks the split):

* WRITABLE_FIELDS - what the tutor may edit here. Text a reviewer does not sign off: headline, bio, specialties.
* VETTED_FIELDS - what vetting reviews (plan §3.1, INV TEA-11): accent, intro video, accent audio, TEFL certificate, photo.
  Never writable here; they change only through the T3 upload/commit flow, which must call `revet_after_vetted_change`.
* Everything else is service-owned (status, sla_strikes, training_completed_at), staff-owned (eskom_area_id: it drives the
  Eskom shield that waives strikes, so a tutor must not pick their own area), derived (ratings) or deprecated (price).
  Power backup has its own endpoint (`profile/power-backup/`).

`update_own_profile` writes with an explicit `update_fields` (only the changed whitelisted fields + updated_at), so it can
never write `status` / `sla_strikes` back from a stale copy and two concurrent edits of different fields do not clobber
each other. No row lock is needed for that.
"""
import logging

from apps.teachers import vetting
from apps.teachers.models import TeacherProfile

logger = logging.getLogger(__name__)

WRITABLE_FIELDS = ('headline', 'bio', 'specialties')
# The rest of the partition (tests/test_t1c_tutor_profile.py checks every concrete TeacherProfile column is in exactly one
# class, so a new column forces a decision here).
IDENTITY_FIELDS = ('id', 'user', 'created_at', 'updated_at')
SERVICE_OWNED_FIELDS = ('status', 'sla_strikes', 'training_completed_at')   # written only by vetting.py / strikes.py / T6
STAFF_OWNED_FIELDS = ('eskom_area_id',)                                      # drives the strike waiver: not self-selectable
DERIVED_FIELDS = ('rating_avg', 'rating_count', 'is_verified', 'is_active')  # computed (reviews) / generated from status
SELF_DECLARED_ELSEWHERE_FIELDS = ('has_inverter_backup', 'has_lte_failover')  # PATCH /teachers/profile/power-backup/
DEPRECATED_FIELDS = ('price_per_25min_usd',)                                 # platform catalog price since Task 10.1
VETTED_FIELDS = (
    'accent', 'intro_video_url', 'intro_video_thumbnail', 'intro_audio_file', 'intro_audio_url',
    'tefl_certificate_file', 'tefl_certificate_url', 'avatar_image', 'avatar_url',
)


def update_own_profile(profile: TeacherProfile, changes: dict) -> list[str]:
    """Apply whitelisted `changes`; returns the names actually changed (nothing is written when none did)."""
    illegal = set(changes) - set(WRITABLE_FIELDS)
    if illegal:
        raise ValueError(f'Not writable through /teachers/me/: {sorted(illegal)}')
    changed = [name for name in WRITABLE_FIELDS if name in changes and getattr(profile, name) != changes[name]]
    if not changed:
        return []
    for name in changed:
        setattr(profile, name, changes[name])
    profile.save(update_fields=[*changed, 'updated_at'])
    logger.info('tutor %s updated own profile fields %s', profile.pk, changed)
    return changed


def revet_after_vetted_change(profile: TeacherProfile, *, actor, fields):
    """
    Hook for T3 (vetted-asset commit): an approved tutor whose video / accent / documents changed goes back to review
    (`approved -> in_review`, INV TEA-11), so content swapped after approval is never shown unreviewed. Tutors not yet live
    are left alone (their next submission is reviewed anyway). Returns the TeacherTransitionResult, or None when nothing
    was due. A suspended / rejected tutor is left alone too; T3 decides whether such commits are allowed at all (plan §3.1:
    commits only while `applied` / `changes_requested`, re-vet for approved tutors).
    """
    profile.refresh_from_db(fields=['status'])
    if profile.status != TeacherProfile.Status.APPROVED:
        return None
    reason = 're-vet: ' + ', '.join(sorted(fields)) + ' changed'
    return vetting.transition_teacher(profile, TeacherProfile.Status.IN_REVIEW, actor=actor, reason=reason)
