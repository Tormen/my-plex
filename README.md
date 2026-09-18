# my-plex

Still under heavy development, but already somewhat usable.

The swiss-army knife for PLEX - a comprehensive Plex media management tool with direct database access and PLEX API access, intelligent caching for offline usage.

**25,000+ lines of Python** | **750+ tests** | **Offline-capable** | **60x faster than Plex API**

## Features

### Library & Media Management
- **List libraries** (`--list`, `--libraries`) with supported/unsupported status
- **List media** across all libraries with flexible filtering (by type, language, watch status, labels)
- **Filter tokens** — intuitive shorthand: `watched:no rating>7 genre` (bare field names add display columns without filtering)
- **Title search** — bare words search movies/series by title AND filepath: `my-plex tagesschau` (episode title search with `ep:word`). Free text is normalized via `CLI_TEXT_NORMALIZE_REGEX` (default: collapse non-alphanumerics to spaces) on both sides, so `emily.in.paris` matches "Emily in Paris" and `who's-that-girl` matches "Who's That Girl". When the search resolves to a single Series (every hit traces to one series, no stray rows), my-plex renders the multi-line detail view — identical to `my-plex Series:NNN`. Use `-V` to keep the table view.
- **Column hiding** — `-field` removes columns: `my-plex lib1 -file` hides FILEPATH
- **Filter + hide** — `-field:value` filters AND hides the column: `my-plex lib1 -genre:comedy` filters by comedy without showing the GENRE column
- **External ID URLs** — bare `imdb` / `tmdb` / `tvdb` tokens add a clickable URL column to each row (episodes inherit IDs from their parent series)
- **Per-library audio-language stats** — `--update-cache` builds a per-library `{lang: [keys]}` index, surfaced as a `LANGUAGES` column in `--list-libraries` (e.g. `en* 79%, fr 15%, de 2% [MULTI]`). Mark a library multi-language by adding `('lib', 'MULTI')` to `AUTO_RESOLVE_AUDIO_LANGUAGE_BY_LIBRARY` — `--list` then auto-shows the AUDIO column for results from that library, and `--no-audio-language --resolve` always prompts (no autoresolve)
- **Movies-only result layout** — when a `--list` result set is all movies, my-plex auto-replaces FILEPATH with YEAR + TITLE + ORIGINAL-TITLE columns. Use bare `path` / `filepath` / `file` token to bring FILEPATH back
- **End-of-filters marker** — `--` makes every following token a literal title search, bypassing filter heuristics: `my-plex -- imdb` searches for the word "imdb" in titles
- **DEFAULT_SCOPE** — config variable for default filters applied to all listings (e.g. `watched:no`)
- **Smart rollup** — episodes with identical display values collapse into Season/Series rows, with matched/total counts when filters are active
- **Supported libraries** — Personal Media libraries (agent=none) are automatically excluded from all operations
- **Duplicate detection** with intelligent classification (exact duplicates vs re-encodes vs true multi-version)
- **Problem scanner** (`--problems`) — driven by the `PROBLEM_CATEGORIES_REGISTRY` single source of truth (v2.69+). Runs every registered category in one pass; counts cached after every `--update-cache`. Use `my-plex --help problems` for the auto-generated category list, or `my-plex --print-problem-categories-md` to regenerate the table below.
  - **Current categories** (auto-generated — regenerate by running `my-plex --print-problem-categories-md`):

    | # | Category | CLI flag | TSV-only? | Description | Fix |
    |---|----------|----------|-----------|-------------|-----|
    | 1 | `broken` | `--broken` |  | Broken/truncated media files (probe error, low bitrate, file not found) | `my-plex --broken --resolve` |
    | 2 | `excess_versions` | `--excess-versions` |  | Entries with 3+ file versions (likely accidental duplicate imports) | `my-plex --excess-versions 3` |
    | 3 | `tsv` | — | ✓ | Episode-scrape failures: no external IDs, misidentified series, truncated titles | Inspect `episodes.err`; re-run with corrected source |
    | 4 | `unmatched` | `--unmatched` |  | Items not matched by Plex metadata agent (`local://` guid; needs Fix Match) | `my-plex --unmatched --resolve [--auto]` |
    | 5 | `no_audio_language` | `--no-audio-language` |  | Items whose audio tracks have no language tag set in Plex | `my-plex --no-audio-language --resolve` |
    | 6 | `unsorted` | `--unsorted` |  | Series with episodes directly in series dir (no season subdirectories) | `my-plex --unsorted --fix` |
    | 7 | `mismatched` | `--mismatched` |  | Title-vs-directory mismatches + multi-version Plex grouping mismatches | `my-plex --mismatched --resolve [--auto]` |
    | 8 | `junk` | `--junk` |  | Sample / RARBG promo / tiny-placeholder files bundled with healthy media | `my-plex --junk --resolve` |
    | 9 | `multi_movie_folder` | `--multi-movie-folder` |  | Wrappers hosting ≥2 distinct Plex Movies (Plex expects 1 Movie per folder) | Split into per-movie wrappers (manual or `my-plex --mv`) |
    | 10 | `library_language_mismatch` | `--library-language-mismatch` |  | Items whose audio language disagrees with their library's configured language | Move to the correct language library (manual or `my-plex --mv`) |
    | 11 | `bad_structure` | `--bad-structure` |  | Media files nested too deeply (Movie >1 dir below lib root, Episode >2) | `my-plex --bad-structure --resolve` |
    | 12 | `misplaced` | `--misplaced` (alias: `--wrong-library`) |  | Items whose content type does not fit their library (Series-of-Movies, Movie-with-SxxEyy) | `my-plex --misplaced --resolve` |
    | 13 | `numbering_issues` | `--episode-numbering-issues` | ✓ | Plex vs scraped numbering disagreement (e.g. Plex E101 vs scraped E01) | `my-plex --renumber --plex` |
    | 14 | `reencode` | `--reencode` |  | Media files whose codecs cannot stream-copy (requires re-encoding) | `my-plex --reencode` |
    | 15 | `remux` | `--remux` |  | Media files whose container is outdated but streams can be copied unchanged | `my-plex --remux` |
    | 16 | `missing_episodes` | `--missing` |  | Episodes present in scraped data but missing from Plex / disk | `my-plex --missing <SERIES>` |
    | 17 | `renumber` | `--renumber` | ✓ | Episodes whose S0xE0x in filename disagrees with scraped data (renaming fixes) | `my-plex --renumber --fix` |
    | 18 | `renumber_nodata` | — | ✓ | Episodes without scraped data — can't verify numbering | `my-plex --renumber -V` |
    | 19 | `renumber_season` | — | ✓ | S-number in filename doesn't match the parent season directory | `my-plex --renumber -V` |
    | 20 | `renumber_abs` | — | ✓ | Plex's episode ordering disagrees with scraped data | `my-plex --renumber -V` |
    | 21 | `unrecognized` | `--unrecognized` |  | Top-level entries in Plex DB that the cache cannot resolve | `my-plex --unrecognized` |

  - **Disabling categories** — add unwanted names to `PROBLEM_CATEGORIES_DISABLED` in `~/.my-plex.conf`, e.g.
    ```python
    PROBLEM_CATEGORIES_DISABLED = ['remux', 'junk']
    ```
  - **Interactive resolve flows** — every `--resolve` writes a JSON log to `~/.my-plex/logs/<cmd>_<TS>.json`. Notable:
    - **`--mismatched --resolve [--auto] [--try]`** (v2.68) — for each title-vs-directory mismatched Series, queries Plex's own metadata agent. Picker exposes: `1-N` pick, `t<title>` re-query Plex agent, `T<title>` re-query online engines, `id:tvdb:NNNNN | id:tmdb:NNNNN | id:imdb:ttNNNNN` to force-match an external ID. In `--auto`, falls through Plex agent → TMDB/TVDB/fernsehserien.de online lookup → synthesizes a `searchResult` from the candidate's external ID → `series.fixMatch()` — without operator intervention when conf ≥ `UNMATCHED_RESOLVE_AUTO_CONFIDENCE_PCT` (default 90%).
    - **`--unmatched --resolve [--auto] [--try]`** — renames wrappers to canonical title + year, then re-triggers Plex's matcher.
    - **`--bad-structure --resolve [--auto]`** — flattens nested wrappers.
    - **`--misplaced --resolve`** *(v2.69, in progress)* — disk-level transition between media types (Series-of-Movies → Movie library; Movie-with-SxxEyy → Series library).
