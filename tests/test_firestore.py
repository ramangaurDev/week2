"""
Tests for Firestore chunk storage.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.storage.firestore_store import FirestoreChunkStore


@pytest.fixture
def mock_firestore_client():
    """Create mock Firestore client."""
    with patch('app.storage.firestore_store.firestore.Client') as mock_client:
        client_instance = Mock()
        collection_mock = Mock()
        client_instance.collection.return_value = collection_mock
        mock_client.return_value = client_instance
        yield mock_client, client_instance, collection_mock


class TestFirestoreChunkStore:
    """Test Firestore chunk storage."""
    
    def test_initialization_success(self, mock_firestore_client):
        """Test successful Firestore initialization."""
        mock_client, client_instance, _ = mock_firestore_client
        
        store = FirestoreChunkStore(project_id="test-project")
        
        assert store.db is not None
        assert store.collection is not None
        mock_client.assert_called_once_with(project="test-project")
    
    def test_initialization_failure(self):
        """Test Firestore initialization failure."""
        with patch('app.storage.firestore_store.firestore.Client', side_effect=Exception("Connection failed")):
            store = FirestoreChunkStore(project_id="test-project")
            assert store.db is None
            assert store.collection is None
    
    def test_store_chunk_success(self, mock_firestore_client):
        """Test successful chunk storage."""
        _, _, collection_mock = mock_firestore_client
        doc_mock = Mock()
        collection_mock.document.return_value = doc_mock
        
        store = FirestoreChunkStore(project_id="test-project")
        
        chunk_data = {
            "text": "Test chunk",
            "metadata": {"source": "test.pdf"},
            "vector": [0.1, 0.2, 0.3]
        }
        
        result = store.store_chunk("chunk_123", chunk_data)
        
        assert result is True
        collection_mock.document.assert_called_once_with("chunk_123")
        doc_mock.set.assert_called_once()
    
    def test_store_chunk_no_collection(self):
        """Test chunk storage without initialized collection."""
        with patch('app.storage.firestore_store.firestore.Client', side_effect=Exception("Init failed")):
            store = FirestoreChunkStore(project_id="test-project")
            result = store.store_chunk("chunk_123", {"text": "test"})
            assert result is False
    
    def test_store_chunk_failure(self, mock_firestore_client):
        """Test chunk storage failure."""
        _, _, collection_mock = mock_firestore_client
        doc_mock = Mock()
        doc_mock.set.side_effect = Exception("Write failed")
        collection_mock.document.return_value = doc_mock
        
        store = FirestoreChunkStore(project_id="test-project")
        result = store.store_chunk("chunk_123", {"text": "test"})
        
        assert result is False
    
    def test_batch_store_chunks_success(self, mock_firestore_client):
        """Test successful batch chunk storage."""
        _, client_instance, collection_mock = mock_firestore_client
        batch_mock = Mock()
        client_instance.batch.return_value = batch_mock
        
        store = FirestoreChunkStore(project_id="test-project")
        
        chunks = {
            "chunk_1": {"text": "First chunk", "vector": [0.1]},
            "chunk_2": {"text": "Second chunk", "vector": [0.2]}
        }
        
        result = store.batch_store_chunks(chunks)
        
        assert result == 2
        batch_mock.commit.assert_called_once()
    
    def test_count_chunks_success(self, mock_firestore_client):
        """Test successful chunk counting."""
        _, _, collection_mock = mock_firestore_client
        
        # Mock count query result
        count_query_mock = Mock()
        count_result_mock = MagicMock()
        count_obj_mock = Mock()
        count_obj_mock.value = 42
        count_result_mock.__getitem__ = Mock(return_value=[count_obj_mock])
        count_query_mock.get.return_value = count_result_mock
        
        collection_mock.count.return_value = count_query_mock
        
        store = FirestoreChunkStore(project_id="test-project")
        result = store.count_chunks()
        
        assert result == 42
        collection_mock.count.assert_called_once()
    
    def test_count_chunks_fallback(self, mock_firestore_client):
        """Test chunk counting fallback to manual count."""
        _, _, collection_mock = mock_firestore_client
        
        # Mock count query failure
        count_query_mock = Mock()
        count_query_mock.get.side_effect = ValueError("Aggregate not supported")
        
        # Mock stream for fallback
        doc1 = Mock()
        doc2 = Mock()
        doc3 = Mock()
        collection_mock.stream.return_value = [doc1, doc2, doc3]
        
        collection_mock.count.return_value = count_query_mock
        
        store = FirestoreChunkStore(project_id="test-project")
        result = store.count_chunks()
        
        assert result == 3
        collection_mock.stream.assert_called_once()
