"""
Vetting rubric and review-integrity checks (slice T4a, docs/TUTOR_STATUS_MACHINE.md §12).

    CRITERIA                                      the four scored criteria (provisional, D-11)
    check_approval(teacher, rubric, reviewed_assets) -> (stored_rubric, stored_assets)     raises RubricError / AssetReviewError
    check_requested_changes(kinds) -> list

Approval needs (1) a rubric with every criterion scored 1..5 and none below VETTING_MIN_RUBRIC_SCORE, (2) every kind in
VETTING_REQUIRED_ASSET_KINDS committed, and (3) proof that the reviewer saw exactly the assets that are live now:
`reviewed_assets` ({kind: etag}) must equal the tutor's current, not-replaced assets. A tutor who swaps a file while a
reviewer has the old one open therefore cannot be approved on content nobody looked at. Scores are staff-only (they are
never serialised to the tutor); the tutor sees the reason and the requested changes.
"""
from django.conf import settings

from apps.teachers.models import TeacherAsset
from apps.teachers.vetting import VettingError

CRITERIA = ('pronunciation', 'teaching_presence', 'professionalism', 'credentials')
SCALE = (1, 5)


class RubricError(VettingError):
    http_status = 400

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class AssetReviewError(VettingError):
    http_status = 409

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def min_score() -> int:
    return int(getattr(settings, 'VETTING_MIN_RUBRIC_SCORE', 3))


def _validate_scores(rubric):
    if rubric is None or rubric == {}:
        raise RubricError('rubric_required', 'A rubric (one score per criterion) is required to approve a tutor.')
    if not isinstance(rubric, dict) or set(rubric) != set(CRITERIA):
        raise RubricError('rubric_invalid', f'The rubric needs exactly these criteria: {", ".join(CRITERIA)}.')
    for name in CRITERIA:
        value = rubric[name]
        if type(value) is not int or not SCALE[0] <= value <= SCALE[1]:    # bool and float are not scores
            raise RubricError('rubric_invalid', f'{name} must be a whole number from {SCALE[0]} to {SCALE[1]}.')
    low = [name for name in CRITERIA if rubric[name] < min_score()]
    if low:
        raise RubricError('rubric_below_threshold',
                          f'Every criterion must score at least {min_score()}; below that: {", ".join(low)}.')
    return {name: rubric[name] for name in CRITERIA}


def current_assets(teacher) -> dict:
    return dict(TeacherAsset.objects.filter(teacher=teacher, replaced_at__isnull=True).values_list('kind', 'etag'))


def check_approval(teacher, rubric, reviewed_assets):
    scores = _validate_scores(rubric)
    live = current_assets(teacher)
    missing = [kind for kind in getattr(settings, 'VETTING_REQUIRED_ASSET_KINDS', ()) if kind not in live]
    if missing:
        raise RubricError('required_assets_missing', f'Required uploads are missing: {", ".join(missing)}.')
    if live:
        if not reviewed_assets:
            raise AssetReviewError('assets_review_required',
                                   'Report the uploads you reviewed (reviewed_assets) to approve a tutor who has uploads.')
        if dict(reviewed_assets) != live:
            raise AssetReviewError('assets_changed',
                                   'The tutor\'s uploads changed since you opened them: review the current files again.')
    return {'version': 1, 'scores': scores}, live


def check_requested_changes(kinds) -> list:
    kinds = [] if kinds is None else kinds
    if not isinstance(kinds, list) or len(kinds) > len(TeacherAsset.Kind.values) or not all(
            isinstance(k, str) and k in TeacherAsset.Kind.values for k in kinds):
        raise RubricError('invalid_requested_changes',
                          f'requested_changes must be a list of: {", ".join(TeacherAsset.Kind.values)}.')
    return list(dict.fromkeys(kinds))
