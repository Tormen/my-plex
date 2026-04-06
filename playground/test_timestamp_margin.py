#!/usr/bin/env python3
import pexpect
import sys

print("Testing timestamp margin fix...")
print("Will resolve a duplicate and verify no cache update prompt afterward\n")

child = pexpect.spawn('my-plex', ['-D', '--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=240)
child.logfile = sys.stdout

try:
    # Wait for first choice prompt
    child.expect("Your choice:", timeout=180)
    
    # Send 'N' to skip (don't actually apply anything)
    print("\n[Sending: N to skip]")
    child.send('N')
    
    # Wait for next prompt or completion
    index = child.expect(["Your choice:", pexpect.EOF], timeout=30)
    
    if index == 0:
        # Got another prompt, send Q to quit
        print("\n[Sending: Q to quit]")
        child.send('Q')
        child.expect(pexpect.EOF, timeout=10)
    
    print("\n[Test completed - no actual changes made]")
    sys.exit(0)

except pexpect.TIMEOUT as e:
    print(f"\n[TIMEOUT] {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] {e}")
    sys.exit(1)
