#!/Users/me/.python.venv/my-plex/bin/python3
"""Test trash operation to debug volume-specific trash issue"""
import sys
import pexpect

print("="*80)
print("TESTING TRASH OPERATION WITH DEBUG OUTPUT")
print("="*80)

# Spawn with -DD for deep debug
child = pexpect.spawn('my-plex', ['-DD', '--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=120)
child.logfile = sys.stdout

try:
    # Wait for first prompt
    idx = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=60)
    if idx == 0:
        child.send('no\n')
        child.expect("Your choice:", timeout=60)

    # Send choice 4 (trash file [2])
    print("\n[Sending: 4]")
    child.send('4')
    child.expect("Your choice:", timeout=30)

    # Send 'A' to apply
    print("[Sending: A]")
    child.send('A')

    # Wait for completion or error
    idx = child.expect(["RESOLUTION MODE COMPLETE", "Failed to move", pexpect.EOF], timeout=60)
    if idx == 1:
        print("\n✗ Trash operation failed")
    elif idx == 0:
        print("\n✓ Trash operation succeeded")

    child.close()

except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)

print("\nTest complete")
