from __future__ import annotations

from app.taxonomy import get_by_code, is_leaf_code, search


def test_code_lookup():
    cand = get_by_code("1090416010000000000")
    assert cand is not None
    assert cand.name == "家用电风扇"
    assert is_leaf_code(cand.code)


def test_unknown_code():
    assert get_by_code("0000000000000000000") is None


def test_search_returns_leaves():
    hits = search("壁扇", 20)
    assert hits
    assert all(len(c.code) == 19 for c in hits)
    names = [c.name for c in hits]
    assert "家用电风扇" in names


def test_search_recall_core_goods():
    cases = {
        "2.5平方电线": "电线电缆",
        "冷热花洒水龙头": "龙头",
        "纱手套（厚）": "手套",
        "600*600天花灯": "照明",
        "配匙": "锁",
    }
    for query, keyword in cases.items():
        names = [c.name for c in search(query, 20)]
        assert any(keyword in n for n in names), f"{query} 候选中缺少 {keyword}"
