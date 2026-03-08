#!/Users/me/.python.venv/my-plex/bin/python3
"""
ONE-TIME SCRIPT: Integrate metadata from JSON file into cache

This script is a ONE-TIME helper to integrate the initial bulk metadata
collection into the cache. After this, --update-cache will handle incremental
metadata collection automatically.

Usage:
    ./one_time_integrate_metadata.py <metadata.json>

Example:
    # After collecting metadata on server:
    scp home:/tmp/video_metadata.json /tmp/
    ./one_time_integrate_metadata.py /tmp/video_metadata.json
"""

import sys
import os
import json
import pickle

# Add parent directory to path to import from main script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import necessary components from main script
# We need to be careful here as the main script has a lot of initialization
# So we'll just handle the cache directly

CACHE_FILE = os.path.expanduser('~/.plex_media_cache.pkl')
LOCK_FILE = os.path.expanduser('~/.plex_media_cache.lock')

def integrate_metadata(json_file):
    """Integrate metadata from JSON into cache"""

    if not os.path.exists(json_file):
        print(f"✗ Error: Metadata file not found: {json_file}")
        sys.exit(1)

    if not os.path.exists(CACHE_FILE):
        print(f"✗ Error: Cache file not found: {CACHE_FILE}")
        print(f"  Run 'my-plex --update-cache' first to create the cache.")
        sys.exit(1)

    # Load metadata JSON
    print(f"Loading metadata from: {json_file}")
    try:
        with open(json_file, 'r') as f:
            metadata_by_filepath = json.load(f)
    except Exception as e:
        print(f"✗ Error loading metadata JSON: {e}")
        sys.exit(1)

    print(f"  Loaded metadata for {len(metadata_by_filepath):,} files")

    # Load cache
    print(f"\nLoading cache from: {CACHE_FILE}")
    try:
        with open(CACHE_FILE, 'rb') as f:
            CACHE = pickle.load(f)
    except Exception as e:
        print(f"✗ Error loading cache: {e}")
        sys.exit(1)

    OBJ_BY_ID = CACHE.get('obj_by_id', {})
    if not OBJ_BY_ID:
        print(f"✗ Error: No media objects found in cache")
        sys.exit(1)

    print(f"  Cache contains {len(OBJ_BY_ID):,} media objects")

    # Integrate metadata
    print(f"\nIntegrating metadata into cache...")
    integrated_count = 0
    filesize_mismatch_count = 0
    not_in_cache_count = 0
    already_has_metadata_count = 0

    for filepath, file_metadata in metadata_by_filepath.items():
        found_in_cache = False

        # Search through all objects
        for obj in OBJ_BY_ID.values():
            files_dict = obj.get('files', {})

            # Check all versions
            for file_info in files_dict.values():
                if file_info.get('filepath') == filepath:
                    found_in_cache = True

                    # Validate filesize
                    cache_filesize = file_info.get('filesize')
                    metadata_filesize = file_metadata.get('filesize')

                    if cache_filesize != metadata_filesize:
                        filesize_mismatch_count += 1
                        print(f"⚠  Filesize mismatch: {filepath}")
                        print(f"   Cache: {cache_filesize:,} bytes, Metadata: {metadata_filesize:,} bytes")
                        continue

                    # Check if already has metadata with same filesize
                    if 'file_metadata' in file_info and file_info['file_metadata'].get('filesize') == metadata_filesize:
                        already_has_metadata_count += 1
                        continue

                    # Add metadata
                    file_info['file_metadata'] = file_metadata
                    integrated_count += 1

                    if integrated_count % 1000 == 0:
                        print(f"  Progress: {integrated_count:,} files integrated...")

        if not found_in_cache:
            not_in_cache_count += 1

    print(f"  ✓ Integrated {integrated_count:,} file metadata entries")

    # Save updated cache
    print(f"\nSaving updated cache to: {CACHE_FILE}")
    try:
        # Create backup first
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"{CACHE_FILE}.before_metadata_{timestamp}"
        shutil.copy2(CACHE_FILE, backup_file)
        print(f"  Created backup: {backup_file}")

        # Save updated cache
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(CACHE, f)
        print(f"  ✓ Cache saved successfully")

    except Exception as e:
        print(f"✗ Error saving cache: {e}")
        sys.exit(1)

    # Print summary
    print(f"\n{'='*80}")
    print(f"METADATA INTEGRATION COMPLETE")
    print(f"{'='*80}")
    print(f"✓ Integrated metadata:    {integrated_count:>8,} files")
    if already_has_metadata_count > 0:
        print(f"  Already had metadata:   {already_has_metadata_count:>8,} files")
    if filesize_mismatch_count > 0:
        print(f"⚠ Filesize mismatches:    {filesize_mismatch_count:>8,} files (skipped)")
    if not_in_cache_count > 0:
        print(f"⚠ Not in cache:           {not_in_cache_count:>8,} files (skipped)")

    print(f"\nCache file size: {os.path.getsize(CACHE_FILE) / (1024*1024):.1f} MB")
    print(f"\nNext step: Run 'my-plex --update-cache' to verify incremental collection works")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    json_file = sys.argv[1]
    integrate_metadata(json_file)
