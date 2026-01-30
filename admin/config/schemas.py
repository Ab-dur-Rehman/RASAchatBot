# =============================================================================
# ADMIN CONFIGURATION SCHEMA
# =============================================================================
# Database schema and Pydantic models for admin configuration
# =============================================================================

"""
Database Tables:
----------------
1. bot_config - Global bot settings
2. task_config - Per-task configuration
3. service_catalog - Available services
4. content_sources - Ingested content metadata
5. admin_users - Admin dashboard users
6. audit_logs - Action audit trail

This module defines:
- SQLAlchemy models for database tables
- Pydantic schemas for API validation
- Default configuration values
"""

from datetime import datetime, time
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field, EmailStr, validator


# =============================================================================
# ENUMS
# =============================================================================

class TaskStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    MAINTENANCE = "maintenance"


class ServiceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    COMING_SOON = "coming_soon"


# =============================================================================
# PYDANTIC SCHEMAS - API Models
# =============================================================================

class BusinessHours(BaseModel):
    """Business hours configuration."""
    start: str = Field("09:00", description="Opening time (HH:MM)")
    end: str = Field("18:00", description="Closing time (HH:MM)")
    
    @validator("start", "end")
    def validate_time_format(cls, v):
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            raise ValueError("Time must be in HH:MM format")


class ServiceConfig(BaseModel):
    """Individual service configuration."""
    id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Display name")
    description: Optional[str] = Field(None, description="Service description")
    price: float = Field(0, ge=0, description="Service price")
    duration_minutes: int = Field(60, ge=15, description="Service duration in minutes")
    enabled: bool = Field(True, description="Whether service is available")
    requires_confirmation: bool = Field(True, description="Requires user confirmation")
    max_party_size: int = Field(10, ge=1, description="Maximum party size")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class TaskConfigBase(BaseModel):
    """Base task configuration."""
    enabled: bool = Field(True, description="Whether task is enabled")
    required_fields: List[str] = Field(
        default_factory=list,
        description="Required form fields"
    )
    optional_fields: List[str] = Field(
        default_factory=list,
        description="Optional form fields"
    )
    business_hours: BusinessHours = Field(
        default_factory=BusinessHours,
        description="Operating hours"
    )
    blocked_dates: List[str] = Field(
        default_factory=list,
        description="Dates when service is unavailable (YYYY-MM-DD)"
    )
    
    @validator("blocked_dates", each_item=True)
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class BookingTaskConfig(TaskConfigBase):
    """Configuration specific to booking tasks."""
    task_type: str = Field("book_service", const=True)
    services: List[ServiceConfig] = Field(
        default_factory=list,
        description="Available services"
    )
    booking_window_days: int = Field(
        90, ge=1, le=365,
        description="How far in advance users can book"
    )
    confirmation_required: bool = Field(True)
    send_email_confirmation: bool = Field(True)
    cancellation_policy: Optional[str] = Field(
        "Free cancellation up to 24 hours before",
        description="Cancellation policy text"
    )
    max_reschedules: int = Field(3, ge=0, description="Maximum reschedules per booking")


class MeetingTaskConfig(TaskConfigBase):
    """Configuration specific to meeting tasks."""
    task_type: str = Field("schedule_meeting", const=True)
    meeting_types: List[str] = Field(
        default_factory=lambda: ["Sales call", "Technical consultation", "General inquiry"],
        description="Available meeting types"
    )
    durations: List[str] = Field(
        default_factory=lambda: ["15 minutes", "30 minutes", "1 hour"],
        description="Available meeting durations"
    )
    send_calendar_invite: bool = Field(True)
    require_notes: bool = Field(False, description="Whether meeting notes are required")


class CancelTaskConfig(BaseModel):
    """Configuration for cancellation tasks."""
    task_type: str = Field("cancel_booking", const=True)
    enabled: bool = Field(True)
    require_confirmation: bool = Field(True)
    cancellation_policy: str = Field("Free cancellation up to 24 hours before")


class TaskConfigCreate(BaseModel):
    """Schema for creating/updating task configuration."""
    task_name: str = Field(..., description="Task identifier")
    config: Union[BookingTaskConfig, MeetingTaskConfig, CancelTaskConfig, TaskConfigBase]


