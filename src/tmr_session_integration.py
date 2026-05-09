#!/usr/bin/env python3
"""
TMR v2 - Session Integration Module

Integrates TMR memory injection with OpenClaw main session.
Shows injected memories above user messages (like Mem0).
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Import TMR components
try:
    from .tmr_injector import TMRCogneeInjector
    from .config_loader import get_config
except ImportError:
    from tmr_injector import TMRCogneeInjector
    from config_loader import get_config


class TMRSessionLogger:
    """
    Detailed logger for TMR operations.
    
    Logs to both console and file with structured format.
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        """Initialize TMR logger"""
        if log_dir is None:
            config = get_config()
            log_dir = config.storage.get('feedback_dir', '~/.openclaw/workspace/memory/feedback')
        
        self.log_dir = Path(log_dir).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_file = self.log_dir / "tmr_detailed.log"
        
        # Setup file logger
        self.logger = logging.getLogger('TMR.Session')
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers = []
        
        # File handler with detailed format
        file_handler = logging.FileHandler(self.log_file, mode='a')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Console handler for visibility
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '[TMR] %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def log_user_message(self, user: str, message: str, session_id: Optional[str] = None):
        """Log incoming user message"""
        self.logger.info("=" * 80)
        self.logger.info("NEW USER MESSAGE")
        self.logger.info("=" * 80)
        self.logger.info(f"User: {user}")
        self.logger.info(f"Session: {session_id or 'N/A'}")
        self.logger.info(f"Timestamp: {datetime.now().isoformat()}")
        self.logger.info(f"Message: {message}")
        self.logger.info("-" * 80)
    
    def log_intent_classification(self, intent: str, confidence: float, patterns_matched: list):
        """Log intent classification results"""
        self.logger.info("[Phase 1] INTENT CLASSIFICATION")
        self.logger.info(f"  Detected Intent: {intent}")
        self.logger.info(f"  Confidence: {confidence:.2f}")
        self.logger.info(f"  Patterns Matched: {patterns_matched}")
    
    def log_query_plan(self, strategy: str, weights: Dict[str, float], max_hops: int):
        """Log query planning"""
        self.logger.info("[Phase 2] QUERY PLANNING")
        self.logger.info(f"  Strategy: {strategy}")
        self.logger.info(f"  Weights: graph={weights.get('graph', 0.4):.2f}, semantic={weights.get('semantic', 0.6):.2f}")
        self.logger.info(f"  Max Hops: {max_hops}")
    
    def log_memory_retrieved(self, index: int, memory: Dict[str, Any]):
        """Log a single retrieved memory"""
        subject = memory.get('subject', 'Unknown')
        relation = memory.get('relation', 'RELATED_TO')
        obj = memory.get('object', 'Unknown')
        strength = memory.get('strength', 0.0)
        evidence = memory.get('evidence', '')
        source = memory.get('source', {})
        
        # Format source
        if isinstance(source, dict):
            source_file = source.get('file', 'unknown')
            line_start = source.get('line_start', 0)
        else:
            source_file = str(source) if source else 'unknown'
            line_start = 0
        
        self.logger.info(f"  [{index}] {subject} → {relation} → {obj}")
        self.logger.info(f"      Confidence: {strength:.1%}")
        self.logger.info(f"      Evidence: \"{evidence[:100]}{'...' if len(evidence) > 100 else ''}\"")
        self.logger.info(f"      Source: {source_file}:{line_start}")
        self.logger.info(f"      Search Method: {memory.get('search_method', 'unknown')}")
        self.logger.info(f"      Hybrid Score: {memory.get('hybrid_score', 0):.3f}")
        
        if 'feedback_boost' in memory:
            self.logger.info(f"      Feedback Boost: {memory['feedback_boost']:.2f}")
        if 'path_hops' in memory:
            self.logger.info(f"      Path Hops: {memory['path_hops']}")
    
    def log_retrieval_summary(self, total_memories: int, final_count: int, processing_time_ms: float):
        """Log retrieval summary"""
        self.logger.info("-" * 80)
        self.logger.info("RETRIEVAL SUMMARY")
        self.logger.info(f"  Total Retrieved: {total_memories}")
        self.logger.info(f"  Final Selected: {final_count}")
        self.logger.info(f"  Processing Time: {processing_time_ms:.2f}ms")
        self.logger.info("=" * 80)
    
    def log_error(self, error: Exception, context: str = ""):
        """Log error with context"""
        self.logger.error("=" * 80)
        self.logger.error("TMR ERROR")
        self.logger.error(f"Context: {context}")
        self.logger.error(f"Error: {str(error)}")
        import traceback
        self.logger.error(traceback.format_exc())
        self.logger.error("=" * 80)


