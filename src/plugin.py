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
# Use new v2 injector with full Cognee pipeline
from tmr_injector import TMRCogneeInjector
from message_buffer import buffer_message
from config_loader import get_config


import logging
from datetime import datetime
import pytz

# IST timezone for all logging (as requested by user)
IST = pytz.timezone('Asia/Kolkata')

class ISTFormatter(logging.Formatter):
    """Custom formatter that uses IST timezone"""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, IST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime('%Y-%m-%d %H:%M:%S') + ' IST'

# Set up logging with IST timezone
plugin_dir = Path(__file__).parent.parent
logs_dir = plugin_dir / 'logs'
logs_dir.mkdir(exist_ok=True)

formatter = ISTFormatter('%(asctime)s - TMR - %(levelname)s - %(message)s')

file_handler = logging.FileHandler(logs_dir / 'tmr.log')
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger('TMR')


class QMDMemoryPlugin:
    """Main plugin class for TrueMemoryRecall (TMR) v2"""

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

        # Initialize NEW v2 injector with full Cognee pipeline
        logger.info("Initializing TMR v2 Cognee-Style Injector...")
        self.injector = TMRCogneeInjector(
            graph_dir=self.config.get('storage', {}).get('graph_dir', '~/.openclaw/workspace/memory/graph'),
            enable_feedback=True
        )
        logger.info("TMR v2 Injector initialized")

    def _load_config(self, config_path: str = None) -> dict:
        """Load configuration from YAML file"""
        import yaml

        # Try new config first, fall back to old
        if config_path is None:
            new_config_path = Path(__file__).parent.parent / 'config' / 'tmr_config.yaml'
            old_config_path = Path(__file__).parent.parent / 'config' / 'plugin.yaml'

            if new_config_path.exists():
                config_path = new_config_path
            else:
                config_path = old_config_path

        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config from {config_path}: {e}")
            return {}
    
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
            speaker: Who sent the message (e.g., "User", "Liz")
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

        # Step 2: Buffer for v2 real-time system (chunked files)
        try:
            flushed = buffer_message(speaker, message)
            if flushed:
                logger.info(f"Message buffer flushed (size/time/session trigger)")
        except Exception as e:
            logger.warning(f"Message buffering failed: {e}")

        # Step 3: Also store to daily file (backward compatibility)
        logger.info(f"Storing message to daily file...")
        line_start, line_end, byte_offset = self.storage.store_message(timestamp, speaker, message)
        logger.info(f"Stored at line {line_start}, byte offset {byte_offset}")

        # Note: Qdrant indexing happens during batch extraction (every 2 hours), not real-time
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
        # Extract actual user message from prompt (remove system metadata)
        clean_query = query
        if 'Sender (untrusted metadata):' in query:
            # Find the actual message after the metadata block
            parts = query.split('[Tue ')
            if len(parts) > 1:
                # Extract message after the timestamp line
                message_parts = parts[1].split('\n', 1)
                if len(message_parts) > 1:
                    clean_query = message_parts[1].strip()
        
        # Log full query clearly
        logger.info("=" * 70)
        logger.info("[TMR] USER QUERY:")
        logger.info("=" * 70)
        for line in clean_query.split('\n'):
            logger.info(f"[TMR]   {line}")
        logger.info("=" * 70)
        
        if not self.config.get('injection', {}).get('enabled', True):
            logger.info("[TMR] Injection disabled in config")
            return ""
        
        context = self.injector.inject_context(query)
        
        if context:
            # Save staging file for auto-feedback evaluating post-agent response
            if hasattr(self.injector, 'last_retrieval_metadata'):
                plugin_dir = Path(__file__).resolve().parent.parent
                staging_path = plugin_dir / 'logs' / 'pending_feedback.json'
                try:
                    import json
                    staging_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(staging_path, 'w', encoding='utf-8') as f:
                        json.dump(self.injector.last_retrieval_metadata, f, indent=2)
                    logger.info(f"[TMR] Staged retrieval metadata for auto-feedback: {staging_path.name}")
                except Exception as e:
                    logger.error(f"[TMR] Failed to stage feedback metadata: {e}")

            # Parse individual memories from context for detailed logging
            logger.info("[TMR] SEARCHING memories...")
            logger.info("-" * 70)
            
            memories = []
            lines = context.split('\n')
            current_source = ""
            
            for line in lines:
                # Track source type
                if 'From previous conversations:' in line:
                    current_source = 'conversations'
                elif 'From workspace context files:' in line:
                    current_source = 'context_file'
                elif 'Source:' in line or 'from:' in line.lower():
                    # Extract source file info
                    pass
                elif line.strip().startswith(('1.', '2.', '3.', '4.', '5.')) and '→' in line:
                    # This is a memory entry like "1. Subject → RELATION → Object"
                    mem_match = line.strip()
                    memories.append({'line': mem_match, 'source': current_source})
                    logger.info(f"[TMR] [FOUND] {mem_match} (from: {current_source})")
            
            if memories:
                logger.info("-" * 70)
                logger.info(f"[TMR] [FOUND] {len(memories)} memories total")
            else:
                logger.info("[TMR] [FOUND] Context injected but no individual memories parsed")
            
            logger.info("-" * 70)
            logger.info(f"[TMR] [INJECTED] {len(context)} characters")
            logger.info("=" * 70)
            
            # Also write to a separate injection log file for easy viewing (in plugin logs dir)
            try:
                injection_detail_file = plugin_dir / 'logs' / 'tmr_injection_detail.log'
                with open(injection_detail_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n{'='*70}\n")
                    f.write(f"QUERY: {clean_query[:500]}\n")
                    f.write(f"{'='*70}\n")
                    f.write(f"INJECTED CONTEXT ({len(context)} chars):\n")
                    f.write(context)
                    f.write(f"\n{'='*70}\n\n")
            except Exception:
                pass  # Don't fail if can't write detail log
            
        else:
            logger.info("[TMR] [NO MEMORY] No relevant memory found for this query")
            logger.info("=" * 70)
        
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
            ("User", "hi", "14:30:00"),  # Should be filtered
            ("User", "im thinking about the memory system", "14:32:15"),  # Store
            ("Liz", "ok", "14:32:20"),  # Filtered
            ("Liz", "yeah what aspect are you considering", "14:33:22"),  # Store
            ("User", "how do we make it cheaper without losing quality", "14:35:47"),  # Store
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
        has_user_msg = any("im thinking about the memory system" in line for line in lines)
        has_liz_msg = any("yeah what aspect are you considering" in line for line in lines)
        
        if has_user_msg and has_liz_msg:
            print("  ✅ Correct messages stored")
        else:
            print("  ❌ Missing expected messages")
            return False
        
        # Verify filtered messages NOT in file
        has_hi = any(line.strip() == "[14:30:00] User: hi" for line in lines)
        has_ok = any(line.strip() == "[14:32:20] Liz: ok" for line in lines)
        
        if not has_hi and not has_ok:
            print("  ✅ Filtered messages correctly excluded")
        else:
            print("  ❌ Filtered messages found in file")
            return False
        
        # Test 4: Verify Qdrant indexing
        print("\nTest 4: Verifying Qdrant indexing...")
        info = plugin.qdrant.get_line_info(str(file_path), 1)  # Line 1 should be first User msg
        
        if info and info.get('speaker') == 'User':
            print(f"  ✅ Qdrant index: {info}")
        else:
            print(f"  ❌ Qdrant indexing failed (got: {info})")
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
            
            # ── AUTO-FEEDBACK: Analyze response against injected memories ──
            try:
                from ai_feedback_generator import auto_feedback_after_response
                
                # Read staged retrieval metadata from inject phase
                staging_path = plugin_dir / 'logs' / 'pending_feedback.json'
                if staging_path.exists():
                    with open(staging_path, 'r', encoding='utf-8') as f:
                        staging = json.load(f)
                    
                    event_id = staging.get('event_id')
                    query = staging.get('query', '')
                    memories_injected = staging.get('memories_injected', [])
                    
                    # Find assistant's response in messages
                    assistant_response = ""
                    for msg in reversed(messages):
                        if msg.get('role') == 'assistant':
                            assistant_response = msg.get('content', '')
                            break
                    
                    if event_id and assistant_response and memories_injected:
                        logger.info(f"[TMR] Auto-feedback: analyzing response for event {event_id[:8]}...")
                        auto_feedback_after_response(
                            query=query,
                            memories_injected=memories_injected,
                            ai_response=assistant_response,
                            event_id=event_id,
                            injector=plugin.injector
                        )
                        logger.info("[TMR] Auto-feedback complete")
                    
                    # Clean up staging file so we don't re-process
                    staging_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"[TMR] Auto-feedback failed: {e}")
            # ── END AUTO-FEEDBACK ──
            
            # Normal message capture/storage
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
