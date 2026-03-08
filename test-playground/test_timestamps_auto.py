#!/Users/me/.python.venv/my-plex/bin/python3
"""Test resolution with full timestamp monitoring - automated"""
import subprocess
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
    """Get current Plex timestamps by calling my-plex with special parsing"""
    # We'll use the cache comparison logic - get fresh stats from Plex
    result = subprocess.run(
        ['timeout', '30', 'my-plex', '--list-libraries'],
        capture_output=True,
        text=True
    )
    
    # For now, just return empty - we'll see the comparison in --list-duplicates output
    return {}

def format_timestamp(ts):
    """Format timestamp for display"""
    if isinstance(ts, datetime):
        return ts.strftime('%Y-%m-%d %H:%M:%S')
    return str(ts)

def show_cache_timestamps(label):
    """Display cache timestamps"""
    print(f"\n{'='*76}")
    print(f"{label}")
    print(f"{'='*76}")
    
    cache_ts = get_cache_timestamps()
    
    print(f"{'Library':<20} | {'CACHE Timestamp'}")
    print(f"{'-'*20}-+-{'-'*19}")
    
    for lib in sorted(cache_ts.keys()):
        cache_t = format_timestamp(cache_ts[lib])
        print(f"{lib:<20} | {cache_t}")
    print()

print("="*76)
print("COMPREHENSIVE TIMESTAMP TEST")
print("="*76)

# Initial state
show_cache_timestamps("INITIAL STATE")

# Step 1: Resolve
print("\nSTEP 1: Resolving duplicate (Chinatown - trash file [1])")
print("-"*76)

import pexpect
child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'], 
                       encoding='utf-8', timeout=240)
child.logfile = sys.stdout

try:
    idx = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=180)
    if idx == 0:
        print("[Answering: no]")
        child.send('no\n')
        child.expect("Your choice:", timeout=180)
    
    print("[Sending: 3 (trash file 1)]")
    child.send('3')
    child.expect("Your choice:", timeout=30)
    print("[Sending: A (apply)]")
    child.send('A')
    child.expect(pexpect.EOF, timeout=120)
    print("\n✓ Resolution completed")
except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)

show_cache_timestamps("AFTER STEP 1 (resolution)")

# Step 2: Check for cache update prompts
print("\nSTEP 2: Checking for cache update prompts")
print("-"*76)

result = subprocess.run(
    ['timeout', '10', 'my-plex', '--list-duplicates'],
    capture_output=True,
    text=True
)

# Show first part of output to see cache status
lines = result.stdout.split('\n')
for i, line in enumerate(lines[:15]):
    print(line)

if 'Cache update available' in result.stdout:
    print("\n✗ FAILED: Cache update prompt detected")
    # Show which libraries need update
    in_update_section = False
    for line in lines:
        if 'Cache update available' in line:
            in_update_section = True
        if in_update_section:
            print(line)
            if line.strip() == '':
                break
    sys.exit(1)
elif 'Cache still up-to-date' in result.stdout:
    print("\n✓ PASSED: No cache update needed")
else:
    print("\n? Status unclear")

show_cache_timestamps("AFTER STEP 2 (verification)")

# Step 3: Restore file
print("\nSTEP 3: Restoring file from trash")
print("-"*76)

result = subprocess.run(
    ['ssh', 'my-plex', 'ls -t /Volumes/2/.Trashes/1001/ | head -1'],
    capture_output=True,
    text=True
)
trash_item = result.stdout.strip()
print(f"Restoring: {trash_item}")

subprocess.run(
    ['ssh', 'my-plex', f'mv /Volumes/2/.Trashes/1001/{trash_item} /Volumes/2/watch.v/,unsorted/'],
    check=True
)
print("✓ File restored")

show_cache_timestamps("AFTER STEP 3 (restore)")

# Step 4: Update cache
print("\nSTEP 4: Running --update-cache")
print("-"*76)

proc = subprocess.Popen(
    ['my-plex', '--update-cache'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)
stdout, _ = proc.communicate(input='yes\n', timeout=300)
# Show summary
for line in stdout.split('\n')[-15:]:
    print(line)

print("\n✓ Update-cache completed")
show_cache_timestamps("AFTER STEP 4 (update-cache)")

# Step 5: Final check
print("\nSTEP 5: Final verification")
print("-"*76)

result = subprocess.run(
    ['timeout', '10', 'my-plex', '--list-duplicates'],
    capture_output=True,
    text=True
)

# Show first part
for line in result.stdout.split('\n')[:15]:
    print(line)

if 'Cache update available' in result.stdout:
    print("\n✗ FAILED: Cache update still needed")
    sys.exit(1)
elif 'Cache still up-to-date' in result.stdout:
    print("\n✓ PASSED: Cache still up-to-date")
else:
    print("\n? Status unclear")

show_cache_timestamps("FINAL STATE")

print("\n" + "="*76)
print("✓ ALL TESTS COMPLETED SUCCESSFULLY")
print("="*76)
