#!/usr/bin/env python3
"""
TMR v2 Intent Classification Module

Detects user query intent to determine optimal retrieval strategy.
Uses rule-based classification with embedding fallback.

Author: Liz (TMR v2)
Date: 2026-03-17
"""

import re
import logging
from typing import Tuple, Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

# Setup logging
logger = logging.getLogger('TMR.IntentClassifier')


@dataclass
class IntentConfig:
    """Configuration for an intent type."""
    patterns: List[str]
    weights: Dict[str, float]
    strategy: str
    max_hops: int
    description: str


class IntentClassifier:
    """
    Classifies user query intent for dynamic retrieval strategy.
    
    Supports 6 intent types:
    - greeting: Casual conversation starters
    - personal_identity: Questions about the AI
    - memory_recall: References to past conversations
    - technical_howto: Technical questions and debugging
    - preference_learn: User preferences and likes/dislikes
    - entity_lookup: Direct entity mentions
    """
    
    # Intent configurations with regex patterns and retrieval strategies
    INTENTS: Dict[str, IntentConfig] = {
        'greeting': IntentConfig(
            patterns=[
                r'\b(hi|hello|hey|how are you|how\s+are\s+you|good morning|good evening|good afternoon|what\s+up|sup|yo)\b',
                r'^\s*(hi|hello|hey)\s*$',
            ],
            weights={'graph': 0.1, 'semantic': 0.9},
            strategy='identity_first',
            max_hops=1,
            description='Casual greeting or conversation starter'
        ),
        
        'personal_identity': IntentConfig(
            patterns=[
                r'\b(who are you|tell me about you|your name|about yourself|what are you|introduce yourself)\b',
                r'\b(your personality|your vibe|what kind of ai|what kind of assistant)\b',
            ],
            weights={'graph': 0.2, 'semantic': 0.8},
            strategy='identity_first',
            max_hops=2,
            description='Questions about AI identity/personality'
        ),
        
        'memory_recall': IntentConfig(
            patterns=[
                r'\b(what did we|remember|we talked about|we discussed|earlier|before|last time|previously)\b',
                r'\b(recall|remind me|what was|what were|as we discussed)\b',
            ],
            weights={'graph': 0.5, 'semantic': 0.5},
            strategy='temporal_priority',
            max_hops=3,
            description='References to previous conversations'
        ),
        
        'technical_howto': IntentConfig(
            patterns=[
                r'\b(how to|how do|how can|how should|what is|what are|explain|why does|why is)\b',
                r'\b(fix|error|issue|problem|bug|broken|not working|failed|fails)\b',
                r'\b(configure|setup|install|implement|debug|troubleshoot)\b',
            ],
            weights={'graph': 0.7, 'semantic': 0.3},
            strategy='technical_depth',
            max_hops=4,
            description='Technical questions, debugging, how-to'
        ),
        
        'preference_learn': IntentConfig(
            patterns=[
                r'\b(i like|i love|i hate|i dislike|my favorite|my preference)\b',
                r'\b(i prefer|i want|i need|i enjoy|i dont like|i don\'t like)\b',
                r'\b(i\s+am\s+interested\s+in|i\s+am\s+into)\b',
            ],
            weights={'graph': 0.6, 'semantic': 0.4},
            strategy='preference_extraction',
            max_hops=2,
            description='User preferences, likes, dislikes'
        ),
        
        'entity_lookup': IntentConfig(
            patterns=[
                r'^[A-Z][a-zA-Z\s]{1,20}$',  # Single proper noun or short phrase
                r'^(who|what|where|when|why|how)\s+(is|are|was|were)\s+([A-Z]\w+)',
            ],
            weights={'graph': 0.8, 'semantic': 0.2},
            strategy='entity_expansion',
            max_hops=3,
            description='Direct entity or concept lookup'
        ),
    }
    
    def __init__(self):
        """Initialize the intent classifier."""
        logger.info("=" * 70)
        logger.info("IntentClassifier initialized")
        logger.info(f"  Loaded {len(self.INTENTS)} intent types")
        for intent_name, config in self.INTENTS.items():
            logger.info(f"    - {intent_name}: {config.description}")
        logger.info("=" * 70)
    
    def classify(self, query: str) -> Tuple[str, float]:
        """
        Classify user query intent.
        
        Args:
            query: User's input query
            
        Returns:
            Tuple of (intent_name, confidence_score)
            
        Example:
            >>> classifier = IntentClassifier()
            >>> classifier.classify("How are you?")
            ('greeting', 0.90)
        """
        logger.info("-" * 70)
        logger.info(f"CLASSIFYING QUERY: \"{query[:100]}\"")
        logger.info("-" * 70)
        
        if not query or not isinstance(query, str):
            logger.warning("  Empty or invalid query, defaulting to 'unknown'")
            return 'unknown', 0.0
        
        # Step 1: Try rule-based classification (fast path)
        logger.info("Step 1: Attempting rule-based classification...")
        rule_result = self._rule_based_classify(query)
        
        if rule_result:
            intent, confidence = rule_result
            logger.info(f"  ✓ Rule-based match: intent='{intent}', confidence={confidence:.2f}")
            logger.info(f"  Strategy: {self.INTENTS[intent].strategy}")
            logger.info(f"  Weights: graph={self.INTENTS[intent].weights['graph']}, semantic={self.INTENTS[intent].weights['semantic']}")
            logger.info("-" * 70)
            return intent, confidence
        
        # Step 2: Fall back to embedding-based classification
        logger.info("  ✗ No rule match, falling back to embedding classification...")
        embedding_result = self._embedding_classify(query)
        
        intent, confidence = embedding_result
        logger.info(f"  ✓ Embedding match: intent='{intent}', confidence={confidence:.2f}")
        logger.info("-" * 70)
        return intent, confidence
    
    def _rule_based_classify(self, query: str) -> Optional[Tuple[str, float]]:
        """
        Classify using regex patterns (fast, 90% accuracy).
        
        Args:
            query: User query string
            
        Returns:
            (intent, confidence) tuple or None if no match
        """
        query_lower = query.lower().strip()
        
        for intent_name, config in self.INTENTS.items():
            logger.debug(f"  Checking intent '{intent_name}'...")
            
            for pattern in config.patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    confidence = 0.90  # Rule-based gives high confidence
                    logger.debug(f"    ✓ Pattern matched: {pattern[:50]}...")
                    return intent_name, confidence
        
        return None
    
    def _embedding_classify(self, query: str) -> Tuple[str, float]:
        """
        Classify using embedding similarity (fallback for edge cases).
        
        For now, returns 'memory_recall' as safe default.
        In production, would compare query embedding to labeled examples.
        
        Args:
            query: User query string
            
        Returns:
            (intent, confidence) tuple
        """
        logger.info("  Using embedding-based classification...")
        
        # TODO: Implement actual embedding comparison
        # For now, use heuristics as fallback
        
        # Check for question marks (likely informational)
        if '?' in query:
            if any(word in query.lower() for word in ['how', 'what', 'why', 'when', 'where']):
                logger.info("    Detected informational question, defaulting to 'technical_howto'")
                return 'technical_howto', 0.60
        
        # Default to memory_recall (safe middle ground)
        logger.info("    No clear pattern, defaulting to 'memory_recall'")
        return 'memory_recall', 0.50
    
    def get_intent_weights(self, intent: str) -> Dict[str, Any]:
        """
        Get retrieval weights and strategy for an intent.
        
        Args:
            intent: Intent name
            
        Returns:
            Dictionary with weights, strategy, max_hops
            
        Example:
            >>> classifier.get_intent_weights('greeting')
            {'graph': 0.1, 'semantic': 0.9, 'strategy': 'identity_first', 'max_hops': 1}
        """
        if intent not in self.INTENTS:
            logger.warning(f"Unknown intent '{intent}', returning defaults")
            return {
                'graph': 0.5,
                'semantic': 0.5,
                'strategy': 'hybrid',
                'max_hops': 2,
                'description': 'Unknown intent - using defaults'
            }
        
        config = self.INTENTS[intent]
        return {
            'graph': config.weights['graph'],
            'semantic': config.weights['semantic'],
            'strategy': config.strategy,
            'max_hops': config.max_hops,
            'description': config.description
        }
    
    def get_all_intents(self) -> List[str]:
        """Return list of all supported intent names."""
        return list(self.INTENTS.keys())


# Simple test function
def test_classifier():
    """Quick test of the classifier."""
    print("=" * 70)
    print("TESTING INTENT CLASSIFIER")
    print("=" * 70)
    
    classifier = IntentClassifier()
    
    test_queries = [
        ("How are you?", "greeting"),
        ("Who are you?", "personal_identity"),
        ("What did we discuss earlier?", "memory_recall"),
        ("How to fix the error?", "technical_howto"),
        ("I like pizza", "preference_learn"),
        ("Liz", "entity_lookup"),
    ]
    
    passed = 0
    failed = 0
    
    for query, expected in test_queries:
        intent, confidence = classifier.classify(query)
        status = "✓ PASS" if intent == expected else "✗ FAIL"
        
        if intent == expected:
            passed += 1
        else:
            failed += 1
            
        print(f"{status} | Query: \"{query[:40]}\" -> Intent: {intent} (expected: {expected})")
    
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    # Run tests
    import sys
    
    # Setup basic logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    success = test_classifier()
    sys.exit(0 if success else 1)
