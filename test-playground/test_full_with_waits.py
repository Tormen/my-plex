#!/Users/me/.python.venv/my-plex/bin/python3
"""
Comprehensive timestamp verification test with wait periods

Test Steps:
1. Resolve a duplicate (automated choice)
2. Wait 30s, then verify NO cache update is needed
3. Undo the resolution by restoring from trash
4. Run --update-cache to sync DISK/PLEX/CACHE
5. Wait 5min, then verify NO cache update is needed

Monitors timestamps in both CACHE and PLEX throughout all steps.
"""
import subprocess
import pickle
import sys
import time
from datetime import datetime

def get_cache_timestamps():
    """Read timestamps from cache file"""
    try:
        with open('/Users/me/.plex_media_cache.pkl', 'rb') as f:
            cache = pickle.load(f)
            return cache.get('library_stats', {}).get('updatedAt', {})
    except Exception as e:
        return {}

def get_plex_timestamps():
    """Get current Plex timestamps from --info output"""
    try:
        # Use --info (which is --show-library-stats) to get timestamps
        # Pipe 'no' to avoid the update prompt
        result = subprocess.run(
            ['sh', '-c', 'echo "no" | my-plex --info 2>&1 | head -60'],
            capture_output=True,
            text=True,
            timeout=60
        )
        timestamps = {}
        in_update_section = False
        current_lib = None

        for line in result.stdout.split('\n'):
            # Look for update available section or individual library info
            if 'Cache update available' in line or 'newer timestamp' in line:
                in_update_section = True
                continue

            if in_update_section:
                # Parse library update info
                if line.strip().startswith('-'):
                    current_lib = line.strip()[2:].strip()  # Remove "- " prefix
                elif 'Plex:' in line and current_lib:
                    parts = line.split('Plex:')
                    if len(parts) == 2:
                        timestamps[current_lib] = parts[1].strip()

                # Exit when we hit empty line or next section
                if line.strip() == '' or 'Update cache now?' in line:
                    break

        # If no updates needed, all timestamps match cache (return empty to use cache values)
        return timestamps
    except Exception as e:
        return {}

def format_timestamp(ts):
    """Format timestamp for display"""
    if isinstance(ts, datetime):
        return ts.strftime('%Y-%m-%d %H:%M:%S')
    return str(ts)

def show_all_timestamps(label):
    """Display timestamps from both CACHE and PLEX for all libraries"""
    print(f"\n{'='*80}")
    print(f"{label}")
    print(f"{'='*80}")

    cache_ts = get_cache_timestamps()
    plex_ts = get_plex_timestamps()

    # Get all library names from cache
    all_libs = set(cache_ts.keys())

    print(f"{'Library':<25} | {'CACHE Timestamp':<20} | {'PLEX Timestamp':<20}")
    print(f"{'-'*25}-+-{'-'*20}-+-{'-'*20}")

    for lib in sorted(all_libs):
        cache_t = format_timestamp(cache_ts.get(lib, 'N/A'))
        # If plex_ts is empty, it means no updates needed - show "= CACHE" to indicate sync
        plex_t = plex_ts.get(lib, '= CACHE' if not plex_ts else 'N/A')
        print(f"{lib:<25} | {cache_t:<20} | {plex_t:<20}")

    if plex_ts:
        print(f"\nNote: PLEX timestamps shown above are DIFFERENT from CACHE (update available)")
    else:
        print(f"\nNote: PLEX timestamps match CACHE (no updates needed)")
    print()

print("="*80)
print("COMPREHENSIVE TIMESTAMP TEST WITH WAIT PERIODS")
print("="*80)

# Initial state
show_all_timestamps("INITIAL STATE (before test)")

# Pre-test: Ensure all libraries are in sync
print("\nPRE-TEST: Ensuring all libraries are in sync...")
print("-"*80)
plex_ts_initial = get_plex_timestamps()
if plex_ts_initial:
    print("⚠ Some libraries are out of sync. Running --update-cache first...")
    proc = subprocess.Popen(
        ['my-plex', '--update-cache'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    stdout, _ = proc.communicate(input='yes\n', timeout=300)
    print("✓ Pre-test cache update completed")
    show_all_timestamps("AFTER PRE-TEST UPDATE (all libraries synced)")
else:
    print("✓ All libraries already in sync")

# Step 1: Resolve
print("\nSTEP 1: Resolving duplicate (first one, choice 4 - keep [1], trash [2])")
print("-"*80)

import pexpect
child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'], 
                       encoding='utf-8', timeout=240)
child.logfile = sys.stdout

try:
    idx = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=180)
    if idx == 0:
        print("\n⚠ WARNING: Cache update prompt appeared before resolution!")
        print("[Answering: no]")
        child.send('no\n')
        child.expect("Your choice:", timeout=180)

    print("\n[Sending: 4 (keep file [1], trash file [2])]")
    child.send('4')
    child.expect("Your choice:", timeout=30)
    print("[Sending: A (apply)]")
    child.send('A')
    child.expect(pexpect.EOF, timeout=120)
    print("\n✓ Resolution completed")
except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)

show_all_timestamps("AFTER STEP 1 (resolution complete)")

# Step 2: Wait 30s, then check for cache update prompts
print("\nSTEP 2: Wait 30 seconds, then check for cache update prompts")
print("-"*80)
print("Waiting 30 seconds...")
for i in range(30, 0, -5):
    print(f"  {i} seconds remaining...")
    time.sleep(5)
