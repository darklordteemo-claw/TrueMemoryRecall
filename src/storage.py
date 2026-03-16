#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Storage Module
Handles daily file storage and line tracking
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


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
            date = datetime.now()
        filename = date.strftime("%Y-%m-%d.md")
        return self.raw_dir / filename
    
    def _open_file_if_needed(self):
        """Open today's file if not already open"""
        today = datetime.now().date()
        
        if self.current_date != today or self.current_file is None:
            # Close previous file if open
            if self.current_file:
                self.current_file.close()
            
            # Open new file
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
                # First close the file we just opened for append, then read
                self.current_file.close()
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.line_count = len(f.readlines())
                # Reopen for append
                self.current_file = open(file_path, 'a', encoding='utf-8')
    
    def store_message(self, timestamp: str, speaker: str, message: str) -> Tuple[int, int]:
        """
        Store a message and return line numbers.
        
        Returns:
            (line_start, line_end)
        """
        self._open_file_if_needed()
        
        line_start = self.line_count + 1
        formatted = f"[{timestamp}] {speaker}: {message}\n"
        
        self.current_file.write(formatted)
        self.current_file.flush()  # Ensure written to disk
        
        line_end = line_start  # Each message is one line
        self.line_count = line_end
        
        return line_start, line_end
    
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
        line1_start, line1_end = storage.store_message("14:32:15", "User", "im thinking about the memory system")
        line2_start, line2_end = storage.store_message("14:33:22", "Liz", "yeah what aspect are you considering")
        line3_start, line3_end = storage.store_message("14:35:47", "User", "how do we make it cheaper")
        
        print(f"  Message 1: lines {line1_start}-{line1_end}")
        print(f"  Message 2: lines {line2_start}-{line2_end}")
        print(f"  Message 3: lines {line3_start}-{line3_end}")
        
        # Test 2: Verify file content
        print("\nTest 2: Verifying file content...")
        today = datetime.now().strftime("%Y-%m-%d")
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
        
        # Debug: Check file content before reopening
        file_path = Path(temp_dir) / f"{today}.md"
        with open(file_path, 'r') as f:
            lines_before = len(f.readlines())
        storage2 = DailyStorage(temp_dir)
        line4_start, _ = storage2.store_message("14:36:00", "Liz", "lets explore some options")
        print(f"  New message appended at line {line4_start}")
        print(f"  ✅ Persistence working" if line4_start == 7 else "  ❌ Persistence failed")
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


if __name__ == "__main__":
    success = test_storage()
    exit(0 if success else 1)
