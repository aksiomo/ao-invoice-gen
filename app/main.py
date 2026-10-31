from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.jobs import registry
from app.pipeline import run_pipeline

settings.ensure_dirs()

app = FastAPI(title="ao-invoice-gen")
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/jobs")
async def create_job(file: UploadFile, background_tasks: BackgroundTasks) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")
    suffix = Path(file.filename).suffix or ".xls"
    job = registry.create(file.filename)
    input_path = settings.upload_dir / f"{job.id}{suffix}"
    job.output_path = settings.generated_dir / f"{job.id}.xlsx"

    size = 0
    with open(input_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                f.close()
                input_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="文件超过大小限制")
            f.write(chunk)

    background_tasks.add_task(run_sync, job, input_path)
    return {"job_id": job.id}


def run_sync(job, input_path: Path) -> None:
    run_pipeline(job, input_path)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job.public()


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    job = registry.get(job_id)
    if job is None or job.stage != "done" or not job.output_path:
        raise HTTPException(status_code=404, detail="结果文件不存在")
    path = Path(job.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="结果文件已被清理")
    download_name = f"发票开具项目信息导入_{Path(job.filename).stem}.xlsx"
    encoded = quote(download_name)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=invoice_template.xlsx; filename*=UTF-8''{encoded}"
            )
        },
    )
