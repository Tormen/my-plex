# my-plex

Still under heavy development, but already somewhat usable.

The swiss-army knife for PLEX - a comprehensive Plex media management tool with direct database access and PLEX API access, intelligent caching for offline usage.

**23,000+ lines of Python** | **630 tests** | **Offline-capable** | **60x faster than Plex API**

## Features

### Library & Media Management
- **List libraries** (`--list`, `--libraries`) with supported/unsupported status
- **List media** across all libraries with flexible filtering (by type, language, watch status, labels)
- **Supported libraries** — Personal Media libraries (agent=none) are automatically excluded from all operations
- **Duplicate detection** with intelligent classification (exact duplicates vs re-encodes vs true multi-version)
- **Broken file detection** — finds truncated/corrupt media by comparing container vs Plex duration
- **Potential mismatch detection** (`--potential-mismatch`) — finds items where Plex title doesn't match directory name
- **Excess version detection** — finds entries with too many file versions
- **Re-encode detection** (`--reencode`) — finds high-bitrate media (size/length ratio) and labels files on disk with `[reencode]` markers; rolls up episodes → season → series
- **On-disk file labels** — `[label]` markers embedded in filenames/directories, read during `--update-cache`, indexed for instant offline lookup
- **Problem scanner** — runs all checks in one pass (`--problems`)
- **Interactive resolution** — guided duplicate/language cleanup with undo support

### Episode Management
- **Missing episode detection** (`--missing`) — compares what you have vs what should exist
- **Multi-source episode data** with automatic fallback chain:
  - **TVDB** (API, most complete for TV, free key)
  - **TMDB** (API, good fallback, free key)
  - **fernsehserien.de** (web scraping, German TV, no key needed)
  - Automatic fallback: if primary source returns 0 episodes, tries next source
- **Auto-detection** of episode source from library agent + language
- **Sort new recordings** (`--sort-new`) — organizes unsorted recordings into season directories
  - Series libraries: matches file dates to episode data, renames with S##E## prefix
  - Movie libraries: creates directories for bare video files, moves sibling files (.srt, .nfo)
  - Target a specific library: `my-plex movies.fr --sort-new --dry-run`
- **Absolute numbering** detection (e.g. filename "101" → S01E01)

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
- **Label management** — add/remove labels
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
my-plex --config-file ~/.my-plex.conf --create
# Edit ~/.my-plex.conf with your Plex DB path and SSH host
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
my-plex --info 'boston legal'

# Search by directory name (when Plex title doesn't match)
my-plex --info 'die millionenshow'

# Find duplicates
my-plex --duplicates

# Find broken files
my-plex --broken

# Run all problem checks
my-plex --problems

# Missing episodes for a show
my-plex --missing 'boston legal'

# Missing episodes for all shows in a library
my-plex series.en --missing

# Sort new recordings (preview)
my-plex --sort-new --dry-run

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

# Optional: Duplicate detection — ignore cross-library duplicates
DUPLICATES_IGNORE_LIBRARY_COMBINATIONS = [['movies.de', 'movies.en', 'movies.fr']]

# Optional: Disk map markers (sync Plex metadata to filenames)
DISK_MAP = {'watched': "'vu@' + WATCHED_DATE if WATCHED else ''"}
DISK_MAP_MOVIE_DIR = {'watched': "'vu@' + WATCHED_DATE if WATCHED else ''"}
DISK_MAP_SERIES_DIR = {'watched': "'vu@' + WATCHED_DATE if WATCHED else ''"}
DISK_MAP_SEASON_DIR = {'watched': "'vu@' + WATCHED_DATE if WATCHED else ''"}
DISK_MAP_MERGE = {'watched': 'newer'}
DISK_MAP_PUSH = {'watched': 'WATCHED'}
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

# Run all 568 tests
my-plex --test all

# Run tests for a specific scope
my-plex --test disk-map
my-plex --test commands
my-plex --test duplicates

# Or with unittest flags
my-plex --unittest -v
```

## Contributing

Open Source — contributions are welcome.

## License

MIT
