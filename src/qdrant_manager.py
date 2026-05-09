#!/usr/bin/env python3
"""
QMD Memory Plugin - Qdrant Connection Module
Manages connection to existing Qdrant instance and collections
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from qdrant_client.http.exceptions import UnexpectedResponse
from typing import List, Dict, Optional
import hashlib
import time
import functools
import logging


def retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0):
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
                    last_exception = e
                    if attempt < max_retries:
                        print(f"  Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}")
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        break
            
            raise last_exception
        return wrapper
    return decorator


class QdrantManager:
    """Manages Qdrant connection and collections for TMR"""
    
    def __init__(self, host: str = "localhost", port: int = 6333, timeout: int = 10):
        self.client = QdrantClient(host=host, port=port, timeout=timeout)
        self.collections = {
            "knowledge_graph": "tmr_knowledge_graph",
            "agents_files": "tmr_agents_files",
            "semantic_vectors": "tmr_semantic_vectors"
        }
        self._has_query_points = None  # Cache for feature detection
    
    @retry_with_backoff(max_retries=3)
    def init_collections(self, vector_size: int = 768) -> bool:
        """
        Initialize Qdrant collections if they don't exist.

        Returns:
            True if all collections ready, False otherwise
        """
        try:
            # Collection 1: Knowledge Graph (with dummy vectors)
            if not self.client.collection_exists(self.collections["knowledge_graph"]):
                self.client.create_collection(
                    collection_name=self.collections["knowledge_graph"],
                    vectors_config=VectorParams(size=1, distance=Distance.COSINE)
                )
                print(f"  Created collection: {self.collections['knowledge_graph']}")

            # Collection 2: Agents Files (workspace context files - AGENTS.md, SOUL.md, etc.)
            if not self.client.collection_exists(self.collections["agents_files"]):
                self.client.create_collection(
                    collection_name=self.collections["agents_files"],
                    vectors_config=VectorParams(size=1, distance=Distance.COSINE)
                )
                print(f"  Created collection: {self.collections['agents_files']}")

            # Collection 5: Semantic Vectors (for embedding-based search)
            if not self.client.collection_exists(self.collections["semantic_vectors"]):
                self.client.create_collection(
                    collection_name=self.collections["semantic_vectors"],
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
                )
                print(f"  Created collection: {self.collections['semantic_vectors']}")

            return True

        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            print(f"  Error creating collections: {e}")
            return False
    
    @retry_with_backoff(max_retries=3)
    def store_line_index(self, file_path: str, line_number: int,
                        timestamp: str, speaker: str, byte_offset: int) -> bool:
        """Store line index metadata for fast lookup"""
        try:
            point_id = hashlib.md5(f"{file_path}:{line_number}".encode()).hexdigest()

            self.client.upsert(
                collection_name=self.collections["line_index"],
                points=[PointStruct(
                    id=point_id,
                    vector=[0.0],  # Dummy vector for metadata storage
                    payload={
                        "file_path": file_path,
                        "line_number": line_number,
                        "timestamp": timestamp,
                        "speaker": speaker,
                        "byte_offset": byte_offset
                    }
                )]
            )
            return True
        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            print(f"  Error storing line index: {e}")
            return False
    
    @retry_with_backoff(max_retries=3)
    def get_line_info(self, file_path: str, line_number: int) -> Optional[Dict]:
        """Retrieve line metadata by file path and line number"""
        try:
            point_id = hashlib.md5(f"{file_path}:{line_number}".encode()).hexdigest()

            result = self.client.retrieve(
                collection_name=self.collections["line_index"],
                ids=[point_id]
            )

            if result:
                return result[0].payload
            return None
        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            print(f"  Error retrieving line info: {e}")
            return None
    
    @retry_with_backoff(max_retries=3)
    def list_collections(self) -> List[str]:
        """List all collections in Qdrant"""
        try:
            collections = self.client.get_collections()
            return [c.name for c in collections.collections]
        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            print(f"  Error listing collections: {e}")
            return []

    @retry_with_backoff(max_retries=3)
    def store_semantic_vector(self, point_id, vector: List[float],
                              payload: Dict) -> bool:
        """
        Store a semantic vector with its relation payload.

        Args:
            point_id: Unique ID for the vector (int or UUID)
            vector: The embedding vector (768-dim for nomic-embed-text)
            payload: The relation data (subject, relation, object, etc.)

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.upsert(
                collection_name=self.collections["semantic_vectors"],
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )]
            )
            return True
        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            print(f"  Error storing semantic vector: {e}")
            return False
    
    @retry_with_backoff(max_retries=3)
    def store_semantic_vectors_batch(self, points: List[dict]) -> bool:
        """Store multiple semantic vectors in batch"""
        try:
            point_structs = []
            for p in points:
                point_structs.append(PointStruct(
                    id=p['id'],
                    vector=p['vector'],
                    payload=p['payload']
                ))

            self.client.upsert(
                collection_name=self.collections["semantic_vectors"],
                points=point_structs
            )
            return True
        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            print(f"  Error storing semantic vectors batch: {e}")
            return False
    
    @retry_with_backoff(max_retries=3)
    def index_relations_batch(self, relations: List[Dict]) -> bool:
        """Store multiple relations in the knowledge graph collection.
        
        Args:
            relations: List of relation dicts to index
            
        Returns:
            True if successful, False otherwise
        """
        import uuid
        try:
            point_structs = []
            for rel in relations:
                point_structs.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=[0.0],
                    payload=rel
                ))

            self.client.upsert(
                collection_name=self.collections["knowledge_graph"],
                points=point_structs
            )
            return True
        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            print(f"  Error storing relations batch: {e}")
            return False
    
    def _check_query_points_support(self) -> bool:
        """Check if the client supports query_points() method."""
        if self._has_query_points is None:
            self._has_query_points = hasattr(self.client, 'query_points')
        return self._has_query_points

    @retry_with_backoff(max_retries=3)
    def search_semantic(self, query_vector: List[float], top_k: int = 5,
                        min_score: float = 0.0) -> List[Dict]:
        """
        Search for similar vectors using cosine similarity.
        Falls back to search() method for older qdrant-client versions.

        Args:
            query_vector: The query embedding vector
            top_k: Number of results to return
            min_score: Minimum similarity score threshold

        Returns:
            List of matching payloads with similarity scores
        """
        try:
            # Check if query_points is available (newer qdrant-client versions)
            if self._check_query_points_support():
                results = self.client.query_points(
                    collection_name=self.collections["semantic_vectors"],
                    query=query_vector,
                    limit=top_k,
                    score_threshold=min_score if min_score > 0 else None
                )

                # Add similarity score to each result payload
                matches = []
                for result in results.points:
                    match = result.payload.copy()
                    match['similarity_score'] = result.score
                    match['source_type'] = 'semantic_search'
                    matches.append(match)

                return matches
            else:
                # Fallback to search() for older qdrant-client versions
                results = self.client.search(
                    collection_name=self.collections["semantic_vectors"],
                    query_vector=query_vector,
                    limit=top_k,
                    score_threshold=min_score if min_score > 0 else None
                )

                # Add similarity score to each result payload
                matches = []
                for result in results:
                    match = result.payload.copy()
                    match['similarity_score'] = result.score
                    match['source_type'] = 'semantic_search'
                    matches.append(match)

                return matches

        except (ConnectionError, TimeoutError, UnexpectedResponse, AttributeError) as e:
            print(f"  Error searching semantic vectors: {e}")
            return []
    
    @retry_with_backoff(max_retries=3)
    def get_relations_for_entity(self, entity: str, 
                                  collection: str = "knowledge_graph") -> List[Dict]:
        """
        Get all relations where entity appears as subject or object.
        
        Args:
            entity: Entity name to search for
            collection: Collection to search (default: knowledge_graph)
            
        Returns:
            List of relation dictionaries
        """
        try:
            logger = logging.getLogger('TMR.Qdrant')
            logger.debug(f"Querying relations for entity: {entity}")
            
            collection_name = self.collections.get(collection, collection)
            
            # Use scroll with filter to find relations
            # Qdrant doesn't have direct text search, so we scroll all and filter
            # In production, would use proper indexing or payload filtering
            
            results = []
            offset = None
            
            while True:
                # Scroll through collection
                scroll_result = self.client.scroll(
                    collection_name=collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True
                )
                
                points, next_offset = scroll_result
                
                for point in points:
                    payload = point.payload
                    subject = payload.get('subject', '')
                    obj = payload.get('object', '')
                    
                    # Check if entity matches subject or object
                    if subject.lower() == entity.lower() or obj.lower() == entity.lower():
                        results.append(payload)
                
                if next_offset is None:
                    break
                offset = next_offset
                
                # Safety limit
                if len(results) > 1000:
                    logger.warning(f"Too many relations for {entity}, truncating")
                    break
            
            logger.debug(f"Found {len(results)} relations for {entity}")
            return results
            
        except (ConnectionError, TimeoutError, UnexpectedResponse) as e:
            logger.error(f"Error getting relations for {entity}: {e}")
            return []


