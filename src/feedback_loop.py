#!/usr/bin/env python3
"""
TMR Feedback Loop - Cognee-Style Self-Improvement System

Learns from retrieval outcomes to optimize:
- Query → Memory relevance scoring
- Graph vs Semantic weight adaptation  
- Memory ranking based on historical usefulness
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum


class FeedbackSignal(Enum):
    """Types of feedback signals (Cognee-style implicit + explicit)"""
    # Implicit signals (inferred from conversation flow)
    QUERY_ANSWERED = "query_answered"          # Query answered, conversation moved on
    MEMORY_REFERENCED = "memory_referenced"     # Retrieved memory appeared in response
    USER_CORRECTED = "user_corrected"          # User contradicted retrieved info
    QUERY_REPEATED = "query_repeated"          # Same/similar query asked again
    TOPIC_SHIFTED = "topic_shifted"            # Abrupt topic change (irrelevant results)
    
    # Explicit signals (direct user feedback)
    EXPLICIT_POSITIVE = "explicit_positive"     # User thumbs up / confirmed helpful
    EXPLICIT_NEGATIVE = "explicit_negative"     # User thumbs down / said irrelevant


@dataclass
class RetrievalEvent:
    """Records a single retrieval operation with full context"""
    event_id: str
    timestamp: datetime
    query: str
    query_vector: Optional[List[float]]  # Embedded query for similarity analysis
    intent: Optional[str]                 # Detected/predicted intent
    
    # Retrieved memories
    memories_injected: List[Dict]         # What was actually injected into context
    
    # Search parameters used
    graph_weight: float
    semantic_weight: float
    semantic_threshold: float
    max_results: int
    
    # Source tracking
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['query_vector'] = self.query_vector if self.query_vector else []
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RetrievalEvent':
        """Create from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['query_vector'] = data.get('query_vector', []) or None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FeedbackRecord:
    """Links a retrieval event to an outcome signal"""
    feedback_id: str
    event_id: str                      # Links to RetrievalEvent
    signal: FeedbackSignal
    timestamp: datetime
    
    # Context at feedback time
    messages_since_retrieval: int      # How many messages passed
    response_quality_hint: Optional[str] = None  # Optional quality indicator
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['signal'] = self.signal.value
        return data


class MemoryPerformanceTracker:
    """
    Tracks performance metrics for individual memories.
    Cognee-style: Each memory gets a dynamic usefulness score.
    """
    
    def __init__(self, qdrant_manager=None):
        self.qdrant = qdrant_manager
        # Cache of memory performance scores (memory_id -> stats)
        self._performance_cache: Dict[str, Dict] = {}
        self._cache_dirty = False
    
    def record_usage(self, memory_id: str, query: str, was_helpful: bool):
        """Record that a memory was used and whether it helped"""
        if memory_id not in self._performance_cache:
            self._performance_cache[memory_id] = {
                'total_uses': 0,
                'helpful_uses': 0,
                'recent_queries': [],
                'last_used': None
            }
        
        stats = self._performance_cache[memory_id]
        stats['total_uses'] += 1
        if was_helpful:
            stats['helpful_uses'] += 1
        stats['recent_queries'].append({
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'helpful': was_helpful
        })
        # Keep only last 10 queries
        stats['recent_queries'] = stats['recent_queries'][-10:]
        stats['last_used'] = datetime.now().isoformat()
        self._cache_dirty = True
    
    def get_usefulness_score(self, memory_id: str) -> float:
        """
        Calculate usefulness score [0.0, 1.0] for a memory.
        Uses Bayesian-like smoothing to avoid overfitting to few samples.
        """
        stats = self._performance_cache.get(memory_id, {
            'total_uses': 0,
            'helpful_uses': 0
        })
        
        total = stats['total_uses']
        helpful = stats['helpful_uses']
        
        # Bayesian average: (helpful + prior) / (total + prior_strength)
        # Prior: assume 50% helpful with strength of 5 (virtual samples)
        prior_mean = 0.5
        prior_strength = 5
        
        score = (helpful + prior_mean * prior_strength) / (total + prior_strength)
        return min(1.0, max(0.0, score))
    
    def get_relevance_boost(self, memory_id: str) -> float:
        """
        Get boost factor for ranking.
        High-performing memories get boosted, poor ones penalized.
        """
        score = self.get_usefulness_score(memory_id)
        # Map [0, 1] to [0.7, 1.3] (±30% adjustment)
        return 0.7 + (score * 0.6)
    
    def persist(self, feedback_dir: Path):
        """Save performance cache to disk"""
        if not self._cache_dirty:
            return
        
        feedback_dir.mkdir(parents=True, exist_ok=True)
        cache_file = feedback_dir / "memory_performance.json"
        
        with open(cache_file, 'w') as f:
            json.dump(self._performance_cache, f, indent=2)
        
        self._cache_dirty = False
    
    def load(self, feedback_dir: Path):
        """Load performance cache from disk"""
        cache_file = feedback_dir / "memory_performance.json"
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                self._performance_cache = json.load(f)


