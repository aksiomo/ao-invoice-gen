"""把《商品和服务税收分类编码表.xls》构建为带全文检索的 SQLite 库。

用法：
    python scripts/build_taxonomy.py [源xls路径] [输出sqlite路径]

默认读取 example_files/商品和服务税收分类编码表.xls，输出 data/taxonomy.sqlite。
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "example_files" / "商品和服务税收分类编码表.xls"
DEFAULT_OUT = ROOT / "data" / "taxonomy.sqlite"

CODE_RE = re.compile(r"^\d{19}$")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*")


def load_rows(path: Path) -> list[tuple[str, str, str, str]]:
    import xlrd

    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    rows: list[tuple[str, str, str, str]] = []
    for r in range(2, sheet.nrows):
        raw = sheet.cell_value(r, 11)
        code = str(raw).split(".", 1)[0].strip()
        if not CODE_RE.fullmatch(code):
            continue
        name = str(sheet.cell_value(r, 12)).strip()
        short = str(sheet.cell_value(r, 13)).strip()
        desc = str(sheet.cell_value(r, 14)).strip()
        if name:
            rows.append((code, name, short, desc))
    return rows


def tokenize(text: str) -> list[str]:
    """CJK 单字 + bigram；连续字母数字（LED/UPS/24V）作为整体 token。"""
    tokens: list[str] = []
    text = text.lower()
    tokens.extend(TOKEN_RE.findall(text))
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(cjk)
    tokens.extend(a + b for a, b in zip(cjk, cjk[1:]))
    return tokens


def compute_leaves(rows: list[tuple[str, str, str, str]]) -> set[str]:
    """去除尾部 00 段后，没有任何更长编码以其为前缀者即叶子。"""
    stripped = {code.rstrip("0"): code for code, *_ in rows}

    def is_leaf(code: str) -> bool:
        stem = code.rstrip("0")
        for other in stripped:
            if other != stem and other.startswith(stem):
                return False
        return True

    return {code for code, *_ in rows if is_leaf(code)}


def build(src: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    rows = load_rows(src)
    leaves = compute_leaves(rows)

    conn = sqlite3.connect(out)
    try:
        conn.executescript(
            """
            CREATE TABLE codes (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                short_name TEXT,
                description TEXT,
                is_leaf INTEGER NOT NULL
            );
            CREATE VIRTUAL TABLE codes_fts USING fts5(
                code UNINDEXED,
                name_tokens,
                short_tokens,
                desc_tokens,
                tokenize = 'unicode61 remove_diacritics 2'
            );
            """
        )
        conn.executemany(
            "INSERT INTO codes(code, name, short_name, description, is_leaf) "
            "VALUES (?,?,?,?,?)",
            [(c, n, s, d, 1 if c in leaves else 0) for c, n, s, d in rows],
        )
        conn.executemany(
            "INSERT INTO codes_fts(code, name_tokens, short_tokens, desc_tokens) "
            "VALUES (?,?,?,?)",
            [
                (
                    c,
                    " ".join(tokenize(n)),
                    " ".join(tokenize(s)),
                    " ".join(tokenize(d)),
                )
                for c, n, s, d in rows
            ],
        )
        conn.commit()
        n_leaf = sum(1 for c in leaves)
        print(f"codes={len(rows)} leaves={n_leaf} -> {out}")
    finally:
        conn.close()


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    build(src, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
