# RASA Chatbot — Self-Hosted Production Deployment Guide

> Complete step-by-step guide for deploying the RASA Chatbot system on your own server.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Step 1 — Server Preparation](#step-1--server-preparation)
4. [Step 2 — Clone & Configure Secrets](#step-2--clone--configure-secrets)
5. [Step 3 — SSL Certificates](#step-3--ssl-certificates)
6. [Step 4 — Configure Nginx](#step-4--configure-nginx)
7. [Step 5 — Build & Launch](#step-5--build--launch)
8. [Step 6 — Train the RASA Model](#step-6--train-the-rasa-model)
9. [Step 7 — Verify the Deployment](#step-7--verify-the-deployment)
10. [Step 8 — Generate Admin JWT Token](#step-8--generate-admin-jwt-token)
11. [Step 9 — Ingest Knowledge Base Content](#step-9--ingest-knowledge-base-content)
12. [Step 10 — Firewall & OS Hardening](#step-10--firewall--os-hardening)
13. [Step 11 — Automated Backups](#step-11--automated-backups)
14. [Step 12 — SSL Auto-Renewal](#step-12--ssl-auto-renewal)
15. [Embedding the Chat Widget](#embedding-the-chat-widget)
16. [Updating & Retraining](#updating--retraining)
17. [Using Ollama (Local LLM)](#using-ollama-local-llm)
18. [Environment Variable Reference](#environment-variable-reference)
19. [Monitoring & Logs](#monitoring--logs)
20. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The system runs as a set of Docker containers orchestrated by Docker Compose:

```
Internet
  │
  ▼
┌──────────┐
│  NGINX   │ :80 (→ redirect) / :443 (HTTPS + WSS)
│ (reverse │
│  proxy)  │
└──┬───┬───┘
   │   │
   │   ├──▶ RASA Server        (:5005)  — NLU + Dialogue
   │   ├──▶ Action Server      (:5055)  — Custom actions / RAG
   │   └──▶ Admin API          (:8080)  — Config management
   │
   ▼ (internal only)
┌──────────────────────────────────────────┐
│  PostgreSQL (:5432)  — Config, audit     │
│  Redis      (:6379)  — Sessions, cache   │
│  ChromaDB   (:8000)  — Vector store      │
│  Duckling   (:8000)  — Entity extraction │
│  Ollama     (:11434) — Local LLM (opt.)  │
└──────────────────────────────────────────┘
```

> PostgreSQL, Redis, and ChromaDB are **not exposed** to the internet — only accessible inside the Docker network.

---

## Prerequisites

### Hardware (minimum production)

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU      | 4 cores | 8 cores     |
| RAM      | 8 GB    | 16 GB       |
| Disk     | 50 GB SSD | 100 GB SSD |

> If running Ollama (local LLM), add at least 8 GB additional RAM (or a GPU).

### Software

| Software | Version | Install |
|----------|---------|---------|
| Docker Engine | 20.10+ | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose | v2.0+ (plugin) | `sudo apt install docker-compose-plugin` |
| Git | 2.30+ | `sudo apt install git` |
| Python 3 | 3.10+ | Needed only for generating secrets |
| certbot | latest | `sudo apt install certbot` (for Let's Encrypt) |

### Networking

- A **domain name** (e.g. `chat.yourdomain.com`) with an **A record** pointing to your server's public IP.
- Ports **80** and **443** open to the internet.

---

## Step 1 — Server Preparation

```bash
# SSH into your server
ssh user@your-server-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Re-login to apply group change
exit
ssh user@your-server-ip

# Verify
docker --version
docker compose version
```

---

## Step 2 — Clone & Configure Secrets

```bash
# Clone the repository
git clone https://github.com/Ab-dur-Rehman/RASAchatBot.git
cd RASAchatBot

# Create .env from template
cp .env.example .env
```

### Generate strong secrets and write them to `.env`:

```bash
# Generate random passwords
PG_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
REDIS_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Write to .env
sed -i "s|POSTGRES_PASSWORD=change_this_secure_password|POSTGRES_PASSWORD=${PG_PASS}|" .env
sed -i "s|REDIS_PASSWORD=change_this_redis_password|REDIS_PASSWORD=${REDIS_PASS}|" .env
sed -i "s|JWT_SECRET=your-256-bit-secret-key-change-this-in-production|JWT_SECRET=${JWT_KEY}|" .env
```

### Set your domain for CORS:

```bash
# Replace with your actual domain
sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=https://chat.yourdomain.com,https://yourdomain.com|" .env
```

### Verify the `.env` file:

```bash
cat .env
```

You should see **no** placeholder values remaining. Every password/secret must be a unique random string.

#### Required variables checklist

| Variable | Must change? | What to set |
|----------|-------------|-------------|
| `POSTGRES_PASSWORD` | **YES** | Strong random password |
| `REDIS_PASSWORD` | **YES** | Strong random password |
| `JWT_SECRET` | **YES** | 64-char hex string |
| `CORS_ORIGINS` | **YES** | Your domain(s), comma-separated |
| `POSTGRES_DB` | Optional | Default: `chatbot` |
| `POSTGRES_USER` | Optional | Default: `rasa` |
| `LOG_LEVEL` | Optional | `INFO` for production |

---

## Step 3 — SSL Certificates

### Option A — Let's Encrypt (recommended for production)

```bash
# Stop anything on port 80
sudo systemctl stop nginx 2>/dev/null || true

# Obtain certificate
sudo certbot certonly --standalone -d chat.yourdomain.com

# Copy certs into the project
sudo cp /etc/letsencrypt/live/chat.yourdomain.com/fullchain.pem docker/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/chat.yourdomain.com/privkey.pem docker/nginx/ssl/key.pem
sudo chown $USER:$USER docker/nginx/ssl/*.pem
chmod 600 docker/nginx/ssl/key.pem
```

### Option B — Self-signed (testing only)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout docker/nginx/ssl/key.pem \
  -out docker/nginx/ssl/cert.pem \
  -subj "/CN=chat.yourdomain.com"
```

> Browsers will show a warning with self-signed certs. Use Let's Encrypt for real deployments.

---

## Step 4 — Configure Nginx

Edit the nginx config to use your domain:

```bash
nano docker/nginx/nginx.conf
```

Replace **both** occurrences of `server_name _;` with your domain:

```nginx
server_name chat.yourdomain.com;
```

> If you don't have SSL certs yet and want to test HTTP first, comment out the `location / { return 301 ... }` redirect block in the HTTP server section.

---

## Step 5 — Build & Launch

```bash
# Build custom Docker images (action-server and admin-api)
docker compose build

# Start the database and cache first
docker compose up -d postgres redis

# Wait for them to initialize (~15 seconds)
sleep 15

# Verify database is ready
docker compose exec postgres pg_isready -U rasa -d chatbot

# Start all remaining services (without nginx for now)
docker compose up -d

# Check everything is running
docker compose ps
```

You should see these containers in `running` state:
- `rasa-server`
- `rasa-actions`
- `admin-api`
- `postgres`
- `redis`
- `chromadb`
- `duckling`

### Start Nginx (production profile)

```bash
docker compose --profile production up -d
```

---

## Step 6 — Train the RASA Model

The RASA server needs a trained model to handle conversations:

```bash
# Train the model (this takes 5–15 minutes)
docker compose exec rasa rasa train

# Restart RASA to pick up the new model
docker compose restart rasa
```

> Models are saved to the `./models/` directory. Keep this backed up.

---

## Step 7 — Verify the Deployment

### Health checks

```bash
# Nginx / HTTPS
curl -k https://chat.yourdomain.com/health

# RASA (internal)
curl http://localhost:5005/

# Action server (internal)
curl http://localhost:5055/health

# Admin API (internal)
curl http://localhost:8080/health
```

### Test a chat message

```bash
curl -X POST https://chat.yourdomain.com/webhooks/rest/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender": "test_user", "message": "hello"}'
```

You should receive a JSON response with the bot's reply.

### Test Socket.IO (real-time)

Open a browser to your domain — the chat widget should connect via WebSocket.

---

## Step 8 — Generate Admin JWT Token

All admin API endpoints require a JWT token. Generate one:

```bash
# Read the JWT_SECRET from .env
JWT_SECRET=$(grep '^JWT_SECRET=' .env | cut -d= -f2)

# Install PyJWT if needed
pip3 install PyJWT 2>/dev/null

# Generate a token valid for 30 days
python3 -c "
import jwt, datetime
token = jwt.encode({
    'sub': 1,
    'email': 'admin@yourdomain.com',
    'role': 'admin',
    'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
}, '${JWT_SECRET}', algorithm='HS256')
print(token)
"
```

Save this token — you'll use it as a `Bearer` token for all admin API calls:

```bash
# Example: get bot config
curl -H "Authorization: Bearer <YOUR_TOKEN>" \
  https://chat.yourdomain.com/api/admin/config/bot
```

---

## Step 9 — Ingest Knowledge Base Content

The knowledge base content in `knowledge_base/data/` needs to be ingested into ChromaDB:

```bash
# Run the content ingester
docker compose exec action-server python -c "
import asyncio
from knowledge_base.ingestion.content_ingester import ContentIngester

async def main():
    ingester = ContentIngester()
    result = await ingester.ingest_directory(
        '/app/knowledge_base/data',
        collection_name='website_content'
    )
    print(f'Ingested: {result}')

asyncio.run(main())
"
```

You can also upload documents via the Admin API:

```bash
curl -X POST https://chat.yourdomain.com/api/knowledge-base/upload \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -F "file=@/path/to/document.md" \
  -F "collection=website_content"
```

---

## Step 10 — Firewall & OS Hardening

Only ports 80 and 443 should be accessible from the internet. All other services (Postgres, Redis, etc.) are internal to the Docker network.

```bash
# UFW firewall setup
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

### Additional hardening

```bash
# Disable root SSH login
sudo sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Enable automatic security updates (Ubuntu)
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Step 11 — Automated Backups

Create a backup script:

```bash
cat > backup.sh << 'SCRIPT'
#!/bin/bash
set -e
BACKUP_DIR="/backups/chatbot"
DATE=$(date +%Y%m%d_%H%M)
BACKUP_FILE="${BACKUP_DIR}/backup_${DATE}"

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting backup..."

# Database dump
docker compose exec -T postgres pg_dump -U rasa chatbot > "${BACKUP_FILE}_db.sql"

# Models
tar -czf "${BACKUP_FILE}_models.tar.gz" models/

# Environment config (sensitive — store securely)
cp .env "${BACKUP_FILE}.env"

# Knowledge base data
tar -czf "${BACKUP_FILE}_kb.tar.gz" knowledge_base/data/

# Compress everything into one archive
tar -czf "${BACKUP_FILE}.tar.gz" \
  "${BACKUP_FILE}_db.sql" \
  "${BACKUP_FILE}_models.tar.gz" \
  "${BACKUP_FILE}.env" \
  "${BACKUP_FILE}_kb.tar.gz"

# Clean up individual files
rm -f "${BACKUP_FILE}_db.sql" "${BACKUP_FILE}_models.tar.gz" \
      "${BACKUP_FILE}.env" "${BACKUP_FILE}_kb.tar.gz"

# Remove backups older than 30 days
find "${BACKUP_DIR}" -name "backup_*.tar.gz" -mtime +30 -delete

echo "[$(date)] Backup complete: ${BACKUP_FILE}.tar.gz"
SCRIPT

chmod +x backup.sh
```

Schedule daily backups:

```bash
# Run daily at 2 AM
(crontab -l 2>/dev/null; echo "0 2 * * * cd $(pwd) && ./backup.sh >> /var/log/chatbot-backup.log 2>&1") | crontab -
```

### Restore from backup

```bash
# Extract backup
tar -xzf /backups/chatbot/backup_20260313_0200.tar.gz

# Restore database
docker compose exec -T postgres psql -U rasa chatbot < backup_20260313_0200_db.sql

# Restore models
tar -xzf backup_20260313_0200_models.tar.gz

# Restart services
docker compose restart
```

---

## Step 12 — SSL Auto-Renewal

Let's Encrypt certificates expire every 90 days. Set up auto-renewal:

```bash
DOMAIN="chat.yourdomain.com"
PROJECT_DIR="$(pwd)"

# Create renewal script
cat > renew-ssl.sh << SCRIPT
#!/bin/bash
certbot renew --quiet
cp /etc/letsencrypt/live/${DOMAIN}/fullchain.pem ${PROJECT_DIR}/docker/nginx/ssl/cert.pem
cp /etc/letsencrypt/live/${DOMAIN}/privkey.pem ${PROJECT_DIR}/docker/nginx/ssl/key.pem
cd ${PROJECT_DIR} && docker compose restart nginx
SCRIPT

chmod +x renew-ssl.sh

# Run twice daily at 3 AM and 3 PM
(crontab -l 2>/dev/null; echo "0 3,15 * * * ${PROJECT_DIR}/renew-ssl.sh >> /var/log/ssl-renewal.log 2>&1") | crontab -
```

---

## Embedding the Chat Widget

Add this to any webpage to embed the chatbot:

```html
<script>
  window.CHATBOT_CONFIG = {
    serverUrl: 'https://chat.yourdomain.com',
    title: 'Chat Support',
    subtitle: 'Ask me anything!',
    primaryColor: '#667eea'
  };
</script>
<script src="https://chat.yourdomain.com/chatbot-widget.js"></script>
```

> You can also copy `dashboard/chatbot-widget.js` and serve it from your own CDN.

---

## Updating & Retraining

### Pull latest code and rebuild

```bash
cd RASAchatBot

# Pull changes
git pull origin master

# Rebuild containers
docker compose build

# Restart services
docker compose up -d
docker compose --profile production up -d
```

### Retrain after NLU/stories changes

```bash
docker compose exec rasa rasa train
docker compose restart rasa
```

### Update knowledge base

After adding/editing files in `knowledge_base/data/`, re-run the ingestion (see [Step 9](#step-9--ingest-knowledge-base-content)).

---

## Using Ollama (Local LLM)

If you want to use a local LLM instead of OpenAI/Anthropic:

```bash
# Start Ollama container
docker compose up -d ollama

# Pull a model (e.g. llama3.2)
docker compose exec ollama ollama pull llama3.2

# For GPU support instead:
docker compose --profile local-llm-gpu up -d ollama-gpu
```

Then configure the LLM via the Admin API to use provider `ollama` with base URL `http://ollama:11434`.

---

## Environment Variable Reference

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `POSTGRES_DB` | No | Database name | `chatbot` |
| `POSTGRES_USER` | No | Database username | `rasa` |
| `POSTGRES_PASSWORD` | **Yes** | Database password | — |
| `REDIS_URL` | No | Redis connection string | `redis://redis:6379/0` |
| `REDIS_PASSWORD` | **Yes** | Redis authentication password | — |
| `JWT_SECRET` | **Yes** | JWT signing key (64+ hex chars) | — |
| `CORS_ORIGINS` | **Yes** | Allowed origins (comma-separated) | `http://localhost:3000,http://localhost:8080` |
| `API_BASE_URL` | No | Backend API for bookings | `http://api-server:8000` |
| `LOG_LEVEL` | No | Logging level | `INFO` |
| `CHROMADB_HOST` | No | ChromaDB hostname | `chromadb` |
| `CHROMADB_PORT` | No | ChromaDB port | `8000` |
| `RASA_DUCKLING_HTTP_URL` | No | Duckling entity service | `http://duckling:8000` |

---

## Monitoring & Logs

### View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f rasa
docker compose logs -f action-server
docker compose logs -f admin-api

# Last 200 lines of a service
docker compose logs --tail=200 rasa
```

### Health check endpoints

| Service | URL | Expected |
|---------|-----|----------|
| Nginx | `https://yourdomain.com/health` | `healthy` |
| RASA | `http://localhost:5005/` | JSON status |
| Action Server | `http://localhost:5055/health` | JSON status |
| Admin API | `http://localhost:8080/health` | `{"status": "healthy"}` |

### Resource usage

```bash
# Container CPU/memory stats
docker stats

# Disk usage
docker system df
```

### Key metrics to monitor

| Metric | Alert if |
|--------|----------|
| Container restarts | Any container restarting repeatedly |
| Response latency | > 3 seconds on `/webhooks/rest/webhook` |
| Disk usage | > 80% |
| Memory per container | RASA > 4 GB, Postgres > 2 GB |
| SSL cert expiry | < 14 days remaining |

---

## Troubleshooting

### Container won't start

```bash
# Check which container is failing
docker compose ps

# View its logs
docker compose logs <service-name>
```

### RASA returns "No model found"

```bash
# Train a model
docker compose exec rasa rasa train

# Verify models exist
ls -la models/

# Restart
docker compose restart rasa
```

### "DB_PASSWORD not set" errors

All services now **require** database passwords via environment variables. Verify your `.env`:

```bash
grep POSTGRES_PASSWORD .env
grep REDIS_PASSWORD .env
grep JWT_SECRET .env
```

None should contain placeholder values.

### Action server can't reach ChromaDB

```bash
# Check ChromaDB is running
docker compose logs chromadb

# Test connectivity from action server
docker compose exec action-server curl http://chromadb:8000/api/v1/heartbeat
```

### 502 Bad Gateway from Nginx

The upstream service isn't ready yet. Check:

```bash
docker compose ps              # all services "Up"?
docker compose logs rasa       # RASA started?
docker compose logs admin-api  # Admin API started?
```

### Redis connection refused

Ensure `REDIS_PASSWORD` in `.env` matches what Redis was started with. If you changed it after first start:

```bash
docker compose down redis
docker volume rm chatbot-redis-data
docker compose up -d redis
```

### Reset everything (nuclear option)

> **Warning**: This deletes all data.

```bash
docker compose down -v
docker compose up -d
docker compose exec rasa rasa train
```

---

## Service Ports Summary

| Service | Internal Port | Host Port | Exposed to Internet |
|---------|--------------|-----------|-------------------|
| Nginx | 80 / 443 | 80 / 443 | **Yes** |
| RASA | 5005 | 5005 | No (via Nginx) |
| Action Server | 5055 | 5055 | No (via Nginx) |
| Admin API | 8080 | 8080 | No (via Nginx) |
| PostgreSQL | 5432 | — | No |
| Redis | 6379 | — | No |
| ChromaDB | 8000 | — | No |
| Duckling | 8000 | 8000 | No |
| Ollama | 11434 | 11434 | No |