class WeightOptimizer:
    """
    Dynamically adjusts graph vs semantic weights based on query type performance.
    Cognee-style: Per-intent weight optimization.
    """
    
    def __init__(self):
        # Default weights per intent type
        self._intent_weights: Dict[str, Dict[str, float]] = {
            'default': {'graph': 0.4, 'semantic': 0.6},
            'greeting': {'graph': 0.1, 'semantic': 0.9},
            'personal_identity': {'graph': 0.2, 'semantic': 0.8},
            'memory_recall': {'graph': 0.6, 'semantic': 0.4},
            'technical_howto': {'graph': 0.7, 'semantic': 0.3},
            'preference_learn': {'graph': 0.5, 'semantic': 0.5},
        }
        
        # Track performance per intent
        self._intent_performance: Dict[str, List[bool]] = {}
    
    def get_weights(self, intent: Optional[str] = None) -> Tuple[float, float]:
        """Get graph_weight, semantic_weight for a given intent"""
        weights = self._intent_weights.get(intent or 'default', 
                                           self._intent_weights['default'])
        return weights['graph'], weights['semantic']
    
    def record_outcome(self, intent: Optional[str], graph_results_helpful: bool, 
                       semantic_results_helpful: bool):
        """
        Record which search type provided helpful results.
        Used for gradual weight adjustment.
        """
        intent = intent or 'default'
        
        if intent not in self._intent_performance:
            self._intent_performance[intent] = []
        
        # Record which source was helpful
        if graph_results_helpful and not semantic_results_helpful:
            self._intent_performance[intent].append('graph')
        elif semantic_results_helpful and not graph_results_helpful:
            self._intent_performance[intent].append('semantic')
        elif graph_results_helpful and semantic_results_helpful:
            self._intent_performance[intent].append('both')
        else:
            self._intent_performance[intent].append('neither')
        
        # Keep last 100 outcomes per intent
        self._intent_performance[intent] = self._intent_performance[intent][-100:]
    
    def adapt_weights(self, intent: Optional[str] = None, 
                      learning_rate: float = 0.05):
        """
        Adjust weights based on historical performance.
        Call periodically (e.g., daily) to adapt.
        """
        intent = intent or 'default'
        
        if intent not in self._intent_performance:
            return
        
        outcomes = self._intent_performance[intent]
        if len(outcomes) < 10:  # Need minimum data
            return
        
        # Count helpful outcomes by source
        graph_wins = outcomes.count('graph')
        semantic_wins = outcomes.count('semantic')
        both_wins = outcomes.count('both')
        
        total_decisive = graph_wins + semantic_wins
        if total_decisive < 5:  # Not enough decisive data
            return
        
        # Calculate adjustment
        graph_ratio = graph_wins / total_decisive
        
        current = self._intent_weights[intent]
        if graph_ratio > 0.6:  # Graph performing better
            current['graph'] = min(0.8, current['graph'] + learning_rate)
            current['semantic'] = 1.0 - current['graph']
        elif graph_ratio < 0.4:  # Semantic performing better
            current['semantic'] = min(0.8, current['semantic'] + learning_rate)
            current['graph'] = 1.0 - current['semantic']
        
        self._intent_weights[intent] = current


