# Detailed Usage Guide — RASA Chatbot

A comprehensive guide on how to set up, customize, train, embed, and manage this chatbot for your own website.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Getting Started (Docker Setup)](#2-getting-started-docker-setup)
3. [How the Bot Answers Questions (Two Layers)](#3-how-the-bot-answers-questions-two-layers)
4. [Customizing Intents for Your Website](#4-customizing-intents-for-your-website)
5. [Adding Responses in Domain](#5-adding-responses-in-domain)
6. [Creating Rules & Stories](#6-creating-rules--stories)
7. [Training the Rasa Model](#7-training-the-rasa-model)
8. [Knowledge Base (RAG) — Files & URLs](#8-knowledge-base-rag--files--urls)
9. [LLM Configuration (Optional)](#9-llm-configuration-optional)
10. [Embedding the Chatbot on Your Website](#10-embedding-the-chatbot-on-your-website)
11. [Admin Dashboard](#11-admin-dashboard)
12. [Rebuilding Containers After Changes](#12-rebuilding-containers-after-changes)
13. [Quick Reference Table](#13-quick-reference-table)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Architecture Overview

```
USER (Browser Widget)
       │
       ▼
┌───────────────────────┐
│    NGINX (Reverse     │   (optional, production profile)
│    Proxy)             │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│   RASA Server         │   Port 5005
│   (NLU + Dialogue)    │   - Intent classification
│                       │   - Entity extraction
│                       │   - Conversation management
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐     ┌──────────────────────┐
│   Action Server       │────▶│  ChromaDB            │   Port 8001
│   (Custom Actions)    │     │  (Vector Store)      │   - Stores document embeddings
│   Port 5055           │     │                      │   - Semantic search (RAG)
└──────────┬────────────┘     └──────────────────────┘
           │
           ├──▶ PostgreSQL (Port 5432) — Config, audit logs, content sources
           ├──▶ Redis (Port 6379) — Session tracking, caching
           ├──▶ Duckling (Port 8000) — Date/time entity extraction
           └──▶ Ollama (Port 11434) — Local LLM (optional)

┌───────────────────────┐
│   Admin API           │   Port 8080
│   (FastAPI)           │   - Knowledge base management
│                       │   - LLM configuration
│                       │   - Training management
└───────────────────────┘
```

### Key Components

| Component | Purpose | Port |
|-----------|---------|------|
| **rasa** | Core NLU engine — classifies intents, extracts entities, manages dialogue | 5005 |
| **action-server** | Runs custom Python actions (KB search, LLM calls, bookings) | 5055 |
| **admin-api** | REST API for managing knowledge base, config, and training | 8080 |
| **chromadb** | Vector database for storing and searching document embeddings | 8001 |
| **postgres** | Relational database for config, audit logs, content source metadata | 5432 |
| **redis** | Session/tracker store and caching layer | 6379 |
| **duckling** | Entity extraction for dates, times, numbers | 8000 |
| **ollama** | Local LLM server (optional, for AI-powered responses) | 11434 |

---

## 2. Getting Started (Docker Setup)

### Prerequisites
- Docker & Docker Compose installed
- At least 4GB RAM available for containers

### Start All Services

```bash
# Start core services
docker-compose up -d

# Check all containers are running
docker-compose ps

# View logs
docker-compose logs -f
```

### Verify Health

```bash
# Rasa server
curl http://localhost:5005/

# Action server
curl http://localhost:5055/health

# Admin API
curl http://localhost:8080/health

# ChromaDB
curl http://localhost:8001/api/v1/heartbeat
```

---

## 3. How the Bot Answers Questions (Two Layers)

This chatbot uses **two independent layers** to answer user questions:

### Layer 1: Rasa NLU + Rules (Intent-Based)

Rasa classifies every incoming message into an **intent** and then follows **rules/stories** to determine the response.

**Files involved:**
- `rasa/data/nlu.yml` — Training examples for each intent
- `rasa/data/rules.yml` — Simple if-then rules (intent → action)
- `rasa/data/stories.yml` — Multi-turn conversation flows
- `rasa/domain.yml` — Intent list, responses, slots, actions
- `rasa/config.yml` — NLU pipeline configuration

**Flow:**
```
User: "What are your hours?"
  → Rasa classifies intent: ask_hours
  → Rule triggers: utter_provide_hours
  → Bot responds: "We're open Monday to Friday, 9 AM to 6 PM."
```

**Requires retraining** when you add/modify intents or training examples.

### Layer 2: Knowledge Base / RAG (Content-Based)

When the intent is `ask_knowledge_base` or the NLU is uncertain (`nlu_fallback`), the bot searches the **ChromaDB vector store** for relevant content from your uploaded files and URLs.

**Flow:**
```
User: "What is your warranty policy on electronics?"
  → Rasa classifies intent: ask_knowledge_base (entity: info_type=warranty)
  → Action: action_answer_from_knowledge_base
  → Searches ChromaDB for "warranty policy electronics"
  → Returns best matching content chunks
  → Bot responds with retrieved answer + source citation
```

**No retraining needed.** Content is available instantly after upload.

### Layer 3 (Optional): LLM Fallback

If configured, unrecognized questions fall through to an LLM (OpenAI, Anthropic, Ollama, etc.) which uses retrieved KB context to generate a natural answer.

---

## 4. Customizing Intents for Your Website

### Step 4.1: Identify Question Categories

Before editing files, list the types of questions your website visitors will ask. For example:

| Your Business Type | Common Intents |
|---|---|
| E-commerce | `ask_shipping`, `ask_returns`, `ask_product_info`, `ask_order_status` |
| SaaS | `ask_pricing_plans`, `ask_features`, `ask_trial`, `ask_integration` |
| Restaurant | `ask_menu`, `ask_reservation`, `ask_dietary`, `ask_delivery` |
| Healthcare | `ask_appointment`, `ask_insurance`, `ask_services`, `ask_doctors` |
| Education | `ask_courses`, `ask_admission`, `ask_fees`, `ask_schedule` |

### Step 4.2: Add Training Examples in nlu.yml

Edit `rasa/data/nlu.yml` and add your custom intents. **Best practices:**

- Add **15–25 training examples** per intent
- Include natural variations (formal, informal, misspelled)
- Use **entities** in square brackets for extractable values
- Don't overlap too much between intents

```yaml
# Example: E-commerce website intents

- intent: ask_shipping
  examples: |
    - How long does shipping take?
    - What are the shipping options?
    - Do you offer free shipping?
    - How much is shipping?
    - When will my order arrive?
    - Can I get express delivery?
    - Do you ship internationally?
    - What courier do you use?
    - How can I track my package?
    - Is there same-day delivery?
    - Shipping costs to [California](location)
    - How long to ship to [UK](location)?
    - Do you deliver on weekends?
    - What is the shipping fee for orders under $50?
    - Is there a minimum for free shipping?

- intent: ask_returns
  examples: |
    - How do I return an item?
    - What is your return policy?
    - Can I get a refund?
    - How many days do I have to return?
    - Is return shipping free?
    - I want to return my order
    - Can I exchange an item?
    - What if my item is damaged?
    - Do you accept returns on sale items?
    - How long does a refund take?
    - Return process for [electronics](product_category)
    - Can I return [clothing](product_category)?
    - I received the wrong item
    - My order arrived broken
    - Where do I ship returns to?

- intent: ask_product_info
  examples: |
    - Tell me about [iPhone 15](product_name)
    - What are the features of [this laptop](product_name)?
    - Is [Nike Air Max](product_name) available?
    - Do you have [size 10](product_attribute) in stock?
    - What colors does [this shirt](product_name) come in?
    - Product specifications for [model X](product_name)
    - Is [this item](product_name) on sale?
    - Compare [product A](product_name) and [product B](product_name)
    - What's the best [laptop](product_category) you have?
    - Do you carry [Samsung](brand) products?

- intent: ask_order_status
  examples: |
    - Where is my order?
    - Track my order [12345](order_id)
    - What's the status of order [67890](order_id)?
    - Has my package shipped?
    - When will I receive my order?
    - I haven't received my delivery
    - My order is late
    - Check order status
    - Can you look up my order?
    - I want to know when my stuff arrives
```

### Step 4.3: Add Entities (Optional)

If your intents use entities (values in `[brackets](entity_name)`), register them in `rasa/domain.yml`:

```yaml
entities:
  - info_type
  - product_name
  - product_category
  - product_attribute
  - brand
  - location
  - order_id
```

---

## 5. Adding Responses in Domain

Edit `rasa/domain.yml` to add responses for your new intents.

### Static Responses (Simple Q&A)

```yaml
responses:
  utter_shipping_info:
    - text: |
        📦 Shipping Information:
        • Standard shipping: 3-5 business days ($5.99)
        • Express shipping: 1-2 business days ($12.99)
        • Free shipping on orders over $50
        
        Track your order at www.yoursite.com/tracking

  utter_return_policy:
    - text: |
        🔄 Return Policy:
        • 30-day return window for all items
        • Items must be unused and in original packaging
        • Free return shipping on defective items
        • Refunds processed within 5-7 business days
        
        Start a return at www.yoursite.com/returns

  # Multiple response variations (Rasa picks randomly):
  utter_greeting:
    - text: "Welcome to YourStore! 👋 How can I help you today?"
    - text: "Hi there! Looking for something specific? I'm here to help!"
    - text: "Hello! 🛍️ What can I assist you with?"
```

### Register New Actions

Add any new utter actions or custom actions to the `actions` list:

```yaml
actions:
  # ... existing actions ...
  - utter_shipping_info
  - utter_return_policy
  - action_track_order          # Custom action (Python code)
  - action_product_search       # Custom action (Python code)
```

### Register New Intents

Make sure every intent in `nlu.yml` is listed under `intents:` in `domain.yml`:

```yaml
intents:
  - greet
  - goodbye
  # ... existing intents ...
  - ask_shipping
  - ask_returns
  - ask_product_info
  - ask_order_status
```

---

## 6. Creating Rules & Stories

### Rules (Single-Turn: Intent → Response)

Edit `rasa/data/rules.yml` for simple question-answer pairs:

```yaml
rules:
  # Static response rules
  - rule: Answer shipping question
    steps:
      - intent: ask_shipping
      - action: utter_shipping_info

  - rule: Answer return question
    steps:
      - intent: ask_returns
      - action: utter_return_policy

  # Knowledge base lookup (for detailed/dynamic answers)
  - rule: Look up product info in knowledge base
    steps:
      - intent: ask_product_info
      - action: action_answer_from_knowledge_base

  # Custom action (calls external API)
  - rule: Track order status
    steps:
      - intent: ask_order_status
      - action: action_track_order
```

### Stories (Multi-Turn Conversations)

Edit `rasa/data/stories.yml` for conversations that span multiple messages:

```yaml
stories:
  - story: User asks about product then shipping
    steps:
      - intent: greet
      - action: utter_greet
      - intent: ask_product_info
      - action: action_answer_from_knowledge_base
      - intent: ask_shipping
      - action: utter_shipping_info
      - intent: thank_you
      - action: utter_thank_you_response

  - story: User wants to return and asks about refund
    steps:
      - intent: ask_returns
      - action: utter_return_policy
      - intent: affirm
      - action: utter_provide_contact
```

---

## 7. Training the Rasa Model

After editing `nlu.yml`, `domain.yml`, `rules.yml`, or `stories.yml`, you **must retrain** the model.

### Option A: Train Inside the Container

```bash
# Enter the Rasa container
docker exec -it rasa-server bash

# Train
cd /app
rasa train

# Exit container (Rasa auto-loads the new model)
exit

# Restart to pick up new model
docker-compose restart rasa
```

### Option B: Train via Admin API

```bash
curl -X POST http://localhost:8080/api/training/train
```

### Option C: Train Locally (if Rasa is installed)

```bash
cd rasa/
rasa train
# Copy the model to models/ directory
cp models/*.tar.gz ../models/
docker-compose restart rasa
```

### Validate Before Training

```bash
docker exec -it rasa-server bash -c "cd /app && rasa data validate"
```

This checks for common issues like missing intents, conflicting stories, etc.

---

## 8. Knowledge Base (RAG) — Files & URLs

The Knowledge Base is your **content layer**. Anything uploaded here is searchable by the bot **immediately** without retraining.

### What to Upload

Upload content that provides detailed answers your bot needs:

| Content Type | Examples |
|---|---|
| Product pages | Product descriptions, specs, pricing |
| FAQ pages | Frequently asked questions & answers |
| Policy documents | Return policy, privacy policy, terms of service |
| Help articles | How-to guides, troubleshooting steps |
| About pages | Company info, team, mission statement |

### Upload Files via API

```bash
# Upload a markdown file
curl -X POST http://localhost:8080/api/knowledge-base/upload \
  -F "file=@docs/faq.md" \
  -F "collection=website_content"

# Upload a PDF
curl -X POST http://localhost:8080/api/knowledge-base/upload \
  -F "file=@docs/product-catalog.pdf" \
  -F "collection=website_content"

# Upload an HTML file
curl -X POST http://localhost:8080/api/knowledge-base/upload \
  -F "file=@pages/about.html" \
  -F "collection=website_content"
```

**Supported file types:** `.txt`, `.md`, `.pdf`, `.html`, `.json`, `.csv`

### Import URLs via API

```bash
# Import a webpage
curl -X POST http://localhost:8080/api/knowledge-base/import-url \
  -F "url=https://yourwebsite.com/faq" \
  -F "collection=website_content"

# Import another page
curl -X POST http://localhost:8080/api/knowledge-base/import-url \
  -F "url=https://yourwebsite.com/about-us" \
  -F "collection=website_content"
```

### Search the Knowledge Base

```bash
curl -X POST http://localhost:8080/api/knowledge-base/search \
  -F "query=What is the return policy?" \
  -F "collection=website_content" \
  -F "top_k=5"
```

### List All Documents

```bash
curl http://localhost:8080/api/knowledge-base/documents
```

### Delete a Document

```bash
curl -X DELETE http://localhost:8080/api/knowledge-base/documents/{doc_id}
```

### View KB Statistics

```bash
curl http://localhost:8080/api/knowledge-base/stats
```

### How It Works Internally

1. **Upload/Import** → Content is read and cleaned (HTML tags removed, etc.)
2. **Chunking** → Text is split into ~500-character chunks with 50-char overlap
3. **Embedding** → Each chunk is converted to a vector using the embedding model
4. **Storage** → Vectors are stored in ChromaDB under a named collection
5. **Search** → When a user asks a question, the bot embeds the query and finds the most similar chunks via cosine similarity
6. **Response** → The top matching chunks are returned as the answer (with source citation)

### Tips for Best Knowledge Base Results

- **Keep content focused:** One topic per file/page works better than one giant document
- **Use clear headings:** They help the chunker create meaningful boundaries
- **Include Q&A pairs:** FAQ-style content performs very well with semantic search
- **Avoid excessive boilerplate:** Remove navigation, footers, and cookie notices from HTML
- **Use descriptive filenames:** They're used as source citations in bot responses

---

## 9. LLM Configuration (Optional)

For AI-powered responses beyond keyword/semantic search, configure an LLM via the Admin API.

### Supported Providers

| Provider | Model Examples | API Key Required |
|---|---|---|
| OpenAI | `gpt-4o-mini`, `gpt-4o` | Yes |
| Anthropic | `claude-3-haiku`, `claude-3-sonnet` | Yes |
| Azure OpenAI | Custom deployment names | Yes |
| Google | `gemini-pro` | Yes |
| Ollama (Local) | `llama3`, `mistral`, `phi3` | No (runs locally) |

### Configure via Admin API

```bash
# Example: Set up OpenAI
curl -X POST http://localhost:8080/api/llm/config \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key": "sk-your-key-here",
    "temperature": 0.7,
    "max_tokens": 500,
    "system_prompt": "You are a helpful customer support agent for YourBusiness. Answer questions based on the provided context. Be concise and friendly."
  }'
```

### Using Local Ollama (No API Key Needed)

```bash
# Start Ollama container (already in docker-compose.yml)
docker-compose up -d ollama

# Pull a model
docker exec ollama ollama pull llama3

# Configure the chatbot to use it
curl -X POST http://localhost:8080/api/llm/config \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "ollama",
    "model": "llama3",
    "api_base_url": "http://ollama:11434"
  }'
```

### How LLM + RAG Works Together

```
User asks a complex question
  → Rasa classifies intent as nlu_fallback or ask_knowledge_base
  → Action server searches ChromaDB for relevant content
  → Retrieved content is passed as context to the LLM
  → LLM generates a natural, context-grounded answer
  → Bot responds with the LLM answer + source citation
```

---

## 10. Embedding the Chatbot on Your Website

### Basic Embed (Any HTML Page)

Add this to the `<body>` of any page on your website:

```html
<!-- Chatbot Configuration -->
<script>
  window.CHATBOT_CONFIG = {
    serverUrl: 'https://your-server.com:5005',   // Your Rasa server URL (public)
    title: 'Your Business Name',                  // Widget title
    subtitle: 'Ask me anything!',                 // Subtitle text
    primaryColor: '#667eea',                      // Brand color (hex)
    position: 'right',                            // 'left' or 'right'
    welcomeMessage: 'Hello! 👋 How can I help you today?',
    placeholder: 'Type your question...'
  };
</script>

<!-- Chatbot Widget Script -->
<script src="https://your-server.com/chatbot-widget.js"></script>
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `serverUrl` | string | `http://localhost:5005` | Rasa server URL (must be accessible from user's browser) |
| `title` | string | `Chat Support` | Chat window title |
| `subtitle` | string | `We usually reply instantly` | Subtitle under title |
| `primaryColor` | string | `#667eea` | Brand color for header and send button |
| `position` | string | `right` | Widget position: `left` or `right` |
| `welcomeMessage` | string | `Hello! 👋 How can I help you today?` | First message shown |
| `placeholder` | string | `Type a message...` | Input placeholder text |
| `userId` | string | auto-generated | Custom user ID for tracking |

### React / Next.js Integration

```jsx
import { useEffect } from 'react';

export default function ChatWidget() {
  useEffect(() => {
    window.CHATBOT_CONFIG = {
      serverUrl: process.env.NEXT_PUBLIC_RASA_URL,
      title: 'Support',
      primaryColor: '#4f46e5',
    };

    const script = document.createElement('script');
    script.src = '/chatbot-widget.js';  // Place in public/ folder
    script.async = true;
    document.body.appendChild(script);

    return () => document.body.removeChild(script);
  }, []);

  return null;
}
```

### WordPress Integration

Add this to your theme's `footer.php` or use a "Custom HTML" widget:

```html
<script>
  window.CHATBOT_CONFIG = {
    serverUrl: 'https://your-rasa-server.com:5005',
    title: 'Help Desk',
    primaryColor: '#0073aa'
  };
</script>
<script src="https://your-rasa-server.com/chatbot-widget.js"></script>
```

### CORS Configuration

Make sure your Rasa server allows requests from your website domain. In `docker-compose.yml`, the Rasa service already has `--cors "*"` which allows all origins. For production, restrict this:

```yaml
command:
  - run
  - --enable-api
  - --cors
  - "https://yourwebsite.com"
  - --endpoints
  - endpoints.yml
```

---

## 11. Admin Dashboard

The admin dashboard is available at `http://localhost:8080` and provides a web UI for:

- **Knowledge Base Management** — Upload files, import URLs, search content, delete documents
- **LLM Configuration** — Set up AI providers (OpenAI, Ollama, etc.)
- **Training Management** — Trigger model retraining
- **System Stats** — View ChromaDB stats, document counts, collection info

### Demo Chat Page

A demo chat interface to test the bot is available at:
- `http://localhost/dashboard/chat-demo.html` (via nginx)
- Or open `dashboard/chat-demo.html` directly in a browser

---

## 12. Rebuilding Containers After Changes

### What Needs Rebuilding?

| File Changed | Container | Rebuild? | Why |
|---|---|---|---|
| `rasa/data/nlu.yml` | rasa | **No** (volume mounted), but needs `rasa train` | Data is mounted at `/app` |
| `rasa/data/rules.yml` | rasa | **No** (volume mounted), but needs `rasa train` | Data is mounted at `/app` |
| `rasa/domain.yml` | rasa | **No** (volume mounted), but needs `rasa train` | Data is mounted at `/app` |
| `rasa/config.yml` | rasa | **No** (volume mounted), but needs `rasa train` | Data is mounted at `/app` |
| `rasa/actions/*.py` | action-server | **No** (volume mounted) | Actions are mounted at `/app/actions` |
| `knowledge_base/**` | action-server | **No** (volume mounted) | KB is mounted at `/app/knowledge_base` |
| `admin/config/*.py` | admin-api | **YES** | Code is baked into image via Dockerfile |
| `requirements-actions.txt` | action-server | **YES** | Dependencies need reinstall |
| `requirements-admin.txt` | admin-api | **YES** | Dependencies need reinstall |
| `docker-compose.yml` | affected services | `docker-compose up -d` | Recreates containers |
| `docker/Dockerfile.*` | respective service | **YES** | Image needs rebuild |

### Rebuild Commands

```bash
# Rebuild a specific container
docker-compose build admin-api
docker-compose up -d admin-api

# Rebuild all custom containers
docker-compose build
docker-compose up -d

# Force rebuild (no cache)
docker-compose build --no-cache admin-api

# Rebuild and restart everything
docker-compose down
docker-compose build
docker-compose up -d
```

### Tip: Mount admin code to avoid rebuilds

Add this volume to the `admin-api` service in `docker-compose.yml`:

```yaml
volumes:
  - ./admin:/app/admin:rw          # Live-mount admin code
  - ./rasa:/app/rasa:rw
  - ./knowledge_base:/app/knowledge_base:rw
```

---

## 13. Quick Reference Table

| What You Want | How To Do It | Retrain Rasa? | Rebuild Container? |
|---|---|---|---|
| Add a new type of question | Edit `nlu.yml` + `domain.yml` + `rules.yml` → `rasa train` | **YES** | No |
| Change a bot response | Edit `domain.yml` responses → `rasa train` | **YES** | No |
| Add FAQ content | Upload `.md`/`.txt` file via Admin API | **NO** | No |
| Add website pages to KB | Import URL via Admin API | **NO** | No |
| Change bot appearance | Edit `CHATBOT_CONFIG` in your embed snippet | **NO** | No |
| Add LLM-powered answers | Configure LLM via Admin API | **NO** | No |
| Modify custom actions | Edit files in `rasa/actions/` (auto-mounted) | **NO** | No |
| Modify admin API code | Edit files in `admin/` → rebuild `admin-api` | **NO** | **YES** |
| Add new Python packages | Edit `requirements-*.txt` → rebuild | **NO** | **YES** |

---

## 14. Troubleshooting

### Bot doesn't respond
```bash
# Check if Rasa is running
docker-compose ps rasa
docker-compose logs rasa --tail 50

# Check if a model is loaded
curl http://localhost:5005/status
```

### Action server errors
```bash
# Check action server logs
docker-compose logs action-server --tail 50

# Verify action server health
curl http://localhost:5055/health
```

### Knowledge base search returns no results
```bash
# Check ChromaDB is running
curl http://localhost:8001/api/v1/heartbeat

# Check if documents exist
curl http://localhost:8080/api/knowledge-base/stats

# Test a search directly
curl -X POST http://localhost:8080/api/knowledge-base/search \
  -F "query=test query" \
  -F "top_k=5"
```

### URL import returns 403 Forbidden
Some websites block automated requests. The system includes browser-like headers to mitigate this, but some sites may still block scraping. Options:
- Download the page as HTML and upload as a file instead
- Use the site's RSS feed or API if available
- Copy-paste content into a `.md` or `.txt` file and upload

### Training fails
```bash
# Validate training data first
docker exec -it rasa-server bash -c "cd /app && rasa data validate"

# Check for conflicting rules/stories
docker exec -it rasa-server bash -c "cd /app && rasa data validate stories"
```

### Container won't start
```bash
# Check logs for the failing container
docker-compose logs <service-name>

# Check system resources
docker system df
docker stats --no-stream
```

---

## File Structure Reference

```
RASAchatBot/
├── docker-compose.yml          # Container orchestration
├── requirements-actions.txt    # Action server Python dependencies
├── requirements-admin.txt      # Admin API Python dependencies
│
├── rasa/                       # ★ RASA TRAINING DATA (edit these)
│   ├── config.yml              #   NLU pipeline & policy config
│   ├── domain.yml              #   Intents, responses, slots, actions
│   ├── endpoints.yml           #   Service endpoint URLs
│   ├── credentials.yml         #   Channel credentials
│   ├── data/
│   │   ├── nlu.yml             #   ★ Intent training examples
│   │   ├── rules.yml           #   ★ Simple intent→action rules
│   │   └── stories.yml         #   ★ Multi-turn conversation flows
│   ├── actions/                #   Custom action Python code
│   │   ├── qa_actions.py       #     Knowledge base Q&A action
│   │   ├── llm_actions.py      #     LLM-powered response action
│   │   ├── booking_actions.py  #     Appointment booking
│   │   └── utils/
│   │       ├── knowledge_base.py  #  ChromaDB search client
│   │       ├── guardrails.py      #  Answer quality checks
│   │       └── validators.py      #  Input validation
│   └── models/                 #   Trained model files (.tar.gz)
│
├── admin/                      #   Admin API (FastAPI)
│   └── config/
│       ├── knowledge_base.py   #     KB upload/import/search endpoints
│       ├── llm.py              #     LLM configuration endpoints
│       ├── training.py         #     Training management
│       └── schema.sql          #     Database schema
│
├── knowledge_base/             #   Knowledge base content & ingestion
│   ├── data/                   #     Static content files
│   │   ├── faq/faq.md
│   │   ├── policies/policies.md
│   │   └── website/about.md
│   └── ingestion/
│       └── content_ingester.py #     File & URL ingestion logic
│
├── dashboard/                  #   Frontend files
│   ├── index.html              #     Admin dashboard UI
│   ├── chat-demo.html          #     Chat testing page
│   └── chatbot-widget.js       #     ★ Embeddable chat widget
│
├── docker/                     #   Docker configuration
│   ├── Dockerfile.actions      #     Action server image
│   ├── Dockerfile.admin        #     Admin API image
│   └── nginx/nginx.conf        #     Reverse proxy config
│
└── docs/                       #   Documentation
    ├── ARCHITECTURE.md
    ├── DEPLOYMENT.md
    ├── SECURITY.md
    └── USAGE_GUIDE.md          #     ★ This file
```
