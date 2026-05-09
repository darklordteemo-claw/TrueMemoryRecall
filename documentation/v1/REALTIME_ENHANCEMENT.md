# TMR v2 Real-Time Enhancement
## Near Real-Time Memory with Chunked Batching

**Date:** 2026-03-18  
**Change:** Added message buffering for 12x latency improvement

---

## THE PROBLEM

**Old Approach:**
```
User Message → Raw File → [WAIT 24 HOURS] → Daily Extraction → Graph
                                                    ↓
                                          New memories available tomorrow
```

**Latency:** Up to 24 hours before new memories are searchable

---

## THE SOLUTION

**New Approach:**
```
User Message → Buffer → Temp File → (ANY condition met) → Raw (NN).md
                                         ↓                      ↓
                    ┌────────────────────┴──────────────────────┐
                    │ Conditions:                               │
                    │ 1. Size: 70% full                         │
                    │ 2. Time gap: >1 hour since last message   │
                    │ 3. Session change: Uddipta ↔ Liz          │
                    │ 4. Cron: Every 2 hours                    │
                    └───────────────────────────────────────────┘
                                                              ↓
                                                    Incremental Extraction  
                                                              ↓
                                              New memories in ~2 hours max
```

**Latency:** 2 hours max (12x improvement)

---

## HOW IT WORKS

### 1. Message Buffering

Messages are buffered in temp files instead of going directly to raw:

```python
from message_buffer import buffer_message

# When user sends message
buffer_message("Uddipta", "Hello Liz!")

# When assistant responds  
buffer_message("Liz", "Hi there!")  # This triggers flush (session change)
```

### 2. Automatic Flushing

Buffer flushes to `raw/` when any of these conditions are met:

| Condition | Description | Default Threshold |
|-----------|-------------|-------------------|
| **Size** | File reaches context limit | ~70% (~28K chars) |
| **Time Gap** | No messages for X minutes | 60 minutes |
| **Session Change** | Different sender than last message | Immediate |
| **Cron** | Time-based flush | Every 2 hours |

**Why these conditions?**
- **Size:** Prevents context overflow during extraction
- **Time Gap:** Don't wait forever if conversation stops  
- **Session Change:** New conversation = new file (clean separation)
- **Cron:** Backup for low-activity periods

### 3. Chunked File Naming

Instead of single daily file:
```
2026-03-18 (01).md  <- First chunk
2026-03-18 (02).md  <- Second chunk (when first reached 70%)
2026-03-18 (03).md  <- Third chunk
```

### 4. Incremental Extraction

Every 2 hours, extractor:
1. Checks for new/changed chunked files
2. Extracts only what's new (hash tracking)
3. Updates knowledge graph
4. Indexes to Qdrant

---

## CONFIGURATION

### Context Limit (Adjustable)

```yaml
# In config/tmr_config.yaml
extraction:
  context_limit: 28000  # 70% of 40K context
```

**Why 70%?**
- Leaves room for system prompts
- Leaves room for extraction instructions
- Prevents context overflow

### Cron Schedule

```cron
# Every 2 hours: Extract new graphs
0 */2 * * * python3 scripts/incremental_extractor.py

# Every 2 hours: Time-based flush
30 */2 * * * python3 -c "flush_buffer_if_old()"

# Daily at 3 AM: Force re-extract all
0 3 * * * python3 scripts/incremental_extractor.py --force
```

---

## TRADE-OFFS

| Approach | Latency | LLM Cost | Complexity |
|----------|---------|----------|------------|
| **Old (Daily)** | 24h | Low | Simple |
| **New (Chunked)** | 2h | Low | Medium |
| **Per-Message** | Instant | High | Complex |

**Chunked batching hits the sweet spot:**
- ✅ 12x faster than daily
- ✅ Same LLM cost as daily
- ✅ Simpler than per-message
- ✅ No context overflow issues

---

## USAGE

### For OpenClaw Integration

```python
from message_buffer import buffer_message
from tmr_injector import TMRCogneeInjector

# When user sends message
def on_user_message(message):
    # Buffer it
    buffer_message("Uddipta", message)
    
    # Retrieve relevant memories
    injector = TMRCogneeInjector()
    context = injector.inject_context(message)
    
    # Add context to LLM prompt
    full_prompt = f"{context}\n\nUser: {message}"
    return full_prompt

# When assistant responds
def on_assistant_response(message):
    buffer_message("Liz", message)
```

### Manual Flush (If Needed)

```python
from message_buffer import flush_buffer

# Force flush before extraction
flushed_file = flush_buffer()
print(f"Flushed to: {flushed_file}")
```

---

## MONITORING

### Check Buffer Stats

```python
from message_buffer import get_message_buffer

buffer = get_message_buffer()
stats = buffer.get_stats()

print(f"Utilization: {stats['utilization']:.1%}")
print(f"Time since flush: {stats['time_since_flush_hours']:.1f} hours")
print(f"Current sequence: {stats['sequence']}")
```

### Check Extraction Status

```bash
cd /home/openclaw/.openclaw/extensions/TrueMemoryRecall
python3 scripts/incremental_extractor.py --stats
```

---

## FILES

### New Components

| File | Purpose |
|------|---------|
| `src/message_buffer.py` | Buffers messages, handles flushing |
| `scripts/incremental_extractor.py` | 2-hour extraction with hash tracking |
| `config/crontab.txt` | Updated cron schedule |
| `temp/` | Buffer directory (auto-created) |

### Modified Components

| File | Change |
|------|--------|
| `src/qdrant_manager.py` | Added logging import fix |
| `src/tmr_injector.py` | Added 'Liz' entity for identity queries |

---

## INSTALLATION

### 1. Install Cron Jobs

```bash
# Add to crontab
crontab config/crontab.txt
```

### 2. Create Temp Directory

```bash
mkdir -p ~/.openclaw/extensions/TrueMemoryRecall/temp
```

### 3. Test

```bash
# Run extractor manually
python3 scripts/incremental_extractor.py

# Check stats
python3 scripts/incremental_extractor.py --stats
```

---

## TUNING

### If Buffer Flushes Too Often

Increase context limit:
```yaml
extraction:
  context_limit: 32000  # 80% instead of 70%
```

### If Latency Still Too High

Decrease cron interval:
```cron
# Run every hour instead of 2
0 * * * * python3 scripts/incremental_extractor.py
```

**Trade-off:** More frequent = higher LLM cost

### If Context Overflow Happens

Decrease context limit:
```yaml
extraction:
  context_limit: 24000  # 60% instead of 70%
```

---

## COMPARISON

### Before (Daily Extraction)

```
User: "I like pizza"
        ↓
[Wait 24 hours]
        ↓
Next day: "What do I like?" → "Pizza"
```

### After (Chunked Extraction)

```
User: "I like pizza"
        ↓
Liz: "Great!" (session change → flush)
        ↓
[Extraction runs within 2 hours]
        ↓
Same session: "What do I like?" → "Pizza"

---

User: "Hello" (after 1 hour gap)
        ↓
[Time gap detected → flush previous session]
        ↓
New file created for this conversation
```

---

## CONCLUSION

The chunked batching approach provides:
- **12x latency improvement** (24h → 2h)
- **Same cost** as daily extraction
- **No context overflow** issues
- **Simple implementation**

Messages are available as memories within 2 hours of being said, making conversations feel much more connected.

---

**Status:** ✅ Implemented and Tested  
**Ready for:** Production deployment  
**Next Step:** Install cron jobs