class TaskConfigResponse(BaseModel):
    """Schema for task configuration API response."""
    task_name: str
    config: Dict[str, Any]
    updated_at: datetime
    updated_by: Optional[str]


# =============================================================================
# GLOBAL BOT CONFIGURATION
# =============================================================================

class BotConfig(BaseModel):
    """Global bot configuration."""
    bot_name: str = Field("Assistant", description="Bot display name")
    welcome_message: str = Field(
        "Hello! How can I help you today?",
        description="Initial greeting message"
    )
    fallback_message: str = Field(
        "I'm not sure I understood that. Could you rephrase?",
        description="Fallback response for unrecognized inputs"
    )
    handoff_enabled: bool = Field(True, description="Enable human handoff")
    handoff_message: str = Field(
        "Let me connect you with a human agent.",
        description="Message when initiating handoff"
    )
    contact_email: EmailStr = Field(..., description="Support email")
    contact_phone: str = Field(..., description="Support phone")
    business_name: str = Field(..., description="Business name")
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    timezone: str = Field("America/New_York", description="Business timezone")


# =============================================================================
# CONTENT SOURCE CONFIGURATION
# =============================================================================

class ContentSource(BaseModel):
    """Content source for knowledge base."""
    id: str
    name: str
    source_type: str = Field(..., description="file, url, or api")
    location: str = Field(..., description="Path or URL")
    collection: str = Field("website_content", description="Vector store collection")
    last_ingested: Optional[datetime] = None
    document_count: int = 0
    enabled: bool = True


# =============================================================================
# ADMIN USER
# =============================================================================

class AdminUserCreate(BaseModel):
    """Schema for creating admin users."""
    email: EmailStr
    name: str
    password: str = Field(..., min_length=8)
    role: str = Field("editor", description="admin, editor, or viewer")


class AdminUser(BaseModel):
    """Admin user response schema."""
    id: int
    email: EmailStr
    name: str
    role: str
    created_at: datetime
    last_login: Optional[datetime]


# =============================================================================
# DEFAULT CONFIGURATIONS
# =============================================================================

DEFAULT_TASK_CONFIGS = {
    "book_service": BookingTaskConfig(
        enabled=True,
        required_fields=["service_type", "date", "time", "name", "email", "phone"],
        optional_fields=["party_size", "notes"],
        services=[
            ServiceConfig(
                id="consultation",
                name="Consultation",
                description="Expert consultation session",
                price=50.00,
                duration_minutes=60,
                enabled=True
            ),
            ServiceConfig(
                id="demo",
                name="Demo",
                description="Product demonstration",
                price=0.00,
                duration_minutes=30,
                enabled=True
            ),
            ServiceConfig(
                id="support",
                name="Support Session",
                description="Technical support session",
                price=75.00,
                duration_minutes=60,
                enabled=True
            )
        ],
        booking_window_days=90,
        confirmation_required=True,
        send_email_confirmation=True
    ).dict(),
    
    "schedule_meeting": MeetingTaskConfig(
        enabled=True,
        required_fields=["meeting_type", "date", "time", "duration", "email"],
        optional_fields=["notes"],
        meeting_types=["Sales call", "Technical consultation", "General inquiry"],
        durations=["15 minutes", "30 minutes", "1 hour"],
        send_calendar_invite=True
    ).dict(),
    
    "cancel_booking": CancelTaskConfig(
        enabled=True,
        require_confirmation=True,
        cancellation_policy="Free cancellation up to 24 hours before"
    ).dict(),
    
    "reschedule_booking": {
        "enabled": True,
        "require_confirmation": True,
        "max_reschedules": 3
    },
    
    "check_booking": {
        "enabled": True
    }
}

DEFAULT_BOT_CONFIG = BotConfig(
    bot_name="Business Assistant",
    welcome_message="Hello! 👋 Welcome to our business. I can help you with information about our services, pricing, and I can also help you book appointments. What can I do for you today?",
    fallback_message="I'm not sure I understood that. I can help with questions about our services, pricing, business hours, or help you book an appointment. What would you like to know?",
    handoff_enabled=True,
    handoff_message="I understand you'd like to speak with a human. Let me connect you with our support team.",
    contact_email="support@example.com",
    contact_phone="(555) 123-4567",
    business_name="Example Business",
    timezone="America/New_York"
).dict()
