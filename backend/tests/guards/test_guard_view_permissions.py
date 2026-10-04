"""
Guard (f): every DRF view declares `permission_classes` explicitly.

Relying on `DEFAULT_PERMISSION_CLASSES` makes a view's exposure invisible at the place it is written and lets a settings change
silently open it. A class in `apps/*/*views*.py` whose base name ends in `APIView`, `View` or `ViewSet` must assign
`permission_classes` in its body or inherit from a class in the same module that does; an `@api_view` function needs a
`@permission_classes(...)` decorator.

How to shrink: add the explicit `permission_classes`, then lower the file's count here. (Throttle / typed-schema checks from
plan §5 are a follow-up; see docs/QUALITY_GATES.md.)
"""
import ast

from guards._scan import APPS, parse, ratchet_errors, scan, src

VIEW_BASE_SUFFIXES = ('APIView', 'View', 'ViewSet')
# Baseline 2026-10-04: {file: number of views without explicit permission_classes}. Only ever lower these numbers.
ALLOWLIST = {}


def _base_name(base):
    return base.attr if isinstance(base, ast.Attribute) else getattr(base, 'id', '')


def _assigns_permissions(cls):
    for stmt in cls.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == 'permission_classes' for t in targets):
            return True
    return False


def views_without_permissions(path):
    tree = parse(path)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}

    def explicit(cls, seen=()):
        if _assigns_permissions(cls):
            return True
        return any(_base_name(b) in classes and _base_name(b) not in seen and explicit(classes[_base_name(b)], (*seen, cls.name))
                   for b in cls.bases)

    def is_view(cls, seen=()):
        for b in cls.bases:
            name = _base_name(b)
            if name.endswith(VIEW_BASE_SUFFIXES):
                return True
            if name in classes and name not in seen and is_view(classes[name], (*seen, cls.name)):
                return True
        return False

    hits = [f'{cls.lineno}: class {cls.name}' for cls in classes.values() if is_view(cls) and not explicit(cls)]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [src(d) for d in node.decorator_list]
            if any(d.startswith('api_view') for d in decorators) and not any(d.startswith('permission_classes') for d in decorators):
                hits.append(f'{node.lineno}: def {node.name} (@api_view)')
    return hits


def _view_files(root=APPS):
    return [p for p in sorted(root.glob('*/*views*.py'))]


def test_every_view_declares_permission_classes():
    errors = ratchet_errors(scan(views_without_permissions, APPS, files=_view_files()), ALLOWLIST)
    assert not errors, 'Declare permission_classes on every view:\n' + '\n'.join(errors)


def test_the_scan_sees_the_view_modules():
    names = {p.relative_to(APPS).as_posix() for p in _view_files()}
    assert {'bookings/views.py', 'admin_api/refund_views.py', 'admin_api/fx_views.py'} <= names


def test_detector(tmp_path):
    bad = tmp_path / 'views.py'
    bad.write_text(
        "class A(APIView):\n    def get(self, r): ...\n"
        "class B(generics.ListAPIView):\n    queryset = None\n"
        "class C(viewsets.ModelViewSet):\n    pass\n"
        "@api_view(['GET'])\ndef d(request): ...\n"
        "class Ok(APIView):\n    permission_classes = (AllowAny,)\n"
        "class OkChild(Ok):\n    pass\n"
        "class Serializer(serializers.Serializer):\n    pass\n"
        "@api_view(['GET'])\n@permission_classes([IsAuthenticated])\ndef e(request): ...\n",
        encoding='utf-8')
    assert [h.split(': ', 1)[1] for h in views_without_permissions(bad)] == ['class A', 'class B', 'class C', 'def d (@api_view)']
