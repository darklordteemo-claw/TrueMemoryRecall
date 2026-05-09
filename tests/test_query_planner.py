#!/usr/bin/env python3
"""
Unit tests for QueryPlanner

Run with: python3 tests/test_query_planner.py
"""

import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from query_planner import QueryPlanner, RetrievalPlan, PlanStep, PlanStepType


class TestQueryPlanner(unittest.TestCase):
    """Test suite for QueryPlanner."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.planner = QueryPlanner()
    
    def test_greeting_plan(self):
        """Test plan for greeting intent."""
        plan = self.planner.plan("How are you?", "greeting", 0.90, 
                                 {'graph': 0.1, 'semantic': 0.9})
        
        self.assertEqual(plan.intent, 'greeting')
        self.assertEqual(plan.get_step_count(), 4)
        self.assertEqual(plan.get_search_method(), 'semantic_first')
    
    def test_technical_plan(self):
        """Test plan for technical intent."""
        plan = self.planner.plan("How to fix error?", "technical_howto", 0.90,
                                 {'graph': 0.7, 'semantic': 0.3})
        
        self.assertEqual(plan.intent, 'technical_howto')
        self.assertEqual(plan.get_search_method(), 'hybrid')
        
        # Check diversity penalty is higher for technical
        rank_step = [s for s in plan.steps if s.type == PlanStepType.RANK_RESULTS][0]
        self.assertEqual(rank_step.params['diversity_penalty'], 0.1)
    
    def test_memory_recall_plan(self):
        """Test plan for memory recall intent."""
        plan = self.planner.plan("What did we discuss?", "memory_recall", 0.90,
                                 {'graph': 0.5, 'semantic': 0.5})
        
        self.assertEqual(plan.intent, 'memory_recall')
        self.assertEqual(plan.get_search_method(), 'hybrid')
        
        # Check recency boost
        rank_step = [s for s in plan.steps if s.type == PlanStepType.RANK_RESULTS][0]
        self.assertEqual(rank_step.params['recency_boost'], 0.2)
    
    def test_entity_lookup_traversal(self):
        """Test that entity lookup uses traversal."""
        plan = self.planner.plan("Liz", "entity_lookup", 0.90,
                                 {'graph': 0.8, 'semantic': 0.2})
        
        self.assertEqual(plan.get_search_method(), 'traversal')
    
    def test_plan_has_all_steps(self):
        """Test that plan includes all required steps."""
        plan = self.planner.plan("Test query", "greeting", 0.90,
                                 {'graph': 0.5, 'semantic': 0.5})
        
        step_types = [s.type for s in plan.steps]
        
        self.assertIn(PlanStepType.EXTRACT_ENTITIES, step_types)
        self.assertIn(PlanStepType.SEARCH, step_types)
        self.assertIn(PlanStepType.PRIORITIZE_SOURCES, step_types)
        self.assertIn(PlanStepType.RANK_RESULTS, step_types)
    
    def test_strategy_selection(self):
        """Test that correct strategy is selected for each intent."""
        test_cases = [
            ('greeting', 'identity_first'),
            ('personal_identity', 'identity_first'),
            ('memory_recall', 'temporal_priority'),
            ('technical_howto', 'technical_depth'),
        ]
        
        for intent, expected_strategy in test_cases:
            plan = self.planner.plan(f"Test {intent}", intent, 0.90,
                                    {'graph': 0.5, 'semantic': 0.5})
            
            # Check source prioritization step has correct strategy
            prioritize_step = [s for s in plan.steps 
                             if s.type == PlanStepType.PRIORITIZE_SOURCES][0]
            self.assertEqual(prioritize_step.params['strategy'], expected_strategy)


if __name__ == '__main__':
    unittest.main()