class CogneeStyleFeedbackLoop:
    """
    Main feedback loop orchestrator.
    Inspired by Cognee's adaptive retrieval with local-first design.
    """
    
    def __init__(self, feedback_dir: str = "~/.openclaw/workspace/memory/feedback",
                 qdrant_manager=None):
        self.feedback_dir = Path(feedback_dir).expanduser()
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        
        self.qdrant = qdrant_manager
        self.performance_tracker = MemoryPerformanceTracker(qdrant_manager)
        self.weight_optimizer = WeightOptimizer()
        
        # Event log (append-only)
        self._event_log_file = self.feedback_dir / "retrieval_events.jsonl"
        self._feedback_log_file = self.feedback_dir / "feedback_records.jsonl"
        
        # In-memory buffers for recent events (for correlation)
        self._recent_events: Dict[str, RetrievalEvent] = {}
        self._event_buffer_duration = timedelta(minutes=30)
        
        # Load persisted state
        self._load_state()
    
    def _load_state(self):
        """Load persisted performance data"""
        self.performance_tracker.load(self.feedback_dir)
        self.weight_optimizer._intent_weights = self._load_json(
            self.feedback_dir / "intent_weights.json",
            default=self.weight_optimizer._intent_weights
        )
        self.weight_optimizer._intent_performance = self._load_json(
            self.feedback_dir / "intent_performance.json",
            default={}
        )
    
    def _load_json(self, path: Path, default: Dict) -> Dict:
        """Load JSON file or return default"""
        if path.exists():
            with open(path, 'r') as f:
                return json.load(f)
        return default
    
    def _save_json(self, path: Path, data: Dict):
        """Save data to JSON file"""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def persist_state(self):
        """Save all state to disk"""
        self.performance_tracker.persist(self.feedback_dir)
        self._save_json(
            self.feedback_dir / "intent_weights.json",
            self.weight_optimizer._intent_weights
        )
        self._save_json(
            self.feedback_dir / "intent_performance.json",
            self.weight_optimizer._intent_performance
        )
    
    def log_retrieval(self, query: str, query_vector: Optional[List[float]],
                      intent: Optional[str], memories_injected: List[Dict],
                      graph_weight: float, semantic_weight: float,
                      semantic_threshold: float, max_results: int,
                      session_id: Optional[str] = None) -> str:
        """
        Log a retrieval event. Call this after every hybrid_search.
        Returns event_id for later feedback correlation.
        """
        event = RetrievalEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            query=query,
            query_vector=query_vector,
            intent=intent,
            memories_injected=memories_injected,
            graph_weight=graph_weight,
            semantic_weight=semantic_weight,
            semantic_threshold=semantic_threshold,
            max_results=max_results,
            session_id=session_id
        )
        
        # Append to log
        with open(self._event_log_file, 'a') as f:
            f.write(json.dumps(event.to_dict()) + '\n')
        
        # Add to recent events buffer
        self._recent_events[event.event_id] = event
        self._cleanup_old_events()
        
        return event.event_id
    
    def _cleanup_old_events(self):
        """Remove events older than buffer duration"""
        cutoff = datetime.now() - self._event_buffer_duration
        old_ids = [
            eid for eid, event in self._recent_events.items()
            if event.timestamp < cutoff
        ]
        for eid in old_ids:
            del self._recent_events[eid]
    
    def record_feedback(self, event_id: str, signal: FeedbackSignal,
                        messages_since: int = 0,
                        quality_hint: Optional[str] = None):
        """
        Record feedback for a retrieval event.
        Call this when a signal is detected (implicit or explicit).
        """
        feedback = FeedbackRecord(
            feedback_id=str(uuid.uuid4()),
            event_id=event_id,
            signal=signal,
            timestamp=datetime.now(),
            messages_since_retrieval=messages_since,
            response_quality_hint=quality_hint
        )
        
        # Append to log
        with open(self._feedback_log_file, 'a') as f:
            f.write(json.dumps(feedback.to_dict()) + '\n')
        
        # Update performance tracker
        event = self._recent_events.get(event_id)
        if event:
            was_helpful = signal in (
                FeedbackSignal.QUERY_ANSWERED,
                FeedbackSignal.MEMORY_REFERENCED,
                FeedbackSignal.EXPLICIT_POSITIVE
            )
            
            for memory in event.memories_injected:
                mem_id = memory.get('id') or self._memory_key(memory)
                self.performance_tracker.record_usage(
                    mem_id, event.query, was_helpful
                )
        
        self.persist_state()
    
    def _memory_key(self, memory: Dict) -> str:
        """Generate a stable key for a memory"""
        # Use subject-relation-object as key if no ID
        subj = memory.get('subject', '')
        rel = memory.get('relation', '')
        obj = memory.get('object', '')
        return f"{subj}:{rel}:{obj}"
    
    def detect_implicit_feedback(self, current_query: str, 
                                 conversation_history: List[Dict]) -> Optional[Tuple[str, FeedbackSignal]]:
        """
        Analyze conversation to detect implicit feedback signals.
        Returns (event_id, signal) if a signal is detected.
        """
        if not conversation_history:
            return None
        
        last_message = conversation_history[-1]
        content = last_message.get('content', '').lower()
        
        # Check for correction patterns
        correction_patterns = [
            r'actually[,\s]+i',
            r'no[,\s]+(that|it)',
            r'(wrong|incorrect)',
            r'i (said|meant)',
            r'not (quite|exactly)',
        ]
        
        for pattern in correction_patterns:
            import re
            if re.search(pattern, content):
                # Find recent retrieval event
                event_id = self._find_related_event(current_query)
                if event_id:
                    return event_id, FeedbackSignal.USER_CORRECTED
        
        # Check for repetition
        if len(conversation_history) >= 2:
            prev_message = conversation_history[-2].get('content', '').lower()
            similarity = self._query_similarity(current_query, prev_message)
            if similarity > 0.8:
                event_id = self._find_related_event(prev_message)
                if event_id:
                    return event_id, FeedbackSignal.QUERY_REPEATED
        
        return None
    
    def _find_related_event(self, query: str) -> Optional[str]:
        """Find a recent retrieval event matching the query"""
        query_lower = query.lower()
        for event_id, event in self._recent_events.items():
            if query_lower in event.query.lower() or event.query.lower() in query_lower:
                return event_id
        return None
    
    def _query_similarity(self, q1: str, q2: str) -> float:
        """Simple Jaccard similarity for quick checks"""
        words1 = set(q1.lower().split())
        words2 = set(q2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)
    
    def get_optimized_weights(self, intent: Optional[str] = None) -> Tuple[float, float]:
        """Get graph and semantic weights optimized for this intent"""
        return self.weight_optimizer.get_weights(intent)
    
    def get_memory_boost(self, memory: Dict) -> float:
        """Get relevance boost for a memory based on historical performance"""
        mem_id = memory.get('id') or self._memory_key(memory)
        return self.performance_tracker.get_relevance_boost(mem_id)
    
    def apply_feedback_ranking(self, results: List[Dict]) -> List[Dict]:
        """
        Re-rank search results using feedback history.
        Call this after hybrid_search, before format_results.
        """
        for result in results:
            boost = self.get_memory_boost(result)
            current_score = result.get('hybrid_score', 0)
            result['hybrid_score'] = current_score * boost
            result['feedback_boost'] = boost
        
        # Re-sort by adjusted score
        results.sort(key=lambda r: r.get('hybrid_score', 0), reverse=True)
        return results
    
    def get_analytics(self, days: int = 7) -> Dict:
        """Get feedback loop analytics for the last N days"""
        cutoff = datetime.now() - timedelta(days=days)
        
        # Count events and feedback
        total_events = 0
        total_feedback = 0
        signal_counts = {s.value: 0 for s in FeedbackSignal}
        
        if self._event_log_file.exists():
            with open(self._event_log_file, 'r') as f:
                for line in f:
                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event['timestamp'])
                    if event_time >= cutoff:
                        total_events += 1
        
        if self._feedback_log_file.exists():
            with open(self._feedback_log_file, 'r') as f:
                for line in f:
                    feedback = json.loads(line)
                    feedback_time = datetime.fromisoformat(feedback['timestamp'])
                    if feedback_time >= cutoff:
                        total_feedback += 1
                        signal_counts[feedback['signal']] += 1
        
        return {
            'period_days': days,
            'total_retrievals': total_events,
            'total_feedback_signals': total_feedback,
            'signal_breakdown': signal_counts,
            'feedback_rate': total_feedback / total_events if total_events > 0 else 0,
            'current_weights': self.weight_optimizer._intent_weights,
            'top_memories': self._get_top_memories(5)
        }
    
    def _get_top_memories(self, n: int) -> List[Dict]:
        """Get top N most useful memories"""
        memories = []
        for mem_id, stats in self.performance_tracker._performance_cache.items():
            if stats['total_uses'] >= 3:  # Minimum usage threshold
                score = self.performance_tracker.get_usefulness_score(mem_id)
                memories.append({
                    'memory_id': mem_id,
                    'usefulness_score': score,
                    'total_uses': stats['total_uses'],
                    'helpful_uses': stats['helpful_uses']
                })
        
        memories.sort(key=lambda m: m['usefulness_score'], reverse=True)
        return memories[:n]


