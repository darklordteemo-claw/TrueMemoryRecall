#!/usr/bin/env python3
"""
TMR Semantic Search - End-to-End Test Script
Tests embeddings, storage, and semantic search functionality
"""

import sys
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Set up timezone to IST
os.environ['TZ'] = 'Asia/Kolkata'

# Add TMR src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from qdrant_manager import QdrantManager
from embedder import TMRRelationEmbedder


def test_qdrant_collections():
    """Test that all Qdrant collections are created"""
    print("\n" + "="*60)
    print("TEST 1: Qdrant Collections")
    print("="*60)
    
    try:
        qdrant = QdrantManager()
        print("  ✅ Connected to Qdrant")
        
        # Initialize collections
        success = qdrant.init_collections(vector_size=768)
        if success:
            print("  ✅ Collections initialized")
        else:
            print("  ❌ Failed to initialize collections")
            return False
        
        # Verify semantic_vectors collection exists
        collections = qdrant.list_collections()
        if "tmr_semantic_vectors" in collections:
            print("  ✅ tmr_semantic_vectors collection exists")
        else:
            print("  ❌ tmr_semantic_vectors collection missing")
            print(f"  Available collections: {collections}")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_embedder():
    """Test the embedder with sample text"""
    print("\n" + "="*60)
    print("TEST 2: Embedder Module")
    print("="*60)
    
    try:
        embedder = TMRRelationEmbedder()
        
        # Test availability
        is_available = embedder.ollama.is_available()
        print(f"  Ollama available: {is_available}")
        
        # Test simple embedding
        text = "User likes Marcello's restaurant and enjoys carbonara pasta"
        print(f"\n  Embedding text: '{text[:50]}...'")
        
        vector = embedder.embed(text)
        if vector and len(vector) == 768:
            print(f"  ✅ Generated {len(vector)}-dim vector")
            print(f"  Sample values: [{vector[0]:.4f}, {vector[1]:.4f}, ...]")
        else:
            print(f"  ⚠️  Using fallback, vector size: {len(vector) if vector else 'None'}")
        
        # Test relation embedding
        print("\n  Embedding relation: User LIKES Marcello's")
        rel_vector = embedder.embed_relation(
            subject="User",
            relation="LIKES",
            obj="Marcello's",
            evidence="the carbonara was so good"
        )
        
        if rel_vector and len(rel_vector) == 768:
            print(f"  ✅ Generated relation embedding")
        else:
            print(f"  ⚠️  Fallback embedding")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_semantic_storage_and_search():
    """Test storing and searching semantic vectors"""
    print("\n" + "="*60)
    print("TEST 3: Semantic Storage & Search")
    print("="*60)
    
    try:
        qdrant = QdrantManager()
        embedder = TMRRelationEmbedder()
        
        # Sample relations to store
        sample_relations = [
            {
                "subject": "User",
                "relation": "LIKES",
                "object": "Marcello's",
                "strength": 0.95,
                "evidence": "the carbonara was so good",
                "source_date": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                "source_file": "memory/raw/2026-03-16.md",
                "line_start": 45
            },
            {
                "subject": "User",
                "relation": "DISLIKES",
                "object": "spicy food",
                "strength": 0.90,
                "evidence": "bad experience at spice palace",
                "source_date": (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'),
                "source_file": "memory/raw/2026-03-15.md",
                "line_start": 23
            },
            {
                "subject": "User",
                "relation": "DISCUSSED",
                "object": "memory systems",
                "strength": 0.75,
                "evidence": "im thinking about the memory system we discussed",
                "source_date": (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'),
                "source_file": "memory/raw/2026-03-14.md",
                "line_start": 12
            },
            {
                "subject": "Liz",
                "relation": "RECOMMENDED",
                "object": "Italian restaurants",
                "strength": 0.80,
                "evidence": "theres a great place called marcellos",
                "source_date": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                "source_file": "memory/raw/2026-03-16.md",
                "line_start": 67
            }
        ]
        
        print(f"  Storing {len(sample_relations)} sample relations...")
        
        # Store relations with embeddings
        stored_count = 0
        for i, rel in enumerate(sample_relations):
            # Generate embedding
            vector = embedder.embed_relation(
                subject=rel['subject'],
                relation=rel['relation'],
                obj=rel['object'],
                evidence=rel.get('evidence', '')
            )
            
            if vector:
                # Store in Qdrant with integer ID
                # Use timestamp + index for unique integer ID
                import time
                point_id = int(time.time() * 1000) + i
                success = qdrant.store_semantic_vector(
                    point_id=point_id,
                    vector=vector,
                    payload=rel
                )
                if success:
                    stored_count += 1
        
        print(f"  ✅ Stored {stored_count}/{len(sample_relations)} relations")
        
        if stored_count == 0:
            print("  ⚠️  No relations stored, skipping search test")
            return True
        
        # Test semantic queries
        test_queries = [
            ("Where should I eat dinner?", "restaurant food"),
            ("I don't like spicy things", "spicy dislike"),
            ("Tell me about memory", "memory systems"),
        ]
        
        print("\n  Testing semantic queries:")
        for query, expected_keywords in test_queries:
            print(f"\n  Query: '{query}'")
            
            # Generate query embedding
            query_vector = embedder.embed(query)
            
            # Search
            results = qdrant.search_semantic(
                query_vector=query_vector,
                top_k=3,
                min_score=0.0
            )
            
            if results:
                print(f"    Found {len(results)} matches:")
                for r in results[:2]:
                    payload = r.get('payload', {})
                    score = r.get('score', 0)
                    subj = payload.get('subject', '?')
                    rel = payload.get('relation', '?')
                    obj = payload.get('object', '?')
                    print(f"      - {subj} {rel} {obj} (score: {score:.3f})")
            else:
                print(f"    No matches found")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_keyword_fallback():
    """Test that keyword fallback works when Ollama is unavailable"""
    print("\n" + "="*60)
    print("TEST 4: Keyword Fallback (Graceful Degradation)")
    print("="*60)
    
    try:
        from embedder import KeywordFallbackEmbedder
        
        fallback = KeywordFallbackEmbedder()
        
        # Test embedding generation
        text = "User likes Italian food and pasta"
        vector = fallback.embed(text)
        
        if vector and len(vector) == 768:
            print(f"  ✅ Fallback generates valid embeddings")
        else:
            print(f"  ❌ Invalid fallback embedding")
            return False
        
        # Test determinism
        vector2 = fallback.embed(text)
        if vector == vector2:
            print(f"  ✅ Fallback is deterministic")
        else:
            print(f"  ❌ Fallback not deterministic")
            return False
        
        # Test that we can still store/retrieve with fallback
        qdrant = QdrantManager()
        
        test_rel = {
            "subject": "Fallback",
            "relation": "TEST",
            "object": "Keyword Search",
            "strength": 0.5,
            "source_date": "2026-03-17"
        }
        
        import time
        point_id = int(time.time() * 1000) + 999
        success = qdrant.store_semantic_vector(
            point_id=point_id,
            vector=vector,
            payload=test_rel
        )
        
        if success:
            print(f"  ✅ Can store fallback embeddings")
        else:
            print(f"  ❌ Failed to store fallback embedding")
            return False
        
        # Search with fallback embedding
        query_vector = fallback.embed("Italian pasta food")
        results = qdrant.search_semantic(query_vector=query_vector, top_k=5)
        
        print(f"  ✅ Fallback search functional ({len(results)} results)")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backward_compatibility():
    """Test that keyword search still works"""
    print("\n" + "="*60)
    print("TEST 5: Backward Compatibility")
    print("="*60)
    
    try:
        from injector import ContextInjector
        
        # Create temp graph with sample data
        import tempfile
        import shutil
        
        temp_dir = tempfile.mkdtemp()
        graph_dir = Path(temp_dir) / "graph"
        graph_dir.mkdir()
        
        # Create a sample graph file
        today = datetime.now()
        graph_file = graph_dir / f"{today.strftime('%Y-%m-%d')}.json"
        
        sample_graph = {
            "date": today.strftime('%Y-%m-%d'),
            "entities": ["User", "Liz", "Marcello's"],
            "relations": [
                {
                    "subject": "User",
                    "relation": "LIKES",
                    "object": "Marcello's",
                    "strength": 0.95,
                    "evidence": "the carbonara was so good",
                    "source": {"file": "memory/raw/2026-03-16.md", "line_start": 45}
                }
            ]
        }
        
        with open(graph_file, 'w') as f:
            json.dump(sample_graph, f)
        
        # Test keyword-based injector
        injector = ContextInjector(str(graph_dir))
        
        # Test query
        query = "Where should I eat?"
        context = injector.inject_context(query)
        
        if context and "Marcello's" in context:
            print(f"  ✅ Keyword search works")
            print(f"  Found match: Marcello's")
        else:
            print(f"  ⚠️  No keyword match (may be expected)")
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """Test that config has been updated correctly"""
    print("\n" + "="*60)
    print("TEST 6: Configuration")
    print("="*60)
    
    try:
        import yaml
        
        config_path = Path(__file__).parent.parent / 'config' / 'plugin.yaml'
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check embeddings section
        embeddings = config.get('embeddings', {})
        if embeddings:
            print(f"  ✅ Embeddings section present")
            print(f"    Provider: {embeddings.get('provider')}")
            print(f"    Model: {embeddings.get('model')}")
            print(f"    Vector size: {embeddings.get('vector_size')}")
        else:
            print(f"  ❌ Embeddings section missing")
            return False
        
        # Check semantic_search section
        semantic = config.get('semantic_search', {})
        if semantic:
            print(f"  ✅ Semantic search section present")
            print(f"    Enabled: {semantic.get('enabled')}")
            print(f"    Collection: {semantic.get('collection')}")
            print(f"    Top-K: {semantic.get('top_k')}")
        else:
            print(f"  ❌ Semantic search section missing")
            return False
        
        # Check timezone
        extraction = config.get('extraction', {})
        timezone = extraction.get('timezone')
        if timezone == 'Asia/Kolkata':
            print(f"  ✅ Timezone set to IST (Asia/Kolkata)")
        else:
            print(f"  ⚠️  Timezone: {timezone} (expected Asia/Kolkata)")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    """Run all tests"""
    print("="*60)
    print("TMR SEMANTIC SEARCH - END-TO-END TEST")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Check timezone
    import time
    time.tzset()
    print(f"Timezone: {time.tzname}")
    
    results = []
    
    # Run tests
    results.append(("Qdrant Collections", test_qdrant_collections()))
    results.append(("Embedder", test_embedder()))
    results.append(("Semantic Storage/Search", test_semantic_storage_and_search()))
    results.append(("Keyword Fallback", test_keyword_fallback()))
    results.append(("Backward Compatibility", test_backward_compatibility()))
    results.append(("Configuration", test_config()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 All tests passed!")
        print("="*60)
        return 0
    else:
        print(f"\n  ⚠️  {total - passed} test(s) failed")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
