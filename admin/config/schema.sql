-- =============================================================================
-- ADMIN DATABASE SCHEMA
-- =============================================================================
-- PostgreSQL schema for admin configuration and audit logging
-- Run this to initialize the admin database
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- BOT CONFIGURATION TABLE
-- =============================================================================
-- Global bot settings (single row configuration)

CREATE TABLE IF NOT EXISTS bot_config (
    id SERIAL PRIMARY KEY,
    bot_name VARCHAR(100) NOT NULL DEFAULT 'Assistant',
    welcome_message TEXT NOT NULL DEFAULT 'Hello! How can I help you today?',
    fallback_message TEXT NOT NULL DEFAULT 'I''m not sure I understood that. Could you rephrase?',
    handoff_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    handoff_message TEXT NOT NULL DEFAULT 'Let me connect you with a human agent.',
    contact_email VARCHAR(255) NOT NULL,
    contact_phone VARCHAR(50) NOT NULL,
    business_name VARCHAR(255) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'America/New_York',
    business_hours JSONB NOT NULL DEFAULT '{"start": "09:00", "end": "18:00"}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(255),
    CONSTRAINT single_config CHECK (id = 1)
);

-- Create single config row if not exists
INSERT INTO bot_config (id, contact_email, contact_phone, business_name)
VALUES (1, 'support@example.com', '(555) 123-4567', 'Example Business')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- TASK CONFIGURATION TABLE
-- =============================================================================
-- Per-task configuration settings

CREATE TABLE IF NOT EXISTS task_config (
    id SERIAL PRIMARY KEY,
    task_name VARCHAR(100) NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(255)
);

-- Index for quick task lookup
CREATE INDEX IF NOT EXISTS idx_task_config_name ON task_config(task_name);
CREATE INDEX IF NOT EXISTS idx_task_config_enabled ON task_config(enabled);

-- Insert default task configurations
INSERT INTO task_config (task_name, enabled, config) VALUES
('book_service', TRUE, '{
    "required_fields": ["service_type", "date", "time", "name", "email", "phone"],
    "optional_fields": ["party_size", "notes"],
    "business_hours": {"start": "09:00", "end": "18:00"},
    "blocked_dates": [],
    "booking_window_days": 90,
    "confirmation_required": true,
    "send_email_confirmation": true,
    "cancellation_policy": "Free cancellation up to 24 hours before"
}'::jsonb),
('schedule_meeting', TRUE, '{
    "required_fields": ["meeting_type", "date", "time", "duration", "email"],
    "optional_fields": ["notes"],
    "business_hours": {"start": "09:00", "end": "18:00"},
    "blocked_dates": [],
    "meeting_types": ["Sales call", "Technical consultation", "General inquiry"],
    "durations": ["15 minutes", "30 minutes", "1 hour"],
    "send_calendar_invite": true
}'::jsonb),
('cancel_booking', TRUE, '{
    "require_confirmation": true,
    "cancellation_policy": "Free cancellation up to 24 hours before"
}'::jsonb),
('reschedule_booking', TRUE, '{
    "require_confirmation": true,
    "max_reschedules": 3
}'::jsonb),
('check_booking', TRUE, '{}'::jsonb)
ON CONFLICT (task_name) DO NOTHING;

-- =============================================================================
-- SERVICE CATALOG TABLE
-- =============================================================================
-- Available services for booking

CREATE TABLE IF NOT EXISTS service_catalog (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    duration_minutes INTEGER NOT NULL DEFAULT 60,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    requires_confirmation BOOLEAN NOT NULL DEFAULT TRUE,
    max_party_size INTEGER NOT NULL DEFAULT 10,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN ('active', 'inactive', 'coming_soon')),
    CONSTRAINT valid_duration CHECK (duration_minutes >= 15),
    CONSTRAINT valid_party_size CHECK (max_party_size >= 1)
);

-- Insert default services
INSERT INTO service_catalog (id, name, description, price, duration_minutes) VALUES
('consultation', 'Consultation', 'Expert consultation session', 50.00, 60),
('demo', 'Demo', 'Product demonstration', 0.00, 30),
('support', 'Support Session', 'Technical support session', 75.00, 60)
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- CONTENT SOURCES TABLE
-- =============================================================================
-- Metadata for ingested knowledge base content

