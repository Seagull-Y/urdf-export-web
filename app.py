#!/usr/bin/env python3
"""
FastAPI web application for Onshape URDF export and web-based 3D visualization.
"""

import os
import sys
import uuid
import json
import asyncio
import zipfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="URDF Exporter", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: dict = {}
JOBS_DIR = Path("jobs")
JOBS_DIR.mkdir(exist_ok=True)

SCRIPT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ExportRequest(BaseModel):
    onshape_url: str
    assembly_name: str = "URDF_Top_Assembly"
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    merge_stls: str = "all"
    simplify_stls: str = "all"


# ---------------------------------------------------------------------------
# Background export task (runs in thread pool via BackgroundTasks)
# ---------------------------------------------------------------------------
def _run_export(job_id: str, req: ExportRequest) -> None:
    """Runs export_urdf.py as a subprocess, streams stdout into job logs."""
    job = JOBS[job_id]
    output_dir = JOBS_DIR / job_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        job["logs"].append(msg)

    log(f"Export started at {datetime.utcnow().isoformat()} UTC")
    log(f"URL: {req.onshape_url}")
    log(f"Assembly: {req.assembly_name}")

    # Per-job config (passed to export_urdf.py via --config)
    config = {
        "assemblyName": req.assembly_name,
        "outputFormat": "urdf",
        "mergeSTLs": req.merge_stls,
        "simplifySTLs": req.simplify_stls,
    }
    config_path = JOBS_DIR / job_id / "config.json"
    config_path.write_text(json.dumps(config, indent=2))

    env = os.environ.copy()
    if req.access_key:
        env["ONSHAPE_ACCESS_KEY"] = req.access_key
    if req.secret_key:
        env["ONSHAPE_SECRET_KEY"] = req.secret_key

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "export_urdf.py"),
        "--url", req.onshape_url,
        "--assembly", req.assembly_name,
        "--output", str(output_dir),
        "--config", str(config_path),
    ]

    log(f"Running export script...")

    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(SCRIPT_DIR),
        )
        for line in proc.stdout:
            log(line.rstrip())
        proc.wait()

        urdf_file = output_dir / "robot.urdf"
        if proc.returncode == 0 and urdf_file.exists():
            assets_dir = output_dir / "assets"
            stl_count = len(list(assets_dir.glob("*.stl"))) if assets_dir.exists() else 0
            log(f"✓ Export successful — robot.urdf + {stl_count} mesh files")
            job["status"] = "success"
            job["urdf_available"] = True
        else:
            log(f"✗ Export failed (exit code {proc.returncode})")
            job["status"] = "failed"

    except FileNotFoundError:
        log("✗ export_urdf.py not found — check server installation")
        job["status"] = "failed"
    except Exception as exc:
        log(f"✗ Unexpected error: {exc}")
        job["status"] = "failed"


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.post("/api/export")
async def start_export(req: ExportRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "created_at": datetime.utcnow().isoformat(),
        "logs": [],
        "urdf_available": False,
    }
    background_tasks.add_task(_run_export, job_id, req)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    job = JOBS[job_id]
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "urdf_available": job["urdf_available"],
        "log_count": len(job["logs"]),
        "created_at": job["created_at"],
    }


@app.get("/api/jobs/{job_id}/stream")
async def stream_logs(job_id: str, request: Request):
    """SSE endpoint: streams log lines. Supports Last-Event-ID for reconnection."""
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")

    # Support reconnection: resume from last received index
    last_id_header = request.headers.get("Last-Event-ID")
    start_index = 0
    if last_id_header:
        try:
            start_index = int(last_id_header) + 1
        except ValueError:
            pass

    async def generator():
        job = JOBS[job_id]
        sent = start_index
        while True:
            logs = job["logs"]
            while sent < len(logs):
                data = json.dumps({"line": logs[sent]})
                yield f"id: {sent}\ndata: {data}\n\n"
                sent += 1

            if job["status"] in ("success", "failed"):
                yield f"data: {json.dumps({'done': True, 'status': job['status']})}\n\n"
                return

            await asyncio.sleep(0.3)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/files/{file_path:path}")
async def serve_file(job_id: str, file_path: str):
    """Serve URDF and STL mesh files for the browser 3D viewer."""
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    output_dir = (JOBS_DIR / job_id / "output").resolve()
    target = (output_dir / file_path).resolve()
    # Path traversal protection
    if not str(target).startswith(str(output_dir)):
        raise HTTPException(403, "Forbidden")
    if not target.exists():
        raise HTTPException(404, f"File not found: {file_path}")
    media = "application/xml" if target.suffix == ".urdf" else "application/octet-stream"
    return FileResponse(str(target), media_type=media)


@app.get("/api/jobs/{job_id}/download")
async def download_zip(job_id: str):
    """Package URDF + assets into a ZIP and return for download."""
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    job = JOBS[job_id]
    if not job["urdf_available"]:
        raise HTTPException(400, "URDF not ready yet")

    output_dir = JOBS_DIR / job_id / "output"
    zip_path = JOBS_DIR / job_id / "robot_urdf.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in output_dir.rglob("*"):
            if fp.is_file():
                zf.write(fp, fp.relative_to(output_dir))

    zip_bytes = zip_path.read_bytes()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="robot_urdf.zip"',
            "Content-Length": str(len(zip_bytes)),
        },
    )


@app.get("/api/jobs")
async def list_jobs():
    """Return up to 20 most recent jobs."""
    return sorted(
        [
            {
                "job_id": j["job_id"],
                "status": j["status"],
                "created_at": j["created_at"],
                "urdf_available": j["urdf_available"],
            }
            for j in JOBS.values()
        ],
        key=lambda x: x["created_at"],
        reverse=True,
    )[:20]


# ---------------------------------------------------------------------------
# Static frontend — mount last so API routes take priority
# ---------------------------------------------------------------------------
static_dir = SCRIPT_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
