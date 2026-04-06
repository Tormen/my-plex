#!/bin/bash
"""
Deploy metadata collection script to Plex server

Usage:
    ./deploy_metadata_collector.sh

This script:
1. Copies collect_video_metadata.py to Plex server
2. Makes it executable
3. Verifies deployment
"""

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTOR_SCRIPT="$SCRIPT_DIR/collect_video_metadata.py"
REMOTE_HOST="home"
REMOTE_PATH="/tmp/collect_video_metadata.py"

echo "========================================"
echo "Deploying metadata collector to server"
echo "========================================"

# Check if collector script exists locally
if [ ! -f "$COLLECTOR_SCRIPT" ]; then
    echo "✗ Error: $COLLECTOR_SCRIPT not found"
    exit 1
fi

echo "1. Copying script to $REMOTE_HOST:$REMOTE_PATH..."
scp "$COLLECTOR_SCRIPT" "$REMOTE_HOST:$REMOTE_PATH"

if [ $? -ne 0 ]; then
    echo "✗ Error: Failed to copy script"
    exit 1
fi

echo "2. Making script executable..."
ssh "$REMOTE_HOST" "chmod +x $REMOTE_PATH"

if [ $? -ne 0 ]; then
    echo "✗ Error: Failed to make script executable"
    exit 1
fi

echo "3. Verifying deployment..."
ssh "$REMOTE_HOST" "python3 $REMOTE_PATH --help" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✓ Deployment successful"
    echo ""
    echo "Script deployed to: $REMOTE_HOST:$REMOTE_PATH"
    echo ""
    echo "Next steps:"
    echo "  1. Generate file list with: my-plex --generate-metadata-filelist"
    echo "  2. Copy file list to server"
    echo "  3. Run collector on server"
    echo "  4. Copy results back and integrate into cache"
else
    echo "✗ Error: Script verification failed"
    exit 1
fi
