#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Storage Module
Handles daily file storage and line tracking
"""

import os
import json
import fcntl
import pytz
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from threading import Lock

# IST timezone for all timestamps
IST = pytz.timezone('Asia/Kolkata')

# Global thread lock for line counting across instances in same process
_line_count_lock = Lock()


class DailyStorage:
    """Manages daily conversation files with line-level tracking"""
    
    def __init__(self, raw_dir: str):
        self.raw_dir = Path(raw_dir).expanduser()
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.current_date = None
        self.current_file = None
        self.line_count = 0
    
    def _get_daily_file_path(self, date: Optional[datetime] = None) -> Path:
        """Get the file path for a given date (default: today)"""
        if date is None:
            date = datetime.now(IST)
        filename = date.strftime("%Y-%m-%d.md")
        return self.raw_dir / filename
    
    def _open_file_if_needed(self):
        """Open today's file if not already open (for backward compatibility)"""
        today = datetime.now(IST).date()
        
        if self.current_date != today or self.current_file is None:
            # Close previous file if open
            if self.current_file:
                self.current_file.close()
            
            file_path = self._get_daily_file_path()
            file_exists = file_path.exists()
            
            self.current_file = open(file_path, 'a', encoding='utf-8')
            self.current_date = today
            
            # Write header if new file
            if not file_exists:
                self.current_file.write(f"# {today} — Auto-generated\n")
                self.current_file.write("# Line numbers for reference\n\n")
                self.line_count = 3  # Header takes 3 lines
            else:
                # Count existing lines
                self.current_file.close()
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.line_count = len(f.readlines())
                self.current_file = open(file_path, 'a', encoding='utf-8')
    
    def store_message(self, timestamp: str, speaker: str, message: str) -> Tuple[int, int, int]:
        """
        Store a message and return line numbers and byte offset.
        Thread-safe across multiple storage instances.
        
        Returns:
            (line_start, line_end, byte_offset)
        """
        # Use global thread lock + file lock for true atomicity
        file_path = self._get_daily_file_path()
        lock_file_path = file_path.with_suffix('.lock')
        
        with _line_count_lock:
            lock_fd = os.open(str(lock_file_path), os.O_RDWR | os.O_CREAT)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                
                # Re-read line count while holding lock to get latest
                if file_path.exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        current_line_count = len(f.readlines())
                else:
                    current_line_count = 0
                
                # Open file for append (no need to re-read)
                with open(file_path, 'a', encoding='utf-8') as f:
                    line_start = current_line_count + 1
                    formatted = f"[{timestamp}] {speaker}: {message}\n"
                    
                    # Get byte offset before writing
                    byte_offset = f.tell()
                    
                    f.write(formatted)
                    f.flush()
                    
                    line_end = line_start
                
                # Update instance state if this is our current file
                today = datetime.now(IST).date()
                if self.current_date == today and self.current_file:
                    self.line_count = line_end
                
                return line_start, line_end, byte_offset
                
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
    
    def close(self):
        """Close current file"""
        if self.current_file:
            self.current_file.close()
            self.current_file = None


