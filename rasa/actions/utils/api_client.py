# =============================================================================
# BACKEND API CLIENT
# =============================================================================
# Async HTTP client for backend API communication with retry logic
# =============================================================================

import os
import logging
import asyncio
from typing import Any, Dict, Optional
import aiohttp
from aiohttp import ClientTimeout

logger = logging.getLogger(__name__)


class BackendAPIClient:
    """
    Async HTTP client for backend API communication.
    
    Features:
    - Automatic retry with exponential backoff
    - JWT/API key authentication
    - Request/response logging
    - Timeout handling
    """
    
    def __init__(self):
        self.base_url = os.getenv("BACKEND_API_URL", "http://backend:8080/api")
        self.api_key = os.getenv("BACKEND_API_KEY", "")
        self.jwt_token = os.getenv("BACKEND_JWT_TOKEN", "")
        self.timeout = ClientTimeout(total=30)
        self.max_retries = 3
        self.retry_delay = 1  # seconds
    
    def _get_headers(self) -> Dict[str, str]:
        """Construct request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Source": "chatbot"
        }
        
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        elif self.api_key:
            headers["X-API-Key"] = self.api_key
        
        return headers
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            data: Request body for POST/PUT
            params: Query parameters
        
        Returns:
            Response data as dictionary
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.request(
                        method=method,
                        url=url,
                        json=data,
                        params=params,
                        headers=self._get_headers()
                    ) as response:
                        
                        response_data = await response.json()
                        
                        if response.status >= 200 and response.status < 300:
                            return {"success": True, **response_data}
                        elif response.status == 404:
                            return {"success": False, "error": "Resource not found"}
                        elif response.status == 401:
                            logger.error("API authentication failed")
                            return {"success": False, "error": "Authentication failed"}
                        elif response.status == 429:
                            # Rate limited - wait and retry
                            retry_after = int(response.headers.get("Retry-After", 5))
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            error_msg = response_data.get("error", f"HTTP {response.status}")
                            return {"success": False, "error": error_msg}
                            
            except asyncio.TimeoutError:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    continue
                return {"success": False, "error": "Request timed out"}
                
            except aiohttp.ClientError as e:
                logger.error(f"Client error: {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    continue
                return {"success": False, "error": "Connection error"}
                
            except Exception as e:
                logger.exception(f"Unexpected error in API request: {str(e)}")
                return {"success": False, "error": "Internal error"}
        
        return {"success": False, "error": "Max retries exceeded"}
    
    # =========================================================================
    # BOOKING ENDPOINTS
    # =========================================================================
    
    async def create_booking(self, booking_data: Dict) -> Dict[str, Any]:
        """Create a new booking."""
        return await self._make_request("POST", "/bookings", data=booking_data)
    
    async def get_booking(self, booking_id: str) -> Dict[str, Any]:
        """Retrieve a booking by ID."""
        return await self._make_request("GET", f"/bookings/{booking_id}")
    
    async def cancel_booking(self, booking_id: str) -> Dict[str, Any]:
        """Cancel an existing booking."""
        return await self._make_request("DELETE", f"/bookings/{booking_id}")
    
    async def reschedule_booking(
        self,
        booking_id: str,
        new_date: str,
        new_time: str
    ) -> Dict[str, Any]:
        """Reschedule a booking to a new date/time."""
        data = {"date": new_date, "time": new_time}
        return await self._make_request("PUT", f"/bookings/{booking_id}", data=data)
    
    async def get_available_slots(
        self,
        service_type: Optional[str] = None,
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get available booking slots."""
        params = {}
        if service_type:
            params["service"] = service_type
        if date:
            params["date"] = date
        return await self._make_request("GET", "/bookings/availability", params=params)
    
    # =========================================================================
    # MEETING ENDPOINTS
    # =========================================================================
    
    async def schedule_meeting(self, meeting_data: Dict) -> Dict[str, Any]:
        """Schedule a new meeting."""
        return await self._make_request("POST", "/meetings", data=meeting_data)
    
    async def get_available_meeting_times(
        self,
        meeting_type: Optional[str] = None,
        date: Optional[str] = None,
        duration: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get available meeting times."""
        params = {}
        if meeting_type:
            params["type"] = meeting_type
        if date:
            params["date"] = date
        if duration:
            params["duration"] = duration
        return await self._make_request("GET", "/meetings/availability", params=params)
    
    # =========================================================================
    # HEALTH CHECK
    # =========================================================================
    
    async def health_check(self) -> bool:
        """Check if the backend API is healthy."""
        try:
            result = await self._make_request("GET", "/health")
            return result.get("success", False)
        except Exception:
            return False
