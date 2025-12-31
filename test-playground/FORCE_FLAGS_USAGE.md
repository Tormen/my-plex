# Force Flags Usage Guide

## Overview

The `my-plex` tool has three force-related flags that control different aspects of cache rebuilding. Understanding when to use each flag helps optimize rebuild time vs. completeness.

## Flag Hierarchy

```
--force
├── --force-plexdata  (Plex metadata verification)
└── --force-metadata  (Video file metadata collection)
```

## Individual Flags

### `--force-plexdata`

**What it does**: Forces Plex to verify ALL existing files and metadata.

**Technical details**:
- Runs BOTH `lib.update()` AND `lib.refresh()`
- `lib.update()`: Scans for NEW files only (fast)
- `lib.refresh()`: Verifies EVERY existing file (slow but thorough)
- Detects additions, changes, AND deletions
- Ensures Plex metadata is completely up-to-date

**When to use**:
- After bulk file operations (moves, renames, deletions)
- When you suspect Plex has stale metadata
- When files exist but Plex doesn't show them
- When you've manually fixed file issues and want Plex to re-verify

**Performance**: SLOW (verifies every file in Plex database)

**Example**:
```bash
my-plex --update-cache --force-plexdata
```

---

### `--force-metadata`

**What it does**: Forces recollection of video file container metadata (durations).

**Technical details**:
- Reads MKV/MP4/AVI container headers
- Collects duration information from file containers
- Used for detecting truncated/broken files
- Normally only collected for new files or files with changed filesize

**When to use**:
- First time setting up broken file detection
- After rebuilding cache with `--from-scratch`
- When you suspect metadata is incorrect or corrupted
- When you want to rebuild metadata from scratch

**Performance**: SLOW (reads file headers for 14k+ files)

**Example**:
```bash
my-plex --update-cache --force-metadata
```

---

### `--force`

**What it does**: Triggers BOTH `--force-plexdata` AND `--force-metadata`.

**Technical details**:
- Equivalent to: `--update-cache --force-plexdata --force-metadata`
- Most comprehensive rebuild option
- Verifies everything: Plex data + video file metadata

**When to use**:
- Complete system verification after major changes
- Recovery from corrupted cache or Plex database
- When you want absolute certainty everything is current
- Initial setup of broken file detection on existing library

**Performance**: SLOWEST (combines both slow operations)

**Example**:
```bash
my-plex --update-cache --force
```

---

## Common Usage Patterns

### Normal Operation (Incremental Updates)
```bash
my-plex --update-cache
```
- Only scans for NEW files in Plex
- Only collects metadata for new/changed files
- **Recommended for regular updates**

---

### After File Operations (Plex Verification)
```bash
my-plex --update-cache --force-plexdata
```
- Verifies all Plex files still exist
- Detects moved/deleted files
- Updates changed Plex metadata
- **Does NOT** recollect video file metadata

---

### First-Time Metadata Collection
```bash
my-plex --update-cache --force-metadata
```
- Keeps existing Plex data
- Collects video file metadata for ALL files
- Sets up broken file detection
- **Recommended for initial metadata setup**

---

### Complete Rebuild
```bash
my-plex --update-cache --force
```
- Verifies ALL Plex files
- Collects ALL video file metadata
- Most thorough but slowest
- **Use sparingly - only when needed**

---

### From Scratch (Clean Slate)
```bash
my-plex --update-cache --from-scratch --force
```
- Deletes existing cache completely
- Rebuilds everything from zero
- Verifies all Plex data
- Collects all video file metadata
- **Nuclear option - rarely needed**

---

## Performance Comparison

For a library with ~14,500 video files:

| Command | Time Estimate | Use Case |
|---------|---------------|----------|
| `--update-cache` | 1-2 minutes | Regular updates (recommended) |
| `--update-cache --force-plexdata` | 5-10 minutes | After file operations |
| `--update-cache --force-metadata` | 15-30 minutes | Initial metadata setup |
| `--update-cache --force` | 20-40 minutes | Complete verification |
| `--update-cache --from-scratch --force` | 25-45 minutes | Clean rebuild |

