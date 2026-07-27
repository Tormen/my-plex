#!/usr/bin/env python3
"""One-shot cleanup: drop orphan version-keys in obj['files'].

Background
----------
`add_media_obj_via_PLEX_API` historically *added* a new version-string key
to an object's `files` dict whenever Plex re-probed the same physical file
and reported a marginally different duration/codec/resolution.  The old
entry was left behind as an orphan — same filepath, different version key.
The new entry usually had no `file_metadata`, which then caused every
subsequent `--scan` to re-queue ffmpeg probing for thousands of files.

v2.41 prevents new orphans (drops the stale key and carries over
`file_metadata` to the new key in both `add_media_obj_via_PLEX_API` and
`_process_series_from_database`).  This playground script cleans up the
orphans that accumulated in the cache BEFORE v2.41 landed.

What it does
------------
For every Movie / Episode object, looks at `obj['files']` and groups
entries by `filepath`.  When a filepath appears under multiple version
keys, keeps the *best* one (criteria below) and drops the rest.

Best entry selection (in order):
  1. The one whose `file_metadata.filesize` matches `file_info.filesize`.
  2. The one whose `file_metadata.filesize` matches by itself.
  3. Any with a non-broken `file_metadata`.
  4. Anything with `file_metadata` (even broken).
  5. Newest by some other signal — at this point we just keep the first
     and drop the others.

USAGE
-----
    python3 playground/dedupe_orphan_version_keys.py [--dry-run] [--cache PATH]

Default cache path: /Users/me/.my-plex/cache.pkl
Backs up the original cache before writing.
"""
from __future__ import annotations
import argparse, os, pickle, shutil, sys
from datetime import datetime


def best_entry(entries):
    """Return the index of the best entry in `entries` (list of file_info dicts)."""
    # Tier 1: file_metadata with filesize matching the file_info filesize
    for i, e in enumerate(entries):
        fm = e.get('file_metadata')
        if isinstance(fm, dict) and not fm.get('broken') and fm.get('filesize') == e.get('filesize'):
            return i
    # Tier 2: any non-broken file_metadata
    for i, e in enumerate(entries):
        fm = e.get('file_metadata')
        if isinstance(fm, dict) and not fm.get('broken'):
            return i
    # Tier 3: any file_metadata (even broken)
    for i, e in enumerate(entries):
        fm = e.get('file_metadata')
        if isinstance(fm, dict):
            return i
    # Tier 4: first one
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--cache', default=os.path.expanduser('~/.my-plex/cache.pkl'),
                    help='Path to cache pickle (default: %(default)s)')
    ap.add_argument('--dry-run', '-n', action='store_true',
                    help='Report what would change; do not write.')
    args = ap.parse_args()

    if not os.path.exists(args.cache):
        print(f"ERROR: cache file not found: {args.cache}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading cache: {args.cache}")
    with open(args.cache, 'rb') as f:
        cache = pickle.load(f)

    obj_by_id = cache.get('obj_by_id') or {}
    print(f"  total objects: {len(obj_by_id):,}")

    by_lib = {}
    objs_with_orphans = 0
    keys_dropped_total = 0

    for key, obj in obj_by_id.items():
        if obj.get('type') not in ('Movie', 'Episode'):
            continue
        files = obj.get('files') or {}
        if not isinstance(files, dict) or len(files) < 2:
            continue

        # Group version-keys by filepath.
        fp_to_keys = {}
        for ver, fi in files.items():
            if not isinstance(fi, dict):
                continue
            fp = fi.get('filepath')
            if not fp:
                continue
            fp_to_keys.setdefault(fp, []).append(ver)

        # Only act on filepaths with >=2 version-keys (orphans present).
        had_orphans = False
        for fp, vkeys in fp_to_keys.items():
            if len(vkeys) < 2:
                continue
            had_orphans = True
            entries = [files[v] for v in vkeys]
            keep_idx = best_entry(entries)
            keep_ver = vkeys[keep_idx]
            drop_vers = [v for v in vkeys if v != keep_ver]

            lib = obj.get('library', '?')
            by_lib.setdefault(lib, {'objs': set(), 'keys_dropped': 0, 'examples': []})
            by_lib[lib]['objs'].add(key)
            by_lib[lib]['keys_dropped'] += len(drop_vers)
            if len(by_lib[lib]['examples']) < 3:
                by_lib[lib]['examples'].append({
                    'key': key, 'filepath': fp,
                    'keep': keep_ver, 'drop': drop_vers,
                })

            if not args.dry_run:
                for v in drop_vers:
                    del files[v]
                keys_dropped_total += len(drop_vers)
        if had_orphans:
            objs_with_orphans += 1

    print()
    print(f"{'LIBRARY':<25s}  OBJS_WITH_ORPHANS  KEYS_TO_DROP")
    print(f"{'-' * 25}  {'-' * 17}  {'-' * 12}")
    for lib in sorted(by_lib):
        s = by_lib[lib]
        print(f"{lib:<25s}  {len(s['objs']):>17,}  {s['keys_dropped']:>12,}")
    print()
    print(f"TOTAL: {objs_with_orphans:,} objects with orphan version-keys, "
          f"{sum(s['keys_dropped'] for s in by_lib.values()):,} keys to drop.")
    print()
    for lib in sorted(by_lib):
        s = by_lib[lib]
        if not s['examples']:
            continue
        print(f"--- examples ({lib}) ---")
        for ex in s['examples']:
            print(f"  {ex['key']}")
            print(f"      filepath: {ex['filepath']}")
            print(f"      keep:     {ex['keep']!r}")
            for d in ex['drop']:
                print(f"      drop:     {d!r}")
        print()

    if args.dry_run:
        print("(dry-run — no changes written)")
        return

    if keys_dropped_total == 0:
        print("Nothing to do.  Cache already clean.")
        return

    # Backup and save.
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = f"{args.cache}.bak_dedupe_orphans_{ts}"
    shutil.copy2(args.cache, backup)
    print(f"Backup written: {backup}")
    with open(args.cache, 'wb') as f:
        pickle.dump(cache, f)
    print(f"Cache rewritten: {args.cache} ({keys_dropped_total:,} orphan keys removed)")


if __name__ == '__main__':
    main()
