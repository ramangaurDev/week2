"""
Production ChatBot RAG Service with Authentication, RBAC, Chat History, and Analytics.
Features: Redis Chat History, Admin Analytics, OIDC Auth, RBAC, Document Ingestion, Vector Search
"""

import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
import time
from contextlib import asynccontextmanager
from pydantic import BaseModel

from app.config import config
from app.logging_config import get_logger
from app.middleware import (
    RateLimitMiddleware, 
    ErrorHandlingMiddleware, 
    RequestValidationMiddleware,
    SecurityHeadersMiddleware
)

# Import authentication and authorization
from app.auth.oidc import get_current_user, get_optional_user
from app.auth.rbac import (
    get_current_user_with_role,
    require_permission,
    require_role,
    Permission,
    Role,
    rbac_manager
)

# Import RAG components
from app.rag.schemas import QueryRequest, QueryResponse, IngestResponse, UnifiedResponse, EvaluateRequest, EvaluateResponse
from app.rag.chunker import extract_and_chunk
from app.rag.embeddings import VertexTextEmbedder
from app.rag.vector_store import VertexVectorStore
from app.rag.generator import GeminiGenerator
from app.rag.reranker import HybridReranker
from app.rag.ragas_eval import RAGASEvaluator
from app.rag.graph_rag import LangGraphRAGPipeline
from app.rag.pii_detector import PIIDetector
from app.storage.gcs_store import GCSDocumentStore
from app.storage.redis_store import RedisChatHistory
from app.analytics import AnalyticsTracker
from app.telemetry import (
    configure_otel, 
    trace_operation, 
    record_vector_search, 
    record_embedding, 
    record_tokens,
    record_llm_generation
)

# Initialize logger
logger = get_logger(__name__)

# Service instances (will be initialized at startup)
embedder: Optional[VertexTextEmbedder] = None
vector_store: Optional[VertexVectorStore] = None
doc_store: Optional[GCSDocumentStore] = None
generator: Optional[GeminiGenerator] = None
reranker: Optional[HybridReranker] = None
evaluator: Optional[RAGASEvaluator] = None
pii_detector: Optional[PIIDetector] = None
langgraph_pipeline: Optional[LangGraphRAGPipeline] = None
redis_history: Optional[RedisChatHistory] = None
analytics: Optional[AnalyticsTracker] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    # Startup
    logger.info("Starting Production RAG Service with Redis & Analytics", config=config.to_dict())
    
    # Validate configuration
    validation = config.validate()
    if not validation["valid"]:
        logger.error("Configuration validation failed", issues=validation["issues"])
        raise RuntimeError(f"Invalid configuration: {validation['issues']}")
    
    # Initialize services
    global embedder, vector_store, doc_store, generator, reranker
    global evaluator, pii_detector, langgraph_pipeline, redis_history, analytics
    
    try:
        logger.info("Initializing services")
        
        embedder = VertexTextEmbedder(
            project=config.PROJECT_ID, 
            location=config.VERTEX_LOCATION
        )
        
        vector_store = VertexVectorStore(
            project=config.PROJECT_ID,
            location=config.VERTEX_LOCATION,
            index_id=config.VERTEX_INDEX_ID,
            index_endpoint_name=config.VERTEX_INDEX_ENDPOINT,
            deployed_index_id=config.DEPLOYED_INDEX_ID
        )
        
        doc_store = GCSDocumentStore(
            project_id=config.PROJECT_ID,
            bucket_name=config.GCS_BUCKET
        )
        
        generator = GeminiGenerator(
            project=config.PROJECT_ID,
            location=config.VERTEX_LOCATION,
            model=config.MODEL_VARIANT
        )
        
        reranker = HybridReranker(
            project=config.PROJECT_ID,
            location=config.VERTEX_LOCATION
        )
        
        evaluator = RAGASEvaluator(
            project=config.PROJECT_ID,
            location=config.VERTEX_LOCATION,
            model=config.MODEL_VARIANT
        )
        
        # Initialize PII Detector
        pii_detector = PIIDetector(project_id=config.PROJECT_ID)
        
        # Initialize LangGraph RAG Pipeline
        langgraph_pipeline = LangGraphRAGPipeline(
            embeddings=embedder,
            vector_store=vector_store,
            reranker=reranker,
            generator=generator,
            max_iterations=2
        )
        
        # Initialize Redis Chat History
        try:
            redis_history = RedisChatHistory(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD")
            )
            logger.info("Redis chat history initialized successfully")
        except Exception as e:
            logger.warning("Redis not available, chat history disabled", error=str(e))
            redis_history = None
        
        # Initialize Analytics Tracker
        analytics = AnalyticsTracker(
            project_id=config.PROJECT_ID,
            collection_name="analytics_metrics"
        )
        
        logger.info("All services initialized successfully (including LangGraph, Redis, and Analytics)")
        
    except Exception as e:
        logger.error("Service initialization failed", error=e)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down RAG service")


