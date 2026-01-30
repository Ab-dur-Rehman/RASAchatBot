# Architecture Documentation

## 1. System Overview

This document describes the production architecture for the RASA-based business chatbot system.

## 2. High-Level Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL INTERFACES                                  │
├────────────────────────────────┬────────────────────────────────────────────────┤
│     Website Chat Widget        │           Admin Dashboard                       │
│  ┌─────────────────────────┐   │    ┌─────────────────────────────────────┐     │
│  │ - Socket.IO/REST Client │   │    │ - React/Vue SPA                     │     │
│  │ - Message Queue UI      │   │    │ - Task Configuration UI             │     │
│  │ - Typing Indicators     │   │    │ - Content Management                │     │
│  │ - File Upload Support   │   │    │ - Analytics Dashboard               │     │
│  └───────────┬─────────────┘   │    └───────────────┬─────────────────────┘     │
└──────────────┼─────────────────┴────────────────────┼───────────────────────────┘
               │                                       │
               ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              GATEWAY LAYER                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         NGINX / Traefik                                  │    │
│  │  - SSL/TLS Termination                                                   │    │
│  │  - Rate Limiting (100 req/min per IP)                                    │    │
│  │  - Request Routing (/webhooks/* → RASA, /admin/* → Admin API)           │    │
│  │  - CORS Headers                                                          │    │
│  │  - Request Size Limits (10MB max)                                        │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
               │                                       │
               ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              APPLICATION LAYER                                    │
├───────────────────────────────────────┬─────────────────────────────────────────┤
│          RASA SERVER                  │         ADMIN API SERVICE               │
│  ┌─────────────────────────────┐      │  ┌─────────────────────────────────┐   │
│  │ Port: 5005                  │      │  │ Port: 8000 (FastAPI)            │   │
│  │                             │      │  │                                 │   │
│  │ ┌─────────────────────────┐ │      │  │ Endpoints:                      │   │
│  │ │   NLU Pipeline          │ │      │  │ - POST /config/tasks            │   │
│  │ │   - Tokenizer           │ │      │  │ - GET/PUT /config/settings      │   │
│  │ │   - Featurizer          │ │      │  │ - POST /content/ingest          │   │
│  │ │   - Intent Classifier   │ │      │  │ - GET /analytics/conversations  │   │
│  │ │   - Entity Extractor    │ │      │  │ - POST /auth/login              │   │
│  │ └─────────────────────────┘ │      │  └─────────────────────────────────┘   │
│  │                             │      │                                         │
│  │ ┌─────────────────────────┐ │      │  Auth: JWT tokens                       │
│  │ │   Dialogue Manager      │ │      │  Rate Limit: 50 req/min                 │
│  │ │   - Policy Ensemble     │ │      │                                         │
│  │ │   - Tracker Store       │ │      │                                         │
│  │ │   - Story Resolution    │ │      │                                         │
│  │ └─────────────────────────┘ │      │                                         │
│  └──────────────┬──────────────┘      │                                         │
│                 │                      │                                         │
└─────────────────┼──────────────────────┴─────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         RASA ACTION SERVER                                        │
│  Port: 5055                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         Action Dispatcher                                │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│         │                    │                    │                    │         │
│         ▼                    ▼                    ▼                    ▼         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │ Q&A Actions │     │Task Actions │     │ Validation  │     │  Utility    │   │
│  │             │     │             │     │  Actions    │     │  Actions    │   │
│  │ action_     │     │ action_     │     │             │     │             │   │
│  │ answer_     │     │ create_     │     │ validate_   │     │ action_     │   │
│  │ question    │     │ booking     │     │ booking_    │     │ get_config  │   │
│  │             │     │             │     │ form        │     │             │   │
│  │ action_     │     │ action_     │     │             │     │ action_     │   │
│  │ search_     │     │ cancel_     │     │ validate_   │     │ log_        │   │
│  │ knowledge   │     │ booking     │     │ meeting_    │     │ interaction │   │
│  │             │     │             │     │ form        │     │             │   │
│  └──────┬──────┘     └──────┬──────┘     └─────────────┘     └─────────────┘   │
│         │                   │                                                    │
└─────────┼───────────────────┼────────────────────────────────────────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                           │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────────┤
│   PostgreSQL    │     Redis       │    ChromaDB     │    External APIs          │
│   Port: 5432    │   Port: 6379    │   Port: 8001    │                           │
├─────────────────┼─────────────────┼─────────────────┼───────────────────────────┤
│ Tables:         │ Keys:           │ Collections:    │ Endpoints:                │
│ - bot_config    │ - session:*     │ - website_      │ - POST /api/bookings      │
│ - task_config   │ - cache:config  │   content       │ - GET /api/bookings/{id}  │
│ - audit_logs    │ - rate:*        │ - faq_content   │ - PUT /api/bookings/{id}  │
│ - conversations │ - tracker:*     │ - policy_docs   │ - DELETE /api/bookings    │
│ - content_      │                 │                 │ - POST /api/meetings      │
│   sources       │                 │                 │ - GET /api/availability   │
└─────────────────┴─────────────────┴─────────────────┴───────────────────────────┘
```

## 3. Data Flow Diagrams

### 3.1 Q&A Flow (Knowledge-Grounded)

```
User: "What are your business hours?"
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. RASA NLU processes message                                    │
│    Intent: ask_business_info (confidence: 0.92)                  │
│    Entity: info_type = "hours"                                   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Dialogue Manager selects action                               │
│    Rule: intent=ask_business_info → action_answer_question       │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Action Server: action_answer_question                         │
│                                                                  │
│    a) Query ChromaDB vector store:                               │
│       - Embed query: "business hours"                            │
│       - Similarity search (top_k=3, threshold=0.75)              │
│                                                                  │
│    b) Retrieved chunks:                                          │
│       - "Hours: Mon-Fri 9AM-6PM, Sat 10AM-4PM" (score: 0.89)    │
│       - "We are closed on Sundays and holidays" (score: 0.82)   │
│                                                                  │
│    c) Construct response with source citation                    │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Response to User                                              │
│    "Our business hours are Monday-Friday 9AM-6PM and            │
│     Saturday 10AM-4PM. We're closed Sundays and holidays.       │
│     [Source: Contact Page]"                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Booking Task Flow

```
User: "I want to book an appointment"
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. RASA NLU                                                      │
│    Intent: book_service (confidence: 0.95)                       │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Check Task Configuration (action_check_task_enabled)          │
│                                                                  │
│    Query: GET /config/tasks/book_service                         │
│    Response: {                                                   │
│      "enabled": true,                                            │
│      "required_fields": ["service_type", "date", "time",        │
│                          "name", "email", "phone"],              │
│      "services": ["consultation", "demo", "support"],            │
│      "business_hours": {"start": "09:00", "end": "18:00"},      │
│      "blocked_dates": ["2024-12-25", "2024-01-01"]              │
│    }                                                             │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Activate booking_form (Slots to fill)                         │
│                                                                  │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │ Bot: "What type of service would you like to book?      │  │
│    │       We offer: Consultation, Demo, Support"            │  │
│    │                                                          │  │
│    │ User: "A consultation please"                            │  │
│    │ → slot: service_type = "consultation" ✓                  │  │
│    └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │ Bot: "What date works for you?"                          │  │
│    │ User: "Next Monday"                                      │  │
│    │ → slot: date = "2024-01-15" ✓                           │  │
│    │ → validate_booking_date (check not blocked, not past)   │  │
│    └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │ Bot: "What time would you prefer?"                       │  │
│    │ User: "2pm"                                              │  │
│    │ → slot: time = "14:00" ✓                                │  │
│    │ → validate_booking_time (check within business hours)   │  │
│    └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│    ... (collect name, email, phone with validation) ...         │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Confirmation Step                                             │
│                                                                  │
│    Bot: "Let me confirm your booking:                           │
│          - Service: Consultation                                 │
│          - Date: Monday, January 15, 2024                       │
│          - Time: 2:00 PM                                        │
│          - Name: John Smith                                     │
│          - Email: john@example.com                              │
│          - Phone: (555) 123-4567                                │
│                                                                  │
│          Is this correct?"                                       │
│                                                                  │
│    User: "Yes"                                                   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Execute Booking (action_create_booking)                       │
│                                                                  │
│    a) Call Backend API:                                          │
│       POST /api/bookings                                         │
│       Headers: { "Authorization": "Bearer {jwt_token}" }         │
│       Body: { service, date, time, name, email, phone }         │
│                                                                  │
│    b) Handle Response:                                           │
│       Success: { "booking_id": "BK-2024-0042", "status": "confirmed" }│
│       Error: Retry logic (3 attempts, exponential backoff)      │
│                                                                  │
│    c) Log to audit table:                                        │
│       { action: "create_booking", booking_id, user_data_hash,   │
│         timestamp, status, conversation_id }                     │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Response to User                                              │
│                                                                  │
│    "Your booking is confirmed! ✓                                │
│                                                                  │
│     Booking Reference: BK-2024-0042                             │
│     Consultation on Monday, January 15, 2024 at 2:00 PM         │
│                                                                  │
│     You'll receive a confirmation email at john@example.com.    │
│     Need to make changes? Just ask me to reschedule or cancel." │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Admin Configuration Update Flow

```
Admin: Updates "book_service" task in dashboard
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Admin Dashboard UI                                            │
│                                                                  │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │ Task Settings: Book Service                              │  │
│    │                                                          │  │
│    │ [✓] Enabled                                              │  │
│    │                                                          │  │
│    │ Required Fields:                                         │  │
│    │ [✓] Service Type  [✓] Date  [✓] Time                    │  │
│    │ [✓] Name          [✓] Email [_] Phone (optional)        │  │
│    │                                                          │  │
│    │ Business Hours: 09:00 - 18:00                           │  │
│    │                                                          │  │
│    │ Add Blocked Date: [2024-02-14] [+ Add]                  │  │
│    │                                                          │  │
│    │ Available Services:                                      │  │
│    │ [✓] Consultation ($50)                                  │  │
│    │ [✓] Demo (Free)                                         │  │
│    │ [_] Premium Support ($150) ← DISABLED                   │  │
│    │                                                          │  │
│    │                              [Save Changes]              │  │
│    └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Admin API receives update                                     │
│                                                                  │
│    PUT /admin/config/tasks/book_service                          │
│    Headers: { "Authorization": "Bearer {admin_jwt}" }            │
│    Body: {                                                       │
│      "enabled": true,                                            │
│      "required_fields": ["service_type", "date", "time",        │
│                          "name", "email"],                       │
│      "optional_fields": ["phone"],                               │
│      "business_hours": { "start": "09:00", "end": "18:00" },    │
│      "blocked_dates": ["2024-12-25", "2024-01-01", "2024-02-14"],│
│      "services": [                                               │
│        { "id": "consultation", "name": "Consultation",          │
│          "price": 50, "enabled": true },                         │
│        { "id": "demo", "name": "Demo",                          │
│          "price": 0, "enabled": true },                          │
│        { "id": "premium_support", "name": "Premium Support",    │
│          "price": 150, "enabled": false }                        │
│      ]                                                           │
│    }                                                             │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Configuration Storage & Cache Invalidation                    │
│                                                                  │
│    a) Validate config against schema                             │
│    b) Store in PostgreSQL: task_config table                     │
│    c) Invalidate Redis cache: DEL cache:config:book_service      │
│    d) Log change: admin_audit_log table                          │
│       { admin_id, action, previous_value, new_value, timestamp } │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. RASA Action Server reads new config                           │
│                                                                  │
│    Next time action_create_booking runs:                         │
│                                                                  │
│    a) Check Redis cache for config                               │
│    b) Cache miss → Query Admin API: GET /config/tasks/book_service│
│    c) Cache response in Redis (TTL: 5 minutes)                   │
│    d) Apply new business rules:                                  │
│       - Phone is now optional                                    │
│       - Feb 14 is blocked                                        │
│       - Premium Support not offered                              │
│                                                                  │
│    NO RASA RETRAINING REQUIRED ✓                                │
└─────────────────────────────────────────────────────────────────┘
```

## 4. Component Details

### 4.1 RASA Server Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| Port | 5005 | Internal, not exposed directly |
| Model | `/app/models/latest.tar.gz` | Volume mounted |
| Tracker Store | Redis | Session persistence |
| Lock Store | Redis | Concurrent request handling |
| Action Endpoint | `http://action-server:5055/webhook` | Internal network |

### 4.2 RASA Action Server

| Setting | Value | Notes |
|---------|-------|-------|
| Port | 5055 | Internal only |
| Concurrency | Async (aiohttp) | Non-blocking I/O |
| Timeout | 60 seconds | For long-running actions |
| Health Check | `/health` | Liveness probe |

### 4.3 Data Stores

#### PostgreSQL Tables
- `bot_config` - Global bot settings
- `task_config` - Per-task configuration (JSON columns)
- `content_sources` - Ingested content metadata
- `audit_logs` - Action audit trail
- `conversations` - Conversation analytics

#### Redis Keys
- `session:{sender_id}` - User session data
- `cache:config:{task_name}` - Config cache (TTL: 300s)
- `rate:{ip}:{endpoint}` - Rate limiting counters
- `tracker:{sender_id}` - RASA tracker store

#### ChromaDB Collections
- `website_content` - Main website pages
- `faq_content` - FAQ entries
- `policy_docs` - Policies and terms

## 5. Scalability Considerations

### Horizontal Scaling
```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  RASA Server 1  │ │  RASA Server 2  │ │  RASA Server 3  │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────┴────────┐
                    │ Shared Redis    │
                    │ (Tracker Store) │
                    └─────────────────┘
```

### Performance Targets
- Response latency: < 500ms (P95)
- Throughput: 100 concurrent conversations
- Availability: 99.9% uptime

## 6. Security Architecture

See [SECURITY.md](SECURITY.md) for detailed security documentation.

### Key Security Controls
1. **Network Isolation**: Services communicate via internal Docker network
2. **TLS Everywhere**: All external communication encrypted
3. **Authentication**: JWT tokens for API access
4. **Rate Limiting**: Per-IP and per-user limits
5. **Input Validation**: All user inputs sanitized
6. **PII Protection**: Sensitive data encrypted, logs masked
