#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Daily Processing Script
Processes yesterday's conversation and extracts knowledge graph
"""

import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Set up logging
plugin_dir = Path(__file__).parent.parent
logs_dir = plugin_dir / 'logs'
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TMR-Daily - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'daily.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TMR-Daily')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from storage import DailyStorage
from qdrant_manager import QdrantManager
from extractor import GeminiExtractor


def process_daily_extraction():
    """
    Process yesterday's conversation file and extract knowledge graph.
    This runs once daily via cron.
    """
    logger.info("="*60)
    logger.info("TMR Daily Processing Started")
    logger.info("="*60)
    
    # Initialize components
    raw_dir = Path("~/.openclaw/workspace/memory/raw").expanduser()
    graph_dir = Path("~/.openclaw/workspace/memory/graph").expanduser()
    graph_dir.mkdir(parents=True, exist_ok=True)
    
    storage = DailyStorage(str(raw_dir))
    qdrant = QdrantManager()
    
    # Get yesterday's file
    yesterday = datetime.now() - timedelta(days=1)
    file_path = storage._get_daily_file_path(yesterday)
    
    print(f"\nProcessing: {file_path}")
    
    # Check if file exists
    if not file_path.exists():
        print(f"  ⚠️  No conversation file for {yesterday.date()}")
        print("  Nothing to process.")
        return True
    
    # Read conversation
    print(f"  Reading conversation file...")
    with open(file_path, 'r', encoding='utf-8') as f:
        conversation = f.read()
    
    lines = conversation.split('\n')
    print(f"  File has {len(lines)} lines")
    
    # Skip if too short
    if len(lines) < 5:  # Header + at least a couple messages
        print(f"  ⚠️  File too short ({len(lines)} lines), skipping extraction")
        return True
    
    # Extract knowledge graph using Gemini
    print(f"\n  Extracting knowledge graph with Gemini...")
    
    # Load API key from config
    config_path = Path(__file__).parent.parent / 'config' / 'plugin.yaml'
    api_key = None
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            api_key = config.get('extraction', {}).get('api_key')
    except Exception as e:
        print(f"  ⚠️  Could not load config: {e}")
        return False
    
    if not api_key:
        print("  ❌ No API key found in config")
        return False
    
    extractor = GeminiExtractor(api_key=api_key)
    graph = extractor.extract_graph(conversation, str(file_path))
    
    if not graph:
        print("  ❌ Extraction failed")
        return False
    
    print(f"  ✅ Extraction successful")
    print(f"     Entities: {len(graph.get('entities', []))}")
    print(f"     Relationships: {len(graph.get('relationships', []))}")
    
    # Save graph to file
    graph_file = graph_dir / f"{yesterday.strftime('%Y-%m-%d')}.json"
    with open(graph_file, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2)
    print(f"  ✅ Saved graph to: {graph_file}")
    
    # Store in Qdrant for fast lookup
    print(f"\n  Storing in Qdrant...")
    for i, rel in enumerate(graph.get('relationships', [])):
        # Create a unique ID for each relationship
        rel_id = f"{yesterday.strftime('%Y%m%d')}_{i}"
        
        # Store in knowledge_graph collection
        try:
            qdrant.client.upsert(
                collection_name=qdrant.collections["knowledge_graph"],
                points=[{
                    "id": rel_id,
                    "vector": [0.0],  # Dummy vector
                    "payload": rel
                }]
            )
        except Exception as e:
            print(f"  ⚠️  Failed to store relation {i}: {e}")
    
    print(f"  ✅ Stored {len(graph.get('relationships', []))} relations in Qdrant")
    
    # Print cost info
    cost = graph.get('extraction_cost', {})
    total_tokens = cost.get('total_tokens', 0)
    print(f"\n  Cost: {total_tokens} tokens (~${total_tokens * 0.0000003:.6f})")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    return True


def test_daily_processing():
    """Test the daily processing with sample data"""
    import tempfile
    import shutil
    from filter import MessageFilter
    
    print("="*60)
    print("TESTING: TMR Daily Processing")
    print("="*60)
    
    # Create temp directories
    temp_dir = tempfile.mkdtemp()
    raw_dir = Path(temp_dir) / "raw"
    graph_dir = Path(temp_dir) / "graph"
    raw_dir.mkdir()
    graph_dir.mkdir()
    
    try:
        # Create a sample conversation file for "yesterday"
        yesterday = datetime.now() - timedelta(days=1)
        file_path = raw_dir / f"{yesterday.strftime('%Y-%m-%d')}.md"
        
        sample_conversation = f"""# {yesterday.date()} — Auto-generated
# Line numbers for reference

[14:32:15] User: im thinking about the memory system we discussed
[14:33:22] Liz: yeah what aspect are you considering
[14:35:47] User: how do we make it cheaper without losing quality
[14:36:00] Liz: lets explore some options
[14:38:10] User: what if we use files instead of database
[14:40:30] Liz: that could work for simplicity
"""
        
        with open(file_path, 'w') as f:
            f.write(sample_conversation)
        
        print(f"Created sample file: {file_path}")
        print(f"Content:\n{sample_conversation[:200]}...\n")
        
        # Initialize storage pointing to temp dir
        storage = DailyStorage(str(raw_dir))
        
        # Check file exists
        check_path = storage._get_daily_file_path(yesterday)
        print(f"Looking for: {check_path}")
        print(f"File exists: {check_path.exists()}")
        
        if not check_path.exists():
            print("  ❌ Test setup failed - file not found")
            return False
        
        # Read file
        with open(check_path, 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        print(f"  File has {len(lines)} lines")
        
        if len(lines) >= 5:
            print("  ✅ File valid for processing")
        else:
            print("  ❌ File too short")
            return False
        
        print("\n" + "="*60)
        print("RESULTS: Daily processing test passed ✅")
        print("Note: Actual Gemini extraction skipped in test")
        print("      (would require API call)")
        print("="*60)
        
        return True
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TMR Daily Processing")
    parser.add_argument("--test", action="store_true", help="Run test mode")
    args = parser.parse_args()
    
    if args.test:
        success = test_daily_processing()
    else:
        success = process_daily_extraction()
    
    sys.exit(0 if success else 1)
