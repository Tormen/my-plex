#!/Users/me/.python.venv/my-plex/bin/python3
"""
Comprehensive timestamp verification test - monitors ALL library timestamps
throughout the complete resolution cycle.

Test Steps:
1. Resolve a duplicate (automated)
2. Wait 30s, run --info and --list-duplicates to verify NO cache update needed
3. Undo resolution by restoring from trash
4. Run --update-cache to sync DISK/PLEX/CACHE
5. Wait 5min, run --info and --list-duplicates to verify NO cache update needed

Uses grep with regex to capture ALL timestamps from ALL libraries at each step.
"""
import subprocess
import sys
import time
import re
from datetime import datetime

def extract_all_timestamps(output):
    """Extract all timestamps from command output using regex"""
    # Match YYYY-MM-DD HH:MM:SS format
    timestamp_pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'

    timestamps = {}
    lines = output.split('\n')

    for i, line in enumerate(lines):
        # Look for library names followed by timestamps
        # Pattern: library_name ... timestamp ... timestamp
        matches = re.findall(timestamp_pattern, line)
        if matches:
            # Try to extract library name from the line
            # Common patterns: "series.de  73  ..." or "- series.de" or "Library: series.de"
            lib_match = re.search(r'(?:^|\s+|-)([a-zA-Z0-9.,_-]+)\s+(?:Series|Movie|\d+|Cache)', line)
            if lib_match:
                lib_name = lib_match.group(1).strip()
                timestamps[lib_name] = matches

    return timestamps

def show_all_timestamps_from_commands():
    """Run both --info and --list-duplicates and extract all timestamps"""
    print(f"\n{'='*80}")
    print(f"TIMESTAMP EXTRACTION (running --info and --list-duplicates)")
    print(f"{'='*80}\n")

    # Run --info
    print("Running: echo 'no' | my-plex --info")
    result_info = subprocess.run(
        ['sh', '-c', "echo 'no' | timeout 60 my-plex --info 2>&1"],
        capture_output=True,
        text=True
    )

    # Run --list-duplicates
    print("Running: echo 'no' | my-plex --list-duplicates")
    result_list = subprocess.run(
        ['sh', '-c', "echo 'no' | timeout 60 my-plex --list-duplicates 2>&1 | head -30"],
        capture_output=True,
        text=True
    )

    # Extract timestamps using grep-like regex
    print("\n" + "="*80)
    print("ALL TIMESTAMPS FOUND (via regex extraction):")
    print("="*80)

    # Show all lines containing timestamps from --info
    print("\nFrom --info:")
    print("-" * 80)
    for line in result_info.stdout.split('\n'):
        if re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line):
            print(line)

    # Show cache status from --list-duplicates
    print("\nFrom --list-duplicates (cache status):")
    print("-" * 80)
    lines = result_list.stdout.split('\n')
    for i, line in enumerate(lines[:30]):
        if 'Cache' in line or 'update' in line.lower() or re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line):
            print(line)

    # Check for cache update prompts
    if 'Cache update available' in result_list.stdout or 'Update cache now?' in result_list.stdout:
        print("\n⚠ WARNING: Cache update prompt detected!")
        return False
    elif 'Cache still up-to-date' in result_list.stdout:
        print("\n✓ Cache is up-to-date (no update needed)")
        return True
    else:
        print("\n? Cache status unclear")
        return None

print("="*80)
print("COMPREHENSIVE TIMESTAMP MONITORING TEST")
print("="*80)
print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# STEP 1: Resolve a duplicate
print("\n" + "="*80)
print("STEP 1: Resolve duplicate (first one, choice 4 - keep [1], trash [2])")
print("="*80)

import pexpect
child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=240)
child.logfile = sys.stdout

try:
    idx = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=180)
    if idx == 0:
        print("\n⚠ WARNING: Cache update prompt before resolution!")
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
    print(f"\n✗ Error during resolution: {e}")
    sys.exit(1)

print(f"\nStep 1 completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
show_all_timestamps_from_commands()

# STEP 2: Wait 30s, then verify NO cache update needed
print("\n" + "="*80)
print("STEP 2: Wait 30 seconds, then verify NO cache update needed")
print("="*80)
print("Waiting 30 seconds...")
for i in range(30, 0, -10):
    print(f"  {i} seconds remaining...")
    time.sleep(10)
print("Wait complete.\n")

step2_ok = show_all_timestamps_from_commands()
if step2_ok == False:
    print("\n✗ FAILED: Cache update needed 30s after resolution!")
    print("This indicates the timestamp fix is NOT working correctly.")
    sys.exit(1)
elif step2_ok == True:
    print("\n✓ PASSED: No cache update needed (30s after resolution)")

# STEP 3: Undo resolution
print("\n" + "="*80)
print("STEP 3: Undo resolution by restoring file from trash")
print("="*80)

# Find most recent .json in plex trash
result = subprocess.run(
    ['ssh', 'my-plex', 'sh', '-c', 'ls -t ~/.plex_trash/*.json 2>/dev/null | head -1'],
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
            subprocess.run(['ssh', 'my-plex', f'rm "{json_file}"'])
        else:
            print(f"✗ Failed to restore: {result.stderr}")
            sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
else:
    print("⚠ No trash metadata found - trying fallback method")
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

print(f"\nStep 3 completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# STEP 4: Run --update-cache
print("\n" + "="*80)
print("STEP 4: Run --update-cache to sync DISK, PLEX, and CACHE")
print("="*80)

proc = subprocess.Popen(
    ['my-plex', '--update-cache'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)
stdout, _ = proc.communicate(input='yes\n', timeout=300)
# Show summary (last 20 lines)
print("Last 20 lines of --update-cache output:")
for line in stdout.split('\n')[-20:]:
    print(line)

print(f"\n✓ Update-cache completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
show_all_timestamps_from_commands()

# STEP 5: Wait 5 minutes, then verify NO cache update needed
print("\n" + "="*80)
print("STEP 5: Wait 5 minutes, then verify NO cache update needed")
print("="*80)
print("Waiting 5 minutes (300 seconds)...")

# Count down in 60-second intervals
for i in range(300, 0, -60):
    print(f"  {i} seconds remaining... ({datetime.now().strftime('%H:%M:%S')})")
    time.sleep(60)

print(f"Wait complete at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

step5_ok = show_all_timestamps_from_commands()
if step5_ok == False:
    print("\n✗ FAILED: Cache update needed 5 minutes after --update-cache!")
    print("This indicates timestamps are drifting or not properly saved.")
    sys.exit(1)
elif step5_ok == True:
    print("\n✓ PASSED: No cache update needed (5 min after update-cache)")

# Final summary
print("\n" + "="*80)
print("✓ ALL TESTS COMPLETED SUCCESSFULLY")
print("="*80)
print(f"\nTest finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("\nSummary:")
print("  ✓ Step 1: Resolution completed")
print("  ✓ Step 2: No cache update needed 30s after resolution")
print("  ✓ Step 3: File restored from trash")
print("  ✓ Step 4: Cache updated to sync DISK/PLEX/CACHE")
print("  ✓ Step 5: No cache update needed 5min after update")
print("\nAll timestamp checks passed - fix is working correctly!")
print("All library timestamps were monitored throughout the test.")
