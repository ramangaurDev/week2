"""
Advanced semantic chunking using sentence embeddings and semantic similarity.
Replaces size-based chunking with intelligent semantic boundary detection.
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from app.logging_config import get_logger

logger = get_logger(__name__)

# Try to import spacy for sentence splitting
try:
    import spacy
    SPACY_AVAILABLE = True
    # Load small English model
    try:
        nlp = spacy.load("en_core_web_sm")
    except:
        nlp = None
        SPACY_AVAILABLE = False
except ImportError:
    SPACY_AVAILABLE = False
    nlp = None


@dataclass
class SemanticChunk:
    """Represents a semantically coherent chunk of text."""
    text: str
    start_idx: int
    end_idx: int
    sentences: List[str]
    avg_embedding: Optional[np.ndarray] = None


class SemanticChunker:
    """
    Advanced chunker that splits text at semantic boundaries using embeddings.
    """
    
    def __init__(
        self,
        embedder=None,
        max_chunk_size: int = 2800,
        min_chunk_size: int = 500,
        similarity_threshold: float = 0.75
    ):
        """
        Initialize semantic chunker.
        
        Args:
            embedder: Text embedding model (Vertex AI TextEmbeddingModel)
            max_chunk_size: Maximum characters per chunk
            min_chunk_size: Minimum characters per chunk
            similarity_threshold: Cosine similarity threshold for merging sentences
        """
        self.embedder = embedder
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.similarity_threshold = similarity_threshold
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into semantically coherent chunks.
        
        Args:
            text: Input text to chunk
        
        Returns:
            List of text chunks
        """
        # Clean text
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        
        # Split into sentences
        sentences = self._split_sentences(text)
        if not sentences:
            return [text]
        
        logger.info(f"Split text into {len(sentences)} sentences")
        
        # If no embedder available, fall back to size-based chunking with sentence boundaries
        if not self.embedder:
            return self._chunk_by_sentences(sentences)
        
        # Semantic chunking with embeddings
        try:
            chunks = self._semantic_chunk(sentences)
            logger.info(f"Created {len(chunks)} semantic chunks")
            return chunks
        except Exception as e:
            logger.warning(f"Semantic chunking failed: {e}, falling back to sentence-based")
            return self._chunk_by_sentences(sentences)
    
    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using spaCy or regex fallback.
        """
        if SPACY_AVAILABLE and nlp:
            # Use spaCy for accurate sentence splitting
            doc = nlp(text)
            sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        else:
            # Fallback: regex-based sentence splitting
            # Split on periods, exclamation marks, question marks followed by space/newline
            pattern = r'(?<=[.!?])\s+(?=[A-Z])'
            sentences = re.split(pattern, text)
            sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def _chunk_by_sentences(self, sentences: List[str]) -> List[str]:
        """
        Fallback chunking that respects sentence boundaries.
        """
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sent_len = len(sentence)
            
            # If sentence itself exceeds max size, force split it
            if sent_len > self.max_chunk_size:
                # Finalize current chunk if any
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                # Split the long sentence into max_chunk_size pieces
                for i in range(0, sent_len, self.max_chunk_size):
                    chunks.append(sentence[i:i + self.max_chunk_size])
                continue
            
            # If adding this sentence exceeds max size, finalize current chunk
            if current_size + sent_len > self.max_chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_size = sent_len
            else:
                current_chunk.append(sentence)
                current_size += sent_len
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _semantic_chunk(self, sentences: List[str]) -> List[str]:
        """
        Create chunks based on semantic similarity between sentences.
        """
        if not sentences:
            return []
        
        # Get embeddings for all sentences
        embeddings = self._get_sentence_embeddings(sentences)
        
        # Calculate similarity between consecutive sentences
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
            similarities.append(sim)
        
        # Find split points where similarity drops below threshold
        split_points = [0]
        current_chunk_size = len(sentences[0])
        
        for i, sim in enumerate(similarities):
            current_chunk_size += len(sentences[i + 1])
            
            # Split if:
            # 1. Similarity is below threshold (semantic break)
            # 2. OR chunk size exceeds maximum
            if sim < self.similarity_threshold or current_chunk_size > self.max_chunk_size:
                split_points.append(i + 1)
                current_chunk_size = len(sentences[i + 1])
        
        split_points.append(len(sentences))
        
        # Create chunks from split points
        chunks = []
        for i in range(len(split_points) - 1):
            start = split_points[i]
            end = split_points[i + 1]
            chunk_sentences = sentences[start:end]
            
            # Ensure minimum chunk size
            chunk_text = " ".join(chunk_sentences)
            if len(chunk_text) >= self.min_chunk_size or i == len(split_points) - 2:
                chunks.append(chunk_text)
            elif chunks:
                # Merge with previous chunk if too small
                chunks[-1] += " " + chunk_text
        
        return chunks
    
    def _get_sentence_embeddings(self, sentences: List[str]) -> List[np.ndarray]:
        """
        Get embeddings for a list of sentences.
        """
        try:
            # Batch embed sentences
            embeddings = self.embedder.get_embeddings(sentences)
            return [np.array(emb.values) for emb in embeddings]
        except Exception as e:
            logger.error(f"Failed to get embeddings: {e}")
            raise
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.
        """
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))


def create_semantic_chunks(
    text: str,
    embedder=None,
    max_chunk_size: int = 2800,
    min_chunk_size: int = 500,
    similarity_threshold: float = 0.75
) -> List[str]:
    """
    Convenience function to create semantic chunks from text.
    
    Args:
        text: Input text
        embedder: Optional embedder for semantic splitting
        max_chunk_size: Maximum chunk size in characters
        min_chunk_size: Minimum chunk size in characters
        similarity_threshold: Similarity threshold for semantic boundaries
    
    Returns:
        List of semantically coherent chunks
    """
    chunker = SemanticChunker(
        embedder=embedder,
        max_chunk_size=max_chunk_size,
        min_chunk_size=min_chunk_size,
        similarity_threshold=similarity_threshold
    )
    return chunker.chunk_text(text)
