# =============================================================================
# AUDIT LOGGER
# =============================================================================
# Secure audit logging for actions and interactions
# =============================================================================

import os
import logging
import json
import hashlib
from typing import Any, Dict, Optional
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Secure audit logging for chatbot actions.
    
    Features:
    - PII-safe logging (hashes sensitive data)
    - Async database writes
    - Structured log format
    - Retention policy support
    """
    
    # Log destination settings
    _db_enabled = os.getenv("AUDIT_LOG_DB", "true").lower() == "true"
    _file_enabled = os.getenv("AUDIT_LOG_FILE", "true").lower() == "true"
    _log_file_path = os.getenv("AUDIT_LOG_PATH", "/app/logs/audit.log")
    
    # Database connection (lazy initialized)
    _db_pool = None
    
    @classmethod
    async def _get_db_pool(cls):
        """Get or create database connection pool."""
        if cls._db_pool is None and cls._db_enabled:
            try:
                import asyncpg
                
                db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/chatbot")
                cls._db_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
                
                # Ensure audit table exists
                async with cls._db_pool.acquire() as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS audit_logs (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMPTZ DEFAULT NOW(),
                            action VARCHAR(100) NOT NULL,
                            conversation_id VARCHAR(255),
                            booking_id VARCHAR(50),
                            meeting_id VARCHAR(50),
                            status VARCHAR(50),
                            data_hash VARCHAR(64),
                            metadata JSONB,
                            error TEXT,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
                        CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
                        CREATE INDEX IF NOT EXISTS idx_audit_logs_conversation ON audit_logs(conversation_id);
                    """)
                    
            except ImportError:
                logger.warning("asyncpg not installed, database logging disabled")
                cls._db_enabled = False
            except Exception as e:
                logger.error(f"Failed to initialize database pool: {e}")
                cls._db_enabled = False
        
        return cls._db_pool
    
    @classmethod
    async def log_action(
        cls,
        action: str,
        conversation_id: Optional[str] = None,
        booking_id: Optional[str] = None,
        meeting_id: Optional[str] = None,
        status: Optional[str] = None,
        data_hash: Optional[str] = None,
        metadata: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """
        Log an action to audit trail.
        
        Args:
            action: Action name (e.g., 'create_booking', 'cancel_booking')
            conversation_id: Unique conversation identifier
            booking_id: Booking reference (if applicable)
            meeting_id: Meeting reference (if applicable)
            status: Action status (success, failed, etc.)
            data_hash: Hash of sensitive data (not the data itself)
            metadata: Additional non-PII metadata
            error: Error message if action failed
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "conversation_id": conversation_id,
            "booking_id": booking_id,
            "meeting_id": meeting_id,
            "status": status,
            "data_hash": data_hash,
            "metadata": cls._sanitize_metadata(metadata),
            "error": error
        }
        
        # Log to database
        if cls._db_enabled:
            await cls._log_to_database(log_entry)
        
        # Log to file
        if cls._file_enabled:
            cls._log_to_file(log_entry)
        
        # Also log to standard logger for monitoring
        log_level = logging.ERROR if error else logging.INFO
        logger.log(log_level, f"AUDIT: {action} | status={status} | conv={conversation_id}")
    
    @classmethod
    async def log_interaction(
        cls,
        conversation_id: str,
        intent: str,
        confidence: float,
        entity_count: int = 0,
        slot_fill_status: Optional[Dict] = None
    ):
        """
        Log a conversation interaction for analytics.
        
        Args:
            conversation_id: Unique conversation identifier
            intent: Detected intent name
            confidence: Intent confidence score
            entity_count: Number of entities extracted
            slot_fill_status: Current slot fill state
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": "interaction",
            "conversation_id": conversation_id,
            "status": "logged",
            "metadata": {
                "intent": intent,
                "confidence": round(confidence, 3),
                "entity_count": entity_count,
                "slots_filled": sum(1 for v in (slot_fill_status or {}).values() if v)
            }
        }
        
        # Log to file only for interactions (high volume)
        if cls._file_enabled:
            cls._log_to_file(log_entry)
    
    @classmethod
    async def _log_to_database(cls, log_entry: Dict):
        """Write log entry to database."""
        try:
            pool = await cls._get_db_pool()
            if pool is None:
                return
            
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO audit_logs 
                    (action, conversation_id, booking_id, meeting_id, status, data_hash, metadata, error)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    log_entry.get("action"),
                    log_entry.get("conversation_id"),
                    log_entry.get("booking_id"),
                    log_entry.get("meeting_id"),
                    log_entry.get("status"),
                    log_entry.get("data_hash"),
                    json.dumps(log_entry.get("metadata")) if log_entry.get("metadata") else None,
                    log_entry.get("error")
                )
                
        except Exception as e:
            logger.error(f"Failed to write audit log to database: {e}")
    
    @classmethod
    def _log_to_file(cls, log_entry: Dict):
        """Write log entry to file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(cls._log_file_path), exist_ok=True)
            
            with open(cls._log_file_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
                
        except Exception as e:
            logger.error(f"Failed to write audit log to file: {e}")
    
    @classmethod
    def _sanitize_metadata(cls, metadata: Optional[Dict]) -> Optional[Dict]:
        """
        Sanitize metadata to remove/hash PII.
        
        Args:
            metadata: Raw metadata dict
        
        Returns:
            Sanitized metadata dict
        """
        if not metadata:
            return None
        
        sanitized = {}
        
        # Fields that should be hashed
        pii_fields = {"email", "phone", "name", "customer_name", "attendee_email"}
        
        # Fields that should be removed entirely
        remove_fields = {"password", "token", "secret", "key"}
        
        for key, value in metadata.items():
            key_lower = key.lower()
            
            if key_lower in remove_fields:
                continue
            elif key_lower in pii_fields and value:
                # Hash PII fields
                sanitized[f"{key}_hash"] = hashlib.sha256(str(value).encode()).hexdigest()[:16]
            else:
                sanitized[key] = value
        
        return sanitized
    
    @classmethod
    def hash_pii(cls, value: str) -> str:
        """
        Create a hash of PII for logging.
        
        Args:
            value: PII value to hash
        
        Returns:
            Truncated SHA256 hash
        """
        if not value:
            return ""
        return hashlib.sha256(value.encode()).hexdigest()[:16]
