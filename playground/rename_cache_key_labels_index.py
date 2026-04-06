#!/usr/bin/env python3
"""One-time cache migration: rename 'labels_index' → 'plex_labels_index'.

Run once before deploying the my-plex version that uses plex_labels_index.
Safe to run multiple times (idempotent).
"""
import os
import pickle
import shutil
from datetime import datetime

CACHE_FILE = os.path.expanduser("~/.my-plex/cache.pkl")
BACKUP_FILE = CACHE_FILE + f".backup_labels_rename_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

print(f"Cache file: {CACHE_FILE}")

with open(CACHE_FILE, "rb") as f:
    cache = pickle.load(f)

if "plex_labels_index" in cache:
    print("Already migrated (plex_labels_index exists). Nothing to do.")
elif "labels_index" not in cache:
    print("No labels_index key found. Cache may be empty or already new format.")
else:
    shutil.copy2(CACHE_FILE, BACKUP_FILE)
    print(f"Backup written: {BACKUP_FILE}")

    cache["plex_labels_index"] = cache.pop("labels_index")
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(cache, f)
    print(f"Done. 'labels_index' renamed to 'plex_labels_index' ({len(cache['plex_labels_index'])} entries).")
