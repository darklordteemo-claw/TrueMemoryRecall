#!/usr/bin/env python3
"""
TMR v2 - Real-Time Message Buffer

Buffers incoming messages in temp files, flushes to raw/ when:
1. File reaches ~70% of LLM context window
2. Time gap > 1 hour since last message
3. Session changes (different sender)
4. Manual flush triggered
5. Cron time-based flush (2 hours)

File naming: yyyy-mm-dd (NN).md where NN is sequence number
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict

# Context window size for Qwen 3.5 Flash (approximate)
# 70% leaves room for system prompts and extraction
DEFAULT_CONTEXT_LIMIT = 28000  # ~70% of 40K context


@dataclass
class BufferState:
    """Tracks current buffer file state"""
    current_file: str
    sequence_number: int
    char_count: int
    last_flush: datetime
    last_message_time: datetime  # NEW: Track last message timestamp
    last_sender: str  # NEW: Track current session speaker
    
    def to_dict(self):
        data = asdict(self)
        data['last_flush'] = self.last_flush.isoformat()
        data['last_message_time'] = self.last_message_time.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BufferState':
        data['last_flush'] = datetime.fromisoformat(data['last_flush'])
        data['last_message_time'] = datetime.fromisoformat(data.get('last_message_time', data['last_flush']))
        data['last_sender'] = data.get('last_sender', '')
        return cls(**data)


class MessageBuffer:
    """
    Buffers messages and flushes to chunked raw files.
    
    Usage:
        buffer = MessageBuffer()
        buffer.append_message("Uddipta", "Hello Liz!")
        # Automatically flushes when size limit reached
    """
    
    def __init__(self, 
                 temp_dir: str = "~/.openclaw/extensions/TrueMemoryRecall/temp",
                 raw_dir: str = "~/.openclaw/workspace/memory/raw",
                 context_limit: int = DEFAULT_CONTEXT_LIMIT):
        """
        Initialize message buffer.
        
        Args:
            temp_dir: Directory for temporary buffer files
            raw_dir: Final destination for raw conversation files
            context_limit: Character limit before flush (~70% of LLM context)
        """
        self.temp_dir = Path(temp_dir).expanduser()
        self.raw_dir = Path(raw_dir).expanduser()
        self.context_limit = context_limit
        
        # Ensure directories exist
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        
        # State tracking
        self.state_file = self.temp_dir / "buffer_state.json"
        self.current_buffer_file: Optional[Path] = None
        self.current_sequence = 1
        self.current_char_count = 0
        
        # Load or initialize state
        self._load_state()
        
        # Ensure buffer file exists
        self._ensure_buffer_file()
    
    def _load_state(self):
        """Load buffer state from disk"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.current_buffer_file = Path(state['current_file'])
                self.current_sequence = state['sequence_number']
                self.current_char_count = state['char_count']
                self.last_flush = datetime.fromisoformat(state['last_flush'])
                self.last_message_time = datetime.fromisoformat(state.get('last_message_time', state['last_flush']))
                self.last_sender = state.get('last_sender', '')
            except Exception as e:
                self._init_new_state()
        else:
            self._init_new_state()
    
    def _init_new_state(self):
        """Initialize fresh state"""
        today = datetime.now()
        self.current_sequence = self._get_next_sequence(today)
        self.current_buffer_file = self._get_buffer_path(today, self.current_sequence)
        self.current_char_count = 0
        now = datetime.now()
        self.last_flush = now
        self.last_message_time = now
        self.last_sender = ''
        self._save_state()
    
    def _get_next_sequence(self, date: datetime) -> int:
        """Get next sequence number for today"""
        date_prefix = date.strftime("%Y-%m-%d")
        
        # Check both temp and raw directories
        existing_sequences = []
        
        # Check temp files
        for f in self.temp_dir.glob(f"{date_prefix} (*.md"):
            match = re.search(r'\((\d+)\)', f.name)
            if match:
                existing_sequences.append(int(match.group(1)))
        
        # Check raw files
        for f in self.raw_dir.glob(f"{date_prefix} (*.md"):
            match = re.search(r'\((\d+)\)', f.name)
            if match:
                existing_sequences.append(int(match.group(1)))
        
        if existing_sequences:
            return max(existing_sequences) + 1
        return 1
    
    def _get_buffer_path(self, date: datetime, sequence: int) -> Path:
        """Get buffer file path"""
        filename = f"{date.strftime('%Y-%m-%d')} ({sequence:02d}).md"
        return self.temp_dir / filename
    
    def _get_raw_path(self, date: datetime, sequence: int) -> Path:
        """Get final raw file path"""
        filename = f"{date.strftime('%Y-%m-%d')} ({sequence:02d}).md"
        return self.raw_dir / filename
    
    def _save_state(self):
        """Save buffer state to disk"""
        state = {
            'current_file': str(self.current_buffer_file),
            'sequence_number': self.current_sequence,
            'char_count': self.current_char_count,
            'last_flush': self.last_flush.isoformat(),
            'last_message_time': getattr(self, 'last_message_time', datetime.now()).isoformat(),
            'last_sender': getattr(self, 'last_sender', '')
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _ensure_buffer_file(self):
        """Ensure current buffer file exists with header"""
        if not self.current_buffer_file.exists():
            today = datetime.now()
            header = f"""# Conversation Log - {today.strftime('%Y-%m-%d')}

**Session:** {self.current_sequence:02d}  
**Started:** {today.strftime('%Y-%m-%d %H:%M')} IST

---

"""
            with open(self.current_buffer_file, 'w') as f:
                f.write(header)
            self.current_char_count = len(header)
    
    def append_message(self, sender: str, message: str,
                      timestamp: Optional[datetime] = None,
                      max_gap_minutes: int = 60) -> bool:
        """
        Append a message to the buffer.

        Auto-flush triggers:
        1. Size: Buffer reaches context_limit
        2. Time gap: > max_gap_minutes since last message
        3. Session change: Different sender than last message

        Args:
            sender: Who sent the message ("Uddipta" or "Liz")
            message: Message content
            timestamp: Optional timestamp (defaults to now)
            max_gap_minutes: Max time gap before flush (default 60 min)

        Returns:
            True if buffer was flushed during this append
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Initialize tracking if first message
        if not hasattr(self, 'last_message_time'):
            self.last_message_time = timestamp
            self.last_sender = sender

        # Check condition 2: Time gap > max_gap_minutes
        time_gap = timestamp - self.last_message_time
        if time_gap > timedelta(minutes=max_gap_minutes):
            print(f"[MessageBuffer] Time gap detected ({time_gap.total_seconds()/60:.0f} min), flushing...")
            self.flush()
            flushed_due_to_time = True
        else:
            flushed_due_to_time = False

        # Check condition 3: Session change (different sender)
        if self.last_sender and self.last_sender != sender:
            print(f"[MessageBuffer] Session change ({self.last_sender} → {sender}), flushing...")
            self.flush()
            flushed_due_to_session = True
        else:
            flushed_due_to_session = False

        # Format message
        formatted = f"**[{timestamp.strftime('%H:%M:%S')}] {sender}:** {message}\n\n"
        message_len = len(formatted)

        # Check condition 1: Size limit
        if self.current_char_count + message_len > self.context_limit:
            # Flush current buffer and start new one
            self.flush()
            flushed_due_to_size = True
        else:
            flushed_due_to_size = False

        # Append to buffer
        with open(self.current_buffer_file, 'a') as f:
            f.write(formatted)

        # Update tracking
        self.current_char_count += message_len
        self.last_message_time = timestamp
        self.last_sender = sender
        self._save_state()

        return flushed_due_to_time or flushed_due_to_session or flushed_due_to_size
    
    def flush(self) -> Optional[Path]:
        """
        Flush current buffer to raw directory.
        
        Returns:
            Path to flushed file, or None if nothing to flush
        """
        if not self.current_buffer_file.exists():
            return None
        
        # Check if file has content beyond header
        with open(self.current_buffer_file, 'r') as f:
            content = f.read()
        
        if len(content) < 200:  # Just header, no messages
            return None
        
        # Move to raw directory
        raw_path = self._get_raw_path(datetime.now(), self.current_sequence)
        
        # Add footer
        footer = f"""
---

**Session End:** {datetime.now().strftime('%Y-%m-%d %H:%M')} IST  
**Total Messages:** ~{content.count('**:')}
"""
        with open(self.current_buffer_file, 'a') as f:
            f.write(footer)
        
        # Move file
        self.current_buffer_file.rename(raw_path)
        
        print(f"[MessageBuffer] Flushed to: {raw_path}")
        
        # Update hash tracking
        self._update_hash_tracking(raw_path)
        
        # Start new buffer
        self.current_sequence += 1
        self.current_char_count = 0
        self.current_buffer_file = self._get_buffer_path(datetime.now(), self.current_sequence)
        self._ensure_buffer_file()
        self._save_state()
        
        return raw_path
    
    def _update_hash_tracking(self, raw_path: Path):
        """Update hash tracking for new file"""
        # Calculate hash
        with open(raw_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Update hash tracking file
        hash_file = self.raw_dir / ".hashes.json"
        
        hashes = {}
        if hash_file.exists():
            try:
                with open(hash_file, 'r') as f:
                    hashes = json.load(f)
            except:
                pass
        
        relative_path = raw_path.name
        hashes[relative_path] = {
            'hash': file_hash,
            'processed': False,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(hash_file, 'w') as f:
            json.dump(hashes, f, indent=2)
        
        print(f"[MessageBuffer] Hash tracking updated for {relative_path}")
    
    def time_based_flush(self, max_age_hours: int = 2) -> Optional[Path]:
        """
        Flush if buffer is older than max_age_hours.
        Call this from cron job.
        
        Args:
            max_age_hours: Maximum age before flush
            
        Returns:
            Path if flushed, None otherwise
        """
        age = datetime.now() - self.last_flush
        if age > timedelta(hours=max_age_hours):
            return self.flush()
        return None
    
    def get_stats(self) -> Dict:
        """Get buffer statistics"""
        now = datetime.now()
        time_since_message = now - getattr(self, 'last_message_time', now)
        
        return {
            'current_file': str(self.current_buffer_file),
            'sequence': self.current_sequence,
            'char_count': self.current_char_count,
            'char_limit': self.context_limit,
            'utilization': self.current_char_count / self.context_limit,
            'last_flush': self.last_flush.isoformat(),
            'time_since_flush_hours': (now - self.last_flush).total_seconds() / 3600,
            'last_message_time': getattr(self, 'last_message_time', now).isoformat(),
            'time_since_message_minutes': time_since_message.total_seconds() / 60,
            'last_sender': getattr(self, 'last_sender', ''),
            'will_flush_on_next': time_since_message > timedelta(minutes=60)
        }
    
    def force_flush(self) -> Optional[Path]:
        """Force flush regardless of size"""
        return self.flush()


# Convenience functions for integration
def get_message_buffer() -> MessageBuffer:
    """Get singleton message buffer instance"""
    # Simple singleton pattern
    if not hasattr(get_message_buffer, '_instance'):
        get_message_buffer._instance = MessageBuffer()
    return get_message_buffer._instance


def buffer_message(sender: str, message: str) -> bool:
    """
    Buffer a message (convenience function).
    
    Returns True if buffer was flushed.
    """
    buffer = get_message_buffer()
    return buffer.append_message(sender, message)


def flush_buffer() -> Optional[Path]:
    """Force flush buffer (convenience function)"""
    buffer = get_message_buffer()
    return buffer.force_flush()


if __name__ == "__main__":
    # Test
    print("Testing MessageBuffer...")
    
    buffer = MessageBuffer(context_limit=1000)  # Small limit for testing
    
    # Add some messages
    for i in range(10):
        flushed = buffer.append_message("Uddipta", f"Test message {i} " * 50)
        if flushed:
            print(f"Buffer flushed after message {i}")
    
    # Show stats
    stats = buffer.get_stats()
    print(f"\nBuffer stats:")
    print(f"  Utilization: {stats['utilization']:.1%}")
    print(f"  Sequence: {stats['sequence']}")
    
    # Force flush
    result = buffer.force_flush()
    if result:
        print(f"\nForce flushed to: {result}")
    
    print("\n✅ MessageBuffer test complete!")
