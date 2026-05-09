#!/usr/bin/env python3
"""
TMR v2 - AI-Generated Feedback System

The AI (Liz) automatically provides feedback on retrieved memories
based on whether they were actually used in the response.
"""

import re
from typing import List, Dict, Optional
from difflib import SequenceMatcher


class AIFeedbackGenerator:
    """
    Generates implicit feedback based on AI's actual usage of memories.
    
    The AI can see:
    1. What memories were injected
    2. What response was generated
    3. Which memories were actually referenced
    
    This provides high-quality implicit feedback without user intervention.
    """
    
    def __init__(self):
        self.similarity_threshold = 0.6  # Minimum similarity to count as "referenced"
    
    def analyze_response(self, 
                        query: str,
                        memories_injected: List[Dict],
                        ai_response: str,
                        event_id: str) -> Dict:
        """
        Analyze AI response to determine which memories were actually helpful.
        
        Args:
            query: Original user query
            memories_injected: List of memories that were injected
            ai_response: The AI's actual response
            event_id: The retrieval event ID for feedback correlation
            
        Returns:
            Dict with feedback for each memory
        """
        feedback_results = []
        
        for memory in memories_injected:
            memory_id = memory.get('id') or self._memory_key(memory)
            
            # Check if memory was referenced in response
            reference_score = self._calculate_reference_score(memory, ai_response)
            
            # Determine feedback signal
            if reference_score > 0.7:
                signal = "MEMORY_REFERENCED"
                helpful = True
                confidence = "high"
            elif reference_score > 0.4:
                signal = "QUERY_ANSWERED"  # Memory provided context but not directly quoted
                helpful = True
                confidence = "medium"
            else:
                signal = "MEMORY_IGNORED"  # Memory was present but not used
                helpful = False
                confidence = "low"
            
            feedback_results.append({
                'memory_id': memory_id,
                'memory_content': f"{memory.get('subject', '')} → {memory.get('relation', '')} → {memory.get('object', '')}",
                'signal': signal,
                'helpful': helpful,
                'confidence': confidence,
                'reference_score': reference_score,
                'evidence': self._extract_evidence(memory, ai_response) if helpful else None
            })
        
        return {
            'event_id': event_id,
            'query': query,
            'total_memories': len(memories_injected),
            'helpful_memories': sum(1 for f in feedback_results if f['helpful']),
            'ignored_memories': sum(1 for f in feedback_results if not f['helpful']),
            'feedback': feedback_results
        }
    
    def _memory_key(self, memory: Dict) -> str:
        """Generate stable key for memory"""
        subj = memory.get('subject', '')
        rel = memory.get('relation', '')
        obj = memory.get('object', '')
        return f"{subj}:{rel}:{obj}"
    
    def _calculate_reference_score(self, memory: Dict, response: str) -> float:
        """
        Calculate how much the AI referenced the memory in its response.
        
        Returns score 0.0-1.0 where:
        - 1.0 = Directly quoted or heavily referenced
        - 0.5 = Concepts mentioned but not exact
        - 0.0 = Not referenced at all
        """
        response_lower = response.lower()
        
        # Components to check
        subject = memory.get('subject', '').lower()
        obj = memory.get('object', '').lower()
        evidence = memory.get('evidence', '').lower()
        
        scores = []
        
        # Check 1: Subject mentioned?
        if subject and len(subject) > 2:
            if subject in response_lower:
                scores.append(0.3)
            elif any(word in response_lower for word in subject.split()):
                scores.append(0.15)
        
        # Check 2: Object mentioned?
        if obj and len(obj) > 2:
            if obj in response_lower:
                scores.append(0.3)
            elif any(word in response_lower for word in obj.split()):
                scores.append(0.15)
        
        # Check 3: Evidence text similarity (most important)
        if evidence and len(evidence) > 5:
            # Check for key phrases from evidence
            evidence_phrases = self._extract_key_phrases(evidence)
            matches = sum(1 for phrase in evidence_phrases if phrase in response_lower)
            if matches > 0:
                scores.append(min(0.4, matches * 0.15))
            
            # Overall similarity
            similarity = SequenceMatcher(None, evidence, response_lower).ratio()
            if similarity > 0.3:  # Significant similarity
                scores.append(similarity * 0.3)
        
        # Check 4: Relation concept
        relation = memory.get('relation', '').lower()
        relation_concepts = {
            'likes': ['like', 'enjoy', 'love', 'prefer', 'favorite'],
            'dislikes': ['dislike', 'hate', 'avoid', 'don\'t like'],
            'discussed': ['discussed', 'talked', 'mentioned', 'conversation'],
            'decided': ['decided', 'chose', 'agreed', 'plan'],
            'fixed': ['fixed', 'solved', 'resolved', 'corrected'],
            'implemented': ['implemented', 'built', 'created', 'made']
        }
        
        if relation in relation_concepts:
            concept_words = relation_concepts[relation]
            if any(word in response_lower for word in concept_words):
                scores.append(0.2)
        
        return min(1.0, sum(scores))
    
    def _extract_key_phrases(self, text: str) -> List[str]:
        """Extract key phrases from evidence text"""
        # Split into sentences, take meaningful ones
        sentences = text.split('.')
        phrases = []
        
        for sentence in sentences:
            sentence = sentence.strip().lower()
            # Filter out short sentences
            if len(sentence) > 10 and len(sentence) < 100:
                phrases.append(sentence)
                # Also add individual words for partial matching
                words = sentence.split()
                if len(words) >= 3:
                    phrases.append(' '.join(words[:3]))
        
        return phrases
    
    def _extract_evidence(self, memory: Dict, response: str) -> Optional[str]:
        """Extract the part of response that references the memory"""
        response_lower = response.lower()
        
        # Try to find which part of response references this memory
        subject = memory.get('subject', '').lower()
        obj = memory.get('object', '').lower()
        
        # Simple extraction: find sentence containing subject or object
        sentences = response.split('.')
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if (subject and subject in sentence_lower) or (obj and obj in sentence_lower):
                return sentence.strip()
        
        return None
    
    def format_feedback_report(self, analysis: Dict) -> str:
        """Format feedback analysis for logging/display"""
        lines = []
        lines.append("=" * 70)
        lines.append("TMR AI-GENERATED FEEDBACK")
        lines.append("=" * 70)
        lines.append(f"Query: {analysis['query'][:80]}...")
        lines.append(f"Event ID: {analysis['event_id'][:8]}...")
        lines.append(f"Memories analyzed: {analysis['total_memories']}")
        lines.append(f"  - Helpful: {analysis['helpful_memories']}")
        lines.append(f"  - Ignored: {analysis['ignored_memories']}")
        lines.append("")
        
        for fb in analysis['feedback']:
            status = "✅ HELPFUL" if fb['helpful'] else "⚠️ IGNORED"
            lines.append(f"{status} [{fb['confidence'].upper()}]")
            lines.append(f"  Memory: {fb['memory_content']}")
            lines.append(f"  Signal: {fb['signal']}")
            lines.append(f"  Reference Score: {fb['reference_score']:.2f}")
            if fb['evidence']:
                lines.append(f"  Evidence in response: \"{fb['evidence'][:100]}...\"")
            lines.append("")
        
        lines.append("=" * 70)
        return "\n".join(lines)


