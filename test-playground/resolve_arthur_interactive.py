#!/usr/bin/env python3
"""
Script to automatically resolve Arthur (2011) duplicate by sending keystrokes
"""
import pexpect
import sys
import time

print("Starting interactive resolution for Arthur (2011)...")
print("Will choose option 4 (trash file [2]) and then Apply")
print()

# Spawn the my-plex process
child = pexpect.spawn('my-plex', ['-D', '--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=180)

# Log all output to stdout so we can see what's happening
child.logfile = sys.stdout

try:
    # Wait for the prompt "Your choice:"
    print("\n[DEBUG] Waiting for first 'Your choice:' prompt...")
    child.expect("Your choice:", timeout=120)

    # Send '4' to trash file [2]
    print("\n[DEBUG] Sending '4' to trash file [2]...")
    time.sleep(0.5)
    child.send('4')

    # Wait for the prompt again (after our choice)
    print("\n[DEBUG] Waiting for next 'Your choice:' prompt...")
    child.expect("Your choice:", timeout=30)

    # Send 'A' to apply
    print("\n[DEBUG] Sending 'A' to apply...")
    time.sleep(0.5)
    child.send('A')

    # Wait for completion
    print("\n[DEBUG] Waiting for process to complete...")
    child.expect(pexpect.EOF, timeout=60)

    print("\n[DEBUG] Process completed!")
    print("Exit code:", child.exitstatus)

except pexpect.TIMEOUT:
    print("\n[ERROR] Timeout waiting for expected output")
    print("Last output:")
    print(child.before)
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Exception: {e}")
    print("Last output:")
    print(child.before if hasattr(child, 'before') else "No output available")
    sys.exit(1)

sys.exit(child.exitstatus if child.exitstatus is not None else 0)
