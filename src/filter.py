#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Filter Module
Tests and filters messages before storage
"""

import re
from typing import Tuple, Optional

# Default patterns to drop (can be overridden by config)
DEFAULT_DROP_PATTERNS = [
    r'^hi$',
    r'^ok$',
    r'^okay$',
    r'^yes$',
    r'^no$',
    r'^yep$',
    r'^nah$',
    r'^hm$',
    r'^hmm$',
    r'^umm?$',
    r'^uhh?$',
    r'^hello$',
    r'^hey$',
    r'^yo$',
    r'^hiya$',
    r'^wait$',
    r'^so$',
    r'^like$',
    r'^well$',
    r'^anyway$',
    r'^btw$',
    r'^testing$',
    r'^test$',
]

class MessageFilter:
    """Filters messages based on configurable rules"""
    
    def __init__(self, min_length: int = 10, drop_patterns: list = None):
        self.min_length = min_length
        self.drop_patterns = drop_patterns or DEFAULT_DROP_PATTERNS
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.drop_patterns]
    
    def should_store(self, message: str) -> Tuple[bool, str]:
        """
        Determine if a message should be stored.
        
        Returns:
            (should_store: bool, reason: str)
        """
        # Strip leading/trailing whitespace
        clean = message.strip()
        
        # Check minimum length
        if len(clean) < self.min_length:
            return False, f"too_short ({len(clean)} chars < {self.min_length})"
        
        # Check drop patterns
        for pattern in self.compiled_patterns:
            if pattern.match(clean):
                return False, f"pattern_match ({pattern.pattern})"
        
        return True, "passed"


def test_filter():
    """Test the filter with sample messages"""
    print("="*60)
    print("TESTING: Message Filter")
    print("="*60)
    
    filter_obj = MessageFilter(min_length=10)
    
    test_cases = [
        # (message, expected_should_store, description)
        ("hi", False, "greeting - single word"),
        ("hello", False, "greeting - hello"),
        ("ok", False, "acknowledgment"),
        ("yes", False, "single word yes"),
        ("wait", False, "filler word"),
        ("hmm", False, "filler hmm"),
        ("test", False, "test message"),
        ("short", False, "too short (5 chars)"),
        ("im thinking about the memory system", True, "valid statement"),
        ("what if we use qmd instead?", True, "valid question"),
        ("yeah lets do it", True, "valid response (10 chars)"),
        ("ok sure", False, "too short after drop check"),
        ("what do you think about this approach?", True, "valid question"),
        ("Hi there, how are you?", True, "greeting + content (ok)"),
    ]
    
    passed = 0
    failed = 0
    
    for msg, expected, desc in test_cases:
        result, reason = filter_obj.should_store(msg)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} | {desc}")
        print(f"       Input: \"{msg}\"")
        print(f"       Expected: {expected}, Got: {result} ({reason})")
        print()
    
    print("="*60)
    print(f"RESULTS: {passed}/{len(test_cases)} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = test_filter()
    exit(0 if success else 1)
