# TMR v2 Session Checkpoint
## Date: 2026-03-18
## Status: IMPLEMENTED, INTEGRATED, DOCUMENTED

---

## Snapshot

TMR v2 now has:
- full Cognee-style retrieval pipeline
- real-time-ish chunked buffering
- 2-hour extraction schedule
- centralized configuration
- logs consolidated into the plugin directory
- documentation updated to reflect actual feedback-loop state

---

## Implemented Components

### Core pipeline
- `src/tmr_injector.py` — unified orchestrator
- `src/intent_classifier.py` — intent routing
- `src/query_planner.py` — retrieval strategy planner
- `src/graph_traversal.py` — multi-hop traversal
- `src/feedback_loop.py` — retrieval logging, scoring, re-ranking

### Real-time-ish ingestion
- `src/message_buffer.py` — temp buffering + chunk flush rules
- `scripts/incremental_extractor.py` — extract only new/changed files
- `config/crontab.txt` — 2-hour schedule + flush schedule

### Integration/logging
- `src/tmr_session_integration.py` — session-facing integration + detailed logging
- `index.ts` / `src/plugin.py` — active plugin path uses plugin-side logs

---

## Important Clarification: Feedback Loop Status

The feedback system is **partially operational**:

### Working now
- retrieval events logged
- injected memories stored per retrieval event
- memory usefulness tracking exists
- adaptive ranking machinery exists
- feedback records can be accepted and persisted

### Not fully wired yet
- automatic post-response scoring is **not fully integrated** into the live reply path
- user does **not** currently have a dedicated explicit feedback UI
- `last_injection.md` is for debugging/transparency only, not the real feedback UX

### Planned next improvement
- AI-generated implicit feedback after each reply:
  - compare user query
  - compare injected memories
  - compare final assistant response
  - auto-mark memories as helpful / weakly useful / ignored

---

## Logging Policy (Updated)

### Correct locations
All plugin logs must stay inside:
- `~/.openclaw/extensions/TrueMemoryRecall/logs/`

Examples:
- `tmr.log`
- `tmr_injection_detail.log`
- `last_injection.md`
- `extraction.log`
- `cron.log`
- `buffer.log`

### Memory directory rule
`~/.openclaw/workspace/memory/` should contain only:
- `raw/`
- `graph/`
- `feedback/`

No ordinary plugin logs should live directly in `memory/`.

### Action taken
- removed stale `workspace/memory/last_injection.md`
- ensured active `last_injection.md` path is plugin-side
- updated docs to reflect that

---

## Documentation Updated This Session

- `FINAL_DOCUMENTATION.md`
  - added current-vs-planned feedback model clarification
  - confirms `logs/last_injection.md` lives in plugin logs

- `PHASE5_INTEGRATION_SUMMARY.md`
  - clarified that feedback loop exists but auto post-response scoring is not fully wired yet

- `PLAN_VS_REALITY.md`
  - added feedback-architecture clarification section

---

## Operational Notes

### Cron
Installed and active:
- incremental extraction every 2 hours
- buffer flush every 2 hours (offset)
- full re-extraction daily

### Inspection
Automated inspection routine exists:
- `scripts/inspect_system.sh`

### Current system state
- production-leaning
- integrated
- test-backed
- still needs final feedback auto-wiring for true self-improvement UX

---

## Next Recommended Task

Implement **auto-feedback integration** into the live response path so that:
1. injected memories are compared against the actual response
2. feedback is recorded automatically
3. ranking improves without manual user inspection

---

**Maintainer note:** documentation now reflects the real system more honestly than the earlier checkpoint claims.