- **Managed-orphan cleanup during `--update-cache`** (v3) — every `--update-cache` run prunes the sidecar files it owns:
  - `disk_map.json` entries whose filepath no longer exists are removed.
  - `episodes.err` files in series directories that have vanished are trashed (`move_to_trash`, recoverable via Finder).
  - Summary block (`>>> --update-cache: managed-orphan housekeeping`) only printed when something was pruned. Use `-V` to see the full filepath list.
  - Files outside `--update-cache`'s ownership (state-preservation sidecars, raw sidecar files in library roots, empty directories) are NOT touched here — those are `--orphaned`'s job.
- **Orphan detection** (`--orphaned`, v3) — housekeeping pass over library roots + the my-plex state directory. Three independent sub-categories; default = all three:
  - `--orphaned --files` — sidecar files (`.nfo`, `.srt`, `.jpg`, `.png`, …) whose video sibling has vanished. 2-character language suffixes are stripped from the candidate stem when matching (`movie.de.srt` is owned by `movie.mkv`). Cover-art files (`cover.jpg`, `folder.jpg`, `poster.jpg`, `fanart.jpg`, `banner.jpg`) are kept while any video lives in the same directory.
  - `--orphaned --dirs` — empty directories anywhere under the library roots (BSD-compatible `find -mindepth 1 -type d -empty`). `--resolve` rmdirs them.
  - `--orphaned --my-plex` — stale `~/.my-plex/state-preservation/<rk>.json` sidecars whose cache key no longer exists in `OBJ_BY_ID`.
  - `--orphaned --resolve [--try] [--yes]` trashes files (`move_to_trash`) and rmdirs empty dirs, looping until idle so a dir emptied by sidecar trashing is caught in the next pass. JSON log at `~/.my-plex/logs/orphaned_<TS>.json`.
  - Scope-aware: `my-plex MOVIE_LIB --orphaned` narrows the walk to one library. See `my-plex --help orphaned`.
