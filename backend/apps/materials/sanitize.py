"""
Lesson HTML cleaning (Wave 2, docs/ADMIN_CONTENT_MANAGEMENT_PENDING.md risk 1).

`Material.content_html` is rendered as raw HTML by the website, so it is cleaned with nh3 (the Ammonia sanitizer) every time a
material is saved, from any path (web admin, Django admin, seed data), and again when the API returns it (rows written before
this existed). Only text formatting, lists, tables and links survive: no scripts, styles, event handlers, forms, iframes or
images (there is no image upload, and a remote image would let a third party track readers).
"""
import re

import nh3

ALLOWED_TAGS = {
    'p', 'br', 'hr', 'h2', 'h3', 'h4', 'strong', 'b', 'em', 'i', 'u', 's', 'mark', 'small', 'sub', 'sup', 'code', 'pre',
    'blockquote', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'a', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
    'section', 'div', 'span',
}
ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
    'th': {'colspan', 'rowspan', 'scope'},
    'td': {'colspan', 'rowspan'},
    'ol': {'start'},
}
URL_SCHEMES = {'http', 'https', 'mailto'}


def clean_lesson_html(html: str) -> str:
    if not html:
        return ''
    cleaned = nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, url_schemes=URL_SCHEMES,
                        link_rel='noopener noreferrer nofollow', strip_comments=True)
    # Browsers' editors leave empty paragraphs around lists (<p><ul>..</ul></p> is re-parsed as <p></p><ul>..</ul><p></p>).
    return _EMPTY_P.sub('', cleaned)


_EMPTY_P = re.compile(r'<p>(?:\s|&nbsp;|<br>)*</p>')