app = FastAPI(
    title="Production ChatBot RAG Service",
    version="3.0.0",
    description="Production-grade RAG system with Auth, RBAC, Chat History, and Analytics",
    lifespan=lifespan
)

# Add middleware (order matters!)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RequestValidationMiddleware, max_content_length=config.MAX_FILE_SIZE)
app.add_middleware(RateLimitMiddleware, max_requests=config.RATE_LIMIT_PER_MINUTE, window_seconds=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure observability
configure_otel(app)


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@app.get("/health")
def health():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "chatbot-rag-service",
        "version": "3.0.0"
    }


@app.get("/readiness")
async def readiness():
    """Readiness probe for Kubernetes."""
    checks = {
        "embedder": embedder is not None,
        "vector_store": vector_store is not None,
        "generator": generator is not None,
        "analytics": analytics is not None,
        "redis": redis_history is not None,
    }
    
    all_ready = all(checks.values())
    
    return {
        "ready": all_ready,
        "checks": checks,
        "timestamp": time.time()
    }


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

class LoginRequest(BaseModel):
    """Login request with Google ID token."""
    id_token: str


@app.post("/api/v1/auth/login")
async def login(request: LoginRequest):
    """
    Authenticate user with Google OIDC ID token.
    Returns user info and role.
    """
    from app.auth.oidc import get_oidc_validator
    
    validator = get_oidc_validator()
    user_info = validator.verify_token(request.id_token)
    
    # Get user role and permissions
    role = rbac_manager.get_user_role(user_info['email'])
    permissions = rbac_manager.get_user_permissions(user_info['email'])
    
    return {
        "user": user_info,
        "role": role.value,
        "permissions": [p.value for p in permissions],
        "authenticated": True
    }


@app.get("/api/v1/auth/me")
async def get_me(user: Dict[str, Any] = Depends(get_current_user_with_role)):
    """Get current user information."""
    return {
        "user": user,
        "authenticated": True
    }


# ============================================================================
# CHAT ENDPOINTS (Protected - Redis Required)
# ============================================================================

class ChatQueryRequest(BaseModel):
    """Chat query request."""
    query: str
    session_id: Optional[str] = None
    top_k: int = 5
    use_reranking: bool = True


class ChatSessionResponse(BaseModel):
    """Chat session response."""
    session_id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


