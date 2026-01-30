# =============================================================================
# ADMIN API ROUTES
# =============================================================================
# FastAPI routes for admin dashboard configuration management
# =============================================================================

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncpg

from .schemas import (
    BotConfig,
    TaskConfigCreate,
    TaskConfigResponse,
    ServiceConfig,
    ContentSource,
    AdminUser,
    AdminUserCreate,
    DEFAULT_TASK_CONFIGS,
    DEFAULT_BOT_CONFIG
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
security = HTTPBearer()


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

async def get_db_pool():
    """Get database connection pool."""
    import os
    pool = await asyncpg.create_pool(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "chatbot_admin"),
        user=os.getenv("DB_USER", "chatbot"),
        password=os.getenv("DB_PASSWORD", "chatbot_pass"),
        min_size=5,
        max_size=20
    )
    return pool

# Global pool (initialize in app startup)
db_pool: Optional[asyncpg.Pool] = None


async def get_db():
    """Dependency for database connection."""
    global db_pool
    if db_pool is None:
        db_pool = await get_db_pool()
    async with db_pool.acquire() as conn:
        yield conn


# =============================================================================
# AUTH DEPENDENCY (Simplified - use proper JWT in production)
# =============================================================================

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin token."""
    # In production, verify JWT token here
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    # Return user info from token
    return {"user_id": 1, "email": "admin@example.com", "role": "admin"}


# =============================================================================
# BOT CONFIGURATION ENDPOINTS
# =============================================================================

@router.get("/config/bot", response_model=Dict[str, Any])
async def get_bot_config(
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Get global bot configuration."""
    row = await conn.fetchrow("SELECT * FROM bot_config WHERE id = 1")
    if not row:
        return DEFAULT_BOT_CONFIG
    return dict(row)


@router.put("/config/bot", response_model=Dict[str, Any])
async def update_bot_config(
    config: BotConfig,
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
):
    """Update global bot configuration."""
    await conn.execute("""
        UPDATE bot_config SET
            bot_name = $1,
            welcome_message = $2,
            fallback_message = $3,
            handoff_enabled = $4,
            handoff_message = $5,
            contact_email = $6,
            contact_phone = $7,
            business_name = $8,
            timezone = $9,
            business_hours = $10,
            updated_by = $11
        WHERE id = 1
    """,
        config.bot_name,
        config.welcome_message,
        config.fallback_message,
        config.handoff_enabled,
        config.handoff_message,
        config.contact_email,
        config.contact_phone,
        config.business_name,
        config.timezone,
        config.business_hours.dict(),
        user.get("email")
    )
    
    # Invalidate cache
    await invalidate_config_cache("bot_config")
    
    return config.dict()


# =============================================================================
# TASK CONFIGURATION ENDPOINTS
# =============================================================================

@router.get("/config/tasks", response_model=List[TaskConfigResponse])
async def get_all_task_configs(
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Get all task configurations."""
    rows = await conn.fetch("SELECT * FROM task_config ORDER BY task_name")
    return [
        TaskConfigResponse(
            task_name=row["task_name"],
            config=row["config"],
            updated_at=row["updated_at"],
            updated_by=row["updated_by"]
        )
        for row in rows
    ]


@router.get("/config/tasks/{task_name}", response_model=TaskConfigResponse)
async def get_task_config(
    task_name: str,
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Get specific task configuration."""
    row = await conn.fetchrow(
        "SELECT * FROM task_config WHERE task_name = $1",
        task_name
    )
    if not row:
        # Return default if exists
        if task_name in DEFAULT_TASK_CONFIGS:
            return TaskConfigResponse(
                task_name=task_name,
                config=DEFAULT_TASK_CONFIGS[task_name],
                updated_at=datetime.utcnow(),
                updated_by=None
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_name}' not found"
        )
    return TaskConfigResponse(
        task_name=row["task_name"],
        config=row["config"],
        updated_at=row["updated_at"],
        updated_by=row["updated_by"]
    )


@router.put("/config/tasks/{task_name}", response_model=TaskConfigResponse)
async def update_task_config(
    task_name: str,
    config_data: TaskConfigCreate,
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
):
    """Update task configuration."""
    config_dict = config_data.config.dict()
    
    await conn.execute("""
        INSERT INTO task_config (task_name, enabled, config, updated_by)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (task_name) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            config = EXCLUDED.config,
            updated_by = EXCLUDED.updated_by
    """,
        task_name,
        config_dict.get("enabled", True),
        config_dict,
        user.get("email")
    )
    
    # Invalidate cache
    await invalidate_config_cache(f"task_config:{task_name}")
    
    row = await conn.fetchrow(
        "SELECT * FROM task_config WHERE task_name = $1",
        task_name
    )
    return TaskConfigResponse(
        task_name=row["task_name"],
        config=row["config"],
        updated_at=row["updated_at"],
        updated_by=row["updated_by"]
    )


@router.patch("/config/tasks/{task_name}/toggle", response_model=Dict[str, Any])
async def toggle_task(
    task_name: str,
    enabled: bool = Query(..., description="Enable or disable task"),
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
):
    """Enable or disable a specific task."""
    await conn.execute("""
        UPDATE task_config SET enabled = $1, updated_by = $2
        WHERE task_name = $3
    """, enabled, user.get("email"), task_name)
    
    await invalidate_config_cache(f"task_config:{task_name}")
    
    return {"task_name": task_name, "enabled": enabled}


