#!/usr/bin/env python3
"""
TMR Full Re-extraction Script
Re-extracts all knowledge graphs with proper Ollama semantic embeddings
"""

import sys
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Add TMR to path
sys.path.insert(0, str(Path.home() / ".openclaw" / "extensions" / "TrueMemoryRecall" / "src"))

from extractor import QwenExtractor
from embedder import TMRRelationEmbedder
from qdrant_manager import QdrantManager

def load_api_key() -> Optional[str]:
    """Load API key from config or environment"""
    config_path = Path.home() / ".openclaw" / "extensions" / "TrueMemoryRecall" / "config" / "plugin.yaml"
    api_key = None
    
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            api_key = config.get('extraction', {}).get('api_key')
            if api_key and api_key.startswith('${') and api_key.endswith('}'):
                env_var = api_key[2:-1]
                api_key = os.environ.get(env_var)
    except Exception:
        pass
    
    if not api_key:
        api_key = os.environ.get('OPENROUTER_API_KEY')
    
    return api_key

def get_line_from_conversation(conversation: str, line_num: int) -> str:
    """Extract a specific line from conversation"""
    lines = conversation.split('\n')
    if 1 <= line_num <= len(lines):
        return lines[line_num - 1]
    return ""

def process_file(file_path: Path, extractor: QwenExtractor, 
                 embedder: TMRRelationEmbedder, qdrant: QdrantManager,
                 graph_dir: Path, stats: Dict) -> bool:
    """Process a single conversation file"""
    print(f"\n{'='*60}")
    print(f"Processing: {file_path.name}")
    print('='*60)
    
    # Read conversation
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            conversation = f.read()
    except Exception as e:
        print(f"  ❌ Failed to read file: {e}")
        stats['errors'].append(f"Read error {file_path.name}: {e}")
        return False
    
    lines = conversation.split('\n')
    print(f"  Lines: {len(lines)}")
    
    if len(lines) < 3:
        print(f"  ⚠️  File too short, skipping")
        stats['skipped'] += 1
        return False
    
    # Extract knowledge graph
    print(f"  Extracting knowledge graph...")
    graph = extractor.extract_graph(conversation, str(file_path))
    
    if not graph:
        print(f"  ❌ Extraction failed")
        stats['errors'].append(f"Extraction failed: {file_path.name}")
        return False
    
    relations = graph.get('relations', [])
    entities = graph.get('entities', [])
    print(f"  ✅ Extracted: {len(entities)} entities, {len(relations)} relations")
    
    stats['total_entities'] += len(entities)
    stats['total_relations'] += len(relations)
    
    # Save graph to JSON file
    date_str = file_path.stem  # e.g., "2026-03-16"
    graph_file = graph_dir / f"{date_str}.json"
    
    # Add metadata
    graph['extraction_timestamp'] = datetime.now().isoformat()
    graph['ollama_embeddings'] = True  # Flag to indicate Ollama was used
    
    try:
        with open(graph_file, 'w', encoding='utf-8') as f:
            json.dump(graph, f, indent=2)
        print(f"  ✅ Saved graph: {graph_file.name}")
        stats['graph_files_created'] += 1
    except Exception as e:
        print(f"  ⚠️  Failed to save graph: {e}")
        stats['errors'].append(f"Save error {file_path.name}: {e}")
    
    # Generate embeddings and store in Qdrant
    if relations:
        print(f"  Generating Ollama embeddings...")
        
        points = []
        for i, rel in enumerate(relations):
            subject = rel.get('subject', '')
            relation = rel.get('relation', '')
            obj = rel.get('object', '')
            evidence = rel.get('evidence', '')
            source = rel.get('source', {})
            
            # Generate embedding
            vector = embedder.embed_relation(subject, relation, obj, evidence)
            
            if vector and len(vector) == 768:
                # Create unique ID
                rel_id = f"{date_str}_{i}"
                point_id = int(hashlib.md5(rel_id.encode()).hexdigest(), 16) % (2**63)
                
                # Build payload with full source info
                payload = {
                    'subject': subject,
                    'relation': relation,
                    'object': obj,
                    'strength': rel.get('strength', 0.5),
                    'evidence': evidence,
                    'source': source,
                    'source_file': str(file_path),
                    'extraction_date': date_str
                }
                
                points.append({
                    'id': point_id,
                    'vector': vector,
                    'payload': payload
                })
            else:
                print(f"    ⚠️  Failed to embed relation {i}: {subject} {relation} {obj}")
                stats['embedding_failures'] += 1
        
        # Store in Qdrant
        if points:
            success = qdrant.store_semantic_vectors_batch(points)
            if success:
                print(f"  ✅ Stored {len(points)} vectors in Qdrant")
                stats['vectors_stored'] += len(points)
            else:
                print(f"  ❌ Failed to store vectors in Qdrant")
                stats['errors'].append(f"Qdrant store failed: {file_path.name}")
        else:
            print(f"  ⚠️  No valid embeddings generated")
    
    # Track cost
    cost = graph.get('extraction_cost', {})
    stats['total_tokens'] += cost.get('total_tokens', 0)
    
    return True

