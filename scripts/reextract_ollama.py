#!/usr/bin/env python3
"""
TMR Full Re-extraction Script - Using Local Ollama
Re-extracts all knowledge graphs using local Ollama qwen2.5:3b model
"""

import sys
import os
import json
import hashlib
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Add TMR to path
sys.path.insert(0, str(Path.home() / ".openclaw" / "extensions" / "TrueMemoryRecall" / "src"))

from embedder import TMRRelationEmbedder
from qdrant_manager import QdrantManager

class OllamaExtractor:
    """Extract knowledge graphs using local Ollama"""
    
    def __init__(self, host: str = "http://192.168.1.100:11434", model: str = "qwen2.5:3b"):
        self.host = host.rstrip('/')
        self.model = model
        self.api_url = f"{self.host}/api/generate"
    
    def extract_graph(self, conversation: str, file_path: str) -> Optional[Dict]:
        """Extract knowledge graph using local Ollama"""
        
        prompt = f"""Extract a knowledge graph from this conversation.

Focus on:
- People (speakers, mentioned individuals)
- Places (restaurants, locations, venues)
- Foods (dishes, cuisines, ingredients)
- Concepts (technologies, ideas, projects)
- Preferences (likes, dislikes, avoidances)
- Decisions (commitments, plans, choices)
- Experiences (good/bad events, stories)

For each relationship, identify:
- strength: 0.0-1.0 (confidence level)
- evidence: exact quote from conversation
- line numbers: where this appears

Return ONLY JSON in this exact format:
{{
  "entities": ["entity1", "entity2", "entity3"],
  "relations": [
    {{
      "subject": "person",
      "relation": "LIKES|DISLIKES|WENT_TO|DISCUSSED|DECIDED|EXPERIENCED",
      "object": "entity",
      "strength": 0.95,
      "evidence": "exact quote",
      "line_start": 4,
      "line_end": 4,
      "text_snippet": "the conversation text from those lines"
    }}
  ]
}}

Conversation (with line numbers):
{conversation}

Source file: {file_path}

Respond with ONLY the JSON, no other text."""

        try:
            data = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0
                }
            }).encode('utf-8')
            
            req = urllib.request.Request(
                self.api_url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode('utf-8'))
                content = result.get('response', '')
                
                cost_info = {
                    "input_tokens": result.get('prompt_eval_count', 0),
                    "output_tokens": result.get('eval_count', 0),
                    "total_tokens": result.get('prompt_eval_count', 0) + result.get('eval_count', 0)
                }
                
                return self._parse_response(content, file_path, cost_info, conversation)
                
        except Exception as e:
            print(f"  Extraction error: {e}")
            return None
    
    def _extract_text_snippet(self, conversation: str, line_start: int, line_end: int) -> str:
        """Extract text snippet from conversation based on line numbers"""
        lines = conversation.split('\n')
        start_idx = max(0, line_start - 1)
        end_idx = min(len(lines), line_end)
        
        if start_idx >= len(lines) or start_idx >= end_idx:
            return ""
        
        snippet_lines = lines[start_idx:end_idx]
        return '\n'.join(snippet_lines).strip()
    
    def _parse_response(self, content: str, file_path: str, cost_info: Dict, conversation: str = None) -> Optional[Dict]:
        """Parse Ollama response into structured graph"""
        import re
        
        # Extract JSON block
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if code_block_match:
            content = code_block_match.group(1)
        
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return None
        
        try:
            data = json.loads(json_match.group())
            
            graph = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_file": file_path,
                "extraction_cost": cost_info,
                "extraction_model": self.model,
                "entities": data.get("entities", []),
                "relations": []
            }
            
            for rel in data.get("relations", []):
                line_start = rel.get("line_start", 0)
                line_end = rel.get("line_end", line_start)
                
                text_snippet = rel.get("text_snippet", "")
                if not text_snippet and conversation and line_start > 0:
                    text_snippet = self._extract_text_snippet(conversation, line_start, line_end)
                
                formatted_rel = {
                    "subject": rel.get("subject"),
                    "relation": rel.get("relation"),
                    "object": rel.get("object"),
                    "strength": rel.get("strength", 0.5),
                    "evidence": rel.get("evidence", ""),
                    "source": {
                        "file": file_path,
                        "line_start": line_start,
                        "line_end": line_end,
                        "text_snippet": text_snippet
                    }
                }
                graph["relations"].append(formatted_rel)
            
            return graph
            
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}")
            return None