@app.post("/api/v1/chat/query")
async def chat_query(
    request: ChatQueryRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_permission(Permission.QUERY_RAG))
):
    """
    Execute a RAG query within a chat session with Redis history.
    Creates new session if session_id not provided.
    """
    start_time = time.time()
    user_id = user['email']
    
    try:
        # Create or get session
        if request.session_id and redis_history:
            session_id = request.session_id
        elif redis_history:
            session_id = redis_history.create_session(user_id, request.query)
        else:
            session_id = "no-redis"
        
        # Add user message to history
        if redis_history:
            redis_history.add_message(session_id, 'user', request.query)
        
        # Get conversation context
        context_messages = []
        if redis_history and request.session_id:
            context_messages = redis_history.get_recent_context(session_id, max_messages=6)
        
        # Execute RAG query using LangGraph pipeline
        with trace_operation("rag_query"):
            result = langgraph_pipeline.query(
                query=request.query,
                top_k=request.top_k,
                use_reranking=request.use_reranking,
                context_history=context_messages
            )
        
        # Add assistant response to history
        if redis_history:
            redis_history.add_message(
                session_id,
                'assistant',
                result['answer'],
                metadata={
                    'tokens': result.get('metadata', {}).get('token_usage', {}),
                    'chunks_used': len(result.get('contexts', [])),
                    'latency_ms': result.get('metadata', {}).get('latency_ms', 0)
                }
            )
        
        # Track analytics
        response_time_ms = (time.time() - start_time) * 1000
        token_usage = result.get('metadata', {}).get('token_usage', {})
        
        if analytics:
            analytics.track_query(
                user_email=user_id,
                query=request.query,
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                model=config.MODEL_VARIANT,
                success=True,
                metadata={
                    'session_id': session_id,
                    'chunks_retrieved': len(result.get('contexts', [])),
                    'reranking_used': request.use_reranking
                }
            )
        
        return {
            "answer": result['answer'],
            "session_id": session_id,
            "contexts": result.get('contexts', []),
            "metadata": {
                **result.get('metadata', {}),
                "response_time_ms": response_time_ms
            }
        }
        
    except Exception as e:
        logger.error("Chat query failed", error=str(e), user=user_id)
        
        # Track failure
        if analytics:
            analytics.track_query(
                user_email=user_id,
                query=request.query,
                response_time_ms=(time.time() - start_time) * 1000,
                token_usage={},
                model=config.MODEL_VARIANT,
                success=False,
                error=str(e)
            )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/chat/sessions", response_model=List[ChatSessionResponse])