class TMRSessionIntegration:
    """
    Main integration class for OpenClaw session.
    
    Usage:
        tmr = TMRSessionIntegration()
        context = tmr.process_user_message("Uddipta", "Hello Liz!")
        # context contains formatted memories to show above message
    """
    
    def __init__(self):
        """Initialize TMR session integration"""
        self.logger = TMRSessionLogger()
        self.injector = TMRCogneeInjector(enable_feedback=True)
        self.config = get_config()
        
        self.logger.logger.info("TMR Session Integration Initialized")
        self.logger.logger.info(f"Log file: {self.logger.log_file}")
    
    def process_user_message(self, user: str, message: str, 
                           session_id: Optional[str] = None) -> str:
        """
        Process user message and return formatted context.
        
        Args:
            user: Username (e.g., "Uddipta")
            message: User's message
            session_id: Optional session identifier
            
        Returns:
            Formatted context string to show above message
        """
        import time
        start_time = time.time()
        
        try:
            # Log user message
            self.logger.log_user_message(user, message, session_id)
            
            # Classify intent (for logging)
            intent, confidence = self.injector.intent_classifier.classify(message)
            
            # Get weights and strategy
            weights = self.config.get_intent_weights(intent)
            strategy_map = {
                'greeting': 'identity_first',
                'personal_identity': 'identity_first',
                'memory_recall': 'temporal_priority',
                'technical_howto': 'technical_depth',
                'preference_learn': 'preference_extraction',
                'entity_lookup': 'entity_expansion'
            }
            strategy = strategy_map.get(intent, 'hybrid')
            max_hops = self.config.get_intent_max_hops(intent)
            
            # Log planning
            self.logger.log_intent_classification(intent, confidence, [])
            self.logger.log_query_plan(strategy, weights, max_hops)
            
            # Retrieve memories
            self.logger.logger.info("[Phase 3-4] RETRIEVING MEMORIES")
            
            # Get raw results before formatting (for logging)
            entities = self.injector.extract_entities(message)
            self.logger.logger.info(f"  Extracted Entities: {entities}")
            
            # Full injection
            context = self.injector.inject_context(message, session_id)
            
            # Get the actual memories that were selected
            # Re-run search to get details for logging
            graph_weight = weights['graph']
            semantic_weight = weights['semantic']
            
            graphs = self.injector._load_knowledge_graphs()
            graph_results = self.injector._search_graph(entities, graphs)
            semantic_results = self.injector._search_semantic(message)
            merged = self.injector._merge_with_weights(
                graph_results, semantic_results, graph_weight, semantic_weight
            )
            
            # Apply enhancements for logging
            merged = self.injector._apply_source_prioritization(merged, strategy)
            merged = self.injector._apply_diversity_ranking(merged)
            merged = self.injector._apply_recency_boosting(merged)
            
            if self.injector._feedback_loop:
                merged = self.injector._feedback_loop.apply_feedback_ranking(merged)
            
            max_results = self.config.hybrid_search.get('merging', {}).get('max_final_results', 5)
            final_results = merged[:max_results]
            
            # Log each memory
            for i, memory in enumerate(final_results, 1):
                self.logger.log_memory_retrieved(i, memory)
            
            # Log summary
            processing_time = (time.time() - start_time) * 1000
            self.logger.log_retrieval_summary(
                len(merged), 
                len(final_results), 
                processing_time
            )
            
            return context
            
        except Exception as e:
            self.logger.log_error(e, f"Processing message: {message}")
            return ""
    
    def format_for_display(self, context: str) -> str:
        """
        Format context for display above user message.
        
        Returns HTML/markdown formatted string.
        """
        if not context:
            return ""
        
        # Add visual separator for display
        formatted = f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🤖 TMR MEMORIES                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
{context}
└─────────────────────────────────────────────────────────────────────────────┘
"""
        return formatted
    
    def get_stats(self) -> Dict:
        """Get TMR system stats"""
        return {
            'log_file': str(self.logger.log_file),
            'log_file_size_bytes': self.logger.log_file.stat().st_size if self.logger.log_file.exists() else 0,
            'config_loaded': self.config is not None,
            'injector_ready': self.injector is not None,
            'feedback_enabled': self.injector._feedback_loop is not None
        }


# Convenience function for main session integration
def get_tmr_integration() -> TMRSessionIntegration:
    """Get singleton TMR session integration"""
    if not hasattr(get_tmr_integration, '_instance'):
        get_tmr_integration._instance = TMRSessionIntegration()
    return get_tmr_integration._instance


def process_message_with_tmr(user: str, message: str, 
                             session_id: Optional[str] = None,
                             show_memories: bool = True) -> tuple:
    """
    Process message with TMR and return both context and display format.
    
    Args:
        user: Username
        message: Message content
        session_id: Optional session ID
        show_memories: Whether to format memories for display
        
    Returns:
        Tuple of (raw_context, formatted_display)
    """
    tmr = get_tmr_integration()
    context = tmr.process_user_message(user, message, session_id)
    
    if show_memories and context:
        display = tmr.format_for_display(context)
        return context, display
    
    return context, ""


if __name__ == "__main__":
    # Test the integration
    print("Testing TMR Session Integration...")
    print("=" * 80)
    
    tmr = TMRSessionIntegration()
    
    # Test messages
    test_messages = [
        ("Uddipta", "How are you Liz?"),
        ("Uddipta", "What did we discuss about TMR?"),
    ]
    
    for user, message in test_messages:
        print(f"\n>>> {user}: {message}")
        print("-" * 80)
        
        context, display = process_message_with_tmr(user, message, show_memories=True)
        
        if display:
            print(display)
        else:
            print("(No memories found)")
    
    # Show stats
    print("\n" + "=" * 80)
    print("TMR Stats:")
    stats = tmr.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n✅ TMR Session Integration test complete!")
    print(f"Detailed logs: {stats['log_file']}")