# Convenience function for integration with injector
def create_feedback_loop(qdrant_manager=None) -> CogneeStyleFeedbackLoop:
    """Factory function to create feedback loop with optional Qdrant manager"""
    return CogneeStyleFeedbackLoop(qdrant_manager=qdrant_manager)


if __name__ == "__main__":
    # Simple test
    print("Testing CogneeStyleFeedbackLoop...")
    
    fb = create_feedback_loop()
    
    # Simulate a retrieval
    memories = [
        {'subject': 'User', 'relation': 'LIKES', 'object': 'Marcello\'s', 'id': 'mem1'},
        {'subject': 'User', 'relation': 'DISLIKES', 'object': 'spicy food', 'id': 'mem2'}
    ]
    
    event_id = fb.log_retrieval(
        query="Where should I eat?",
        query_vector=None,
        intent="preference_query",
        memories_injected=memories,
        graph_weight=0.4,
        semantic_weight=0.6,
        semantic_threshold=0.75,
        max_results=5
    )
    
    print(f"Logged retrieval event: {event_id}")
    
    # Simulate positive feedback
    fb.record_feedback(event_id, FeedbackSignal.QUERY_ANSWERED)
    print("Recorded positive feedback")
    
    # Check performance
    print(f"Memory 1 usefulness: {fb.performance_tracker.get_usefulness_score('mem1'):.2f}")
    
    # Get analytics
    analytics = fb.get_analytics(days=1)
    print(f"\nAnalytics: {json.dumps(analytics, indent=2, default=str)}")
    
    print("\n✅ Feedback loop test passed!")
