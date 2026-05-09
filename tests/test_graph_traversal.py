#!/usr/bin/env python3
"""
Unit tests for MultiHopTraversal

Run with: python3 tests/test_graph_traversal.py
"""

import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from graph_traversal import MultiHopTraversal, GraphPath


class MockQdrant:
    """Mock Qdrant manager for testing."""
    
    def __init__(self, mock_relations):
        self.mock_relations = mock_relations
    
    def get_relations_for_entity(self, entity, collection="knowledge_graph"):
        return self.mock_relations.get(entity, [])


class TestGraphTraversal(unittest.TestCase):
    """Test suite for MultiHopTraversal."""
    
    def setUp(self):
        """Set up test fixtures with mock data."""
        # Create mock relations
        self.mock_relations = {
            "User": [
                {"subject": "User", "relation": "DISCUSSED", "object": "TMR", "strength": 0.95},
                {"subject": "User", "relation": "EXPERIENCED", "object": "API Key Error", "strength": 0.85},
            ],
            "TMR": [
                {"subject": "User", "relation": "DISCUSSED", "object": "TMR", "strength": 0.95},
                {"subject": "TMR", "relation": "USES", "object": "Qdrant", "strength": 0.90},
                {"subject": "TMR", "relation": "HAS", "object": "Logging", "strength": 0.80},
            ],
            "Qdrant": [
                {"subject": "TMR", "relation": "USES", "object": "Qdrant", "strength": 0.90},
                {"subject": "Qdrant", "relation": "STORES", "object": "Vectors", "strength": 0.95},
            ],
        }
        
        self.qdrant = MockQdrant(self.mock_relations)
        self.traversal = MultiHopTraversal(self.qdrant)
    
    def test_single_hop(self):
        """Test 1-hop traversal."""
        paths = self.traversal.traverse(["User"], max_hops=1, max_paths=10)
        
        self.assertEqual(len(paths), 2)  # User -> TMR, User -> API Key Error
        
        # Check paths exist
        path_strings = [p.to_string() for p in paths]
        self.assertTrue(any("TMR" in s for s in path_strings))
        self.assertTrue(any("API Key Error" in s for s in path_strings))
    
    def test_two_hop(self):
        """Test 2-hop traversal."""
        paths = self.traversal.traverse(["User"], max_hops=2, max_paths=10)
        
        # Should find User -> TMR -> Qdrant
        path_strings = [p.to_string() for p in paths]
        has_qdrant_path = any("Qdrant" in s for s in path_strings)
        self.assertTrue(has_qdrant_path)
    
    def test_path_scoring(self):
        """Test that paths are scored correctly."""
        paths = self.traversal.traverse(["User"], max_hops=1)
        
        # Higher strength relation should have higher score
        tmr_path = [p for p in paths if "TMR" in p.to_string()][0]
        error_path = [p for p in paths if "API Key Error" in p.to_string()][0]
        
        self.assertGreater(tmr_path.score, error_path.score)
    
    def test_diversity_filtering(self):
        """Test that similar paths are filtered."""
        # With diversity filtering, should get different endpoints
        paths = self.traversal.traverse(["User"], max_hops=2, max_paths=10)
        
        endpoints = set()
        for path in paths:
            if path.entities:
                endpoints.add(path.entities[-1])
        
        # Should have diverse endpoints
        self.assertGreater(len(endpoints), 0)
    
    def test_min_score_filtering(self):
        """Test minimum score filtering."""
        paths = self.traversal.traverse(["User"], max_hops=2, min_score=0.9)
        
        for path in paths:
            self.assertGreaterEqual(path.score, 0.9)
    
    def test_graph_path_class(self):
        """Test GraphPath dataclass."""
        path = GraphPath(entities=["User"])
        
        rel = {"subject": "User", "relation": "TEST", "object": "Object", "strength": 0.8}
        path.add_step("Object", rel)
        
        self.assertEqual(len(path.entities), 2)
        self.assertEqual(path.score, 0.8)
        self.assertEqual(path.hops, 1)
        self.assertIn("TEST", path.to_string())


if __name__ == '__main__':
    unittest.main()
