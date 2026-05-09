# TMR v2: Final Implementation Documentation
## Complete Cognee-Style GraphRAG System with Real-Time Memory

**Version:** 2.0 Final  
**Status:** Production Ready (Legacy)  
**Date:** 2026-03-18  
**Architecture:** Cognee-Style GraphRAG with Self-Improvement

---

> **📢 TMR v3 Design Available**  
> This document describes the current (v2) implementation.  
> See [`documentation/v2/DOCUMENTATION_V2.md`](../v2/DOCUMENTATION_V2.md) for the next-generation architecture with two-layer memory, consolidation engine, and improved injection.

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Component Reference](#3-component-reference)
4. [Data Flow](#4-data-flow)
5. [Configuration](#5-configuration)
6. [Logging & Monitoring](#6-logging--monitoring)
7. [Inspection Routine](#7-inspection-routine)

---

## 1. EXECUTIVE SUMMARY

### What Is TMR v2?

**True Memory Recall (TMR) v2** is a production-ready knowledge graph memory system that provides AI assistants with persistent, contextual memory across sessions. It implements a full Cognee-style GraphRAG pipeline with real-time capabilities.

### Key Features

| Feature | Description |
|---------|-------------|
| **Intent-Aware Retrieval** | 6 intent types with custom weights and strategies |
| **Multi-Hop Traversal** | BFS graph traversal (1-4 hops) for deep connections |
| **Real-Time Buffering** | 2-hour max latency (12x improvement over daily) |
| **Self-Improvement** | Feedback loop that learns from retrieval outcomes |
| **Source Prioritization** | Identity files prioritized for personality queries |
| **Diversity Ranking** | Prevents redundant similar results |
| **Recency Boosting** | Recent conversations naturally prioritized |

### Success Metrics (Achieved)

| Query | Expected Result | Status |
|-------|----------------|--------|
| "How are you?" | Liz personality from SOUL.md | ✅ Working |
| "Where should I eat?" | Marcello's, carbonara preference | ✅ Working |
| "What did we discuss?" | Actual conversation topics | ✅ Working |
| "Who are you?" | SOUL.md content | ✅ Working |
| "Fix TMR logging" | Logging architecture | ✅ Working |

---

## 2. SYSTEM ARCHITECTURE

### 2.1 High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STAGE 1: CAPTURE & BUFFER                          │
│                         (Real-time, Zero LLM Cost)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User Message ──▶ MessageBuffer ──▶ Temp File ──▶ (Trigger) ──▶ Raw File  │
│                                                                             │
│   Triggers:                                                                 │
│   - 70% context limit (~28K chars)                                         │
│   - >60 min time gap                                                       │
│   - Session change (Uddipta ↔ Liz)                                         │
│   - 2-hour cron flush                                                      │
│                                                                             │
│   Output: ~/.openclaw/workspace/memory/raw/YYYY-MM-DD (NN).md              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Every 2 hours (cron)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      STAGE 2: EXTRACTION & INDEXING                        │
│                   (Qwen via OpenRouter + Ollama Embeddings)                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Raw Files ──▶ Qwen Extractor ──▶ Relations ──▶ Qdrant                     │
│              │                     Embeddings ──▶ Qdrant                    │
│              │                                                              │
│   Hash Check ─┘  (Only new/changed files via incremental_extractor.py)     │
│                                                                             │
│   Collections:                                                              │
│   - tmr_knowledge_graph (conversation relations)                           │
│   - tmr_agents_files (context file relations)                              │
│   - tmr_semantic_vectors (embeddings for semantic search)                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ On Every Query
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAGE 3: COGNEE-STYLE RETRIEVAL                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Query ──▶ [Phase 1] Intent Classification ──▶ intent + confidence        │
│                              ↓                                              │
│                    [Phase 2] Query Planning ──▶ strategy + weights         │
│                              ↓                                              │
│   Entities ──▶ [Phase 3] Multi-Hop Traversal (if max_hops > 1) ──▶ paths   │
│                              ↓                                              │
│                    [Phase 4] Feedback Ranking ──▶ boosted results          │
│                              ↓                                              │
│   Hybrid Search (semantic + graph) ──▶ merged results                       │
│                              ↓                                              │
│   Source Prioritization ──▶ Diversity ──▶ Recency ──▶ Final Results        │
│                              ↓                                              │
│                    Format ──▶ Inject ──▶ Log for Learning                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Phase Breakdown

#### Phase 1: Intent Classification
- **File:** `src/intent_classifier.py`
- **Purpose:** Detect query type for dynamic retrieval strategy
- **Intents:** greeting, personal_identity, memory_recall, technical_howto, preference_learn, entity_lookup
- **Output:** (intent_name, confidence_score)

#### Phase 2: Query Planning
- **File:** `src/query_planner.py`
- **Purpose:** Create execution plan based on intent
- **Strategies:** identity_first, temporal_priority, technical_depth, preference_extraction, entity_expansion, hybrid
- **Output:** RetrievalPlan with 4 execution steps

#### Phase 3: Multi-Hop Graph Traversal
- **File:** `src/graph_traversal.py`
- **Purpose:** Find deep connections via BFS
- **Algorithm:** Breadth-first search with cycle detection
- **Output:** List[GraphPath] ranked by accumulated score

#### Phase 4: Feedback Loop & Ranking
- **File:** `src/feedback_loop.py`
- **Purpose:** Learn from retrieval outcomes
- **Features:** Bayesian usefulness scoring, weight adaptation, re-ranking
- **Output:** Re-ranked results with performance tracking

#### Phase 5: Tiered Context Injection (Added 2026-05-05)
- **File:** `src/tmr_injector.py` (`format_results()`, `_calculate_relevance_score()`)
- **Purpose:** Inject only the most relevant memories; reduce context bloat
- **Features:**
  - Composite relevance scoring beyond raw semantic similarity
  - Session-level thread tracking for conversation continuity
  - Three-tier output: full summary, reference-only, or skip
- **Output:** Tiered memory block with high-relevance summaries + low-relevance references

**Relevance Factors:**

| Factor | Weight | Description |
|--------|--------|-------------|
| Base hybrid score | 60% | Semantic + graph match |
| Thread continuity | Up to +0.45 | Boost if memory shares entities with recent session topics |
| Recency | Up to +0.20 | Today's memories get biggest boost |
| Intent alignment | +0.10 | Boost if relation type matches query intent |

**Tier Thresholds:**

| Tier | Relevance | Injected Format |
|------|-----------|-----------------|
| Tier 1 | ≥ 0.75 | Full narrative summary + metadata + source line |
| Tier 2 | 0.45 – 0.74 | Reference only: `file:line — hint (rel: score)` |
| Tier 3 | < 0.45 | Silently skipped |

**Session Context Tracking:**
- `_session_recent_entities` tracks entities from last 10 queries
- `_session_recent_queries` maintains conversation thread state
- Thread continuity has **massive impact** on ranking — if we're discussing "API keys" and you ask "what about that error?", the API key error memory jumps to Tier 1

---

## 3. COMPONENT REFERENCE

### 3.1 Core Components

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| **TMRCogneeInjector** | `src/tmr_injector.py` | Main orchestrator (Phases 1-4) | ✅ Active |
| **IntentClassifier** | `src/intent_classifier.py` | Phase 1: Intent detection | ✅ Active |
| **QueryPlanner** | `src/query_planner.py` | Phase 2: Strategy planning | ✅ Active |
| **MultiHopTraversal** | `src/graph_traversal.py` | Phase 3: BFS traversal | ✅ Active |
| **CogneeStyleFeedbackLoop** | `src/feedback_loop.py` | Phase 4: Self-improvement | ✅ Active |
| **MessageBuffer** | `src/message_buffer.py` | Real-time message buffering | ✅ Active |
| **TMRSessionIntegration** | `src/tmr_session_integration.py` | OpenClaw integration | ✅ Active |
| **QdrantManager** | `src/qdrant_manager.py` | Vector database operations | ✅ Active |
| **OllamaEmbedder** | `src/embedder.py` | Local embeddings | ✅ Active |
| **QwenExtractor** | `src/extractor.py` | LLM knowledge extraction | ✅ Active |

### 3.2 Support Components

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| **ConfigLoader** | `src/config_loader.py` | Centralized configuration | ✅ Active |
| **MessageFilter** | `src/filter.py` | Message filtering | ✅ Active |
| **DailyStorage** | `src/storage.py` | Daily file writer | ✅ Active (legacy) |
| **IncrementalExtractor** | `scripts/incremental_extractor.py` | 2-hour extraction | ✅ Active |

### 3.3 TypeScript Integration

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| **Plugin Entry** | `index.ts` | OpenClaw hooks | ✅ Active |
| **QMDMemoryPlugin** | `src/plugin.py` | Python plugin entry | ✅ Active |

### 3.4 Configuration Files

| File | Purpose | Location |
|------|---------|----------|
| **tmr_config.yaml** | All tunable parameters | `config/tmr_config.yaml` |
| **crontab.txt** | Cron job schedule | `config/crontab.txt` |
| **.env** | API keys (OpenRouter) | `~/.openclaw/extensions/TrueMemoryRecall/.env` |

### 3.5 Test Files

| File | Purpose | Tests |
|------|---------|-------|
| **test_intent_classifier.py** | Intent classification tests | 23 |
| **test_query_planner.py** | Query planning tests | 6 |
| **test_graph_traversal.py** | Graph traversal tests | 6 |
| **test_feedback_loop.py** | Feedback loop tests | 14 |
| **Total** | | **49** |

**All 49 tests passing ✅**

---

## 4. DATA FLOW

### 4.1 Message Flow

```
User Message
    ↓
MessageBuffer (temp file)
    ↓
Trigger Met (70% / 60min / session change / 2hr)
    ↓
Raw File (YYYY-MM-DD (NN).md)
    ↓
Incremental Extractor (every 2 hours)
    ↓
Qwen Extraction
    ↓
Qdrant Storage (relations + embeddings)
    ↓
Indexed for Search
```

### 4.2 Query Flow

```
User Query
    ↓
[Phase 1] Intent Classification → intent + confidence
    ↓
[Phase 2] Query Planning → strategy + weights
    ↓
[Phase 3] Graph Traversal (if max_hops > 1)
    ↓
Hybrid Search (graph + semantic)
    ↓
Source Prioritization → Diversity → Recency
    ↓
[Phase 4] Feedback Ranking
    ↓
Format Results
    ↓
Inject into LLM Context
    ↓
Log for Learning
```

### 4.3 Directory Structure

```
~/.openclaw/extensions/TrueMemoryRecall/
├── src/
│   ├── tmr_injector.py          # Main orchestrator
│   ├── intent_classifier.py     # Phase 1
│   ├── query_planner.py         # Phase 2
│   ├── graph_traversal.py       # Phase 3
│   ├── feedback_loop.py         # Phase 4
│   ├── message_buffer.py        # Real-time buffering
│   ├── tmr_session_integration.py # OpenClaw integration
│   ├── qdrant_manager.py        # Qdrant operations
│   ├── embedder.py              # Ollama embeddings
│   ├── extractor.py             # Qwen extraction
│   ├── config_loader.py         # Configuration
│   ├── filter.py                # Message filtering
│   ├── storage.py               # Daily storage (legacy)
│   └── plugin.py                # Plugin entry
├── scripts/
│   ├── incremental_extractor.py # 2-hour extraction
│   ├── openclaw_integration_demo.py # Integration example
│   └── full_reextract.py        # Force re-extraction
├── config/
│   ├── tmr_config.yaml          # All parameters
│   └── crontab.txt              # Cron schedule
├── tests/
│   ├── test_intent_classifier.py
│   ├── test_query_planner.py
│   ├── test_graph_traversal.py
│   └── test_feedback_loop.py
├── logs/                        # All TMR logs
│   ├── tmr.log                  # Main plugin log
│   ├── tmr_injection_detail.log # Detailed injections
│   ├── last_injection.md        # Last injection visible
│   ├── extraction.log           # Extraction process
│   ├── cron.log                 # Cron job log
│   └── buffer.log               # Buffer flush log
└── temp/                        # Message buffer temp files

~/.openclaw/workspace/memory/
├── raw/                         # Conversation files
│   └── YYYY-MM-DD (NN).md
├── graph/                       # Knowledge graphs
│   └── YYYY-MM-DD.json
└── feedback/                    # Feedback loop data
    └── memory_performance.json
```

---

## 5. CONFIGURATION

### 5.1 Key Parameters (tmr_config.yaml)

```yaml
# Context Limits
extraction:
  context_limit: 28000  # 70% of ~40K context

# Flush Triggers
buffer_flush:
  max_gap_minutes: 60
  context_percentage: 70

# Intent Weights
feedback_loop:
  default_weights:
    greeting:
      graph: 0.1
      semantic: 0.9
    technical_howto:
      graph: 0.7
      semantic: 0.3

# Extraction Schedule
cron:
  incremental: "0 */2 * * *"  # Every 2 hours
  force_flush: "30 */2 * * *"  # Every 2 hours (offset)
  full_reextract: "0 3 * * *"  # Daily at 3 AM
```

### 5.2 Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `OPENROUTER_API_KEY` | LLM extraction | Yes |
| `QDRANT_HOST` | Vector DB host | Optional (default: localhost) |
| `QDRANT_PORT` | Vector DB port | Optional (default: 6333) |

---

## 6. LOGGING & MONITORING

### 6.1 Log Locations

| Log | Location | Purpose |
|-----|----------|---------|
| **Main Plugin Log** | `logs/tmr.log` | All plugin operations |
| **Injection Detail** | `logs/tmr_injection_detail.log` | Detailed injection logs |
| **Last Injection** | `logs/last_injection.md` | Visible last injection |
| **Extraction** | `logs/extraction.log` | 2-hour extraction process |
| **Cron** | `logs/cron.log` | Cron job execution |
| **Buffer** | `logs/buffer.log` | Buffer flush events |
| **Session Integration** | `~/.openclaw/workspace/memory/feedback/tmr_detailed.log` | Session-level details |

### 6.2 What's Logged

**Every User Message:**
- Timestamp (IST)
- Username
- Session ID
- Full message content

**Intent Classification:**
- Detected intent
- Confidence score
- Patterns matched

**Retrieved Memories:**
- Subject → Relation → Object
- Confidence level
- Evidence text
- Source file + line number
- Search method
- Hybrid score
- Feedback boost

**Summary:**
- Total memories retrieved
- Final count after ranking
- Processing time (ms)

### 6.3 Feedback Model: Current vs Planned

**Current state:**
- Retrieval events are logged automatically.
- Injected memories are stored in feedback event history.
- The system can accept feedback signals (`query_answered`, `memory_referenced`, `user_corrected`, etc.).
- `logs/last_injection.md` is a plugin-side debugging artifact that shows the last injected memory block for inspection.

**Important limitation right now:**
- The feedback loop is **not yet fully auto-wired** to the final assistant response.
- That means the system logs retrievals and can score memories, but it does **not yet automatically judge every response and submit feedback without an explicit integration step**.

**Planned next improvement:**
- Add AI-generated implicit feedback after each response.
- Compare:
  1. user query
  2. injected memories
  3. actual assistant response
- Then automatically mark memories as:
  - helpful / referenced
  - weakly useful
  - ignored / likely irrelevant

**Design note:**
- The intended long-term UX is that the assistant handles most feedback automatically.
- User-visible thumbs-up/down can be added later, but should be optional rather than required.
- `last_injection.md` exists only for debugging and transparency; it is not meant to be the primary feedback UI.

---

## 7. INSPECTION ROUTINE

### 7.1 Pre-Flight Checklist

Use this routine to verify the entire system is operational.

#### Step 1: Directory Structure Verification

```bash
# Check plugin directory exists
test -d ~/.openclaw/extensions/TrueMemoryRecall && echo "✅ Plugin directory exists" || echo "❌ Plugin directory missing"

# Check all required subdirectories
test -d ~/.openclaw/extensions/TrueMemoryRecall/src && echo "✅ src/ exists"
test -d ~/.openclaw/extensions/TrueMemoryRecall/config && echo "✅ config/ exists"
test -d ~/.openclaw/extensions/TrueMemoryRecall/logs && echo "✅ logs/ exists"
test -d ~/.openclaw/extensions/TrueMemoryRecall/tests && echo "✅ tests/ exists"
test -d ~/.openclaw/extensions/TrueMemoryRecall/temp && echo "✅ temp/ exists"
test -d ~/.openclaw/workspace/memory/raw && echo "✅ memory/raw/ exists"
test -d ~/.openclaw/workspace/memory/graph && echo "✅ memory/graph/ exists"
test -d ~/.openclaw/workspace/memory/feedback && echo "✅ memory/feedback/ exists"
```

#### Step 2: Core Files Verification

```bash
# Check all core Python files exist
cd ~/.openclaw/extensions/TrueMemoryRecall/src

test -f tmr_injector.py && echo "✅ tmr_injector.py" || echo "❌ tmr_injector.py missing"
test -f intent_classifier.py && echo "✅ intent_classifier.py" || echo "❌ missing"
test -f query_planner.py && echo "✅ query_planner.py" || echo "❌ missing"
test -f graph_traversal.py && echo "✅ graph_traversal.py" || echo "❌ missing"
test -f feedback_loop.py && echo "✅ feedback_loop.py" || echo "❌ missing"
test -f message_buffer.py && echo "✅ message_buffer.py" || echo "❌ missing"
test -f tmr_session_integration.py && echo "✅ tmr_session_integration.py" || echo "❌ missing"
test -f config_loader.py && echo "✅ config_loader.py" || echo "❌ missing"
test -f qdrant_manager.py && echo "✅ qdrant_manager.py" || echo "❌ missing"
test -f embedder.py && echo "✅ embedder.py" || echo "❌ missing"
test -f extractor.py && echo "✅ extractor.py" || echo "❌ missing"
test -f plugin.py && echo "✅ plugin.py" || echo "❌ missing"

# Check configuration
test -f ../config/tmr_config.yaml && echo "✅ tmr_config.yaml" || echo "❌ missing"
```

#### Step 3: Dependencies Verification

```bash
# Check Python packages
python3 -c "import qdrant_client; print('✅ qdrant_client')" 2>/dev/null || echo "❌ qdrant_client missing"
python3 -c "import yaml; print('✅ pyyaml')" 2>/dev/null || echo "❌ pyyaml missing"
python3 -c "import requests; print('✅ requests')" 2>/dev/null || echo "❌ requests missing"

# Check external services
curl -s http://localhost:6333/healthz > /dev/null && echo "✅ Qdrant running" || echo "❌ Qdrant not running"
curl -s http://192.168.1.100:11434/api/tags > /dev/null && echo "✅ Ollama running" || echo "❌ Ollama not running"
```

#### Step 4: Qdrant Collections Verification

```bash
# Check all collections exist
collections=$(curl -s http://localhost:6333/collections | jq -r '.result.collections[].name')

echo "$collections" | grep -q "tmr_knowledge_graph" && echo "✅ tmr_knowledge_graph" || echo "❌ missing"
echo "$collections" | grep -q "tmr_semantic_vectors" && echo "✅ tmr_semantic_vectors" || echo "❌ missing"
echo "$collections" | grep -q "tmr_agents_files" && echo "✅ tmr_agents_files" || echo "❌ missing"

# Check point counts
echo "Collection point counts:"
curl -s http://localhost:6333/collections/tmr_knowledge_graph | jq '.result.points_count'
curl -s http://localhost:6333/collections/tmr_semantic_vectors | jq '.result.points_count'
curl -s http://localhost:6333/collections/tmr_agents_files | jq '.result.points_count'
```

#### Step 5: Configuration Verification

```bash
cd ~/.openclaw/extensions/TrueMemoryRecall

# Check config loads
python3 -c "
from src.config_loader import get_config
c = get_config()
print('✅ Config loads successfully')
print(f'   Graph dir: {c.storage.get(\"graph_dir\")}')
print(f'   Raw dir: {c.storage.get(\"raw_dir\")}')
print(f'   Intents: {len(c.get_all_intents())} configured')
"
```

#### Step 6: Component Initialization Verification

```bash
cd ~/.openclaw/extensions/TrueMemoryRecall

# Test each component
python3 -c "
from src.intent_classifier import IntentClassifier
c = IntentClassifier()
i, conf = c.classify('test')
print(f'✅ IntentClassifier works (intent: {i}, conf: {conf})')
" 2>&1 | grep "✅"

python3 -c "
from src.query_planner import QueryPlanner
p = QueryPlanner()
plan = p.plan('test', 'greeting', 0.9, {'graph': 0.4, 'semantic': 0.6})
print(f'✅ QueryPlanner works ({plan.get_step_count()} steps)')
" 2>&1 | grep "✅"

python3 -c "
from src.graph_traversal import MultiHopTraversal
from src.qdrant_manager import QdrantManager
q = QdrantManager()
t = MultiHopTraversal(q)
print('✅ GraphTraversal initializes')
" 2>&1 | grep "✅"

python3 -c "
from src.feedback_loop import CogneeStyleFeedbackLoop
f = CogneeStyleFeedbackLoop()
print('✅ FeedbackLoop initializes')
" 2>&1 | grep "✅"

python3 -c "
from src.message_buffer import MessageBuffer
b = MessageBuffer()
print('✅ MessageBuffer initializes')
" 2>&1 | grep "✅"
```

#### Step 7: Full Integration Test

```bash
cd ~/.openclaw/extensions/TrueMemoryRecall

python3 -c "
import sys
sys.path.insert(0, 'src')
from tmr_injector import TMRCogneeInjector

print('Testing full integration...')
injector = TMRCogneeInjector(enable_feedback=True)

# Test query
result = injector.inject_context('How are you?')
memories = result.count('→') if result else 0

print(f'✅ Full pipeline works ({memories} memories retrieved)')
" 2>&1 | grep "✅"
```

#### Step 8: Cron Job Verification

```bash
# Check cron jobs installed
crontab -l | grep -q "incremental_extractor" && echo "✅ Incremental extractor cron installed" || echo "❌ Missing"
crontab -l | grep -q "time_based_flush" && echo "✅ Buffer flush cron installed" || echo "❌ Missing"

# Check schedule
echo "Current cron schedule:"
crontab -l | grep -E "^#|^\d"
```

#### Step 9: Log Files Verification

```bash
cd ~/.openclaw/extensions/TrueMemoryRecall/logs

test -f tmr.log && echo "✅ tmr.log exists" || echo "❌ missing"
test -f last_injection.md && echo "✅ last_injection.md exists" || echo "❌ missing"

# Check log sizes
echo "Log file sizes:"
du -h *.log *.md 2>/dev/null | sort -h

# Check recent activity
echo "Last 5 log entries:"
tail -5 tmr.log 2>/dev/null | head -5
```

#### Step 10: Test Suite Verification

```bash
cd ~/.openclaw/extensions/TrueMemoryRecall

# Run all tests
python3 tests/test_intent_classifier.py 2>&1 | tail -1
python3 tests/test_query_planner.py 2>&1 | tail -1
python3 tests/test_graph_traversal.py 2>&1 | tail -1
python3 tests/test_feedback_loop.py 2>&1 | tail -1
```

### 7.2 Runtime Verification

After startup, verify these continuously:

#### Check Message Buffering

```bash
# Check buffer stats
python3 -c "
from src.message_buffer import get_message_buffer
b = get_message_buffer()
s = b.get_stats()
print(f'Buffer utilization: {s[\"utilization\"]:.1%}')
print(f'Sequence: {s[\"sequence\"]}')
print(f'Time since flush: {s[\"time_since_flush_hours\"]:.1f}h')
"
```

#### Check Recent Extractions

```bash
# Check extraction log
tail -20 ~/.openclaw/extensions/TrueMemoryRecall/logs/extraction.log

# Check for errors
grep -i "error\|failed" ~/.openclaw/extensions/TrueMemoryRecall/logs/extraction.log | tail -5
```

#### Check Memory Injection

```bash
# Check last injection
cat ~/.openclaw/extensions/TrueMemoryRecall/logs/last_injection.md

# Check injection detail
tail -50 ~/.openclaw/extensions/TrueMemoryRecall/logs/tmr_injection_detail.log
```

### 7.3 Debugging Common Issues

#### Issue: No memories retrieved

```bash
# 1. Check Qdrant has data
curl -s http://localhost:6333/collections/tmr_knowledge_graph | jq '.result.points_count'

# 2. Check extraction ran recently
ls -lt ~/.openclaw/workspace/memory/graph/*.json | head -3

# 3. Check for extraction errors
tail -50 ~/.openclaw/extensions/TrueMemoryRecall/logs/extraction.log | grep -i error
```

#### Issue: Intent classification wrong

```bash
# Test classification
python3 -c "
from src.intent_classifier import IntentClassifier
c = IntentClassifier()
queries = ['How are you?', 'Fix the bug', 'What did we discuss?']
for q in queries:
    i, conf = c.classify(q)
    print(f'{q} -> {i} ({conf:.2f})')
"
```

#### Issue: Processing too slow

```bash
# Check processing time in logs
grep "Processing time" ~/.openclaw/extensions/TrueMemoryRecall/logs/tmr.log | tail -5

# Check Qdrant response time
time curl -s http://localhost:6333/collections/tmr_knowledge_graph > /dev/null
```

### 7.4 Maintenance Checklist

**Daily:**
- [ ] Check extraction log for errors
- [ ] Verify last_injection.md updated
- [ ] Monitor log file sizes

**Weekly:**
- [ ] Run full test suite
- [ ] Check Qdrant collection sizes
- [ ] Review feedback loop analytics
- [ ] Archive old logs

**Monthly:**
- [ ] Tune intent weights based on usage
- [ ] Update intent patterns if needed
- [ ] Performance benchmark
- [ ] Dependency updates

---

## APPENDIX

### A. Quick Reference Commands

```bash
# Full system test
cd ~/.openclaw/extensions/TrueMemoryRecall && python3 tests/test_intent_classifier.py && python3 tests/test_query_planner.py && python3 tests/test_graph_traversal.py && python3 tests/test_feedback_loop.py

# Check all logs
tail -f ~/.openclaw/extensions/TrueMemoryRecall/logs/*.log

# Force extraction
python3 scripts/incremental_extractor.py --force

# Check Qdrant
curl http://localhost:6333/collections | jq '.result.collections[].name'

# View last injection
cat ~/.openclaw/extensions/TrueMemoryRecall/logs/last_injection.md
```

### B. File Size Guidelines

| File/Dir | Max Size | Action if Exceeded |
|----------|----------|-------------------|
| tmr.log | 100MB | Archive and rotate |
| tmr_injection_detail.log | 500MB | Archive and rotate |
| memory/raw/ | 1GB per file | Archive old files |
| memory/graph/ | 100MB total | Compress old graphs |
| logs/ | 2GB total | Clean up old logs |

### C. Performance Targets

| Metric | Target | Acceptable |
|--------|--------|------------|
| Query latency | <1000ms | <2000ms |
| Intent classification | <50ms | <100ms |
| Graph search | <500ms | <1000ms |
| Semantic search | <800ms | <1500ms |
| Total retrieval | <1500ms | <2500ms |

### D. Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| TMR-E001 | Qdrant connection failed | Check Qdrant service |
| TMR-E002 | Ollama connection failed | Check Ollama service |
| TMR-E003 | Extraction failed | Check API key, retry |
| TMR-E004 | Intent classification failed | Check patterns config |
| TMR-E005 | Buffer flush failed | Check disk space |

---

**Documentation Version:** 2.1  
**Last Updated:** 2026-05-05  
**Maintained by:** Liz 🦎
