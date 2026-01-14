"""Main FastAPI application for eCFR analyzer."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import agencies, titles

# Create FastAPI app
app = FastAPI(
    title="eCFR Analyzer API",
    description="Read-only REST API for analyzing federal regulations by agency",
    version="0.0.1",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["GET"],  # Read-only API
    allow_headers=["*"],
)

# Include routers
app.include_router(agencies.router, prefix="/api/v1")
app.include_router(titles.router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
    """Root endpoint with API information.

    Returns:
        API information
    """
    return {
        "name": "eCFR Analyzer API",
        "version": "0.0.1",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy"}
