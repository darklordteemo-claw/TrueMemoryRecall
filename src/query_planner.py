#!/usr/bin/env python3
"""
TMR v2 Query Planner Module

Plans and executes retrieval strategy based on query intent.
Converts intent into actionable retrieval plan with multiple steps.

Author: Liz (TMR v2)
Date: 2026-03-17
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

# Setup logging
logger = logging.getLogger('TMR.QueryPlanner')


class PlanStepType(Enum):
    """Types of plan execution steps."""
    EXTRACT_ENTITIES = "extract_entities"
    SEARCH = "search"
    PRIORITIZE_SOURCES = "prioritize_sources"
    RANK_RESULTS = "rank_results"
    FILTER_RESULTS = "filter_results"


@dataclass
class PlanStep:
    """Single step in a retrieval plan."""
    type: PlanStepType
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    
    def __post_init__(self):
        if not self.description:
            self.description = f"{self.type.value} step"


@dataclass
class RetrievalPlan:
    """Complete retrieval plan for a query."""
    query: str
    intent: str
    intent_confidence: float
    steps: List[PlanStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_step(self, step_type: PlanStepType, params: Dict[str, Any] = None, 
                 description: str = "") -> None:
        """Add a step to the plan."""
        if params is None:
            params = {}
        self.steps.append(PlanStep(step_type, params, description))
    
    def get_step_count(self) -> int:
        """Get total number of steps."""
        return len(self.steps)
    
    def get_search_method(self) -> str:
        """Get the search method from the plan."""
        for step in self.steps:
            if step.type == PlanStepType.SEARCH:
                return step.params.get('method', 'unknown')
        return 'unknown'


class QueryPlanner:
    """
    Plans retrieval strategy based on query intent.
    
    Creates dynamic execution plans that adapt to:
    - Query intent type (greeting, technical, etc.)
    - Source prioritization (identity files vs conversations)
    - Search method (traversal vs hybrid vs semantic)
    - Result ranking strategy
    """
    
    # Strategy configurations
    STRATEGIES = {
        'identity_first': {
            'description': 'Prioritize identity/personality files (SOUL.md, IDENTITY.md)',
            'source_priority': ['tmr_agents_files', 'tmr_knowledge_graph'],
            'boost_identity': True,
        },
        'temporal_priority': {
            'description': 'Prioritize recent conversations',
            'source_priority': ['tmr_knowledge_graph', 'tmr_agents_files'],
            'boost_recent': True,
            'time_decay': 0.95,  # Older memories decay
        },
        'technical_depth': {
            'description': 'Deep traversal for technical details',
            'source_priority': ['tmr_knowledge_graph'],
            'boost_technical': True,
        },
        'preference_extraction': {
            'description': 'Extract and store user preferences',
            'source_priority': ['tmr_knowledge_graph', 'tmr_agents_files'],
            'extract_preferences': True,
        },
        'entity_expansion': {
            'description': 'Expand from entity to connected concepts',
            'source_priority': ['tmr_knowledge_graph', 'tmr_agents_files'],
            'expand_entities': True,
        },
        'hybrid': {
            'description': 'Balanced graph and semantic search',
            'source_priority': ['tmr_knowledge_graph', 'tmr_agents_files'],
        }
    }
    
    def __init__(self):
        """Initialize the query planner."""
        logger.info("=" * 70)
        logger.info("QueryPlanner initialized")
        logger.info(f"  Loaded {len(self.STRATEGIES)} strategies")
        for name, config in self.STRATEGIES.items():
            logger.info(f"    - {name}: {config['description']}")
        logger.info("=" * 70)
    
    def plan(self, query: str, intent: str, intent_confidence: float,
             weights: Dict[str, float]) -> RetrievalPlan:
        """
        Create a retrieval plan based on query and intent.
        
        Args:
            query: User's input query
            intent: Classified intent type
            intent_confidence: Confidence score from classifier
            weights: Dictionary with 'graph' and 'semantic' weights
            
        Returns:
            RetrievalPlan with execution steps
            
        Example:
            >>> planner = QueryPlanner()
            >>> plan = planner.plan("How are you?", "greeting", 0.90, 
            ...                     {'graph': 0.1, 'semantic': 0.9})
            >>> print(plan.get_step_count())
            4
        """
        logger.info("-" * 70)
        logger.info("PLANNING RETRIEVAL")
        logger.info("-" * 70)
        logger.info(f"Query: \"{query[:80]}\"")
        logger.info(f"Intent: {intent} (confidence: {intent_confidence:.2f})")
        logger.info(f"Weights: graph={weights['graph']}, semantic={weights['semantic']}")
        
        # Create plan
        plan = RetrievalPlan(
            query=query,
            intent=intent,
            intent_confidence=intent_confidence
        )
        
        # Get strategy configuration
        strategy = self._get_strategy(intent)
        logger.info(f"Strategy: {strategy}")
        
        # Step 1: Extract entities
        logger.info("Step 1: Adding entity extraction...")
        extract_method = 'ner' if intent == 'technical_howto' else 'simple'
        plan.add_step(
            PlanStepType.EXTRACT_ENTITIES,
            {'method': extract_method, 'max_entities': 10},
            f"Extract entities using {extract_method} method"
        )
        
        # Step 2: Select search method
        logger.info("Step 2: Selecting search method...")
        search_method = self._select_search_method(intent, weights)
        max_hops = self._get_max_hops(intent)
        plan.add_step(
            PlanStepType.SEARCH,
            {
                'method': search_method,
                'max_hops': max_hops,
                'weights': weights,
                'collections': self.STRATEGIES[strategy]['source_priority']
            },
            f"Search using {search_method} (max {max_hops} hops)"
        )
        logger.info(f"  Selected: {search_method} with {max_hops} max hops")
        
        # Step 3: Prioritize sources
        logger.info("Step 3: Adding source prioritization...")
        plan.add_step(
            PlanStepType.PRIORITIZE_SOURCES,
            {
                'strategy': strategy,
                'boost_identity': self.STRATEGIES[strategy].get('boost_identity', False),
                'boost_recent': self.STRATEGIES[strategy].get('boost_recent', False),
                'source_priority': self.STRATEGIES[strategy]['source_priority']
            },
            f"Prioritize sources using {strategy} strategy"
        )
        
        # Step 4: Rank results
        logger.info("Step 4: Adding result ranking...")
        diversity_penalty = 0.1 if intent in ['technical_howto', 'entity_lookup'] else 0.05
        recency_boost = 0.2 if intent in ['memory_recall'] else 0.0
        plan.add_step(
            PlanStepType.RANK_RESULTS,
            {
                'diversity_penalty': diversity_penalty,
                'recency_boost': recency_boost,
                'top_k': 5
            },
            f"Rank with diversity penalty {diversity_penalty}, recency boost {recency_boost}"
        )
        logger.info(f"  Diversity penalty: {diversity_penalty}, Recency boost: {recency_boost}")
        
        logger.info(f"Plan complete: {plan.get_step_count()} steps")
        logger.info("-" * 70)
        
        return plan
    
    def _get_strategy(self, intent: str) -> str:
        """Get strategy name for intent."""
        strategy_map = {
            'greeting': 'identity_first',
            'personal_identity': 'identity_first',
            'memory_recall': 'temporal_priority',
            'technical_howto': 'technical_depth',
            'preference_learn': 'preference_extraction',
            'entity_lookup': 'entity_expansion'
        }
        return strategy_map.get(intent, 'hybrid')
    
    def _select_search_method(self, intent: str, weights: Dict[str, float]) -> str:
        """Select search method based on intent and weights."""
        # If semantic weight is high (>0.7), use semantic-first
        if weights['semantic'] > 0.7:
            return 'semantic_first'
        
        # If graph weight is high (>0.7), use traversal
        if weights['graph'] > 0.7:
            return 'traversal'
        
        # Balanced weights = hybrid
        return 'hybrid'
    
    def _get_max_hops(self, intent: str) -> int:
        """Get maximum traversal hops for intent."""
        hops_map = {
            'greeting': 1,
            'personal_identity': 2,
            'memory_recall': 3,
            'technical_howto': 4,
            'preference_learn': 2,
            'entity_lookup': 3
        }
        return hops_map.get(intent, 2)
    
    def execute_plan(self, plan: RetrievalPlan) -> Dict[str, Any]:
        """
        Execute a retrieval plan (placeholder for actual implementation).
        
        Args:
            plan: RetrievalPlan to execute
            
        Returns:
            Execution results
        """
        logger.info(f"Executing plan with {plan.get_step_count()} steps...")
        
        results = {
            'plan': plan,
            'executed_steps': [],
            'memories_found': [],
            'status': 'success'
        }
        
        for i, step in enumerate(plan.steps, 1):
            logger.info(f"  Executing step {i}: {step.type.value}")
            # Placeholder: In real implementation, execute each step
            results['executed_steps'].append({
                'step': i,
                'type': step.type.value,
                'params': step.params,
                'status': 'completed'
            })
        
        logger.info("Plan execution complete")
        return results


# Test function
def test_planner():
    """Test the query planner."""
    print("=" * 70)
    print("TESTING QUERY PLANNER")
    print("=" * 70)
    
    planner = QueryPlanner()
    
    test_cases = [
        ("How are you?", "greeting", {'graph': 0.1, 'semantic': 0.9}),
        ("Who are you?", "personal_identity", {'graph': 0.2, 'semantic': 0.8}),
        ("What did we discuss?", "memory_recall", {'graph': 0.5, 'semantic': 0.5}),
        ("How to fix the error?", "technical_howto", {'graph': 0.7, 'semantic': 0.3}),
        ("I like pizza", "preference_learn", {'graph': 0.6, 'semantic': 0.4}),
        ("Liz", "entity_lookup", {'graph': 0.8, 'semantic': 0.2}),
    ]
    
    passed = 0
    failed = 0
    
    for query, intent, weights in test_cases:
        try:
            plan = planner.plan(query, intent, 0.90, weights)
            search_method = plan.get_search_method()
            
            print(f"\nQuery: \"{query}\"")
            print(f"  Intent: {intent}")
            print(f"  Search method: {search_method}")
            print(f"  Steps: {plan.get_step_count()}")
            
            # Verify plan has expected steps
            step_types = [s.type for s in plan.steps]
            expected_types = [
                PlanStepType.EXTRACT_ENTITIES,
                PlanStepType.SEARCH,
                PlanStepType.PRIORITIZE_SOURCES,
                PlanStepType.RANK_RESULTS
            ]
            
            if all(t in step_types for t in expected_types):
                print(f"  ✓ All expected steps present")
                passed += 1
            else:
                print(f"  ✗ Missing expected steps")
                failed += 1
                
        except Exception as e:
            print(f"\n✗ FAILED: {query} - {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    success = test_planner()
    sys.exit(0 if success else 1)
