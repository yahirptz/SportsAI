"""EdgeIQ FastAPI application entry point.

Run locally with:

    uvicorn app.main:app --reload

Interactive docs at http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.db import init_db

init_db()  # create tracking tables if they don't exist (idempotent)

app = FastAPI(
    title="EdgeIQ — Sports Intelligence Platform",
    version=settings.version,
    description=(
        "Same-game parlay intelligence built on verified last-N floor data, "
        "live enrichment, and a self-improving agent loop."
    ),
)

# Frontend (Next.js dev server) origin; tighten for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "EdgeIQ",
        "tagline": "The Intelligent Edge",
        "docs": "/docs",
        "api": "/api",
    }
