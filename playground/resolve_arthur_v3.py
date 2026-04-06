#!/usr/bin/env python3
import pexpect
import sys

print("Running resolution for Arthur (2011)...")
print("Will answer 'no' to cache update, then choose option 4 and Apply\n")

child = pexpect.spawn('my-plex', ['-D', '--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=240)
child.logfile = sys.stdout

try:
    # First, handle the cache update prompt
    child.expect("Update cache now\\? \\(yes/no\\):", timeout=60)
    print("\n[Sending: no]")
    child.send('no\n')

    # Wait for the first "Your choice:" prompt for Arthur
    child.expect("Your choice:", timeout=180)

    # Send '4' to trash file [2]
    print("\n[Sending: 4]")
    child.send('4')

    # Wait for next prompt
    child.expect("Your choice:", timeout=30)

    # Send 'A' to apply
    print("\n[Sending: A]")
    child.send('A')

    # Wait for completion
    child.expect(pexpect.EOF, timeout=120)

    print("\n[Process completed]")
    sys.exit(child.exitstatus if child.exitstatus is not None else 0)

except pexpect.TIMEOUT as e:
    print(f"\n[TIMEOUT] {e}")
    print(f"Last output: {child.before[-500:]}")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] {e}")
    sys.exit(1)