def test_storage():
    """Test the storage module"""
    import tempfile
    import shutil
    
    print("="*60)
    print("TESTING: Daily Storage")
    print("="*60)
    
    # Create temp directory for testing
    temp_dir = tempfile.mkdtemp()
    
    try:
        storage = DailyStorage(temp_dir)
        
        # Test 1: Store messages
        print("\nTest 1: Storing messages...")
        line1_start, line1_end, offset1 = storage.store_message("14:32:15", "User", "im thinking about the memory system")
        line2_start, line2_end, offset2 = storage.store_message("14:33:22", "Liz", "yeah what aspect are you considering")
        line3_start, line3_end, offset3 = storage.store_message("14:35:47", "User", "how do we make it cheaper")
        
        print(f"  Message 1: lines {line1_start}-{line1_end}, offset {offset1}")
        print(f"  Message 2: lines {line2_start}-{line2_end}, offset {offset2}")
        print(f"  Message 3: lines {line3_start}-{line3_end}, offset {offset3}")
        
        # Verify offsets are increasing
        assert offset1 < offset2 < offset3, "Byte offsets should increase"
        print(f"  ✅ Byte offsets correctly tracked and increasing")
        
        # Test 2: Verify file content
        print("\nTest 2: Verifying file content...")
        today = datetime.now(IST).strftime("%Y-%m-%d")
        file_path = Path(temp_dir) / f"{today}.md"
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        print(f"  File created: {file_path.exists()}")
        print(f"  Content preview:")
        for i, line in enumerate(content.split('\n')[:6], 1):
            print(f"    Line {i}: {line[:60]}{'...' if len(line) > 60 else ''}")
        
        # Test 3: Check line numbers
        print("\nTest 3: Checking line numbers...")
        lines = content.split('\n')
        
        checks = [
            (line1_start, "[14:32:15] User: im thinking about the memory system"),
            (line2_start, "[14:33:22] Liz: yeah what aspect are you considering"),
            (line3_start, "[14:35:47] User: how do we make it cheaper"),
        ]
        
        all_passed = True
        for expected_line, expected_content in checks:
            if expected_line <= len(lines):
                actual = lines[expected_line - 1].strip()
                passed = expected_content in actual
                status = "✅" if passed else "❌"
                print(f"  {status} Line {expected_line}: {actual[:50]}...")
                if not passed:
                    all_passed = False
            else:
                print(f"  ❌ Line {expected_line} does not exist (file has {len(lines)} lines)")
                all_passed = False
        
        # Test 4: File persists across storage instances
        print("\nTest 4: Persistence test...")
        storage.close()
        
        storage2 = DailyStorage(temp_dir)
        line4_start, line4_end, offset4 = storage2.store_message("14:36:00", "Liz", "lets explore some options")
        print(f"  New message appended at line {line4_start}, offset {offset4}")
        # After 3 messages, the 4th should be at line 4 (no header in this test)
        print(f"  ✅ Persistence working" if line4_start == 4 else f"  ❌ Persistence failed (expected line 4, got {line4_start})")
        storage2.close()
        
        print("\n" + "="*60)
        if all_passed:
            print("RESULTS: All tests passed ✅")
        else:
            print("RESULTS: Some tests failed ❌")
        print("="*60)
        
        return all_passed
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_concurrent_writes():
    """Test concurrent writes to verify race condition fix"""
    import tempfile
    import shutil
    import threading
    import time
    
    print("\n" + "="*60)
    print("TESTING: Concurrent Writes (Race Condition)")
    print("="*60)
    
    temp_dir = tempfile.mkdtemp()
    errors = []
    stored_messages = []
    lock = threading.Lock()
    
    def writer(storage_id, message_prefix, count):
        try:
            storage = DailyStorage(temp_dir)
            for i in range(count):
                timestamp = f"14:{30+i:02d}:00"
                msg = f"{message_prefix} message {i}"
                speaker = "User" if storage_id == 0 else "Liz"
                line_start, line_end, offset = storage.store_message(timestamp, speaker, msg)
                with lock:
                    stored_messages.append((storage_id, i, line_start, offset, msg))
                time.sleep(0.01)  # Small delay to increase contention
            storage.close()
        except Exception as e:
            with lock:
                errors.append(f"Writer {storage_id}: {e}")
    
    try:
        # Launch multiple concurrent writers
        threads = []
        num_writers = 4
        messages_per_writer = 10
        
        for i in range(num_writers):
            t = threading.Thread(target=writer, args=(i, f"Writer{i}", messages_per_writer))
            threads.append(t)
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Check results
        print(f"\n  Writers: {num_writers}, Messages per writer: {messages_per_writer}")
        print(f"  Total messages stored: {len(stored_messages)}")
        print(f"  Errors: {len(errors)}")
        
        if errors:
            for e in errors:
                print(f"    ❌ {e}")
            return False
        
        # Verify line numbers are unique and sequential
        line_numbers = sorted([m[2] for m in stored_messages])
        if len(line_numbers) != len(set(line_numbers)):
            print("  ❌ Duplicate line numbers detected!")
            # Show duplicates
            from collections import Counter
            counts = Counter(line_numbers)
            for line, count in counts.items():
                if count > 1:
                    print(f"      Line {line} appears {count} times")
            return False
        
        # Verify byte offsets are unique
        offsets = [m[3] for m in stored_messages]
        if len(offsets) != len(set(offsets)):
            print("  ❌ Duplicate byte offsets detected!")
            return False
        
        # Verify line numbers are sequential (no gaps)
        expected_lines = list(range(min(line_numbers), max(line_numbers) + 1))
        if line_numbers != expected_lines:
            print(f"  ❌ Line numbers not sequential! Missing: {set(expected_lines) - set(line_numbers)}")
            return False
        
        # Verify file integrity
        today = datetime.now(IST).strftime("%Y-%m-%d")
        file_path = Path(temp_dir) / f"{today}.md"
        with open(file_path, 'r') as f:
            content = f.read()
            lines = content.strip().split('\n')
        
        # Should have: 3 header lines + 40 message lines
        expected_content_lines = num_writers * messages_per_writer
        actual_content_lines = len([l for l in lines if l.strip() and not l.startswith('#')])
        
        print(f"  Expected {expected_content_lines} content lines, found {actual_content_lines}")
        
        if actual_content_lines == expected_content_lines:
            print("  ✅ File integrity verified")
        else:
            print("  ❌ File integrity check failed")
            return False
        
        print("\n  ✅ Concurrent write test passed - no race conditions detected")
        return True
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    success1 = test_storage()
    success2 = test_concurrent_writes()
    exit(0 if (success1 and success2) else 1)
