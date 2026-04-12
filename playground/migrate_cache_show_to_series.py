#!/usr/bin/env python3
"""One-time migration: rename Show→Series in cache.pkl

Migrates:
  - Cache keys:    Show:NNNN  →  Series:NNNN
  - Type strings:  'Show'     →  'Series'
  - Pickle keys:   obj_by_show*  →  obj_by_series*
  - Internal refs: series_key, type fields

Usage:
  python3 playground/migrate_cache_show_to_series.py [--cache PATH]

Default cache path: ~/.my-plex/cache.pkl
Creates a backup at cache.pkl.bak-show-to-series before writing.
"""

import os, sys, pickle, shutil

CACHE_PATH = os.path.expanduser('~/.my-plex/cache.pkl')
if '--cache' in sys.argv:
    idx = sys.argv.index('--cache')
    if idx + 1 < len(sys.argv):
        CACHE_PATH = sys.argv[idx + 1]

if not os.path.exists(CACHE_PATH):
    print(f"ERROR: Cache file not found: {CACHE_PATH}")
    sys.exit(1)

# Load cache
print(f"Loading cache: {CACHE_PATH}")
with open(CACHE_PATH, 'rb') as f:
    cache = pickle.load(f)

print(f"Cache keys: {list(cache.keys())}")

# --- 1. Rename top-level pickle keys ---
KEY_RENAMES = {
    'obj_by_show': 'obj_by_series',
    'obj_by_show_episodes': 'obj_by_series_episodes',
    'obj_by_show_scraped': 'obj_by_series_scraped',
}
for old_key, new_key in KEY_RENAMES.items():
    if old_key in cache:
        print(f"  Renaming pickle key: {old_key} → {new_key}")
        cache[new_key] = cache.pop(old_key)

# --- 2. Rename cache keys in OBJ_BY_ID: Show:NNN → Series:NNN ---
obj_by_id = cache.get('obj_by_id', {})
keys_to_rename = [k for k in obj_by_id if k.startswith('Show:')]
print(f"  Renaming {len(keys_to_rename)} Show:NNN keys in obj_by_id")
for old_key in keys_to_rename:
    new_key = 'Series:' + old_key[5:]
    obj_by_id[new_key] = obj_by_id.pop(old_key)

# --- 3. Update type field in all objects ---
type_count = 0
for key, obj in obj_by_id.items():
    if isinstance(obj, dict) and obj.get('type') == 'Show':
        obj['type'] = 'Series'
        type_count += 1
print(f"  Updated type 'Show'→'Series' in {type_count} objects")

# --- 4. Rename 'show_key' field → 'series_key' in all objects ---
field_count = 0
for key, obj in obj_by_id.items():
    if isinstance(obj, dict) and 'show_key' in obj:
        obj['series_key'] = obj.pop('show_key')
        field_count += 1
print(f"  Renamed 'show_key'→'series_key' field in {field_count} objects")

# --- 5. Update series_key references in episodes/seasons (Show: → Series:) ---
ref_count = 0
for key, obj in obj_by_id.items():
    if isinstance(obj, dict):
        sk = obj.get('series_key', '')
        if isinstance(sk, str) and sk.startswith('Show:'):
            obj['series_key'] = 'Series:' + sk[5:]
            ref_count += 1
print(f"  Updated {ref_count} series_key references")

# --- 5. Rename keys in OBJ_BY_SERIES (was OBJ_BY_SHOW) ---
obj_by_series = cache.get('obj_by_series', {})
show_keys = [k for k in obj_by_series if k.startswith('Show:')]
print(f"  Renaming {len(show_keys)} Show:NNN keys in obj_by_series")
for old_key in show_keys:
    new_key = 'Series:' + old_key[5:]
    obj_by_series[new_key] = obj_by_series.pop(old_key)

# --- 6. Rename keys in OBJ_BY_SERIES_EPISODES ---
obj_by_eps = cache.get('obj_by_series_episodes', {})
show_keys = [k for k in obj_by_eps if k.startswith('Show:')]
print(f"  Renaming {len(show_keys)} Show:NNN keys in obj_by_series_episodes")
for old_key in show_keys:
    new_key = 'Series:' + old_key[5:]
    obj_by_eps[new_key] = obj_by_eps.pop(old_key)

# --- 7. Rename keys in OBJ_BY_SERIES_SCRAPED ---
obj_by_scraped = cache.get('obj_by_series_scraped', {})
show_keys = [k for k in obj_by_scraped if k.startswith('Show:')]
print(f"  Renaming {len(show_keys)} Show:NNN keys in obj_by_series_scraped")
for old_key in show_keys:
    new_key = 'Series:' + old_key[5:]
    obj_by_scraped[new_key] = obj_by_scraped.pop(old_key)

# --- 8. Rename keys in OBJ_BY_LIBRARY ---
obj_by_lib = cache.get('obj_by_library', {})
for lib_name, lib_data in obj_by_lib.items():
    if isinstance(lib_data, dict) and 'Show' in lib_data:
        print(f"  Renaming OBJ_BY_LIBRARY['{lib_name}']['Show'] → ['Series']")
        lib_data['Series'] = lib_data.pop('Show')
        # Rename individual keys in the list
        if isinstance(lib_data['Series'], list):
            lib_data['Series'] = [
                'Series:' + k[5:] if k.startswith('Show:') else k
                for k in lib_data['Series']
            ]

# --- 9. Rename keys in OBJ_BY_FILEPATH ---
obj_by_fp = cache.get('obj_by_filepath', {})
fp_count = 0
for fp, key in list(obj_by_fp.items()):
    if isinstance(key, str) and key.startswith('Show:'):
        obj_by_fp[fp] = 'Series:' + key[5:]
        fp_count += 1
print(f"  Updated {fp_count} Show: refs in obj_by_filepath")

# --- 10. Rename 'shows' key in obj_count dicts ---
obj_count = cache.get('obj_count', {})
for lib_name, counts in obj_count.items():
    if isinstance(counts, dict) and 'shows' in counts:
        counts['series'] = counts.pop('shows')
        print(f"  Renamed obj_count['{lib_name}']['shows'] → ['series']")

# --- Backup and save ---
backup_path = CACHE_PATH + '.bak-show-to-series'
print(f"\nBacking up to: {backup_path}")
shutil.copy2(CACHE_PATH, backup_path)

print(f"Writing migrated cache: {CACHE_PATH}")
with open(CACHE_PATH, 'wb') as f:
    pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)

# --- Verify ---
print(f"\nVerification:")
with open(CACHE_PATH, 'rb') as f:
    verify = pickle.load(f)

show_keys_remaining = [k for k in verify.get('obj_by_id', {}) if k.startswith('Show:')]
show_types_remaining = sum(1 for obj in verify.get('obj_by_id', {}).values()
                           if isinstance(obj, dict) and obj.get('type') == 'Show')
old_pickle_keys = [k for k in verify if k.startswith('obj_by_show')]

print(f"  Show: keys in obj_by_id: {len(show_keys_remaining)} (should be 0)")
print(f"  type='Show' objects:     {show_types_remaining} (should be 0)")
print(f"  Old pickle keys:         {old_pickle_keys} (should be [])")

if show_keys_remaining or show_types_remaining or old_pickle_keys:
    print("\n⚠ Migration incomplete — some Show references remain!")
    sys.exit(1)
else:
    print("\n✓ Migration complete. All Show references converted to Series.")
