#!/bin/bash
"""
Test the complete metadata collection workflow

This script tests the entire metadata collection and integration process:
1. Generate file list from cache
2. Deploy collector to server
3. Copy file list to server
4. Run collector on server
5. Copy results back
6. Integrate metadata into cache
7. Verify integration

Usage:
    ./test_metadata_workflow.sh [--dry-run]

Options:
    --dry-run    Show commands without executing
"""

set -e

DRY_RUN=false
if [ "$1" == "--dry-run" ]; then
    DRY_RUN=true
    echo "DRY RUN MODE - Commands will be shown but not executed"
    echo ""
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE_HOST="home"

# File paths
LOCAL_FILELIST="/tmp/video_files_for_metadata.txt"
LOCAL_METADATA_JSON="/tmp/video_metadata.json"
REMOTE_FILELIST="/tmp/video_files_for_metadata.txt"
REMOTE_METADATA_JSON="/tmp/video_metadata.json"
REMOTE_COLLECTOR="/tmp/collect_video_metadata.py"

echo "========================================"
echo "METADATA COLLECTION WORKFLOW TEST"
echo "========================================"
echo ""

# Function to run command or show in dry-run
run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY RUN] $@"
    else
        echo "Running: $@"
        "$@"
    fi
}

# Step 1: Generate file list from cache
echo "Step 1: Generate file list from cache using Python"
echo "--------------------------------------"
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] python3 -c 'import pickle; cache=pickle.load(open(\"~/.plex_media_cache.pkl\",\"rb\")); ...'"
else
    echo "Generating file list from cache..."
    python3 << 'EOF'
import pickle
import os

cache_file = os.path.expanduser('~/.plex_media_cache.pkl')
output_file = '/tmp/video_files_for_metadata.txt'

# Load cache
with open(cache_file, 'rb') as f:
    cache = pickle.load(f)

obj_by_id = cache.get('obj_by_id', {})

# Collect all filepaths
filepaths = set()
for obj in obj_by_id.values():
    files_dict = obj.get('files', {})
    for file_info in files_dict.values():
        filepath = file_info.get('filepath')
        if filepath:
            filepaths.add(filepath)

# Write to file
with open(output_file, 'w') as f:
    for filepath in sorted(filepaths):
        f.write(f"{filepath}\n")

print(f"✓ Generated file list: {output_file}")
print(f"  Total files: {len(filepaths):,}")
EOF
fi
echo ""

if [ "$DRY_RUN" = false ] && [ ! -f "$LOCAL_FILELIST" ]; then
    echo "✗ Error: File list was not created"
    exit 1
fi

# Step 2: Deploy collector to server
echo "Step 2: Deploy collector script to server"
echo "--------------------------------------"
run_cmd "$SCRIPT_DIR/deploy_metadata_collector.sh"
echo ""

# Step 3: Copy file list to server
echo "Step 3: Copy file list to server"
echo "--------------------------------------"
run_cmd scp "$LOCAL_FILELIST" "$REMOTE_HOST:$REMOTE_FILELIST"
echo ""

# Step 4: Run collector on server
echo "Step 4: Run metadata collector on server"
echo "--------------------------------------"
echo "This may take several minutes for large libraries..."
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] ssh $REMOTE_HOST 'python3 $REMOTE_COLLECTOR --file-list $REMOTE_FILELIST --output $REMOTE_METADATA_JSON --progress 100'"
else
    echo "Running: ssh $REMOTE_HOST 'python3 $REMOTE_COLLECTOR --file-list $REMOTE_FILELIST --output $REMOTE_METADATA_JSON --progress 100'"
    ssh "$REMOTE_HOST" "python3 $REMOTE_COLLECTOR --file-list $REMOTE_FILELIST --output $REMOTE_METADATA_JSON --progress 100"
fi
echo ""

# Step 5: Copy results back
echo "Step 5: Copy metadata results back from server"
echo "--------------------------------------"
run_cmd scp "$REMOTE_HOST:$REMOTE_METADATA_JSON" "$LOCAL_METADATA_JSON"
echo ""

if [ "$DRY_RUN" = false ] && [ ! -f "$LOCAL_METADATA_JSON" ]; then
    echo "✗ Error: Metadata JSON was not copied back"
    exit 1
fi

# Step 6: Integrate metadata into cache (ONE-TIME)
echo "Step 6: Integrate metadata into cache using one-time script"
echo "--------------------------------------"
run_cmd "$SCRIPT_DIR/one_time_integrate_metadata.py" "$LOCAL_METADATA_JSON"
echo ""

# Step 7: Verify integration
echo "Step 7: Verify integration (check cache info)"
echo "--------------------------------------"
run_cmd my-plex --info
echo ""

echo "========================================"
echo "WORKFLOW TEST COMPLETE"
echo "========================================"
echo ""
echo "Files created:"
echo "  Local file list:   $LOCAL_FILELIST"
echo "  Local metadata:    $LOCAL_METADATA_JSON"
echo "  Remote file list:  $REMOTE_HOST:$REMOTE_FILELIST"
echo "  Remote metadata:   $REMOTE_HOST:$REMOTE_METADATA_JSON"
echo ""
echo "Next steps:"
echo "  - Run 'my-plex --update-cache' to verify incremental metadata collection"
echo "  - Check that existing files with metadata are not re-scanned"
echo "  - Add new files and verify only new files get metadata collected"