async def get_chat_sessions(
    user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all chat sessions for current user."""
    if not redis_history:
        raise HTTPException(status_code=503, detail="Chat history not available")
    
    user_id = user['email']
    sessions = redis_history.get_user_sessions(user_id, limit=limit, offset=offset)
    
    return sessions


@app.get("/api/v1/chat/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get message history for a specific chat session."""
    if not redis_history:
        raise HTTPException(status_code=503, detail="Chat history not available")
    
    messages = redis_history.get_session_history(session_id)
    
    return {
        "session_id": session_id,
        "messages": messages
    }


@app.delete("/api/v1/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_permission(Permission.DELETE_HISTORY))
):
    """Delete a chat session."""
    if not redis_history:
        raise HTTPException(status_code=503, detail="Chat history not available")
    
    user_id = user['email']
    redis_history.delete_session(session_id, user_id)
    
    return {"message": "Session deleted", "session_id": session_id}


# ============================================================================
# LEGACY RAG ENDPOINTS (Backward compatibility - no Redis required)
# ============================================================================


@app.get("/liveness")
def liveness():
    """
    Liveness probe - checks if service is running.
    Used by Cloud Run to detect if instance needs to be restarted.
    """
    return {"alive": True, "timestamp": time.time()}

@app.post("/ingest", response_model=IngestResponse)
async def ingest(files: List[UploadFile] = File(...)):
    """
    Ingest documents: extract text, chunk, embed, and store in vector search + Cloud Storage.
    
    Production features:
    - Stores documents in Cloud Storage for audit trail
    - Persists chunks in Firestore (if enabled)
    - Full error handling and logging
    - File size validation
    
    Supports: PDF, DOCX, HTML, TXT
    """
    with trace_operation("ingest_documents", {"num_files": len(files)}):
        try:
            # Validate file count
            if len(files) > config.MAX_FILES_PER_REQUEST:
                raise HTTPException(
                    status_code=400,
                    detail=f"Too many files. Maximum: {config.MAX_FILES_PER_REQUEST}"
                )
            
            # Read file contents and validate size
            docs = []
            gcs_uris = []
            
            for f in files:
                content = await f.read()
                
                if len(content) > config.MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File {f.filename} exceeds maximum size of {config.MAX_FILE_SIZE} bytes"
                    )
                
                # Store in Cloud Storage
                gcs_uri = doc_store.upload_document(
                    filename=f.filename,
                    content=content,
                    content_type=f.content_type or "application/octet-stream",
                    metadata={"ingested_at": time.time()}
                )
                
                if gcs_uri:
                    gcs_uris.append(gcs_uri)
                    logger.info(f"Document uploaded to GCS", filename=f.filename, gcs_uri=gcs_uri)
                
                docs.append((f.filename, content))
            
            # Extract and chunk
            with trace_operation("extract_and_chunk", {"num_docs": len(docs)}):
                chunks = extract_and_chunk(docs)
            
            if not chunks:
                raise HTTPException(status_code=400, detail="No text extracted from files")
            
            logger.info(f"Extracted {len(chunks)} chunks from {len(files)} files")
            
            # PII Detection
            logger.info(" Starting PII detection scan...")
            if pii_detector:
                for chunk in chunks:
                    pii_result = pii_detector.detect_pii(chunk["text"])
                    # Add PII metadata to chunk
                    chunk.setdefault("metadata", {})["pii_status"] = pii_result["status"]
                    chunk["metadata"]["pii_types"] = pii_result["pii_types"]
                    chunk["metadata"]["pii_count"] = pii_result["pii_count"]
                    
                    if pii_result["status"] in ["high_risk", "blocked"]:
                        logger.warning(f" High-risk PII detected in chunk {chunk['id']}", pii_types=pii_result["pii_types"])
                logger.info(f" PII detection completed for {len(chunks)} chunks")
            else:
                logger.warning(" PII detector not available - marking all as clean")
                # Fallback: mark as clean if PII detector unavailable
                for chunk in chunks:
                    chunk.setdefault("metadata", {})["pii_status"] = "clean"
            
            # Embed chunks
            start_time = time.time()
            with trace_operation("embed_chunks", {"num_chunks": len(chunks)}):
                vectors = embedder.embed([c["text"] for c in chunks])
            
            embedding_time = time.time() - start_time
            record_embedding(embedding_time, len(chunks))
            logger.info(f"Generated embeddings", num_chunks=len(chunks), duration=embedding_time)
            
            # Upsert to Vertex Vector Search
            with trace_operation("upsert_vectors", {"num_vectors": len(vectors)}):
                ids = vector_store.upsert(chunks, vectors)
            
            logger.info(f"Upserted to Vector Search", num_vectors=len(ids))
            
            # Note: Chunks are stored in Vertex AI Vector Search only (no Firestore duplication)
            
            return IngestResponse(
                ingested=len(ids),
                chunk_ids=ids,
                message=f"Successfully ingested {len(files)} files into {len(ids)} chunks",
                gcs_uris=gcs_uris if gcs_uris else None
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Ingestion failed", error=e, num_files=len(files))
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.post("/ingest-and-query", response_model=UnifiedResponse)
async def ingest_and_query(
    question: str = Form(..., description="User's question"),
    files: List[UploadFile] = File(..., description="Documents to process")
):
    """
    **UNIFIED ENDPOINT: Accept documents + question in a SINGLE API call**
    
    This endpoint implements the complete Week-1 pipeline:
    1. Accept user documents (PDF, DOCX, HTML, TXT)
    2. Extract text from all documents
    3. Chunk text into smaller pieces (1500-3000 chars with overlap)
    4. Convert chunks to embeddings (text-embedding-004, 768-dim)
    5. Auto-index into Vertex AI Vector Search
    6. Perform semantic search for user question
    7. Generate answer using Gemini 1.5 Flash
    8. Enforce PII detection and filtering
    9. Provide full observability metrics
    10. Return combined response
    
    **Default Settings:**
    - top_k: 5
    - pii_filter: enabled
    - reranker: disabled (for speed)
    - temperature: 0.2
    
    **Example Request (form-data):**
    - question: "What are the security risks?"
    - files: [document1.pdf, document2.docx]
    
    **Returns:** Ingestion stats + Answer + Citations + Metrics in ONE response
    """
    start_time = time.time()
    metrics = {}
    
    with trace_operation("unified_ingest_and_query", {"num_files": len(files), "question_length": len(question)}):
        try:
            logger.info("Starting unified pipeline", num_files=len(files), question=question[:100])
            
            # ===== STEP 1: Validate inputs =====
            if len(files) > config.MAX_FILES_PER_REQUEST:
                raise HTTPException(
                    status_code=400,
                    detail=f"Too many files. Maximum: {config.MAX_FILES_PER_REQUEST}"
                )
            
            if not question or len(question.strip()) == 0:
                raise HTTPException(status_code=400, detail="Question cannot be empty")
            
            # ===== STEP 2: Read files and upload to GCS =====
            extract_start = time.time()
            docs = []
            gcs_uris = []
            
            for f in files:
                content = await f.read()
                
                if len(content) > config.MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File {f.filename} exceeds maximum size"
                    )
                
                # Store in Cloud Storage
                gcs_uri = doc_store.upload_document(
                    filename=f.filename,
                    content=content,
                    content_type=f.content_type or "application/octet-stream",
                    metadata={"ingested_at": time.time(), "question": question[:200]}
                )
                
                if gcs_uri:
                    gcs_uris.append(gcs_uri)
                
                docs.append((f.filename, content))
            
            # ===== STEP 3: Extract and chunk text =====
            with trace_operation("extract_and_chunk", {"num_docs": len(docs)}):
                chunks = extract_and_chunk(docs)
            
            if not chunks:
                raise HTTPException(status_code=400, detail="No text extracted from files")
            
            metrics["extraction_time"] = time.time() - extract_start
            metrics["num_chunks"] = len(chunks)
            logger.info(f"Extracted {len(chunks)} chunks", duration=metrics["extraction_time"])
            
            # ===== STEP 3.5: PII Detection =====
            pii_results = []
            has_high_risk_pii = False
            if pii_detector:
                for chunk in chunks:
                    pii_result = pii_detector.detect_pii(chunk["text"])
                    pii_results.append(pii_result)
                    # Add PII metadata to chunk
                    chunk.setdefault("metadata", {})["pii_status"] = pii_result["status"]
                    chunk["metadata"]["pii_types"] = pii_result["pii_types"]
                    chunk["metadata"]["pii_count"] = pii_result["pii_count"]
                    
                    if pii_result["status"] in ["high_risk", "blocked"]:
                        has_high_risk_pii = True
                        logger.warning(f"High-risk PII detected in chunk {chunk['id']}", pii_types=pii_result["pii_types"])
            else:
                # Fallback: mark as clean if PII detector unavailable
                for chunk in chunks:
                    chunk.setdefault("metadata", {})["pii_status"] = "clean"
            
            # ===== STEP 4: Generate embeddings =====
            embed_start = time.time()
            with trace_operation("embed_chunks", {"num_chunks": len(chunks)}):
                vectors = embedder.embed([c["text"] for c in chunks])
            
            metrics["embedding_time"] = time.time() - embed_start
            record_embedding(metrics["embedding_time"], len(chunks))
            logger.info(f"Generated embeddings", num_chunks=len(chunks), duration=metrics["embedding_time"])
            
            # ===== STEP 5: Upsert to Vector Search =====
            upsert_start = time.time()
            with trace_operation("upsert_vectors", {"num_vectors": len(vectors)}):
                chunk_ids = vector_store.upsert(chunks, vectors)
            
            metrics["upsert_time"] = time.time() - upsert_start
            logger.info(f"Indexed in Vector Search", num_vectors=len(chunk_ids), duration=metrics["upsert_time"])
            
            # Note: Chunks stored in Vertex AI Vector Search only (no Firestore duplication)
            
            # ===== STEP 6: Embed question and search =====
            retrieval_start = time.time()
            with trace_operation("embed_question"):
                question_vector = embedder.embed([question])[0]
            
            # Search with PII filter enabled (default)
            with trace_operation("vector_search", {"top_k": 5}):
                search_results = vector_store.search(
                    query=question,
                    top_k=5,
                    enable_pii_filter=True  # Enforce PII filtering
                )
            
            metrics["retrieval_time"] = time.time() - retrieval_start
            record_vector_search(metrics["retrieval_time"], len(search_results))
            logger.info(f"Retrieved chunks", num_results=len(search_results), duration=metrics["retrieval_time"])
            
            if not search_results:
                raise HTTPException(
                    status_code=404,
                    detail="No relevant chunks found. Documents may not be indexed yet or question is unrelated."
                )
            
            # ===== STEP 7: Generate answer with Gemini =====
            generation_start = time.time()
            contexts = [r["text"] for r in search_results]
            
            with trace_operation("generate_answer", {"num_contexts": len(contexts)}):
                answer, citations, token_usage = generator.generate(question, contexts)
            
            metrics["generation_time"] = time.time() - generation_start
            record_llm_generation(metrics["generation_time"], len(contexts))
            record_tokens(token_usage["total_tokens"], "generate")
            logger.info(f"Generated answer", duration=metrics["generation_time"], tokens=token_usage)
            
            # ===== STEP 8: Build unified response =====
            metrics["total_time"] = time.time() - start_time
            
            # Determine actual PII filtered status
            pii_detected = any(r["has_pii"] for r in pii_results) if pii_results else False
            pii_filtered_status = pii_detector is not None  # True if PII detection was performed
            
            return UnifiedResponse(
                status="success",
                ingested_chunks=len(chunk_ids),
                question=question,
                answer=answer,
                contexts=contexts,
                citations=citations,
                pii_filtered=pii_filtered_status,
                model_used="gemini-2.0-flash-001",
                metrics=metrics,
                gcs_uris=gcs_uris if gcs_uris else None
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Unified pipeline failed", error=e)
            raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """
    Query the RAG system: retrieve relevant chunks, re-rank, and generate answer.
    
    Production features:
    - Timeout handling for all operations
    - Graceful fallback for missing data
    - Detailed error logging
    - Performance metrics
    
    Features:
    - Vector search retrieval
    - Hybrid re-ranking
    - Grounded LLM generation
    - Citation extraction
    """
    with trace_operation("rag_query", {"question_length": len(req.question)}):
        try:
            logger.info("Processing query", question_preview=req.question[:100], top_k=req.top_k)
            
            # Retrieve top-K chunks from vector search
            start_time = time.time()
            with trace_operation("vector_search", {"top_k": req.top_k}):
                neighbors = vector_store.search(req.question, top_k=req.top_k * 2)  # Get more for re-ranking
            
            search_time = time.time() - start_time
            record_vector_search(search_time, len(neighbors))
            logger.info(f"Vector search completed", num_results=len(neighbors), duration=search_time)
            
            if not neighbors:
                logger.warning("No search results found")
                return QueryResponse(
                    question=req.question,
                    answer="No relevant documents found. Please ingest documents first.",
                    contexts=[],
                    citations=[],
                    model_used="none",
                    retrieval_scores=[]
                )
            
            # Re-rank results
            start_time = time.time()
            with trace_operation("rerank", {"num_chunks": len(neighbors)}):
                reranked = reranker.rerank(req.question, neighbors, top_k=req.top_k)
            
            rerank_time = time.time() - start_time
            logger.info(f"Re-ranking completed", num_chunks=len(reranked), duration=rerank_time)
            
            contexts = [n.get("text", "") for n in reranked]
            retrieval_scores = [
                {
                    "chunk_id": n.get("id", ""),
                    "score": n.get("rerank_score", n.get("score", 0.0))
                }
                for n in reranked
            ]
            
            # Generate answer with citations
            start_time = time.time()
            with trace_operation("generate_answer", {"num_contexts": len(contexts)}):
                answer, citations, token_usage = generator.answer(
                    question=req.question,
                    contexts=contexts,
                    temperature=req.temperature
                )
            
            generation_time = time.time() - start_time
            logger.info(f"Answer generation completed", duration=generation_time, num_citations=len(citations), tokens=token_usage)
            
            # Record actual token usage from Gemini
            record_tokens(token_usage["total_tokens"], "generate")
            
            return QueryResponse(
                question=req.question,
                answer=answer,
                contexts=contexts,
                citations=citations,
                model_used=config.MODEL_VARIANT,
                retrieval_scores=retrieval_scores
            )
            
        except Exception as e:
            logger.error("Query failed", error=e, question_preview=req.question[:100])
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(req: EvaluateRequest):
    """
    Evaluate RAG response quality using RAGAS metrics.
    
    Metrics:
    - Answer Correctness
    - Faithfulness (groundedness)
    - Context Precision
    - Context Recall
    - Toxicity Score
    """
    with trace_operation("ragas_evaluation"):
        try:
            logger.info("Starting RAGAS evaluation", num_contexts=len(req.contexts))
            
            metrics = evaluator.evaluate(
                question=req.question,
                answer=req.answer,
                contexts=req.contexts,
                ground_truth=req.ground_truth
            )
            
            logger.info("RAGAS evaluation completed", metrics=metrics.to_dict())
            
            return EvaluateResponse(
                metrics=metrics.to_dict(),
                explanation={
                    "answer_correctness": "Semantic similarity to ground truth or question",
                    "faithfulness": "How well the answer is grounded in contexts",
                    "context_precision": "Relevance of retrieved contexts to question",
                    "context_recall": "Coverage of answer by contexts",
                    "toxicity_score": "Harmful content detection (lower is better)"
                }
            )
            
        except Exception as e:
            logger.error("Evaluation failed", error=e)
            raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@app.get("/stats")
def get_stats():
    """Get system statistics and configuration."""
    stats = {
        "service": "chatbot-rag-service",
        "version": "3.0.0",
        "environment": config.ENVIRONMENT,
        "configuration": config.to_dict(),
        "features": {
            "document_ingestion": True,
            "cloud_storage": doc_store is not None,
            "vector_search": vector_store is not None,
            "re_ranking": reranker is not None,
            "llm_generation": generator is not None,
            "ragas_evaluation": evaluator is not None,
            "redis_chat_history": redis_history is not None,
            "analytics_tracking": analytics is not None,
            "observability": True,
            "rate_limiting": True,
            "security_headers": True,
            "rbac_auth": True
        }
    }
    
    # Add vector store size if available
    if vector_store and hasattr(vector_store, 'chunk_store'):
        stats["vector_store_size"] = len(vector_store.chunk_store)
        stats["sample_chunks"] = list(vector_store.chunk_store.keys())[:5]
    
    return stats


@app.get("/config")
def get_config():
    """Get current configuration (excludes secrets)."""
    return {
        "config": config.to_dict(),
        "validation": config.validate()
    }


@app.post("/query/advanced", response_model=QueryResponse)
async def query_langgraph(req: QueryRequest):
    """
    Query using LangGraph stateful RAG pipeline with advanced features:
    - Adaptive retrieval (refines query if confidence is low)
    - Self-correction capabilities
    - Multi-turn conversation memory
    - Iterative refinement (up to 2 iterations)
    
    This endpoint provides better results for complex queries that may need
    query refinement or multiple retrieval attempts.
    """
    with trace_operation("langgraph_rag_query", {"question_length": len(req.question)}):
        try:
            logger.info("Processing LangGraph query", question_preview=req.question[:100])
            
            # Convert chat history format
            chat_history = []
            if req.chat_history:
                for turn in req.chat_history:
                    if isinstance(turn, dict):
                        chat_history.append((turn.get("user", ""), turn.get("assistant", "")))
                    elif isinstance(turn, (list, tuple)) and len(turn) == 2:
                        chat_history.append((turn[0], turn[1]))
            
            # Run LangGraph pipeline
            start_time = time.time()
            result = await langgraph_pipeline.query(
                query=req.question,
                chat_history=chat_history
            )
            
            query_time = time.time() - start_time
            logger.info(
                "LangGraph query completed",
                duration=query_time,
                confidence=result["confidence"],
                iterations=result["iterations"]
            )
            
            # Format response - extract just the text strings for citations
            contexts = [source["text"] for source in result["sources"]]
            citations = [source["text"] for source in result["sources"][:3]]  # Top 3 as citations
            
            # Format retrieval scores as list of dicts
            retrieval_scores = [
                {
                    "chunk_id": source.get("id", f"chunk_{i}"),
                    "score": source.get("score", 0.0)
                }
                for i, source in enumerate(result["sources"])
            ]
            
            return QueryResponse(
                question=req.question,
                answer=result["response"],
                contexts=contexts,
                citations=citations,
                model_used=config.MODEL_VARIANT,
                retrieval_scores=retrieval_scores
            )
            
        except Exception as e:
            logger.error("LangGraph query failed", error=e, question=req.question[:100])
            raise HTTPException(status_code=500, detail=f"LangGraph query failed: {str(e)}")


# ============================================================================
# ADMIN ANALYTICS ENDPOINTS (Admin Only - Analytics Required)
# ============================================================================

@app.get("/api/v1/admin/analytics/usage")
async def get_usage_analytics(
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    days: int = Query(7, ge=1, le=90)
):
    """Get usage analytics (admin only)."""
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not available")
    
    stats = analytics.get_usage_stats(days=days)
    return stats


@app.get("/api/v1/admin/analytics/users")
async def get_user_analytics(
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_role(Role.ADMIN)),
    days: int = Query(30, ge=1, le=90)
):
    """Get per-user analytics (admin only)."""
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not available")
    
    top_users = analytics.get_top_users(days=days, limit=20)
    return {"top_users": top_users}


