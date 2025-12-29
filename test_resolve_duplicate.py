#!/usr/bin/env python3
"""
Test script for --list-duplicates --resolve functionality.

Usage:
    ./test_resolve_duplicate.py [--choice CHOICE] [--apply] [--debug] [--timeout SECONDS]

Examples:
    # Choose option 4 (trash file [2]) and apply
    ./test_resolve_duplicate.py --choice 4 --apply

    # Choose option 3 (trash file [1]) without applying
    ./test_resolve_duplicate.py --choice 3

    # Run with debug output and custom timeout
    ./test_resolve_duplicate.py --choice 4 --apply --debug --timeout 300
"""
import pexpect
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description='Test --list-duplicates --resolve with automated choices'
    )
    parser.add_argument(
        '--choice',
        type=str,
        required=True,
        help='Choice to send at first prompt (e.g., 1-7, N, Q)'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Send "A" to apply changes (otherwise sends "Q" to quit)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Run my-plex with -D debug flag'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=240,
        help='Timeout in seconds (default: 240)'
    )
    parser.add_argument(
        '--output-log',
        type=str,
        help='Save output to specified log file'
    )

    args = parser.parse_args()

    # Build command
    cmd_args = ['--list-duplicates', '--resolve']
    if args.debug:
        cmd_args.insert(0, '-D')

    print("=" * 76)
    print(f"TESTING: --list-duplicates --resolve")
    print("=" * 76)
    print(f"Choice: {args.choice}")
    print(f"Apply: {'Yes (A)' if args.apply else 'No (Q)'}")
    print(f"Debug: {args.debug}")
    print(f"Timeout: {args.timeout}s")
    if args.output_log:
        print(f"Output log: {args.output_log}")
    print("=" * 76)
    print()

    child = pexpect.spawn('my-plex', cmd_args, encoding='utf-8', timeout=args.timeout)

    # Optionally save to log file
    if args.output_log:
        output_file = open(args.output_log, 'w')
        child.logfile_read = output_file
    else:
        child.logfile = sys.stdout

    try:
        # Wait for the first "Your choice:" prompt
        child.expect("Your choice:", timeout=180)
        print(f"\n[Sending choice: {args.choice}]", flush=True)
        child.send(args.choice)

        # Wait for next prompt
        child.expect("Your choice:", timeout=30)

        if args.apply:
            print("\n[Sending: A to apply]", flush=True)
            child.send('A')
        else:
            print("\n[Sending: Q to quit without applying]", flush=True)
            child.send('Q')

        # Wait for completion
        child.expect(pexpect.EOF, timeout=120)

        print("\n[Process completed successfully]")
        exit_code = child.exitstatus if child.exitstatus is not None else 0

        if args.output_log:
            output_file.close()
            print(f"\n[Output saved to: {args.output_log}]")

        sys.exit(exit_code)

    except pexpect.TIMEOUT as e:
        print(f"\n[TIMEOUT] {e}")
        if hasattr(child, 'before') and child.before:
            print(f"Last output: {child.before[-500:]}")
        if args.output_log:
            output_file.close()
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        if args.output_log:
            output_file.close()
        sys.exit(1)


if __name__ == '__main__':
    main()
