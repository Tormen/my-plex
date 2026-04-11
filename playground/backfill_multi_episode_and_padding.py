"""One-time cache patch for the multi-episode + padding refactor.

Avoids `my-plex --update-cache --from-scratch` by patching the existing
cache.pkl in place with the new fields introduced across:

  - 8a9ea37 episodes: zero-pad S0XE0X per show; drop episode_map
  - cf5b4e2 episodes: detect Plex multi-episode files; collapse S07E15-16

Applies, per show in obj_by_id:
  1. show['S_pad_width'] / show['E_pad_width']   (computed from max idx)
  2. each episode's obj['S0XE0X']                (rewritten with per-show
                                                  padding widths)
  3. obj['multi_episode_siblings']               (sorted leader-first list
                                                  for every episode group
                                                  sharing a single file)

Not applied here (populated on the next regular --update-cache run):
  - obj['scraped_E_str']: filled by _ensure_tsv_and_normalize_episodes
    when Plex and the scraped TSV disagree. Missing on episodes for
    which the old cache already removed episode_map indirection —
    a normal --update-cache (no --from-scratch) will re-scrape and
    populate it.
  - OBJ_BY_SHOW_SCRAPED[show]['episode_map'] / ['season_map']: dead
    structures. Left in place; harmless (nothing reads them), will
    disappear the next time their parent dict is rewritten.
"""
import os
import pickle
import shutil
from collections import defaultdict

CACHE_FILE = os.path.expanduser('~/.my-plex/cache.pkl')

print(f"Loading cache: {CACHE_FILE}")
with open(CACHE_FILE, 'rb') as f:
    data = pickle.load(f)

obj_by_id = data.get('obj_by_id', {})
if not obj_by_id:
    raise SystemExit("obj_by_id is empty — nothing to patch.")

# Group episodes by show_key
eps_by_show = defaultdict(list)   # show_key -> [(ep_key, ep_obj), ...]
shows = {}                        # show_key -> show_obj
for key, obj in obj_by_id.items():
    if not isinstance(obj, dict):
        continue
    t = obj.get('type', '')
    if t == 'Show':
        shows[key] = obj
    elif t == 'Episode':
        sk = obj.get('show_key', '')
        if sk:
            eps_by_show[sk].append((key, obj))

print(f"Shows: {len(shows)}  Episodes grouped: {sum(len(v) for v in eps_by_show.values())}")

pad_updated = 0
s0xe0x_updated = 0
multi_ep_groups = 0
multi_ep_eps = 0

for show_key, show_obj in shows.items():
    show_eps = eps_by_show.get(show_key, [])

    # ---- 1. per-show padding widths (match my-plex.py formula) ----
    max_s_idx = 0
    max_e_idx = 0
    for _, ep in show_eps:
        si = ep.get('S_idx', 0) or 0
        ei = ep.get('E_idx', 0) or 0
        if si > max_s_idx:
            max_s_idx = si
        if ei > max_e_idx:
            max_e_idx = ei
    s_pad = max(2, len(str(max_s_idx))) if max_s_idx else 2
    e_pad = max(2, len(str(max_e_idx))) if max_e_idx else 2
    if show_obj.get('S_pad_width') != s_pad or show_obj.get('E_pad_width') != e_pad:
        show_obj['S_pad_width'] = s_pad
        show_obj['E_pad_width'] = e_pad
        pad_updated += 1

    # ---- 2. rewrite every episode's display-only S0XE0X ----
    for _, ep in show_eps:
        si = ep.get('S_idx', 0) or 0
        ei = ep.get('E_idx', 0) or 0
        new_s0xe0x = f"S{si:0{s_pad}d}E{ei:0{e_pad}d}"
        if ep.get('S0XE0X') != new_s0xe0x:
            ep['S0XE0X'] = new_s0xe0x
            s0xe0x_updated += 1

    # ---- 3. detect multi-episode file groups (shared filepath) ----
    file_to_eps = defaultdict(list)
    for ep_key, ep in show_eps:
        fp = ep.get('file', '')
        if fp:
            file_to_eps[fp].append(ep_key)
    for fp, sib_keys in file_to_eps.items():
        if len(sib_keys) < 2:
            continue
        # Sort by E_idx so siblings[0] is the lowest-E leader
        sib_keys.sort(key=lambda k: obj_by_id.get(k, {}).get('E_idx', 0))
        multi_ep_groups += 1
        for ep_key in sib_keys:
            ep = obj_by_id.get(ep_key)
            if ep is not None:
                ep['multi_episode_siblings'] = list(sib_keys)
                multi_ep_eps += 1

print()
print(f"Shows with padding widths written:     {pad_updated}")
print(f"Episodes with S0XE0X rewritten:        {s0xe0x_updated}")
print(f"Multi-episode file groups detected:    {multi_ep_groups}")
print(f"Episodes marked with siblings:         {multi_ep_eps}")

backup = CACHE_FILE + '.bak-multi-episode-padding'
shutil.copy2(CACHE_FILE, backup)
print(f"\nBackup saved: {backup}")

with open(CACHE_FILE, 'wb') as f:
    pickle.dump(data, f)
print("Cache updated.")
