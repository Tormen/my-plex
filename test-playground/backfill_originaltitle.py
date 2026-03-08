#!/usr/bin/env python3
"""
Backfill script to add originalTitle to existing cache entries.

This script reads the existing Plex cache, connects to the Plex server,
and adds the originalTitle field to all cached media items.
"""

import pickle
import os
import sys
import time
from pathlib import Path

# Add parent directory to path to import from main script
sys.path.insert(0, str(Path(__file__).parent))

# Import necessary components from main script
# We'll need to run this after setting up the environment
print("Loading my-plex configuration...")

# Read config from the main script
config_file = os.path.expanduser('~/.my-plex.conf')
if not os.path.exists(config_file):
    print(f"ERROR: Config file not found: {config_file}")
    print(f"Please create a config file first:")
    print(f"  my-plex --create")
    sys.exit(1)

# Execute the config file to get settings
config_vars = {}
with open(config_file, 'r') as f:
    exec(f.read(), config_vars)

# Get cache file location
CACHE_FILE = config_vars.get('CACHE_FILE', '.plex_media_cache.pkl')
# If it's a relative path, expand it relative to home directory
if not os.path.isabs(CACHE_FILE):
    CACHE_FILE = os.path.expanduser(f"~/{CACHE_FILE}")
else:
    CACHE_FILE = os.path.expanduser(CACHE_FILE)

# Get Plex connection details
PLEX_URL = config_vars.get('PLEX_URL')
PLEX_TOKEN = config_vars.get('PLEX_TOKEN')
PLEX_XML_URL = config_vars.get('PLEX_XML_URL')

print(f"Cache file: {CACHE_FILE}")
print(f"Plex URL configured: {bool(PLEX_URL or PLEX_XML_URL)}")

# Check if cache exists
if not os.path.exists(CACHE_FILE):
    print(f"ERROR: Cache file not found: {CACHE_FILE}")
    print("Please run 'my-plex --update-cache' first to create the cache.")
    sys.exit(1)

# Load the cache
print(f"\nLoading cache from {CACHE_FILE}...")
try:
    with open(CACHE_FILE, 'rb') as f:
        cache_data = pickle.load(f)
except Exception as e:
    print(f"ERROR: Failed to load cache: {e}")
    sys.exit(1)

print(f"Cache loaded successfully!")
print(f"Total entries in cache: {len(cache_data)}")

# Connect to Plex
print("\nConnecting to Plex server...")
try:
    from plexapi.server import PlexServer

    # Parse PLEX_XML_URL if provided
    if PLEX_XML_URL:
        import urllib.parse
        parsed = urllib.parse.urlparse(PLEX_XML_URL)
        query_params = urllib.parse.parse_qs(parsed.query)

        # Extract base URL and token
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        token = query_params.get('X-Plex-Token', [None])[0]

        if not token:
            print("ERROR: No X-Plex-Token found in PLEX_XML_URL")
            sys.exit(1)

        plex = PlexServer(base_url, token)
    elif PLEX_URL and PLEX_TOKEN:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN)
    else:
        print("ERROR: No Plex connection configured (need PLEX_URL+PLEX_TOKEN or PLEX_XML_URL)")
        sys.exit(1)

    print(f"Connected to Plex server: {plex.friendlyName}")
except Exception as e:
    print(f"ERROR: Failed to connect to Plex: {e}")
    sys.exit(1)

# Process cache entries
print("\nBackfilling originalTitle for cache entries...")
updated_count = 0
skipped_count = 0
error_count = 0

# The actual media entries are in cache_data['obj_by_id']
if 'obj_by_id' not in cache_data:
    print("ERROR: Cache structure not recognized - missing 'obj_by_id' key")
    sys.exit(1)

media_entries = cache_data['obj_by_id']
total_entries = len(media_entries)
print(f"Found {total_entries} media entries to process")

# Process entries with progress tracking and rate limiting
processed_count = 0
start_time = time.time()
last_save_time = start_time

for key, val in media_entries.items():
    processed_count += 1

    # Skip if originalTitle already exists
    if 'originalTitle' in val:
        skipped_count += 1
        continue

    try:
        # Get the Plex object by ratingKey
        obj_id = val.get('id')
        if not obj_id:
            if processed_count % 1000 == 1:  # Only warn occasionally for metadata entries
                print(f"INFO: Skipping metadata entry {key}")
            error_count += 1
            val['originalTitle'] = None
            continue

        # Fetch the object from Plex
        obj = plex.fetchItem(obj_id)

        # Get originalTitle if available
        original_title = getattr(obj, 'originalTitle', None) if hasattr(obj, 'originalTitle') else None

        # Update cache entry
        val['originalTitle'] = original_title
        updated_count += 1

        # Progress reporting
        if processed_count % 100 == 0:
            elapsed = time.time() - start_time
            rate = processed_count / elapsed if elapsed > 0 else 0
            eta_seconds = (total_entries - processed_count) / rate if rate > 0 else 0
            eta_mins = int(eta_seconds / 60)
            print(f"Progress: {processed_count}/{total_entries} ({100*processed_count/total_entries:.1f}%) - "
                  f"{updated_count} updated, {skipped_count} skipped, {error_count} errors - "
                  f"Rate: {rate:.1f} entries/sec - ETA: {eta_mins} mins")
            sys.stdout.flush()

        # Save checkpoint every 5 minutes
        if time.time() - last_save_time > 300:
            print(f"\nSaving checkpoint at {processed_count}/{total_entries}...")
            try:
                with open(CACHE_FILE, 'wb') as f:
                    pickle.dump(cache_data, f)
                print(f"Checkpoint saved successfully")
                last_save_time = time.time()
            except Exception as e:
                print(f"WARNING: Failed to save checkpoint: {e}")

        # Small delay to avoid hammering the Plex server
        time.sleep(0.05)

    except Exception as e:
        print(f"ERROR processing {key} (ID: {obj_id if 'obj_id' in locals() else 'unknown'}): {e}")
        error_count += 1
        # Set to None so we don't try again
        val['originalTitle'] = None
        continue

print(f"\nBackfill complete!")
print(f"  Updated: {updated_count}")
print(f"  Skipped (already had originalTitle): {skipped_count}")
print(f"  Errors: {error_count}")

# Save the updated cache
backup_file = f"{CACHE_FILE}.backup-before-originaltitle"
print(f"\nCreating backup: {backup_file}")
try:
    import shutil
    shutil.copy2(CACHE_FILE, backup_file)
    print(f"Backup created successfully")
except Exception as e:
    print(f"WARNING: Failed to create backup: {e}")
    response = input("Continue without backup? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        sys.exit(1)

print(f"\nSaving updated cache to {CACHE_FILE}...")
try:
    with open(CACHE_FILE, 'wb') as f:
        pickle.dump(cache_data, f)
    print(f"Cache saved successfully!")
except Exception as e:
    print(f"ERROR: Failed to save cache: {e}")
    print(f"Backup is available at: {backup_file}")
    sys.exit(1)

print("\nDone! The cache has been updated with originalTitle information.")
print(f"Backup of original cache: {backup_file}")