def process_agents_files(extractor: QwenExtractor, embedder: TMRRelationEmbedder, 
                         qdrant: QdrantManager, agents_dir: Path, stats: Dict):
    """Process workspace context files (AGENTS.md, etc.)"""
    print(f"\n{'='*60}")
    print("Processing Workspace Context Files")
    print('='*60)
    
    workspace_dir = Path.home() / ".openclaw" / "workspace"
    context_files = ['AGENTS.md', 'SOUL.md', 'USER.md', 'TOOLS.md', 'MEMORY.md']
    
    for filename in context_files:
        file_path = workspace_dir / filename
        if not file_path.exists():
            continue
        
        print(f"\n  Processing: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"    ❌ Failed to read: {e}")
            continue
        
        # Extract graph from context file
        # Add line numbers to content for extraction
        lines = content.split('\n')
        numbered_content = '\n'.join([f"{i+1}. {line}" for i, line in enumerate(lines)])
        
        graph = extractor.extract_graph(numbered_content, str(file_path))
        
        if not graph:
            print(f"    ⚠️  No relations extracted from {filename}")
            continue
        
        relations = graph.get('relations', [])
        print(f"    ✅ Extracted {len(relations)} relations")
        stats['total_relations'] += len(relations)
        
        # Save to agents_files
        graph_file = agents_dir / f"{filename}.json"
        try:
            with open(graph_file, 'w', encoding='utf-8') as f:
                json.dump(graph, f, indent=2)
            print(f"    ✅ Saved: {graph_file.name}")
        except Exception as e:
            print(f"    ⚠️  Failed to save: {e}")
        
        # Store in Qdrant agents_files collection
        if relations:
            for i, rel in enumerate(relations):
                rel_id = f"agents_{filename}_{i}"
                
                try:
                    qdrant.client.upsert(
                        collection_name=qdrant.collections["agents_files"],
                        points=[{
                            'id': rel_id,
                            'vector': [0.0],  # Dummy vector for metadata
                            'payload': rel
                        }]
                    )
                except Exception as e:
                    print(f"    ⚠️  Failed to store in Qdrant: {e}")

def main():
    """Main re-extraction process"""
    print("="*70)
    print("TMR FULL RE-EXTRACTION WITH OLLAMA EMBEDDINGS")
    print("="*70)
    print(f"Started: {datetime.now().isoformat()}")
    print()
    
    # Stats tracking
    stats = {
        'files_processed': 0,
        'files_failed': 0,
        'skipped': 0,
        'total_entities': 0,
        'total_relations': 0,
        'vectors_stored': 0,
        'graph_files_created': 0,
        'embedding_failures': 0,
        'total_tokens': 0,
        'errors': []
    }
    
    # Initialize components
    print("Initializing components...")
    
    # API key
    api_key = load_api_key()
    if not api_key:
        print("❌ No API key found. Set OPENROUTER_API_KEY environment variable.")
        sys.exit(1)
    print("  ✅ API key loaded")
    
    # Ollama embedder
    embedder = TMRRelationEmbedder(host="http://192.168.1.100:11434")
    if not embedder.ollama.is_available():
        print("❌ Ollama not available at http://192.168.1.100:11434")
        sys.exit(1)
    print("  ✅ Ollama embedder ready")
    
    # Qdrant
    qdrant = QdrantManager()
    qdrant.init_collections(vector_size=768)
    print("  ✅ Qdrant connected")
    
    # Extractor
    extractor = QwenExtractor(api_key=api_key)
    print("  ✅ Qwen extractor ready")
    
    # Directories
    raw_dir = Path.home() / ".openclaw" / "workspace" / "memory" / "raw"
    graph_dir = Path.home() / ".openclaw" / "workspace" / "memory" / "graph"
    agents_dir = graph_dir / "agents_files"
    
    graph_dir.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nDirectories:")
    print(f"  Raw: {raw_dir}")
    print(f"  Graph: {graph_dir}")
    print(f"  Agents: {agents_dir}")
    
    # Find all raw conversation files
    raw_files = sorted(raw_dir.glob("*.md"))
    print(f"\nFound {len(raw_files)} raw conversation files")
    
    if not raw_files:
        print("⚠️  No conversation files found to process")
        return
    
    # Process each file
    for file_path in raw_files:
        success = process_file(file_path, extractor, embedder, qdrant, graph_dir, stats)
        if success:
            stats['files_processed'] += 1
        else:
            stats['files_failed'] += 1
    
    # Process agents files
    process_agents_files(extractor, embedder, qdrant, agents_dir, stats)
    
    # Final report
    print("\n" + "="*70)
    print("RE-EXTRACTION COMPLETE")
    print("="*70)
    print(f"\nStatistics:")
    print(f"  Files processed: {stats['files_processed']}")
    print(f"  Files failed: {stats['files_failed']}")
    print(f"  Files skipped (too short): {stats['skipped']}")
    print(f"  Total entities extracted: {stats['total_entities']}")
    print(f"  Total relations extracted: {stats['total_relations']}")
    print(f"  Vectors stored in Qdrant: {stats['vectors_stored']}")
    print(f"  Graph files created: {stats['graph_files_created']}")
    print(f"  Embedding failures: {stats['embedding_failures']}")
    print(f"  Total tokens used: {stats['total_tokens']}")
    
    if stats['errors']:
        print(f"\n  Errors ({len(stats['errors'])}):")
        for error in stats['errors'][:5]:
            print(f"    - {error}")
        if len(stats['errors']) > 5:
            print(f"    ... and {len(stats['errors']) - 5} more")
    
    # Verify embeddings
    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70)
    
    # Check Ollama was used
    print(f"\nOllama semantic available: {embedder.is_semantic_available()}")
    
    # Sample vector dimensions
    sample_vector = embedder.embed("test query for verification")
    if sample_vector and len(sample_vector) == 768:
        print(f"✅ Embedding dimensions: {len(sample_vector)} (expected: 768)")
    else:
        print(f"❌ Embedding dimensions: {len(sample_vector) if sample_vector else 'None'} (expected: 768)")
    
    # Count vectors in Qdrant
    try:
        count_result = qdrant.client.count(collection_name="tmr_semantic_vectors")
        print(f"✅ Vectors in tmr_semantic_vectors: {count_result.count}")
    except Exception as e:
        print(f"❌ Failed to count vectors: {e}")
    
    # Check sample graph file has source with line_end and text_snippet
    sample_graph_files = list(graph_dir.glob("*.json"))
    if sample_graph_files:
        try:
            with open(sample_graph_files[0], 'r') as f:
                sample_graph = json.load(f)
            
            relations = sample_graph.get('relations', [])
            if relations:
                first_rel = relations[0]
                source = first_rel.get('source', {})
                has_line_end = 'line_end' in source
                has_text_snippet = 'text_snippet' in source
                
                print(f"\n✅ Sample graph has line_end: {has_line_end}")
                print(f"✅ Sample graph has text_snippet: {has_text_snippet}")
                
                if has_line_end and has_text_snippet:
                    print(f"   line_start: {source.get('line_start')}")
                    print(f"   line_end: {source.get('line_end')}")
                    print(f"   text_snippet: {source.get('text_snippet', '')[:80]}...")
        except Exception as e:
            print(f"⚠️  Failed to verify sample graph: {e}")
    
    print(f"\nFinished: {datetime.now().isoformat()}")
    print("="*70)

if __name__ == "__main__":
    main()
