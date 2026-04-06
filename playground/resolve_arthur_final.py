#!/usr/bin/env python3
import pexpect
import sys

print("=" * 76)
print("TESTING: Resolution with cache corruption fix")
print("=" * 76)
print()
print("Will choose option 4 (trash file [2]) and Apply")
print()

child = pexpect.spawn('my-plex', ['-D', '--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=300)

# Save output to file for analysis
output_file = open('/tmp/resolve_final_output.log', 'w')
child.logfile_read = output_file

try:
    # Wait for the first "Your choice:" prompt
    child.expect("Your choice:", timeout=180)
    print("[Found Arthur duplicate, sending: 4]")
    child.send('4')

    # Wait for next prompt
    child.expect("Your choice:", timeout=30)
    print("[Sending: A to apply]")
    child.send('A')

    # Wait for completion
    child.expect(pexpect.EOF, timeout=120)

    print("\n[Process completed successfully]")
    output_file.close()

    sys.exit(child.exitstatus if child.exitstatus is not None else 0)

except pexpect.TIMEOUT as e:
    print(f"\n[TIMEOUT] {e}")
    output_file.close()
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] {e}")
    output_file.close()
    sys.exit(1)
