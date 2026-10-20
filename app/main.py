"""UPAE FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .routers import synthesize

app = FastAPI(
    title="Unified Paleontology API Engine",
    description=(
        "Async federated gateway synthesizing paleontology, geology, "
        "biodiversity, and related upstream APIs into a single payload."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(synthesize.router)


@app.get("/")
@app.get("/api/v1/")
def index() -> dict:
    return {
        "name": "Unified Paleontology API Engine (UPAE)",
        "version": __version__,
        "mvp": True,
        "endpoint": "/api/v1/synthesize",
        "example": (
            "/api/v1/synthesize?taxon=Hadrosaurus&lat=34.55&lng=-78.45&radius_km=50"
        ),
        "live_adapters": [
            "PBDB",
            "MACROSTRAT",
            "NEOTOMA",
            "IDIGBIO",
            "MORPHOSOURCE",
            "GBIF",
            "PALEOCLIMATE",
            "CROSSREF",
            "OPENALEX",
            "MINDAT",
        ],
        "stub_adapters": [],
        "mindat_note": "Requires MINDAT_API_KEY (env, key.env, or Render secret file)",
        "openalex_note": "Optional OPENALEX_API_KEY / OPENALEX_MAILTO (mailto falls back to CROSSREF_MAILTO)",
    }
