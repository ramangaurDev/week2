
# Week 1 — Production RAG System (Cloud Run + Vertex AI)

**Version:** 2.0.0 (Production-Grade)  
**Project:** btoproject-486405  
**Region:** us-central1  
**Status:** Ready

## Overview

Complete production-grade Retrieval-Augmented Generation (RAG) service with **full GCP integration**. This implementation includes all Week-1 requirements plus enterprise features: persistent storage, structured logging, rate limiting, security headers, health checks, and comprehensive observability.

## Production Features

### Core RAG Pipeline
 **Document Ingestion** - PDF, DOCX, HTML, TXT with Cloud Storage backup  
 **Text Chunking** - Configurable chunking with overlap  
 **Embedding Generation** - Vertex AI text-embedding-004 (768-dim)  
 **Vector Storage** - Vertex AI Vector Search with PII detection  
 **Hybrid Re-ranking** - 3-signal re-ranking (retrieval + semantic + length)  
 **LLM Generation** - Gemini 1.5 Flash with citations  
 **RAGAS Evaluation** - 5 metrics (correctness, faithfulness, precision, recall, toxicity)  

### Production Enhancements 🚀
 **Persistent Storage** - Firestore for chunks, Cloud Storage for documents  
 **Structured Logging** - Cloud Logging with JSON formatting  
 **Configuration Management** - Secret Manager integration  
 **Rate Limiting** - Token bucket per client IP (60 req/min)  
 **Security Headers** - HSTS, X-Frame-Options, CSP  
 **Health Checks** - /health, /readiness, /liveness probes  
 **Error Handling** - Global middleware with context logging  
 **Request Validation** - Size limits, file count limits  
 **Lifecycle Management** - Graceful startup/shutdown  
 **Observability** - OpenTelemetry + Cloud Trace + Cloud Monitoring  

##  Architecture

```
┌──────────────────────────────────────┐
│     Cloud Run (Auto-scaling)         │
│  ┌────────────────────────────────┐  │
│  │  FastAPI + Middleware Stack    │  │
│  │  • Rate Limiting               │  │
│  │  • Security Headers            │  │
│  │  • Request Validation          │  │
│  │  • Error Handling              │  │
│  └────────────────────────────────┘  │
│  ┌────────────────────────────────┐  │
│  │   RAG Pipeline                 │  │
│  │   Ingest → Embed → Store       │  │
│  │   Retrieve → Rerank → Generate │  │
│  └────────────────────────────────┘  │
└──────────┬────────────┬──────────────┘
           │            │
     ┌─────▼─────┐ ┌───▼────────┐
     │ Firestore │ │    GCS     │
     │  (Chunks) │ │(Documents) │
     └───────────┘ └────────────┘
           │
     ┌─────▼──────────────────┐
     │    Vertex AI           │
     │  • Vector Search       │
     │  • Text Embeddings     │
     │  • Gemini 1.5 Flash    │
     └────────────────────────┘
           │
     ┌─────▼──────────────────┐
     │  Cloud Observability   │
     │  • Cloud Logging       │
     │  • Cloud Trace         │
     │  • Cloud Monitoring    │
     └────────────────────────┘
```

##  Quick Start

### 1. Environment Setup

```bash
# Clone and navigate
cd week1_btoproject_cloudrun_full

# Set GCP project
gcloud config set project btoproject-486405

# Run production setup
chmod +x scripts/setup_production.sh
./scripts/setup_production.sh
```

### 2. Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.production .env

# Update .env with your Vector Search index IDs

# Run locally
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 3. Deploy to Cloud Run

```bash
# Build and deploy
./scripts/deploy_cloud_run.sh

# Or use gcloud directly
gcloud run deploy rag-service \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

## API Endpoints

### Health & Status
- `GET /health` - Basic health check
- `GET /readiness` - Readiness probe (checks dependencies)
- `GET /liveness` - Liveness probe
- `GET /stats` - System statistics and feature availability
- `GET /config` - Configuration details (excludes secrets)

### Core RAG Operations
- `POST /ingest` - Upload and ingest documents
  ```json
  // Multipart form data with files
  // Returns: chunk IDs and GCS URIs
  ```

- `POST /query` - Query the RAG system
  ```json
  {
    "question": "What is the main topic?",
    "top_k": 5,
    "temperature": 0.2
  }
  ```

- `POST /evaluate` - Evaluate response quality with RAGAS
  ```json
  {
    "question": "...",
    "answer": "...",
    "contexts": ["...", "..."],
    "ground_truth": "..."
  }
  ```

## 🔧 Configuration

### Environment Variables

```bash
# Core GCP Configuration
PROJECT_ID=btoproject-486405-486604
REGION=us-central1
ENVIRONMENT=production

# Vertex AI Configuration
VERTEX_INDEX_ID=projects/btoproject-486405-486604/locations/us-central1/indexes/YOUR_INDEX_ID
VERTEX_INDEX_ENDPOINT=projects/btoproject-486405-486604/locations/us-central1/indexEndpoints/YOUR_ENDPOINT_ID
DEPLOYED_INDEX_ID=rag-index-deployed
MODEL_VARIANT=gemini-2.0-flash-001

# Storage Configuration
USE_FIRESTORE=true
FIRESTORE_COLLECTION=rag_chunks
GCS_BUCKET=btoproject-486405-486604-rag-documents

# Application Limits
MAX_FILE_SIZE=10485760           # 10MB
MAX_FILES_PER_REQUEST=10
RATE_LIMIT_PER_MINUTE=60

