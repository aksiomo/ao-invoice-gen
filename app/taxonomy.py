"""税收分类编码检索：FTS5 粗召回 + 本地规则重排。"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

ALNUM_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_FUNCTION_CHARS = set("个米位用的与和")

# 业务语义词扩展：采购口语 -> 税收分类命名常用字（仅用于扩大 LIKE 召回）
_SYNONYM_CHARS: dict[str, tuple[str, ...]] = {
    "灯": ("灯", "照明", "光源", "光"),
    "匙": ("匙", "锁"),
    "板": ("板",),
    "纸": ("纸",),
    "盒": ("盒", "箱", "容器"),
}


@dataclass(frozen=True)
class Candidate:
    code: str
    name: str
    short_name: str
    description: str

    def brief(self, desc_limit: int = 80) -> dict:
        desc = self.description
        if len(desc) > desc_limit:
            desc = desc[:desc_limit] + "…"
        return {
            "code": self.code,
            "name": self.name,
            "short_name": self.short_name,
            "description": desc,
        }


def _tokens(query: str) -> tuple[list[str], list[str]]:
    q = query.lower().strip()
    alnum = [t for t in ALNUM_RE.findall(q) if not t.isdigit() or len(t) > 1]
    cjk = CJK_RE.findall(q)
    bigrams = [a + b for a, b in zip(cjk, cjk[1:])]
    return alnum, bigrams


def _connect(path: Path | None = None) -> sqlite3.Connection:
    db = path or settings.taxonomy_db
    if not Path(db).exists():
        raise FileNotFoundError(
            f"税收编码库不存在：{db}，请先运行 python scripts/build_taxonomy.py"
        )
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def get_by_code(code: str, conn: sqlite3.Connection | None = None) -> Candidate | None:
    own = conn is None
    conn = conn or _connect()
    try:
        row = conn.execute(
            "SELECT code, name, short_name, description, is_leaf FROM codes WHERE code=?",
            (str(code).strip(),),
        ).fetchone()
        if row is None:
            return None
        return Candidate(row["code"], row["name"], row["short_name"] or "", row["description"] or "")
    finally:
        if own:
            conn.close()


def is_leaf_code(code: str, conn: sqlite3.Connection | None = None) -> bool:
    own = conn is None
    conn = conn or _connect()
    try:
        row = conn.execute("SELECT is_leaf FROM codes WHERE code=?", (str(code).strip(),)).fetchone()
        return bool(row and row["is_leaf"])
    finally:
        if own:
            conn.close()


def _score(query: str, cand: Candidate, tier: int, bm25: float) -> float:
    q = query.strip()
    name = cand.name
    short = cand.short_name
    text = name + " " + short

    score = (2 - tier) * 10.0
    score -= max(bm25, 0.0) * 0.15

    if q == name:
        score += 150
    if q == short:
        score += 80
    if q and q in name:
        score += 60
    if name and name in q and name != q:
        score += 25

    alnum, bigrams = _tokens(q)
    unigrams = list(dict.fromkeys(CJK_RE.findall(q)))

    bg_name = sum(1 for bg in bigrams if bg in name)
    bg_any = sum(1 for bg in bigrams if bg in name or bg in short)
    if bigrams:
        score += 70.0 * bg_name / len(bigrams)
        score += 25.0 * (bg_any - bg_name) / len(bigrams)
    core_uni = [u for u in unigrams if u not in _FUNCTION_CHARS]
    name_chars = CJK_RE.findall(name)
    uni_name = sum(1 for u in core_uni if u in name)
    uni_hit = sum(1 for u in core_uni if u in text)
    if core_uni:
        if tier == 1:
            coverage = uni_name / len(core_uni)
            density = uni_name / max(len(name_chars), 1)
            score += 30.0 * coverage
            score += 18.0 * density
            score += 8.0 * (uni_hit - uni_name) / len(core_uni)
        else:
            score += 10.0 * uni_hit / len(core_uni)

    for ch, syns in _SYNONYM_CHARS.items():
        if ch in q and tier >= 1:
            if any(syn != ch and (syn in name or syn in short) for syn in syns):
                score += 26.0

    name_l = name.lower()
    short_l = short.lower()
    alnum_hit = sum(1 for tok in alnum if tok in name_l or tok in short_l)
    if alnum:
        score += 30.0 * alnum_hit / len(alnum)

    if bigrams and bg_any == 0 and tier >= 1:
        score -= 25
    score -= min(len(name), 24) * 0.04
    return score


def _fts_search(
    conn: sqlite3.Connection, terms: list[str], pool: int
) -> list[tuple[Candidate, float]]:
    if not terms:
        return []
    match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
    sql = (
        "SELECT f.code AS code, bm25(codes_fts, 10.0, 3.0, 1.0) AS rank, "
        "c.name AS name, c.short_name AS short_name, c.description AS description "
        "FROM codes_fts f JOIN codes c ON c.code = f.code "
        "WHERE codes_fts MATCH ? AND c.is_leaf = 1 "
        "ORDER BY rank LIMIT ?"
    )
    out = []
    for row in conn.execute(sql, (match, pool)):
        cand = Candidate(row["code"], row["name"], row["short_name"] or "", row["description"] or "")
        out.append((cand, row["rank"]))
    return out


def _select_diverse(scored: list[tuple[Candidate, float, int]], k: int) -> list[Candidate]:
    """按总分选 k 个；tier1 候选与 tier0 已统一打分，直接取全局 Top-k。"""
    return [cand for cand, _, _ in scored[:k]]


def search(query: str, k: int | None = None, conn: sqlite3.Connection | None = None) -> list[Candidate]:
    k = k or settings.top_k
    own = conn is None
    conn = conn or _connect()
    try:
        q = query.strip()
        alnum, bigrams = _tokens(q)
        cjk_unigrams = list(dict.fromkeys(CJK_RE.findall(q)))
        merged: dict[str, tuple[Candidate, int, float]] = {}

        def absorb(hits: list[tuple[Candidate, float]], tier: int) -> None:
            for cand, rank in hits:
                prev = merged.get(cand.code)
                if prev is None or tier < prev[1]:
                    merged[cand.code] = (cand, tier, rank)

        exact = conn.execute(
            "SELECT code, name, short_name, description FROM codes WHERE name=? AND is_leaf=1",
            (q,),
        ).fetchone()
        if exact is not None:
            cand = Candidate(exact["code"], exact["name"], exact["short_name"] or "", exact["description"] or "")
            merged[exact["code"]] = (cand, -1, -100.0)

        absorb(_fts_search(conn, bigrams + alnum, 120), 0)

        core_unigrams = [u for u in cjk_unigrams if u not in _FUNCTION_CHARS]
        uni_pool: dict[str, tuple[Candidate, int]] = {}
        for ch in core_unigrams[-6:]:
            for row in conn.execute(
                "SELECT code, name, short_name, description FROM codes "
                "WHERE is_leaf=1 AND name LIKE ? LIMIT 400",
                (f"%{ch}%",),
            ):
                cand = Candidate(row["code"], row["name"], row["short_name"] or "", row["description"] or "")
                prev = uni_pool.get(cand.code)
                overlap = 1 if prev is None else prev[1] + 1
                uni_pool[cand.code] = (cand, overlap)
        ranked_pool = sorted(
            uni_pool.values(),
            key=lambda x: (x[1], -len(CJK_RE.findall(x[0].name))),
            reverse=True,
        )
        for cand, overlap in ranked_pool[:60]:
            merged.setdefault(cand.code, (cand, 1, 10.0 - overlap))
        for ch in core_unigrams[-4:]:
            for row in conn.execute(
                "SELECT code, name, short_name, description FROM codes "
                "WHERE is_leaf=1 AND short_name LIKE ? LIMIT 60",
                (f"%{ch}%",),
            ):
                cand = Candidate(row["code"], row["name"], row["short_name"] or "", row["description"] or "")
                merged.setdefault(cand.code, (cand, 1, 12.0))

        for ch, syns in _SYNONYM_CHARS.items():
            if ch not in core_unigrams:
                continue
            for syn in syns:
                if syn == ch:
                    continue
                for row in conn.execute(
                    "SELECT code, name, short_name, description FROM codes "
                    "WHERE is_leaf=1 AND (name LIKE ? OR short_name LIKE ?) LIMIT 80",
                    (f"%{syn}%", f"%{syn}%"),
                ):
                    cand = Candidate(row["code"], row["name"], row["short_name"] or "", row["description"] or "")
                    merged.setdefault(cand.code, (cand, 1, 12.0))

        scored = sorted(
            ((cand, _score(q, cand, tier, rank), tier) for cand, tier, rank in merged.values()),
            key=lambda x: x[1],
            reverse=True,
        )
        return _select_diverse(scored, k)
    finally:
        if own:
            conn.close()
