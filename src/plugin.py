#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Main Entry Point
Integrates filter, storage, and Qdrant for auto-extract functionality
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from filter import MessageFilter
from storage import DailyStorage
from qdrant_manager import QdrantManager
from injector import ContextInjector


import logging
from datetime import datetime

# Set up logging
plugin_dir = Path(__file__).parent.parent
logs_dir = plugin_dir / 'logs'
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TMR - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(logs_dir / 'tmr.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TMR')


class QMDMemoryPlugin:
    """Main plugin class for TrueMemoryRecall (TMR)"""
    
    def __init__(self, config_path: str = None):
        """Initialize plugin with configuration"""
        self.config = self._load_config(config_path)
        
        # Initialize components
        self.filter = MessageFilter(
            min_length=self.config.get('filter', {}).get('min_length', 10)
        )
        
        self.storage = DailyStorage(
            raw_dir=self.config.get('storage', {}).get('raw_dir', '~/.openclaw/workspace/memory/raw')
        )
        
        self.qdrant = QdrantManager(
            host=self.config.get('qdrant', {}).get('host', 'localhost'),
            port=self.config.get('qdrant', {}).get('port', 6333)
        )
        
        # Initialize Qdrant collections
        self.qdrant.init_collections(vector_size=768)
        
        # Initialize injector for context building
        self.injector = ContextInjector(
            graph_dir=self.config.get('storage', {}).get('graph_dir', '~/.openclaw/workspace/memory/graph')
        )
    
    def _load_config(self, config_path: str = None) -> dict:
        """Load configuration from YAML file"""
        import yaml
        
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'plugin.yaml'
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
            return {}
    
    def on_message_received(self, speaker: str, message: str, timestamp: str = None) -> bool:
        """
        Hook: Called when a new message is received.
        
        Args:
            speaker: Who sent the message (e.g., "Uddipta", "Liz")
            message: The message content
            timestamp: Optional timestamp (default: now)
        
        Returns:
            True if message was stored, False if filtered out
        """
        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Step 1: Filter
        logger.info(f"Processing message from {speaker}: {message[:50]}...")
        should_store, reason = self.filter.should_store(message)
        
        if not should_store:
            logger.info(f"Filtered out: {reason}")
            return False
        
        # Step 2: Store to daily file
        logger.info(f"Storing message to daily file...")
        line_start, line_end = self.storage.store_message(timestamp, speaker, message)
        logger.info(f"Stored at line {line_start}")
        
        # Step 3: Index in Qdrant
        file_path = str(self.storage._get_daily_file_path())
        logger.info(f"Indexing in Qdrant: {file_path}:{line_start}")
        self.qdrant.store_line_index(
            file_path=file_path,
            line_number=line_start,
            timestamp=timestamp,
            speaker=speaker,
            byte_offset=0  # TODO: Calculate actual byte offset
        )
        logger.info(f"Successfully indexed in Qdrant")
        
        return True
    
    def on_context_build(self, query: str) -> str:
        """
        Hook: Called when building context for a query.
        Returns context string to inject.
        
        Args:
            query: The user's query
        
        Returns:
            Context string to add to LLM context (or empty string)
        """
        logger.info(f"Building context for query: {query[:50]}...")
        
        if not self.config.get('injection', {}).get('enabled', True):
            logger.info("Injection disabled in config")
            return ""
        
        context = self.injector.inject_context(query)
        
        if context:
            logger.info(f"Injected context with {context.count('Source:')} relations")
        else:
            logger.info("No relevant context found for injection")
        
        return context
    
    def close(self):
        """Cleanup resources"""
        self.storage.close()


