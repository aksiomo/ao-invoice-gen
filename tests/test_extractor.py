from __future__ import annotations

import pytest

from app.agents import extractor as extractor_mod


def _fake_chat(payload):
    def _call(system, user, *, model, temperature=None):
        return payload

    return _call


def test_parse_basic_items(monkeypatch):
    matrix = [
        ["采购入库单"],
        ["入库单号 20261010007"],
        ["存货编码", "存货名称", "规格型号", "主计量单位", "数量", "本币单价", "本币金额"],
        ["5004502", "4分线管", "", "条", "5.00", "3.0000", "15.00"],
        ["合计", "", "", "", "5", "", "15.00"],
    ]
    payload = {
        "items": [
            {
                "receipt_no": "20261010007",
                "name": "4分线管",
                "unit": "条",
                "quantity": "5.00",
                "unit_price": "3.0000",
                "amount": "15.00",
            }
        ]
    }
    monkeypatch.setattr(extractor_mod, "chat_json", _fake_chat(payload))
    items = extractor_mod.extract_items(matrix)
    assert len(items) == 1
    assert items[0].name == "4分线管"
    assert items[0].quantity is not None
    assert float(items[0].amount) == 15.00


def test_rejects_tampered_name(monkeypatch):
    matrix = [
        ["存货名称", "单位", "数量"],
        ["电磁加药计量泵（消毒水）", "台", "1"],
    ]
    bad = {"items": [{"name": "电磁加药计量泵", "unit": "台", "quantity": "1"}]}
    good = {"items": [{"name": "电磁加药计量泵（消毒水）", "unit": "台", "quantity": "1"}]}
    calls = {"n": 0}

    def _call(system, user, *, model, temperature=None):
        calls["n"] += 1
        return bad if calls["n"] == 1 else good

    monkeypatch.setattr(extractor_mod, "chat_json", _call)
    items = extractor_mod.extract_items(matrix)
    assert items[0].name == "电磁加药计量泵（消毒水）"
    assert calls["n"] == 2


def test_persistent_tamper_raises(monkeypatch):
    matrix = [["存货名称"], ["真实商品"]]
    payload = {"items": [{"name": "被改写的商品"}]}
    monkeypatch.setattr(extractor_mod, "chat_json", _fake_chat(payload))
    with pytest.raises(extractor_mod.ExtractionError):
        extractor_mod.extract_items(matrix)
