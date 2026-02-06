"""
Comprehensive tests for app/rag/generator.py
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from app.rag.generator import GeminiGenerator


class TestGeminiGenerator:
    """Test suite for GeminiGenerator class."""
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_initialization(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test generator initialization."""
        mock_embedder = Mock()
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(
            project="test-project",
            location="us-central1",
            model="gemini-2.0-flash-001"
        )
        
        assert generator.project == "test-project"
        assert generator.location == "us-central1"
        assert generator.model_name == "gemini-2.0-flash-001"
        assert generator.max_tokens == 8000
        mock_vertexai.init.assert_called_once_with(project="test-project", location="us-central1")
        mock_gen_model.assert_called_once_with("gemini-2.0-flash-001")
        mock_embedding_model.from_pretrained.assert_called_once_with("text-embedding-004")
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    @patch.dict("os.environ", {"MAX_TOKENS": "4000"})
    def test_initialization_custom_max_tokens(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test initialization with custom max_tokens from env."""
        mock_embedder = Mock()
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        assert generator.max_tokens == 4000
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_embed(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test text embedding."""
        mock_embedding = Mock()
        mock_embedding.values = [0.1, 0.2, 0.3, 0.4]
        
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        result = generator._embed("test text")
        
        assert result == [0.1, 0.2, 0.3, 0.4]
        mock_embedder.get_embeddings.assert_called_once_with(["test text"])
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_generate_success(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test successful answer generation."""
        # Setup mocks
        mock_response = Mock()
        mock_response.text = "This is the answer based on context."
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50
        mock_response.usage_metadata.total_token_count = 150
        
        mock_gen_instance = Mock()
        mock_gen_instance.generate_content.return_value = mock_response
        mock_gen_model.return_value = mock_gen_instance
        
        mock_embedding = Mock()
        mock_embedding.values = [0.5, 0.5]
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        question = "What is the answer?"
        contexts = ["Context 1", "Context 2"]
        
        answer, citations, token_usage = generator.generate(question, contexts, temperature=0.2)
        
        assert answer == "This is the answer based on context."
        assert len(citations) <= 3
        assert token_usage["prompt_tokens"] == 100
        assert token_usage["completion_tokens"] == 50
        assert token_usage["total_tokens"] == 150
        
        mock_gen_instance.generate_content.assert_called_once()
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_answer_method(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test answer method (same as generate)."""
        mock_response = Mock()
        mock_response.text = "Answer text"
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 80
        mock_response.usage_metadata.candidates_token_count = 40
        mock_response.usage_metadata.total_token_count = 120
        
        mock_gen_instance = Mock()
        mock_gen_instance.generate_content.return_value = mock_response
        mock_gen_model.return_value = mock_gen_instance
        
        mock_embedding = Mock()
        mock_embedding.values = [0.5, 0.5]
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        answer, citations, token_usage = generator.answer("Question?", ["Context"])
        
        assert answer == "Answer text"
        assert token_usage["total_tokens"] == 120
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_generate_error_handling(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test error handling during generation."""
        mock_gen_instance = Mock()
        mock_gen_instance.generate_content.side_effect = Exception("API Error")
        mock_gen_model.return_value = mock_gen_instance
        
        mock_embedder = Mock()
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        answer, citations, token_usage = generator.generate("Question?", ["Context"])
        
        assert "Error generating answer" in answer
        assert citations == []
        assert token_usage["total_tokens"] == 0
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_build_prompt(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test prompt building."""
        mock_embedder = Mock()
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        question = "What is AI?"
        contexts = ["Context one", "Context two", "Context three"]
        
        prompt = generator._build_prompt(question, contexts)
        
        assert "What is AI?" in prompt
        assert "[1] Context one" in prompt
        assert "[2] Context two" in prompt
        assert "[3] Context three" in prompt
        assert "You are a helpful AI assistant" in prompt
        assert "Answer ONLY based on the provided context" in prompt
        assert "personal data" in prompt.lower()
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_compress_context_empty(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test compress_context with empty contexts."""
        mock_embedder = Mock()
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        result = generator.compress_context([], "query", max_tokens=1000)
        
        assert result == []
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_compress_context_under_limit(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test compress_context when already under token limit."""
        mock_embedder = Mock()
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        contexts = ["Short context one", "Short context two"]
        result = generator.compress_context(contexts, "query", max_tokens=10000)
        
        assert result == contexts
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_compress_context_needs_compression(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test compress_context when compression is needed."""
        mock_embedding = Mock()
        mock_embedding.values = np.random.rand(768).tolist()
        
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        # Create long contexts that exceed token limit
        long_context = "A" * 5000  # ~1250 tokens
        contexts = [long_context] * 10  # ~12500 tokens total
        
        result = generator.compress_context(contexts, "query", max_tokens=1000)
        
        # Should be compressed
        assert len(result) < len(contexts)
        # Estimate total tokens in result
        total_chars = sum(len(ctx) for ctx in result)
        estimated_tokens = total_chars // 4
        assert estimated_tokens <= 1000
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_compress_context_with_truncation(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test compress_context with partial truncation."""
        mock_embedding = Mock()
        mock_embedding.values = [0.5] * 768
        
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        contexts = ["Context " + str(i) * 1000 for i in range(5)]
        result = generator.compress_context(contexts, "query", max_tokens=500)
        
        assert len(result) > 0
        # Check total size is within limit
        total_chars = sum(len(ctx) for ctx in result)
        assert total_chars <= 500 * 4  # max_tokens * 4 chars/token
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_compress_context_error_fallback(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test compress_context error handling with fallback."""
        mock_embedder = Mock()
        mock_embedder.get_embeddings.side_effect = Exception("Embedding error")
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        contexts = ["Context 1", "Context 2", "Context 3"]
        result = generator.compress_context(contexts, "query", max_tokens=100)
        
        # Should fallback to simple truncation
        assert len(result) > 0
        total_chars = sum(len(ctx) for ctx in result)
        assert total_chars <= 100 * 4
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_extract_citations_empty(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test extract_citations with empty contexts."""
        mock_embedder = Mock()
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        result = generator._extract_citations("Some answer", [])
        
        assert result == []
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_extract_citations_success(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test successful citation extraction."""
        mock_embedding = Mock()
        mock_embedding.values = [0.8, 0.6, 0.4, 0.2]
        
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        contexts = ["Context A", "Context B", "Context C", "Context D"]
        result = generator._extract_citations("Answer text", contexts)
        
        # Should return top 3
        assert len(result) == 3
        assert all(ctx in contexts for ctx in result)
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_extract_citations_fewer_than_three(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test citation extraction with fewer than 3 contexts."""
        mock_embedding = Mock()
        mock_embedding.values = [0.5, 0.5]
        
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        contexts = ["Context 1", "Context 2"]
        result = generator._extract_citations("Answer", contexts)
        
        assert len(result) == 2
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_extract_citations_error_fallback(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test citation extraction error handling."""
        mock_embedder = Mock()
        mock_embedder.get_embeddings.side_effect = Exception("Embedding error")
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        contexts = ["Context 1", "Context 2", "Context 3", "Context 4"]
        result = generator._extract_citations("Answer", contexts)
        
        # Fallback: return first 3
        assert result == contexts[:3]
    
    @patch("app.rag.generator.vertexai")
    @patch("app.rag.generator.GenerativeModel")
    @patch("app.rag.generator.TextEmbeddingModel")
    def test_generate_no_usage_metadata(self, mock_embedding_model, mock_gen_model, mock_vertexai):
        """Test generation when response has no usage metadata."""
        mock_response = Mock()
        mock_response.text = "Answer without metadata"
        mock_response.usage_metadata = None
        
        mock_gen_instance = Mock()
        mock_gen_instance.generate_content.return_value = mock_response
        mock_gen_model.return_value = mock_gen_instance
        
        mock_embedding = Mock()
        mock_embedding.values = [0.5, 0.5]
        mock_embedder = Mock()
        mock_embedder.get_embeddings.return_value = [mock_embedding]
        mock_embedding_model.from_pretrained.return_value = mock_embedder
        
        generator = GeminiGenerator(project="test", location="us-central1")
        
        answer, citations, token_usage = generator.generate("Question?", ["Context"])
        
        assert answer == "Answer without metadata"
        assert token_usage["prompt_tokens"] == 0
        assert token_usage["completion_tokens"] == 0
        assert token_usage["total_tokens"] == 0
