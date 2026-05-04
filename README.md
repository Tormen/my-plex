# my-plex

Still under heavy development, but already somewhat usable.

The swiss-army knife for PLEX - a comprehensive Plex media management tool with direct database access and PLEX API access, intelligent caching for offline usage.

**25,000+ lines of Python** | **750+ tests** | **Offline-capable** | **60x faster than Plex API**

## Features

### Library & Media Management
- **List libraries** (`--list`, `--libraries`) with supported/unsupported status
- **List media** across all libraries with flexible filtering (by type, language, watch status, labels)
- **Filter tokens** — intuitive shorthand: `watched:no rating>7 genre` (bare field names add display columns without filtering)
- **Title search** — bare words search movies/series by title: `my-plex tagesschau` (episode title search with `ep:word`)
- **Column hiding** — `-field` removes columns: `my-plex ,unsorted -file` hides FILEPATH
- **Filter + hide** — `-field:value` filters AND hides the column: `my-plex ,unsorted -genre:comedy` filters by comedy without showing the GENRE column
- **External ID URLs** — bare `imdb` / `tmdb` / `tvdb` tokens add a clickable URL column to each row (episodes inherit IDs from their parent series)
- **Per-library audio-language stats** — `--update-cache` builds a per-library `{lang: [keys]}` index, surfaced as a `LANGUAGES` column in `--list-libraries` (e.g. `en* 79%, fr 15%, de 2% [MULTI]`). Mark a library multi-language by adding `('lib', 'MULTI')` to `AUTO_RESOLVE_AUDIO_LANGUAGE_BY_LIBRARY` — `--list` then auto-shows the AUDIO column for results from that library, and `--no-audio-language --resolve` always prompts (no autoresolve)
- **Movies-only result layout** — when a `--list` result set is all movies, my-plex auto-replaces FILEPATH with YEAR + TITLE + ORIGINAL-TITLE columns. Use bare `path` / `filepath` / `file` token to bring FILEPATH back
- **End-of-filters marker** — `--` makes every following token a literal title search, bypassing filter heuristics: `my-plex -- imdb` searches for the word "imdb" in titles
- **DEFAULT_SCOPE** — config variable for default filters applied to all listings (e.g. `watched:no`)
- **Smart rollup** — episodes with identical display values collapse into Season/Series rows, with matched/total counts when filters are active
- **Supported libraries** — Personal Media libraries (agent=none) are automatically excluded from all operations
- **Duplicate detection** with intelligent classification (exact duplicates vs re-encodes vs true multi-version)
- **Problem scanner** (`--problems`) — runs all 12 checks in one pass, counts stored in cache after every `--update-cache`:
  - **Broken files** (`--broken`) — truncated/corrupt media detected by comparing container duration vs Plex duration and ffmpeg probe
  - **Excess versions** (`--excess-versions`) — entries with 3+ file versions (accidental duplicates, failed moves)
  - **Episode data failures** (`--problems --tsv`) — shows that could not be matched to an episode source (no external IDs, scrape failed, source not found, etc.)
  - **Unmatched items** (`--unmatched`) — media with `local://` GUID: never matched by any Plex metadata agent, or matched but missing external IDs (TMDB/TVDB) needed for episode scraping
  - **Unsorted series** (`--unsorted`) — series with episodes directly in the series directory instead of season subdirectories; fix with `--unsorted --fix`
  - **Potential mismatches** (`--mismatch`) — items where the Plex title doesn't match the filesystem directory name (likely wrong match in Plex)
  - **Plex numbering issues** (`--renumber --plex`) — shows where Plex and the scraped source (TMDB/TVDB/fernsehserien.de) disagree on season/episode numbers
  - **Re-encode candidates** (`--reencode`) — high-bitrate media above configurable threshold; rolls up episodes → season → series; labels files on disk with `[reencode]` markers
  - **Renumber candidates** (`--renumber`) — episodes whose filename S0xE0x disagrees with scraped data; fix with `--renumber --fix`
  - **Renumber: lack of data** — episodes without scraped data (can't determine correct numbering)
  - **Renumber: season mismatch** — S-number in filename doesn't match season directory
  - **Renumber: absolute numbering mismatch** — Plex's episode ordering disagrees with scraped data
- **On-disk file labels** — `[label]` markers embedded in filenames/directories, read during `--update-cache`, indexed for instant offline lookup
- **Interactive resolution** — guided duplicate/language cleanup with undo support

### Episode Management
- **Missing episode detection** (`--missing`) — compares what you have vs what should exist
- **Multi-source episode data** with automatic fallback chain:
  - **TVDB** (API, most complete for TV, free key)
  - **TMDB** (API, good fallback, free key)
  - **fernsehserien.de** (web scraping, German TV, no key needed)
  - Automatic fallback: if primary source returns 0 episodes, tries next source
- **Auto-detection** of episode source from library agent + language
- **Sort new recordings** (`--unsorted --fix` or `--sort-new`) — organizes unsorted recordings into season directories
  - Series libraries: matches file dates to episode data, renames with S##E## prefix
  - Movie libraries: creates directories for bare video files, moves sibling files (.srt, .nfo)
  - Scoped: `my-plex movies.fr --sort-new --dry-run` or `my-plex 'Tagesschau' --unsorted --fix`
- **Absolute numbering** detection (e.g. filename "101" → S01E01)
- **Renumber episodes** (`--renumber`) — detect and fix incorrect S0xE0x numbering in filenames
  - Scraped data (TMDB/TVDB/fernsehserien.de) is the ground truth for correct numbering
  - `--renumber --fix` renames files using `RENUMBER_NAME_PATTERN` config
  - `--renumber --fix --try` for dry-run preview
  - `--renumber --plex` shows Plex metadata numbering issues (replaces `--episode-numbering-issues`)
  - Scoped: library, series, season, or single episode

### Disk Map (Metadata Markers)
- **Bidirectional sync** between Plex metadata and filesystem markers
  - `--plex2disk` — sync Plex metadata → disk (add `[marker]` tags to filenames/directories)
  - `--disk2plex` — sync disk markers → Plex (push watched status, ratings, labels back)
  - `--plex-disk-sync` — bidirectional: disk→plex first, then plex→disk
- **4 scopes**: media files, movie directories, series directories, season directories
- **Python expressions** for marker values — fully configurable, no hardcoded labels
- **Merge strategies**: `newer` (compare timestamps), `plex` (Plex wins), `disk` (disk wins)
- **Legacy migration** — automatically converts old `[vu@TIMESTAMP]` markers to new system
- **Sidecar tracking** — JSON file tracks which markers were applied to each file/directory

### Cache Architecture
- **Three-tier data access**: Cache → Plex DB → Plex API
- **Cache-first design** — all read commands work offline from pickle cache
- **Direct database access** via SSH — 60x faster than Plex API for bulk operations
- **Incremental updates** — only refreshes changed libraries
- **Checkpoint/resume** — cache updates survive interruptions
- **Library locations cached** — root paths stored for offline directory operations

### Search & Info
- **Flexible search** (`--info`) by Plex ID, cache key, filepath, or partial title
- **Filepath fallback** — when title search fails, searches directory names (catches Plex mismatches)
- **Detailed item info** with metadata, file versions, external IDs, ratings
- **System overview** — cache status, server stats, library summary

### Operations
- **Library scanning** (`--scan`) — trigger Plex filesystem scans, wait for completion
- **Configurable scan behavior** — `AUTO_SCAN_PLEX_LIBRARIES_ON_UPDATE_CACHE` controls whether `--update-cache` auto-scans
- **File operations** — trash, rename, move with automatic alternative path resolution
- **Label management** — add/remove labels with scope support (single item, title, or entire library)
- **Watch status** — mark watched/unwatched, set view offset
- **Playlist management** — create, modify, delete playlists

### Remote Operation
- **SSH-transparent** — reads and writes episode data on the Plex server via SSH
- **No mount required** — works without mounted volumes (SSH fallback for all file I/O)
- **Path resolution** — automatic translation between server and local paths via `ALTERNATIVE_ROOTPATHS`

## Installation

```bash
# Clone and add to PATH
git clone https://github.com/Tormen/my-plex.git
ln -s "$(pwd)/my-plex/my-plex" /usr/local/bin/my-plex   # or anywhere in your PATH

# Configure
my-plex --create-config ~/.my-plex.conf      # Write default config to file
# Or: my-plex --create-config > ~/.my-plex.conf   # Same via stdout
# Edit ~/.my-plex.conf with your Plex DB path and SSH host
# Inspect the active config any time:  my-plex --config
```

That's it. On first run, the `my-plex` shell wrapper automatically:
- Creates a Python virtualenv (`~/.python.venv/my-plex/`)
- Installs all dependencies (`plexapi`, `readchar`)
- Sets up zsh tab-completion

### Requirements
- Python 3.10+ (uses `match/case`)
- `virtualenv` (for automatic venv setup)
- SSH access to the Plex server (for database and file operations)
- SQLite3 on the Plex server

## Quick Start

```bash
# First time: build the cache (reads entire Plex DB, takes ~1 minute)
my-plex --update-cache --from-scratch

# List all libraries (with supported status)
my-plex --list

# Show detailed library info
my-plex --libraries

# Search for a title
my-plex --info 'Tagesschau'

# Search by directory name (when Plex title doesn't match)
my-plex --info 'die millionenshow'

# Find duplicates
my-plex --duplicates

# Find broken files
my-plex --broken

# Run all 12 problem checks in one pass
my-plex --problems

# Show full details for each check
my-plex --problems -V

# Run individual checks
my-plex --broken
my-plex --excess-versions 3
my-plex --unmatched
my-plex --unsorted
my-plex --mismatch
my-plex --renumber --plex          # Plex metadata numbering issues
my-plex --reencode
my-plex --renumber
my-plex --problems --tsv

# Scope any check to a specific item
my-plex Series:5191 --problems      # All checks for one series
my-plex Series:5191 --broken        # Broken files for one series
my-plex 'Tagesschau' --unmatched # Check a specific title

# Detect and fix incorrect episode numbering (preview)
my-plex --renumber --fix --try

# Fix numbering for a specific show
my-plex Series:5191 --renumber --fix --try

# Missing episodes for a series
my-plex --missing 'Tagesschau'

# Missing episodes for all shows in a library
my-plex series.en --missing

# Sort new recordings (preview)
my-plex --sort-new --dry-run                    # shortcut for --unsorted --fix
my-plex --unsorted --fix --dry-run              # equivalent
my-plex 'Tagesschau' --unsorted --fix --try   # sort one series

# Sort movies in a specific library
my-plex movies.fr --sort-new --dry-run

# Sync Plex metadata to disk markers
my-plex --plex2disk --dry-run

# Sync disk markers back to Plex
my-plex --disk2plex --dry-run
```

## Configuration

Configuration file: `~/.my-plex.conf` (Python syntax, loaded via `exec()`)

```python
# Required: SSH host for Plex server
PLEX_DB_REMOTE_HOST = 'my-plex'

# Required: Path to Plex database on the server
PLEX_DB_PATH = '/path/to/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db'

# Optional: Alternative mount points (for local file access)
ALTERNATIVE_ROOTPATHS = [('/server/path/', '/local/mount/')]

# Optional: API keys for --missing episode sources
TVDB_API_KEY = 'your-tvdb-key'    # Free: https://thetvdb.com/dashboard
TMDB_API_KEY = 'your-tmdb-token'  # Free: https://www.themoviedb.org/settings/api

# Optional: Per-library episode source override
MISSING_EPISODES_SOURCE = {'series.de': 'fernsehserien.de', 'series.en': 'tvdb'}

# Optional: Episode renumbering filename pattern (for --renumber --fix)
RENUMBER_NAME_PATTERN = '{S0XE0X} {TITLE}'

# Optional: Duplicate detection — ignore cross-library duplicates
DUPLICATES_IGNORE_LIBRARY_COMBINATIONS = [['movies.de', 'movies.en', 'movies.fr']]

# Optional: Default filter scope (applied to all listing commands)
DEFAULT_SCOPE = 'watched:no'  # Only show unwatched items by default

# Optional: Unified disk ↔ Plex marker map (drives both --plex2disk and --disk2plex).
# One entry per Plex variable; each entry has scope, merge policy, and a
# `values` map of Plex-value → marker template + recognising regexes.
DISK_PLEX_MAP = {
    'AUDIO_LANG': {
        'scope': 'file',
        'merge': 'disk',  # filename is ground truth
        'values': {
            'de':      {'plex2disk': '[de]',
                        'disk2plex': [r'\[(de|german)\]', r'_TVOON_DE\.']},
            'fr':      {'plex2disk': '[fr]',
                        'disk2plex': [r'\[(fr|french)\]']},
            'en':      {'plex2disk': '[en]',
                        'disk2plex': [r'\[(en|english)\]']},
            'unknown': {},  # mute placeholder bucket
        },
    },
    'WATCHED': {
        'scope': ['file', 'movie_dir', 'series_dir', 'season_dir'],
        'merge': 'newer',  # most recent timestamp wins
        'values': {
            True: {
                'plex2disk': '[vu@{WATCHED_DATE}]',
                'disk2plex': [r'\[vu@(?P<WATCHED_DATE>\d{4}-\d{2}-\d{2})\]',
                              r'\[vu\]'],
            },
        },
    },
}
```

Use `my-plex --help <topic>` for detailed help on any command.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    my-plex CLI                        │
├──────────┬───────────┬───────────────────────────────┤
│  Cache   │  Plex DB  │          Plex API             │
│ (pickle) │ (SQLite)  │         (plexapi)             │
│          │           │                               │
│ --list   │ --update  │ --scan (lib.update)           │
│ --info   │   -cache  │ --rm (media.delete)           │
│ --broken │           │ --resolve (labels, ratings)   │
│ --missing│           │ --playlist (CRUD)             │
│ --plex2d.│           │ --disk2plex (push)            │
│ (offline)│ (via SSH) │ (HTTP API)                    │
└──────────┴───────────┴───────────────────────────────┘
```

## Testing

```bash
# List available test scopes
my-plex --test

# Run all tests
my-plex --test all

# Run tests for a specific scope
my-plex --test disk-map
my-plex --test commands
my-plex --test duplicates
my-plex --test renumber
my-plex --test rename

# Or with unittest flags
my-plex --unittest -v
```

## Contributing

Open Source — contributions are welcome.

## License

MIT
