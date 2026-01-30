# Knowledge Base Ingestion Package

This directory contains scripts for ingesting content into the vector store.

## Quick Start

```bash
# Ingest files from a directory
python -m knowledge_base.ingestion.content_ingester -d ./data/website_content

# Ingest from URLs
python -m knowledge_base.ingestion.content_ingester -u https://example.com/about https://example.com/services

# Specify collection and chunk size
python -m knowledge_base.ingestion.content_ingester -d ./data -c faq_content --chunk-size 300
```

## Supported Formats

- HTML files (`.html`, `.htm`)
- Markdown files (`.md`)
- Plain text files (`.txt`)
- Web pages (via URL scraping)

## Chunking Strategy

Content is split into chunks using a sliding window approach:
- Default chunk size: 500 characters
- Default overlap: 50 characters
- Minimum chunk size: 100 characters

Chunks are created at sentence boundaries when possible to preserve semantic meaning.
