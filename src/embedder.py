#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Embedding Module
Handles local embedding generation using Ollama for semantic search
"""

import logging
from typing import List, Optional, Dict, Any
import hashlib
import json
from pathlib import Path

logger = logging.getLogger('TMR-Embedder')


# Module-level constants
DEFAULT_OLLAMA_TIMEOUT = 15  # Seconds for health check (configurable via env)


class OllamaEmbedder:
    """
    Generates embeddings using local Ollama instance.
    Falls back to keyword-based search if Ollama is unavailable.
    Automatically chunks large texts to fit model context window.
    """
    
    DEFAULT_MODEL = "nomic-embed-text"
    DEFAULT_HOST = "http://192.168.1.100:11434"  # Your Ollama instance
    DEFAULT_TIMEOUT = 15  # Seconds for health check
    VECTOR_SIZE = 768  # nomic-embed-text produces 768-dim vectors
    
    # nomic-embed-text context window (use 70% for safety)
    # nomic-embed-text has 2048 token context, we use 70% = ~1400 tokens
    MAX_TOKENS = 1400  # ~5600 characters at 4 chars/token
    CHUNK_OVERLAP = 100  # Character overlap between chunks
    
    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST):
        self.model = model
        self.host = host.rstrip('/')
        self._available = None  # Cache availability check
        
    def _check_ollama_available(self) -> bool:
        """Check if Ollama is available"""
        if self._available is not None:
            return self._available
            
        try:
            import urllib.request
            import urllib.error
            import os
            
            # Allow timeout override via environment variable
            timeout = int(os.getenv('OLLAMA_HEALTH_TIMEOUT', DEFAULT_OLLAMA_TIMEOUT))
            
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                self._available = response.status == 200
                return self._available
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            self._available = False
            return False
    
    def embed(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Vector of floats or None if embedding failed
        """
        if not self._check_ollama_available():
            return None
            
        try:
            import urllib.request
            import urllib.error
            
            data = json.dumps({
                "model": self.model,
                "prompt": text
            }).encode('utf-8')
            
            req = urllib.request.Request(
                f"{self.host}/api/embeddings",
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                embedding = result.get('embedding')
                
                if embedding and len(embedding) == self.VECTOR_SIZE:
                    return embedding
                else:
                    logger.warning(f"Invalid embedding size: {len(embedding) if embedding else 'None'}")
                    return None
                    
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None
    
    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embeddings (None for failed embeddings)
        """
        results = []
        for text in texts:
            results.append(self.embed(text))
        return results
    
    def embed_relation(self, subject: str, relation: str, obj: str, 
                       evidence: str = "") -> Optional[List[float]]:
        """
        Create a rich embedding text from relation components and embed it.
        
        Args:
            subject: Subject entity
            relation: Relation type
            obj: Object entity
            evidence: Supporting evidence text
            
        Returns:
            Embedding vector or None
        """
        # Create a rich text representation of the relation
        # This helps with semantic search by including context
        parts = [f"{subject} {relation} {obj}"]
        
        if evidence:
            parts.append(f"Evidence: {evidence}")
        
        # Also include a natural language form
        parts.append(f"{subject} has a {relation.lower()} relationship with {obj}")
        
        text = " | ".join(parts)
        return self.embed(text)
    
    def is_available(self) -> bool:
        """Check if the embedder is available"""
        return self._check_ollama_available()
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars)"""
        return len(text) // 4
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks that fit within token limit.
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        # If text fits in one chunk, return as-is
        if self._estimate_tokens(text) <= self.MAX_TOKENS:
            return [text]
        
        # Calculate chunk size in characters
        chunk_size = self.MAX_TOKENS * 4  # chars per chunk
        
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            # Find chunk boundary (try to break at space)
            end = min(start + chunk_size, text_len)
            
            # Try to find a good break point (space or newline)
            if end < text_len:
                # Look for space or newline within last 50 chars
                search_start = max(start, end - 50)
                for i in range(end - 1, search_start, -1):
                    if text[i] in ' \n':
                        end = i
                        break
            
            chunks.append(text[start:end])
            
            # Move start with overlap
            start = end - self.CHUNK_OVERLAP
            if start < 0:
                start = 0
        
        return chunks
    
    def embed_with_chunking(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding with automatic chunking for large texts.
        Averages embeddings from all chunks.
        
        Args:
            text: Text to embed (may be chunked)
            
        Returns:
            Vector of floats or None if embedding failed
        """
        if not self._check_ollama_available():
            return None
        
        # Check if text needs chunking
        if self._estimate_tokens(text) <= self.MAX_TOKENS:
            return self.embed(text)
        
        # Chunk and embed each part
        chunks = self._chunk_text(text)
        logger.info(f"Text too large ({len(text)} chars), splitting into {len(chunks)} chunks")
        
        embeddings = []
        for i, chunk in enumerate(chunks):
            chunk_embedding = self.embed(chunk)
            if chunk_embedding:
                embeddings.append(chunk_embedding)
        
        if not embeddings:
            return None
        
        # Average embeddings from all chunks
        # Simple mean pooling
        avg_embedding = []
        for i in range(self.VECTOR_SIZE):
            avg = sum(emb[i] for emb in embeddings) / len(embeddings)
            avg_embedding.append(avg)
        
        return avg_embedding


class KeywordFallbackEmbedder:
    """
    Fallback embedder that uses keyword hashing.
    Provides deterministic "embeddings" for keyword matching when Ollama is down.
    """
    
    VECTOR_SIZE = 768  # Same size as Ollama for compatibility
    
    def __init__(self):
        self.common_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can',
            'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for',
            'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'between',
            'and', 'but', 'or', 'yet', 'so', 'if', 'because', 'although',
            'though', 'while', 'where', 'when', 'that', 'which', 'who',
            'whom', 'whose', 'what', 'this', 'these', 'those', 'i', 'you',
            'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us',
            'them', 'my', 'your', 'his', 'its', 'our', 'their'
        }
    
    def _text_to_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text"""
        import re
        
        # Lowercase and extract words
        words = re.findall(r'\b[a-z]+\b', text.lower())
        
        # Filter out common words
        keywords = [w for w in words if w not in self.common_words and len(w) > 2]
        
        return keywords
    
    def _keyword_hash_vector(self, keywords: List[str]) -> List[float]:
        """Create a sparse vector from keywords using multiple hash functions"""
        vector = [0.0] * self.VECTOR_SIZE
        
        for keyword in keywords:
            # Use multiple hash positions for each keyword
            for i in range(3):  # 3 hash positions per keyword
                hash_input = f"{keyword}:{i}".encode('utf-8')
                # Use SHA256 instead of MD5 to avoid collision risks
                hash_val = int(hashlib.sha256(hash_input).hexdigest(), 16)
                pos = hash_val % self.VECTOR_SIZE
                vector[pos] += 1.0
        
        # Normalize
        total = sum(v ** 2 for v in vector) ** 0.5
        if total > 0:
            vector = [v / total for v in vector]
        
        return vector
    
    def embed(self, text: str) -> List[float]:
        """Generate keyword-based embedding"""
        keywords = self._text_to_keywords(text)
        return self._keyword_hash_vector(keywords)
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate keyword-based embeddings for multiple texts"""
        return [self.embed(text) for text in texts]
    
    def embed_relation(self, subject: str, relation: str, obj: str,
                       evidence: str = "") -> List[float]:
        """Embed a relation using keywords"""
        text = f"{subject} {relation} {obj} {evidence}"
        return self.embed(text)
    
    def is_available(self) -> bool:
        """Always available"""
        return True


class TMRRelationEmbedder:
    """
    Main embedder class that combines Ollama with keyword fallback.
    Provides semantic search capabilities with graceful degradation.
    """
    
    VECTOR_SIZE = 768
    
    def __init__(self, model: str = "nomic-embed-text", 
                 host: str = "http://192.168.1.100:11434"):
        self.ollama = OllamaEmbedder(model=model, host=host)
        self.fallback = KeywordFallbackEmbedder()
        self._use_fallback = False
        
    def embed(self, text: str) -> List[float]:
        """
        Embed text using best available method.
        Tries Ollama first with automatic chunking for large texts.
        Falls back to keyword hashing if Ollama unavailable.
        """
        if not self._use_fallback:
            # Use chunked embedding for large texts
            if self.ollama._estimate_tokens(text) > self.ollama.MAX_TOKENS:
                result = self.ollama.embed_with_chunking(text)
            else:
                result = self.ollama.embed(text)
            
            if result is not None:
                return result
            # Ollama failed, switch to fallback
            logger.warning("Switching to keyword fallback embedder")
            self._use_fallback = True
        
        return self.fallback.embed(text)
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts"""
        if not self._use_fallback:
            results = self.ollama.embed_batch(texts)
            if all(r is not None for r in results):
                return results
            logger.warning("Switching to keyword fallback embedder")
            self._use_fallback = True
        
        return self.fallback.embed_batch(texts)
    
    def embed_relation(self, subject: str, relation: str, obj: str,
                       evidence: str = "") -> List[float]:
        """Embed a knowledge graph relation with automatic chunking for large texts"""
        if not self._use_fallback:
            # Create relation text
            parts = [f"{subject} {relation} {obj}"]
            if evidence:
                parts.append(f"Evidence: {evidence}")
            parts.append(f"{subject} has a {relation.lower()} relationship with {obj}")
            text = " | ".join(parts)
            
            # Check if text needs chunking
            if self.ollama._estimate_tokens(text) > self.ollama.MAX_TOKENS:
                # Use chunked embedding for large texts
                result = self.ollama.embed_with_chunking(text)
            else:
                # Use regular embedding for small texts
                result = self.ollama.embed(text)
            
            if result is not None:
                return result
            logger.warning("Switching to keyword fallback embedder")
            self._use_fallback = True
        
        return self.fallback.embed_relation(subject, relation, obj, evidence)
    
    def is_semantic_available(self) -> bool:
        """Check if semantic (Ollama) embeddings are available"""
        return self.ollama.is_available() and not self._use_fallback
    
    def reset_fallback(self):
        """Reset fallback state (retry Ollama)"""
        self._use_fallback = False
        self.ollama._available = None


def test_embedder():
    """Test the embedder functionality"""
    print("="*60)
    print("TESTING: TMR Relation Embedder")
    print("="*60)
    
    # Test 1: Ollama availability
    print("\nTest 1: Checking Ollama availability...")
    embedder = TMRRelationEmbedder()
    
    is_available = embedder.ollama.is_available()
    print(f"  {'✅' if is_available else '⚠️'} Ollama available: {is_available}")
    
    # Test 2: Simple embedding
    print("\nTest 2: Generating simple embedding...")
    text = "User likes Marcello's restaurant and enjoys carbonara"
    vector = embedder.embed(text)
    
    if vector and len(vector) == 768:
        print(f"  ✅ Generated {len(vector)}-dim embedding")
        print(f"  Sample values: {vector[:5]}")
    else:
        print(f"  ❌ Failed: vector size = {len(vector) if vector else 'None'}")
        return False
    
    # Test 3: Relation embedding
    print("\nTest 3: Embedding a knowledge graph relation...")
    rel_vector = embedder.embed_relation(
        subject="User",
        relation="LIKES",
        obj="Marcello's",
        evidence="the carbonara was so good"
    )
    
    if rel_vector and len(rel_vector) == 768:
        print(f"  ✅ Generated relation embedding")
        print(f"  Sample values: {rel_vector[:5]}")
    else:
        print(f"  ❌ Failed")
        return False
    
    # Test 4: Batch embedding
    print("\nTest 4: Batch embedding...")
    texts = [
        "User dislikes spicy food",
        "User discussed memory systems",
        "Liz recommended a restaurant"
    ]
    batch_vectors = embedder.embed_batch(texts)
    
    if len(batch_vectors) == 3 and all(len(v) == 768 for v in batch_vectors):
        print(f"  ✅ Generated {len(batch_vectors)} embeddings")
    else:
        print(f"  ❌ Failed")
        return False
    
    # Test 5: Fallback behavior
    print("\nTest 5: Testing keyword fallback...")
    fallback = KeywordFallbackEmbedder()
    
    fb_vector = fallback.embed("User likes Italian food")
    if fb_vector and len(fb_vector) == 768:
        print(f"  ✅ Fallback generates valid embeddings")
        # Verify deterministic
        fb_vector2 = fallback.embed("User likes Italian food")
        if fb_vector == fb_vector2:
            print(f"  ✅ Fallback is deterministic")
        else:
            print(f"  ❌ Fallback not deterministic")
    else:
        print(f"  ❌ Fallback failed")
        return False
    
    # Test 6: Semantic status
    print("\nTest 6: Checking semantic status...")
    status = embedder.is_semantic_available()
    print(f"  Semantic search available: {status}")
    
    print("\n" + "="*60)
    print("RESULTS: All embedder tests passed ✅")
    print("="*60)
    
    return True


if __name__ == "__main__":
    success = test_embedder()
    exit(0 if success else 1)
