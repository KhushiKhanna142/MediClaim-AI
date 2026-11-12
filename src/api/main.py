"""FastAPI application entrypoint for MediClaim-AI."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router

app = FastAPI(
    title="MediClaim-AI API",
    description="Automated & Auditable Health Insurance Claim Adjudication API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount under /api for React frontend and also at root for direct API clients
app.include_router(router, prefix="/api")
app.include_router(router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "MediClaim-AI API", "version": "1.0.0"}


# Serve built React frontend if available
_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST_DIR.exists():
    assets_dir = _DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def serve_spa():
        return FileResponse(str(_DIST_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
