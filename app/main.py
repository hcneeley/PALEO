"""UPAE FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .http import shutdown_http_client, startup_http_client
from .routers import occurrences, synthesize


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = await startup_http_client()
    yield
    await shutdown_http_client()


app = FastAPI(
    title="Paleontological Aggregator for Localities, Evidence & Occurrences",
    description=(
        "PALEO — async federated gateway synthesizing paleontology, geology, "
        "biodiversity, and related upstream APIs into a single payload."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(synthesize.router)
app.include_router(occurrences.router)


@app.get("/")
@app.get("/api/v1/")
def index() -> dict:
    return {
        "name": "Paleontological Aggregator for Localities, Evidence & Occurrences (PALEO)",
        "version": __version__,
        "mvp": True,
        "endpoint": "/api/v1/synthesize",
        "occurrences_page": "/api/v1/occurrences",
        "example": (
            "/api/v1/synthesize?taxon=Hadrosaurus&lat=34.55&lng=-78.45&radius_km=50"
        ),
        "example_occurrences": (
            "/api/v1/occurrences?provider=GBIF&taxon=Hadrosaurus&offset=50&limit=100"
        ),
        "live_adapters": [
            "TAXONOMY",
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
