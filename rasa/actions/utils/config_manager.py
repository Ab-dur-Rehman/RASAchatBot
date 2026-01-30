# =============================================================================
# CONFIGURATION MANAGER
# =============================================================================
# Manages runtime task configuration with caching
# =============================================================================

import os
import logging
import json
from typing import Any, Dict, Optional
import asyncio
import aiohttp
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Manages task configuration with caching.
    
    Configuration hierarchy:
    1. Redis cache (TTL: 5 minutes)
    2. Admin API
    3. Default config file
    
    Features:
    - Automatic cache invalidation
    - Fallback to defaults on API failure
    - Config change notifications (optional)
    """
    
    # Class-level cache to share across instances
    _cache: Dict[str, Dict] = {}
    _cache_timestamps: Dict[str, datetime] = {}
    _cache_ttl = timedelta(minutes=5)
    
    def __init__(self):
        self.admin_api_url = os.getenv("ADMIN_API_URL", "http://admin-api:8000")
        self.api_key = os.getenv("ADMIN_API_KEY", "")
        self.use_redis = os.getenv("USE_REDIS_CACHE", "true").lower() == "true"
        
        # Redis connection (if available)
        self._redis = None
        if self.use_redis:
            self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis connection for caching."""
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/2")
            self._redis = redis.from_url(redis_url)
        except ImportError:
            logger.warning("Redis package not installed, using in-memory cache")
            self._redis = None
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            self._redis = None
    
    async def get_task_config(self, task_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific task.
        
        Args:
            task_name: Name of the task (e.g., 'book_service', 'schedule_meeting')
        
        Returns:
            Task configuration dictionary
        """
        cache_key = f"config:{task_name}"
        
        # Check in-memory cache first
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Check Redis cache
        if self._redis:
            try:
                cached = self._redis.get(cache_key)
                if cached:
                    config = json.loads(cached)
                    self._update_local_cache(cache_key, config)
                    return config
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")
        
        # Fetch from Admin API
        config = await self._fetch_from_api(task_name)
        
        if config:
            self._update_cache(cache_key, config)
            return config
        
        # Fallback to default config
        return self._get_default_config(task_name)
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached config is still valid."""
        if cache_key not in self._cache:
            return False
        
        timestamp = self._cache_timestamps.get(cache_key)
        if not timestamp:
            return False
        
        return datetime.now() - timestamp < self._cache_ttl
    
    def _update_local_cache(self, cache_key: str, config: Dict):
        """Update in-memory cache."""
        self._cache[cache_key] = config
        self._cache_timestamps[cache_key] = datetime.now()
    
    def _update_cache(self, cache_key: str, config: Dict):
        """Update both Redis and local cache."""
        self._update_local_cache(cache_key, config)
        
        if self._redis:
            try:
                self._redis.setex(
                    cache_key,
                    int(self._cache_ttl.total_seconds()),
                    json.dumps(config)
                )
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")
    
    async def _fetch_from_api(self, task_name: str) -> Optional[Dict]:
        """Fetch config from Admin API."""
        try:
            url = f"{self.admin_api_url}/config/tasks/{task_name}"
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=5) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Config API returned {response.status}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.warning("Config API request timed out")
            return None
        except Exception as e:
            logger.warning(f"Error fetching config from API: {e}")
            return None
    
    def _get_default_config(self, task_name: str) -> Dict[str, Any]:
        """Return default configuration for a task."""
        
        defaults = {
            "book_service": {
                "enabled": True,
                "required_fields": ["service_type", "date", "time", "name", "email", "phone"],
                "optional_fields": ["party_size", "notes"],
                "business_hours": {"start": "09:00", "end": "18:00"},
                "blocked_dates": [],
                "booking_window_days": 90,
                "services": [
                    {"id": "consultation", "name": "Consultation", "price": 50, "enabled": True},
                    {"id": "demo", "name": "Demo", "price": 0, "enabled": True},
                    {"id": "support", "name": "Support Session", "price": 75, "enabled": True}
                ],
                "confirmation_required": True,
                "send_email_confirmation": True
            },
            "schedule_meeting": {
                "enabled": True,
                "required_fields": ["meeting_type", "date", "time", "duration", "email"],
                "optional_fields": ["notes"],
                "business_hours": {"start": "09:00", "end": "17:00"},
                "blocked_dates": [],
                "meeting_types": ["Sales call", "Technical consultation", "General inquiry"],
                "durations": ["15 minutes", "30 minutes", "1 hour"],
                "confirmation_required": True,
                "send_calendar_invite": True
            },
            "cancel_booking": {
                "enabled": True,
                "require_confirmation": True,
                "cancellation_policy": "Free cancellation up to 24 hours before"
            },
            "reschedule_booking": {
                "enabled": True,
                "require_confirmation": True,
                "max_reschedules": 3
            },
            "check_booking": {
                "enabled": True
            }
        }
        
        return defaults.get(task_name, {"enabled": True})
    
    async def invalidate_cache(self, task_name: Optional[str] = None):
        """
        Invalidate cached configuration.
        
        Args:
            task_name: Specific task to invalidate, or None for all
        """
        if task_name:
            cache_key = f"config:{task_name}"
            self._cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)
            
            if self._redis:
                try:
                    self._redis.delete(cache_key)
                except Exception as e:
                    logger.warning(f"Error invalidating Redis cache: {e}")
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            
            if self._redis:
                try:
                    keys = self._redis.keys("config:*")
                    if keys:
                        self._redis.delete(*keys)
                except Exception as e:
                    logger.warning(f"Error clearing Redis cache: {e}")
    
    async def get_all_task_configs(self) -> Dict[str, Dict]:
        """Get configuration for all tasks."""
        task_names = [
            "book_service",
            "schedule_meeting",
            "cancel_booking",
            "reschedule_booking",
            "check_booking"
        ]
        
        configs = {}
        for task_name in task_names:
            configs[task_name] = await self.get_task_config(task_name)
        
        return configs