CREATE TABLE IF NOT EXISTS content_sources (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    location TEXT NOT NULL,
    collection_name VARCHAR(100) NOT NULL DEFAULT 'website_content',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_ingested TIMESTAMP WITH TIME ZONE,
    document_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_source_type CHECK (source_type IN ('file', 'url', 'api', 'directory'))
);

-- =============================================================================
-- ADMIN USERS TABLE
-- =============================================================================
-- Dashboard admin users

CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'editor',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    CONSTRAINT valid_role CHECK (role IN ('admin', 'editor', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email);

-- =============================================================================
-- AUDIT LOGS TABLE
-- =============================================================================
-- Comprehensive audit trail

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    session_id VARCHAR(255),
    action_type VARCHAR(100) NOT NULL,
    action_name VARCHAR(100) NOT NULL,
    user_type VARCHAR(50) NOT NULL DEFAULT 'visitor',
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,
    input_data JSONB DEFAULT '{}'::jsonb,
    output_data JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT
);

-- Indexes for audit log queries
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action_type, action_name);
CREATE INDEX IF NOT EXISTS idx_audit_success ON audit_logs(success);

-- Partition audit logs by month for performance (PostgreSQL 10+)
-- Uncomment if using partitioning
-- CREATE TABLE audit_logs_y2024m01 PARTITION OF audit_logs
--     FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- =============================================================================
-- CONVERSATION ANALYTICS TABLE
-- =============================================================================
-- Aggregated conversation metrics

CREATE TABLE IF NOT EXISTS conversation_analytics (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    total_conversations INTEGER NOT NULL DEFAULT 0,
    successful_tasks INTEGER NOT NULL DEFAULT 0,
    failed_tasks INTEGER NOT NULL DEFAULT 0,
    fallback_triggered INTEGER NOT NULL DEFAULT 0,
    human_handoffs INTEGER NOT NULL DEFAULT 0,
    avg_conversation_turns DECIMAL(5, 2) DEFAULT 0,
    top_intents JSONB DEFAULT '[]'::jsonb,
    task_breakdown JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_analytics_date UNIQUE (date)
);

CREATE INDEX IF NOT EXISTS idx_analytics_date ON conversation_analytics(date DESC);

-- =============================================================================
-- FUNCTIONS AND TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to relevant tables
CREATE TRIGGER update_bot_config_updated_at
    BEFORE UPDATE ON bot_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_task_config_updated_at
    BEFORE UPDATE ON task_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_service_catalog_updated_at
    BEFORE UPDATE ON service_catalog
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_content_sources_updated_at
    BEFORE UPDATE ON content_sources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Active tasks view
CREATE OR REPLACE VIEW active_tasks AS
SELECT task_name, config
FROM task_config
WHERE enabled = TRUE;

-- Active services view
CREATE OR REPLACE VIEW active_services AS
SELECT id, name, description, price, duration_minutes
FROM service_catalog
WHERE status = 'active';

-- Recent audit summary view
CREATE OR REPLACE VIEW recent_audit_summary AS
SELECT
    action_type,
    action_name,
    COUNT(*) as total_count,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failure_count,
    MIN(timestamp) as first_occurrence,
    MAX(timestamp) as last_occurrence
FROM audit_logs
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY action_type, action_name
ORDER BY total_count DESC;

-- =============================================================================
-- GRANTS (adjust roles as needed)
-- =============================================================================

-- Example: Create read-only role for reporting
-- CREATE ROLE chatbot_reader;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO chatbot_reader;
-- GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO chatbot_reader;

-- Example: Create app role for the chatbot
-- CREATE ROLE chatbot_app;
-- GRANT SELECT, INSERT, UPDATE ON bot_config TO chatbot_app;
-- GRANT SELECT ON task_config, service_catalog TO chatbot_app;
-- GRANT INSERT ON audit_logs TO chatbot_app;
