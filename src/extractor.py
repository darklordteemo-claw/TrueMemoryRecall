#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Extractor Module
Daily knowledge graph extraction using Gemini Flash Lite
"""

import json
import time
import urllib.request
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import List, Dict, Optional, Tuple


def retry_with_backoff(max_retries=3, base_delay=1.0):
    """Retry decorator with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


class QwenExtractor:
    """Extracts knowledge graphs using Qwen 3.5 Flash via OpenRouter"""
    
    # Model context windows (approximate token limits)
    MODEL_CONTEXT_WINDOWS = {
        'qwen/qwen3.5-flash-02-23': 32000,  # 32K context
        'qwen/qwen3.5-flash-20260224': 32000,
        'default': 8000  # Safe default
    }
    
    # Use 70% of context window for safety
    CONTEXT_WINDOW_USAGE = 0.70
    
    # Reserve tokens for prompt template, response, and safety margin
    PROMPT_OVERHEAD = 1500  # Tokens reserved for prompt template
    MAX_RESPONSE_TOKENS = 4000  # Expected response size
    SAFETY_MARGIN = 500  # Reduced safety margin (70% handles safety)
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        # Load model from config if not provided
        if model is None:
            model = self._load_model_from_config()
        self.model = model
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Calculate max conversation tokens for this model (use 70% for safety)
        context_window = self.MODEL_CONTEXT_WINDOWS.get(model, self.MODEL_CONTEXT_WINDOWS['default'])
        usable_tokens = int(context_window * self.CONTEXT_WINDOW_USAGE)
        self.max_conversation_tokens = usable_tokens - self.PROMPT_OVERHEAD - self.MAX_RESPONSE_TOKENS - self.SAFETY_MARGIN
        # Rough estimate: 1 token ≈ 4 characters
        self.max_conversation_chars = self.max_conversation_tokens * 4
        
        print(f"  Extractor initialized: {model}")
        print(f"  Max conversation size: ~{self.max_conversation_chars} chars ({self.max_conversation_tokens} tokens)")
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars for English)"""
        return len(text) // 4
    
    def _chunk_conversation(self, conversation: str) -> List[Tuple[str, int, int]]:
        """
        Split conversation into chunks that fit within token limit.
        
        Returns list of (chunk_text, start_line, end_line) tuples.
        """
        lines = conversation.split('\n')
        total_lines = len(lines)
        
        # If conversation fits in one chunk, return as-is
        if len(conversation) <= self.max_conversation_chars:
            return [(conversation, 1, total_lines)]
        
        chunks = []
        current_chunk_lines = []
        current_chunk_size = 0
        chunk_start_line = 1
        
        for i, line in enumerate(lines, 1):
            line_size = len(line) + 1  # +1 for newline
            
            # Check if adding this line would exceed limit
            if current_chunk_size + line_size > self.max_conversation_chars and current_chunk_lines:
                # Save current chunk
                chunk_text = '\n'.join(current_chunk_lines)
                chunks.append((chunk_text, chunk_start_line, i - 1))
                
                # Start new chunk with overlap (keep last 5 lines for context)
                overlap_lines = current_chunk_lines[-5:] if len(current_chunk_lines) > 5 else current_chunk_lines
                current_chunk_lines = overlap_lines + [line]
                current_chunk_size = sum(len(l) + 1 for l in current_chunk_lines)
                chunk_start_line = i - len(overlap_lines)
            else:
                current_chunk_lines.append(line)
                current_chunk_size += line_size
        
        # Add final chunk
        if current_chunk_lines:
            chunk_text = '\n'.join(current_chunk_lines)
            chunks.append((chunk_text, chunk_start_line, total_lines))
        
        return chunks
    
    def _merge_graphs(self, graphs: List[Dict]) -> Dict:
        """Merge multiple graph chunks into single graph, removing duplicates."""
        if not graphs:
            return None
        
        if len(graphs) == 1:
            return graphs[0]
        
        # Use first graph as base
        merged = {
            "date": graphs[0]["date"],
            "source_file": graphs[0]["source_file"],
            "extraction_cost": {
                "input_tokens": sum(g["extraction_cost"]["input_tokens"] for g in graphs),
                "output_tokens": sum(g["extraction_cost"]["output_tokens"] for g in graphs),
                "total_tokens": sum(g["extraction_cost"]["total_tokens"] for g in graphs)
            },
            "entities": [],
            "relations": []
        }
        
        # Track seen entities and relations to avoid duplicates
        seen_entities = set()
        seen_relations = set()
        
        for graph in graphs:
            # Add unique entities
            for entity in graph.get("entities", []):
                if entity.lower() not in seen_entities:
                    seen_entities.add(entity.lower())
                    merged["entities"].append(entity)
            
            # Add unique relations
            for rel in graph.get("relations", []):
                rel_key = (rel.get("subject", ""), rel.get("relation", ""), rel.get("object", ""))
                if rel_key not in seen_relations:
                    seen_relations.add(rel_key)
                    merged["relations"].append(rel)
        
        return merged
    
    def _load_model_from_config(self) -> str:
        """Load model from plugin.yaml config"""
        import yaml
        config_paths = [
            Path.home() / ".openclaw" / "extensions" / "TrueMemoryRecall" / "config" / "plugin.yaml",
            Path(__file__).parent.parent / "config" / "plugin.yaml",
        ]
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        return config.get('extraction', {}).get('model', 'qwen/qwen3.5-flash-02-23')
                except Exception:
                    pass
        return 'qwen/qwen3.5-flash-02-23'
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def extract_graph(self, conversation: str, file_path: str) -> Optional[Dict]:
        """
        Extract knowledge graph from conversation.
        Automatically chunks large conversations to fit model context window.
        
        Args:
            conversation: Raw conversation text with line numbers
            file_path: Path to source file (for references)
        
        Returns:
            Dictionary with entities and relationships, or None if failed
        """
        # Check if conversation needs chunking
        estimated_tokens = self._estimate_tokens(conversation)
        
        if estimated_tokens > self.max_conversation_tokens:
            print(f"  Conversation large ({estimated_tokens} tokens), chunking...")
            chunks = self._chunk_conversation(conversation)
            print(f"  Split into {len(chunks)} chunks")
            
            # Extract from each chunk
            chunk_graphs = []
            for i, (chunk_text, start_line, end_line) in enumerate(chunks, 1):
                print(f"  Processing chunk {i}/{len(chunks)} (lines {start_line}-{end_line})...")
                graph = self._extract_single_chunk(chunk_text, file_path, start_line)
                if graph:
                    chunk_graphs.append(graph)
            
            # Merge results
            if chunk_graphs:
                return self._merge_graphs(chunk_graphs)
            return None
        else:
            # Small enough to process in one go
            return self._extract_single_chunk(conversation, file_path, 1)
    
    def _extract_single_chunk(self, conversation: str, file_path: str, start_line_offset: int = 1) -> Optional[Dict]:
        """Extract narrative summaries from a single chunk (internal method)."""
        prompt = f"""You are a memory extraction system. Read the conversation and produce 1-3 sentence narrative summaries.

