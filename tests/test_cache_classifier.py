from __future__ import annotations

import json

from app.agents import classifier as clf
from app.cache import cache_key, lookup_many, save_many
from app.config import settings
from app.schemas import ClassifiedItem


def test_cache_roundtrip(tmp_path, monkeypatch):
    db = tmp_path / "cache.sqlite"
    monkeypatch.setattr(settings, "cache_db", db)

    save_many(
        [
            ClassifiedItem(
                name="壁扇",
                code="1090416010000000000",
                category_name="家用电风扇",
                short_name="家用通风电器具",
            )
        ],
        model="test-model",
    )
    hit = lookup_many([" 壁扇 "])
    assert cache_key(" 壁扇 ") in hit
    assert hit["壁扇"].code == "1090416010000000000"
    assert hit["壁扇"].from_cache is True


def test_classify_uses_cache_without_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_db", tmp_path / "cache.sqlite")
    save_many(
        [
            ClassifiedItem(
                name="壁扇",
                code="1090416010000000000",
                category_name="家用电风扇",
                short_name="家用通风电器具",
            )
        ]
    )

    def _boom(*args, **kwargs):
        raise AssertionError("缓存命中时不应调用 LLM")

    monkeypatch.setattr(clf, "_llm_classify", _boom)
    items, hits = clf.classify_names(["壁扇", "壁扇"])
    assert hits == 1
    assert len(items) == 1
    assert items[0].code == "1090416010000000000"


def test_validate_results_rejects_bad_code():
    payload = {"results": [{"name": "壁扇", "code": "123"}]}
    chosen, errors = clf._validate_results(payload, ["壁扇"])
    assert errors
    assert "壁扇" not in chosen


def test_llm_choose_validates_code_exists(monkeypatch):
    fake_response = {
        "results": [
            {"name": "壁扇", "code": "1090416010000000000", "reason": "家用通风电器"}
        ]
    }
    monkeypatch.setattr(
        clf,
        "chat_json",
        lambda *a, **k: json.loads(json.dumps(fake_response)),
    )
    items = clf._llm_classify(["壁扇"])
    assert len(items) == 1
    assert items[0].category_name == "家用电风扇"
