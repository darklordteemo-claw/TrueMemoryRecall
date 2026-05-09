#!/usr/bin/env python3
"""
TMR v2 - Cognee-Style GraphRAG Injector
========================================

Unified pipeline integrating:
- Phase 1: Intent Classification
- Phase 2: Query Planning  
- Phase 3: Multi-Hop Graph Traversal
- Phase 4: Feedback Loop (Self-Improvement)

Architecture:
    Query → Intent → Plan → (Traverse if multi-hop) → Hybrid Search → 
    Feedback Ranking → Format → Inject → Log for Learning

Author: Liz (TMR v2)
Date: 2026-03-18
Changes from original plan:
    - Added centralized config management via config_loader.py
    - All tunable parameters moved to tmr_config.yaml
    - Added source prioritization per strategy
    - Added diversity ranking
    - Added recency boosting
"""

import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta

# Import config loader first
try:
    from .config_loader import get_config, TMRConfig
    from .intent_classifier import IntentClassifier
    from .query_planner import QueryPlanner, PlanStepType
    from .graph_traversal import MultiHopTraversal
    from .feedback_loop import CogneeStyleFeedbackLoop, FeedbackSignal
except ImportError:
    # Fallback for direct execution
    from config_loader import get_config, TMRConfig
    from intent_classifier import IntentClassifier
    from query_planner import QueryPlanner, PlanStepType
    from graph_traversal import MultiHopTraversal
    from feedback_loop import CogneeStyleFeedbackLoop, FeedbackSignal

# Setup logging
logger = logging.getLogger('TMR.Injector')


