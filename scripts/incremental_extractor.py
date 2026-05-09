#!/usr/bin/env python3
"""
TMR v2 - Incremental Knowledge Graph Extraction

Runs every 2 hours to extract relations from new/changed raw files.
Uses hash tracking to avoid reprocessing unchanged files.

Usage:
    python3 incremental_extractor.py [--force]
    
    --force: Reprocess all files regardless of hash
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple

# Load environment variables from .env file manually (for cron compatibility)
def load_env_file():
    script_dir = Path(__file__).parent.parent
    env_path = script_dir / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"\'')

load_env_file()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractor import QwenExtractor
from qdrant_manager import QdrantManager
from config_loader import get_config

# Setup logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('TMR.IncrementalExtractor')


class IncrementalExtractor:
    """
    Extracts knowledge graphs incrementally from raw conversation files.
    Only processes new or changed files based on hash tracking.
    """
    
    def __init__(self):
        self.config = get_config()
        
        # Paths
        self.raw_dir = Path(self.config.storage.get('raw_dir', '~/.openclaw/workspace/memory/raw')).expanduser()
        self.graph_dir = Path(self.config.storage.get('graph_dir', '~/.openclaw/workspace/memory/graph')).expanduser()
        self.hash_file = self.raw_dir / ".hashes.json"
        
        # Ensure directories exist
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        api_key = os.environ.get('OPENROUTER_API_KEY')
        if not api_key:
            logger.error("OPENROUTER_API_KEY not found in environment or .env file")
            raise ValueError("OPENROUTER_API_KEY is required")
        self.extractor = QwenExtractor(api_key=api_key)
        self.qdrant = QdrantManager()
        
        # Load hash tracking
        self.processed_hashes = self._load_hash_tracking()
    
    def _load_hash_tracking(self) -> Dict[str, Dict]:
        """Load hash tracking database"""
        if self.hash_file.exists():
            try:
                with open(self.hash_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load hash file: {e}")
                return {}
        return {}
    
    def _save_hash_tracking(self):
        """Save hash tracking database"""
        with open(self.hash_file, 'w') as f:
            json.dump(self.processed_hashes, f, indent=2)
    
    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    def _get_files_to_process(self, force_all: bool = False) -> List[Tuple[Path, str]]:
        """
        Get list of raw files that need processing.
        
        Returns:
            List of (file_path, file_hash) tuples
        """
        files_to_process = []
        
        # Find all .md files in raw directory
        md_files = list(self.raw_dir.glob("*.md"))
        
        # Also check for sequence files (yyyy-mm-dd (NN).md)
        md_files.extend(self.raw_dir.glob("* (*).md"))
        
        for file_path in md_files:
            if file_path.name.startswith('.'):
                continue
            
            # Calculate current hash
            current_hash = self._calculate_hash(file_path)
            
            # Check if already processed
            relative_name = file_path.name
            
            if force_all:
                files_to_process.append((file_path, current_hash))
            elif relative_name not in self.processed_hashes:
                # New file
                files_to_process.append((file_path, current_hash))
                logger.info(f"New file: {relative_name}")
            elif self.processed_hashes[relative_name].get('hash') != current_hash:
                # Modified file
                files_to_process.append((file_path, current_hash))
                logger.info(f"Modified file: {relative_name}")
            elif not self.processed_hashes[relative_name].get('processed', True):
                # Previously failed or never actually processed despite having hash
                files_to_process.append((file_path, current_hash))
                logger.info(f"Unfinished file: {relative_name}")
        
        return files_to_process
    
    def _extract_from_file(self, file_path: Path) -> Dict:
        """
        Extract knowledge graph from a single file.
        
        Returns:
            Knowledge graph dict
        """
        logger.info(f"Extracting from: {file_path.name}")
        
        # Read file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract using Qwen
        result = self.extractor.extract_graph(content, str(file_path))
        
        return result
    
    def _save_graph(self, file_path: Path, graph: Dict):
        """Save extracted graph to disk"""
        # Parse date from filename
        # Handle both yyyy-mm-dd.md and yyyy-mm-dd (NN).md
        date_match = file_path.stem.split(' ')[0]  # Get first part before space
        
        try:
            datetime.strptime(date_match, '%Y-%m-%d')
            date_str = date_match
        except ValueError:
            # Use file modification time
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            date_str = mtime.strftime('%Y-%m-%d')
        
        # Save to graph directory
        output_file = self.graph_dir / f"{date_str}.json"
        
        # If file exists, merge with existing
        if output_file.exists():
            try:
                with open(output_file, 'r') as f:
                    existing = json.load(f)
                
                # Merge relations (avoid duplicates)
                existing_relations = existing.get('relations', [])
                new_relations = graph.get('relations', [])
                
                # Simple dedup by string representation
                existing_set = {json.dumps(r, sort_keys=True) for r in existing_relations}
                for rel in new_relations:
                    rel_str = json.dumps(rel, sort_keys=True)
                    if rel_str not in existing_set:
                        existing_relations.append(rel)
                
                existing['relations'] = existing_relations
                
                # Merge entities
                existing_entities = set(existing.get('entities', []))
                existing_entities.update(graph.get('entities', []))
                existing['entities'] = list(existing_entities)
                
                # Update metadata
                existing['extraction_time'] = datetime.now().isoformat()
                existing['source_files'] = existing.get('source_files', []) + [file_path.name]
                
                graph = existing
                
            except Exception as e:
                logger.warning(f"Could not merge with existing graph: {e}")
        
        # Save
        with open(output_file, 'w') as f:
            json.dump(graph, f, indent=2)
        
        logger.info(f"Saved graph to: {output_file}")
        return output_file
    
    def _index_to_qdrant(self, graph: Dict, source_file: str):
        """Index extracted relations to Qdrant"""
        try:
            relations = graph.get('relations', [])
            if not relations:
                logger.info("No relations to index")
                return
            
            logger.info(f"Indexing {len(relations)} relations to Qdrant")
            
            # Add source info to each relation
            for rel in relations:
                rel['source_file'] = source_file
                rel['indexed_at'] = datetime.now().isoformat()
            
            # Index to Qdrant
            self.qdrant.index_relations_batch(relations)
            
            logger.info(f"Indexed {len(relations)} relations")
            
        except Exception as e:
            logger.error(f"Failed to index to Qdrant: {e}")
    
    def run(self, force_all: bool = False) -> Dict:
        """
        Run incremental extraction.
        
        Args:
            force_all: Process all files regardless of hash
            
        Returns:
            Statistics dict
        """
        logger.info("=" * 70)
        logger.info("TMR v2 Incremental Extraction Starting")
        logger.info("=" * 70)
        
        stats = {
            'files_processed': 0,
            'relations_extracted': 0,
            'entities_found': 0,
            'errors': 0,
            'start_time': datetime.now().isoformat()
        }
        
        # Get files to process
        files_to_process = self._get_files_to_process(force_all)
        
        if not files_to_process:
            logger.info("No new or changed files to process")
            stats['end_time'] = datetime.now().isoformat()
            return stats
        
        logger.info(f"Processing {len(files_to_process)} files")
        
        # Process each file
        for file_path, file_hash in files_to_process:
            try:
                # Extract
                graph = self._extract_from_file(file_path)
                
                # Save graph
                output_file = self._save_graph(file_path, graph)
                
                # Index to Qdrant
                self._index_to_qdrant(graph, file_path.name)
                
                # Update hash tracking
                relative_name = file_path.name
                self.processed_hashes[relative_name] = {
                    'hash': file_hash,
                    'processed': True,
                    'timestamp': datetime.now().isoformat(),
                    'relations_count': len(graph.get('relations', [])),
                    'entities_count': len(graph.get('entities', []))
                }
                
                # Update stats
                stats['files_processed'] += 1
                stats['relations_extracted'] += len(graph.get('relations', []))
                stats['entities_found'] += len(graph.get('entities', []))
                
                logger.info(f"✅ Processed: {file_path.name} "
                          f"({len(graph.get('relations', []))} relations)")
                
            except Exception as e:
                logger.error(f"❌ Failed to process {file_path.name}: {e}")
                stats['errors'] += 1
        
        # Save hash tracking
        self._save_hash_tracking()
        
        stats['end_time'] = datetime.now().isoformat()
        
        logger.info("=" * 70)
        logger.info("Incremental Extraction Complete")
        logger.info(f"Files: {stats['files_processed']}")
        logger.info(f"Relations: {stats['relations_extracted']}")
        logger.info(f"Entities: {stats['entities_found']}")
        if stats['errors'] > 0:
            logger.warning(f"Errors: {stats['errors']}")
        logger.info("=" * 70)
        
        return stats


def main():
    parser = argparse.ArgumentParser(description='TMR v2 Incremental Extractor')
    parser.add_argument('--force', action='store_true',
                       help='Reprocess all files regardless of hash')
    parser.add_argument('--stats', action='store_true',
                       help='Show statistics and exit')
    
    args = parser.parse_args()
    
    extractor = IncrementalExtractor()
    
    if args.stats:
        # Show current stats
        print("Hash Tracking Statistics:")
        print("=" * 50)
        for filename, info in extractor.processed_hashes.items():
            print(f"{filename}:")
            print(f"  Relations: {info.get('relations_count', 0)}")
            print(f"  Processed: {info.get('timestamp', 'unknown')}")
        return
    
    # Run extraction
    stats = extractor.run(force_all=args.force)
    
    # Print summary
    print("\n" + "=" * 50)
    print("Extraction Summary:")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Relations extracted: {stats['relations_extracted']}")
    print(f"Entities found: {stats['entities_found']}")
    if stats['errors'] > 0:
        print(f"Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
