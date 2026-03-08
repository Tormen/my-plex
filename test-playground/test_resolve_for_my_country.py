#!/Users/me/.python.venv/my-plex/bin/python3
"""
Test script to resolve "For My Country (2023)" duplicate
Chooses option 4 (trash [2]) and applies the changes
"""
import sys
import pexpect
from datetime import datetime

print("="*80)
print("TESTING DUPLICATE RESOLUTION FOR 'FOR MY COUNTRY (2023)'")
print("="*80)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Spawn the resolution process
print("Spawning: my-plex --list-duplicates --resolve")
child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=300)
child.logfile = sys.stdout

try:
    # Wait for the first duplicate prompt (For My Country)
    print("\n[Waiting for 'Your choice:' prompt...]")
    idx = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=180)

    if idx == 0:
        print("\n⚠ Cache update prompt detected - answering 'no'")
        child.send('no\n')
        child.expect("Your choice:", timeout=180)

    # Send choice 4 (trash file [2])
    print("\n[Sending choice: 4 (trash file [2])]")
    child.send('4')

    # Wait for next prompt
    child.expect("Your choice:", timeout=30)

    # Send 'A' to apply
    print("[Sending: A (apply changes)]")
    child.send('A')

    # Wait for completion message
    print("\n[Waiting for RESOLUTION MODE COMPLETE...]")
    child.expect("RESOLUTION MODE COMPLETE", timeout=120)

    # Wait a bit more for final output
    child.expect(pexpect.EOF, timeout=10)

    print("\n" + "="*80)
    print("✓ RESOLUTION COMPLETED SUCCESSFULLY")
    print("="*80)

except pexpect.TIMEOUT as e:
    print(f"\n✗ TIMEOUT: {e}")
    print(f"Buffer before timeout:\n{child.before}")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\nFinished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
