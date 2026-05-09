#!/usr/bin/env python3
"""
Unit tests for IntentClassifier

Run with: python3 -m pytest tests/test_intent_classifier.py -v
"""

import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from intent_classifier import IntentClassifier


class TestIntentClassifier(unittest.TestCase):
    """Test suite for IntentClassifier."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.classifier = IntentClassifier()
    
    # ==================== GREETING TESTS ====================
    
    def test_greeting_simple(self):
        """Test simple greeting."""
        intent, confidence = self.classifier.classify("Hi")
        self.assertEqual(intent, 'greeting')
        self.assertGreaterEqual(confidence, 0.9)
    
    def test_greeting_question(self):
        """Test greeting as question."""
        intent, confidence = self.classifier.classify("How are you?")
        self.assertEqual(intent, 'greeting')
        self.assertGreaterEqual(confidence, 0.9)
    
    def test_greeting_morning(self):
        """Test time-based greeting."""
        intent, confidence = self.classifier.classify("Good morning!")
        self.assertEqual(intent, 'greeting')
    
    # ==================== PERSONAL IDENTITY TESTS ====================
    
    def test_who_are_you(self):
        """Test identity question."""
        intent, confidence = self.classifier.classify("Who are you?")
        self.assertEqual(intent, 'personal_identity')
    
    def test_tell_me_about_you(self):
        """Test about request."""
        intent, confidence = self.classifier.classify("Tell me about yourself")
        self.assertEqual(intent, 'personal_identity')
    
    def test_personality_question(self):
        """Test personality question."""
        intent, confidence = self.classifier.classify("What is your personality?")
        self.assertEqual(intent, 'personal_identity')
    
    # ==================== MEMORY RECALL TESTS ====================
    
    def test_what_did_we_discuss(self):
        """Test past conversation reference."""
        intent, confidence = self.classifier.classify("What did we discuss earlier?")
        self.assertEqual(intent, 'memory_recall')
    
    def test_remember_request(self):
        """Test remember request."""
        intent, confidence = self.classifier.classify("Remember when we talked about TMR?")
        self.assertEqual(intent, 'memory_recall')
    
    def test_recall_request(self):
        """Test recall request."""
        intent, confidence = self.classifier.classify("Recall what I said before")
        self.assertEqual(intent, 'memory_recall')
    
    # ==================== TECHNICAL HOWTO TESTS ====================
    
    def test_how_to_question(self):
        """Test how-to question."""
        intent, confidence = self.classifier.classify("How to fix the error?")
        self.assertEqual(intent, 'technical_howto')
    
    def test_what_is_question(self):
        """Test what-is question."""
        intent, confidence = self.classifier.classify("What is knowledge graph?")
        self.assertEqual(intent, 'technical_howto')
    
    def test_error_fix(self):
        """Test error fix request."""
        intent, confidence = self.classifier.classify("Fix the connection error")
        self.assertEqual(intent, 'technical_howto')
    
    def test_explain_request(self):
        """Test explain request."""
        intent, confidence = self.classifier.classify("Explain how TMR works")
        self.assertEqual(intent, 'technical_howto')
    
    # ==================== PREFERENCE LEARN TESTS ====================
    
    def test_i_like(self):
        """Test like statement."""
        intent, confidence = self.classifier.classify("I like pizza")
        self.assertEqual(intent, 'preference_learn')
    
    def test_i_hate(self):
        """Test dislike statement."""
        intent, confidence = self.classifier.classify("I hate waiting")
        self.assertEqual(intent, 'preference_learn')
    
    def test_my_favorite(self):
        """Test favorite statement."""
        intent, confidence = self.classifier.classify("My favorite color is blue")
        self.assertEqual(intent, 'preference_learn')
    
    def test_i_prefer(self):
        """Test preference statement."""
        intent, confidence = self.classifier.classify("I prefer tea over coffee")
        self.assertEqual(intent, 'preference_learn')
    
    # ==================== ENTITY LOOKUP TESTS ====================
    
    def test_single_name(self):
        """Test single entity mention."""
        intent, confidence = self.classifier.classify("Liz")
        self.assertEqual(intent, 'entity_lookup')
    
    def test_proper_noun(self):
        """Test proper noun."""
        intent, confidence = self.classifier.classify("Qdrant")
        self.assertEqual(intent, 'entity_lookup')
    
    # ==================== EDGE CASE TESTS ====================
    
    def test_empty_query(self):
        """Test empty query handling."""
        intent, confidence = self.classifier.classify("")
        self.assertEqual(intent, 'unknown')
        self.assertEqual(confidence, 0.0)
    
    def test_get_intent_weights(self):
        """Test weight retrieval."""
        weights = self.classifier.get_intent_weights('greeting')
        self.assertEqual(weights['graph'], 0.1)
        self.assertEqual(weights['semantic'], 0.9)
        self.assertEqual(weights['strategy'], 'identity_first')
    
    def test_get_intent_weights_unknown(self):
        """Test weight retrieval for unknown intent."""
        weights = self.classifier.get_intent_weights('nonexistent')
        self.assertEqual(weights['graph'], 0.5)  # Default
        self.assertEqual(weights['semantic'], 0.5)
    
    def test_get_all_intents(self):
        """Test getting all intent names."""
        intents = self.classifier.get_all_intents()
        self.assertEqual(len(intents), 6)
        self.assertIn('greeting', intents)
        self.assertIn('technical_howto', intents)


if __name__ == '__main__':
    unittest.main()
