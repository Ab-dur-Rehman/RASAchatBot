# Business Website Chatbot - RASA Production System

A production-ready conversational AI chatbot built with RASA Open Source for business websites.

## Features

- **Visitor Chat**: Friendly greetings, small talk, and user guidance
- **Knowledge-Grounded Q&A**: Answers from your website content and business resources only
- **Task Execution**: Bookings, meeting scheduling, reservations management
- **Admin Dashboard Control**: Runtime configuration of tasks and business rules

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  Website Widget (REST/Socket.IO)  │  Admin Dashboard (React/Vue)            │
└───────────────────┬───────────────┴────────────────────┬────────────────────┘
                    │                                    │
                    ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API GATEWAY / NGINX                                │
│  (SSL Termination, Rate Limiting, Request Routing)                          │
└───────────────────┬───────────────────────────────────┬─────────────────────┘
                    │                                    │
        ┌───────────▼───────────┐           ┌───────────▼───────────┐
        │    RASA SERVER        │           │   ADMIN API SERVICE   │
        │  (NLU + Dialogue)     │           │   (FastAPI/Flask)     │
        │  - Intent Detection   │           │   - Config CRUD       │
        │  - Entity Extraction  │           │   - Content Mgmt      │
        │  - Story Management   │           │   - Analytics         │
        └───────────┬───────────┘           └───────────┬───────────┘
                    │                                    │
        ┌───────────▼───────────────────────────────────▼───────────┐
        │                    RASA ACTION SERVER                      │
        │  (Custom Actions - Python)                                 │
        │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐  │
        │  │ Q&A Actions │ │Task Actions │ │ Validation Actions  │  │
        │  │ (RAG/KB)    │ │(Bookings)   │ │ (Forms, Slots)      │  │
        │  └──────┬──────┘ └──────┬──────┘ └──────────┬──────────┘  │
        └─────────┼───────────────┼───────────────────┼─────────────┘
                  │               │                   │
    ┌─────────────▼───────────────▼───────────────────▼─────────────┐
    │                     DATA LAYER                                  │
    ├─────────────────┬─────────────────┬─────────────────┬─────────┤
    │  PostgreSQL     │  Redis          │  ChromaDB       │ Backend │
    │  (Config, Logs) │  (Cache,Session)│  (Vector Store) │  APIs   │
    └─────────────────┴─────────────────┴─────────────────┴─────────┘
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.9+ (for local development)

### Development Setup

```bash
# Clone and enter directory
cd RASAchatBot

# Start all services
docker-compose up -d

# Train the model (first time)
docker-compose exec rasa rasa train

# Run in interactive mode for testing
docker-compose exec rasa rasa shell
```

### Production Deployment

```bash
# Use production compose file
docker-compose -f docker-compose.prod.yml up -d
```

## Project Structure

```
RASAchatBot/
├── rasa/                       # RASA bot configuration
│   ├── actions/                # Custom action server
│   │   ├── __init__.py
│   │   ├── actions.py          # Main actions
│   │   ├── booking_actions.py  # Booking task actions
│   │   ├── qa_actions.py       # Knowledge base Q&A
│   │   ├── validation_actions.py
│   │   └── utils/
│   ├── data/                   # Training data
│   │   ├── nlu.yml
│   │   ├── stories.yml
│   │   └── rules.yml
│   ├── models/                 # Trained models
│   ├── domain.yml              # Domain definition
│   ├── config.yml              # Pipeline config
│   ├── credentials.yml         # Channel credentials
│   └── endpoints.yml           # Service endpoints
├── knowledge_base/             # Content & vector store
│   ├── ingestion/              # Content ingestion scripts
│   ├── data/                   # Raw content files
│   └── vectorstore/            # ChromaDB persistence
├── admin/                      # Admin dashboard & API
│   ├── api/                    # FastAPI backend
│   ├── config/                 # Configuration schemas
│   └── migrations/             # DB migrations
├── docker/                     # Docker configurations
├── scripts/                    # Utility scripts
├── tests/                      # Test suites
├── docker-compose.yml          # Development setup
├── docker-compose.prod.yml     # Production setup
└── README.md
```

## Documentation

- [Architecture Details](docs/ARCHITECTURE.md)
- [RASA Configuration Guide](docs/RASA_CONFIG.md)
- [Knowledge Base Setup](docs/KNOWLEDGE_BASE.md)
- [Admin Dashboard Guide](docs/ADMIN_DASHBOARD.md)
- [Deployment Checklist](docs/DEPLOYMENT.md)
- [Security Guidelines](docs/SECURITY.md)

## License

Proprietary - All rights reserved.
