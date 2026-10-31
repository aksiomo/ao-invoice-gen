from __future__ import annotations

import re

from app.io_excel import detect_format, read_matrix

from .conftest import PURCHASE_FILE


def test_detect_html_pseudo_xls():
    assert detect_format(PURCHASE_FILE) == "html"


def test_parse_purchase_file():
    matrix = read_matrix(PURCHASE_FILE)
    assert len(matrix) > 100

    headers = sum(1 for r in matrix if r[:2] == ["存货编码", "存货名称"])
    assert headers == 13

    items = [r for r in matrix if len(r) >= 7 and re.fullmatch(r"\d+", r[0] or "") and r[1]]
    assert len(items) == 90

    assert items[0][1] == "4分线管"
    assert items[0][3] == "条"
    assert items[0][6] == "15.00"
    assert any(r[1] == "600*600天花灯" and r[2] == "公牛" for r in items)
