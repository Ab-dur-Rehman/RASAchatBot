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
# LLM CONFIGURATION
# =============================================================================

class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    GOOGLE = "google"
    CUSTOM = "custom"


class LLMConfig(BaseModel):
    """LLM configuration for AI-powered chat."""
    enabled: bool = Field(True, description="Enable LLM-based responses")
    provider: LLMProvider = Field(LLMProvider.OPENAI, description="LLM provider")
    model: str = Field("gpt-4o-mini", description="Model identifier")
    api_key: Optional[str] = Field(None, description="API key (encrypted in DB)")
    api_base_url: Optional[str] = Field(None, description="Custom API base URL (for Ollama/Azure)")
    temperature: float = Field(0.7, ge=0, le=2, description="Response creativity (0-2)")
    max_tokens: int = Field(500, ge=50, le=4000, description="Maximum response tokens")
    system_prompt: str = Field(
        "You are a helpful business assistant. Answer questions based on the provided context. "
        "If you don't know the answer, say so politely. Keep responses concise and professional.",
        description="System prompt for the LLM"
    )
    use_knowledge_base: bool = Field(True, description="Use RAG for context")
    fallback_to_llm: bool = Field(True, description="Use LLM when RASA confidence is low")
    confidence_threshold: float = Field(0.6, ge=0, le=1, description="RASA confidence threshold for LLM fallback")


class LLMConfigCreate(BaseModel):
    """Schema for creating/updating LLM configuration."""
    enabled: Optional[bool] = None
    provider: Optional[LLMProvider] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    use_knowledge_base: Optional[bool] = None
    fallback_to_llm: Optional[bool] = None
    confidence_threshold: Optional[float] = None


class KnowledgeBaseDocument(BaseModel):
    """Document in the knowledge base."""
    id: str
    filename: str
    file_type: str
    content_preview: Optional[str] = None
    chunk_count: int = 0
    status: str = Field("pending", description="pending, processing, ready, error")
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class KnowledgeBaseStats(BaseModel):
    """Knowledge base statistics."""
    total_documents: int = 0
    total_chunks: int = 0
    collections: List[str] = []
    last_updated: Optional[datetime] = None


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


# =============================================================================
# DEFAULT LLM CONFIGURATION
# =============================================================================

DEFAULT_LLM_CONFIG = LLMConfig(
    enabled=False,
    provider=LLMProvider.OPENAI,
    model="gpt-4o-mini",
    api_key=None,
    temperature=0.7,
    max_tokens=500,
    system_prompt="You are a helpful business assistant. Answer questions based on the provided context. If you don't know the answer, say so politely. Keep responses concise and professional.",
    use_knowledge_base=True,
    fallback_to_llm=True,
    confidence_threshold=0.6
).dict()
