#!/usr/bin/env python3
"""
TrueMemoryRecall (TMR) Plugin - Extractor Module
Daily knowledge graph extraction using Gemini Flash Lite
"""

import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class GeminiExtractor:
    """Extracts knowledge graphs using Gemini Flash Lite via OpenRouter"""
    
    def __init__(self, api_key: str, model: str = "google/gemini-2.0-flash-lite-001"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def extract_graph(self, conversation: str, file_path: str) -> Optional[Dict]:
        """
        Extract knowledge graph from conversation.
        
        Args:
            conversation: Raw conversation text with line numbers
            file_path: Path to source file (for references)
        
        Returns:
            Dictionary with entities and relationships, or None if failed
        """
        prompt = f"""Extract a knowledge graph from this conversation.

Focus on:
- People (speakers, mentioned individuals)
- Places (restaurants, locations, venues)
- Foods (dishes, cuisines, ingredients)
- Concepts (technologies, ideas, projects)
- Preferences (likes, dislikes, avoidances)
- Decisions (commitments, plans, choices)
- Experiences (good/bad events, stories)

For each relationship, identify:
- strength: 0.0-1.0 (confidence level)
- evidence: exact quote from conversation
- line numbers: where this appears

Return ONLY JSON in this exact format:
{{
  "entities": ["entity1", "entity2", "entity3"],
  "relations": [
    {{
      "subject": "person",
      "relation": "LIKES|DISLIKES|WENT_TO|DISCUSSED|DECIDED|EXPERIENCED",
      "object": "entity",
      "strength": 0.95,
      "evidence": "exact quote",
      "line_start": 4,
      "line_end": 4
    }}
  ]
}}

Conversation (with line numbers):
{conversation}

Source file: {file_path}"""

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
                return self._parse_response(content, file_path, cost_info)
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f"  HTTP Error {e.code}: {error_body[:200]}")
            return None
        except Exception as e:
            import traceback
            print(f"  Extraction error: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None
    
    def _parse_response(self, content: str, file_path: str, cost_info: Dict) -> Optional[Dict]:
        """Parse Gemini response into structured graph"""
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
                "entities": data.get("entities", []),
                "relations": []
            }
            
            # Format relations with source info
            for rel in data.get("relations", []):
                formatted_rel = {
                    "subject": rel.get("subject"),
                    "relation": rel.get("relation"),
                    "object": rel.get("object"),
                    "strength": rel.get("strength", 0.5),
                    "evidence": rel.get("evidence", ""),
                    "source": {
                        "file": file_path,
                        "line_start": rel.get("line_start", 0),
                        "line_end": rel.get("line_end", 0)
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
    print("Testing Gemini Extractor...")
    
    api_key = os.environ.get('TMR_API_KEY') or os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        print("Error: TMR_API_KEY or OPENROUTER_API_KEY not set")
        sys.exit(1)
    
    extractor = GeminiExtractor(api_key=api_key)
    
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