class TMRCogneeInjector:
    """
    Cognee-style GraphRAG injector with full Phase 1-4 integration.
    
    Features:
    - Intent-aware retrieval with per-intent weights
    - Query planning with strategy selection
    - Multi-hop graph traversal (BFS)
    - Self-improving feedback loop
    - Source prioritization
    - Diversity and recency ranking
    """
    
    def __init__(self, graph_dir: Optional[str] = None, enable_feedback: bool = True):
        """
        Initialize TMR v2 injector with all components.
        
        Args:
            graph_dir: Path to knowledge graph directory (from config if None)
            enable_feedback: Whether to enable Phase 4 feedback loop
        """
        logger.info("=" * 70)
        logger.info("TMR v2 Cognee-Style Injector Initializing")
        logger.info("=" * 70)
        
        # Load configuration
        self.config = get_config()
        
        # Storage paths
        if graph_dir is None:
            graph_dir = self.config.storage.get('graph_dir', '~/.openclaw/workspace/memory/graph')
        self.graph_dir = Path(graph_dir).expanduser()
        
        # Initialize Phase 1: Intent Classification
        if self.config.intent_classification.get('enabled', True):
            self.intent_classifier = IntentClassifier()
            logger.info("✅ Phase 1: Intent Classification initialized")
        else:
            self.intent_classifier = None
            logger.info("⏸️ Phase 1: Intent Classification disabled")
        
        # Initialize Phase 2: Query Planner
        if self.config.query_planning.get('enabled', True):
            self.query_planner = QueryPlanner()
            logger.info("✅ Phase 2: Query Planner initialized")
        else:
            self.query_planner = None
            logger.info("⏸️ Phase 2: Query Planner disabled")
        
        # Initialize Phase 3: Graph Traversal
        if self.config.graph_traversal.get('enabled', True):
            self._qdrant = None  # Lazy init
            self._traversal = None  # Lazy init
            logger.info("✅ Phase 3: Graph Traversal ready (lazy init)")
        else:
            self._qdrant = None
            self._traversal = None
            logger.info("⏸️ Phase 3: Graph Traversal disabled")
        
        # Initialize Phase 4: Feedback Loop
        self._feedback_loop = None
        if enable_feedback and self.config.feedback_loop.get('enabled', True):
            try:
                feedback_dir = self.config.storage.get('feedback_dir')
                self._feedback_loop = CogneeStyleFeedbackLoop(
                    feedback_dir=feedback_dir,
                    qdrant_manager=None  # Will lazy-load when needed
                )
                logger.info("✅ Phase 4: Feedback Loop initialized")
            except Exception as e:
                logger.warning(f"⚠️ Phase 4: Feedback Loop failed to initialize: {e}")
        else:
            logger.info("⏸️ Phase 4: Feedback Loop disabled")
        
        # Lazy-loaded components
        self._embedder = None
        
        # Session-level conversation thread tracking
        # Tracks entities/topics from recent queries in current session
        self._session_recent_entities: List[str] = []
        self._session_recent_queries: List[str] = []
        self._session_max_history = 10  # Keep last N queries for context
        
        logger.info("=" * 70)
        logger.info("TMR v2 Injector Ready")
        logger.info("=" * 70)
    
    def _get_embedder(self):
        """Lazy initialization of embedder"""
        if self._embedder is None:
            from embedder import TMRRelationEmbedder
            embed_config = self.config.embeddings
            host = embed_config.get('host', 'http://localhost:11434')
            self._embedder = TMRRelationEmbedder(host=host)
        return self._embedder
    
    def _get_qdrant(self):
        """Lazy initialization of Qdrant manager"""
        if self._qdrant is None:
            from qdrant_manager import QdrantManager
            self._qdrant = QdrantManager()
        return self._qdrant
    
    def _get_traversal(self):
        """Lazy initialization of graph traversal"""
        if self._traversal is None:
            qdrant = self._get_qdrant()
            self._traversal = MultiHopTraversal(qdrant)
        return self._traversal
    
    # ========================================================================
    # MAIN ENTRY POINT: Full Cognee-Style Pipeline
    # ========================================================================
    
    def inject_context(self, query: str, session_id: Optional[str] = None) -> str:
        """
        Main entry point: Full Cognee-style pipeline with all phases.
        
        Pipeline:
        1. Classify intent (Phase 1)
        2. Create retrieval plan (Phase 2)
        3. Execute search (Phase 3 if multi-hop, else hybrid)
        4. Apply feedback ranking (Phase 4)
        5. Format and return
        6. Log for learning (Phase 4)
        
        Args:
            query: User query string
            session_id: Optional session ID for feedback tracking
            
        Returns:
            Formatted context string for injection
        """
        logger.info("\n" + "=" * 70)
        logger.info("TMR v2: Processing Query")
        logger.info(f"Query: \"{query[:80]}\"")
        logger.info("=" * 70)
        
        # -------------------------------------------------------------------
        # PHASE 1: Intent Classification
        # -------------------------------------------------------------------
        if self.intent_classifier:
            intent, confidence = self.intent_classifier.classify(query)
            logger.info(f"\n[Phase 1] Intent: {intent} (confidence: {confidence:.2f})")
        else:
            intent, confidence = 'default', 0.5
            logger.info(f"\n[Phase 1] Intent classification disabled, using default")
        
        # Get intent-specific weights from config
        weights = self.config.get_intent_weights(intent)
        graph_weight = weights['graph']
        semantic_weight = weights['semantic']
        logger.info(f"  Weights: graph={graph_weight:.2f}, semantic={semantic_weight:.2f}")
        
        # Get max hops for this intent
        max_hops = self.config.get_intent_max_hops(intent)
        logger.info(f"  Max hops: {max_hops}")
        
        # -------------------------------------------------------------------
        # PHASE 2: Query Planning
        # -------------------------------------------------------------------
        if self.query_planner:
            plan = self.query_planner.plan(query, intent, confidence, weights)
            strategy = self._get_strategy_from_intent(intent)
            logger.info(f"\n[Phase 2] Strategy: {strategy}")
            logger.info(f"  Plan steps: {plan.get_step_count()}")
        else:
            plan = None
            strategy = 'hybrid'
            logger.info(f"\n[Phase 2] Query planning disabled, using default strategy")
        
        # -------------------------------------------------------------------
        # Execute Retrieval
        # -------------------------------------------------------------------
        
        # Extract entities
        entities = self.extract_entities(query)
        
        # For identity queries, add "Liz" as entity (user asking about AI)
        if intent in ('greeting', 'personal_identity'):
            if 'liz' not in [e.lower() for e in entities]:
                entities.append('Liz')
                logger.info(f"\n[Extraction] Added 'Liz' for identity query")
        
        logger.info(f"\n[Extraction] Found entities: {entities}")
        
        all_results = []
        
        # PHASE 3: Multi-Hop Traversal (if enabled and appropriate)
        if (self.config.graph_traversal.get('enabled', True) and 
            max_hops > 1 and 
            entities):
            
            logger.info(f"\n[Phase 3] Multi-Hop Traversal ({max_hops} hops)")
            traversal_results = self._execute_traversal(entities, max_hops, strategy)
            all_results.extend(traversal_results)
            logger.info(f"  Found {len(traversal_results)} paths via traversal")
        
        # Hybrid Search (always run as baseline/fallback)
        logger.info(f"\n[Hybrid Search] Running with optimized weights")
        hybrid_results = self._execute_hybrid_search(
            query, entities, graph_weight, semantic_weight
        )
        logger.info(f"  Found {len(hybrid_results)} results via hybrid search")
        all_results.extend(hybrid_results)
        
        # Merge and deduplicate
        merged_results = self._merge_and_deduplicate(all_results)
        logger.info(f"  Total unique results: {len(merged_results)}")
        
        # Apply source prioritization based on strategy
        merged_results = self._apply_source_prioritization(merged_results, strategy)
        
        # Apply diversity ranking
        merged_results = self._apply_diversity_ranking(merged_results)
        
        # Apply recency boosting
        merged_results = self._apply_recency_boosting(merged_results)
        
        # -------------------------------------------------------------------
        # PHASE 4: Feedback-Based Re-ranking
        # -------------------------------------------------------------------
        if self._feedback_loop:
            logger.info(f"\n[Phase 4] Applying feedback-based re-ranking")
            merged_results = self._feedback_loop.apply_feedback_ranking(merged_results)
            logger.info(f"  Re-ranked {len(merged_results)} results")
        
        # Calculate contextual relevance scores for tiered injection
        logger.info(f"\n[Tiered Relevance] Scoring {len(merged_results)} results...")
        for result in merged_results:
            result['relevance_score'] = self._calculate_relevance_score(result, query, entities, intent)
        
        # Sort by relevance score (not just hybrid score)
        merged_results.sort(key=lambda r: r.get('relevance_score', 0), reverse=True)
        
        # Get final top results
        max_results = self.config.hybrid_search.get('merging', {}).get('max_final_results', 5)
        final_results = merged_results[:max_results]
        
        # -------------------------------------------------------------------
        # Log Retrieval for Feedback Loop
        # -------------------------------------------------------------------
        event_id = None
        if self._feedback_loop:
            try:
                # Get query vector for feedback logging
                query_vector = None
                try:
                    embedder = self._get_embedder()
                    query_vector = embedder.embed(query)
                except Exception as e:
                    logger.debug(f"Could not embed query for feedback: {e}")
                
                event_id = self._feedback_loop.log_retrieval(
                    query=query,
                    query_vector=query_vector,
                    intent=intent,
                    memories_injected=final_results,
                    graph_weight=graph_weight,
                    semantic_weight=semantic_weight,
                    semantic_threshold=self.config.hybrid_search.get('semantic', {}).get('threshold', 0.75),
                    max_results=max_results,
                    session_id=session_id
                )
                logger.info(f"\n[Feedback] Logged retrieval event: {event_id[:8]}...")
                
                # Store event_id in results for later feedback correlation
                for r in final_results:
                    r['_feedback_event_id'] = event_id

                # Expose metadata for the plugin caller to save an auto-feedback staging file
                self.last_retrieval_metadata = {
                    "event_id": event_id,
                    "query": query,
                    "memories_injected": final_results,
                    "intent": intent
                }
                    
            except Exception as e:
                logger.warning(f"Could not log retrieval: {e}")
        
        # -------------------------------------------------------------------
        # Format and Return
        # -------------------------------------------------------------------
        # Update session context BEFORE formatting (so next query has continuity)
        self._update_session_context(query, entities)
        
        formatted = self.format_results(final_results)
        
        logger.info(f"\n[Output] Returning {len(final_results)} formatted memories")
        logger.info("=" * 70)
        
        return formatted
    
    # ========================================================================
    # PHASE 3: Multi-Hop Traversal Execution
    # ========================================================================
    
    def _execute_traversal(self, entities: List[str], max_hops: int, 
                          strategy: str) -> List[Dict]:
        """
        Execute multi-hop graph traversal.
        
        Args:
            entities: Starting entities
            max_hops: Maximum hops to traverse
            strategy: Retrieval strategy
            
        Returns:
            List of results from traversal paths
        """
        try:
            traversal = self._get_traversal()
            
            # Get traversal config
            trav_config = self.config.graph_traversal
            min_score = trav_config.get('bfs', {}).get('min_path_score', 0.1)
            max_paths = trav_config.get('bfs', {}).get('max_paths_per_entity', 10)
            
            # Execute traversal
            paths = traversal.traverse(
                start_entities=entities,
                max_hops=max_hops,
                min_score=min_score,
                max_paths=max_paths
            )
            
            # Convert paths to result format
            results = []
            for path in paths:
                if path.relations:
                    # Use the last relation as the primary result
                    # but include path context
                    last_rel = path.relations[-1]
                    result = last_rel.copy()
                    result['path_score'] = path.score
                    result['path_hops'] = path.hops
                    result['path_entities'] = path.entities
                    result['search_method'] = 'traversal'
                    result['hybrid_score'] = path.score  # For ranking
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.warning(f"Traversal failed: {e}, falling back to single-hop")
            return []
    
    # ========================================================================
    # HYBRID SEARCH (Refactored to use Config)
    # ========================================================================
    
    def _execute_hybrid_search(self, query: str, entities: List[str],
                               graph_weight: float, 
                               semantic_weight: float) -> List[Dict]:
        """
        Execute hybrid search with configured parameters.
        """
        # Load knowledge graphs
        graphs = self._load_knowledge_graphs()
        
        # Graph search
        graph_results = self._search_graph(entities, graphs)
        
        # Semantic search
        semantic_results = self._search_semantic(query)
        
        # Merge with custom weights
        merged = self._merge_with_weights(graph_results, semantic_results,
                                         graph_weight, semantic_weight)
        
        return merged
    
    def _load_knowledge_graphs(self, days: int = 30) -> List[Dict]:
        """Load knowledge graphs from recent days"""
        graphs = []
        today = datetime.now()
        
        for i in range(days):
            date = today - timedelta(days=i)
            graph_file = self.graph_dir / f"{date.strftime('%Y-%m-%d')}.json"
            
            if graph_file.exists():
                try:
                    with open(graph_file, 'r') as f:
                        graph = json.load(f)
                        graph['source_date'] = date.strftime('%Y-%m-%d')
                        graph['age_days'] = i
                        graphs.append(graph)
                except Exception as e:
                    logger.debug(f"Could not load graph {graph_file}: {e}")
                    continue
        
        return graphs
    
    def _search_graph(self, entities: List[str], 
                     graphs: List[Dict]) -> List[Dict]:
        """Search knowledge graph for entity matches"""
        if not entities or not graphs:
            return []
        
        all_relations = []
        
        # Get thresholds from config
        thresh_config = self.config.hybrid_search.get('graph', {}).get('strength_thresholds', {})
        recent_days = thresh_config.get('recent_days', 7)
        recent_thresh = thresh_config.get('recent_threshold', 0.80)
        medium_days = thresh_config.get('medium_days', 30)
        medium_thresh = thresh_config.get('medium_threshold', 0.65)
        old_thresh = thresh_config.get('old_threshold', 0.50)
        
        for graph in graphs:
            age_days = graph.get('age_days', 0)
            
            # Adaptive threshold based on age
            if age_days <= recent_days:
                min_strength = recent_thresh
            elif age_days <= medium_days:
                min_strength = medium_thresh
            else:
                min_strength = old_thresh
            
            for rel in graph.get('relations', []):
                subject = rel.get('subject', '').lower()
                obj = rel.get('object', '').lower()
                relation_type = rel.get('relation', '').lower()
                evidence = rel.get('evidence', '').lower()
                strength = rel.get('strength', 0.5)
                
                if strength < min_strength:
                    continue
                
                # Calculate match score
                match_score = 0.0
                matched_entities = []
                
                for entity in entities:
                    entity_lower = entity.lower()
                    
                    if entity_lower == subject or entity_lower == obj:
                        match_score += 1.0
                        matched_entities.append(entity)
                    elif entity_lower in subject or entity_lower in obj:
                        match_score += 0.7
                        matched_entities.append(entity)
                    elif entity_lower in relation_type:
                        match_score += 0.5
                        matched_entities.append(entity)
                    elif entity_lower in evidence:
                        match_score += 0.3
                        matched_entities.append(entity)
                
                if match_score > 0:
                    rel_copy = rel.copy()
                    rel_copy['graph_score'] = match_score * strength
                    rel_copy['match_score'] = match_score
                    rel_copy['matched_entities'] = matched_entities
                    rel_copy['source_date'] = graph.get('source_date', 'unknown')
                    rel_copy['age_days'] = age_days
                    rel_copy['search_method'] = 'graph'
                    all_relations.append(rel_copy)
        
        # Sort by score
        all_relations.sort(key=lambda r: r.get('graph_score', 0), reverse=True)
        
        # Limit results
        max_results = self.config.hybrid_search.get('graph', {}).get('max_results', 10)
        return all_relations[:max_results]
    
    def _search_semantic(self, query: str) -> List[Dict]:
        """Search using semantic similarity"""
        try:
            embedder = self._get_embedder()
            qdrant = self._get_qdrant()
            
            # Get query embedding
            query_vector = embedder.embed(query)
            if query_vector is None:
                logger.warning("Failed to embed query for semantic search")
                return []
            
            # Get semantic config
            sem_config = self.config.hybrid_search.get('semantic', {})
            threshold = sem_config.get('threshold', 0.75)
            top_k = sem_config.get('top_k', 10)
            
            # Search Qdrant
            results = qdrant.search_semantic(
                query_vector=query_vector,
                top_k=top_k,
                min_score=threshold
            )
            
            for result in results:
                result['search_method'] = 'semantic'
                result['semantic_score'] = result.get('similarity_score', 0)
            
            return results
            
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []
    
    def _merge_with_weights(self, graph_results: List[Dict],
                           semantic_results: List[Dict],
                           graph_weight: float,
                           semantic_weight: float) -> List[Dict]:
        """Merge results with custom weights"""
        seen = {}
        
        # Process graph results
        for rel in graph_results:
            key = (rel.get('subject', ''), rel.get('relation', ''), rel.get('object', ''))
            graph_score = rel.get('graph_score', 0)
            
            if key not in seen:
                seen[key] = rel.copy()
                seen[key]['hybrid_score'] = graph_score * graph_weight
                seen[key]['search_method'] = 'graph'
            else:
                seen[key]['hybrid_score'] += graph_score * graph_weight
                seen[key]['search_method'] = 'hybrid'
        
        # Process semantic results
        for rel in semantic_results:
            key = (rel.get('subject', ''), rel.get('relation', ''), rel.get('object', ''))
            semantic_score = rel.get('similarity_score', 0)
            
            if key not in seen:
                seen[key] = rel.copy()
                seen[key]['hybrid_score'] = semantic_score * semantic_weight
                seen[key]['search_method'] = 'semantic'
            else:
                existing_score = seen[key].get('hybrid_score', 0)
                boost = semantic_score * semantic_weight
                seen[key]['hybrid_score'] = existing_score + boost
                seen[key]['similarity_score'] = semantic_score
                seen[key]['search_method'] = 'hybrid'
        
        combined = list(seen.values())
        combined.sort(key=lambda r: r.get('hybrid_score', 0), reverse=True)
        
        return combined
    
    def _merge_and_deduplicate(self, results: List[Dict]) -> List[Dict]:
        """Merge results and deduplicate"""
        seen = {}
        key_fields = self.config.hybrid_search.get('merging', {}).get('deduplication', {}).get('key_fields', ['subject', 'relation', 'object'])
        
        for result in results:
            # Create dedup key
            key = tuple(result.get(f, '') for f in key_fields)
            
            if key not in seen:
                seen[key] = result
            else:
                # Keep higher score
                existing_score = seen[key].get('hybrid_score', 0)
                new_score = result.get('hybrid_score', 0)
                if new_score > existing_score:
                    seen[key] = result
        
        combined = list(seen.values())
        combined.sort(key=lambda r: r.get('hybrid_score', 0), reverse=True)
        return combined
    
    # ========================================================================
    # RANKING ENHANCEMENTS (Beyond Original Plan)
    # ========================================================================
    
    def _get_strategy_from_intent(self, intent: str) -> str:
        """Map intent to strategy name"""
        strategy_map = {
            'greeting': 'identity_first',
            'personal_identity': 'identity_first',
            'memory_recall': 'temporal_priority',
            'technical_howto': 'technical_depth',
            'preference_learn': 'preference_extraction',
            'entity_lookup': 'entity_expansion'
        }
        return strategy_map.get(intent, 'hybrid')
    
    def _apply_source_prioritization(self, results: List[Dict], 
                                    strategy: str) -> List[Dict]:
        """
        Apply source prioritization based on strategy.
        
        Beyond original plan: Boosts results from preferred sources.
        """
        strategy_config = self.config.get_strategy_config(strategy)
        source_priority = strategy_config.get('source_priority', [])
        
        if not source_priority:
            return results
        
        # Create priority scores
        priority_scores = {src: len(source_priority) - i 
                          for i, src in enumerate(source_priority)}
        
        for result in results:
            # Determine source type
            if result.get('source_type') == 'context_file':
                source = 'tmr_agents_files'
            else:
                source = 'tmr_knowledge_graph'
            
            # Apply boost based on priority
            priority = priority_scores.get(source, 0)
            if priority > 0:
                boost = 1.0 + (priority * 0.1)  # 10% boost per priority level
                result['hybrid_score'] = result.get('hybrid_score', 0) * boost
                result['source_boost'] = boost
        
        # Re-sort
        results.sort(key=lambda r: r.get('hybrid_score', 0), reverse=True)
        return results
    
    def _apply_diversity_ranking(self, results: List[Dict]) -> List[Dict]:
        """
        Apply diversity ranking to penalize similar results.
        
        Beyond original plan: Prevents redundant similar memories.
        """
        if not results:
            return results
        
        ranking_config = self.config.query_planning.get('ranking', {})
        diversity_penalty = ranking_config.get('diversity_penalty', 0.1)
        max_similarity = ranking_config.get('max_similarity', 0.8)
        
        # Simple diversity: penalize if same subject-object pair
        seen_pairs = set()
        
        for result in results:
            pair = (result.get('subject', ''), result.get('object', ''))
            
            if pair in seen_pairs:
                # Apply penalty
                result['hybrid_score'] = result.get('hybrid_score', 0) * (1 - diversity_penalty)
                result['diversity_penalty'] = True
            else:
                seen_pairs.add(pair)
        
        # Re-sort
        results.sort(key=lambda r: r.get('hybrid_score', 0), reverse=True)
        return results
    
    def _apply_recency_boosting(self, results: List[Dict]) -> List[Dict]:
        """
        Boost recent memories.
        
        Beyond original plan: Time-decay for older memories.
        """
        if not results:
            return results
        
        ranking_config = self.config.query_planning.get('ranking', {})
        recency_days = ranking_config.get('recency_boost_days', 7)
        recency_multiplier = ranking_config.get('recency_multiplier', 1.2)
        
        for result in results:
            age_days = result.get('age_days', 999)
            
            if age_days <= recency_days:
                result['hybrid_score'] = result.get('hybrid_score', 0) * recency_multiplier
                result['recency_boost'] = True
        
        # Re-sort
        results.sort(key=lambda r: r.get('hybrid_score', 0), reverse=True)
        return results
    
    # ========================================================================
    # ENTITY EXTRACTION (From Config)
    # ========================================================================
    
    def extract_entities(self, query: str) -> List[str]:
        """Extract entities from query using config"""
        entities = []
        query_lower = query.lower()
        
        # Proper nouns
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        entities.extend([noun.strip() for noun in proper_nouns])
        
        # Acronyms
        acronyms = re.findall(r'\b[A-Z]{2,}\b', query)
        entities.extend(acronyms)
        
        # Quoted phrases
        quoted = re.findall(r'"([^"]+)"', query)
        entities.extend(quoted)
        
        # Domain keywords from config
        domain_keywords = self.config.entity_extraction.get('domain_keywords', {})
        for domain, keywords in domain_keywords.items():
            if any(kw in query_lower for kw in keywords):
                entities.append(domain)
        
        # Clean and deduplicate
        min_length = self.config.entity_extraction.get('min_length', 2)
        cleaned = []
        seen = set()
        
        for entity in entities:
            entity_clean = entity.strip().lower()
            if (len(entity_clean) >= min_length and 
                entity_clean not in seen):
                cleaned.append(entity_clean)
                seen.add(entity_clean)
        
        return cleaned
    
    # ========================================================================
    # FORMATTING
    # ========================================================================
    
    def _calculate_relevance_score(self, result: Dict, query: str,
                                     query_entities: List[str], intent: str) -> float:
        """
        Calculate contextual relevance score beyond raw semantic similarity.
        
        Factors:
        - Base hybrid score (semantic + graph match)
        - Conversation thread continuity (entity overlap with recent session)
        - Recency (today's memories score higher)
        - Query intent alignment
        
        Returns: score 0.0 - 1.0
        """
        # Base score: use raw similarity (semantic) or match_score (graph), not the weighted hybrid_score
        # hybrid_score is already dampened by intent weights, using it here compounds the reduction
        raw_similarity = result.get('similarity_score', result.get('match_score', result.get('graph_score', 0)))
        base_score = min(raw_similarity, 1.0)
        
        # Thread continuity: boost if memory shares entities with recent session topics
        thread_boost = 0.0
        result_entities = [
            result.get('subject', '').lower(),
            result.get('object', '').lower()
        ]
        result_entities.extend([e.lower() for e in result.get('matched_entities', [])])
        
        for session_entity in self._session_recent_entities:
            if any(session_entity in re for re in result_entities):
                thread_boost += 0.15  # Significant boost for thread continuity
        thread_boost = min(thread_boost, 0.45)  # Cap thread boost
        
        # Recency boost (today = +0.2, this week = +0.1)
        recency_boost = 0.0
        age_days = result.get('age_days', result.get('days_old', 999))
        if age_days <= 1:
            recency_boost = 0.2
        elif age_days <= 3:
            recency_boost = 0.1
        elif age_days <= 7:
            recency_boost = 0.05
        
        # Intent alignment (boost if memory type matches query intent)
        intent_boost = 0.0
        relation = result.get('relation', '').upper()
        if intent == 'preference_learn' and relation in ('LIKES', 'DISLIKES', 'PREFERS'):
            intent_boost = 0.1
        elif intent == 'memory_recall' and relation in ('DISCUSSED', 'DECIDED', 'REMEMBERED'):
            intent_boost = 0.1
        elif intent == 'technical_howto' and relation in ('FIXED', 'CONFIGURES', 'USES'):
            intent_boost = 0.1
        
        # Combine: raw similarity weighted + boosts
        relevance = base_score * 0.7 + thread_boost + recency_boost + intent_boost * 0.5
        relevance = min(relevance, 1.0)
        
        logger.debug(f"Relevance: base={base_score:.2f} thread={thread_boost:.2f} "
                     f"recency={recency_boost:.2f} intent={intent_boost:.2f} -> {relevance:.2f}")
        return relevance
    
    def _update_session_context(self, query: str, entities: List[str]):
        """Track recent query entities for conversation thread continuity."""
        self._session_recent_queries.append(query)
        if len(self._session_recent_queries) > self._session_max_history:
            self._session_recent_queries.pop(0)
        
        # Add new entities, deduplicate
        for entity in entities:
            entity_lower = entity.lower()
            if entity_lower not in self._session_recent_entities:
                self._session_recent_entities.append(entity_lower)
        
        # Keep only last N entities
        max_entities = self._session_max_history * 3
        if len(self._session_recent_entities) > max_entities:
            self._session_recent_entities = self._session_recent_entities[-max_entities:]
    
    def format_results(self, results: List[Dict]) -> str:
        """
        Format search results as tiered injection.
        
        Tier 1 (relevance >= 0.75): Full summary + metadata + source
        Tier 2 (0.45 <= relevance < 0.75): Reference only (file:line + hint)
        Tier 3 (relevance < 0.45): Skip entirely
        """
        if not results:
            return ""
        
        tier1 = []  # Full injection
        tier2 = []  # Reference only
        
        for rel in results:
            score = rel.get('relevance_score', 0)
            if score >= 0.75:
                tier1.append(rel)
            elif score >= 0.45:
                tier2.append(rel)
        
        if not tier1 and not tier2:
            return ""
        
        lines = ["", "[RELATED MEMORY - TMR]", ""]
        
        # Tier 1: Full summaries (highly relevant)
        if tier1:
            lines.append("From previous conversations:")
            lines.append("")
            
            for i, rel in enumerate(tier1, 1):
                summary = rel.get('summary', '').strip()
                if not summary:
                    subject = rel.get('subject', 'Unknown')
                    relation = rel.get('relation', 'RELATED_TO')
                    obj = rel.get('object', 'something').strip('"')
                    summary = f"{subject} {relation.lower()} {obj}."
                
                strength = rel.get('strength', 0.5)
                search_method = rel.get('search_method', 'unknown').upper()
                relevance = rel.get('relevance_score', 0)
                
                source = rel.get('source', {})
                if isinstance(source, dict):
                    source_file = source.get('file', rel.get('source_file', 'unknown'))
                    line_start = source.get('line_start', rel.get('line_start', 0))
                    line_end = source.get('line_end', rel.get('line_end', line_start))
                else:
                    source_file = str(source) if source else 'unknown'
                    line_start = rel.get('line_start', 0)
                    line_end = rel.get('line_end', line_start)
                
                if source_file.startswith('/home/openclaw/.openclaw/workspace/'):
                    source_file = source_file.replace('/home/openclaw/.openclaw/workspace/', '')
                
                meta_parts = [f"conf: {strength:.0%}", f"rel: {relevance:.2f}"]
                meta_parts.append(f"method: {search_method}")
                
                lines.append(f"{i}. {summary}")
                lines.append(f"   ({', '.join(meta_parts)})")
                if line_end > line_start:
                    lines.append(f"   [Source: {source_file}:{line_start}-{line_end}]")
                else:
                    lines.append(f"   [Source: {source_file}:{line_start}]")
                lines.append("")
        
        # Tier 2: References only (possibly relevant)
        if tier2:
            if tier1:
                lines.append("Also referenced (fetch if needed):")
            else:
                lines.append("From previous conversations:")
            lines.append("")
            
            for i, rel in enumerate(tier2, len(tier1) + 1):
                # Build a short hint from the memory
                hint = rel.get('summary', '').strip()
                if not hint:
                    subject = rel.get('subject', '?')
                    obj = rel.get('object', '?')
                    hint = f"{subject} → {obj}"
                else:
                    # Truncate to ~8 words for hint
                    words = hint.split()[:8]
                    hint = ' '.join(words)
                    if len(hint.split()) > 8:
                        hint += "..."
                
                relevance = rel.get('relevance_score', 0)
                
                source = rel.get('source', {})
                if isinstance(source, dict):
                    source_file = source.get('file', rel.get('source_file', 'unknown'))
                    line_start = source.get('line_start', rel.get('line_start', 0))
                    line_end = source.get('line_end', rel.get('line_end', line_start))
                else:
                    source_file = str(source) if source else 'unknown'
                    line_start = rel.get('line_start', 0)
                    line_end = rel.get('line_end', line_start)
                
                if source_file.startswith('/home/openclaw/.openclaw/workspace/'):
                    source_file = source_file.replace('/home/openclaw/.openclaw/workspace/', '')
                
                ref = f"{source_file}:{line_start}" if line_start else source_file
                lines.append(f"{i}. [{ref}] — {hint} (rel: {relevance:.2f})")
            lines.append("")
        
        lines.append("[END RELATED MEMORY]")
        lines.append("")
        
        return "\n".join(lines)
    
    # ========================================================================
    # FEEDBACK INTERFACE
    # ========================================================================
    
    def report_feedback(self, event_id: str, signal_type: str,
                       messages_since: int = 0) -> bool:
        """
        Report feedback for a retrieval event.
        
        Args:
            event_id: The feedback event ID
            signal_type: One of the FeedbackSignal values
            messages_since: Number of messages since retrieval
            
        Returns:
            True if feedback was recorded
        """
        if not self._feedback_loop:
            logger.warning("Feedback loop not available")
            return False
        
        try:
            signal = FeedbackSignal(signal_type)
            self._feedback_loop.record_feedback(event_id, signal, messages_since)
            logger.info(f"Recorded feedback: {signal_type} for event {event_id[:8]}")
            return True
        except (ValueError, Exception) as e:
            logger.warning(f"Could not record feedback: {e}")
            return False
    
    def detect_implicit_feedback(self, query: str, 
                                conversation_history: List[Dict]) -> Optional[Tuple[str, FeedbackSignal]]:
        """
        Detect implicit feedback from conversation.
        
        Args:
            query: Current query
            conversation_history: Recent conversation
            
        Returns:
            Tuple of (event_id, signal) if detected, None otherwise
        """
        if not self._feedback_loop:
            return None
        
        return self._feedback_loop.detect_implicit_feedback(query, conversation_history)
    
    def get_analytics(self, days: int = 7) -> Dict:
        """Get feedback loop analytics"""
        if self._feedback_loop:
            return self._feedback_loop.get_analytics(days)
        return {"error": "Feedback loop not enabled"}


# Legacy alias for compatibility
HybridSearchInjector = TMRCogneeInjector


if __name__ == "__main__":
    # Simple test
    print("Testing TMR v2 Cognee-Style Injector...")
    print("=" * 70)
    
    # Create injector
    injector = TMRCogneeInjector()
    
    # Test queries
    test_queries = [
        "How are you?",
        "What did we discuss yesterday?",
        "Where should I eat?",
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        context = injector.inject_context(query)
        print(context[:500] + "..." if len(context) > 500 else context)
    
    print("\n" + "=" * 70)
    print("Test complete!")
