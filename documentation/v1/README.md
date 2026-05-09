# TrueMemoryRecall (TMR) 🧠

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-33%2F33%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue.svg)]()

> OpenClaw memory plugin with knowledge graphs — auto-capture, auto-extract, auto-inject.

**Zero LLM cost** during real-time storage. **Twice-daily** knowledge graph extraction.

---

## 🚀 Features

| Feature | Status | Description |
|---------|--------|-------------|
| **Auto-Capture** | ✅ Ready | Messages saved to daily markdown files |
| **Auto-Extract** | ✅ Ready | Twice-daily knowledge graph via Gemini |
| **Auto-Inject** | ✅ Ready | Context injection with adaptive thresholds |
| **Smart Restart** | ✅ Ready | Delayed gateway restart with completion marker |

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/TeemoAI/TrueMemoryRecall.git
cd TrueMemoryRecall

# Install Python dependencies
pip install qdrant-client pyyaml

# Copy to OpenClaw extensions
cp -r . ~/.openclaw/extensions/TrueMemoryRecall

# Configure your API key in config/plugin.yaml
# Then restart OpenClaw
```

---

## 🔧 OpenClaw Installation Guide

### Prerequisites

1. **OpenClaw Gateway** installed and running
2. **Qdrant** running locally (or accessible remotely):
   ```bash
   docker run -p 6333:6333 qdrant/qdrant
   ```
3. **Python 3.10+** with pip

### Step-by-Step Setup

#### 1. Clone and Install

```bash
git clone https://github.com/TeemoAI/TrueMemoryRecall.git
cd TrueMemoryRecall

# Install Python dependencies
pip install qdrant-client pyyaml
```

#### 2. Copy to OpenClaw Extensions

```bash
# Create extensions directory if it doesn't exist
mkdir -p ~/.openclaw/extensions

# Copy TMR to OpenClaw
cp -r TrueMemoryRecall ~/.openclaw/extensions/

# Verify structure
ls ~/.openclaw/extensions/TrueMemoryRecall/
# Should show: index.ts, src/, scripts/, config/, etc.
```

#### 3. Configure API Keys

**Set the TMR_API_KEY environment variable:**

```bash
# Add to ~/.bashrc or ~/.zshrc for persistence
export TMR_API_KEY="sk-or-v1-your-key-here"

# Or set temporarily for current session
export TMR_API_KEY="sk-or-v1-your-key-here"
```

Get your API key from: https://openrouter.ai/keys

**Optional: Edit `~/.openclaw/extensions/TrueMemoryRecall/config/plugin.yaml`:**

```yaml
openrouter:
  # Uses TMR_API_KEY env var by default
  # Or set explicitly here (not recommended for security)
  api_key: "${TMR_API_KEY}"
  model: "google/gemini-2.0-flash-lite-001"

qdrant:
  host: "localhost"
  port: 6333
  # If using remote Qdrant:
  # url: "https://your-qdrant-instance.com"
  # api_key: "your-qdrant-api-key"

tmr:
  extraction_schedule: "0 12,0 * * *"  # 12PM and 12AM
  thresholds:
    recent: 0.85   # 0-7 days: high confidence
    medium: 0.70   # 7-30 days: medium confidence
    old: 0.60      # 30+ days: lower threshold
```

#### 4. Set Up Cron (Optional but Recommended)

**Option A: System Cron**
```bash
# Edit crontab
crontab -e

# Add these lines for twice-daily extraction
0 12 * * * /usr/bin/python3 ~/.openclaw/extensions/TrueMemoryRecall/scripts/twice-daily-extract.py >> ~/.openclaw/extensions/TrueMemoryRecall/logs/cron.log 2>&1
0 0 * * * /usr/bin/python3 ~/.openclaw/extensions/TrueMemoryRecall/scripts/twice-daily-extract.py >> ~/.openclaw/extensions/TrueMemoryRecall/logs/cron.log 2>&1
```

**Option B: OpenClaw Cron (if available)**
```bash
# Copy job definitions
cp ~/.openclaw/extensions/TrueMemoryRecall/config/cron-jobs.json ~/.openclaw/.openclaw/cron/jobs.json
```

#### 5. Configure OpenClaw Memory Slot

Edit your OpenClaw config (`~/.openclaw/.openclaw/openclaw.json`):

```json
{
  "plugins": {
    "slots": {
      "memory": "true-memory-recall"
    },
    "entries": {
      "true-memory-recall": {
        "path": "~/.openclaw/extensions/TrueMemoryRecall/index.ts",
        "enabled": true
      }
    }
  }
}
```

#### 6. Create Required Directories

```bash
# Create data directories
mkdir -p ~/.openclaw/workspace/memory/raw
mkdir -p ~/.openclaw/workspace/memory/graph
mkdir -p ~/.openclaw/extensions/TrueMemoryRecall/logs
```

#### 7. Restart OpenClaw

```bash
# Option 1: Using the safe restart script
cd ~/.openclaw/extensions/TrueMemoryRecall
python3 scripts/trigger_restart.py --confirm

# Option 2: Manual restart
systemctl --user restart openclaw-gateway
# or
openclaw gateway restart
```

#### 8. Verify Installation

Check the logs to confirm TMR loaded:
```bash
tail -f /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep -i "TMR"
```

You should see:
```
[TMR] Plugin registered
[TMR] Plugin initialized
```

Send a test message and verify it's captured:
```bash
tail ~/.openclaw/workspace/memory/raw/$(date +%Y-%m-%d).md
```

---

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "Plugin not loading" | Check `openclaw.json` path is correct and absolute |
| "Qdrant connection failed" | Verify Qdrant is running: `curl http://localhost:6333` |
| "No messages being saved" | Check file permissions on `memory/raw/` directory |
| "Extraction not running" | Check cron is set up and script is executable |
| "API key errors" | Verify key in `config/plugin.yaml` is valid |

