#!/usr/bin/env python3
"""
TMR v2 - OpenClaw Main Session Integration Example

Shows how to integrate TMR memory injection with OpenClaw's main session
so that memories appear above user messages (like Mem0).

To use in OpenClaw:
1. Import this module in your main session handler
2. Call process_incoming_message() for each user message
3. Prepend the returned context to the LLM prompt
"""

import sys
from pathlib import Path

# Add TMR to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tmr_session_integration import TMRSessionIntegration, process_message_with_tmr
from message_buffer import buffer_message


class OpenClawTMRBridge:
    """
    Bridge between OpenClaw main session and TMR.
    
    This class handles:
    1. Buffering user messages
    2. Retrieving relevant memories
    3. Formatting for display above messages
    4. Buffering assistant responses
    5. Logging everything to tmr_detailed.log
    """
    
    def __init__(self):
        """Initialize the bridge"""
        self.tmr = TMRSessionIntegration()
        self.session_id = None  # Set this if you have session tracking
        
        print("[TMR Bridge] Initialized")
        print(f"[TMR Bridge] Log file: {self.tmr.logger.log_file}")
    
    def on_user_message(self, username: str, message: str) -> dict:
        """
        Call this when a user sends a message.
        
        Args:
            username: Who sent the message (e.g., "Uddipta")
            message: The message content
            
        Returns:
            Dict with:
            - 'context': Raw context for LLM
            - 'display': Formatted for display above message
            - 'memories_count': Number of memories found
            - 'intent': Detected intent
            - 'confidence': Intent confidence
        """
        # Step 1: Buffer the message for later extraction
        buffer_message(username, message)
        
        # Step 2: Retrieve relevant memories
        context = self.tmr.process_user_message(username, message, self.session_id)
        
        # Step 3: Format for display
        display = self.tmr.format_for_display(context) if context else ""
        
        # Step 4: Get intent info
        intent, confidence = self.tmr.injector.intent_classifier.classify(message)
        
        # Count memories
        memories_count = context.count('→') if context else 0
        
        return {
            'context': context,
            'display': display,
            'memories_count': memories_count,
            'intent': intent,
            'confidence': confidence,
            'logged': True
        }
    
    def on_assistant_response(self, response: str):
        """
        Call this when the assistant responds.
        
        Args:
            response: Assistant's response text
        """
        # Buffer the response
        buffer_message("Liz", response)
        
        # Log to TMR
        self.tmr.logger.logger.info("=" * 80)
        self.tmr.logger.logger.info("ASSISTANT RESPONSE")
        self.tmr.logger.logger.info("=" * 80)
        self.tmr.logger.logger.info(f"Response: {response[:200]}{'...' if len(response) > 200 else ''}")
        self.tmr.logger.logger.info("=" * 80)
    
    def build_llm_prompt(self, username: str, message: str, 
                        include_memories: bool = True) -> str:
        """
        Build the complete prompt for the LLM including memories.
        
        Args:
            username: User's name
            message: User's message
            include_memories: Whether to include TMR memories
            
        Returns:
            Complete prompt string
        """
        if not include_memories:
            return f"{username}: {message}"
        
        # Get memories
        result = self.on_user_message(username, message)
        context = result['context']
        
        # Build prompt
        if context:
            prompt = f"""{context}

{username}: {message}

Liz:"""
        else:
            prompt = f"{username}: {message}\n\nLiz:"
        
        return prompt
    
    def show_memories_above_message(self, username: str, message: str) -> str:
        """
        Returns formatted memories to display above the user message
        in the chat interface (like Mem0).
        
        Returns:
            Formatted string with memories, or empty string if none
        """
        result = self.on_user_message(username, message)
        return result['display']


def demo_main_session():
    """
    Demonstrates how TMR works in a main session context.
    """
    print("=" * 80)
    print("TMR v2 - Main Session Integration Demo")
    print("=" * 80)
    print()
    print("This shows how memories appear above user messages (like Mem0)")
    print()
    
    # Create bridge
    bridge = OpenClawTMRBridge()
    
    # Simulate conversation
    conversation = [
        ("Uddipta", "How are you Liz?"),
        ("Liz", "I'm doing great! Working on memory improvements."),
        ("Uddipta", "What did we discuss about TMR yesterday?"),
    ]
    
    for speaker, text in conversation:
        if speaker == "Uddipta":
            print(f"\n{'=' * 80}")
            print(f"[USER MESSAGE]")
            print(f"{'=' * 80}")
            
            # Show memories above message (like Mem0)
            memories = bridge.show_memories_above_message(speaker, text)
            if memories:
                print(memories)
            else:
                print("(No relevant memories found)")
            
            # Show the actual message
            print(f"\n{speaker}: {text}")
            
            # Show what gets sent to LLM
            prompt = bridge.build_llm_prompt(speaker, text)
            print(f"\n{'─' * 80}")
            print("[PROMPT SENT TO LLM]")
            print(f"{'─' * 80}")
            print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
            
        else:
            print(f"\n{speaker}: {text}")
            bridge.on_assistant_response(text)
    
    print("\n" + "=" * 80)
    print("Demo complete!")
    print(f"Check detailed logs at: {bridge.tmr.logger.log_file}")
    print("=" * 80)


# Example of how to integrate with actual OpenClaw main session
EXAMPLE_INTEGRATION_CODE = '''
# In your OpenClaw main session handler:

from tmr_session_integration import get_tmr_integration

# Initialize once
tmr = get_tmr_integration()

def handle_incoming_message(user_message, username="Uddipta"):
    """Handle incoming user message with TMR"""
    
    # Step 1: Get memories
    context = tmr.process_user_message(username, user_message)
    
    # Step 2: Build prompt with memories
    if context:
        full_prompt = f"{context}\\n\\n{username}: {user_message}\\n\\nLiz:"
    else:
        full_prompt = f"{username}: {user_message}\\n\\nLiz:"
    
    # Step 3: Send to LLM
    response = llm.generate(full_prompt)
    
    # Step 4: Buffer response
    from message_buffer import buffer_message
    buffer_message("Liz", response)
    
    return response

# For UI display (show memories above message):
def get_memory_display(username, message):
    """Get formatted memories to show above message"""
    context = tmr.process_user_message(username, message)
    if context:
        return tmr.format_for_display(context)
    return ""
'''


if __name__ == "__main__":
    # Run demo
    demo_main_session()
    
    print("\n\n" + "=" * 80)
    print("EXAMPLE INTEGRATION CODE:")
    print("=" * 80)
    print(EXAMPLE_INTEGRATION_CODE)
