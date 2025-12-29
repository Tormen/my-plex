#!/usr/bin/env python3
"""
Script to automatically resolve Arthur (2011) duplicate by choosing option 4 (trash file [2])
"""
import subprocess
import sys

# Run my-plex with --list-duplicates --resolve and provide automated input
proc = subprocess.Popen(
    ['my-plex', '-D', '--list-duplicates', '--resolve'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1  # Line buffered
)

# Send input: "4" to choose trash file [2], then "A" to apply
# We need to provide these when prompted
try:
    # Wait a bit for the prompt and send input
    import time
    time.sleep(2)  # Give it time to load and display

    # Send "4" to trash file [2]
    proc.stdin.write("4\n")
    proc.stdin.flush()

    time.sleep(0.5)

    # Send "A" to apply
    proc.stdin.write("A\n")
    proc.stdin.flush()

    # Close stdin to signal we're done
    proc.stdin.close()

    # Wait for completion and get output
    output, _ = proc.communicate(timeout=120)
    print(output)

    sys.exit(proc.returncode)

except subprocess.TimeoutExpired:
    proc.kill()
    print("Process timed out")
    sys.exit(1)
except Exception as e:
    proc.kill()
    print(f"Error: {e}")
    sys.exit(1)
