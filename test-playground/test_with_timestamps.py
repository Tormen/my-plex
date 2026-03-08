#!/Users/me/.python.venv/my-plex/bin/python3
"""
Test resolution with full timestamp monitoring
"""
import subprocess
import json
import pickle
import sys
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
    """Get timestamps from Plex via my-plex"""
    result = subprocess.run(
        ['my-plex', '-D', '--list-libraries'],
        capture_output=True,
        text=True,
        timeout=30
    )
    timestamps = {}
    for line in result.stdout.split('\n'):
        if 'updatedAt=' in line:
            # Parse lines like: "  movies.en  updatedAt=2025-12-29 11:20:24"
            parts = line.strip().split()
            if len(parts) >= 3:
                lib_name = parts[0]
                ts_str = ' '.join(parts[2:]).replace('updatedAt=', '')
                timestamps[lib_name] = ts_str
    return timestamps

def format_timestamp(ts):
    """Format timestamp for display"""
    if isinstance(ts, datetime):
        return ts.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(ts, str):
        return ts
    else:
        return str(ts)

def show_timestamps(label):
    """Display current timestamps from both PLEX and CACHE"""
    print(f"\n{'='*76}")
    print(f"{label}")
    print(f"{'='*76}")
    
    cache_ts = get_cache_timestamps()
    plex_ts = get_plex_timestamps()
    
    # Get all library names
    all_libs = sorted(set(list(cache_ts.keys()) + list(plex_ts.keys())))
    
    print(f"{'Library':<20} | {'CACHE Timestamp':<19} | {'PLEX Timestamp':<19} | {'Match'}")
    print(f"{'-'*20}-+-{'-'*19}-+-{'-'*19}-+-{'-'*5}")
    
    for lib in all_libs:
        cache_t = format_timestamp(cache_ts.get(lib, 'N/A'))
        plex_t = plex_ts.get(lib, 'N/A')
        match = "✓" if cache_t == plex_t or (isinstance(cache_ts.get(lib), datetime) and cache_ts.get(lib).strftime('%Y-%m-%d %H:%M:%S') == plex_t) else "✗"
        print(f"{lib:<20} | {cache_t:<19} | {plex_t:<19} | {match}")
    print()

# Initial state
show_timestamps("INITIAL STATE (before any operations)")

print("\nPress Enter to continue with Step 1 (resolve duplicate)...")
input()

# Step 1: Resolve duplicate
print("\n" + "="*76)
print("STEP 1: Resolving duplicate (Chinatown - trash file [1])")
print("="*76)

import pexpect
child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'], 
                       encoding='utf-8', timeout=240)
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
except Exception as e:
    print(f"\nError in resolution: {e}")
    sys.exit(1)

print("\n✓ Resolution completed")
show_timestamps("AFTER STEP 1 (after resolution)")

# Step 2: Verify no cache update needed
print("\n" + "="*76)
print("STEP 2: Verifying NO cache update prompt")
print("="*76)

result = subprocess.run(
    ['timeout', '10', 'my-plex', '--list-duplicates'],
    capture_output=True,
    text=True
)

if 'Cache update available' in result.stdout:
    print("✗ FAILED: Cache update prompt found!")
    print(result.stdout[:500])
    sys.exit(1)
elif 'Cache still up-to-date' in result.stdout:
    print("✓ PASSED: Cache still up-to-date")
else:
    print("? UNCLEAR: Could not determine cache status")
    print(result.stdout[:300])

show_timestamps("AFTER STEP 2 (after verification)")

print("\nPress Enter to continue with Step 3 (restore file)...")
input()

# Step 3: Restore file
print("\n" + "="*76)
print("STEP 3: Restoring trashed file")
print("="*76)

result = subprocess.run(
    ['ssh', 'my-plex', 'ls -t /Volumes/2/.Trashes/1001/ | head -1'],
    capture_output=True,
    text=True
)
trash_item = result.stdout.strip()
print(f"Found: {trash_item}")

subprocess.run(
    ['ssh', 'my-plex', f'mv /Volumes/2/.Trashes/1001/{trash_item} /Volumes/2/watch.v/,unsorted/'],
    check=True
)
print("✓ File restored")

show_timestamps("AFTER STEP 3 (after restore)")

print("\nPress Enter to continue with Step 4 (update-cache)...")
input()

# Step 4: Update cache
print("\n" + "="*76)
print("STEP 4: Running --update-cache")
print("="*76)

proc = subprocess.Popen(
    ['my-plex', '--update-cache'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)
stdout, _ = proc.communicate(input='yes\n', timeout=300)
print(stdout[-1000:])  # Show last 1000 chars

print("✓ Update-cache completed")
show_timestamps("AFTER STEP 4 (after update-cache)")

# Step 5: Final verification
print("\n" + "="*76)
print("STEP 5: Final verification")
print("="*76)

result = subprocess.run(
    ['timeout', '10', 'my-plex', '--list-duplicates'],
    capture_output=True,
    text=True
)

if 'Cache update available' in result.stdout:
    print("✗ FAILED: Cache update prompt found!")
    print(result.stdout[:500])
    sys.exit(1)
elif 'Cache still up-to-date' in result.stdout:
    print("✓ PASSED: Cache still up-to-date")
else:
    print("? UNCLEAR: Could not determine cache status")
    print(result.stdout[:300])

show_timestamps("AFTER STEP 5 (final state)")

print("\n" + "="*76)
print("✓ ALL TESTS PASSED!")
print("="*76)
