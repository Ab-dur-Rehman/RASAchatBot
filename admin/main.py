# =============================================================================
# Admin API Main Application
# =============================================================================
# FastAPI application entry point
# =============================================================================

from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import os

from .config.api import router as config_router


# Database pool
db_pool: asyncpg.Pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    global db_pool
    
    # Startup
    db_pool = await asyncpg.create_pool(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "chatbot"),
        user=os.getenv("DB_USER", "rasa"),
        password=os.getenv("DB_PASSWORD", "rasa_password"),
        min_size=5,
        max_size=20
    )
    
    # Import and set pool in config module
    from .config import api
    api.db_pool = db_pool
    
    yield
    
    # Shutdown
    if db_pool:
        await db_pool.close()


# Create application
app = FastAPI(
    title="Chatbot Admin API",
    description="Configuration and management API for RASA chatbot",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(config_router)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint."""
    return {
        "service": "Chatbot Admin API",
        "version": "1.0.0",
        "docs": "/docs"
    }