def test_plugin():
    """Test the full plugin integration"""
    import tempfile
    import shutil
    
    print("="*60)
    print("TESTING: QMD Memory Plugin (Integration)")
    print("="*60)
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Create minimal config file for testing
        config_path = Path(temp_dir) / 'test_config.yaml'
        config_content = f"""
storage:
  raw_dir: "{temp_dir}"
qdrant:
  host: "localhost"
  port: 6333
filter:
  min_length: 10
"""
        with open(config_path, 'w') as f:
            f.write(config_content)
        
        # Initialize plugin
        print("\nTest 1: Initialize plugin...")
        plugin = QMDMemoryPlugin(config_path=str(config_path))
        print("  ✅ Plugin initialized")
        
        # Test 2: Process messages
        print("\nTest 2: Processing messages...")
        messages = [
            ("Uddipta", "hi", "14:30:00"),  # Should be filtered
            ("Uddipta", "im thinking about the memory system", "14:32:15"),  # Store
            ("Liz", "ok", "14:32:20"),  # Filtered
            ("Liz", "yeah what aspect are you considering", "14:33:22"),  # Store
            ("Uddipta", "how do we make it cheaper without losing quality", "14:35:47"),  # Store
        ]
        
        stored_count = 0
        filtered_count = 0
        
        for speaker, message, timestamp in messages:
            result = plugin.on_message_received(speaker, message, timestamp)
            if result:
                stored_count += 1
            else:
                filtered_count += 1
        
        print(f"\n  Results: {stored_count} stored, {filtered_count} filtered")
        print(f"  ✅ Message processing working")
        
        # Test 3: Verify file content
        print("\nTest 3: Verifying stored content...")
        plugin.storage.close()  # Flush to disk
        
        # Find the created file (should be today's date)
        temp_path = Path(temp_dir)
        md_files = list(temp_path.glob("*.md"))
        
        if not md_files:
            print("  ❌ No .md files found")
            return False
        
        file_path = md_files[0]  # Should be only one
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        lines = content.strip().split('\n')
        print(f"  File has {len(lines)} lines")
        
        # Check that we have the right messages
        has_uddipta_msg = any("im thinking about the memory system" in line for line in lines)
        has_liz_msg = any("yeah what aspect are you considering" in line for line in lines)
        
        if has_uddipta_msg and has_liz_msg:
            print("  ✅ Correct messages stored")
        else:
            print("  ❌ Missing expected messages")
            return False
        
        # Verify filtered messages NOT in file
        has_hi = any(line.strip() == "[14:30:00] Uddipta: hi" for line in lines)
        has_ok = any(line.strip() == "[14:32:20] Liz: ok" for line in lines)
        
        if not has_hi and not has_ok:
            print("  ✅ Filtered messages correctly excluded")
        else:
            print("  ❌ Filtered messages found in file")
            return False
        
        # Test 4: Verify Qdrant indexing
        print("\nTest 4: Verifying Qdrant indexing...")
        info = plugin.qdrant.get_line_info(str(file_path), 4)  # Line 4 should be first Uddipta msg
        
        if info and info.get('speaker') == 'Uddipta':
            print(f"  ✅ Qdrant index: {info}")
        else:
            print("  ❌ Qdrant indexing failed")
            return False
        
        plugin.close()
        
        print("\n" + "="*60)
        print("RESULTS: All integration tests passed ✅")
        print("="*60)
        return True
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    """CLI entry point for TypeScript integration"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--inject', help='Query to inject context for')
    parser.add_argument('--capture', help='JSON array of messages to capture')
    args = parser.parse_args()
    
    plugin = QMDMemoryPlugin()
    
    if args.inject:
        # Called by TypeScript before_agent_start hook
        context = plugin.on_context_build(args.inject)
        if context:
            print(context)
        plugin.close()
        return 0
    
    if args.capture:
        # Called by TypeScript after_agent_end hook
        try:
            messages = json.loads(args.capture)
            for msg in messages:
                speaker = msg.get('role', 'Unknown')
                content = msg.get('content', '')
                timestamp = datetime.now().strftime('%H:%M:%S')
                plugin.on_message_received(speaker, content, timestamp)
        except Exception as e:
            logger.error(f"Capture error: {e}")
        plugin.close()
        return 0
    
    # Default: run tests
    success = test_plugin()
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
