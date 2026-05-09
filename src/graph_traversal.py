#!/usr/bin/env python3
"""
TMR v2 Multi-Hop Graph Traversal Module

Performs multi-hop breadth-first search on knowledge graph.
Finds paths like: User -[DISCUSSED]-> TMR -[USES]-> Qdrant

Author: Liz (TMR v2)
Date: 2026-03-17
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime

# Setup logging
logger = logging.getLogger('TMR.GraphTraversal')


@dataclass
class GraphPath:
    """Represents a path through the knowledge graph."""
    entities: List[str] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    score: float = 1.0
    hops: int = 0
    
    def add_step(self, entity: str, relation: Dict[str, Any]):
        """Add a step to the path."""
        self.entities.append(entity)
        self.relations.append(relation)
        # Score is product of relation strengths
        relation_strength = relation.get('strength', 0.5)
        self.score *= relation_strength
        self.hops += 1
    
    def to_string(self) -> str:
        """Convert path to readable string."""
        if not self.relations:
            return str(self.entities[0]) if self.entities else "Empty path"
        
        parts = [self.entities[0]]
        for i, rel in enumerate(self.relations):
            parts.append(f"-[{rel.get('relation', '?')}]->")
            if i + 1 < len(self.entities):
                parts.append(self.entities[i + 1])
        
        return " ".join(parts)


class MultiHopTraversal:
    """
    Performs multi-hop traversal on knowledge graph.
    
    Uses BFS to find paths from starting entities.
    Ranks paths by accumulated strength scores.
    Filters for diversity (avoid similar paths).
    """
    
    def __init__(self, qdrant_manager):
        """
        Initialize with Qdrant manager for relation lookups.
        
        Args:
            qdrant_manager: Instance of QdrantManager for DB queries
        """
        self.qdrant = qdrant_manager
        logger.info("=" * 70)
        logger.info("MultiHopTraversal initialized")
        logger.info("=" * 70)
    
    def traverse(self, start_entities: List[str], max_hops: int = 3,
                 min_score: float = 0.1, max_paths: int = 10) -> List[GraphPath]:
        """
        Perform multi-hop BFS traversal from starting entities.
        
        Args:
            start_entities: List of entity names to start from
            max_hops: Maximum number of hops (default 3)
            min_score: Minimum path score threshold (default 0.1)
            max_paths: Maximum number of paths to return (default 10)
            
        Returns:
            List of GraphPath objects ranked by score
            
        Example:
            >>> traversal = MultiHopTraversal(qdrant)
            >>> paths = traversal.traverse(["User"], max_hops=2)
            >>> for path in paths:
            ...     print(f"{path.to_string()} (score: {path.score:.2f})")
            User -[DISCUSSED]-> TMR (score: 0.95)
            User -[EXPERIENCED]-> API Key Error (score: 0.85)
        """
        logger.info("-" * 70)
        logger.info(f"STARTING MULTI-HOP TRAVERSAL")
        logger.info(f"  Start entities: {start_entities}")
        logger.info(f"  Max hops: {max_hops}")
        logger.info(f"  Min score: {min_score}")
        logger.info(f"  Max paths: {max_paths}")
        logger.info("-" * 70)
        
        all_paths = []
        visited = set()  # Track visited (entity, hop) pairs
        
        for start_entity in start_entities:
            logger.info(f"\nTraversing from: {start_entity}")
            
            # BFS queue: (current_entity, current_path, current_hop)
            queue = deque([(start_entity, GraphPath(entities=[start_entity]), 0)])
            
            entity_paths = 0  # Track paths from this entity
            
            while queue and entity_paths < max_paths:
                current_entity, current_path, current_hop = queue.popleft()
                
                # Check if we've reached max hops
                if current_hop >= max_hops:
                    if current_path.hops > 0 and current_path.score >= min_score:
                        all_paths.append(current_path)
                        entity_paths += 1
                    continue
                
                # Mark as visited
                visit_key = (current_entity, current_hop)
                if visit_key in visited:
                    continue
                visited.add(visit_key)
                
                # Get connected relations from Qdrant
                logger.debug(f"  Hop {current_hop}: Finding relations for '{current_entity}'")
                relations = self._get_relations_for_entity(current_entity)
                
                logger.debug(f"    Found {len(relations)} relations")
                
                for rel in relations:
                    # Determine next entity
                    if rel.get('subject') == current_entity:
                        next_entity = rel.get('object')
                    elif rel.get('object') == current_entity:
                        next_entity = rel.get('subject')
                    else:
                        continue  # Shouldn't happen
                    
                    # Skip if creates cycle
                    if next_entity in current_path.entities:
                        continue
                    
                    # Create new path
                    new_path = GraphPath(
                        entities=current_path.entities.copy(),
                        relations=current_path.relations.copy(),
                        score=current_path.score,
                        hops=current_path.hops
                    )
                    new_path.add_step(next_entity, rel)
                    
                    # Check score threshold
                    if new_path.score < min_score:
                        continue
                    
                    # Add to queue for next hop
                    queue.append((next_entity, new_path, current_hop + 1))
                    
                    # Also add as final path (shorter paths are valid too)
                    if new_path.score >= min_score:
                        all_paths.append(new_path)
                        entity_paths += 1
            
            logger.info(f"  Found {entity_paths} paths from {start_entity}")
        
        logger.info(f"\nTotal paths found: {len(all_paths)}")
        
        # Rank and filter paths
        ranked_paths = self._rank_and_filter_paths(all_paths, max_paths)
        
        logger.info(f"After ranking/filtering: {len(ranked_paths)} paths")
        logger.info("-" * 70)
        
        return ranked_paths
    
    def _get_relations_for_entity(self, entity: str) -> List[Dict[str, Any]]:
        """
        Get all relations connected to an entity from Qdrant.
        
        Args:
            entity: Entity name
            
        Returns:
            List of relation dictionaries
        """
        try:
            logger.debug(f"Querying Qdrant for entity: {entity}")
            
            # Query Qdrant for relations where entity is subject or object
            relations = self.qdrant.get_relations_for_entity(entity, collection="knowledge_graph")
            
            logger.debug(f"Found {len(relations)} relations for {entity}")
            return relations
            
        except Exception as e:
            logger.error(f"Error querying relations for {entity}: {e}")
            return []
    
    def _rank_and_filter_paths(self, paths: List[GraphPath], 
                               max_paths: int) -> List[GraphPath]:
        """
        Rank paths by score and filter for diversity.
        
        Args:
            paths: List of paths to rank
            max_paths: Maximum number to return
            
        Returns:
            Ranked and filtered list of paths
        """
        if not paths:
            return []
        
        # Sort by score (descending)
        paths.sort(key=lambda p: p.score, reverse=True)
        
        # Filter for diversity (avoid similar paths)
        diverse_paths = []
        seen_endpoints = set()
        
        for path in paths:
            # Use final entity as endpoint
            if path.entities:
                endpoint = path.entities[-1]
                
                # Skip if we already have a path to this endpoint
                if endpoint in seen_endpoints:
                    continue
                
                seen_endpoints.add(endpoint)
                diverse_paths.append(path)
                
                if len(diverse_paths) >= max_paths:
                    break
        
        return diverse_paths
    
    def find_paths_between(self, start: str, end: str, max_hops: int = 4) -> List[GraphPath]:
        """
        Find paths between two specific entities.
        
        Args:
            start: Starting entity
            end: Target entity
            max_hops: Maximum hops allowed
            
        Returns:
            List of paths from start to end
        """
        logger.info(f"Finding paths from '{start}' to '{end}' (max {max_hops} hops)")
        
        all_paths = self.traverse([start], max_hops=max_hops, max_paths=100)
        
        # Filter paths that end at target
        target_paths = [p for p in all_paths if end in p.entities]
        
        logger.info(f"Found {len(target_paths)} paths to '{end}'")
        
        return target_paths


# Test function
def test_traversal():
    """Test the graph traversal."""
    print("=" * 70)
    print("TESTING MULTI-HOP TRAVERSAL")
    print("=" * 70)
    
    # Mock Qdrant manager for testing
    class MockQdrant:
        pass
    
    traversal = MultiHopTraversal(MockQdrant())
    
    # Test with mock data would go here
    # For now, just verify initialization
    print("✓ MultiHopTraversal initialized successfully")
    
    print("=" * 70)
    return True


if __name__ == "__main__":
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    success = test_traversal()
    sys.exit(0 if success else 1)
