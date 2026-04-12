"""One-time cache patch: add abs_ep_idx to episodes with scraped data.

Avoids `my-plex --update-cache --from-scratch` by patching the existing
cache.pkl in place with the new abs_ep_idx field.

Applies, per show in obj_by_id (only if scraped data exists):
  1. episode_obj['abs_ep_idx']  — 1-based running counter across all seasons
  2. season_obj['abs_ep_max']   — highest abs_ep_idx within that season
  3. show_obj['abs_ep_max']     — highest abs_ep_idx across show (= total episodes)

Multi-episode siblings share the leader's abs_ep_idx (leader = siblings[0]).
Shows without scraped data are skipped — no abs_ep_idx assigned.
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
obj_by_show = data.get('obj_by_show', {})
obj_by_show_episodes = data.get('obj_by_show_episodes', {})
obj_by_show_scraped = data.get('obj_by_show_scraped', {})

if not obj_by_id:
    raise SystemExit("obj_by_id is empty — nothing to patch.")

shows_with_scraped = 0
shows_without_scraped = 0
episodes_updated = 0
seasons_updated = 0
shows_updated = 0

for show_key, scraped in obj_by_show_scraped.items():
    scraped_eps = scraped.get('episodes', {})
    if not scraped_eps:
        shows_without_scraped += 1
        continue

    show_obj = obj_by_id.get(show_key)
    if not show_obj:
        continue

    ep_data = obj_by_show_episodes.get(show_key, {})
    if not ep_data:
        shows_without_scraped += 1
        continue

    shows_with_scraped += 1
    abs_counter = 0
    show_abs_max = 0

    for s_str in sorted(ep_data.keys()):
        e_dict = ep_data[s_str]
        season_abs_max = 0
        for e_str in sorted(e_dict.keys()):
            for _ver, ep_keys in e_dict[e_str].items():
                for ep_key in ep_keys:
                    ep_obj = obj_by_id.get(ep_key)
                    if not ep_obj:
                        continue
                    # Multi-episode non-leaders share the leader's abs_ep_idx
                    siblings = ep_obj.get('multi_episode_siblings') or []
                    if len(siblings) >= 2 and ep_key != siblings[0]:
                        leader = obj_by_id.get(siblings[0])
                        if leader and 'abs_ep_idx' in leader:
                            ep_obj['abs_ep_idx'] = leader['abs_ep_idx']
                            episodes_updated += 1
                            continue
                    abs_counter += 1
                    ep_obj['abs_ep_idx'] = abs_counter
                    episodes_updated += 1
                    if abs_counter > season_abs_max:
                        season_abs_max = abs_counter

        # Store season abs_ep_max
        s_key_lookup = obj_by_show.get(show_key, {}).get(s_str)
        if s_key_lookup:
            season_obj = obj_by_id.get(s_key_lookup)
            if season_obj:
                season_obj['abs_ep_max'] = season_abs_max
                seasons_updated += 1
        if season_abs_max > show_abs_max:
            show_abs_max = season_abs_max

    show_obj['abs_ep_max'] = show_abs_max
    shows_updated += 1

print()
print(f"Shows with scraped data (updated):     {shows_with_scraped}")
print(f"Shows without scraped data (skipped):   {shows_without_scraped}")
print(f"Episodes with abs_ep_idx assigned:      {episodes_updated}")
print(f"Seasons with abs_ep_max assigned:        {seasons_updated}")
print(f"Shows with abs_ep_max assigned:          {shows_updated}")

backup = CACHE_FILE + '.bak-abs-ep-idx'
shutil.copy2(CACHE_FILE, backup)
print(f"\nBackup saved: {backup}")

with open(CACHE_FILE, 'wb') as f:
    pickle.dump(data, f)
print("Cache updated.")
