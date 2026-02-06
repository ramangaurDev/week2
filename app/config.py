"""
Production-grade configuration management using GCP Secret Manager.
"""

import os
from typing import Optional, Dict, Any
from functools import lru_cache
import logging

# Optional Secret Manager import for production
try:
    from google.cloud.secretmanager_v1 import SecretManagerServiceClient
    SECRET_MANAGER_AVAILABLE = True
except ImportError:
    SECRET_MANAGER_AVAILABLE = False
    SecretManagerServiceClient = None

logger = logging.getLogger(__name__)


class Config:
    """Production configuration with GCP Secret Manager integration."""
    
    def __init__(self):
        # GCP Configuration
        self.PROJECT_ID = os.getenv("PROJECT_ID", "btoproject-486405-486604")
        self.REGION = os.getenv("REGION", "us-central1")
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
        
        # Vertex AI Configuration
        self.VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", self.REGION)
        self.VERTEX_INDEX_ID = os.getenv("VERTEX_INDEX_ID")
        self.VERTEX_INDEX_ENDPOINT = os.getenv("VERTEX_INDEX_ENDPOINT")
        self.DEPLOYED_INDEX_ID = os.getenv("DEPLOYED_INDEX_ID", "rag-index-deployed")
        
        # Model Configuration
        self.MODEL_VARIANT = os.getenv("MODEL_VARIANT", "gemini-2.0-flash-001")
        self.EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")
        self.MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8000"))
        self.EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
        
        # Application Configuration
        self.MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB
        self.MAX_FILES_PER_REQUEST = int(os.getenv("MAX_FILES_PER_REQUEST", "10"))
        self.RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        self.CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour
        
        # Timeout Configuration
        self.EMBEDDING_TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT", "30"))
        self.GENERATION_TIMEOUT = int(os.getenv("GENERATION_TIMEOUT", "60"))
        self.VECTOR_SEARCH_TIMEOUT = int(os.getenv("VECTOR_SEARCH_TIMEOUT", "10"))
        
        # Retry Configuration
        self.MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
        self.RETRY_DELAY = int(os.getenv("RETRY_DELAY", "1"))
        
        # Firestore Configuration (for persistent chunk storage)
        self.USE_FIRESTORE = os.getenv("USE_FIRESTORE", "true").lower() == "true"
        self.FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "rag_chunks")
        
        # Cloud Storage Configuration (for document storage)
        self.GCS_BUCKET = os.getenv("GCS_BUCKET", f"{self.PROJECT_ID}-rag-documents")
        
        # Logging Configuration
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        
        # Secret Manager Client
        self._secret_client = None
    
    @property
    def secret_client(self):
        """Lazy initialization of Secret Manager client."""
        if not SECRET_MANAGER_AVAILABLE or SecretManagerServiceClient is None:
            logger.warning("Secret Manager not available - running in local mode")
            return None
        if self._secret_client is None:
            self._secret_client = SecretManagerServiceClient()
        return self._secret_client
    
    @lru_cache(maxsize=128)
    def get_secret(self, secret_id: str, version: str = "latest") -> str:
        """
        Retrieve secret from GCP Secret Manager with caching.
        
        Args:
            secret_id: Secret identifier
            version: Secret version (default: latest)
        
        Returns:
            Secret value as string
        """
        if not SECRET_MANAGER_AVAILABLE or self.secret_client is None:
            logger.warning(f"Secret Manager not available, cannot retrieve secret: {secret_id}")
            # In production, this would fail - in local dev, return empty string
            return os.getenv(secret_id, "")
        
        try:
            name = f"projects/{self.PROJECT_ID}/secrets/{secret_id}/versions/{version}"
            response = self.secret_client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            logger.error(f"Failed to retrieve secret {secret_id}: {e}")
            # Fallback to environment variable
            return os.getenv(secret_id, "")
    
    def validate(self) -> Dict[str, Any]:
        """
        Validate configuration and return status.
        
        Returns:
            Dict with validation results
        """
        issues = []
        
        if not self.PROJECT_ID:
            issues.append("PROJECT_ID is not set")
        
        if not self.VERTEX_INDEX_ID:
            issues.append("VERTEX_INDEX_ID is not set")
        
        if not self.VERTEX_INDEX_ENDPOINT:
            issues.append("VERTEX_INDEX_ENDPOINT is not set")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "config": {
                "project_id": self.PROJECT_ID,
                "region": self.REGION,
                "environment": self.ENVIRONMENT,
                "model": self.MODEL_VARIANT,
                "embedding_model": self.EMBEDDING_MODEL
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary (excluding secrets)."""
        return {
            "project_id": self.PROJECT_ID,
            "region": self.REGION,
            "environment": self.ENVIRONMENT,
            "vertex_location": self.VERTEX_LOCATION,
            "model_variant": self.MODEL_VARIANT,
            "embedding_model": self.EMBEDDING_MODEL,
            "max_tokens": self.MAX_TOKENS,
            "embedding_dimension": self.EMBEDDING_DIMENSION,
            "max_file_size": self.MAX_FILE_SIZE,
            "rate_limit": self.RATE_LIMIT_PER_MINUTE,
            "use_firestore": self.USE_FIRESTORE,
            "gcs_bucket": self.GCS_BUCKET
        }


# Global configuration instance
config = Config()
