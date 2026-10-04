"""
Guard (a): `TeacherProfile.is_verified` / `is_active` / `status` are written only by the tutor status service.

Plan §3.1: `status` becomes the only stored column and `is_verified` / `is_active` become GeneratedFields; the one writer is
`teachers/vetting.py::transition_teacher` (slice T1a). Until then the sites below write the booleans directly.

How to shrink: when a site is routed through the service, lower (or delete) its count here. T1a empties this dict and adds
`teachers/vetting.py` (+ the data migration, which is excluded anyway) to ALLOWED_WRITERS.
"""
import ast
import re

from guards._scan import APPS, parse, ratchet_errors, rel, scan, src

FIELDS = {'is_verified', 'is_active', 'status'}
# The service that owns the transitions (does not exist until T1a).
ALLOWED_WRITERS = {'teachers/vetting.py'}
# Baseline 2026-10-04: {file: number of direct writes}. Only ever lower these numbers.
ALLOWLIST = {
    'admin_api/views.py': 2,                              # VerifyTeacherView sets is_verified / is_active (T1b rewrite)
    'teachers/strikes.py': 2,                             # add_strike deactivates (-> suspended in T1a)
    'users/management/commands/seed_data.py': 2,          # seeds (-> factory/status in T1a)
    'users/management/commands/seed_phase41_data.py': 2,
}
WRITE_METHODS = {'create', 'update', 'get_or_create', 'update_or_create', 'bulk_create'}
TEACHERISH = ('teacher', 'profile', 'tutor')
NON_TEACHER_RECEIVER = re.compile(r'user|availab|pack|price|bundle|slot', re.IGNORECASE)


def _is_teacher_receiver(text):
    low = text.lower()
    return any(word in low for word in TEACHERISH)


def _attr_targets(target):
    if isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _attr_targets(elt)
    elif isinstance(target, ast.Attribute):
        yield target


def _attribute_write(target):
    """
    `x.is_verified = ...`: any receiver (only TeacherProfile has the field).
    `x.is_active = ...`: any receiver except ones that are clearly another model (User, availability, packs, prices), because
        tutor rows are often held in neutral names (`locked`, `profile`).
    `x.status = ...`: only teacher-looking receivers (every other model has a `status`; T1a's own guard is stricter).
    """
    if target.attr == 'is_verified':
        return True
    if target.attr == 'is_active':
        return not NON_TEACHER_RECEIVER.search(src(target.value))
    return target.attr == 'status' and _is_teacher_receiver(src(target.value))


def _assignment_hits(node):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [f'{node.lineno}: {src(attr)} = ...' for target in targets for attr in _attr_targets(target) if _attribute_write(attr)]


def _setattr_hits(node):
    if not (isinstance(node.func, ast.Name) and node.func.id == 'setattr' and len(node.args) >= 2):
        return []
    name = node.args[1]
    if isinstance(name, ast.Constant) and name.value in FIELDS and (
            name.value == 'is_verified' or _is_teacher_receiver(src(node.args[0]))):
        return [f'{node.lineno}: setattr({src(node.args[0])}, {name.value!r}, ...)']
    return []


def _orm_write_hits(node):
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS and 'TeacherProfile' in src(func.value)):
        return []
    hits = [f'{node.lineno}: {func.attr}({kw.arg}=...)' for kw in node.keywords if kw.arg in FIELDS]
    for kw in node.keywords:
        if kw.arg in ('defaults', 'create_defaults') and isinstance(kw.value, ast.Dict):
            hits += [f'{node.lineno}: {func.attr}({kw.arg}={{{key.value!r}: ...}})' for key in kw.value.keys
                     if isinstance(key, ast.Constant) and key.value in FIELDS]
    return hits


def teacher_status_writes(path):
    hits = []
    for node in ast.walk(parse(path)):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            hits += _assignment_hits(node)
        elif isinstance(node, ast.Call):
            hits += _setattr_hits(node) + _orm_write_hits(node)
    return hits


