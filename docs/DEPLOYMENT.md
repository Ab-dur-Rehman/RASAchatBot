# =============================================================================
# DEPLOYMENT GUIDE
# =============================================================================
# Step-by-step instructions for deploying the chatbot to production
# =============================================================================

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Development Setup](#development-setup)
4. [Production Deployment](#production-deployment)
5. [Training the Model](#training-the-model)
6. [Configuration](#configuration)
7. [Monitoring](#monitoring)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Docker | 20.10+ | Container runtime |
| Docker Compose | 2.0+ | Multi-container orchestration |
| Python | 3.10+ | Local development |
| Git | 2.30+ | Version control |

### Hardware Requirements

**Development:**
- 4GB RAM minimum
- 10GB disk space

**Production:**
- 8GB RAM minimum (16GB recommended)
- 50GB SSD storage
- 4 CPU cores

---

## Quick Start

### 1. Clone and Configure

```bash
# Clone repository
git clone <repository-url>
cd RASAchatBot

# Create environment file
cp .env.example .env

# Edit .env with your settings
# IMPORTANT: Change all passwords and secrets!
```

### 2. Start Services

```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f
```

### 3. Train the Model

```bash
# Train RASA model
docker-compose exec rasa rasa train

# Test in shell
docker-compose exec rasa rasa shell
```

### 4. Verify Deployment

```bash
# Check RASA is responding
curl http://localhost:5005/

# Check action server
curl http://localhost:5055/health

# Check admin API
curl http://localhost:8080/health
```

---

## Development Setup

### Local Python Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: .\venv\Scripts\activate  # Windows

# Install RASA
pip install rasa==3.6.15

# Install action server dependencies
pip install -r requirements-actions.txt

# Install admin API dependencies
pip install -r requirements-admin.txt
```

### Run Services Locally

**Terminal 1 - RASA Server:**
```bash
cd rasa
rasa run --enable-api --cors "*" --debug
```

**Terminal 2 - Action Server:**
```bash
cd rasa
rasa run actions --port 5055
```

**Terminal 3 - Supporting Services:**
```bash
# Start only databases
docker-compose up -d postgres redis chromadb duckling
```

### Testing

```bash
# Interactive testing
rasa shell

# Run NLU tests
rasa test nlu

# Run story tests
rasa test core
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] All environment variables configured
- [ ] SSL certificates ready
- [ ] Domain DNS configured
- [ ] Backup strategy in place
- [ ] Monitoring configured
- [ ] Security review completed

### Step 1: Prepare Environment

```bash
# Create production environment file
cp .env.example .env.production

# Edit with production values
nano .env.production
```

**Critical settings to change:**
```bash
# Database
POSTGRES_PASSWORD=<strong-random-password>

# Security
JWT_SECRET=<256-bit-random-key>

# API
API_BASE_URL=https://your-backend-api.com

# CORS
CORS_ORIGINS=https://your-website.com
```

### Step 2: Build Images

```bash
# Build custom images
docker-compose build

# Tag for registry (optional)
docker tag chatbot-actions:latest your-registry/chatbot-actions:v1.0.0
docker push your-registry/chatbot-actions:v1.0.0
```

### Step 3: Initialize Database

```bash
# Start database only
docker-compose up -d postgres

# Wait for initialization
sleep 10

# Verify schema was created
docker-compose exec postgres psql -U rasa -d chatbot -c "\dt"
```

### Step 4: Train and Deploy Model

```bash
# Train model
docker-compose run --rm rasa rasa train

# Start all services
docker-compose --env-file .env.production up -d

# Verify
docker-compose ps
```

### Step 5: Configure SSL (Production)

Place SSL certificates:
```bash
mkdir -p docker/nginx/ssl
cp /path/to/cert.pem docker/nginx/ssl/
cp /path/to/key.pem docker/nginx/ssl/
```

Enable HTTPS in nginx.conf (uncomment the SSL server block).

### Step 6: Enable Production Profile

```bash
# Start with nginx reverse proxy
docker-compose --profile production up -d
```

---

## Training the Model

### Initial Training

```bash
# Full training
docker-compose exec rasa rasa train

# Training takes 5-15 minutes depending on data size
```

### Incremental Updates

When updating NLU data or stories:

```bash
# Train only NLU
docker-compose exec rasa rasa train nlu

# Train only Core
docker-compose exec rasa rasa train core

# Full retrain
docker-compose exec rasa rasa train
```

### Model Management

```bash
# List models
ls -la models/

# Test specific model
docker-compose exec rasa rasa shell --model models/20240115-120000.tar.gz
```

### A/B Testing Models

```yaml
# endpoints.yml - Multiple models
models:
  model_a:
    url: models/model_v1.tar.gz
    weight: 0.8
  model_b:
    url: models/model_v2.tar.gz
    weight: 0.2
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_DB` | Database name | chatbot |
| `POSTGRES_USER` | Database user | rasa |
| `POSTGRES_PASSWORD` | Database password | (required) |
| `REDIS_URL` | Redis connection string | redis://redis:6379/0 |
| `JWT_SECRET` | JWT signing key | (required) |
| `CORS_ORIGINS` | Allowed origins | http://localhost:3000 |
| `LOG_LEVEL` | Logging verbosity | INFO |

### Runtime Configuration (Admin API)

Tasks can be configured at runtime via the admin API:

```bash
# Get current config
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/admin/config/tasks

# Update task config
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}' \
  http://localhost:8080/api/admin/config/tasks/book_service/toggle?enabled=false
```

### Knowledge Base Updates

```bash
# Ingest new content
docker-compose exec action-server python -m knowledge_base.ingestion.content_ingester \
  --source /app/knowledge_base/data \
  --recursive

# Re-ingest specific source
docker-compose exec action-server python -m knowledge_base.ingestion.content_ingester \
  --url https://your-website.com/docs
```

---

## Monitoring

### Health Checks

Built-in health endpoints:

```bash
# RASA
curl http://localhost:5005/

# Action Server
curl http://localhost:5055/health

# Admin API
curl http://localhost:8080/health

# All services via docker
docker-compose ps
```

### Logging

View logs:
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f rasa
docker-compose logs -f action-server

# Last 100 lines
docker-compose logs --tail=100 rasa
```

### Metrics (Optional Setup)

For Prometheus/Grafana monitoring:

```yaml
# Add to docker-compose.yml
prometheus:
  image: prom/prometheus
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
  depends_on:
    - prometheus
```

### Key Metrics to Monitor

| Metric | Alert Threshold |
|--------|-----------------|
| Response latency | > 2s |
| Error rate | > 5% |
| NLU confidence | < 0.5 average |
| Fallback rate | > 10% |
| Memory usage | > 80% |
| CPU usage | > 70% sustained |

---

## Troubleshooting

### Common Issues

#### RASA won't start

```bash
# Check logs
docker-compose logs rasa

# Verify model exists
ls -la models/

# Retrain if needed
docker-compose run --rm rasa rasa train
```

#### Actions not responding

```bash
# Check action server logs
docker-compose logs action-server

# Test action server directly
curl http://localhost:5055/health

# Restart action server
docker-compose restart action-server
```

#### Database connection errors

```bash
# Check postgres is running
docker-compose ps postgres

# Check connection
docker-compose exec postgres pg_isready

# Check credentials in .env match
```

#### ChromaDB issues

```bash
# Check chromadb logs
docker-compose logs chromadb

# Verify collection
curl http://localhost:8001/api/v1/collections

# Reset if needed (WARNING: deletes data)
docker-compose down -v chromadb
docker-compose up -d chromadb
```

### Debug Mode

Enable debug logging:

```bash
# Set in .env
LOG_LEVEL=DEBUG

# Restart services
docker-compose restart

# Or run RASA in debug mode
docker-compose exec rasa rasa shell --debug
```

### Support

For issues:
1. Check logs for error messages
2. Review documentation
3. Search existing issues
4. Create new issue with:
   - Error message
   - Steps to reproduce
   - Environment details (OS, Docker version)

---

## Backup and Recovery

### Database Backup

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U rasa chatbot > backup_$(date +%Y%m%d).sql

# Restore
docker-compose exec -T postgres psql -U rasa chatbot < backup_20240115.sql
```

### Model Backup

```bash
# Models are stored in ./models/ - include in backup
tar -czvf models_backup.tar.gz models/
```

### Full System Backup

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/backups/chatbot_$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Database
docker-compose exec postgres pg_dump -U rasa chatbot > $BACKUP_DIR/database.sql

# Models
cp -r models/ $BACKUP_DIR/

# Configuration
cp .env $BACKUP_DIR/
cp -r rasa/ $BACKUP_DIR/

# Compress
tar -czvf $BACKUP_DIR.tar.gz $BACKUP_DIR
```

---

## Scaling

### Horizontal Scaling

```yaml
# docker-compose.override.yml
services:
  rasa:
    deploy:
      replicas: 3
  
  action-server:
    deploy:
      replicas: 2
```

### Load Balancing

Use NGINX upstream for multiple RASA instances:

```nginx
upstream rasa_cluster {
    least_conn;
    server rasa-1:5005;
    server rasa-2:5005;
    server rasa-3:5005;
}
```

### Kubernetes Deployment

For Kubernetes, use the [RASA Helm charts](https://github.com/RasaHQ/helm-charts):

```bash
helm repo add rasa https://helm.rasa.com
helm install my-chatbot rasa/rasa
```
