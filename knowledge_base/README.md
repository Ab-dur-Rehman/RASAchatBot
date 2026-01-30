# Knowledge Base System

This directory contains the knowledge base system for the chatbot, including:
- Content ingestion scripts
- Raw content data files
- Vector store persistence

## Directory Structure

```
knowledge_base/
├── ingestion/           # Content ingestion scripts
│   └── content_ingester.py
├── data/               # Raw content files to ingest
│   ├── website/        # Website page content
│   ├── faq/            # FAQ documents
│   └── policies/       # Policy documents
└── vectorstore/        # ChromaDB persistence (auto-generated)
```

## Setup

1. Place your content files in the `data/` subdirectories
2. Run the ingestion script to populate the vector store
3. The vector store will be persisted and used by the action server

## Content Organization

Organize your content by type:

- **website/**: Main website pages (about, services, contact, etc.)
- **faq/**: Frequently asked questions
- **policies/**: Policies (refund, privacy, terms, etc.)

## Ingestion Commands

```bash
# Ingest all website content
docker-compose exec action-server python -m knowledge_base.ingestion.content_ingester \
    -d /app/knowledge_base/data/website \
    -c website_content

# Ingest FAQ content
docker-compose exec action-server python -m knowledge_base.ingestion.content_ingester \
    -d /app/knowledge_base/data/faq \
    -c faq_content

# Ingest policy documents
docker-compose exec action-server python -m knowledge_base.ingestion.content_ingester \
    -d /app/knowledge_base/data/policies \
    -c policy_docs
```
