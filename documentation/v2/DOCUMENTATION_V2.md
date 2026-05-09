# TMR V2 Design: Two-Layer Memory Architecture
## A Ground-Truth-Preserving Consolidation Engine for Long-Term Agent Memory

**Version:** 2.0 (Design) — Replaces V1 single-layer architecture  
**Status:** Design Phase  
**Date:** 2026-05-09  
**Architecture:** Two-Layer Memory with Background Consolidation (no AI at query time)

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [The Problem with V1](#2-the-problem-with-v1)
3. [Core Design Principles](#3-core-design-principles)
4. [Two-Layer Architecture](#4-two-layer-architecture)
5. [Layer 1: Raw Memory](#5-layer-1-raw-memory)
6. [Layer 2: Processed Memory](#6-layer-2-processed-memory)
7. [Consolidation Engine](#7-consolidation-engine)
8. [Conflict Resolution Strategy](#8-conflict-resolution-strategy)
9. [Profile Memory](#9-profile-memory)
10. [Dynamic Scoring](#10-dynamic-scoring)
11. [Enhanced Extraction](#11-enhanced-extraction)
12. [Improved Injection](#12-improved-injection)
13. [Feedback Loop](#13-feedback-loop)
14. [Temporal Management](#14-temporal-management)
15. [Scrutiny Log: Gaps Found & Closed](#15-scrutiny-log-gaps-found--closed)
16. [Migration Path](#16-migration-path)
17. [Cost Analysis](#17-cost-analysis)
18. [Error Handling & Rollback](#18-error-handling--rollback)
19. [Testing Strategy](#19-testing-strategy)
20. [Implementation Plan](#20-implementation-plan)
21. [System Comparison](#21-system-comparison)
22. [Glossary](#22-glossary)

---

## 1. EXECUTIVE SUMMARY

### The Core Insight

TMR V1 stores everything in one layer. Raw triples in, raw triples out. This means contradictions accumulate forever, stale facts never decay, scoring has no discrimination, and there's no concept of personality or profiles.

**V2 fixes this with two layers:** raw (immutable) and processed (consolidated). **All AI work is in background cron jobs. Zero AI at query time.**

| Component | AI Needed? | When | Why |
|-----------|:----------:|------|-----|
| **Extraction** (existing) | ✅ LLM | Cron (2h) | Turn conversations → triples |
| **Consolidation** (new) | ✅ LLM (partial) | Cron (2h) | **Only** for real conflicts; ADD/MERGE skip LLM |
| **Profiling** (new) | ✅ LLM | Cron (daily) | Update user/agent/relationship profiles |
| **Scoring** (new) | ❌ No AI | Query time | Pure math formula |
| **Injection** (improved) | ❌ No AI | Query time | Template-based formatting |
| **Feedback** (new) | ❌ No AI | Query + cron | Keyword-overlap heuristic |
| **Search/Retrieval** | ❌ No AI | Query time | Vector search + math scoring |

**Extra LLM cost:** ~5-15 calls per 2h cycle = 60-180 extra calls/day. Cognee costs infinitely more because they call LLM on every search.

---

## 2. THE PROBLEM WITH V1

- **No cleanup possible** — contradictions stay forever
- **Stale info gets equal weight** — no decay
- **Flat scoring** — everything clusters at 0.45-0.55
- **No profiles** — just generic "User prefers X"

---

## 3. CORE DESIGN PRINCIPLES

| # | Principle | Rationale |
|---|-----------|-----------|
| **P1** | **No AI at query time** | You're paying for extraction cron, not per-query. Search/score/format are math-only. |
| **P2** | **Raw layer is immutable** | Deleted data can recover. Consolidation can rebuild from scratch. |
| **P3** | **LLM is last resort** | Heuristics handle 90% of cases. Only call LLM for genuine ambiguity. |
| **P4** | **Layer 2 is regenerable** | Bug in consolidation? Fix + regenerate. Zero data loss. |
| **P5** | **Profiles over flat facts** | User + Agent + Relationship profiles capture more than triples ever could. |
| **P6** | **Self-improving via Gemma 4 cron** | Feedback loop uses local model hourly. No AI at query time. Human reviews and decides. |

---

## 4. TWO-LAYER ARCHITECTURE

```
┌──────────────────────────────────────────────────────────────────┐
│                        QUERY TIME (NO AI)                        │
│                                                                  │
│  User query ──▶ Search Layer 2 ──▶ Score (math) ──▶ Format ──▶ │
│                                                                    │
│  If Layer 2 empty:                                               │
│    └─▶ Search Layer 1 raw (fallback) ──▶ Same format           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Built by
┌──────────────────────────────────────────────────────────────────┐
│                     CRON JOB (EVERY 2H)                          │
│                                                                  │
│  Raw convo ──▶ Qwen extract ──▶ Layer 1 (raw, immutable)         │
│                                    │                             │
│                                    ▼                             │
│                           ┌──────────────────┐                   │
│                           │  CONSOLIDATION   │                   │
│                           │                  │                   │
│                           │  Group by entity │ ← heuristic only │
│                           │  Check conflicts │ ← heuristic 90%  │
│                           │  Resolve (LLM)   │ ← only if needed │
│                           │  Update profiles │ ← batched daily  │
│                           └────────┬─────────┘                   │
│                                    │                             │
│                                    ▼                             │
│                              Layer 2 (processed)                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. LAYER 1: RAW MEMORY

### 5.1 Collections

| V1 Name | V2 Name | What It Is |
|---------|---------|------------|
| `tmr_knowledge_graph` | `tmr_knowledge_graph_raw` | Raw triples — immutable |
| `tmr_semantic_vectors` | `tmr_semantic_vectors_raw` | Raw embeddings — immutable |
| (new) | `tmr_consolidated_graph` | Consolidated memories — mutated by cron |
| (new) | `tmr_consolidated_vectors` | Consolidated embeddings |
| (new) | `tmr_profiles` | User/agent/relationship profiles |
| (new) | `tmr_feedback_log` | Feedback history for self-improvement |

### 5.2 Immutability Guarantee

Layer 1 data is **never modified after insertion**. Operations: INSERT, READ only. No UPDATE, no DELETE. Ever.

---

## 6. LAYER 2: PROCESSED MEMORY

Store format:

```json
{
  "id": "uuid",
  "summary": "User discussed TMR memory injection, noting graph search fails because extractor hardcodes 'User' as subject",
  "entity_type": "discussion",
  "topics": ["TMR", "memory injection"],
  "entities": {
    "primary": {"name": "User", "type": "person"},
    "mentioned": [{"name": "TMR", "type": "project"}]
  },
  "temporal": {
    "created": "2026-05-09T19:00:00Z",
    "last_referenced": "2026-05-09T20:00:00Z",
    "state": "current"
  },
  "confidence": {
    "overall": 0.72,
    "recency": 0.90,
    "specificity": 0.65,
    "entity_match": 0.55,
    "usage_frequency": 0.40
  },
  "source": {"file": "memory/raw/2026-05-09.md", "line": 42},
  "consolidation": {
    "supersedes": [],
    "superseded_by": null,
    "source_count": 1
  },
  "injection_count": 3,
  "consecutive_misses": 0
}
```

Every field is either pre-computed in cron or updated with simple math at query time.

---

## 7. CONSOLIDATION ENGINE

### 7.1 Pipeline

```
1. Load new raw memories from Layer 1 (since last checkpoint)
2. Group by primary entity (just extract subject string — NO LLM)
3. For each entity group:
   ├─ Entity new in Layer 2? ──► ADD (NO LLM)
   ├─ Content similar (sim > 0.9)? ──► MERGE (NO LLM)
   ├─ Content contradictory (sim < 0.3, same relation)?
   │   └─ Timestamp is unambiguous ──► SUPERSEDE older (NO LLM)
   │   └─ Ambiguous ──► LLM decides (MINORITY CASE)
   └─ Different relation, same entity ──► ADD as new entry (NO LLM)
4. Check for expired memories by entity type rules (NO LLM)
5. Write back to Layer 2
```

### 7.2 LLM Call Analysis

| Scenario | % of Memories | LLM Needed? |
|----------|:-------------:|:-----------:|
| ADD (new entity) | 70-80% | ❌ No |
| MERGE (similar) | 10-15% | ❌ No |
| ADD (same entity, new topic) | 5-10% | ❌ No |
| SUPERSEDE (unambiguous) | 2-5% | ❌ No |
| SUPERSEDE (ambiguous) | 1-3% | ✅ Yes |
| Summary generation | 10-20% | ⚡ Optional (Phase 2) |

**Result:** ~1-5% of memories need LLM at consolidation. For 100 memories/day, that's 1-5 LLM calls per cycle, 12-60 per day.

### 7.3 Summary Generation Strategy

| Option | When | Description |
|--------|------|-------------|
| **A (Phase 1)** | Default | Skip summaries. Use raw `object` field. Works fine. |
| **B (Phase 2)** | Stable pipeline | Generate summaries only for conflicts/merges — LLM already doing context work, one extra sentence. |
| **C (Phase 3)** | Full feature | Batch summaries in separate daily cron. Lower cost but stale data. |

**Start with A.** Improvement comes from scoring + consolidation, not summaries.

---

## 8. CONFLICT RESOLUTION STRATEGY

### 8.1 Heuristic Flow

```
New raw memory "User prefers VS Code" — from extraction on 2026-05-10

Check Layer 2 for existing "User" entity memories:
  ├─ "User prefers PyCharm" (2026-05-01)
  │   └─ Same relation, contradicts ──► SUPERSEDE (newer timestamp wins, NO LLM)
  │
  ├─ "User discussed VS Code" (2026-05-08)
  │   └─ Different relation, same entity ──► ADD as new entry (NO LLM)
  │
  ├─ "User uses VS Code" (2026-05-09)
  │   └─ Similar intent ──► MERGE (NO LLM, increment source_count)
  │
  └─ "User prefers VS Code for Python, PyCharm for web" (2026-05-10)
      └─ Context-restricted preference ──► LLM decides if this is NEW or UPDATE
```

### 8.2 When to Call LLM

Only when:
1. **Temporal ambiguity** — can't tell which supersedes which
2. **Refinement** — "likes pasta" → "prefers carbonara", is this update or new fact?
3. **Context-dependent contradiction** — "User prefers X for web but Y for mobile"

### 8.3 Lightweight LLM Prompt

```
Existing: "User prefers VS Code"
New:      "User prefers VS Code for Python, PyCharm for web"

Decide: ADD | UPDATE | SUPERSEDE | MERGE
Entity type: preference | fact | event | instruction | discussion

Output:
decision: <X>
reason: <one sentence>
entity_type: <type>
```

---

## 9. PROFILE MEMORY

### 9.1 Why Three Profiles?

| Profile | Captures |
|---------|----------|
| User | What you like, your style, recurring topics |
| Agent | What I'm good at, my gaps, learned adaptations |
| Relationship | The dynamic between us — how to communicate **you** in **this mode** |

The relationship profile is the key differentiator. EverMemOS and MemMachine don't have this.

### 9.2 Profile Schemas (Abbreviated)

**User profile** includes: communication style, technical level per domain, decision pattern, recurring topics with frequency, key facts, preferences with confidence.

**Agent profile** includes: strengths, weaknesses, knowledge gaps, learned adaptations per context, confidence calibration.

**Relationship profile** includes: interaction modes (deep work/debugging/casual), triggers for each mode, communication shortcuts learned from history, trust level.

### 9.3 Profile Updates

- **User profile**: LLM extracts patterns from ~1 week of conversation (daily cron — not every 2h)
- **Agent profile**: Updated from feedback loop results (what worked, what tanked)
- **Relationship profile**: Derived from user + agent profiles + interaction history

### 9.4 Profile Injection

At query time, relevant profile traits are injected alongside memories. Templates, no AI. Example:

```
[PROFILE: Uddipta]
  Style: direct, weighs options before deciding
  Current focus: SnookerFlow, TMR
  Technical: expert (SE), intermediate (design/ops)

[PROFILE: Relationship]
  In technical design: provide tradeoffs + code, don't force single answer
```

### 9.5 Anti-Bloat

Cap profiles at ~50 entries. Replace oldest/lowest-confidence when full. Version for rollback.

---

## 10. DYNAMIC SCORING

### 10.1 Formula

```python
def score(memory, query, now):
    # RECENCY (weight: 0.25)
    days = (now - memory.created).days
    recency = 1.0 if days < 1 else 0.9 if days < 7 else 0.7 if days < 30 else 0.5 if days < 90 else 0.3

    # SPECIFICITY (weight: 0.25) — 4 indicators, max 1.0
    indicators = 0
    if len(memory.object or memory.summary) > 50: indicators += 1  # Has detail
    if any(r in memory.relation for r in ["prefers", "uses", "decided", "configured"]):
        indicators += 1  # Has preference/action
    if any(c.isdigit() for c in memory.object): indicators += 1  # Has concrete values
    if len(memory.entities.mentioned) > 0: indicators += 1  # Links to other entities
    specificity = min(1.0, indicators / 4)

    # ENTITY MATCH (weight: 0.25)
    query_nouns = simple_noun_extract(query)  # spaCy or regex, no LLM
    memory_entities = [memory.subject] + [e.name for e in memory.entities.mentioned]
    overlap = len(set(query_nouns) & set(memory_entities))
    entity_match = min(1.0, overlap / max(1, len(query_nouns)))

    # USAGE FREQUENCY (weight: 0.25)
    ic = memory.injection_count
    usage = 0.1 if ic == 0 else 0.3 if ic <= 2 else 0.5 if ic <= 5 else 0.7 if ic <= 10 else 0.9

    overall = recency*0.25 + specificity*0.25 + entity_match*0.25 + usage*0.25

    return {"overall": round(overall, 2), "recency": recency,
            "specificity": specificity, "entity_match": entity_match,
            "usage": usage}
```

### 10.2 Tier Thresholds

| Tier | Score | Action |
|------|-------|--------|
| 1 | ≥ 0.60 | Full injection with summary |
| 2 | 0.35 – 0.59 | Reference only |
| 3 | < 0.35 | Skip |

Thresholds lower than V1 (0.75/0.45) because scoring now discriminates properly.

---

## 11. ENHANCED EXTRACTION

Phase 1: **Don't change the extractor.** Current raw triples are fine.

Phase 2: Optional. Add to extractor prompt:
```
For each memory, also classify:
- Type: preference | fact | event | instruction | discussion
- Importance: 1-10
- Entities mentioned: comma-separated list
```

**Risk:** Prompt change could degrade quality.  
**Mitigation:** A/B test for 1 cycle before switching.

---

## 12. IMPROVED INJECTION

### 12.1 No AI — Pure Templates

```python
def format_tier1(m):
    badge = f"[{m.entity_type.title()}]"
    if m.topics: badge = badge[:-1] + f": {m.topics[0]}]"
    summary = m.summary or m.object
    source = f"📎 {m.source.file}:{m.source.line}"
    meta = f"🎯 relevance: {m.confidence['overall']} | seen: {time_ago(m.last_referenced)}"
    return f"{badge}\n{summary}\n{source}\n{meta}"

def format_tier2(m):
    hint = (m.summary[:80] if m.summary else m.object[:80]) + "..."
    return f"📎 {m.source.file}:{m.source.line} — {hint}"
```

### 12.2 Example Output

```
📌 [Discussion: TMR]
  User pointed out that extractor hardcodes all subjects as "User",
  making graph search fail for entity-specific queries.
  📎 memory/raw/2026-05-08.md:19-20
  🎯 relevance: 0.72 | seen: 2h ago
```

---

## 13. FEEDBACK LOOP (GEMMA 4 CRON, NO AI AT QUERY TIME)

### 13.1 Architecture

The feedback loop has two parts:
1. **Query-time tracking** — zero cost. Just writes a temp JSON file.
2. **Gemma 4 scoring** — runs hourly via cron. Local model, no API cost.

```
Query time (no AI):
├─ User asks question
├─ Script injects memories into context
├─ AI responds
└─ Script writes temp file: temp/feedback/TIMESTAMP-uuid.json

Every 1h (cron):
├─ scripts/feedback_scorer.py runs
├─ Reads all temp/feedback/*.json files
├─ For each: asks Gemma 4 "Was this memory relevant?"
├─ Gemma returns score (0.0-1.0) + one-sentence reasoning
├─ Saves to logs/feedback_scored/YYYY-MM-DD/ (permanent record)
└─ Deletes temp files (only scored data remains)
```

### 13.2 Temp File (Query-Time Write)

```json
{
  "timestamp": "2026-05-09T21:00:00Z",
  "query": "Fix the TMR extractor",
  "injected_memory": "User prefers VS Code",
  "response": "I'll open the editor for you",
  "memory_source": "memory/raw/2026-05-09.md:42",
  "scored": false
}
```

### 13.3 Gemma 4 Scoring Prompt

```
Query: "Fix the TMR extractor"
Response: "I'll open the editor for you"
Memory: "User prefers VS Code"

Was this memory relevant to answering the query?
Score 0.0 to 1.0 where 0 = confused response, 1 = directly useful.
Give one-sentence reason.

Format:
Score: 0.6
Reason: Sets coding context but doesn't directly help fix the extractor.
```

Gemma 4 is ~1B parameters via Ollama. ~50-100ms per inference. No network calls.

### 13.4 Scored File Format (Permanent)

```json
{
  "timestamp": "2026-05-09T21:00:00Z",
  "query": "Fix the TMR extractor",
  "injected_memory": "User prefers VS Code",
  "response": "I'll open the editor for you",
  "memory_source": "memory/raw/2026-05-09.md:42",
  "gemma_score": 0.6,
  "gemma_reasoning": "Sets coding context but doesn't directly help fix the extractor.",
  "model": "gemma4:1b",
  "processed_at": "2026-05-09T22:00:00Z",
  "human_override": null
}
```

### 13.5 Why Gemma 4 Beats Keywords

| Approach | Example | Result |
|----------|---------|--------|
| **Keyword matching** | "VS Code" vs "editor" → no match | ❌ Wrongly scores 0.0 |
| **Gemma 4** | Understands "editor" = "VS Code" | ✅ Scores 0.6 (context-relevant) |

Gemma 4 is tiny but understands word relationships. Good enough for this.

### 13.6 Human Review

```bash
# Review last 7 days, sorted by lowest scores
python scripts/review_feedback.py --since 7d --sort score_asc
```

Shows:
```
Low-scored memories (Gemma < 0.3):
─────────────────────────────────────
1. "User lives in Europe" → 0.0
   Query: "Fix the TMR extractor"
   Reason: "Completely irrelevant to technical debugging"
   → [Suppress] [Keep] [Override: ___]

2. "User discussed TMR memory injection" → 0.1
   Query: "Fix the TMR extractor"
   Reason: "Generic discussion, not actionable"
   → [Suppress] [Keep] [Override: ___]
```

**You always have final say.** Gemma pre-filters. You decide.

### 13.7 Adjustable Model Size

Since we store both temp files **and** Gemma-scored results, you can:
1. **Start with Gemma 4 1B** — fast, cheap, handles obvious cases
2. **Upgrade to Gemma 4 4B or 27B** — if 1B misses subtle relevance
3. **Compare models** — run multiple models on same files, pick best
4. **Override any score** — human judgment wins

### 13.8 Score Application (Manual Default)

**Mode A (Manual — default):**
- You review weekly
- You manually adjust memory scores in Layer 2
- Zero automation risk

**Mode B (Semi-Auto — Phase 3):**
- Gemma < 0.2 for 30 days → suggest suppression
- You approve or deny

**Mode C (Auto — never default):**
- Only after months of proven Mode A/B reliability

### 13.9 Directory Structure

```
~/.openclaw/extensions/TrueMemoryRecall/
├── temp/
│   └── feedback/              # Unscored — cleared after cron
├── logs/
│   └── feedback_scored/       # Permanent Gemma-scored records
│       └── 2026-05-09/
│           └── 21-00-uuid.json
```

### 13.10 Cost

| Model | Per-Inference | 100 Memories/Day | Daily Cost |
|-------|:-------------:|:----------------:|:----------:|
| Gemma 4 1B | 50-100ms CPU | ~10 sec total | Zero (local) |
| Gemma 4 4B | 200-400ms | ~40 sec total | Zero (local) |
| Gemma 4 27B | 2-5s | ~5 min total | Zero (local, needs GPU) |

Compare to **GPT-4/Claude API**: $0.0001-0.01 per call. 100 calls/day = $0.01-1/day.
Local Gemma = **$0 forever.**

---

## 14. TEMPORAL MANAGEMENT

### 14.1 State Machine

```
[NEW] ──► [CURRENT] ──► [SUPERSEDED]  (newer info came)
                      │
                      └──► [EXPIRED]    (no reference for N days)
```

### 14.2 Expiry Rules

| Entity Type | Expire After | Reason |
|------------:|-------------|--------|
| fact | Never | Facts don't change (User is in India) |
| preference | 90 days | Preferences evolve |
| event | 30 days | Events are one-time |
| instruction | 7 days | Usually one-shot |
| discussion | 60 days | Context fades |

Expired memories aren't deleted — just excluded from search. Layer 1 fallback still finds them.

---

## 15. SCRUTINY LOG: GAPS FOUND & CLOSED

This section exists because Uddipta asked me to **scrutinize my own plan** before committing to it. Here's what I found wrong with my own thinking:

### Gap 1: Migration Path
**First draft:** Assumed clean start. ❌  
**Reality:** V1 has thousands of existing triples. Can't drop them.  
**Fix:** Migrate existing data on first V2 run. See [Migration Path](#16-migration-path).

### Gap 2: LLM Cost Was Underestimated
**First draft:** Said "~20 LLM calls/day" without analysis. ❌  
**Reality:** Prompted extraction stays the same. Consolidation adds ~5-15 calls/cycle = ~60-180/day.  
**Fix:** Added detailed LLM usage breakdown in [Consolidation Engine](#7-consolidation-engine). Most cases (ADD, MERGE) use zero LLM.

### Gap 3: Summary Generation Was Vague
**First draft:** Implied every memory needs a new LLM summary. ❌  
**Reality:** That's expensive. Most memories are fine with the raw `object` text.  
**Fix:** Three options (A/B/C) — start with Option A (no summaries, use raw text). See Section 7.3.

### Gap 4: No Entity Type at Extraction Time
**First draft:** Proposed changing extractor prompt immediately. ❌  
**Reality:** Prompt changes risk degrading extraction quality. Current triples are acceptable.  
**Fix:** Entity typing happens in consolidation, not extraction. Extractor stays unchanged for Phase 1.

### Gap 5: Feedback Loop Required AI at Query Time
**First draft:** Suggested comparing injection to response using LLM. ❌  
**Reality:** Violates "no AI at query time" principle.  
**Fix:** Gemma 4 cron-based scoring. Query time only writes temp files (zero cost). Hourly cron uses local Gemma 4 to score relevance. See [Feedback Loop](#13-feedback-loop).

### Gap 6: No Fallback Strategy
**First draft:** Search Layer 2 only. ❌ What if Layer 2 is empty or corrupted?  
**Fix:** Fallback to Layer 1 raw search if Layer 2 fails or returns no results.

### Gap 7: Entity Matching Was Undefined
**First draft:** "Group by entity" sounds simple. ❌  
**Reality:** Needs a specific algorithm (entity name normalization, alias handling).  
**Fix:** Added heuristic flow in Section 8.1 with clear thresholds (sim > 0.9 = merge, sim < 0.3 = contradiction).

### Gap 8: Profiles Were Just Another Memory Type
**First draft:** Profiles would be stored alongside regular memories. ❌  
**Reality:** Profiles need separate management — caps, versioning, rollback. Entangling them with regular memories is messy.  **Fix:** Separate `tmr_profiles` collection with explicit anti-bloat rules.

### Gap 9: Scoring Was Too Complex
**First draft:** Had convoluted multi-factor formula with weights that weren't justified. ❌  **Reality:** Equal weights (25% each) for 4 factors is fine. Complexity doesn't improve discrimination.  **Fix:** Simplified to 4 factors × 25% each. Easy to tune.

### Gap 10: Timezones and DST
**First draft:** Used naive timestamp math. ❌ Will break in June when DST hits.  **Reality:** Need UTC everywhere, convert to local time only for display.  **Fix:** All timestamps stored as UTC ISO-8601.

### Gap 11: What Happens If Consolidation Crashes?
**First draft:** No recovery plan. ❌  **Reality:** If a cycle crashes, 2h of raw memories never consolidate.  **Fix:** Checkpoint tracking per cycle. Retry failed batches. Logging to identify which loop failed.

### Gap 12: Testing Was Not Defined
**First draft:** Jumped to implementation. ❌  **Reality:** Can't measure improvement if we don't have tests.  **Fix:** Added specific testing strategy in Section 19.

### Gap 13: Phase 3 Was Undefined
**First draft:** Jumped from Phase 1 → Phase 4 with no Phase 3. ❌  **Reality:** Vague phases = missed features.  **Fix:** 4 clear phases, each with exit criteria.

---

## 16. MIGRATION PATH

### Step 1: Rename Collections (One-Time)

```python
# During V2 setup
from qdrant_client import QdrantClient

client = QdrantClient(...)

# Rename existing V1 collections
client.update_collection(
    collection_name="tmr_knowledge_graph",
    new_name="tmr_knowledge_graph_raw"
)
client.update_collection(
    collection_name="tmr_semantic_vectors",
    new_name="tmr_semantic_vectors_raw"
)

# Create new Layer 2 collections
client.create_collection("tmr_consolidated_graph", ...)
client.create_collection("tmr_consolidated_vectors", ...)
```

### Step 2: Initial Consolidation

After renaming, run one-shot consolidation on ALL existing raw data:

```python
# Migration script
raw_memories = client.scroll("tmr_knowledge_graph_raw", limit=10000)
for batch in chunks_of(raw_memories, 100):
    consolidate(batch)  # Reuses normal consolidation logic
    write_to("tmr_consolidated_graph")
```

**Expected runtime:** ~2-3 hours for ~5,000 existing memories.  
**Downtime:** Zero. V1 injection keeps working until V2 is ready.

### Step 3: Flip Injection to Layer 2

```python
# In tmr_injector.py
class TMRInjector:
    def search(self, query):
        # Try Layer 2 first
        results = search_layer2(query)
        
        # Fallback if nothing found
        if not results:
            results = search_layer1_raw(query)
        
        return results
```

### Step 4: Clean Up V1 References

After 48 hours of stable V2 operation, mark V1 collections as deprecated.

---

## 17. COST ANALYSIS

### Current V1 Daily Cost

| Component | Calls/Day | Cost |
|-----------|:---------:|------|
| Extraction (Qwen) | 12 cron cycles × ~8 calls | Base cost (fixed) |
| **Total V1** | ~96 | Baseline |

### V2 Additional Daily Cost

| Component | Calls/Day | Cases |
|-----------|:---------:|------|
| Consolidation (ADD/MERGE — heuristic) | 0 | 85-90% of memories |
| Consolidation (conflict resolution) | ~10-30 | ~5% of memories |
| Summary generation (Phase 1: no) | 0 | Skipped |
| Profile updates | ~5-10 | Daily refresh |
| **Total V2 Extra** | ~15-40 | Small vs Cognee's per-query model |

### Cost Comparison

| System | AI Calls at Query Time? | AI Calls/Day (100 queries) |
|--------|:-----------------------:|:--------------------------:|
| **V2 (ours)** | None | ~180 (all in background) |
| **Cognee** | Yes — every search | ~300 (background + per-query) |
| **Mem0** | Yes — per query | ~100 user + per-query |

**Key advantage:** V2 runs the same cost regardless of query volume. Cognee gets more expensive as traffic scales.

---

## 18. ERROR HANDLING & ROLLBACK

### Failure Modes

| Failure | Recovery Action | Rollback Plan |
|---------|----------------|---------------|
| Extraction crash | Retry next cron cycle | Re-run same batch |
| Consolidation crash | Skip this cycle, retry next | Re-process from checkpoint |
| LLM down during conflict resolution | Fall back to heuristic (newer wins) | N/A — safe default |
| Layer 2 corruption | Regenerate from Layer 1 | Full rebuild, single command |
| Query-time crash (V2 → Layer 2) | Fallback to Layer 1 (V1 format) | Immediate, transparent |
| Profile bloat | Auto-trim oldest entries | Rebuild from scratch if needed |

### Recovery Script

```python
#!/usr/bin/env python3
# scripts/v2_disaster_recovery.py
"""
If Layer 2 is corrupted, rebuild from immutable Layer 1.
Usage: python v2_disaster_recovery.py --clean-slate
"""

if __name__ == "__main__":
    # 1. Backup current Layer 2 (just in case)
    backup_collection("tmr_consolidated_graph")
    
    # 2. Clear Layer 2
    delete_collection("tmr_consolidated_graph")
    delete_collection("tmr_consolidated_vectors")
    
    # 3. Rebuild from Layer 1 — every single raw memory
    raw = scroll_all("tmr_knowledge_graph_raw")
    consolidate_all(raw)
    
    # 4. Verify checksums
    assert count(L2) >= count(L1)  # Some merges reduce count slightly
```

---

## 19. TESTING STRATEGY

| Test | What It Validates | How |
|------|------------------|-----|
| **Consolidation smoke** | Engine doesn't crash | Run on 100 sample triples |
| **Scoring threshold** | Tier 1/2/3 separation works | Hand-label 30 memories, verify scoring order |
| **Conflict resolution** | Contradictions are caught | Feed "User prefers X" + "User prefers Y" → verify SUPERSEDE |
| **Migration** | Data integrity across layers | Count L1 before migration = count L1 after migration |
| **Fatigue test** | 1000-memory batch | Run overnight on synthetic data |
| **Injection format** | No missing fields | Parse output with strict JSON schema |
| **Fallback** | Layer 2 failure → Layer 1 works | Delete L2, verify query still returns results |

**Exit Criteria for Phase 1 → Phase 2:**
- Zero migration errors
- Scoring produces at least 20% of memories in Tier 1 and 30% in Tier 3
- Conflict resolution correctly handles 90%+ of contradiction test cases

---

## 20. IMPLEMENTATION PLAN

### Phase 1: Foundation (Week 1)

**Goal:** Two layers exist, scoring works, zero AI at query time.

| Task | File | Effort |
|------|------|--------|
| Rename V1 collections + create L2 collections | `src/qdrant_manager.py` | 2h |
| Build consolidation engine (ADD/MERGE/SUPERSEDE heuristics) | `src/consolidation_engine.py` | 1d |
| Implement scoring (4-factor math) | `src/consolidation_engine.py` | 4h |
| Update injection to search Layer 2 + fallback to L1 | `src/tmr_injector.py` | 4h |
| Migrate existing data from L1 → L2 | `scripts/migrate_to_v2.py` | 4h |
| Add injection tracking (no AI) | `src/feedback_loop.py` | 2h |
| Testing | `tests/` | 4h |

**Exit criteria:** All existing V1 data visible via Layer 2 search. No injection errors.

### Phase 2: Conflict Resolution + Profiles (Week 2)

**Goal:** LLM resolves real conflicts, profiles exist.

| Task | File | Effort |
|------|------|--------|
| LLM conflict resolution (ambiguous cases only) | `src/consolidation_engine.py` | 1d |
| Profile schema + store | `src/profile_manager.py` | 4h |
| Daily profile update cron | `scripts/update_profiles.py` | 4h |
| Profile injection templates | `src/tmr_injector.py` | 4h |
| Feedback loop application (demotion/boosting) | `src/feedback_loop.py` | 2h |

**Exit criteria:** 95% of conflicts resolved correctly. Profiles inject naturally.

### Phase 3: Richer Format + Summary Generation (Week 3)

**Goal:** Prettier injection, summaries from LLM when needed.

| Task | Effort |
|------|--------|
| Summary generation during consolidation (Option B) | 1d |
| Entity typing in extraction (optional extractor prompt update) | 1d (A/B test first) |
| Improved injection format (badges, nice layout) | 4h |

### Phase 4: Polish + Evaluation (Week 4)

**Goal:** Compare V1 vs V2 injection quality.

| Task | Effort |
|------|--------|
| Logging + metrics collection | 4h |
| Side-by-side injection comparison | 8h |
| Performance benchmarks (latency) | 4h |
| Documentation update | 4h |

---

## 21. SYSTEM COMPARISON

| Feature | V1 (Current) | V2 (Design) | Cognee | Mem0 | MemMachine |
|---------|:------------:|:-----------:|:------:|:----:|:----------:|
| Layers | 1 (mixed) | 2 (raw+processed) | 2 (raw+enriched) | 2 (vector+graph) | 2 (episodic+profile) |
| AI at query time | None ✅ | None ✅ | Yes ❌ | Yes ❌ | Yes ❌ |
| AI cost | Fixed (cron) | Fixed + small (cron) | Per-query (scales) | Per-query (scales) | Per-query (scales) |
| Conflict resolution | None | ✅ Heuristic + LLM fallback | ✅ Entity consolidation | ✅ LLM ADD/UPDATE | ✅ Ground-truth preserving |
| Temporal tracking | None | ✅ Full state machine | ⚡ Partial | ⚡ Partial | ✅ Full |
| Profile memory | None | ✅ User+Agent+Relationship | ⚡ User only | ✅ User only | ✅ User+Agent |
| Relationship profile | None | ✅ Yes (ours only) | ❌ No | ❌ No | ❌ No (user only) |
| Self-improving scoring | None | ✅ Usage-frequency heuristic | ⚡ Basic | ⚡ Basic | ✅ Retrieval agent |
| Ground-truth preserved | No (mutates raw) | ✅ Yes (immutable L1) | ⚡ Raw is kept but enriched separately | ✅ Yes | ✅ Full episodes |
| Open source | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Open core | ✅ Yes |
| Scalability | Exhaustion | Chronological ordering | ✅ Incremental | ✅ Incremental | ✅ Incremental |

---

## 22. GLOSSARY

| Term | Definition |
|------|------------|
| **Layer 1** | **Raw Memory** — immutable source of truth. All extraction output lives here forever. |
| **Layer 2** | **Processed Memory** — consolidated, scored, temporal. What gets injected into context. |
| **Consolidation Engine** | Background process that turns Layer 1 → Layer 2. Handles conflicts, scoring, expiry. |
| **Profile Memory** | Three structured objects (user, agent, relationship) that capture personality + dynamic. |
| **Conflict Resolution** | Process of deciding what to do when new memory contradicts old: ADD/MERGE/SUPERSEDE. |
| **Supercede** | When newer info makes old info outdated. Old marked `superseded`, new marked `current`. |
| **Expired** | Memory marked as too old for active injection. Not deleted — just hidden. |
| **Entity Typing** | Classifying memories into types: preference, fact, event, instruction, discussion. |
| **Usage Frequency** | Score tracking how often an injected memory actually contributes to responses. |
| **Feedback Loop** | System that adjusts memory scores based on whether they were useful in practice. |
| **No AI at query time** | The principle that search/score/format use math only — zero LLM calls per query. |
| **Ground-truth preserving** | Raw copy is immutable. Processed layer is derived, disposable, rebuildable. |

---

**Document Version:** 2.0 (Post-Scrutiny)  
**Last Updated:** 2026-05-09  
**Author:** Liz 🦎  
**Branch:** `v2-design`  
**Status:** Ready for Phase 1 implementation
