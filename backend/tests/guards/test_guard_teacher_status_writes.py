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
CREATE_METHODS = {'create', 'get_or_create', 'update_or_create', 'bulk_create'}
UPDATE_METHODS = {'update'}
BULK_UPDATE = 'bulk_update'

# Receiver heuristic (the scan has no types; it reads the source text of the receiver, e.g. `request.user.teacher_profile`):
#   1. OTHER  when it names a model that merely shares a field name and contains a tutor word: availabilities, strikes, slots;
#   2. TUTOR  when it contains teacher / profile / tutor (checked BEFORE the `user` exclusion, so
#             `request.user.teacher_profile` is a tutor);
#   3. OTHER  when it names User / packs / prices / bundles / bookings / transactions / refunds / purchases;
#   4. UNKNOWN otherwise (`locked`, `qs`, `p`).
# `self` is classified by the enclosing class: TUTOR inside `class TeacherProfile`, OTHER elsewhere.
# Field rules: `is_verified` is flagged on every receiver (only TeacherProfile has it); `is_active` on TUTOR and UNKNOWN
# receivers (tutor rows often sit in neutral names); `status` on TUTOR receivers only (every other model has a `status`;
# T1a adds a stricter guard for its own service).
FIRST_OTHER = re.compile(r'availab|strike|slot', re.IGNORECASE)
TUTOR = re.compile(r'teacher|profile|tutor', re.IGNORECASE)
LATER_OTHER = re.compile(r'user|pack|price|bundle|booking|transaction|refund|purchase', re.IGNORECASE)
TUTOR_CLASSES = {'TeacherProfile'}


def classify(receiver_text, enclosing_class=None):
    if receiver_text == 'self':
        return 'tutor' if enclosing_class in TUTOR_CLASSES else 'other'
    if FIRST_OTHER.search(receiver_text):
        return 'other'
    if TUTOR.search(receiver_text):
        return 'tutor'
    if LATER_OTHER.search(receiver_text):
        return 'other'
    return 'unknown'


def flagged(field, kind):
    if field == 'is_verified':
        return True
    if field == 'is_active':
        return kind in ('tutor', 'unknown')
    return field == 'status' and kind == 'tutor'


def _attr_targets(target):
    if isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _attr_targets(elt)
    elif isinstance(target, ast.Attribute):
        yield target


def _const_strings(node):
    return [e.value for e in getattr(node, 'elts', []) if isinstance(e, ast.Constant) and isinstance(e.value, str)]


def _dict_keys(node):
    return [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)] \
        if isinstance(node, ast.Dict) else []


def _written_fields(call):
    """(field, how) pairs a create/update/bulk_update call writes: kwargs, **{...}, defaults={...}, bulk_update fields."""
    method = call.func.attr
    fields = []
    for kw in call.keywords:
        if kw.arg in FIELDS:
            fields.append((kw.arg, f'{kw.arg}='))
        elif kw.arg is None:
            fields += [(key, f'**{{{key!r}}}') for key in _dict_keys(kw.value) if key in FIELDS]
        elif kw.arg in ('defaults', 'create_defaults'):
            fields += [(key, f'{kw.arg}={{{key!r}}}') for key in _dict_keys(kw.value) if key in FIELDS]
        elif kw.arg == 'fields' and method == BULK_UPDATE:
            fields += [(f, f'fields=[{f!r}]') for f in _const_strings(kw.value) if f in FIELDS]
    if method == BULK_UPDATE and len(call.args) >= 2:
        fields += [(f, f'[{f!r}]') for f in _const_strings(call.args[1]) if f in FIELDS]
    return fields


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.hits = []
        self.classes = []

    @property
    def cls(self):
        return self.classes[-1] if self.classes else None

    def visit_ClassDef(self, node):
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def _assign(self, node, targets):
        for target in targets:
            for attr in _attr_targets(target):
                if attr.attr in FIELDS and flagged(attr.attr, classify(src(attr.value), self.cls)):
                    self.hits.append(f'{node.lineno}: {src(attr)} = ...')
        self.generic_visit(node)

    def visit_Assign(self, node):
        self._assign(node, node.targets)

    def visit_AugAssign(self, node):
        self._assign(node, [node.target])

    def visit_AnnAssign(self, node):
        self._assign(node, [node.target])

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name) and func.id == 'setattr' and len(node.args) >= 2:
            name = node.args[1]
            if isinstance(name, ast.Constant) and name.value in FIELDS \
                    and flagged(name.value, classify(src(node.args[0]), self.cls)):
                self.hits.append(f'{node.lineno}: setattr({src(node.args[0])}, {name.value!r}, ...)')
        elif isinstance(func, ast.Attribute) and func.attr in CREATE_METHODS | UPDATE_METHODS | {BULK_UPDATE}:
            receiver = src(func.value)
            if func.attr in CREATE_METHODS and 'TeacherProfile' not in receiver:
                receiver_kind = None                      # creates are only checked on TeacherProfile itself
            else:
                receiver_kind = classify(receiver, self.cls)
            for field, how in _written_fields(node) if receiver_kind else []:
                if flagged(field, receiver_kind):
                    self.hits.append(f'{node.lineno}: {func.attr}({how}...)')
        self.generic_visit(node)


def teacher_status_writes(path):
    visitor = _Visitor()
    visitor.visit(parse(path))
    return visitor.hits


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
            elif isinstance(func, ast.Attribute) and func.attr in CREATE_METHODS | UPDATE_METHODS | {BULK_UPDATE}:
                hits += [f'{node.lineno}: {func.attr}(status=...)' for kw in node.keywords if kw.arg == 'status']
                hits += [f'{node.lineno}: {func.attr}([... "status" ...])' for arg in node.args
                         if isinstance(arg, (ast.List, ast.Tuple)) and any(
                             isinstance(e, ast.Constant) and e.value == 'status' for e in arg.elts)]
    return hits


def test_strict_detector_ignores_other_teachers_app_models_with_their_own_status(tmp_path):
    """Sign-off minor 7: future teachers-app models (documents, applications, training) have a `status` of their own."""
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "document.status = 'quarantined'\n"
        "teacher_document.status = 'committed'\n"
        "application.status = 'sent'\n"
        "training_progress.status = 'done'\n"
        "TeacherDocument.objects.filter(pk=1).update(status='committed')\n"
        "TeacherApplication.objects.create(user=u, status='sent')\n"
        "TrainingProgress.objects.bulk_update(rows, ['status'])\n"
        "class TeacherDocument(models.Model):\n"
        "    def commit(self):\n"
        "        self.status = 'committed'\n",
        encoding='utf-8')
    assert strict_status_writes(ok) == []
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "class TeacherProfile(models.Model):\n"
        "    def x(self):\n"
        "        self.status = 'approved'\n"
        "TeacherProfile.objects.filter(pk=1).update(status='approved')\n"
        "locked.status = 'approved'\n"
        "teacher.status = 'approved'\n",
        encoding='utf-8')
    assert len(strict_status_writes(bad)) == 4


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
