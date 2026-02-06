"""
Tests for GCS document storage.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.storage.gcs_store import GCSDocumentStore


@pytest.fixture
def mock_gcs_client():
    """Create mock GCS client."""
    with patch('app.storage.gcs_store.storage.Client') as mock_client:
        client_instance = Mock()
        bucket_mock = Mock()
        bucket_mock.exists.return_value = True
        client_instance.bucket.return_value = bucket_mock
        mock_client.return_value = client_instance
        yield mock_client, client_instance, bucket_mock


class TestGCSDocumentStore:
    """Test GCS document storage."""
    
    def test_initialization_existing_bucket(self, mock_gcs_client):
        """Test initialization with existing bucket."""
        mock_client, client_instance, bucket_mock = mock_gcs_client
        
        store = GCSDocumentStore(project_id="test-project", bucket_name="test-bucket")
        
        assert store.bucket is not None
        client_instance.bucket.assert_called_once_with("test-bucket")
        bucket_mock.exists.assert_called_once()
    
    def test_initialization_creates_bucket(self, mock_gcs_client):
        """Test initialization creates bucket if not exists."""
        mock_client, client_instance, bucket_mock = mock_gcs_client
        bucket_mock.exists.return_value = False
        client_instance.create_bucket.return_value = bucket_mock
        
        store = GCSDocumentStore(project_id="test-project", bucket_name="new-bucket")
        
        assert store.bucket is not None
        client_instance.create_bucket.assert_called_once_with("new-bucket", location="us-central1")
    
    def test_initialization_failure(self):
        """Test GCS initialization failure."""
        with patch('app.storage.gcs_store.storage.Client', side_effect=Exception("Connection failed")):
            store = GCSDocumentStore(project_id="test-project", bucket_name="test-bucket")
            assert store.bucket is None
    
    def test_upload_document_success(self, mock_gcs_client):
        """Test successful document upload."""
        _, _, bucket_mock = mock_gcs_client
        blob_mock = Mock()
        blob_mock.public_url = "https://storage.googleapis.com/bucket/doc.pdf"
        bucket_mock.name = "test-bucket"
        bucket_mock.blob.return_value = blob_mock
        
        store = GCSDocumentStore(project_id="test-project", bucket_name="test-bucket")
        
        content = b"Test document content"
        result = store.upload_document(
            filename="test.pdf",
            content=content,
            content_type="application/pdf"
        )
        
        assert result is not None
        assert result.startswith("gs://test-bucket/documents/")
        assert "test.pdf" in result
        blob_mock.upload_from_string.assert_called_once_with(content, content_type="application/pdf")
    
    def test_upload_document_with_metadata(self, mock_gcs_client):
        """Test document upload with metadata."""
        _, _, bucket_mock = mock_gcs_client
        blob_mock = Mock()
        blob_mock.public_url = "https://storage.googleapis.com/bucket/doc.pdf"
        bucket_mock.blob.return_value = blob_mock
        
        store = GCSDocumentStore(project_id="test-project", bucket_name="test-bucket")
        
        metadata = {"user": "test@example.com", "department": "engineering"}
        result = store.upload_document(
            filename="test.pdf",
            content=b"content",
            metadata=metadata
        )
        
        assert result is not None
        assert blob_mock.metadata == metadata
    
    def test_upload_document_no_bucket(self):
        """Test document upload without initialized bucket."""
        with patch('app.storage.gcs_store.storage.Client', side_effect=Exception("Init failed")):
            store = GCSDocumentStore(project_id="test-project", bucket_name="test-bucket")
            result = store.upload_document("test.pdf", b"content")
            assert result is None
    
    def test_upload_document_failure(self, mock_gcs_client):
        """Test document upload failure."""
        _, _, bucket_mock = mock_gcs_client
        blob_mock = Mock()
        blob_mock.upload_from_string.side_effect = Exception("Upload failed")
        bucket_mock.blob.return_value = blob_mock
        
        store = GCSDocumentStore(project_id="test-project", bucket_name="test-bucket")
        result = store.upload_document("test.pdf", b"content")
        
        assert result is None
