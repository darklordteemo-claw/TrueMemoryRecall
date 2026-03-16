#!/usr/bin/env python3
"""
QMD Memory Plugin - Qdrant Connection Module
Manages connection to existing Qdrant instance and collections
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import List, Dict, Optional
import hashlib


class QdrantManager:
    """Manages Qdrant connection and collections for TMR"""
    
    def __init__(self, host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)
        self.collections = {
            "conversations": "tmr_conversations",
            "line_index": "tmr_line_index", 
            "knowledge_graph": "tmr_knowledge_graph"
        }
    
    def init_collections(self, vector_size: int = 768) -> bool:
        """
        Initialize Qdrant collections if they don't exist.
        
        Returns:
            True if all collections ready, False otherwise
        """
        try:
            # Collection 1: Conversations (with vectors)
            if not self.client.collection_exists(self.collections["conversations"]):
                self.client.create_collection(
                    collection_name=self.collections["conversations"],
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                print(f"  Created collection: {self.collections['conversations']}")
            
            # Collection 2: Line Index (with dummy vectors for metadata storage)
            if not self.client.collection_exists(self.collections["line_index"]):
                self.client.create_collection(
                    collection_name=self.collections["line_index"],
                    vectors_config=VectorParams(size=1, distance=Distance.COSINE)
                )
                print(f"  Created collection: {self.collections['line_index']}")
            
            # Collection 3: Knowledge Graph (with dummy vectors)
            if not self.client.collection_exists(self.collections["knowledge_graph"]):
                self.client.create_collection(
                    collection_name=self.collections["knowledge_graph"],
                    vectors_config=VectorParams(size=1, distance=Distance.COSINE)
                )
                print(f"  Created collection: {self.collections['knowledge_graph']}")
            
            return True
            
        except Exception as e:
            print(f"  Error creating collections: {e}")
            return False
    
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
        except Exception as e:
            print(f"  Error storing line index: {e}")
            return False
    
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
        except Exception as e:
            print(f"  Error retrieving line info: {e}")
            return None
    
    def list_collections(self) -> List[str]:
        """List all collections in Qdrant"""
        try:
            collections = self.client.get_collections()
            return [c.name for c in collections.collections]
        except Exception as e:
            print(f"  Error listing collections: {e}")
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
    except Exception as e:
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
    expected = ["qmd_conversations", "qmd_line_index", "qmd_knowledge_graph"]
    
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
            print("  ❌ Failed to retrieve")
            all_exist = False
    else:
        print("  ❌ Failed to store")
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
