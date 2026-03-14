# my-plex

The swiss-army knife for PLEX - a comprehensive Plex media management tool with direct database access and PLEX API access, intelligent caching for offline usage.

**17,000+ lines of Python** | **370 tests** | **Offline-capable** | **60x faster than Plex API**

## Features

### Library & Media Management
- **List media** across all libraries with flexible filtering (by type, language, watch status, labels)
- **Duplicate detection** with intelligent classification (exact duplicates vs re-encodes vs true multi-version)
- **Broken file detection** — finds truncated/corrupt media by comparing container vs Plex duration
- **Excess version detection** — finds entries with too many file versions
- **Problem scanner** — runs all checks in one pass (`--problems`)
- **Interactive resolution** — guided duplicate/language cleanup with undo support

### Episode Management
- **Missing episode detection** (`--missing`) — compares what you have vs what should exist
- **Multi-source episode data**:
  - **TVDB** (API, most complete for TV, free key)
  - **TMDB** (API, good fallback, free key)
  - **fernsehserien.de** (web scraping, German TV, no key needed)
- **Auto-detection** of episode source from library agent + language
- **Sort new recordings** (`--sort-new`) — organizes unsorted recordings into season directories
- **Absolute numbering** detection (e.g. filename "101" → S01E01)

### Cache Architecture
- **Three-tier data access**: Cache → Plex DB → Plex API
- **Cache-first design** — all read commands work offline from pickle cache
- **Direct database access** via SSH — 60x faster than Plex API for bulk operations
- **Incremental updates** — only refreshes changed libraries
- **Checkpoint/resume** — cache updates survive interruptions

### Search & Info
- **Flexible search** (`--info`) by Plex ID, cache key, filepath, or partial title
- **Detailed item info** with metadata, file versions, external IDs, ratings
- **System overview** — cache status, server stats, library summary

### Operations
- **Library scanning** — trigger Plex filesystem scans, wait for completion
- **File operations** — trash, rename, move with automatic alternative path resolution
- **Label management** — add/remove labels
- **Watch status** — mark watched/unwatched, set view offset
- **Playlist management** — create, modify, delete playlists

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

# List all media
my-plex --list

# Show system info
my-plex --info

# Search for a title
my-plex --info 'boston legal'

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

# Override episode source
my-plex 'friends' --missing --source tvdb

# Sort new recordings
my-plex --sort-new --dry-run
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
│ --search │           │                               │
│ (offline)│ (via SSH) │ (HTTP API)                    │
└──────────┴───────────┴───────────────────────────────┘
```

## Testing

```bash
# Run all 370 tests
my-plex --test

# Or with unittest flags
my-plex --unittest -v
```

## Contributing

Open Source — contributions are welcome.

## License

MIT