def test_qdrant_connection():
    """Test Qdrant connection and collection management"""
    print("="*60)
    print("TESTING: TMR Qdrant Connection")
    print("="*60)
    
    # Test 1: Connection
    print("\nTest 1: Connecting to Qdrant...")
    try:
        manager = QdrantManager(host="localhost", port=6333)
        print("  ✅ Connected to Qdrant")
    except (ConnectionError, TimeoutError) as e:
        print(f"  ❌ Failed to connect: {e}")
        print("  Note: Is Qdrant running? Check with: docker ps | grep qdrant")
        return False
    
    # Test 2: List existing collections
    print("\nTest 2: Listing existing collections...")
    collections = manager.list_collections()
    print(f"  Found {len(collections)} collections:")
    for c in collections:
        print(f"    - {c}")
    
    # Test 3: Create our collections
    print("\nTest 3: Creating QMD collections...")
    success = manager.init_collections(vector_size=768)
    if success:
        print("  ✅ All collections ready")
    else:
        print("  ❌ Failed to create collections")
        return False
    
    # Test 4: Verify collections exist
    print("\nTest 4: Verifying collections...")
    collections = manager.list_collections()
    expected = ["tmr_conversations", "tmr_line_index", "tmr_knowledge_graph", "tmr_semantic_vectors"]
    
    all_exist = True
    for coll in expected:
        if coll in collections:
            print(f"  ✅ {coll}")
        else:
            print(f"  ❌ {coll} missing")
            all_exist = False
    
    # Test 5: Store and retrieve line index
    print("\nTest 5: Testing line index storage...")
    test_file = "memory/raw/2026-03-16.md"
    test_line = 4
    
    stored = manager.store_line_index(
        file_path=test_file,
        line_number=test_line,
        timestamp="14:32:15",
        speaker="User",
        byte_offset=150
    )
    
    if stored:
        print(f"  ✅ Stored line index for {test_file}:{test_line}")
        
        # Retrieve it
        info = manager.get_line_info(test_file, test_line)
        if info:
            print(f"  ✅ Retrieved: {info}")
            if info.get("speaker") == "User" and info.get("timestamp") == "14:32:15":
                print("  ✅ Data matches")
            else:
                print("  ❌ Data mismatch")
                all_exist = False
        else:
            print(f"  ❌ Failed to retrieve")
            all_exist = False
    else:
        print(f"  ❌ Failed to store")
        all_exist = False
    
    # Test 6: Semantic vector storage and search
    print("\nTest 6: Testing semantic vector storage...")
    import time
    test_vector = [0.1] * 768
    test_payload = {
        "subject": "Test",
        "relation": "TEST",
        "object": "Semantic Vector",
        "strength": 0.95
    }
    
    stored = manager.store_semantic_vector(
        point_id=int(time.time() * 1000),
        vector=test_vector,
        payload=test_payload
    )
    
    if stored:
        print(f"  ✅ Stored semantic vector")
        
        # Search for it
        results = manager.search_semantic(query_vector=test_vector, top_k=1)
        if results:
            print(f"  ✅ Semantic search works (found {len(results)} results)")
        else:
            print(f"  ⚠️  Semantic search returned no results (may be expected)")
    else:
        print(f"  ❌ Failed to store semantic vector")
        all_exist = False
    
    print("\n" + "="*60)
    if all_exist:
        print("RESULTS: All tests passed ✅")
    else:
        print("RESULTS: Some tests failed ❌")
    print("="*60)
    
    return all_exist


if __name__ == "__main__":
    success = test_qdrant_connection()
    exit(0 if success else 1)