- **Canonical naming** (`--naming`, v3) — template-driven renames from the `NAMING_RULES` CONF dict (opt-in; empty by default):
  - Per object type (`MOVIE_FILE` / `MOVIE_DIR` / `EPISODE_FILE` / `SEASON_DIR` / `SERIES_DIR`) a rule defines a `template` of cache-field variables — `'{TITLE.lower.nodiacritic.dots} [{YEAR}]'` — plus optional sed-style `transforms` (regex/replacement pairs with backrefs).
  - Modifiers chain with dots, applied left-to-right: `.lower` `.upper` `.dots` `.nodiacritic` `.nopunct` `.alnum` `.pad2`/`.pad3`.
  - Canonical name shape: `<templated base> [user label …] [DPM marker …]<.ext>` — user `[label]` tokens and sidecar-owned DPM markers are preserved (configurable via `preserve_labels` / `preserve_markers` / `preserve_ext`).
  - `--naming [SCOPE]` previews (read-only, KEY-first table); `--naming --resolve [--try] [--yes]` applies — conflicts abort before any rename, sibling files (`.nfo`, `.srt`, …) follow automatically, and the cache is updated in-process. JSON log at `~/.my-plex/logs/naming_<TS>.json`.
  - Every applied rename records the FIRST original name as `naming_original` in `disk_map.json`; `--naming --revert [SCOPE]` restores it even across multiple `--naming` runs.
  - Items whose template references an empty/missing field are skipped (listed with `-V`), never crashed. See `my-plex --help naming`.
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
- **Sort new recordings** (`--sort`; legacy synonym `--sort-new`; or `--unsorted --fix`) — organizes unsorted recordings across **all libraries** (series-type AND movie-type)
  - **`--sort --redo` / `--sort-new --redo` (v2.67+)** — strip existing `SxxEyy` markers (regex configurable via `SORT_NEW_SXXEYY_REGEX`) from filenames in scope and re-sort from scratch. Use after a `--mismatched --resolve` re-binds a series to a new metadata source.
  - **Season-token wrapper consolidation (v3)** — phase 0 of every `--sort-new` run. Release wrappers whose directory name carries a season token (`<series>.s01.<release junk>`, regex configurable via `SORT_NEW_SEASON_TOKEN_REGEX`) are consolidated into `<library_root>/<series>/s<NN>/`: the wrapper name is cut at the token (part before = canonical series name, digits = season). Flat wrappers (episodes at depth 1) and layered ones (already holding an `s<NN>/` subdir — layer stripped) are both handled; several wrappers of one series merge into one series dir. Moves never clobber (`mv -n`), stale fake-series artifacts (`episodes.tsv*`, `episodes.err`) are trashed, the emptied wrapper is `rmdir`'d, cache + `disk_map.json` update in-process, JSON log written. A real series whose title merely contains `.sNN` is left alone (layout guard). Run `--scan` afterwards so Plex re-catalogues.
  - Series libraries: matches file dates to episode data, renames with S##E## prefix
  - Movie libraries: creates directories for bare video files, moves sibling files (.srt, .nfo)
  - **`SORT_NEW_SCAN_LOCATIONS`** (default `['.', 's0x', ',new']`) — list of paths to scan inside each series dir (series libs) or each library root (movie libs). Each entry is either a string path or `(path, 'touch')` / `(path, 'touch-all')` — `touch` leaves a zero-byte placeholder with the moved file's name so external auto-downloaders see "already taken"; `touch-all` extends that to sidecars too.
  - Scoped: `my-plex lib4 --sort-new --dry-run` or `my-plex 'Tagesschau' --unsorted --fix`
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
  - `--plex-disk-sync` / `--sync` — bidirectional: disk→plex first, then plex→disk
  - **Invariant (v2.69):** sync touches FILENAMES / PATHNAMES only — never the bytes of your media files. Container audio-track tags, codecs, container format are explicitly OUT of scope. For file mutation, use the explicit commands: `--no-audio-language --resolve` (rewrites container audio-track tags via mp4box / mkvpropedit), `--remux` (repackage container, no re-encode), `--reencode` (re-encode streams).
  - `--remux` — stream-copy outdated-container files (e.g. `.avi`) to `.mkv`, attaching the resolved audio language as track metadata. Default: PREVIEW only; `--yes` commits. Combine with `--no-audio-language` to bulk-fix files where Plex has no audio language yet (e.g. German DVR recordings with `[TVOON]` filename hints).
  - **`layout:` scope token** (v1.20) — orthogonal to `type:`. Where `type:` filters by what Plex catalogued an item as, `layout:` filters by what the FILESYSTEM thinks each top-level library entry looks like (its on-disk shape). Surfaces mis-classification: `layout:movie`, `layout:series`, `layout:season`, `layout:episode`. First call builds an in-memory classification index via ONE bulk `find -maxdepth 2` per library; subsequent lookups O(1). Use with `--mv-to` to relocate mis-shaped content: e.g. `my-plex --mv-to lib6 lib2 layout:series` moves series-shaped folders out of a Movie library. When `layout:` returns 0 items, the folder isn't in Plex's index at all — use `--unrecognized` for that case.
  - **PURE `type:` semantics** (v1.20) — `type:series` returns ONLY Series Plex objects, `type:season` ONLY Seasons, `type:episode` ONLY Episodes, `type:movie` ONLY Movies. No auto-expansion. For action commands needing file-owners, use `type:episode` (or pass an explicit `Series:NNN`/`Season:NNN` cache key, which auto-expands as before).
  - **`--mv-to` / `--move-to`** (v1.20 — renamed from `--mv` / `--move`): explicit `-to` suffix makes destination semantics unambiguous.
  - `--unrecognized` / `--alien` (v1.11) — list top-level entries in each library rootpath that Plex DB does NOT have a `media_part` for. Catches download leftovers (`.tmp`/`.part`), folders Plex couldn't match (wrong agent, name confusion), or content dropped at a library root that Plex never indexed. Particularly useful in Movie libraries that accidentally contain Series-shaped folders (`show.s01e0X.*` patterns) which Plex's movie matcher rejected. Detection rule: Plex DB authoritative (queries `media_parts.file`). Also integrated into `--problems`. Synonym: `--alien`.
  - **SCOPE is universal** (v1.9 → v2.0) — there is ONE scope syntax in my-plex, used identically by every SCOPE-taking command (`--list`, `--mv-to`, `--remux`, `--plex2disk`, `--disk2plex`, `--rename`, `--renumber`, `--reencode`, `--broken`, `--unmatched`, `--unsorted`, `--mismatched`, `--missing`, `--problems`, `--original-languages`, `--unrecognized` — and any future verb). SCOPE can be a library name, cache key, full filepath, title search, or filter expression (`type:series`, `layout:series`, `lang:fr`, `country:france`, `original_lang:de`, `year>2020`, `bitrate>2`, etc.). Multiple tokens **AND-combine**: e.g. `my-plex --mv-to lib4 lib1 original_lang:fr` resolves to "every originally-French movie currently in `lib1`" and moves them. Write your query once, plug it into the verb. See `my-plex --help scope`.
  - `--original-languages` (v1.8) — backfill the `original_language` field on cached Movies / Series from the TMDB API. Required to power the new `original_lang:` / `originallang:` / `original_language:` filter tokens, which distinguish "in French audio (possibly dubbed)" from "originally in French" — e.g. an Italian movie dubbed to French has `audio_languages=['fr']` but `original_language='it'`. Companion token `country:` (no backfill needed; data already in cache) accepts ISO 3166-1 alpha-2 codes (`country:fr`) AND English names (`country:france`, `country:united_states`). Language tokens accept ISO 639-1 codes (`original_lang:fr`) AND English names (`originallang:french`). Use `--help original-languages` for details.
  - `--mv` / `--move` / `--mv-to` / `--move-to` — move Plex media to another library. Usage: `--mv DEST_LIB [SCOPE]`. Accepts every Plex type in the cache: **whole Series** (`Series:NNN` → expands to all seasons + episodes), **whole Season** (`Season:NNN` → expands to all its episodes), **single Episode** (`Episode:NNN`), **Movie** (`Movie:NNN` — all versions), **whole library** (library name), title search, full filepath, or omitted = global (every Movie / Episode currently in another library). Sibling files (`.nfo`, `.srt`, posters, …) move alongside the main video files. Duplicate detection in DEST_LIB by (Plex title + originalTitle + year) — interactive prompt with `[s]kip / [o]verwrite / [S]kip-all / [O]verwrite-all / [q]uit`, or `--force` to auto-overwrite. Default: PREVIEW only; `--yes` commits. After moving, triggers Plex library scans on source AND destination so Plex re-indexes the files (Plex assigns new IDs for cross-library moves; run `--update-cache` afterwards to repopulate cache).
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
my-plex --update-cache --force-plex

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
my-plex --mismatched
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
my-plex lib6 --missing