For each significant memory, write a concise summary that captures:
- WHO was involved
- WHAT happened or was decided  
- WHEN it happened
- WHY it matters

Each summary must be 1-3 sentences, plain text (NOT triples).

For each memory, also provide:
- line_start: starting line number in this conversation
- line_end: ending line number
- evidence: the exact quote this is based on

Also extract a list of key entities (people, projects, technologies, concepts) mentioned.

Return ONLY JSON in this exact format:
{{
  "entities": ["TMR", "OpenRouter", "DeepSeek-V3"],
  "memories": [
    {{
      "summary": "Uddipta and Liz spent March 18 debugging TMR's OpenRouter API key issue. Liz kept using the wrong key from .bashrc instead of the .env file.",
      "line_start": 45,
      "line_end": 78,
      "evidence": "Liz: The key is returning 401 for chat completions..."
    }},
    {{
      "summary": "Uddipta prefers DeepSeek-V3 as the default model because it's free via OpenRouter with 195K context.",
      "line_start": 120,
      "line_end": 125,
      "evidence": "Uddipta: Default model: DeepSeek-V3 (free via OpenRouter)"
    }}
  ]
}}

Conversation (with line numbers):
{conversation}

Source file: {file_path}

Note: This is chunk starting at line {start_line_offset}. Adjust line numbers accordingly."""

        try:
            data = json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0
            }).encode('utf-8')
            
            req = urllib.request.Request(
                self.api_url,
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}'
                },
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                # Track usage
                usage = result.get("usage", {})
                cost_info = {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }
                
                content = result["choices"][0]["message"]["content"]
                return self._parse_response(content, file_path, cost_info, conversation, start_line_offset)
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f"  HTTP Error {e.code}: {error_body[:200]}")
            return None
        except Exception as e:
            import traceback
            print(f"  Extraction error: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None
    
    def _extract_text_snippet(self, conversation: str, line_start: int, line_end: int) -> str:
        """Extract text snippet from conversation based on line numbers"""
        lines = conversation.split('\n')
        # Adjust for 1-based line numbers
        start_idx = max(0, line_start - 1)
        end_idx = min(len(lines), line_end)
        
        if start_idx >= len(lines) or start_idx >= end_idx:
            return ""
        
        snippet_lines = lines[start_idx:end_idx]
        return '\n'.join(snippet_lines).strip()
    
    def _parse_response(self, content: str, file_path: str, cost_info: Dict, conversation: str = None, line_offset: int = 1) -> Optional[Dict]:
        """Parse Qwen response into structured graph"""
        import re
        
        # Extract JSON block (handle markdown code blocks)
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if code_block_match:
            content = code_block_match.group(1)
        
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return None
        
        try:
            data = json.loads(json_match.group())
            
            # Add metadata
            graph = {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_file": file_path,
                "extraction_cost": cost_info,
                "entities": [],
                "relations": []
            }
            
            # Extract entities
            graph["entities"] = data.get("entities", [])

            # Handle new memories format
            memories = data.get("memories", [])
            for mem in memories:
                line_start = mem.get("line_start", 0)
                line_end = mem.get("line_end", line_start)
                
                # Adjust line numbers for chunk offset
                if line_offset > 1:
                    line_start = line_start + line_offset - 1
                    line_end = line_end + line_offset - 1
                
                summary = mem.get("summary", "")
                evidence = mem.get("evidence", "")
                
                # Extract a pseudo-subject/object from summary for backward compat
                # Use first sentence or first 10 words as subject hint
                subject_hint = summary.split('.')[0][:50] if summary else "Memory"
                
                formatted_rel = {
                    "subject": "User",
                    "relation": "REMEMBERED",
                    "object": subject_hint,
                    "strength": mem.get("strength", 0.5),
                    "evidence": evidence,
                    "summary": summary,
                    "source": {
                        "file": file_path,
                        "line_start": line_start,
                        "line_end": line_end,
                        "text_snippet": evidence
                    }
                }
                graph["relations"].append(formatted_rel)
            
            # Also handle old relations format for backward compat
            for rel in data.get("relations", []):
                line_start = rel.get("line_start", 0)
                line_end = rel.get("line_end", line_start)
                
                if line_offset > 1:
                    line_start = line_start + line_offset - 1
                    line_end = line_end + line_offset - 1
                
                text_snippet = rel.get("text_snippet", "")
                if not text_snippet and conversation and line_start > 0:
                    text_snippet = self._extract_text_snippet(conversation, line_start - line_offset + 1, line_end - line_offset + 1)
                
                # Build summary from relation
                subject = rel.get("subject", "User")
                relation = rel.get("relation", "DISCUSSED")
                obj = rel.get("object", "something")
                summary = f"{subject} {relation.lower()} {obj}."
                
                formatted_rel = {
                    "subject": subject,
                    "relation": relation,
                    "object": obj,
                    "strength": rel.get("strength", 0.5),
                    "evidence": rel.get("evidence", ""),
                    "summary": summary,
                    "source": {
                        "file": file_path,
                        "line_start": line_start,
                        "line_end": line_end,
                        "text_snippet": text_snippet
                    }
                }
                graph["relations"].append(formatted_rel)
            
            return graph
            
        except json.JSONDecodeError:
            return None


if __name__ == "__main__":
    import sys
    import os
    
    # Test extraction with sample data
    print("Testing Qwen Extractor...")
    
    api_key = os.environ.get('TMR_API_KEY') or os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        print("Error: TMR_API_KEY or OPENROUTER_API_KEY not set")
        sys.exit(1)
    
    extractor = QwenExtractor(api_key=api_key)
    
    sample = """1. [10:00] User: thinking about lunch
2. [10:01] User: maybe that italian place
3. [10:02] Liz: Marcello's?
4. [10:03] User: yeah the carbonara was amazing there"""
    
    graph = extractor.extract_graph(sample, "test.md")
    
    if graph:
        print(f"Success! Found {len(graph.get('entities', []))} entities")
        print(f"Relations: {len(graph.get('relations', []))}")
    else:
        print("Extraction failed")
        sys.exit(1)
