"""QA review of Q0 item 8: the shared parser tolerates a UTF-8 BOM and names the file on a syntax error."""
import pytest

from guards._scan import parse


def test_a_file_with_a_bom_parses(tmp_path):
    path = tmp_path / 'bom.py'
    path.write_bytes(b'\xef\xbb\xbfx = 1\n')
    assert parse(path).body


def test_a_syntax_error_names_the_file(tmp_path):
    path = tmp_path / 'apps' / 'broken.py'
    path.parent.mkdir()
    path.write_text('def f(:\n', encoding='utf-8')
    with pytest.raises(SyntaxError, match='broken.py'):
        parse(path)
