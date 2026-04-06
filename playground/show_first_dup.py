#!/Users/me/.python.venv/my-plex/bin/python3
import pexpect
import sys

child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'],
                       encoding='utf-8', timeout=240)
output_file = open('/tmp/first_dup_output.log', 'w')
child.logfile_read = output_file

try:
    # Handle cache update prompt if it appears
    index = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=180)
    
    if index == 0:
        # Cache update prompt - say no
        print("[Answering 'no' to cache update]")
        child.send('no\n')
        child.expect("Your choice:", timeout=180)
    
    # Now at first duplicate choice
    print("[Found first duplicate]")
    child.send('q')
    child.expect(pexpect.EOF, timeout=5)
    
    output_file.close()
    
    # Show last 80 lines before "Your choice:"
    with open('/tmp/first_dup_output.log', 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if "Your choice:" in line:
                start = max(0, i - 80)
                print("\n" + "="*76)
                print("FIRST DUPLICATE:")
                print("="*76)
                for j in range(start, i + 1):
                    print(lines[j], end='')
                break
    
    sys.exit(0)

except Exception as e:
    output_file.close()
    print(f"Error: {e}")
    sys.exit(1)
