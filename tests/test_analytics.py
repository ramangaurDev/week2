"""
Comprehensive test suite for analytics tracking.
Tests usage metrics, latency tracking, and token cost calculations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from app.analytics import AnalyticsTracker


class TestAnalyticsTracker:
    """Test analytics tracking functionality."""
    
    @pytest.fixture
    def mock_firestore(self):
        """Mock Firestore client."""
        with patch('app.analytics.firestore.Client') as mock:
            db_client = MagicMock()
            mock.return_value = db_client
            collection_mock = MagicMock()
            db_client.collection.return_value = collection_mock
            yield collection_mock
    
    @pytest.fixture
    def tracker(self, mock_firestore):
        """Create AnalyticsTracker with mocked Firestore."""
        return AnalyticsTracker(project_id='test-project')
    
    def test_initialization(self, tracker, mock_firestore):
        """Test tracker initialization."""
        assert tracker.collection is not None
    
    def test_track_query_success(self, tracker, mock_firestore):
        """Test tracking successful query."""
        tracker.track_query(
            user_email='test@example.com',
            query='What is AI?',
            response_time_ms=150.5,
            token_usage={'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30},
            model='gemini-pro',
            success=True
        )
        
        mock_firestore.add.assert_called_once()
        call_args = mock_firestore.add.call_args[0][0]
        assert call_args['type'] == 'query'
        assert call_args['user_email'] == 'test@example.com'
        assert call_args['success'] is True
        assert call_args['response_time_ms'] == 150.5
    
    def test_track_query_failure(self, tracker, mock_firestore):
        """Test tracking failed query."""
        tracker.track_query(
            user_email='test@example.com',
            query='Test query',
            response_time_ms=50.0,
            token_usage={'input_tokens': 10, 'output_tokens': 0, 'total_tokens': 10},
            model='gemini-pro',
            success=False,
            error='Rate limit exceeded'
        )
        
        mock_firestore.add.assert_called_once()
        call_args = mock_firestore.add.call_args[0][0]
        assert call_args['success'] is False
        assert call_args['error'] == 'Rate limit exceeded'
    
    def test_track_query_with_metadata(self, tracker, mock_firestore):
        """Test tracking query with additional metadata."""
        metadata = {'chunks_retrieved': 5, 'rerank_score': 0.95}
        
        tracker.track_query(
            user_email='test@example.com',
            query='Test',
            response_time_ms=100.0,
            token_usage={'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30},
            model='gemini-pro',
            metadata=metadata
        )
        
        call_args = mock_firestore.add.call_args[0][0]
        assert call_args['metadata'] == metadata
    
    def test_track_document_upload(self, tracker, mock_firestore):
        """Test tracking document upload."""
        tracker.track_document_upload(
            user_email='test@example.com',
            filename='document.pdf',
            file_size_bytes=1024000,
            chunks_created=10,
            processing_time_ms=500.0
        )
        
        mock_firestore.add.assert_called_once()
        call_args = mock_firestore.add.call_args[0][0]
        assert call_args['type'] == 'document_upload'
        assert call_args['filename'] == 'document.pdf'
        assert call_args['file_size_bytes'] == 1024000
        assert call_args['chunks_created'] == 10
    
    def test_get_usage_stats(self, tracker, mock_firestore):
        """Test retrieving usage statistics."""
        # Mock query results
        mock_docs = [
            MagicMock(to_dict=lambda: {
                'user_email': 'user1@example.com',
                'response_time_ms': 100,
                'token_usage': {'total_tokens': 30},
                'token_cost_usd': 0.001,
                'success': True,
                'date': '2026-02-06'
            }),
            MagicMock(to_dict=lambda: {
                'user_email': 'user2@example.com',
                'response_time_ms': 200,
                'token_usage': {'total_tokens': 50},
                'token_cost_usd': 0.002,
                'success': True,
                'date': '2026-02-06'
            })
        ]
        mock_firestore.where.return_value.where.return_value.where.return_value.stream.return_value = mock_docs
        
        stats = tracker.get_usage_stats()
        
        assert 'queries' in stats
        assert 'tokens' in stats
        assert 'cost' in stats
        assert 'users' in stats
    
    def test_get_user_usage(self, tracker, mock_firestore):
        """Test retrieving user-specific statistics."""
        mock_docs = [
            MagicMock(to_dict=lambda: {
                'user_email': 'test@example.com',
                'response_time_ms': 150,
                'token_usage': {'total_tokens': 40},
                'success': True,
                'token_cost_usd': 0.001,
                'date': '2026-02-06'
            })
        ]
        mock_firestore.where.return_value.where.return_value.where.return_value.stream.return_value = mock_docs
        
        stats = tracker.get_user_usage('test@example.com', days=30)
        
        assert isinstance(stats, dict)
    
    def test_get_hourly_distribution(self, tracker, mock_firestore):
        """Test retrieving hourly query distribution."""
        mock_docs = [
            MagicMock(to_dict=lambda: {'hour': 10, 'date': '2026-02-06'}),
            MagicMock(to_dict=lambda: {'hour': 10, 'date': '2026-02-06'}),
            MagicMock(to_dict=lambda: {'hour': 14, 'date': '2026-02-06'})
        ]
        mock_firestore.where.return_value.where.return_value.stream.return_value = mock_docs
        
        distribution = tracker.get_hourly_distribution(days=7)
        
        assert isinstance(distribution, dict)
        assert len(distribution) == 24  # 24 hours
    
    def test_get_model_usage(self, tracker, mock_firestore):
        """Test retrieving model usage statistics."""
        mock_docs = [
            MagicMock(to_dict=lambda: {
                'token_usage': {'total_tokens': 100},
                'token_cost_usd': 0.005,
                'model': 'gemini-pro',
                'response_time_ms': 150,
                'date': '2026-02-06'
            }),
            MagicMock(to_dict=lambda: {
                'token_usage': {'total_tokens': 200},
                'token_cost_usd': 0.010,
                'model': 'gemini-flash',
                'response_time_ms': 100,
                'date': '2026-02-06'
            })
        ]
        mock_firestore.where.return_value.where.return_value.stream.return_value = mock_docs
        
        model_stats = tracker.get_model_usage(days=30)
        
        assert isinstance(model_stats, dict)
        assert 'gemini-pro' in model_stats or 'gemini-flash' in model_stats
    
    def test_get_top_users(self, tracker, mock_firestore):
        """Test retrieving top users by query count."""
        mock_docs = [
            MagicMock(to_dict=lambda: {'user_email': 'user1@example.com', 'date': '2026-02-06'}),
            MagicMock(to_dict=lambda: {'user_email': 'user1@example.com', 'date': '2026-02-06'}),
            MagicMock(to_dict=lambda: {'user_email': 'user2@example.com', 'date': '2026-02-06'})
        ]
        mock_firestore.where.return_value.where.return_value.stream.return_value = mock_docs
        
        top_users = tracker.get_top_users(days=7, limit=10)
        
        assert isinstance(top_users, list)
        if top_users:
            assert 'user_email' in top_users[0]
            assert 'query_count' in top_users[0]