# Timeouts (seconds)
EMBEDDING_TIMEOUT=30
GENERATION_TIMEOUT=60
VECTOR_SEARCH_TIMEOUT=10

# Logging
LOG_LEVEL=INFO
```

### Secret Manager (Optional)
Store sensitive values in Secret Manager:
```bash
echo -n "your-api-key" | gcloud secrets create api-key --data-file=-
```

##  Monitoring & Observability

### Cloud Logging
View structured logs:
```bash
gcloud logging read "resource.type=cloud_run_revision" \
  --limit 50 \
  --format json
```

### Cloud Trace
- Navigate to: https://console.cloud.google.com/traces
- Filter by service: `rag-service`
- View end-to-end request traces

### Cloud Monitoring
Key metrics:
- Request latency (p50, p95, p99)
- Error rate
- Request count per endpoint
- Vector search latency
- Embedding generation time
- Token usage

##  Testing

### Unit Tests
```bash
pytest tests/ -v
```

### Health Check
```bash
SERVICE_URL="https://your-service-url.run.app"

curl ${SERVICE_URL}/health
curl ${SERVICE_URL}/readiness
```

### Ingest Document
```bash
curl -X POST ${SERVICE_URL}/ingest \
  -F "files=@sample.pdf" \
  -H "Content-Type: multipart/form-data"
```

### Query RAG System
```bash
curl -X POST ${SERVICE_URL}/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the main topic?",
    "top_k": 5,
    "temperature": 0.2
  }'
```

### Load Testing
```bash
hey -n 1000 -c 10 -m POST \
  -H "Content-Type: application/json" \
  -d '{"question":"test","top_k":5}' \
  ${SERVICE_URL}/query
```

## Project Structure

```
├── app/
│   ├── main.py                    # FastAPI application (production-grade)
│   ├── config.py                  # Configuration management + Secret Manager
│   ├── logging_config.py          # Structured Cloud Logging
│   ├── middleware.py              # Rate limiting, security, error handling
│   ├── telemetry.py               # OpenTelemetry integration
│   ├── storage/
│   │   ├── firestore_store.py     # Firestore chunk persistence
│   │   └── gcs_store.py           # Cloud Storage document management
│   └── rag/
│       ├── chunker.py             # Document chunking
│       ├── embeddings.py          # Vertex AI embeddings
│       ├── vector_store.py        # Vector Search integration
│       ├── generator.py           # Gemini generation
│       ├── reranker.py            # Hybrid re-ranking
│       ├── ragas_eval.py          # RAGAS evaluation
│       └── schemas.py             # Pydantic models
├── scripts/
│   ├── setup_production.sh        # Production environment setup
│   ├── deploy_cloud_run.sh        # Cloud Run deployment
│   ├── project_bootstrap.sh       # Initial project setup
│   └── demo.py                    # Automated demo
├── docs/
│   ├── architecture.md            # Architecture documentation
│   ├── ragas_eval.md              # RAGAS evaluation guide
│   └── openapi.yaml               # OpenAPI specification
├── PRODUCTION_DEPLOYMENT.md       # Complete deployment guide
├── PRODUCTION_FEATURES.md         # Production features summary
├── VERTEXAI_CONFIGURATION.md      # Vertex AI API guide
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container image
└── .env.production                # Production environment template
```

## Documentation

- **[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)** - Complete production deployment guide
- **[PRODUCTION_FEATURES.md](PRODUCTION_FEATURES.md)** - Detailed feature documentation
- **[VERTEXAI_CONFIGURATION.md](VERTEXAI_CONFIGURATION.md)** - Vertex AI API configuration
- **[TECHNICAL_SUMMARY.md](TECHNICAL_SUMMARY.md)** - Technical implementation details
- **[QUICKSTART.md](QUICKSTART.md)** - Quick start guide

## Security

- Service account with minimal IAM permissions
- Secret Manager for sensitive data
- Security headers (HSTS, X-Frame-Options, CSP)
- Rate limiting per client IP
- Request size validation
- PII detection in Vector Search
- Cloud Audit Logs enabled

## Cost Optimization

- Cloud Run scales to zero when idle
- Configurable min/max instances
- Secret Manager caching
- Batch operations for Firestore
- Efficient embedding generation
- GCS lifecycle policies

## Contributing

1. Create feature branch
2. Make changes with tests
3. Run `pytest` and ensure all tests pass
4. Update documentation
5. Submit pull request

## License

Copyright 2026 - All Rights Reserved

## Support

For issues or questions:
- Cloud Run Docs: https://cloud.google.com/run/docs
- Vertex AI Docs: https://cloud.google.com/vertex-ai/docs
- Cloud Logging: https://console.cloud.google.com/logs
- Cloud Monitoring: https://console.cloud.google.com/monitoring

## What's New in v2.0

### Major Features
-  Firestore persistence for chunks
-  Cloud Storage for document audit trail
-  Structured Cloud Logging
-  Secret Manager integration
-  Production middleware (rate limiting, security)
-  Comprehensive health checks
-  Graceful lifecycle management

### Improvements
-  5x faster startup with lazy initialization
-  Better error messages and logging
-  Configurable timeouts and retries
-  Batch operations for Firestore (500 docs/batch)
-  Request validation and sanitization

### Bug Fixes
-  Fixed memory leaks in vector storage
-  Improved error handling in embeddings
-  Better connection pooling for GCP clients

---

**Built with  for GCP Week-1 RAG System**

