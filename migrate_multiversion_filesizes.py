#!/usr/bin/env python3
"""
Migration script to update cache with correct file sizes for multi-version items.

This script:
1. Loads the existing Plex cache
2. Finds all multi-version items (items with multiple file versions in files dict)
3. Connects to Plex server and fetches the correct file size for each version
4. Updates the cache with the correct file sizes
5. Saves the updated cache

Run this ONCE to migrate from old format to new format.
"""

import pickle
import os
import sys
import time
from pathlib import Path

# Add parent directory to path to import from main script
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("Multi-Version Filesize Migration Script")
print("=" * 80)
print()

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
print()

# Check if cache exists
if not os.path.exists(CACHE_FILE):
    print(f"ERROR: Cache file not found: {CACHE_FILE}")
    print("Please run 'my-plex --update-cache' first to create the cache.")
    sys.exit(1)

# Load the cache
print(f"Loading cache from {CACHE_FILE}...")
try:
    with open(CACHE_FILE, 'rb') as f:
        cache_data = pickle.load(f)
except Exception as e:
    print(f"ERROR: Failed to load cache: {e}")
    sys.exit(1)

print(f"Cache loaded successfully!")
print(f"Total entries in cache: {len(cache_data.get('obj_by_id', {}))}")
print()

# Find multi-version items
media_entries = cache_data.get('obj_by_id', {})
multi_version_items = []

for key, obj in media_entries.items():
    files_dict = obj.get('files', {})
    if len(files_dict) > 1:
        multi_version_items.append((key, obj))

print(f"Found {len(multi_version_items)} multi-version items")
print()

if len(multi_version_items) == 0:
    print("No multi-version items found. Nothing to migrate.")
    sys.exit(0)

# Connect to Plex
print("Connecting to Plex server...")
try:
    from plexapi.server import PlexServer
    import urllib.parse

    # Parse PLEX_XML_URL if provided
    if PLEX_XML_URL:
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

print()

# Process multi-version items
print("Migrating multi-version items...")
print("=" * 80)
print()

updated_count = 0
error_count = 0
already_migrated_count = 0
start_time = time.time()

for idx, (key, obj) in enumerate(multi_version_items, 1):
    plex_id = obj.get('id')
    title = obj.get('title', 'Unknown')
    files_dict = obj.get('files', {})

    print(f"[{idx}/{len(multi_version_items)}] {title} (Plex ID: {plex_id})")

    # Check if already migrated (files dict has new format)
    first_file_info = next(iter(files_dict.values()))
    if isinstance(first_file_info, dict):
        print(f"  Already migrated (new format detected)")
        already_migrated_count += 1
        continue

    try:
        # Fetch the item from Plex
        item = plex.fetchItem(plex_id)

        # Build new files dict with correct filesizes
        new_files_dict = {}

        for media_idx, media in enumerate(item.media):
            for part in media.parts:
                # Reconstruct the version string (must match the one in cache)
                duration_minutes = round(media.duration / 60000, 2) if media.duration else 0
                version = f"{duration_minutes}min {media.width}x{media.height} ({media.videoCodec} {media.audioCodec})"

                # Check if this version exists in cache
                if version in files_dict:
                    new_files_dict[version] = {
                        'filepath': part.file,
                        'filesize': part.size
                    }
                    print(f"  ✓ {version}: {part.size / (1024**2):.1f} MB")

        # Update the object
        if new_files_dict:
            obj['files'] = new_files_dict
            updated_count += 1
        else:
            print(f"  ⚠ Warning: No matching versions found in Plex")
            error_count += 1

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        error_count += 1
        continue

    # Small delay to avoid hammering Plex
    time.sleep(0.05)

print()
print("=" * 80)
print(f"Migration complete!")
print(f"  Updated: {updated_count}")
print(f"  Already migrated: {already_migrated_count}")
print(f"  Errors: {error_count}")
print(f"  Total processed: {len(multi_version_items)}")
print()

if updated_count > 0:
    # Create backup
    backup_file = f"{CACHE_FILE}.backup-before-filesize-migration"
    print(f"Creating backup: {backup_file}")
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

    print()
    print(f"Saving updated cache to {CACHE_FILE}...")
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache_data, f)
        print(f"Cache saved successfully!")
    except Exception as e:
        print(f"ERROR: Failed to save cache: {e}")
        print(f"Backup is available at: {backup_file}")
        sys.exit(1)

    print()
    print("Done! The cache has been updated with correct file sizes for multi-version items.")
    print(f"Backup of original cache: {backup_file}")
else:
    print("No changes made to cache.")
