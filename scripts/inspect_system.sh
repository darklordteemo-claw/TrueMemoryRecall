#!/bin/bash
# TMR v2 - Complete System Inspection Routine
# Run this script to verify all components are working

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    TMR v2 - SYSTEM INSPECTION ROUTINE                        ║"
echo "║                         $(date '+%Y-%m-%d %H:%M:%S')                          ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠️ WARN${NC}: $1"
    ((WARNINGS++))
}

section() {
    echo
    echo "═══════════════════════════════════════════════════════════════════════════════"
    echo "  $1"
    echo "═══════════════════════════════════════════════════════════════════════════════"
}

# ============================================
# SECTION 1: DIRECTORY STRUCTURE
# ============================================
section "SECTION 1: DIRECTORY STRUCTURE VERIFICATION"

DIRS=(
    "$HOME/.openclaw/extensions/TrueMemoryRecall"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/config"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/logs"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/tests"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/temp"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/scripts"
    "$HOME/.openclaw/workspace/memory/raw"
    "$HOME/.openclaw/workspace/memory/graph"
    "$HOME/.openclaw/workspace/memory/feedback"
)

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        pass "Directory exists: $(basename $dir)"
    else
        fail "Directory missing: $dir"
    fi
done

# ============================================
# SECTION 2: CORE FILES
# ============================================
section "SECTION 2: CORE FILES VERIFICATION"