---

### Customization

**Change extraction frequency:**
Edit `scripts/twice-daily-extract.py` or modify your cron schedule.

**Adjust thresholds:**
Higher values = more selective injection. Lower values = more aggressive.

**Use different model:**
Update `config/plugin.yaml` with any OpenRouter model ID.

**Custom data directory:**
Modify `index.ts` and Python files to change `RAW_DIR` and `graph_dir`.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway                         │
├─────────────────────────────────────────────────────────────┤
│  TypeScript Layer (Hooks)          Python Layer (Logic)     │
│  ┌─────────────────────┐          ┌──────────────────┐     │
│  │ message_received    │─────────▶│ filter.py        │     │
│  │ agent_end           │─────────▶│ storage.py       │     │
│  │ before_agent_start  │◀─────────│ injector.py      │     │
│  └─────────────────────┘          └────────┬─────────┘     │
│                                            │               │
│  ┌─────────────────────────────────────────▼─────────────┐ │
│  │              Qdrant Vector Database                   │ │
│  │  ┌─────────────┐  ┌──────────┐  ┌─────────────────┐  │ │
│  │  │conversations│  │line_index│  │knowledge_graph  │  │ │
│  │  └─────────────┘  └──────────┘  └─────────────────┘  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 File Structure

```
TrueMemoryRecall/
├── index.ts                    # OpenClaw plugin entry
├── src/
│   ├── plugin.py              # Main Python entry
│   ├── filter.py              # Message filtering (14 tests)
│   ├── storage.py             # Daily file storage (4 tests)
│   ├── qdrant_manager.py      # Vector DB (5 tests)
│   ├── extractor.py           # Gemini extraction (3 tests)
│   └── injector.py            # Context injection (3 tests)
├── scripts/
│   ├── daily_process.py       # Cron extraction script
│   ├── twice-daily-extract.py # 12PM + 12AM extraction
│   ├── restart-gateway.sh     # Safe restart helper
│   └── trigger_restart.py     # Restart trigger
├── config/
│   └── plugin.yaml            # Configuration + API keys
└── tests/                     # 33 tests total
```

**Data Storage:**
```
~/.openclaw/workspace/memory/
├── raw/                       # Daily conversation files
│   └── YYYY-MM-DD.md
└── graph/                     # Knowledge graphs
    └── YYYY-MM-DD.json
```

---

## ⚙️ Configuration

Create `config/plugin.yaml`:

```yaml
openrouter:
  api_key: "sk-or-v1-..."      # Your TMR-specific API key
  model: "google/gemini-2.0-flash-lite-001"

qdrant:
  host: "localhost"
  port: 6333
  collections:
    prefix: "tmr_"

tmr:
  extraction_schedule: "0 12,0 * * *"  # 12PM & 12AM
  thresholds:
    recent: 0.85    # 0-7 days
    medium: 0.70    # 7-30 days
    old: 0.60       # 30+ days
```

---

## 🔄 How It Works

### 1. Auto-Capture (Real-time, Zero LLM Cost)
```
User: "thinking about the memory system"
  ↓ [Filter] ✅ Keep (10+ chars, not filler)
  ↓ [Storage] Append to memory/raw/2026-03-16.md
  ↓ [Qdrant] Index with line reference
```

### 2. Auto-Extract (Twice Daily)
```
Read: memory/raw/2026-03-16.md
  ↓ [Qwen 3.5 Flash] Extract entities & relations
  ↓ [Save] memory/graph/2026-03-16.json
  ↓ [Qdrant] Store for fast lookup

Cost: ~$0.00001 per extraction
```

### 3. Auto-Inject (Every Query)
```
User: "Where should I eat?"
  ↓ [Analyze] Extract entities
  ↓ [Search] Find matching relations
  ↓ [Inject with adaptive threshold]

[RELATED MEMORY - TMR]
1. User → LIKES → Marcello's (95%)
   Source: memory/raw/2026-03-16.md:45
[END RELATED MEMORY]
```

---

## 🧪 Testing

```bash
# Run all tests
python3 -m pytest tests/ -v

# Test specific module
python3 -m pytest tests/test_filter.py -v
python3 -m pytest tests/test_storage.py -v
```

**Results:** 33/33 passing

---

## 💰 Cost Tracking

| Operation | Cost | Frequency |
|-----------|------|-----------|
| Real-time capture | $0.00 | Every message |
| Knowledge graph extraction | ~$0.000003 | Twice daily |
| Context injection | $0.00 | Every query |
| **Monthly estimate** | **<$0.50** | - |

---

## 📋 Sample Output

### Daily Conversation File
```markdown
[14:32:15] User: thinking about the memory system
[14:33:22] Liz: what aspect?
[14:35:47] User: how to make it cheaper
```

### Knowledge Graph
```json
{
  "date": "2026-03-16",
  "entities": ["User", "memory systems"],
  "relations": [{
    "subject": "User",
    "relation": "DISCUSSED",
    "object": "memory systems",
    "strength": 0.75,
    "source": {"file": "memory/raw/2026-03-16.md", "line": 1}
  }]
}
```

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## 📝 License

[MIT](LICENSE) © 2026 True Memory Recall Contributors

---

**Built with 🦎 by Liz for Teemo**
for Teemo**
mazing`)
5. Open a Pull Request

---

## 📝 License

[MIT](LICENSE) © 2026 True Memory Recall Contributors

---

**Built with 🦎 by Liz for Teemo**
