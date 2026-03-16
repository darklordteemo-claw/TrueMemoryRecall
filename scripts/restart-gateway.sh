#!/bin/bash
# TMR Gateway Restart Script
# Waits for agent to finish, restarts, confirms, then notifies

# Configuration
WAIT_TIME=2
MAX_WAIT=60
USER="openclaw"

# Step 1: Wait for agent to finish responding
echo "[TMR-Restart] Waiting ${WAIT_TIME}s for agent to complete..."
sleep $WAIT_TIME

# Step 2: Restart the gateway
echo "[TMR-Restart] Restarting OpenClaw gateway..."
systemctl --user restart openclaw-gateway

# Step 3: Wait for gateway to be active
echo "[TMR-Restart] Waiting for gateway to become active..."
for i in $(seq 1 $MAX_WAIT); do
    if systemctl --user is-active openclaw-gateway >/dev/null 2>&1; then
        echo "[TMR-Restart] Gateway is active!"
        break
    fi
    sleep 1
done

# Step 4: Verify TMR loaded
sleep 2
if openclaw gateway status 2>/dev/null | grep -q "true-memory-recall"; then
    echo "[TMR-Restart] TMR plugin loaded successfully"
    STATUS="✅ Gateway restarted, TMR active"
else
    echo "[TMR-Restart] Warning: TMR may not be loaded"
    STATUS="⚠️ Gateway restarted, check TMR status"
fi

# Step 5: Create completion marker
TIMESTAMP=$(date +%s)
echo "$(date '+%H:%M:%S') - $STATUS" >> /tmp/tmr_restart_notifications.log

echo "[TMR-Restart] ✅ COMPLETE: $STATUS"
echo "[TMR-Restart] Send any message to resume the session"
