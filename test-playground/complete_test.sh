#!/bin/bash

# Step 3: Restore the trashed file
echo "STEP 3: Restoring trashed file"
echo "------------------------------------------------------------------------"
TRASH_ITEM=$(ssh my-plex "ls -t /Volumes/2/.Trashes/1001/ | head -1")
echo "Found: $TRASH_ITEM"
ssh my-plex "mv /Volumes/2/.Trashes/1001/$TRASH_ITEM /Volumes/2/watch.v/,unsorted/"
echo "✓ Restored"
echo ""

# Step 4: Update cache
echo "STEP 4: Running --update-cache"
echo "------------------------------------------------------------------------"
echo "yes" | timeout 300 my-plex --update-cache 2>&1 | tail -30
echo "✓ Done"
echo ""

# Step 5: Final verification
echo "STEP 5: Final verification - checking for cache update prompts"
echo "------------------------------------------------------------------------"
timeout 10 my-plex --list-duplicates 2>&1 | head -30
