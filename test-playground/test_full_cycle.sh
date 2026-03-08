#!/bin/bash
set -e

echo "============================================================================"
echo "FULL TEST CYCLE: Resolve → Verify No Cache Update → Undo → Update → Verify"
echo "============================================================================"
echo ""

# Step 1: Resolve duplicate (trash file [1] of Changing Lanes)
echo "STEP 1: Resolving duplicate (Changing Lanes - keeping file 2, trashing file 1)"
echo "------------------------------------------------------------------------"
cat > /tmp/resolve_test.py << 'PYEOF'
#!/Users/me/.python.venv/my-plex/bin/python3
import pexpect, sys
child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'], encoding='utf-8', timeout=240)
child.logfile = sys.stdout
try:
    idx = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=180)
    if idx == 0:
        child.send('no\n')
        child.expect("Your choice:", timeout=180)
    child.send('3')  # Trash file [1]
    child.expect("Your choice:", timeout=30)
    child.send('A')  # Apply
    child.expect(pexpect.EOF, timeout=120)
    sys.exit(0)
except Exception as e:
    print(f"\nError: {e}")
    sys.exit(1)
PYEOF
chmod +x /tmp/resolve_test.py
/tmp/resolve_test.py 2>&1 | tee /tmp/step1_resolve.log
echo ""
echo "✓ Step 1 completed"
echo ""

# Step 2: Verify NO cache update needed
echo "STEP 2: Verifying NO cache update prompt for ,unsorted library"
echo "------------------------------------------------------------------------"
timeout 10 my-plex --list-duplicates 2>&1 | tee /tmp/step2_verify.log | head -50
echo ""
if grep -q ",unsorted" /tmp/step2_verify.log; then
    echo "✗ FAILED: ,unsorted library still shows cache update needed!"
    exit 1
else
    echo "✓ Step 2 completed - NO cache update prompt for ,unsorted"
fi
echo ""

# Step 3: Find and restore the trashed file
echo "STEP 3: Restoring trashed file from Plex server trash"
echo "------------------------------------------------------------------------"
# Find the most recent trash item
TRASH_ITEM=$(ssh my-plex "ls -t /Volumes/2/.Trashes/1001/ | head -1")
echo "Found trash item: $TRASH_ITEM"
# Restore it
ssh my-plex "mv /Volumes/2/.Trashes/1001/$TRASH_ITEM /Volumes/2/watch.v/,unsorted/"
echo "✓ Restored to: /Volumes/2/watch.v/,unsorted/$TRASH_ITEM"
echo "✓ Step 3 completed"
echo ""

# Step 4: Update cache to sync DISK, PLEX, CACHE
echo "STEP 4: Running --update-cache to sync DISK, PLEX, and CACHE"
echo "------------------------------------------------------------------------"
echo "yes" | timeout 300 my-plex --update-cache 2>&1 | tee /tmp/step4_update.log | tail -50
echo "✓ Step 4 completed"
echo ""

# Step 5: Verify NO cache update needed after full sync
echo "STEP 5: Final verification - NO cache update should be needed"
echo "------------------------------------------------------------------------"
timeout 10 my-plex --list-duplicates 2>&1 | tee /tmp/step5_final.log | head -50
echo ""
if grep -q "Cache update available" /tmp/step5_final.log; then
    echo "✗ FAILED: Cache update still needed after full sync!"
    exit 1
else
    echo "✓ Step 5 completed - Cache is fully up-to-date"
fi
echo ""

echo "============================================================================"
echo "✓ ALL TESTS PASSED!"
echo "============================================================================"
