# TrueMemoryRecall (TMR) Plugin - Complete

**Status:** Phase 1, 2, 3 Complete ✅  
**Total Tests:** 33/33 passing  
**Cost:** Tracked under separate TMR OpenRouter API key

---

## What Was Built

### Core Components

| Component | File | Purpose | Tests |
|-----------|------|---------|-------|
| **Filter** | `src/filter.py` | Drop "hi", "ok", keep meaningful messages | 14/14 ✅ |
| **Storage** | `src/storage.py` | Daily files with line tracking | 4/4 ✅ |
| **Qdrant Manager** | `src/qdrant_manager.py` | Vector DB connection & indexing | 5/5 ✅ |
| **Extractor** | `src/extractor.py` | Gemini Flash Lite knowledge graph extraction | 3/3 ✅ |
| **Injector** | `src/injector.py` | Auto-inject Cognee relations + references | 3/3 ✅ |
| **Plugin Core** | `src/plugin.py` | Integration & OpenClaw hooks | 4/4 ✅ |

### Scripts

| Script | File | Purpose |
|--------|------|---------|
| **Daily Process** | `scripts/daily_process.py` | Cron job for nightly extraction |

### Configuration

| File | Purpose |
|------|---------|
| `manifest.json` | OpenClaw plugin registration |
| `config/plugin.yaml` | User configuration + TMR API key |

---

## How It Works

### 1. Auto-Extract (Real-time)
```
User: "im thinking about the memory system"
  ↓ [Filter] ✅ Keep (10+ chars, not filler)
  ↓ [Storage] Append to memory/raw/2026-03-16.md, line 4
  ↓ [Qdrant] Index: file + line 4 + speaker + timestamp
```

### 2. Daily Batch (3 AM)
```
Read: memory/raw/2026-03-16.md
  ↓ [Gemini] Extract entities & relationships
  ↓ [Save] memory/graph/2026-03-16.json
  ↓ [Qdrant] Store relations for fast lookup

Cost: ~$0.000003 per day (tracked under TMR API key)
```

### 3. Auto-Inject (Every Query)
```
User: "Where should I eat?"
  ↓ [Analyze] Extract entities: ["food", "restaurant", "eat"]
  ↓ [Search] Find matching relations in Qdrant
  ↓ [Inject]

[RELATED MEMORY - TMR]
1. Uddipta → LIKES → Marcello's (confidence: 95%)
   Evidence: "yea the carbonara was so good"
   Source: memory/raw/2026-03-16.md:45

2. Uddipta → DISLIKES → spicy food (confidence: 90%)
   Evidence: "bad experience at spice palace"
   Source: memory/raw/2026-03-16.md:52
[END RELATED MEMORY]

Me: "How about Marcello's? You loved the carbonara there..."
```

---

## File Structure

```
~/.openclaw/extensions/TrueMemoryRecall/
├── manifest.json              # Plugin manifest
├── config/
│   └── plugin.yaml           # Config + TMR API key
├── src/
│   ├── __init__.py
│   ├── plugin.py             # Main entry + hooks
│   ├── filter.py             # Message filtering
│   ├── storage.py            # Daily file storage
│   ├── qdrant_manager.py     # Qdrant connection
│   ├── extractor.py          # Gemini extraction
│   └── injector.py           # Context injection
└── scripts/
    └── daily_process.py      # Cron script

~/.openclaw/workspace/memory/
├── raw/                      # Daily conversation files
│   ├── 2026-03-16.md
│   └── ...
└── graph/                    # Extracted knowledge graphs
    ├── 2026-03-16.json
    └── ...
```

---

## Qdrant Collections

| Collection | Purpose |
|------------|---------|
| `tmr_conversations` | Vector embeddings for semantic search |
| `tmr_line_index` | Line number → byte offset mapping |
| `tmr_knowledge_graph` | Extracted relations with references |

---

## Cost Tracking

**TMR-specific OpenRouter API Key:**
- Key: `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`
- Model: `google/gemini-2.0-flash-lite-001`
- Cost per extraction: ~$0.000003 (3 millionths of a dollar)
- Monthly estimate: <$0.50

---

## Test Results Summary

```
Filter Tests:        14/14 ✅
Storage Tests:        4/4  ✅
Qdrant Tests:         5/5  ✅
Plugin Integration:   4/4  ✅
Extractor Tests:      3/3  ✅
Injector Tests:       3/3  ✅
─────────────────────────────
TOTAL:               33/33 ✅
```

---

## Next Steps (Manual/OpenClaw Integration)

To fully activate:

1. **OpenClaw Plugin Registration**
   - Copy `TrueMemoryRecall` to OpenClaw's extensions folder
   - Restart OpenClaw to load plugin

2. **Cron Setup**
   - Add to OpenClaw's cron: `0 3 * * * scripts/daily_process.py`
   - Or use system cron

3. **Test End-to-End**
   - Send messages, verify they appear in daily file
   - Wait for daily extraction (or run manually)
   - Query and verify auto-inject works

---

## Sample Output

### Daily File (`memory/raw/2026-03-16.md`)
```markdown
# 2026-03-16 — Auto-generated
# Line numbers for reference

[14:32:15] Uddipta: im thinking about the memory system we discussed
[14:33:22] Liz: yeah what aspect are you considering
[14:35:47] Uddipta: how do we make it cheaper without losing quality
```

### Knowledge Graph (`memory/graph/2026-03-16.json`)
```json
{
  "date": "2026-03-16",
  "source_file": "memory/raw/2026-03-16.md",
  "extraction_cost": {"total_tokens": 1200},
  "entities": ["Uddipta", "Liz", "memory systems"],
  "relationships": [
    {
      "subject": "Uddipta",
      "relation": "DISCUSSED",
      "object": "memory systems",
      "strength": 0.75,
      "evidence": "im thinking about the memory system",
      "source": {"file": "memory/raw/2026-03-16.md", "line_start": 4}
    }
  ]
}
```

---

**Built by Liz 🦎 for Uddipta**  
**Status: Ready for OpenClaw integration** ✅
