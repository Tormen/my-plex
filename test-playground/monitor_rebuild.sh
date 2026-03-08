#!/bin/bash
# Monitor the rebuild and save log when complete

LOG_FILE="/tmp/debug_from_scratch.log"
DEST_FILE="/Users/MINE/data/src/,py/prj/my-plex/update-cache_--force_--from-scratch.log"

# Wait for the process to complete (check every 30 seconds)
while ps aux | grep -q "[m]y-plex.*update-cache.*from-scratch"; do
    sleep 30
done

# Wait a bit more to ensure output is flushed
sleep 5

# Copy the log file
if [ -f "$LOG_FILE" ]; then
    cp "$LOG_FILE" "$DEST_FILE"
    echo "Log saved to: $DEST_FILE"
    ls -lh "$DEST_FILE"
else
    echo "Error: Log file not found at $LOG_FILE"
fi
