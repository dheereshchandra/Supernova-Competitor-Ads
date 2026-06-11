"""Ad Studio FastAPI app factory.

Serves the committed React build (webapp/frontend/dist) and the /api routes.
Run: python3.13 -m uvicorn webapp.backend.app:app --port 8787  (from repo root)
"""
from __future__ import annotations

import subprocess

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import api_browse, api_jobs, auth, db, media
from .config import FRONTEND_DIST, REPO, settings
from .data import catalog


def _git_state() -> dict:
    try:
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                               capture_output=True, text=True, timeout=10)
        ahead = subprocess.run(["git", "rev-list", "--count", "@{u}..HEAD"], cwd=REPO,
                               capture_output=True, text=True, timeout=10)
        return {"dirty": bool(dirty.stdout.strip()),
                "unpushed": int(ahead.stdout.strip() or 0) if ahead.returncode == 0 else None}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"dirty": None, "unpushed": None}


def create_app() -> FastAPI:
    app = FastAPI(title="Supernova Ad Studio", docs_url=None, redoc_url=None)
    app.include_router(auth.router)
    app.include_router(api_browse.router)
    app.include_router(api_jobs.router)
    app.include_router(media.router)

    @app.get("/api/health")
    def health():
        cat = catalog()
        cat.reload_if_stale()
        return {
            "ok": True,
            "keys": settings().key_presence(),
            "auth": "enabled" if settings().auth_enabled else "DISABLED (set STUDIO_PASSWORD)",
            "data_as_of": cat.loaded_at,
            "competitors": len(cat.competitors()),
            "git": _git_state(),
        }

    @app.on_event("startup")
    def _startup():
        db.conn()
        catalog().reload_if_stale()
        # Job worker + tracker syncer attach here (jobs.py / sheets.py).
        try:
            from . import jobs
            jobs.start_worker(app)
        except ImportError:
            pass
        try:
            from . import sheets
            sheets.start_syncer(app)
        except ImportError:
            pass
        # Pre-warm winner thumbnails off-thread so the first browse is instant.
        if settings().env.get("STUDIO_PREWARM_THUMBS", "1") == "1":
            import threading
            threading.Thread(target=media.prewarm, daemon=True).start()

    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str, request: Request):
            f = FRONTEND_DIST / path
            if path and f.is_file():
                return FileResponse(f)
            return FileResponse(FRONTEND_DIST / "index.html")
    else:
        @app.get("/")
        def no_frontend():
            return JSONResponse({"error": "frontend not built — run npm run build in webapp/frontend"})

    return app


app = create_app()