# Integration function for OpenClaw
def auto_feedback_after_response(query: str, 
                                 memories_injected: List[Dict],
                                 ai_response: str,
                                 event_id: str,
                                 injector) -> None:
    """
    Automatically generate and report feedback after AI generates response.
    
    This should be called automatically after every response.
    
    Args:
        query: User's query
        memories_injected: Memories that were injected
        ai_response: AI's generated response
        event_id: The retrieval event ID
        injector: The TMR injector instance (for reporting feedback)
    """
    generator = AIFeedbackGenerator()
    
    # Analyze the response
    analysis = generator.analyze_response(query, memories_injected, ai_response, event_id)
    
    # Log the feedback
    print(generator.format_feedback_report(analysis))
    
    # Report feedback for helpful memories
    for fb in analysis['feedback']:
        if fb['helpful']:
            # Determine signal type
            if fb['signal'] == 'MEMORY_REFERENCED':
                signal_type = 'memory_referenced'
            else:
                signal_type = 'query_answered'
            
            # Report to feedback loop
            try:
                injector.report_feedback(
                    event_id=event_id,
                    signal_type=signal_type,
                    messages_since=0
                )
            except Exception as e:
                print(f"[Feedback] Could not report feedback: {e}")


if __name__ == "__main__":
    # Demo
    print("Testing AI Feedback Generator...")
    print("=" * 70)
    
    # Simulate a query and response
    query = "Where should I eat?"
    
    memories = [
        {
            'id': 'mem1',
            'subject': 'User',
            'relation': 'LIKES',
            'object': 'Marcello\'s',
            'evidence': 'User said they love the carbonara at Marcello\'s'
        },
        {
            'id': 'mem2',
            'subject': 'User',
            'relation': 'DISLIKES',
            'object': 'spicy food',
            'evidence': 'User mentioned they hate spicy food'
        },
        {
            'id': 'mem3',
            'subject': 'User',
            'relation': 'LIKES',
            'object': 'sushi',
            'evidence': 'User enjoys sushi occasionally'
        }
    ]
    
    # AI response that references first two memories
    ai_response = """
Based on your preferences, I'd recommend Marcello's! You mentioned loving 
their carbonara before. Just be careful with the spice level since you 
dislike spicy food - maybe ask for mild sauce.
    """
    
    event_id = "test-event-123"
    
    # Generate feedback
    generator = AIFeedbackGenerator()
    analysis = generator.analyze_response(query, memories, ai_response, event_id)
    
    print(generator.format_feedback_report(analysis))
    
    print("\n" + "=" * 70)
    print("Test complete!")
    print("=" * 70)