# Sort new recordings (preview)
my-plex --sort-new --dry-run                    # shortcut for --unsorted --fix
my-plex --unsorted --fix --dry-run              # equivalent
my-plex 'Tagesschau' --unsorted --fix --try   # sort one series

# Sort movies in a specific library
my-plex lib4 --sort-new --dry-run

# Sync Plex metadata to disk markers
my-plex --plex2disk --dry-run

# Sync disk markers back to Plex
my-plex --disk2plex --dry-run
```

## Configuration

Configuration file (Python syntax, loaded via `exec()`). Searched in order,
first hit wins:

1. `/LINKS/default/my-plex.conf` — primary system-wide location
2. `~/.my-plex/my-plex.conf`
3. `~/.my-plex.conf` — legacy, still honoured
4. `/etc/my-plex.conf`
5. `/usr/local/etc/my-plex.conf`

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
MISSING_EPISODES_SOURCE = {'lib5': 'fernsehserien.de', 'lib6': 'tvdb'}

# Optional: Episode renumbering filename pattern (for --renumber --fix)
RENUMBER_NAME_PATTERN = '{S0XE0X} {TITLE}'

# Optional: Duplicate detection — ignore cross-library duplicates
DUPLICATES_IGNORE_LIBRARY_COMBINATIONS = [['lib2', 'lib3', 'lib4']]

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

## Version and release

```bash
my-plex --version              # v2.69 (build 1a2b3c4d5e6f, from commit 325612a)
my-plex --stamp-version        # analyze: what would be stamped
my-plex --stamp-version go     # record HEAD in SCRIPT_COMMIT, amend HEAD
```

- The **build id** is a hash of the file itself, so two installs that differ
  never report the same `--version`; compare installs by diffing it.
- `SCRIPT_COMMIT` names the commit the file was released from. It lags HEAD
  by one, because the stamp amends HEAD and a commit cannot contain its own sha.
- Release order: commit, `--stamp-version go`, push. The stamp refuses a
  commit that is already pushed, anything staged, or uncommitted edits to
  `my-plex.py` itself.
- A tagged version number is never reused: once HEAD has moved past the tag
  for `SCRIPT_VERSION`, bump it (`my-plex --test version` enforces this).

## Contributing

Open Source — contributions are welcome.

## License

MIT