def process_file(file_path: Path, extractor: OllamaExtractor, 
                 embedder: TMRRelationEmbedder, qdrant: QdrantManager,
                 graph_dir: Path, stats: Dict) -> bool:
    """Process a single conversation file"""
    print(f"\n{'='*60}")
    print(f"Processing: {file_path.name}")
    print('='*60)
    
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
    print(f"  Extracting with Ollama {extractor.model}...")
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
    date_str = file_path.stem
    graph_file = graph_dir / f"{date_str}.json"
    
    graph['extraction_timestamp'] = datetime.now().isoformat()
    graph['ollama_embeddings'] = True
    
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
            
            vector = embedder.embed_relation(subject, relation, obj, evidence)
            
            if vector and len(vector) == 768:
                rel_id = f"{date_str}_{i}"
                point_id = int(hashlib.md5(rel_id.encode()).hexdigest(), 16) % (2**63)
                
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
        
        if points:
            success = qdrant.store_semantic_vectors_batch(points)
            if success:
                print(f"  ✅ Stored {len(points)} vectors in Qdrant")
                stats['vectors_stored'] += len(points)
            else:
                print(f"  ❌ Failed to store vectors in Qdrant")
                stats['errors'].append(f"Qdrant store failed: {file_path.name}")
    
    cost = graph.get('extraction_cost', {})
    stats['total_tokens'] += cost.get('total_tokens', 0)
    
    return True


def main():
    """Main re-extraction process"""
    print("="*70)
    print("TMR FULL RE-EXTRACTION WITH OLLAMA (Local Model)")
    print("="*70)
    print(f"Started: {datetime.now().isoformat()}")
    print()
    
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
    
    print("Initializing components...")
    
    # Ollama embedder
    embedder = TMRRelationEmbedder(host="http://192.168.1.100:11434")
    if not embedder.ollama.is_available():
        print("❌ Ollama not available at http://192.168.1.100:11434")
        sys.exit(1)
    print("  ✅ Ollama embedder ready (nomic-embed-text)")
    
    # Ollama extractor
    extractor = OllamaExtractor(host="http://192.168.1.100:11434", model="qwen2.5:3b")
    print("  ✅ Ollama extractor ready (qwen2.5:3b)")
    
    # Qdrant
    qdrant = QdrantManager()
    qdrant.init_collections(vector_size=768)
    print("  ✅ Qdrant connected")
    
    # Directories
    raw_dir = Path.home() / ".openclaw" / "workspace" / "memory" / "raw"
    graph_dir = Path.home() / ".openclaw" / "workspace" / "memory" / "graph"
    
    graph_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nDirectories:")
    print(f"  Raw: {raw_dir}")
    print(f"  Graph: {graph_dir}")
    
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
    
    # Verification
    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70)
    
    print(f"\nOllama semantic available: {embedder.is_semantic_available()}")
    
    sample_vector = embedder.embed("test query for verification")
    if sample_vector and len(sample_vector) == 768:
        print(f"✅ Embedding dimensions: {len(sample_vector)} (expected: 768)")
    else:
        print(f"❌ Embedding dimensions: {len(sample_vector) if sample_vector else 'None'}")
    
    try:
        count_result = qdrant.client.count(collection_name="tmr_semantic_vectors")
        print(f"✅ Vectors in tmr_semantic_vectors: {count_result.count}")
    except Exception as e:
        print(f"❌ Failed to count vectors: {e}")
    
    # Check sample graph file
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
