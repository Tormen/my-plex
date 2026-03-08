#!/Users/me/.python.venv/my-plex/bin/python3
import pexpect, sys
child = pexpect.spawn('my-plex', ['--list-duplicates', '--resolve'], encoding='utf-8', timeout=240)
child.logfile = sys.stdout
try:
    idx = child.expect(["Update cache now\\? \\(yes/no\\):", "Your choice:"], timeout=180)
    if idx == 0:
        child.send('no\n')
        child.expect("Your choice:", timeout=180)
    child.send('3')  # Trash file [1]
    child.expect("Your choice:", timeout=30)
    child.send('A')  # Apply
    child.expect(pexpect.EOF, timeout=120)
    sys.exit(0)
except Exception as e:
    print(f"\nError: {e}")
    sys.exit(1)
