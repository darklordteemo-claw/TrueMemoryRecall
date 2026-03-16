#!/usr/bin/env python3
"""
TMR Gateway Restart Helper
Call this to trigger a delayed restart
"""

import subprocess
import sys
from pathlib import Path

def restart_gateway():
    """Trigger async gateway restart"""
    script = Path(__file__).parent / "restart-gateway.sh"
    
    # Run restart script in background
    subprocess.Popen(
        ["bash", str(script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    
    return True

if __name__ == "__main__":
    # Require --confirm flag to actually run
    if "--confirm" not in sys.argv:
        print("Usage: python3 trigger_restart.py --confirm")
        print("This will restart the gateway after a 2-second delay.")
        print("Only run this when you're done with your current response!")
        sys.exit(0)
    
    restart_gateway()
    print("✅ Gateway restart scheduled")
    print("   Timeline:")
    print("   - T+0s: Your current response completes")
    print("   - T+2s: Gateway restart begins")
    print("   - T+5s: Gateway back online")
    print("   - T+6s: Marker file created, plugin reloads")
    print("   - You will see [TMR-RESTART-MARKER] in next response")
