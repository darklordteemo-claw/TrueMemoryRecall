#!/usr/bin/env python3
"""
TMR v2 Integration Example

Shows how to integrate message buffering with the unified injector
for near real-time memory retrieval.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from message_buffer import buffer_message, flush_buffer
from tmr_injector import TMRCogneeInjector
from config_loader import get_config


def process_user_message(user_message: str, user_name: str = "Uddipta") -> str:
    """
    Process a user message through TMR v2 pipeline:
    1. Buffer the message
    2. Retrieve relevant memories
    3. Return context for LLM
    
    This is called when user sends a message.
    """
    # Step 1: Buffer the user message
    buffer_message(user_name, user_message)
    
    # Step 2: Retrieve relevant memories based on query
    injector = TMRCogneeInjector()
    context = injector.inject_context(user_message)
    
    return context


def process_assistant_response(assistant_message: str, user_message: str) -> str:
    """
    Process assistant response:
    1. Buffer the response
    2. Optionally: Check if user is correcting/clarifying
    3. Return feedback signal if detected
    
    This is called after assistant responds.
    """
    # Step 1: Buffer the assistant message
    buffer_message("Liz", assistant_message)
    
    # Step 2: Detect implicit feedback
    # (In real implementation, would compare with conversation history)
    # For now, just return the message for storage
    
    return assistant_message


def main():
    """Demonstrate the full flow"""
    print("=" * 70)
    print("TMR v2 Integration Example")
    print("=" * 70)
    
    # Simulate conversation
    conversation = [
        ("Uddipta", "How are you Liz?"),
        ("Liz", "I'm doing great! Working on making my memory even better."),
        ("Uddipta", "What did we discuss about TMR yesterday?"),
        ("Liz", "We talked about implementing the Cognee-style feedback loop."),
        ("Uddipta", "Actually, I think we discussed the query planner first."),
    ]
    
    injector = TMRCogneeInjector(enable_feedback=False)
    
    for sender, message in conversation:
        print(f"\n[{sender}]: {message}")
        print("-" * 70)
        
        if sender == "Uddipta":
            # User message - retrieve context
            context = injector.inject_context(message)
            if context:
                print("[TMR Retrieved Context]:")
                print(context[:500] + "..." if len(context) > 500 else context)
            else:
                print("[TMR] No relevant memories found")
            
            # Buffer the message
            buffer_message(sender, message)
            
        else:
            # Assistant response - just buffer
            buffer_message(sender, message)
            print("[TMR] Response buffered")
    
    # Show buffer stats
    from message_buffer import get_message_buffer
    buffer = get_message_buffer()
    stats = buffer.get_stats()
    
    print(f"\n{'=' * 70}")
    print("Buffer Statistics:")
    print(f"  Current file: {stats['current_file']}")
    print(f"  Sequence: {stats['sequence']}")
    print(f"  Utilization: {stats['utilization']:.1%}")
    print(f"  Time since flush: {stats['time_since_flush_hours']:.1f} hours")
    
    print("\n" + "=" * 70)
    print("In production:")
    print("  - Messages buffer until ~70% full OR 2 hours pass")
    print("  - Cron job extracts every 2 hours")
    print("  - New memories available in ~2 hours max (vs 24 hours before)")
    print("=" * 70)


if __name__ == "__main__":
    main()