*Note: Times vary based on library size, network speed (SSH), and server load.*

---

## Decision Tree

**Start here**: Do you need to update the cache?

1. **Just checking for new files?**
   → `my-plex --update-cache`

2. **Moved/deleted files or suspect Plex is out of sync?**
   → `my-plex --update-cache --force-plexdata`

3. **Setting up broken file detection for first time?**
   → `my-plex --update-cache --force-metadata`

4. **Want to verify EVERYTHING?**
   → `my-plex --update-cache --force`

5. **Cache corrupted or want to start fresh?**
   → `my-plex --update-cache --from-scratch --force`

---

## Technical Notes

### Backwards Compatibility

The old `FORCE_REBUILD` variable still exists internally and maps to `FORCE_PLEXDATA`. This ensures existing code and configs continue to work.

### Metadata Collection Details

**MKV files**: Reads first 4KB of file to extract EBML duration header
**MP4/M4V/AVI files**: Uses `ffprobe` to read container duration
**Remote files**: Currently skipped (SSH implementation pending)

### Incremental Metadata Logic

During normal `--update-cache`, metadata is collected:
- ✓ For NEW files (no metadata exists)
- ✓ For files with CHANGED filesize (likely modified)
- ✗ For existing files with unchanged filesize (already cached)

With `--force-metadata`, ALL files get metadata collected regardless of cache state.

---

## Examples with Explanations

### Example 1: Daily Maintenance
```bash
my-plex --update-cache
```
**Why**: Quick check for new files added to libraries. Takes 1-2 minutes.

---

### Example 2: After Moving Movies
```bash
# You moved 50 movies from ,unsorted to movies.en
my-plex --update-cache --force-plexdata
```
**Why**: Plex needs to verify file locations changed. Takes 5-10 minutes.

---

### Example 3: Setting Up Broken File Detection
```bash
# First time enabling metadata-based broken file detection
my-plex --update-cache --force-metadata
```
**Why**: Needs to collect container durations for all 14k files. Takes 15-30 minutes. Only needed once.

---

### Example 4: After Server Crash
```bash
# Server crashed, Plex database might be inconsistent
my-plex --update-cache --force
```
**Why**: Verifies both Plex database AND file metadata integrity. Takes 20-40 minutes.

---

## Flag Combinations

### Valid Combinations
- ✓ `--update-cache` (alone)
- ✓ `--update-cache --force-plexdata`
- ✓ `--update-cache --force-metadata`
- ✓ `--update-cache --force` (triggers both above)
- ✓ `--update-cache --from-scratch` (clears cache first)
- ✓ `--update-cache --from-scratch --force` (complete clean rebuild)

### Invalid/Redundant Combinations
- ✗ `--force-plexdata` without `--update-cache` (no effect)
- ✗ `--force-metadata` without `--update-cache` (no effect)
- ⚠ `--force --force-plexdata` (redundant, `--force` already includes it)
- ⚠ `--force --force-metadata` (redundant, `--force` already includes it)

---

## Monitoring During Rebuild

Always monitor three sources during cache operations:

1. **DISK**: File system state (moves, deletes, renames)
2. **PLEX**: Plex server database state
3. **CACHE**: Local cache file state

Use `--info` to check cache vs Plex timestamps before/after operations.

---

## Summary

- Use `--update-cache` for **regular updates** (fastest)
- Use `--force-plexdata` for **Plex verification** (medium)
- Use `--force-metadata` for **video metadata** (slow)
- Use `--force` for **complete verification** (slowest)
- Use `--from-scratch` for **clean rebuild** (nuclear)

**Remember**: More comprehensive = slower. Choose the minimum needed for your situation.
