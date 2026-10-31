from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXAMPLE_DIR = ROOT / "example_files"
PURCHASE_FILE = EXAMPLE_DIR / "采购入库单.XLS"
TAXONOMY_XLS = EXAMPLE_DIR / "商品和服务税收分类编码表.xls"
TEMPLATE_FILE = ROOT / "app" / "assets" / "发票开具项目信息导入模板.xlsx"
TAXONOMY_DB = ROOT / "data" / "taxonomy.sqlite"


@pytest.fixture(scope="session", autouse=True)
def ensure_taxonomy_db():
    if not TAXONOMY_DB.exists():
        from scripts.build_taxonomy import build

        build(TAXONOMY_XLS, TAXONOMY_DB)
    yield
