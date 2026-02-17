"""
FastAPI Application Entry Point

Configures the application with middleware, routers, and lifecycle events.
"""
# RAG assistant support added

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import settings
from app.db.mongo import mongodb
from app.db.es import es_client
from app.api.v1.auth import router as auth_router
from app.api.v1.sources import router as sources_router
from app.api.v1.news import router as news_router
from app.api.v1.search import router as search_router
from app.api.v1.tags import router as tags_router
from app.api.v1.assistant import router as assistant_router
from app.services.scheduler import setup_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.

    Handles startup and shutdown events for database connections.
    """
    # === Startup ===
    logger.info(f"Starting {settings.app_name}...")

    # Connect to databases
    await mongodb.connect()
    await mongodb.create_indexes()

    try:
        await es_client.connect()
    except Exception as e:
        logger.warning(f"Elasticsearch not available: {e}")
        logger.warning("Search features will be disabled")

    # Start background scheduler
    setup_scheduler()

    logger.info(f"{settings.app_name} started successfully")

    yield

    # Shutdown scheduler
    shutdown_scheduler()

    # === Shutdown ===
    logger.info(f"Shutting down {settings.app_name}...")

    await es_client.disconnect()
    await mongodb.disconnect()

    logger.info(f"{settings.app_name} shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="A modern news aggregation platform with multi-source collection and intelligent search",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# === Middleware ===

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions with unified response format."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "Internal server error", "data": None},
    )


# === Routes ===


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "code": 200,
        "message": "ok",
        "data": {"status": "healthy", "app": settings.app_name, "version": "1.0.0"},
    }


# API v1 routes
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(sources_router, prefix=settings.api_v1_prefix)
app.include_router(news_router, prefix=settings.api_v1_prefix)
app.include_router(search_router, prefix=settings.api_v1_prefix)
app.include_router(tags_router, prefix=settings.api_v1_prefix)
app.include_router(assistant_router, prefix=settings.api_v1_prefix)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