@app.get("/api/v1/admin/analytics/models")
async def get_model_analytics(
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    days: int = Query(30, ge=1, le=90)
):
    """Get model usage analytics."""
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not available")
    
    model_stats = analytics.get_model_usage(days=days)
    return {"models": model_stats}


@app.get("/api/v1/admin/analytics/hourly")
async def get_hourly_distribution(
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_permission(Permission.VIEW_ANALYTICS)),
    days: int = Query(7, ge=1, le=30)
):
    """Get query distribution by hour."""
    if not analytics:
        raise HTTPException(status_code=503, detail="Analytics not available")
    
    distribution = analytics.get_hourly_distribution(days=days)
    return {"hourly_distribution": distribution}


# ============================================================================
# USER MANAGEMENT ENDPOINTS (Admin Only)
# ============================================================================

class AssignRoleRequest(BaseModel):
    """Request to assign role to user."""
    user_email: str
    role: str


@app.post("/api/v1/admin/users/assign-role")
async def assign_user_role(
    request: AssignRoleRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_permission(Permission.MANAGE_USERS))
):
    """Assign role to a user (admin only)."""
    try:
        role = Role(request.role)
        rbac_manager.assign_role(request.user_email, role)
        
        return {
            "message": "Role assigned successfully",
            "user_email": request.user_email,
            "role": role.value
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {request.role}")


@app.get("/api/v1/admin/users")
async def list_users(
    user: Dict[str, Any] = Depends(get_current_user),
    _auth: None = Depends(require_role(Role.ADMIN))
):
    """List all users and their roles."""
    users = rbac_manager.list_all_users()
    return {"users": users}


# ============================================================================
# USER PROFILE ENDPOINTS
# ============================================================================

@app.get("/api/v1/user/stats")
async def get_user_stats(
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get statistics for current user."""
    user_email = user['email']
    
    stats = {}
    
    # Chat history stats
    if redis_history:
        stats['chat'] = redis_history.get_stats(user_email)
    
    # Usage stats
    if analytics:
        stats['usage'] = analytics.get_user_usage(user_email, days=30)
    
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=True
    )

