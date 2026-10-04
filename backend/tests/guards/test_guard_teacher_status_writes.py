"""
Guard (a): `TeacherProfile.is_verified` / `is_active` / `status` are written only by the tutor status service.

Plan §3.1: `status` is the only stored column and `is_verified` / `is_active` are GeneratedFields of it; the one writer is
`teachers/vetting.py::transition_teacher` / `create_teacher_profile` (slice T1a, docs/TUTOR_STATUS_MACHINE.md). Migrations
are excluded by the scanner. T1a emptied the baseline allowlist: there is no exception left.

Two detectors: the Q0 one over all of `apps/` (tutor-looking receivers for `status`), and a stricter one over `apps/teachers/`
where any `status` write (every receiver, every ORM write method) outside the service fails.
"""
import ast
import re

from guards._scan import APPS, parse, ratchet_errors, rel, scan, src

FIELDS = {'is_verified', 'is_active', 'status'}
# The service that owns the transitions.
ALLOWED_WRITERS = {'teachers/vetting.py'}
# Baseline 2026-10-04 was 4 files / 8 writes; T1a routed every one through the service. Never add an entry.
ALLOWLIST = {}
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


def strict_status_writes(path):
    """Inside apps/teachers/: ANY `.status` assignment / setattr, or `status=` kwarg to an ORM write method."""
    hits = []
    for node in ast.walk(parse(path)):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            hits += [f'{node.lineno}: {src(a)} = ...' for t in targets for a in _attr_targets(t) if a.attr == 'status']
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == 'setattr' and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant) and node.args[1].value == 'status':
                hits.append(f'{node.lineno}: setattr(..., "status", ...)')
            elif isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS | {'bulk_update'}:
                hits += [f'{node.lineno}: {func.attr}(status=...)' for kw in node.keywords if kw.arg == 'status']
                hits += [f'{node.lineno}: {func.attr}([... "status" ...])' for arg in node.args
                         if isinstance(arg, (ast.List, ast.Tuple)) and any(
                             isinstance(e, ast.Constant) and e.value == 'status' for e in arg.elts)]
    return hits


def test_teachers_app_writes_status_only_in_the_service():
    found = scan(strict_status_writes, APPS / 'teachers')
    found = {path: sites for path, sites in found.items() if f'teachers/{path}' not in ALLOWED_WRITERS}
    assert not found, f'TeacherProfile.status is written only by teachers/vetting.py: {found}'


def test_the_service_itself_is_seen_by_the_strict_detector():
    assert strict_status_writes(APPS / 'teachers' / 'vetting.py'), 'the detector must see the one real writer'


def test_strict_detector_shapes(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text("locked.status = 'x'\nsetattr(row, 'status', 'x')\nQ.objects.filter().update(status='x')\n"
                   "Q.objects.bulk_update(rows, ['status'])\n", encoding='utf-8')
    assert len(strict_status_writes(bad)) == 4
    ok = tmp_path / 'ok.py'
    ok.write_text("x = profile.status\nQ.objects.filter(status='approved')\n", encoding='utf-8')
    assert strict_status_writes(ok) == []


def test_ratchet_fails_on_a_new_offending_file(tmp_path):
    (tmp_path / 'teachers').mkdir()
    (tmp_path / 'teachers' / 'new_view.py').write_text('profile.is_verified = True\n', encoding='utf-8')
    errors = ratchet_errors(_found(tmp_path), {})
    assert errors and 'teachers/new_view.py' in errors[0]
    assert rel(tmp_path / 'teachers' / 'new_view.py', tmp_path) == 'teachers/new_view.py'