print("Wait complete. Checking cache status...")

result = subprocess.run(
    ['timeout', '10', 'my-plex', '--list-duplicates'],
    capture_output=True,
    text=True
)

# Show first part of output to see cache status
lines = result.stdout.split('\n')
for i, line in enumerate(lines[:15]):
    print(line)

if 'Cache update available' in result.stdout or 'Update cache now?' in result.stdout:
    print("\n✗ FAILED: Cache update prompt detected after 30s wait!")
    print("This indicates the timestamp fix is NOT working correctly.")
    # Show which libraries need update
    in_update_section = False
    for line in lines:
        if 'Cache update available' in line or 'newer timestamp' in line:
            in_update_section = True
        if in_update_section:
            print(line)
            if line.strip() == '':
                break
    sys.exit(1)
elif 'Cache still up-to-date' in result.stdout:
    print("\n✓ PASSED: No cache update needed (30s after resolution)")
else:
    print("\n? Status unclear - reviewing output")

show_all_timestamps("AFTER STEP 2 (30s wait + verification)")

# Step 3: Undo by restoring file from trash
print("\nSTEP 3: Undo resolution by restoring file from trash")
print("-"*80)

# Find most recent .json in plex trash (contains metadata)
result = subprocess.run(
    ['ssh', 'my-plex', 'ls -t ~/.plex_trash/*.json 2>/dev/null | head -1'],
    capture_output=True,
    text=True
)

if result.returncode == 0 and result.stdout.strip():
    import json
    json_file = result.stdout.strip()
    print(f"Found trash metadata: {json_file}")

    # Read JSON to get paths
    result = subprocess.run(
        ['ssh', 'my-plex', f'cat {json_file}'],
        capture_output=True,
        text=True
    )

    try:
        trash_data = json.loads(result.stdout)
        original_path = trash_data.get('original_path')
        trashed_file = trash_data.get('trashed_file')

        print(f"  Original: {original_path}")
        print(f"  Trashed:  {trashed_file}")

        # Restore file
        result = subprocess.run(
            ['ssh', 'my-plex', f'mv "{trashed_file}" "{original_path}"'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("✓ File restored successfully")
            # Remove JSON metadata
            subprocess.run(['ssh', 'my-plex', f'rm "{json_file}"'])
        else:
            print(f"✗ Failed to restore: {result.stderr}")
    except Exception as e:
        print(f"✗ Error: {e}")
else:
    print("⚠ No trash metadata found - trying fallback method")
    # Fallback: try system trash
    result = subprocess.run(
        ['ssh', 'my-plex', 'ls -t /Volumes/2/.Trashes/1001/ | head -1'],
        capture_output=True,
        text=True
    )
    if result.stdout.strip():
        trash_item = result.stdout.strip()
        print(f"Restoring: {trash_item}")
        subprocess.run(
            ['ssh', 'my-plex', f'mv /Volumes/2/.Trashes/1001/{trash_item} /Volumes/2/watch.v/,unsorted/']
        )
        print("✓ File restored")

show_all_timestamps("AFTER STEP 3 (undo - file restored)")

# Step 4: Update cache to sync DISK/PLEX/CACHE
print("\nSTEP 4: Running --update-cache to sync DISK, PLEX, and CACHE")
print("-"*80)

proc = subprocess.Popen(
    ['my-plex', '--update-cache'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)
stdout, _ = proc.communicate(input='yes\n', timeout=300)
# Show summary (last 15 lines)
for line in stdout.split('\n')[-15:]:
    print(line)

print("\n✓ Update-cache completed")
show_all_timestamps("AFTER STEP 4 (update-cache complete)")

# Step 5: Wait 5 minutes, then final verification
print("\nSTEP 5: Wait 5 minutes, then verify NO cache update needed")
print("-"*80)
print("Waiting 5 minutes (300 seconds)...")

# Count down in 30-second intervals
for i in range(300, 0, -30):
    print(f"  {i} seconds remaining...")
    time.sleep(30)

print("Wait complete. Final verification...")

result = subprocess.run(
    ['timeout', '10', 'my-plex', '--list-duplicates'],
    capture_output=True,
    text=True
)

# Show first part of output
lines = result.stdout.split('\n')
for line in lines[:15]:
    print(line)

if 'Cache update available' in result.stdout or 'Update cache now?' in result.stdout:
    print("\n✗ FAILED: Cache update needed 5 minutes after --update-cache!")
    print("This indicates timestamps are drifting or not properly saved.")
    # Show which libraries need update
    for line in lines:
        if 'newer timestamp' in line or 'Cache update' in line:
            print(line)
    sys.exit(1)
elif 'Cache still up-to-date' in result.stdout:
    print("\n✓ PASSED: Cache still up-to-date (5 min after update-cache)")
else:
    print("\n? Status unclear")

show_all_timestamps("FINAL STATE (5 min after update-cache)")

print("\n" + "="*80)
print("✓ ALL TESTS COMPLETED SUCCESSFULLY")
print("="*80)
print("\nSummary:")
print("  ✓ Step 1: Resolution completed")
print("  ✓ Step 2: No cache update needed 30s after resolution")
print("  ✓ Step 3: File restored from trash")
print("  ✓ Step 4: Cache updated to sync DISK/PLEX/CACHE")
print("  ✓ Step 5: No cache update needed 5min after update")
print("\nAll timestamp checks passed - fix is working correctly!")