def _found(root=APPS):
    found = scan(teacher_status_writes, root)
    return {path: sites for path, sites in found.items() if path not in ALLOWED_WRITERS}


def test_teacher_status_is_written_only_by_the_service_or_the_baseline():
    errors = ratchet_errors(_found(), ALLOWLIST)
    assert not errors, 'Route TeacherProfile status writes through teachers/vetting.py::transition_teacher (T1a):\n' + '\n'.join(errors)


def test_detector_catches_every_write_shape(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "profile.is_verified = True\n"
        "locked.is_active = False\n"
        "teacher.sla_strikes, teacher.is_active = 1, False\n"
        "locked_profile.status = 'approved'\n"
        "setattr(teacher, 'is_active', False)\n"
        "TeacherProfile.objects.filter(pk=1).update(is_verified=True)\n"
        "TeacherProfile.objects.get_or_create(user=u, defaults={'is_active': True, 'bio': ''})\n"
        "TeacherProfile.objects.create(user=u, status='approved')\n",
        encoding='utf-8')
    assert len(teacher_status_writes(bad)) == 8


def test_detector_ignores_reads_and_other_models(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "user.is_active = False\n"                      # User.is_active is Django auth, not the tutor
        "booking.status = 'x'\n"
        "TeacherProfile.objects.filter(is_verified=True, is_active=True)\n"
        "TeacherAvailability.objects.get_or_create(teacher=p, defaults={'is_active': True})\n"
        "is_verified = serializers.BooleanField()\n",
        encoding='utf-8')
    assert teacher_status_writes(ok) == []


def test_detector_catches_the_qa_probes(tmp_path):
    """QA review of Q0 (MAJOR 1): shapes the first detector missed."""
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "request.user.teacher_profile.is_active = False\n"          # 'user' in the chain, but it ends in a tutor
        "qs.update(is_verified=True)\n"                              # update on any receiver
        "TeacherProfile.objects.filter(pk=1).update(**{'is_active': False})\n"
        "TeacherProfile.objects.bulk_update(ps, ['is_active'])\n"
        "TeacherProfile.objects.bulk_update(ps, fields=['status'])\n"
        "qs.update(is_active=False)\n"                               # unknown receiver: is_active is assumed a tutor
        "class TeacherProfile(models.Model):\n"
        "    def suspend(self):\n"
        "        self.status = 'suspended'\n"
        "        self.is_active = False\n",
        encoding='utf-8')
    assert len(teacher_status_writes(bad)) == 8


def test_detector_ignores_other_models_writing_the_same_names(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "TeacherAvailability.objects.filter(teacher=t).update(is_active=False)\n"
        "teacher.availabilities.update(is_active=False)\n"
        "User.objects.bulk_update(users, ['is_active'])\n"
        "CreditPack.objects.update(is_active=False)\n"
        "LessonPrice.objects.filter(currency='USD').update(is_active=False)\n"
        "Booking.objects.filter(pk=1).update(status='x')\n"
        "qs.update(status='x')\n"                                    # status on an unknown receiver: not a tutor
        "class Booking(models.Model):\n"
        "    def x(self):\n"
        "        self.status = 'y'\n"
        "class TeacherAvailability(models.Model):\n"
        "    def off(self):\n"
        "        self.is_active = False\n",
        encoding='utf-8')
    assert teacher_status_writes(ok) == []


def test_ratchet_fails_on_a_new_offending_file(tmp_path):
    (tmp_path / 'teachers').mkdir()
    (tmp_path / 'teachers' / 'new_view.py').write_text('profile.is_verified = True\n', encoding='utf-8')
    errors = ratchet_errors(_found(tmp_path), {})
    assert errors and 'teachers/new_view.py' in errors[0]
    assert rel(tmp_path / 'teachers' / 'new_view.py', tmp_path) == 'teachers/new_view.py'
