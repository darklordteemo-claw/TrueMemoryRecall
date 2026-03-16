#!/usr/bin/env python3
"""
TMR Twice-Daily Extraction
Runs at 12:00 and 00:00 to extract knowledge graphs from raw conversations
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from storage import DailyStorage
from qdrant_manager import QdrantManager
from extractor import GeminiExtractor
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TMR-Extract - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / '.openclaw' / 'extensions' / 'TrueMemoryRecall' / 'logs' / 'extraction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TMR-Extract')


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
    
    # Process yesterday and today
    dates_to_process = [
        datetime.now() - timedelta(days=1),
        datetime.now()
    ]
    
    total_extracted = 0
    
    for date in dates_to_process:
        file_path = storage._get_daily_file_path(date)
        
        if not file_path.exists():
            logger.info(f"No file for {date.date()}, skipping")
            continue
        
        # Check if already extracted
        graph_file = graph_dir / f"{date.strftime('%Y-%m-%d')}.json"
        if graph_file.exists():
            logger.info(f"Already extracted for {date.date()}, skipping")
            continue
        
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
        import os
        api_key = os.environ.get('OPENROUTER_API_KEY')
        if not api_key:
            logger.error("OPENROUTER_API_KEY environment variable not set. Skipping.")
            continue
        extractor = GeminiExtractor(api_key=api_key)
        graph = extractor.extract_graph(conversation, str(file_path))
        
        if not graph:
            logger.error(f"Extraction failed for {date.date()}")
            continue
        
        logger.info(f"Extracted: {len(graph.get('entities', []))} entities, {len(graph.get('relations', []))} relations")
        
        # Save graph
        with open(graph_file, 'w', encoding='utf-8') as f:
            json.dump(graph, f, indent=2)
        logger.info(f"Saved graph to: {graph_file}")
        
        # Store in Qdrant
        for i, rel in enumerate(graph.get('relations', [])):
            try:
                qdrant.client.upsert(
                    collection_name=qdrant.collections["knowledge_graph"],
                    points=[{
                        "id": f"{date.strftime('%Y%m%d')}_{i}",
                        "vector": [0.0],
                        "payload": rel
                    }]
                )
            except Exception as e:
                logger.warning(f"Failed to store relation {i}: {e}")
        
        logger.info(f"Stored {len(graph.get('relations', []))} relations in Qdrant")
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
        extract_conversations()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
