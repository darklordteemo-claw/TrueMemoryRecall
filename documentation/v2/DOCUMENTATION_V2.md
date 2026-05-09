# TMR v3: Two-Layer Memory Architecture
## Next-Generation Design for Context-Aware Memory Injection

**Version:** 3.0 (Design)  
**Status:** Design Phase  
**Date:** 2026-05-09  
**Architecture:** Two-Layer Memory with Consolidation Engine

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [The Problem with V2](#2-the-problem-with-v2)
3. [Two-Layer Architecture](#3-two-layer-architecture)
4. [Layer 1: Raw Memory (Source of Truth)](#4-layer-1-raw-memory-source-of-truth)
5. [Layer 2: Processed Memory (For Injection)](#5-layer-2-processed-memory-for-injection)
6. [Consolidation Engine](#6-consolidation-engine)
7. [Richer Memory Format](#7-richer-memory-format)
8. [Improved Injection Strategy](#8-improved-injection-strategy)
9. [Implementation Plan](#9-implementation-plan)
10. [Comparison with Other Systems](#10-comparison-with-other-systems)
11. [Glossary](#11-glossary)

---

## 1. EXECUTIVE SUMMARY

### The Core Insight

TMR v2 has a fundamental design tension: **raw memories need to be preserved forever, but raw memories are also what gets injected.** This means we can never clean, consolidate, or improve the memory store without risking data loss.

**TMR v3 resolves this by splitting memory into two layers:**

| Layer | Purpose | Mutable? | Used For |
|-------|---------|----------|----------|
| **Layer 1 — Raw** | Immutable source of truth | Never | Audit trail, exact recall |
| **Layer 2 — Processed** | Consolidated, scored, injected | Yes | Context injection, retrieval |

The raw layer stays untouched forever. The processed layer is rebuilt from raw data using a **Consolidation Engine** that handles conflict resolution, temporal tracking, merging, and scoring. If the processed layer has bugs, you regenerate it — zero data loss.

### Key Improvements Over V2

| Area | V2 | V3 |
|------|-----|-----|
| **Memory storage** | Single layer — raw triples | Two layers — raw + processed |
| **Memory management** | ADD only | ADD/UPDATE/DELETE/MERGE on processed layer |
| **Entity types** | Flat strings ("User", "topic") | Typed entities (Person, Project, Preference, Location, etc.) |
| **Temporal tracking** | None | Creation time, last-referenced time, state transitions |
| **Conflict resolution** | None | New info supersedes old; old marked as `superseded` |
| **Confidence scoring** | Flat ~0.5 | Dynamic: recency + specificity + entity-type + usage frequency |
| **Injection format** | Generic triples | Rich summaries with file paths, entity context |
| **Feedback loop** | Wired but not used | Auto-judge: compare injected vs actual response utility |

---

## 2. THE PROBLEM WITH V2

### 2.1 Single Layer = No Cleanup

V2 stores everything in one Qdrant collection (`tmr_knowledge_graph`). Every extracted relation lives forever. This means:

- **Contradictions accumulate**: "User prefers VS Code" and "User uses PyCharm" both exist with equal weight
- **Stale info never decays**: Preferences from 3 months ago have the same score as yesterday's
- **No way to improve**: If the extraction quality is poor, you can't fix it without losing data

### 2.2 Generic Extraction

The Qwen extractor produces flat triples:

```json
{
  "subject": "User",
  "relation": "REMEMBERED",
  "object": "discussed TMR memory injection logic"
}
```

This loses:
- **Entity types**: Is "SnookerFlow" a project, a website, a game?
- **Temporal context**: Was this a one-time event or an ongoing preference?
- **Importance**: Is this a critical bug or a casual observation?
- **Relationships**: How does this connect to other memories?

### 2.3 Flat Confidence Scoring

The relevance score in V2 is computed from:
- Base hybrid score (60%)
- Thread continuity (up to +0.45)
- Recency (up to +0.20)
- Intent alignment (+0.10)

In practice, every memory clusters around 0.45–0.55 — barely above the Tier 1/Tier 2 boundary. The scoring lacks **discrimination** because the input features (the triples) are too uniform.

---

## 3. TWO-LAYER ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 1: RAW MEMORY                               │
│                         (Immutable Source of Truth)                        │
│                                                                             │
│   Raw Files ──▶ Qwen Extractor ──▶ Raw Relations ──▶ Qdrant (size=1)       │
│                      │                                                        │
│                      │ (also saved to disk: memory/graph/YYYY-MM-DD.json)     │
│                      ▼                                                        │
│              Raw Embeddings ──▶ Qdrant (size=768)                            │
│                                                                             │
│   Collections:                                                              │
│   - tmr_knowledge_graph_raw (relations, size=1)                            │
│   - tmr_semantic_vectors_raw (embeddings, size=768)                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Consolidation Engine (runs after extraction)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LAYER 2: PROCESSED MEMORY                             │
│                      (Consolidated, For Injection)                         │
│                                                                             │
│   Consolidation Engine:                                                     │
│   1. Read raw relations from Layer 1                                       │
│   2. Resolve conflicts (ADD/UPDATE/DELETE/MERGE)                           │
│   3. Apply temporal tracking                                               │
│   4. Compute dynamic confidence scores                                     │
│   5. Write to Layer 2                                                       │
│                                                                             │
│   Collections:                                                              │
│   - tmr_consolidated_graph (processed relations, size=1)                   │
│   - tmr_consolidated_vectors (processed embeddings, size=768)              │
│                                                                             │
│   Can be rebuilt from Layer 1 at any time.                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ On query
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      RETRIEVAL & INJECTION                                 │
│                                                                             │
│   Query ──▶ Intent Classification ──▶ Search Processed Layer ──▶            │
│   ──▶ Dynamic Scoring ──▶ Tiered Injection ──▶ Context                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Data Flow

```
1. Raw conversation → Qwen Extractor → Layer 1 (raw relations + embeddings)
2. Consolidation Engine triggers → reads Layer 1 → resolves → writes Layer 2
3. User query → search Layer 2 → score → inject into context
4. (Optional) If Layer 2 seems wrong → fall back to Layer 1 for exact truth
```

### 3.2 Key Design Principle

**Layer 2 is always rebuildable from Layer 1.** This means:

- We can experiment with consolidation strategies without risk
- If the consolidation engine has a bug, we fix it and regenerate
- The raw truth is always available for audit

---

## 4. LAYER 1: RAW MEMORY (SOURCE OF TRUTH)

### 4.1 What Stays the Same

- **Extraction pipeline**: Qwen extractor → relations + embeddings (unchanged from V2)
- **Raw file storage**: `memory/raw/YYYY-MM-DD.md` (unchanged)
- **Graph file storage**: `memory/graph/YYYY-MM-DD.json` (unchanged)
- **Incremental extraction**: 2-hour cron (unchanged)

### 4.2 What Changes

**Renamed Qdrant collections** to make the two-layer structure explicit:

| Old Name | New Name | Purpose |
|----------|----------|---------|
| `tmr_knowledge_graph` | `tmr_knowledge_graph_raw` | Raw relations |
| `tmr_semantic_vectors` | `tmr_semantic_vectors_raw` | Raw embeddings |
| `tmr_agents_files` | `tmr_agents_files_raw` | Raw agent file metadata |

**Richer raw format** (optional, can be phased):

```json
{
  "subject": "User",
  "relation": "PREFERS",
  "object": "dark green ball logo for SnookerFlow",
  "entity_type": "preference",
  "temporal_context": "stated_on: 2026-05-09",
  "importance": 7,
  "source": {
    "file": "memory/raw/2026-05-09.md",
    "line_start": 42,
    "line_end": 45,
    "text_snippet": "User: the dark green ball logo looks better"
  },
  "extraction_timestamp": "2026-05-09T19:00:00Z"
}
```

The key additions:
- `entity_type`: Categorizes the memory (preference, fact, event, instruction, etc.)
- `temporal_context`: When the information was relevant
- `importance`: LLM-assigned importance score (1-10) at extraction time
- `extraction_timestamp`: When this was extracted (for recency scoring)

### 4.3 Immutability Guarantee

**Layer 1 data is never modified after insertion.** The only operations are:
- **INSERT**: New raw relations from extraction
- **READ**: For consolidation engine and fallback queries

No UPDATES, no DELETES, no MERGES. Ever.

---

## 5. LAYER 2: PROCESSED MEMORY (FOR INJECTION)

### 5.1 Purpose

Layer 2 is the **curated, consolidated view** of all memories. It's what gets searched and injected into context. It can be regenerated from Layer 1 at any time.

### 5.2 Collections

| Collection | Size | Purpose |
|------------|------|---------|
| `tmr_consolidated_graph` | 1 | Processed relations with resolved conflicts |
| `tmr_consolidated_vectors` | 768 | Processed embeddings for semantic search |

### 5.3 Memory Format

Layer 2 memories are richer than Layer 1:

```json
{
  "id": "uuid",
  "summary": "User prefers dark green ball logo for SnookerFlow website",
  "entity_type": "preference",
  "entities": {
    "primary": {"name": "User", "type": "person"},
    "secondary": [
      {"name": "SnookerFlow", "type": "project"},
      {"name": "dark green ball logo", "type": "design_element"}
    ]
  },
  "temporal": {
    "created": "2026-05-09T19:00:00Z",
    "last_referenced": "2026-05-09T20:00:00Z",
    "state": "current"  // current | superseded | expired
  },
  "confidence": {
    "overall": 0.85,
    "recency": 0.95,
    "specificity": 0.80,
    "source_quality": 0.75,
    "usage_frequency": 0.70
  },
  "source": {
    "raw_file": "memory/raw/2026-05-09.md",
    "line_start": 42,
    "line_end": 45
  },
  "consolidation": {
    "supersedes": ["uuid-of-older-version"],
    "superseded_by": null,
    "merge_group": "snookerflow-design",
    "consolidation_timestamp": "2026-05-09T20:05:00Z"
  }
}
```

### 5.4 Key Features

**Entity typing**: Every memory has typed entities (person, project, preference, location, etc.). This enables:
- Entity-specific search ("find all project-related memories")
- Relationship mapping ("what projects does User have preferences about?")
- Better relevance scoring (matching entity types between query and memory)

**Temporal tracking**: Each memory tracks:
- `created`: When the memory was first extracted
- `last_referenced`: When it was last injected into context (updated on injection)
- `state`: `current` | `superseded` | `expired`

**Confidence breakdown**: Instead of a single flat score, confidence has sub-scores:
- `recency`: Higher for recent memories
- `specificity`: Higher for memories with specific details (prefers X over Y, not just "likes X")
- `source_quality`: Higher when extracted from direct statements vs inferred
- `usage_frequency`: Higher for memories that have been useful in past injections

---

## 6. CONSOLIDATION ENGINE

### 6.1 Overview

The Consolidation Engine is the core new component. It runs after each extraction cycle and processes raw Layer 1 memories into consolidated Layer 2 memories.

```
Raw Memories (Layer 1)
    │
    ▼
┌─────────────────────┐
│ 1. Entity Matching  │ ← Group memories by entity
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 2. Conflict Detect  │ ← Find contradictions
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 3. Conflict Resolve │ ← ADD / UPDATE / DELETE / MERGE / SUPERSEDE
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 4. Temporal Update  │ ← Track state transitions
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 5. Score Compute    │ ← Dynamic confidence scoring
└─────────┬───────────┘
          ▼
    Layer 2 (Processed)
```

### 6.2 Phase 1: Entity Matching

Group raw memories by their primary entities to identify related memories.

```
Input: Raw memories
Process: For each memory, extract primary entity → group with existing memories about same entity
Output: Entity groups

Example:
  "User prefers VS Code"  → group: {entity: "User", sub_entity: "VS Code"}
  "User uses PyCharm"     → group: {entity: "User", sub_entity: "PyCharm"}
  Both in "User → editor_preference" group
```

### 6.3 Phase 2: Conflict Detection

Within each entity group, detect conflicts between memories.

**Conflict types:**

| Type | Example | Resolution |
|------|---------|------------|
| **Direct contradiction** | "User prefers VS Code" vs "User prefers PyCharm" | Newer supersedes older |
| **Temporal change** | "User lives in London" vs "User lives in Tokyo" | State transition: old → superseded |
| **Refinement** | "User likes pasta" vs "User prefers carbonara" | Merge: carbonara is specific type of pasta preference |
| **Duplicate** | Same fact extracted twice | Merge: keep one, reference both sources |

**Detection method:**

For each new raw memory, compare against existing Layer 2 memories with the same entity/sub-entity:
1. Compute semantic similarity between the `object` fields
2. If similarity > 0.9 → likely duplicate → MERGE
3. If similarity < 0.3 but same entity/sub-entity → possible contradiction → flag for resolution
4. If one is a specific instance of the other (e.g., "pasta" vs "carbonara") → MERGE as refinement

### 6.4 Phase 3: Conflict Resolution

For each detected conflict, the LLM (Qwen) decides the appropriate operation:

| Operation | When | Effect |
|-----------|------|--------|
| **ADD** | New memory about a new entity | Create new Layer 2 entry |
| **UPDATE** | New info complements existing | Add details to existing entry |
| **MERGE** | Same info from different sources | Combine sources, update confidence |
| **SUPERSEDE** | New info contradicts old | Mark old as `superseded`, create new entry |
| **DELETE** | Info is clearly wrong/no longer relevant | Remove from Layer 2 (raw still exists) |
| **NOOP** | Info is trivial or redundant | Skip |

**Implementation:**

```python
def resolve_conflict(raw_memory, existing_l2_memories):
    """
    LLM decides what to do with a raw memory vs existing processed memories.
    """
    prompt = f"""
    Existing memory: {existing_l2_memories}
    New information: {raw_memory}
    
    Choose ONE operation:
    - ADD: New information about a new topic
    - UPDATE: New information adds to existing (no contradiction)
    - MERGE: Same information from different source
    - SUPERSEDE: New information contradicts existing (mark old as outdated)
    - DELETE: Information is wrong or no longer relevant
    - NOOP: Information is trivial or already fully covered
    
    Output: operation, reason
    """
    # LLM call
    return operation, reason
```

This is intentionally **lightweight** — only runs on detected conflicts, not on every memory. Most memories will be simple ADDs.

### 6.5 Phase 4: Temporal Update

Track when memories change state:

```
Timeline:
  Day 1: "User lives in London" → Layer 2: {state: "current"}
  Day 30: "User moved to Tokyo" → Layer 2: {
    "User lives in Tokyo": {state: "current"},
    "User lives in London": {state: "superseded", superseded_by: "User lives in Tokyo"}
  }
```

**Temporal state machine:**

```
                    ┌──────────┐
        New info    │          │   Time passes
     ──────────────▶│ Current  │──────────────▶
                    │          │                │
                    └──────────┘                │
                         │                      │
                         │ Contradiction         │ No reference for N days
                         ▼                      ▼
                    ┌──────────┐          ┌──────────┐
                    │Superseded│          │ Expired  │
                    └──────────┘          └──────────┘
```

**Expiry policy:**
- Memories with `entity_type: preference` → expire after 90 days without reference
- Memories with `entity_type: fact` → never expire
- Memories with `entity_type: event` → expire after 30 days
- Memories with `entity_type: instruction` → expire after 7 days (likely one-time)

### 6.6 Phase 5: Score Computation

Dynamic confidence scoring replaces V2's flat scoring:

```python
def compute_confidence(memory):
    scores = {}
    
    # Recency: higher for recent memories
    days_old = (now - memory.created).days
    scores['recency'] = max(0, 1 - (days_old / 90))  # Linear decay over 90 days
    
    # Specificity: higher for specific vs generic memories
    # "prefers VS Code over PyCharm" > "likes coding"
    scores['specificity'] = min(1, len(memory.object.split()) / 10)
    
    # Source quality: direct statement > inferred > extracted
    quality_map = {"direct": 0.9, "inferred": 0.7, "extracted": 0.5}
    scores['source_quality'] = quality_map.get(memory.source_type, 0.5)
    
    # Usage frequency: higher for memories that have been useful
    if memory.injection_count > 5:
        scores['usage_frequency'] = 0.9
    elif memory.injection_count > 2:
        scores['usage_frequency'] = 0.7
    else:
        scores['usage_frequency'] = 0.4
    
    # Overall: weighted combination
    weights = {
        'recency': 0.30,
        'specificity': 0.25,
        'source_quality': 0.25,
        'usage_frequency': 0.20
    }
    
    overall = sum(scores[k] * weights[k] for k in weights)
    return {
        'overall': overall,
        **scores
    }
```

---

## 7. RICHER MEMORY FORMAT

### 7.1 Entity Types

All entities in Layer 2 are typed. The initial taxonomy:

| Type | Examples | Scoring Weight |
|------|----------|----------------|
| `person` | User, Liz | High — always relevant |
| `project` | SnookerFlow, TMR | High — project context |
| `preference` | food, editor, design | Medium — user likes/dislikes |
| `location` | home, work, city | Medium — where things happen |
| `event` | meeting, bug, release | Medium — one-time occurrences |
| `instruction` | fix this, deploy that | Low — usually one-time |
| `fact` | API key, server address | High — always relevant |
| `concept` | GraphRAG, embeddings | Medium — discussion topics |

### 7.2 Relation Types

Richer relation types beyond V2's flat `REMEMBERED`:

| Relation | Example |
|----------|---------|
| `PREFERS` | User → PREFERS → dark green ball logo |
| `WORKS_ON` | User → WORKS_ON → SnookerFlow project |
| `LOCATED_AT` | Server → LOCATED_AT → 192.168.1.106 |
| `INSTRUCTED` | User → INSTRUCTED → fix the dimension mismatch |
| `DISCUSSED` | User ↔ Liz → DISCUSSED → TMR architecture |
| `DECIDED` | User → DECIDED → two-layer memory architecture |
| `USES` | User → USES → VS Code |
| `IS_A` | SnookerFlow → IS_A → web application |
| `RELATED_TO` | Logo → RELATED_TO → SnookerFlow branding |

### 7.3 Summary Generation

Instead of injecting raw triples, Layer 2 stores a **generated summary** for each memory:

```
Raw triple:    User → PREFERS → dark green ball logo for SnookerFlow
Summary:       "User prefers the dark green ball logo (with #00e5a0 green stroke, 
               white center circle, and dark 'SF' text) for the SnookerFlow website. 
               This was implemented across all pages including index.html, admin.html, 
               LoginPage.tsx, and the favicon."
```

Summaries are generated by the LLM during consolidation and stored in Layer 2. They provide **immediately useful context** without needing to read the source file.

---

## 8. IMPROVED INJECTION STRATEGY

### 8.1 Current V2 Injection

```
[RELATED MEMORY - TMR]

From previous conversations:

1. The User questioned the TMR memory injection logic, noting that graph search fails
   because the extractor hardcodes the subject as "User".
   (conf: 50%, rel: 0.95, method: HYBRID)
   [Source: memory/raw/2026-05-08.md:19-20]
```

Problems:
- Generic summaries ("The User questioned...")
- Flat confidence (50%)
- No entity context
- Method info (HYBRID) is noise, not signal

### 8.2 V3 Injection Format

```
📌 [Memory: Project - TMR]
   User identified that the extractor hardcodes all subjects as "User", making graph 
   search fail because it can't distinguish between different entities. This was 
   discussed as a critical bug in the extraction pipeline.
   📎 memory/raw/2026-05-08.md:19-20
   🎯 relevance: 0.85 | last referenced: 2h ago | state: current

📌 [Memory: Decision - Architecture]
   User decided on a two-layer memory architecture for TMR v3: Raw layer (immutable 
   source of truth) + Processed layer (consolidated, for injection). The consolidation 
   engine handles conflict resolution, temporal tracking, and dynamic scoring.
   📎 memory/raw/2026-05-09.md:42-48
   🎯 relevance: 0.92 | last referenced: just now | state: current
```

Key improvements:
- **Entity badges**: `[Memory: Project - TMR]`, `[Memory: Decision - Architecture]`
- **Rich summaries**: Full sentence context, not generic triples
- **Source links**: Clean file paths
- **Relevance score**: Dynamic, with breakdown
- **Temporal context**: "last referenced: 2h ago"
- **State**: "current" vs "superseded"

### 8.3 Tier Thresholds (Refined)

| Tier | Score Range | Format |
|------|-------------|--------|
| **Tier 1** | ≥ 0.75 | Full summary + entity badge + source link + metadata |
| **Tier 2** | 0.45 – 0.74 | Short hint + source link only |
| **Tier 3** | < 0.45 | Silently skipped |

### 8.4 Auto-Feedback Loop

After every response, the system compares:
1. Query
2. Injected memories
3. Actual assistant response

If a memory was injected but the response didn't reference it → downweight that memory's `usage_frequency`
If a memory wasn't injected but the response referenced it → it should have been → upweight similar memories

This creates a **self-improving injection system** that learns which memories are actually useful.

---

## 9. IMPLEMENTATION PLAN

### Phase 1: Foundation (Week 1)

**Goal**: Set up the two-layer infrastructure without changing extraction.

1. **Create new Qdrant collections**
   - `tmr_consolidated_graph` (size=1)
   - `tmr_consolidated_vectors` (size=768)
   - Rename existing: `tmr_knowledge_graph` → `tmr_knowledge_graph_raw`

2. **Build Consolidation Engine skeleton**
   - `src/consolidation_engine.py`
   - Phase 1: Entity matching (group raw memories by entity)
   - Phase 5: Score computation (dynamic confidence)

3. **Basic copy**: Copy all raw memories to Layer 2 with default scores

**Deliverable**: Two layers exist, Layer 2 is a direct copy of Layer 1

### Phase 2: Conflict Resolution (Week 2)

**Goal**: Add ADD/UPDATE/DELETE/MERGE/SUPERSEDE logic.

1. **Implement conflict detection**
   - Entity matching within groups
   - Semantic similarity comparison
   - Contradiction flagging

2. **Implement conflict resolution**
   - LLM call for conflict operations
   - State machine (current → superseded → expired)

3. **Temporal tracking**
   - Creation timestamps
   - Last-referenced updates
   - Expiry policy

**Deliverable**: Consolidation engine resolves conflicts, tracks state changes

### Phase 3: Richer Extraction (Week 3)

**Goal**: Improve raw extraction quality for better consolidation.

1. **Update Qwen extractor prompt**
   - Entity type classification
   - Importance scoring at extraction time
   - Richer relation types (PREFERS, WORKS_ON, etc.)

2. **Summary generation**
   - LLM generates human-readable summaries during consolidation

**Deliverable**: Raw memories have entity types, importance scores, and summaries

### Phase 4: Improved Injection (Week 4)

**Goal**: Use Layer 2 for injection with dynamic scoring and auto-feedback.

1. **Update injection pipeline**
   - Search Layer 2 instead of Layer 1
   - New injection format (entity badges, rich summaries)
   - Dynamic confidence scoring

2. **Auto-feedback loop**
   - Track which memories were injected
   - Compare against actual response
   - Update usage frequency scores

**Deliverable**: Full two-layer injection with self-improvement

---

## 10. COMPARISON WITH OTHER SYSTEMS

### 10.1 Mem0

| Feature | Mem0 | TMR v3 |
|---------|------|--------|
| Extraction | LLM extracts facts from message pairs | Qwen extractor (unchanged) |
| Memory management | ADD/UPDATE/DELETE/NOOP via LLM | Same, plus MERGE and SUPERSEDE |
| Graph variant | Entities as nodes, edges as relationships | Same approach via entity typing |
| Scoring | Criteria-based retrieval | Dynamic confidence with sub-scores |
| Raw preservation | Not explicit | **Layer 1 is immutable** |
| Latency | 0.71s median | Target: <1s |

### 10.2 Zep

| Feature | Zep | TMR v3 |
|---------|-----|--------|
| Temporal KG | Graphiti engine — state changes tracked | Temporal state machine (current/superseded/expired) |
| Async processing | Background processing | Consolidation runs after extraction |
| Message compression | Auto-summarizes old history | Summary generation during consolidation |
| DMR benchmark | 94.8% | Not benchmarked (custom use case) |

### 10.3 Letta (MemGPT)

| Feature | Letta | TMR v3 |
|---------|-------|--------|
| Core memory | Always in context | Not applicable (different architecture) |
| Archival memory | Searchable long-term | Layer 2 processed memory |
| Agent-led memory | Agent decides what to remember | Consolidation engine decides |
| Self-managing | Agent reads/writes own memory | Auto-feedback loop adjusts scores |

### 10.4 Microsoft GraphRAG

| Feature | GraphRAG | TMR v3 |
|---------|----------|--------|
| Community detection | Leiden algorithm | Not planned (document-level, not corpus-level) |
| Summarization | Per-community summaries | Per-memory summaries |
| Local search | Entity-specific | Entity-specific via typing |
| Global search | Community-level themes | Not applicable (conversation memory, not document corpus) |

---

## 11. GLOSSARY

| Term | Definition |
|------|------------|
| **Layer 1 (Raw)** | Immutable source of truth. Raw relations and embeddings from extraction. Never modified. |
| **Layer 2 (Processed)** | Consolidated memory store. Handles conflict resolution, temporal tracking, scoring. Used for injection. |
| **Consolidation Engine** | Component that processes Layer 1 into Layer 2. Runs after each extraction cycle. |
| **Entity Typing** | Categorizing entities (person, project, preference, etc.) for better search and scoring. |
| **Temporal State** | Current / Superseded / Expired — tracks whether a memory is still relevant. |
| **Conflict Resolution** | Process of detecting and resolving contradictions between memories (ADD/UPDATE/DELETE/MERGE/SUPERSEDE/NOOP). |
| **Dynamic Scoring** | Confidence score with sub-scores (recency, specificity, source quality, usage frequency). |
| **Auto-Feedback** | Self-improvement loop that adjusts memory scores based on injection usefulness. |
| **Tiered Injection** | Three-tier output: Tier 1 (full summary), Tier 2 (reference only), Tier 3 (skipped). |

---

## APPENDIX A: File Structure

```
~/.openclaw/extensions/TrueMemoryRecall/
├── documentation/
│   ├── v1/                          # V2 docs (legacy)
│   │   ├── FINAL_DOCUMENTATION.md
│   │   ├── PLAN_VS_REALITY.md
│   │   ├── REALTIME_ENHANCEMENT.md
│   │   ├── CHANGES_BEYOND_PLAN.md
│   │   ├── PHASE5_INTEGRATION_SUMMARY.md
│   │   ├── SEMANTIC_SEARCH_SUMMARY.md
│   │   ├── README.md
│   │   ├── TMR-v2-Session-Checkpoint-2026-03-18.md
│   │   └── TMR-v2-Session-Checkpoint.md
│   ├── v2/                          # V3 design docs
│   │   └── DOCUMENTATION_V2.md      ← This file
│   └── decisions/                   # Key architectural decisions (future)
├── src/
│   ├── embedder.py                  # Unchanged
│   ├── extractor.py                 # Updated for richer extraction (Phase 3)
│   ├── qdrant_manager.py            # Updated for two-layer collections
│   ├── tmr_injector.py              # Updated for Layer 2 search + new format
│   ├── consolidation_engine.py      # NEW: Consolidation Engine
│   ├── intent_classifier.py         # Unchanged
│   ├── query_planner.py             # Unchanged
│   ├── graph_traversal.py           # Unchanged
│   ├── feedback_loop.py             # Updated for auto-feedback
│   └── ...
├── scripts/
│   └── incremental_extractor.py     # Updated to trigger consolidation
└── ...
```

## APPENDIX B: Key Metrics to Track

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Injection relevance | >0.75 avg | User feedback score after each response |
| False positive rate | <20% | Memories injected but not useful |
| Consolidation latency | <5s per cycle | Time to process new raw memories |
| Layer 2 rebuild time | <60s for full rebuild | Time to regenerate from Layer 1 |
| Memory discrimination | >0.3 std dev in scores | Standard deviation of confidence scores |
| Conflict resolution accuracy | >80% | Manual audit of resolved conflicts |

---

**Documentation Version:** 3.0 (Design)  
**Last Updated:** 2026-05-09  
**Author:** Liz 🦎  
**Status:** Design Phase — pending implementation