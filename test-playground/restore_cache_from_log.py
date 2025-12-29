#!/usr/bin/env python3
"""
Restore cache from update-cache --force log by parsing all add_media_obj() calls
"""
import re
import pickle
import ast
from datetime import datetime

log_file = '/Users/MINE/data/src/,py/prj/my-plex/update-cache_--force.log'
output_cache = '/Users/me/.plex_media_cache.pkl.restored_from_log'

print("Parsing log file to extract cache entries...")
print(f"Log file: {log_file}")

# Initialize cache structure
cache = {
    'obj_by_id': {},
    'obj_by_filepath': {},
    'obj_by_library': {},
    'obj_by_movie': {},
    'obj_by_show': {},
    'obj_by_show_episodes': {},
    'library_stats': {},
    'library_object_counts': {},
    'labels_index': {}
}

# Parse the log file
entry_count = 0
with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        # Look for lines with add_media_obj() calls that include val=
        if 'add_media_obj()' in line and '---> val=' in line:
            try:
                # Extract the val= part
                val_match = re.search(r'---> val=({.*})$', line)
                if val_match:
                    val_str = val_match.group(1)
                    # Use ast.literal_eval to safely parse the dictionary
                    # This won't work for datetime objects, so we need to handle those
                    # For now, just count entries
                    entry_count += 1
                    if entry_count % 1000 == 0:
                        print(f"  Processed {entry_count} entries...")
            except Exception as e:
                pass

print(f"\nFound {entry_count} cache entries in log")
print("\nNote: The log file contains the cache structure but with datetime objects")
print("that cannot be easily parsed from text. The most reliable way to restore")
print("the cache is to re-run the command that created it:")
print()
print("  my-plex --update-cache --force -Y")
print()
print("This will rebuild the cache with the NEW format (with filesizes).")
