#!/usr/bin/env python3
"""
TMR Twice-Daily Extraction
Runs at 12:00 and 00:00 to extract knowledge graphs from raw conversations
"""

import sys
import os
import json
import pytz
from datetime import datetime, timedelta
from pathlib import Path

# Load environment variables from .env file manually (overrides existing)
def load_env_file():
    script_dir = Path(__file__).parent.parent
    env_path = script_dir / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Always use .env value (for cron compatibility)
                    os.environ[key.strip()] = value.strip().strip('"\'')

load_env_file()

# IST timezone for all timestamps
IST = pytz.timezone('Asia/Kolkata')

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from storage import DailyStorage
from qdrant_manager import QdrantManager
from extractor import QwenExtractor
from embedder import TMRRelationEmbedder
import logging

# Custom formatter for IST timestamps
class ISTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, IST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

# Setup logging with IST timestamps
log_handler = logging.FileHandler(Path.home() / '.openclaw' / 'extensions' / 'TrueMemoryRecall' / 'logs' / 'extraction.log')
log_handler.setFormatter(ISTFormatter('%(asctime)s - TMR-Extract - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setFormatter(ISTFormatter('%(asctime)s - TMR-Extract - %(levelname)s - %(message)s'))

logger = logging.getLogger('TMR-Extract')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
logger.addHandler(console_handler)


def extract_agents_files():
    """Extract knowledge graphs from workspace context files (AGENTS.md, SOUL.md, etc.)"""
    logger.info("\n" + "="*60)
    logger.info("Processing Workspace Context Files")
    logger.info("="*60)
    
    workspace_dir = Path.home() / ".openclaw" / "workspace"
    graph_dir = Path.home() / ".openclaw" / "workspace" / "memory" / "graph"
    agents_graph_dir = graph_dir / "agents_files"
    agents_graph_dir.mkdir(parents=True, exist_ok=True)
    
    # Files to process
    context_files = [
        "AGENTS.md",
        "SOUL.md", 
        "TOOLS.md",
        "IDENTITY.md",
        "USER.md",
        "MEMORY.md"
    ]
    
    qdrant = QdrantManager()
    embedder = TMRRelationEmbedder()
    
    # Initialize semantic vectors collection (ensures it exists)
    try:
        qdrant.init_collections(vector_size=768)
    except Exception as e:
        logger.warning(f"Failed to init collections: {e}")
    
    import os
    api_key = os.environ.get('TMR_API_KEY') or os.environ.get('OPENROUTER_API_KEY')
    
    if not api_key:
        logger.error("TMR_API_KEY or OPENROUTER_API_KEY not set. Skipping agents files.")
        return False
    
    extractor = QwenExtractor(api_key=api_key)
    total_processed = 0
    
    for filename in context_files:
        file_path = workspace_dir / filename
        
        if not file_path.exists():
            logger.info(f"{filename}: not found, skipping")
            continue
        
        # Check hash for change detection
        graph_file = agents_graph_dir / f"{filename}.json"
        hash_file = agents_graph_dir / f"{filename}.hash"
        
        import hashlib
        with open(file_path, 'rb') as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        # Skip if unchanged
        if graph_file.exists() and hash_file.exists():
            with open(hash_file, 'r') as f:
                stored_hash = f.read().strip()
            if stored_hash == current_hash:
                logger.info(f"{filename}: unchanged, skipping")
                continue
            else:
                logger.info(f"{filename}: changed, re-extracting...")
        else:
            logger.info(f"{filename}: new file, extracting...")
        
        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if len(content) < 50:
            logger.info(f"{filename}: too short, skipping")
            continue
        
        # Extract knowledge graph
        logger.info(f"{filename}: extracting knowledge graph...")
        graph = extractor.extract_graph(content, str(file_path))
        
        if not graph:
            logger.error(f"{filename}: extraction failed")
            continue
        
        logger.info(f"{filename}: {len(graph.get('entities', []))} entities, {len(graph.get('relations', []))} relations")
        
        # Save graph
        with open(graph_file, 'w', encoding='utf-8') as f:
            json.dump(graph, f, indent=2)
        
        # Save hash
        with open(hash_file, 'w') as f:
            f.write(current_hash)
        
        # Store in Qdrant with file-specific IDs
        base_id = int(hashlib.md5(filename.encode()).hexdigest(), 16) % (10**10)
        relations = graph.get('relations', [])
        
        # Prepare batch data for semantic vectors
        semantic_batch = []
        texts_to_embed = []
        relation_indices = []
        
        for i, rel in enumerate(relations):
            try:
                # Add source file info
                rel_with_source = rel.copy()
                rel_with_source['source_file'] = filename
                rel_with_source['source_type'] = 'context_file'
                
                point_id = base_id + i
                
                # Store in agents_files collection (existing behavior)
                qdrant.client.upsert(
                    collection_name=qdrant.collections["agents_files"],
                    points=[{
                        "id": point_id,
                        "vector": [0.0],
                        "payload": rel_with_source
                    }]
                )
                
                # Prepare for semantic embedding
                # Create text from subject + relation + object
                text = f"{rel.get('subject', '')} {rel.get('relation', '')} {rel.get('object', '')}".strip()
                if text:
                    texts_to_embed.append(text)
                    relation_indices.append((point_id, rel_with_source))
                
            except Exception as e:
                logger.warning(f"Failed to store relation {i} for {filename}: {e}")
        
        # Batch embed and store semantic vectors
        if texts_to_embed:
            try:
                logger.info(f"{filename}: embedding {len(texts_to_embed)} relations...")
                embeddings = embedder.embed_batch(texts_to_embed)
                
                for idx, embedding in enumerate(embeddings):
                    if embedding:
                        point_id, rel_payload = relation_indices[idx]
                        semantic_batch.append({
                            'id': point_id,
                            'vector': embedding,
                            'payload': rel_payload
                        })
                
                # Store batch in semantic vectors collection
                if semantic_batch:
                    success = qdrant.store_semantic_vectors_batch(semantic_batch)
                    if success:
                        logger.info(f"{filename}: stored {len(semantic_batch)} semantic vectors")
                    else:
                        logger.warning(f"{filename}: failed to store some semantic vectors")
            except Exception as e:
                logger.warning(f"Failed to embed relations for {filename}: {e}")
                # Continue without failing - backward compatibility
        
        logger.info(f"{filename}: stored {len(relations)} relations")
        total_processed += 1
    
    logger.info(f"\nContext files processed: {total_processed}/{len(context_files)}")
    return True


def extract_conversations():
    """Extract knowledge graphs from yesterday and today"""
    logger.info("="*60)
    logger.info("TMR Twice-Daily Extraction Started")
    logger.info("="*60)
    
    raw_dir = Path.home() / ".openclaw" / "workspace" / "memory" / "raw"
    graph_dir = Path.home() / ".openclaw" / "workspace" / "memory" / "graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    
    storage = DailyStorage(str(raw_dir))
    qdrant = QdrantManager()
    embedder = TMRRelationEmbedder()
    
    # Initialize semantic vectors collection (ensures it exists)
    try:
        qdrant.init_collections(vector_size=768)
    except Exception as e:
        logger.warning(f"Failed to init collections: {e}")
    
    # Process yesterday and today
    dates_to_process = [
        datetime.now(IST) - timedelta(days=1),
        datetime.now(IST)
    ]
    
    total_extracted = 0
    
    for date in dates_to_process:
        file_path = storage._get_daily_file_path(date)
        
        if not file_path.exists():
            logger.info(f"No file for {date.date()}, skipping")
            continue
        
        # Check if already extracted
        graph_file = graph_dir / f"{date.strftime('%Y-%m-%d')}.json"
        hash_file = graph_dir / f"{date.strftime('%Y-%m-%d')}.hash"
        
        # Calculate current file hash
        import hashlib
        with open(file_path, 'rb') as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        # Skip only if hash matches (file unchanged)
        if graph_file.exists() and hash_file.exists():
            with open(hash_file, 'r') as f:
                stored_hash = f.read().strip()
            if stored_hash == current_hash:
                logger.info(f"Already extracted for {date.date()} (no changes), skipping")
                continue
            else:
                logger.info(f"Raw file changed for {date.date()}, re-extracting...")
        
        logger.info(f"\nProcessing: {file_path}")
        
        # Read conversation
        with open(file_path, 'r', encoding='utf-8') as f:
            conversation = f.read()
        
        lines = conversation.split('\n')
        if len(lines) < 5:
            logger.info(f"File too short ({len(lines)} lines), skipping")
            continue
        
        # Extract with Gemini
        logger.info(f"Extracting knowledge graph...")
        
        # Load API key from environment
        api_key = os.environ.get('TMR_API_KEY') or os.environ.get('OPENROUTER_API_KEY')
        if not api_key:
            logger.error("TMR_API_KEY or OPENROUTER_API_KEY environment variable not set. Skipping.")
            continue
        extractor = QwenExtractor(api_key=api_key)
        graph = extractor.extract_graph(conversation, str(file_path))
        
        if not graph:
            logger.error(f"Extraction failed for {date.date()}")
            continue
        
        logger.info(f"Extracted: {len(graph.get('entities', []))} entities, {len(graph.get('relations', []))} relations")
        
        # Save graph
        with open(graph_file, 'w', encoding='utf-8') as f:
            json.dump(graph, f, indent=2)
        logger.info(f"Saved graph to: {graph_file}")
        
        # Save hash for change detection
        with open(hash_file, 'w') as f:
            f.write(current_hash)
        logger.info(f"Saved file hash to: {hash_file}")
        
        # Store in Qdrant
        import uuid
        base_id = int(date.strftime('%Y%m%d')) * 10000  # Base for this date
        relations = graph.get('relations', [])
        
        # Prepare batch data for semantic vectors
        semantic_batch = []
        texts_to_embed = []
        relation_indices = []
        
        for i, rel in enumerate(relations):
            try:
                point_id = base_id + i  # Integer ID
                
                # Store in knowledge_graph collection (existing behavior)
                qdrant.client.upsert(
                    collection_name=qdrant.collections["knowledge_graph"],
                    points=[{
                        "id": point_id,
                        "vector": [0.0],
                        "payload": rel
                    }]
                )
                
                # Prepare for semantic embedding
                # Create text from subject + relation + object
                text = f"{rel.get('subject', '')} {rel.get('relation', '')} {rel.get('object', '')}".strip()
                if text:
                    texts_to_embed.append(text)
                    relation_indices.append((point_id, rel))
                
            except Exception as e:
                logger.warning(f"Failed to store relation {i}: {e}")
        
        # Batch embed and store semantic vectors
        if texts_to_embed:
            try:
                logger.info(f"Embedding {len(texts_to_embed)} relations...")
                embeddings = embedder.embed_batch(texts_to_embed)
                
                for idx, embedding in enumerate(embeddings):
                    if embedding:
                        point_id, rel_payload = relation_indices[idx]
                        # Add source info for conversations
                        rel_with_source = rel_payload.copy()
                        rel_with_source['source_date'] = date.strftime('%Y-%m-%d')
                        rel_with_source['source_type'] = 'conversation'
                        
                        semantic_batch.append({
                            'id': point_id,
                            'vector': embedding,
                            'payload': rel_with_source
                        })
                
                # Store batch in semantic vectors collection
                if semantic_batch:
                    success = qdrant.store_semantic_vectors_batch(semantic_batch)
                    if success:
                        logger.info(f"Stored {len(semantic_batch)} semantic vectors")
                    else:
                        logger.warning(f"Failed to store some semantic vectors")
            except Exception as e:
                logger.warning(f"Failed to embed relations: {e}")
                # Continue without failing - backward compatibility
        
        logger.info(f"Stored {len(relations)} relations in Qdrant")
        total_extracted += 1
        
        # Print cost
        cost = graph.get('extraction_cost', {})
        logger.info(f"Cost: {cost.get('total_tokens', 0)} tokens")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Extraction complete: {total_extracted} files processed")
    logger.info(f"{'='*60}")
    
    return True


if __name__ == "__main__":
    try:
        # Extract conversations (yesterday and today)
        extract_conversations()
        
        # Extract workspace context files (AGENTS.md, SOUL.md, etc.)
        extract_agents_files()
        
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
(1)