FILES=(
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/tmr_injector.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/intent_classifier.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/query_planner.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/graph_traversal.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/feedback_loop.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/message_buffer.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/tmr_session_integration.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/config_loader.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/qdrant_manager.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/embedder.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/extractor.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/src/plugin.py"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/config/tmr_config.yaml"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/index.ts"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        pass "File exists: $(basename $file)"
    else
        fail "File missing: $file"
    fi
done

# ============================================
# SECTION 3: EXTERNAL DEPENDENCIES
# ============================================
section "SECTION 3: EXTERNAL DEPENDENCIES"

# Check Python packages
echo "Checking Python packages..."
python3 -c "import qdrant_client" 2>/dev/null && pass "qdrant_client package" || fail "qdrant_client package"
python3 -c "import yaml" 2>/dev/null && pass "pyyaml package" || fail "pyyaml package"
python3 -c "import requests" 2>/dev/null && pass "requests package" || fail "requests package"
python3 -c "import pytz" 2>/dev/null && pass "pytz package" || fail "pytz package"

# Check external services
echo
echo "Checking external services..."

# Qdrant
if curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
    pass "Qdrant service running"
else
    fail "Qdrant service not running"
fi

# Ollama
if curl -s http://192.168.1.100:11434/api/tags > /dev/null 2>&1; then
    pass "Ollama service running"
else
    warn "Ollama service not running (optional for fallback)"
fi

# ============================================
# SECTION 4: QDRANT COLLECTIONS
# ============================================
section "SECTION 4: QDRANT COLLECTIONS"

if command -v jq &> /dev/null; then
    COLLECTIONS=$(curl -s http://localhost:6333/collections 2>/dev/null | jq -r '.result.collections[].name' 2>/dev/null)
    
    if echo "$COLLECTIONS" | grep -q "tmr_knowledge_graph"; then
        pass "Collection: tmr_knowledge_graph"
        COUNT=$(curl -s http://localhost:6333/collections/tmr_knowledge_graph | jq '.result.points_count' 2>/dev/null)
        echo "    Points: $COUNT"
    else
        fail "Collection missing: tmr_knowledge_graph"
    fi
    
    if echo "$COLLECTIONS" | grep -q "tmr_semantic_vectors"; then
        pass "Collection: tmr_semantic_vectors"
        COUNT=$(curl -s http://localhost:6333/collections/tmr_semantic_vectors | jq '.result.points_count' 2>/dev/null)
        echo "    Points: $COUNT"
    else
        fail "Collection missing: tmr_semantic_vectors"
    fi
    
    if echo "$COLLECTIONS" | grep -q "tmr_agents_files"; then
        pass "Collection: tmr_agents_files"
        COUNT=$(curl -s http://localhost:6333/collections/tmr_agents_files | jq '.result.points_count' 2>/dev/null)
        echo "    Points: $COUNT"
    else
        fail "Collection missing: tmr_agents_files"
    fi
else
    warn "jq not installed, skipping collection verification"
fi

# ============================================
# SECTION 5: CONFIGURATION
# ============================================
section "SECTION 5: CONFIGURATION VERIFICATION"

cd "$HOME/.openclaw/extensions/TrueMemoryRecall" 2>/dev/null || exit 1

python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from config_loader import get_config
    c = get_config()
    print('CONFIG_OK')
    print(f'graph_dir: {c.storage.get(\"graph_dir\", \"NOT SET\")}')
    print(f'raw_dir: {c.storage.get(\"raw_dir\", \"NOT SET\")}')
    print(f'intents: {len(c.get_all_intents())}')
except Exception as e:
    print(f'CONFIG_ERROR: {e}')
" 2>&1 | grep -q "CONFIG_OK" && pass "Configuration loads successfully" || fail "Configuration error"

# Check API key
if [ -f ".env" ]; then
    if grep -q "OPENROUTER_API_KEY" .env; then
        pass "OpenRouter API key configured"
    else
        fail "OpenRouter API key not found in .env"
    fi
else
    fail ".env file not found"
fi

# ============================================
# SECTION 6: COMPONENT INITIALIZATION
# ============================================
section "SECTION 6: COMPONENT INITIALIZATION"

cd "$HOME/.openclaw/extensions/TrueMemoryRecall"

# Test IntentClassifier
python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from intent_classifier import IntentClassifier
    c = IntentClassifier()
    i, conf = c.classify('test query')
    print('INTENT_OK')
except Exception as e:
    print(f'INTENT_ERROR: {e}')
" 2>&1 | grep -q "INTENT_OK" && pass "IntentClassifier initializes" || fail "IntentClassifier error"

# Test QueryPlanner
python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from query_planner import QueryPlanner
    p = QueryPlanner()
    plan = p.plan('test', 'greeting', 0.9, {'graph': 0.4, 'semantic': 0.6})
    print('PLANNER_OK')
except Exception as e:
    print(f'PLANNER_ERROR: {e}')
" 2>&1 | grep -q "PLANNER_OK" && pass "QueryPlanner initializes" || fail "QueryPlanner error"

# Test GraphTraversal
python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from graph_traversal import MultiHopTraversal
    from qdrant_manager import QdrantManager
    q = QdrantManager()
    t = MultiHopTraversal(q)
    print('TRAVERSAL_OK')
except Exception as e:
    print(f'TRAVERSAL_ERROR: {e}')
" 2>&1 | grep -q "TRAVERSAL_OK" && pass "GraphTraversal initializes" || fail "GraphTraversal error"

# Test FeedbackLoop
python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from feedback_loop import CogneeStyleFeedbackLoop
    f = CogneeStyleFeedbackLoop()
    print('FEEDBACK_OK')
except Exception as e:
    print(f'FEEDBACK_ERROR: {e}')
" 2>&1 | grep -q "FEEDBACK_OK" && pass "FeedbackLoop initializes" || fail "FeedbackLoop error"

# Test MessageBuffer
python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from message_buffer import MessageBuffer
    b = MessageBuffer()
    print('BUFFER_OK')
except Exception as e:
    print(f'BUFFER_ERROR: {e}')
" 2>&1 | grep -q "BUFFER_OK" && pass "MessageBuffer initializes" || fail "MessageBuffer error"

# ============================================
# SECTION 7: FULL INTEGRATION TEST
# ============================================
section "SECTION 7: FULL INTEGRATION TEST"

cd "$HOME/.openclaw/extensions/TrueMemoryRecall"

python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from tmr_injector import TMRCogneeInjector
    injector = TMRCogneeInjector(enable_feedback=True)
    result = injector.inject_context('How are you?')
    memories = result.count('→') if result else 0
    print(f'INTEGRATION_OK: {memories} memories')
except Exception as e:
    print(f'INTEGRATION_ERROR: {e}')
" 2>&1 | grep -q "INTEGRATION_OK" && pass "Full pipeline operational" || fail "Integration test failed"

# ============================================
# SECTION 8: CRON JOBS
# ============================================
section "SECTION 8: CRON JOB VERIFICATION"

if crontab -l 2>/dev/null | grep -q "incremental_extractor"; then
    pass "Incremental extractor cron installed"
else
    fail "Incremental extractor cron not installed"
fi

if crontab -l 2>/dev/null | grep -q "time_based_flush\|message_buffer"; then
    pass "Buffer flush cron installed"
else
    fail "Buffer flush cron not installed"
fi

echo
echo "Current cron schedule:"
crontab -l 2>/dev/null | grep -E "^#|incremental|buffer" | head -10

# ============================================
# SECTION 9: LOG FILES
# ============================================
section "SECTION 9: LOG FILE VERIFICATION"

LOGS=(
    "$HOME/.openclaw/extensions/TrueMemoryRecall/logs/tmr.log"
    "$HOME/.openclaw/extensions/TrueMemoryRecall/logs/last_injection.md"
)

for log in "${LOGS[@]}"; do
    if [ -f "$log" ]; then
        pass "Log exists: $(basename $log)"
    else
        warn "Log missing: $(basename $log)"
    fi
done

echo
echo "Log file sizes:"
cd "$HOME/.openclaw/extensions/TrueMemoryRecall/logs" 2>/dev/null && du -sh * 2>/dev/null | sort -h

# ============================================
# SECTION 10: DATA INTEGRITY
# ============================================
section "SECTION 10: DATA INTEGRITY"

# Check raw files
RAW_COUNT=$(ls -1 "$HOME/.openclaw/workspace/memory/raw/"*.md 2>/dev/null | wc -l)
if [ $RAW_COUNT -gt 0 ]; then
    pass "Raw files present: $RAW_COUNT files"
else
    warn "No raw files found"
fi

# Check graph files
GRAPH_COUNT=$(ls -1 "$HOME/.openclaw/workspace/memory/graph/"*.json 2>/dev/null | wc -l)
if [ $GRAPH_COUNT -gt 0 ]; then
    pass "Graph files present: $GRAPH_COUNT files"
else
    warn "No graph files found"
fi

# Check for recent activity
RECENT_RAW=$(find "$HOME/.openclaw/workspace/memory/raw/" -name "*.md" -mtime -1 2>/dev/null | wc -l)
if [ $RECENT_RAW -gt 0 ]; then
    pass "Recent raw files (last 24h): $RECENT_RAW"
else
    warn "No recent raw files (last 24h)"
fi

# ============================================
# SUMMARY
# ============================================
echo
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                           INSPECTION SUMMARY                                 ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo
echo -e "${GREEN}✅ PASSED:${NC}  $PASSED"
echo -e "${RED}❌ FAILED:${NC}   $FAILED"
echo -e "${YELLOW}⚠️ WARNINGS:${NC} $WARNINGS"
echo

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}                    SYSTEM STATUS: OPERATIONAL ✅${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    exit 0
else
    echo -e "${RED}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}                    SYSTEM STATUS: ISSUES DETECTED ❌${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════════════════════${NC}"
    exit 1
fi
