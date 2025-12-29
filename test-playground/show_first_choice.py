#!/usr/bin/env python3
import pexpect
import sys

print("=" * 76)
print("CAPTURING: First duplicate choice from --list-duplicates --resolve")
print("=" * 76)
print()

child = pexpect.spawn('my-plex', ['-D', '--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=300)

# Save output to file for analysis
output_file = open('/tmp/resolve_first_choice.log', 'w')
child.logfile_read = output_file

try:
    # Wait for the first "Your choice:" prompt
    child.expect("Your choice:", timeout=180)
    print("\n[Found first duplicate choice prompt]")

    # Send 'q' to quit so we can see the output
    child.send('q')

    # Wait for completion or EOF
    try:
        child.expect(pexpect.EOF, timeout=5)
    except:
        pass

    output_file.close()

    print("\n[Displaying the choice that was presented]")
    print("=" * 76)

    # Read and display the log file, showing lines around "Your choice:"
    with open('/tmp/resolve_first_choice.log', 'r') as f:
        lines = f.readlines()
        # Find "Your choice:" and show 50 lines before it
        for i, line in enumerate(lines):
            if "Your choice:" in line:
                start = max(0, i - 50)
                for j in range(start, i + 1):
                    print(lines[j], end='')
                break

    print("=" * 76)
    sys.exit(0)

except pexpect.TIMEOUT as e:
    print(f"\n[TIMEOUT] {e}")
    output_file.close()
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] {e}")
    output_file.close()
    sys.exit(1)
