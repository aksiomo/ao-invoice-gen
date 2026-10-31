"""编排：读取 -> Agent A 规范化 -> 缓存/Agent B 分类 -> 写出模板。"""

from __future__ import annotations

from pathlib import Path

from app.agents.classifier import classify_names
from app.agents.extractor import extract_items
from app.excel_writer import build_final_rows, write_workbook
from app.io_excel import read_matrix
from app.jobs import Job


def run_pipeline(job: Job, input_path: Path) -> None:
    try:
        job.stage = "reading"
        job.message = "读取并解析表格文件"
        matrix = read_matrix(input_path)

        job.stage = "extracting"
        job.message = "Agent 正在规范化表格结构"
        items = extract_items(matrix)
        job.items = items
        job.total_items = len(items)
        unique_names = list(dict.fromkeys(it.name.strip() for it in items if it.name))
        job.unique_names = len(unique_names)

        job.stage = "classifying"
        job.message = f"分类处理中：共 {len(unique_names)} 种商品"
        classified, cache_hits = classify_names(unique_names)
        job.cache_hits = cache_hits
        by_name = {c.name: c for c in classified}

        missing = [n for n in unique_names if n not in by_name]
        if missing:
            raise RuntimeError("以下商品未获得分类：" + "、".join(missing[:10]))

        job.stage = "writing"
        job.message = "生成发票导入模板"
        rows, warnings = build_final_rows(items, by_name)
        job.rows = rows
        job.warnings = warnings

        output_path = Path(str(job.output_path) if job.output_path else "")
        if not output_path:
            from app.config import settings

            output_path = settings.generated_dir / f"{job.id}.xlsx"
            job.output_path = output_path
        write_workbook(rows, output_path)

        job.stage = "done"
        job.message = f"完成：{len(rows)} 行，缓存命中 {cache_hits}/{len(unique_names)}"
    except Exception as exc:  # noqa: BLE001 - 任务级统一错误出口
        job.stage = "error"
        job.error = f"{type(exc).__name__}: {exc}"
        job.message = "处理失败"
