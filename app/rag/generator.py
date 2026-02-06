"""
Enhanced LLM Generator with Claude Sonnet 4.5 support.
Generates grounded answers from retrieved contexts using Gemini or Claude.
"""

import os
from typing import List, Tuple, Dict
import numpy as np
import vertexai
from vertexai.generative_models import GenerativeModel
from vertexai.language_models import TextEmbeddingModel
from app.logging_config import get_logger

logger = get_logger(__name__)

class GeminiGenerator:
    """
    Generates answers using Google Gemini models.
    Supports grounded generation with citations.
    """
    
    def __init__(self, project: str, location: str, model: str = "gemini-2.0-flash-001"):
        vertexai.init(project=project, location=location)
        self.project = project
        self.location = location
        self.model_name = model
        self.gen = GenerativeModel(model)
        self.embedder = TextEmbeddingModel.from_pretrained("text-embedding-004")
        self.max_tokens = int(os.getenv("MAX_TOKENS", "8000"))

    def _embed(self, text: str) -> List[float]:
        """Generate embedding for text."""
        return self.embedder.get_embeddings([text])[0].values

    def generate(self, question: str, contexts: List[str], temperature: float = 0.2) -> Tuple[str, List[str], Dict[str, int]]:
        """
        Generate answer with citations from contexts (alias for answer method).
        
        Args:
            question: User's query
            contexts: Retrieved context chunks
            temperature: Sampling temperature (lower = more deterministic)
        
        Returns:
            Tuple of (answer, citations, token_usage)
        """
        return self.answer(question, contexts, temperature)

    def answer(self, question: str, contexts: List[str], temperature: float = 0.2) -> Tuple[str, List[str], Dict[str, int]]:
        """
        Generate answer with citations from contexts.
        
        Args:
            question: User's query
            contexts: Retrieved context chunks
            temperature: Sampling temperature (lower = more deterministic)
        
        Returns:
            Tuple of (answer, citations, token_usage)
        """
        # Apply prompt compression if contexts are too long
        compressed_contexts = self.compress_context(contexts, question, max_tokens=self.max_tokens // 2)
        
        prompt = self._build_prompt(question, compressed_contexts)
        
        try:
            # Generate with Gemini
            response = self.gen.generate_content(
                prompt,
                generation_config={
                    "temperature": temperature,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": self.max_tokens,
                }
            )
            
            answer = response.text
            
            # Extract real token usage from Gemini response metadata
            token_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
            
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                token_usage = {
                    "prompt_tokens": response.usage_metadata.prompt_token_count,
                    "completion_tokens": response.usage_metadata.candidates_token_count,
                    "total_tokens": response.usage_metadata.total_token_count
                }
            
            # Extract citations (top 3 most relevant contexts)
            citations = self._extract_citations(answer, contexts)
            
            return answer, citations, token_usage
            
        except Exception as e:
            error_msg = f"Error generating answer: {str(e)}"
            print(error_msg)
            return error_msg, [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _build_prompt(self, question: str, contexts: List[str]) -> str:
        """
        Build grounded prompt with system instructions and contexts.
        """
        ctx = "\n---\n".join([f"[{i+1}] {c}" for i, c in enumerate(contexts)])
        
        system = """You are a helpful AI assistant specializing in question-answering based on provided documents.

CRITICAL INSTRUCTIONS:
1. Answer ONLY based on the provided context below
2. You must never output personal data (emails, phone numbers, credit card numbers, names, addresses, account numbers, or any sensitive identifiers) even if present in retrieved documents. If a user asks for such information, decline and explain that the data is protected.
3. If the user requests any personal or sensitive information, refuse and provide a privacy-safe alternative.
4. If the answer is not in the context, say "I don't have enough information to answer this question based on the provided documents."
5. Include specific citations by referencing context numbers [1], [2], etc.
6. Be concise but complete
7. Do not hallucinate or make up information
8. If multiple contexts provide relevant information, synthesize them coherently
"""
        
        return f"""{system}

Context Documents:
{ctx}

Question: {question}

Answer (with citations):"""

    def compress_context(
        self,
        contexts: List[str],
        query: str,
        max_tokens: int = 4000,
        compression_ratio: float = 0.6
    ) -> List[str]:
        """
        Compress long contexts to fit within token limits using semantic ranking and summarization.
        
        Args:
            contexts: List of context chunks
            query: User's query for relevance scoring
            max_tokens: Maximum tokens for compressed context
            compression_ratio: Target compression ratio (0.6 = 60% of original)
        
        Returns:
            Compressed list of contexts
        """
        if not contexts:
            return []
        
        try:
            # Estimate tokens (rough: 1 token ≈ 4 chars)
            total_chars = sum(len(ctx) for ctx in contexts)
            estimated_tokens = total_chars // 4
            
            logger.info(
                f"Context compression: {estimated_tokens} tokens → target {max_tokens} tokens"
            )
            
            # If already under limit, return as-is
            if estimated_tokens <= max_tokens:
                return contexts
            
            # Step 1: Rank contexts by relevance to query
            query_emb = self._embed(query)
            scored_contexts = []
            
            for ctx in contexts:
                ctx_emb = self._embed(ctx)
                # Cosine similarity
                similarity = np.dot(query_emb, ctx_emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(ctx_emb)
                )
                scored_contexts.append((similarity, ctx))
            
            # Sort by relevance (highest first)
            scored_contexts.sort(reverse=True, key=lambda x: x[0])
            
            # Step 2: Select top contexts until we hit token limit
            compressed = []
            char_budget = max_tokens * 4  # Convert tokens to chars
            current_chars = 0
            
            for score, ctx in scored_contexts:
                ctx_len = len(ctx)
                if current_chars + ctx_len <= char_budget:
                    compressed.append(ctx)
                    current_chars += ctx_len
                else:
                    # Try to fit a truncated version
                    remaining = char_budget - current_chars
                    if remaining > 200:  # Only if we have reasonable space
                        truncated = ctx[:remaining - 3] + "..."
                        if current_chars + len(truncated) <= char_budget:
                            compressed.append(truncated)
                            current_chars += len(truncated)
                    break
            
            logger.info(
                f"Compressed {len(contexts)} contexts to {len(compressed)} contexts "
                f"({current_chars // 4} tokens)"
            )
            
            return compressed
            
        except Exception as e:
            logger.error(f"Context compression failed: {e}")
            # Fallback: return truncated original contexts
            char_budget = max_tokens * 4
            total = 0
            result = []
            for ctx in contexts:
                if total + len(ctx) <= char_budget:
                    result.append(ctx)
                    total += len(ctx)
                else:
                    break
            return result

    def _extract_citations(self, answer: str, contexts: List[str]) -> List[str]:
        """
        Extract most relevant contexts as citations.
        Returns top 3 contexts that are semantically similar to the answer.
        """
        if not contexts:
            return []
        
        try:
            answer_emb = self._embed(answer)
            
            # Score each context by similarity to answer
            scores = []
            for i, ctx in enumerate(contexts):
                ctx_emb = self._embed(ctx)
                # Cosine similarity
                similarity = np.dot(answer_emb, ctx_emb) / (
                    np.linalg.norm(answer_emb) * np.linalg.norm(ctx_emb)
                )
                scores.append((similarity, i, ctx))
            
            # Sort by similarity and return top 3
            scores.sort(reverse=True)
            return [ctx for _, _, ctx in scores[:3]]
            
        except Exception:
            # Fallback: return first 3 contexts
            return contexts[:min(3, len(contexts))]
