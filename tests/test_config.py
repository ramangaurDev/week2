"""
Comprehensive tests for app/config.py
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from app.config import Config


class TestConfig:
    """Test suite for Config class."""
    
    def test_config_initialization_defaults(self):
        """Test config initialization with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            
            assert config.PROJECT_ID == "btoproject-486405-486604"
            assert config.REGION == "us-central1"
            assert config.ENVIRONMENT == "production"
            assert config.MODEL_VARIANT == "gemini-2.0-flash-001"
            assert config.EMBEDDING_MODEL == "text-embedding-004"
            assert config.MAX_TOKENS == 8000
            assert config.EMBEDDING_DIMENSION == 768
            assert config.MAX_FILE_SIZE == 10485760
            assert config.MAX_FILES_PER_REQUEST == 10
            assert config.RATE_LIMIT_PER_MINUTE == 60
            assert config.CACHE_TTL == 3600
            assert config.EMBEDDING_TIMEOUT == 30
            assert config.GENERATION_TIMEOUT == 60
            assert config.VECTOR_SEARCH_TIMEOUT == 10
            assert config.MAX_RETRIES == 3
            assert config.RETRY_DELAY == 1
            assert config.USE_FIRESTORE is True
            assert config.FIRESTORE_COLLECTION == "rag_chunks"
            assert config.GCS_BUCKET == "btoproject-486405-486604-rag-documents"
            assert config.LOG_LEVEL == "INFO"
    
    def test_config_initialization_from_env(self):
        """Test config initialization from environment variables."""
        env_vars = {
            "PROJECT_ID": "test-project",
            "REGION": "us-west1",
            "ENVIRONMENT": "development",
            "VERTEX_LOCATION": "us-east1",
            "VERTEX_INDEX_ID": "test-index-123",
            "VERTEX_INDEX_ENDPOINT": "test-endpoint",
            "DEPLOYED_INDEX_ID": "custom-deployed",
            "MODEL_VARIANT": "gemini-pro",
            "EMBEDDING_MODEL": "text-embedding-005",
            "MAX_TOKENS": "4000",
            "EMBEDDING_DIMENSION": "512",
            "MAX_FILE_SIZE": "5242880",
            "MAX_FILES_PER_REQUEST": "5",
            "RATE_LIMIT_PER_MINUTE": "30",
            "CACHE_TTL": "1800",
            "EMBEDDING_TIMEOUT": "20",
            "GENERATION_TIMEOUT": "40",
            "VECTOR_SEARCH_TIMEOUT": "5",
            "MAX_RETRIES": "5",
            "RETRY_DELAY": "2",
            "USE_FIRESTORE": "false",
            "FIRESTORE_COLLECTION": "custom_chunks",
            "GCS_BUCKET": "custom-bucket",
            "LOG_LEVEL": "DEBUG"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            
            assert config.PROJECT_ID == "test-project"
            assert config.REGION == "us-west1"
            assert config.ENVIRONMENT == "development"
            assert config.VERTEX_LOCATION == "us-east1"
            assert config.VERTEX_INDEX_ID == "test-index-123"
            assert config.VERTEX_INDEX_ENDPOINT == "test-endpoint"
            assert config.DEPLOYED_INDEX_ID == "custom-deployed"
            assert config.MODEL_VARIANT == "gemini-pro"
            assert config.EMBEDDING_MODEL == "text-embedding-005"
            assert config.MAX_TOKENS == 4000
            assert config.EMBEDDING_DIMENSION == 512
            assert config.MAX_FILE_SIZE == 5242880
            assert config.MAX_FILES_PER_REQUEST == 5
            assert config.RATE_LIMIT_PER_MINUTE == 30
            assert config.CACHE_TTL == 1800
            assert config.EMBEDDING_TIMEOUT == 20
            assert config.GENERATION_TIMEOUT == 40
            assert config.VECTOR_SEARCH_TIMEOUT == 5
            assert config.MAX_RETRIES == 5
            assert config.RETRY_DELAY == 2
            assert config.USE_FIRESTORE is False
            assert config.FIRESTORE_COLLECTION == "custom_chunks"
            assert config.GCS_BUCKET == "custom-bucket"
            assert config.LOG_LEVEL == "DEBUG"
    
    def test_secret_client_not_available(self):
        """Test secret client when Secret Manager is not available."""
        config = Config()
        
        with patch("app.config.SECRET_MANAGER_AVAILABLE", False):
            client = config.secret_client
            assert client is None
    
    @patch("app.config.SecretManagerServiceClient")
    def test_secret_client_initialization(self, mock_client_class):
        """Test lazy initialization of secret client."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        with patch("app.config.SECRET_MANAGER_AVAILABLE", True):
            config = Config()
            config._secret_client = None  # Reset
            
            # First access initializes
            client1 = config.secret_client
            assert client1 == mock_client
            mock_client_class.assert_called_once()
            
            # Second access reuses
            client2 = config.secret_client
            assert client2 == mock_client
            assert mock_client_class.call_count == 1
    
    def test_get_secret_not_available(self):
        """Test get_secret when Secret Manager is not available."""
        config = Config()
        
        with patch("app.config.SECRET_MANAGER_AVAILABLE", False):
            with patch.dict(os.environ, {"TEST_SECRET": "fallback_value"}):
                secret = config.get_secret("TEST_SECRET")
                assert secret == "fallback_value"
    
    @patch("app.config.SECRET_MANAGER_AVAILABLE", False)
    def test_get_secret_no_client(self):
        """Test get_secret when client is None."""
        config = Config()
        
        with patch.dict(os.environ, {"TEST_SECRET": "env_value"}):
            secret = config.get_secret("TEST_SECRET")
            assert secret == "env_value"
    
    @patch("app.config.SecretManagerServiceClient")
    def test_get_secret_success(self, mock_client_class):
        """Test successful secret retrieval."""
        mock_response = Mock()
        mock_response.payload.data.decode.return_value = "secret_value"
        
        mock_client = Mock()
        mock_client.access_secret_version.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        with patch("app.config.SECRET_MANAGER_AVAILABLE", True):
            config = Config()
            config._secret_client = mock_client
            
            secret = config.get_secret("my-secret", "latest")
            
            assert secret == "secret_value"
            mock_client.access_secret_version.assert_called_once()
            call_args = mock_client.access_secret_version.call_args
            assert "projects/btoproject-486405-486604/secrets/my-secret/versions/latest" in call_args[1]["request"]["name"]
    
    @patch("app.config.SecretManagerServiceClient")
    def test_get_secret_failure_fallback(self, mock_client_class):
        """Test get_secret falls back to env var on error."""
        mock_client = Mock()
        mock_client.access_secret_version.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client
        
        with patch("app.config.SECRET_MANAGER_AVAILABLE", True):
            with patch.dict(os.environ, {"FAILED_SECRET": "env_fallback"}):
                config = Config()
                config._secret_client = mock_client
                
                secret = config.get_secret("FAILED_SECRET")
                
                assert secret == "env_fallback"
    
    def test_validate_success(self):
        """Test validation with all required fields."""
        env_vars = {
            "PROJECT_ID": "test-project",
            "VERTEX_INDEX_ID": "index-123",
            "VERTEX_INDEX_ENDPOINT": "endpoint-456"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            result = config.validate()
            
            assert result["valid"] is True
            assert len(result["issues"]) == 0
            assert result["config"]["project_id"] == "test-project"
            assert result["config"]["region"] == "us-central1"
            assert result["config"]["environment"] == "production"
            assert result["config"]["model"] == "gemini-2.0-flash-001"
            assert result["config"]["embedding_model"] == "text-embedding-004"
    
    def test_validate_missing_project_id(self):
        """Test validation fails when PROJECT_ID is missing."""
        with patch.dict(os.environ, {"PROJECT_ID": ""}, clear=True):
            config = Config()
            config.PROJECT_ID = ""
            
            result = config.validate()
            
            assert result["valid"] is False
            assert "PROJECT_ID is not set" in result["issues"]
    
    def test_validate_missing_vertex_index_id(self):
        """Test validation fails when VERTEX_INDEX_ID is missing."""
        with patch.dict(os.environ, {"PROJECT_ID": "test"}, clear=True):
            config = Config()
            config.VERTEX_INDEX_ID = None
            
            result = config.validate()
            
            assert result["valid"] is False
            assert "VERTEX_INDEX_ID is not set" in result["issues"]
    
    def test_validate_missing_vertex_endpoint(self):
        """Test validation fails when VERTEX_INDEX_ENDPOINT is missing."""
        env_vars = {
            "PROJECT_ID": "test",
            "VERTEX_INDEX_ID": "index-123"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            config.VERTEX_INDEX_ENDPOINT = None
            
            result = config.validate()
            
            assert result["valid"] is False
            assert "VERTEX_INDEX_ENDPOINT is not set" in result["issues"]
    
    def test_validate_multiple_issues(self):
        """Test validation with multiple missing fields."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config()
            config.PROJECT_ID = ""
            config.VERTEX_INDEX_ID = None
            config.VERTEX_INDEX_ENDPOINT = None
            
            result = config.validate()
            
            assert result["valid"] is False
            assert len(result["issues"]) == 3
            assert "PROJECT_ID is not set" in result["issues"]
            assert "VERTEX_INDEX_ID is not set" in result["issues"]
            assert "VERTEX_INDEX_ENDPOINT is not set" in result["issues"]
    
    def test_to_dict(self):
        """Test exporting config as dictionary."""
        env_vars = {
            "PROJECT_ID": "test-project",
            "REGION": "us-west1",
            "ENVIRONMENT": "staging",
            "MODEL_VARIANT": "gemini-pro",
            "EMBEDDING_MODEL": "text-embedding-005",
            "MAX_TOKENS": "4000",
            "EMBEDDING_DIMENSION": "512",
            "MAX_FILE_SIZE": "5242880",
            "RATE_LIMIT_PER_MINUTE": "30",
            "USE_FIRESTORE": "false",
            "GCS_BUCKET": "custom-bucket"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config()
            result = config.to_dict()
            
            assert result["project_id"] == "test-project"
            assert result["region"] == "us-west1"
            assert result["environment"] == "staging"
            assert result["model_variant"] == "gemini-pro"
            assert result["embedding_model"] == "text-embedding-005"
            assert result["max_tokens"] == 4000
            assert result["embedding_dimension"] == 512
            assert result["max_file_size"] == 5242880
            assert result["rate_limit"] == 30
            assert result["use_firestore"] is False
            assert result["gcs_bucket"] == "custom-bucket"
            
            # Verify vertex_location defaults to region
            assert result["vertex_location"] == "us-west1"
