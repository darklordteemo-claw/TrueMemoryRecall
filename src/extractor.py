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
  "relationships": [
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
        # First try to find JSON inside ```json ... ``` blocks
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
                "relationships": []
            }
            
            # Format relationships with source info
            for rel in data.get("relationships", []):
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
                graph["relationships"].append(formatted_rel)
            
            return graph
            
        except json.JSONDecodeError:
            return None


def test_extractor():
    """Test the extractor with sample data"""
    print("="*60)
    print("TESTING: TMR Gemini Extractor")
    print("="*60)
    
    # Use the TMR-specific API key
    api_key = "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"
    
    # Sample conversation (same as test data)
    conversation = """1. # 2026-03-10 — Auto-generated
2. # Line numbers for reference
3. 
4. [18:30] User: hey liz im hungry but dunno what to eat
5. [18:31] User: hmm not sure. went to that italian place last week. marcello's i think?
6. [18:32] User: yea the carbonara was so good. wanna go there again
7. [18:33] User: nah not feeling veggie tonight. oh wait i had bad experience at spice palace last month
8. [18:35] User: cool lets do that. making reservation now"""
    
    print("\nTest 1: Extracting knowledge graph...")
    print("  This uses the TMR-specific OpenRouter API key")
    print("  Model: google/gemini-2.0-flash-lite-001")
    
    extractor = GeminiExtractor(api_key=api_key)
    graph = extractor.extract_graph(conversation, "memory/raw/2026-03-10.md")
    
    if not graph:
        print("  ❌ Extraction failed")
        return False
    
    print(f"  ✅ Extraction successful")
    print(f"\n  Cost: {graph.get('extraction_cost', {})}")
    print(f"  Entities found: {len(graph.get('entities', []))}")
    print(f"  Relationships found: {len(graph.get('relationships', []))}")
    
    # Display entities
    print(f"\n  Entities:")
    for entity in graph.get("entities", [])[:10]:
        print(f"    - {entity}")
    
    # Display relationships
    print(f"\n  Relationships (top 5):")
    for i, rel in enumerate(graph.get("relationships", [])[:5], 1):
        print(f"    {i}. {rel['subject']} --[{rel['relation']}: {rel['strength']}]--> {rel['object']}")
        print(f"       Evidence: \"{rel['evidence'][:50]}...\"" if len(rel['evidence']) > 50 else f"       Evidence: \"{rel['evidence']}\"")
        print(f"       Lines: {rel['source']['line_start']}-{rel['source']['line_end']}")
    
    # Validate key entities found
    print("\nTest 2: Validating key entities...")
    entities = [e.lower() for e in graph.get("entities", [])]
    
    checks = [
        ("User" in entities or "user" in entities, "Found User"),
        ("marcello" in str(entities), "Found Marcello's"),
        ("spice palace" in str(entities), "Found Spice Palace"),
        ("carbonara" in str(entities), "Found carbonara"),
    ]
    
    all_passed = True
    for passed, desc in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False
    
    # Validate relationships
    print("\nTest 3: Validating relationships...")
    rels = graph.get("relationships", [])
    
    has_likes = any(r.get("relation") == "LIKES" for r in rels)  # LIKES anything (carbonara)
    has_dislikes = any(r.get("relation") in ["DISLIKES", "EXPERIENCED"] for r in rels)  # negative experience
    
    print(f"  {'✅' if has_likes else '❌'} Found LIKES relationship")
    print(f"  {'✅' if has_dislikes else '❌'} Found DISLIKES/AVOID relationship")
    
    if not has_likes or not has_dislikes:
        all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("RESULTS: All extraction tests passed ✅")
        print(f"Cost tracked under TMR API key")
    else:
        print("RESULTS: Some tests failed ❌")
    print("="*60)
    
    return all_passed


if __name__ == "__main__":
    success = test_extractor()
    exit(0 if success else 1)