# =============================================================================
# SERVICE CATALOG ENDPOINTS
# =============================================================================

@router.get("/services", response_model=List[Dict[str, Any]])
async def get_services(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Get all services."""
    if status_filter:
        rows = await conn.fetch(
            "SELECT * FROM service_catalog WHERE status = $1 ORDER BY name",
            status_filter
        )
    else:
        rows = await conn.fetch("SELECT * FROM service_catalog ORDER BY name")
    return [dict(row) for row in rows]


@router.post("/services", response_model=Dict[str, Any])
async def create_service(
    service: ServiceConfig,
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Create a new service."""
    try:
        await conn.execute("""
            INSERT INTO service_catalog (
                id, name, description, price, duration_minutes,
                status, requires_confirmation, max_party_size, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
            service.id,
            service.name,
            service.description,
            service.price,
            service.duration_minutes,
            "active" if service.enabled else "inactive",
            service.requires_confirmation,
            service.max_party_size,
            service.metadata or {}
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service with ID '{service.id}' already exists"
        )
    
    return service.dict()


@router.put("/services/{service_id}", response_model=Dict[str, Any])
async def update_service(
    service_id: str,
    service: ServiceConfig,
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Update an existing service."""
    result = await conn.execute("""
        UPDATE service_catalog SET
            name = $1,
            description = $2,
            price = $3,
            duration_minutes = $4,
            status = $5,
            requires_confirmation = $6,
            max_party_size = $7,
            metadata = $8
        WHERE id = $9
    """,
        service.name,
        service.description,
        service.price,
        service.duration_minutes,
        "active" if service.enabled else "inactive",
        service.requires_confirmation,
        service.max_party_size,
        service.metadata or {},
        service_id
    )
    
    if result == "UPDATE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_id}' not found"
        )
    
    await invalidate_config_cache("services")
    return service.dict()


@router.delete("/services/{service_id}")
async def delete_service(
    service_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Delete a service (soft delete by setting inactive)."""
    await conn.execute(
        "UPDATE service_catalog SET status = 'inactive' WHERE id = $1",
        service_id
    )
    return {"status": "deleted", "service_id": service_id}


# =============================================================================
# CONTENT SOURCES ENDPOINTS
# =============================================================================

@router.get("/content-sources", response_model=List[Dict[str, Any]])
async def get_content_sources(
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Get all content sources."""
    rows = await conn.fetch("SELECT * FROM content_sources ORDER BY name")
    return [dict(row) for row in rows]


@router.post("/content-sources", response_model=Dict[str, Any])
async def add_content_source(
    source: ContentSource,
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Add a new content source."""
    await conn.execute("""
        INSERT INTO content_sources (
            id, name, source_type, location, collection_name, enabled
        ) VALUES ($1, $2, $3, $4, $5, $6)
    """,
        source.id,
        source.name,
        source.source_type,
        source.location,
        source.collection,
        source.enabled
    )
    return source.dict()


@router.post("/content-sources/{source_id}/ingest")
async def trigger_ingestion(
    source_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Trigger content ingestion for a source."""
    # Get source details
    row = await conn.fetchrow(
        "SELECT * FROM content_sources WHERE id = $1",
        source_id
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Content source '{source_id}' not found"
        )
    
    # In production, trigger async ingestion job
    # For now, just return acknowledgment
    return {
        "status": "queued",
        "source_id": source_id,
        "message": "Ingestion job has been queued"
    }


# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================

@router.get("/analytics/summary")
async def get_analytics_summary(
    days: int = Query(7, ge=1, le=90),
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Get analytics summary for the specified period."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    rows = await conn.fetch("""
        SELECT * FROM conversation_analytics
        WHERE date >= $1
        ORDER BY date DESC
    """, start_date.date())
    
    if not rows:
        return {
            "period_days": days,
            "total_conversations": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "daily_breakdown": []
        }
    
    total_conversations = sum(row["total_conversations"] for row in rows)
    successful_tasks = sum(row["successful_tasks"] for row in rows)
    failed_tasks = sum(row["failed_tasks"] for row in rows)
    
    return {
        "period_days": days,
        "total_conversations": total_conversations,
        "successful_tasks": successful_tasks,
        "failed_tasks": failed_tasks,
        "success_rate": successful_tasks / (successful_tasks + failed_tasks) if (successful_tasks + failed_tasks) > 0 else 0,
        "daily_breakdown": [dict(row) for row in rows]
    }


@router.get("/analytics/audit-logs")
async def get_audit_logs(
    action_type: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
):
    """Get audit logs with filtering."""
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    param_count = 0
    
    if action_type:
        param_count += 1
        query += f" AND action_type = ${param_count}"
        params.append(action_type)
    
    if success is not None:
        param_count += 1
        query += f" AND success = ${param_count}"
        params.append(success)
    
    param_count += 1
    query += f" ORDER BY timestamp DESC LIMIT ${param_count}"
    params.append(limit)
    
    param_count += 1
    query += f" OFFSET ${param_count}"
    params.append(offset)
    
    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


# =============================================================================
# CACHE INVALIDATION HELPER
# =============================================================================

async def invalidate_config_cache(key: str):
    """Invalidate Redis cache for configuration."""
    import aioredis
    import os
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis = await aioredis.from_url(redis_url)
        await redis.delete(f"config:{key}")
        await redis.close()
    except Exception:
        # Log but don't fail if cache invalidation fails
        pass
