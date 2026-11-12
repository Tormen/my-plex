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
    | 9 | `multi_movie_folder` | `--multi-movie-folder` |  | Wrappers hosting ≥2 distinct Plex Movies (Plex expects 1 Movie per folder) | Split into per-movie wrappers (manual or `my-plex --mv-to`) |
    | 10 | `library_language_mismatch` | `--library-language-mismatch` |  | Items whose audio language disagrees with their library's configured language | Move to the correct language library (manual or `my-plex --mv-to`) |
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
  - `--unrecognized` / `--alien` (v1.11) — list top-level entries in each library rootpath that Plex DB does NOT have a `media_part` for. Catches download leftovers (`.tmp`/`.part`), folders Plex couldn't match (wrong agent, name confusion), or content dropped at a library root that Plex never indexed. Particularly useful in Movie libraries that accidentally contain Series-shaped folders (`show.s01e0X.*` patterns) which Plex's movie matcher rejected. Detection rule: Plex DB authoritative (queries `media_parts.file`). Also integrated into `--problems`. Synonym: `--alien`.
  - **SCOPE is universal** (v1.9 → v2.0) — there is ONE scope syntax in my-plex, used identically by every SCOPE-taking command (`--list`, `--mv-to`, `--remux`, `--plex2disk`, `--disk2plex`, `--rename`, `--renumber`, `--reencode`, `--broken`, `--unmatched`, `--unsorted`, `--mismatched`, `--missing`, `--problems`, `--unrecognized` — and any future verb). SCOPE can be a library name (a bare word that names a library in the cache, unless it is a type shortcut — `movie`, `movies`, `series`, `show`, `shows` — `watched` / `unwatched` or a field name such as `title` or `year`: then write `library:NAME`; any other bare word is a title search), cache key, full filepath, title search, or filter expression (`type:series`, `layout:series`, `lang:fr`, `country:france`, `original_lang:de`, `year>2020`, `bitrate>2`, etc.). Multiple tokens **AND-combine**: e.g. `my-plex --mv-to lib4 lib1 original_lang:fr` resolves to "every originally-French movie currently in `lib1`" and moves them. Write your query once, plug it into the verb. See `my-plex --help scope`.
  - **Original-language backfill** (v1.8; folded into `--update-cache` in v3) — the tail of every `--update-cache` fills the `original_language` field on cached Movies / Series from the TMDB API, when `TMDB_API_KEY` is set; without the key it is skipped silently. The backfill powers the `original_lang:` / `originallang:` / `original_language:` filter tokens, which distinguish "in French audio (possibly dubbed)" from "originally in French" — e.g. an Italian movie dubbed to French has `audio_languages=['fr']` but `original_language='it'`. Companion token `country:` (no backfill needed; data already in cache) accepts ISO 3166-1 alpha-2 codes (`country:fr`) AND English names (`country:france`, `country:united_states`). Language tokens accept ISO 639-1 codes (`original_lang:fr`) AND English names (`originallang:french`). Use `--help original-languages` for details.
  - `--mv-to` / `--move-to` — move Plex media to another library. Usage: `--mv-to DEST_LIB [SCOPE]`; the `-to` suffix says the FIRST argument is the destination. Accepts every Plex type in the cache: **whole Series** (`Series:NNN` → expands to all seasons + episodes), **whole Season** (`Season:NNN` → expands to all its episodes), **single Episode** (`Episode:NNN`), **Movie** (`Movie:NNN` — all versions), **whole library** (library name), title search, full filepath, or omitted = global (every Movie / Episode currently in another library). Sibling files (`.nfo`, `.srt`, posters, …) move alongside the main video files. Duplicate detection in DEST_LIB by (Plex title + originalTitle + year) — interactive prompt with `[s]kip / [o]verwrite / [S]kip-all / [O]verwrite-all / [q]uit`, or `--force` to auto-overwrite. Default: PREVIEW only; `--yes` commits. After moving, triggers Plex library scans on source AND destination so Plex re-indexes the files (Plex assigns new IDs for cross-library moves; run `--update-cache` afterwards to repopulate cache).
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
- **Installing** (`--install`, as root) — the firewall rules my-plex needs and the ssh Host entry it connects through; see [Installing](#installing---install-as-root)

### Output control
- **`-V` / `-VV`** — more detail for the reader; **`-D` / `-DD`** — diagnostics
  for debugging my-plex itself. Two independent axes; `-D` implies `-V`.
- **`-Q` / `--quiet`** — prints **nothing** on stdout: no progress, no summary,
  and no result either, so do not pass it to a command whose output you came
  for. Errors and warnings stay on stderr, so an unattended caller mails the
  failure and nothing else:

  ```bash
  my-plex -Q --update-cache            # cron: silent unless it fails
  my-plex -Q --sort-new --resolve -Y   # -Y answers the confirmation in advance
  ```

  It redirects file descriptor 1, not just Python's `sys.stdout`, so output
  from the `ssh` and `ffmpeg` children is silenced with everything else. `-V`
  or `-D` overrides it, including against a `QUIET` pinned in the config. A
  command that would ask a yes/no question refuses under `-Q` rather than wait
  on an invisible prompt — answer it with `-Y`/`--yes` or `-N`/`--no`.

### Remote Operation
- **SSH-transparent** — reads and writes episode data on the Plex server via SSH
- **No mount required** — works without mounted volumes (SSH fallback for all file I/O)
- **Path resolution** — automatic translation between server and local paths via `ALTERNATIVE_ROOTPATHS`

## Installation

```bash
# Clone and add to PATH
git clone https://github.com/Tormen/my-plex.git
ln -s "$(pwd)/my-plex/my-plex" /usr/local/bin/my-plex      # or anywhere in your PATH

# Configure
my-plex --create-config ~/.my-plex.conf      # Write default config to file: mode 0600, never over an existing file
# Or: my-plex --create-config > FILE   # the template on stdout: the redirect overwrites a file there, with the umask's mode
# Edit ~/.my-plex.conf with your Plex DB path and the Plex token; the Plex
# server's ssh address goes in the site config (see "Installing" below)
# See the files read and each key they set:  my-plex --config

# Then, in a root shell: the firewall rules, and the ssh Host entry as you
my-plex --install
```

Nothing else to install by hand: `my-plex` is a launcher of a few lines that
finds its two modules beside itself -- `my_plex_boot.py`, which decides who
runs and in what interpreter, and `my_plex.py`, the tool -- and on its first
run it
- creates its own virtualenv (`~/.python.venv/my-plex/`) with the stdlib
  `venv` module and re-executes itself inside it,
- installs its two dependencies there (`plexapi`, `readchar`),
- writes its zsh completion to `~/.zsh/completions/_my-plex` and adds the
  `fpath` line to `~/.zshrc` once.

None of that is an install step: each happens when needed, on every run,
whether or not anyone said `--install`. `--help` and `--version` answer
without any of it, so they work on a machine with no virtualenv and no
network.

The launcher is there so that `my_plex.py` is IMPORTED, and its bytecode cached:
deployed, every start after the first loads it instead of parsing the module
again. A deployed copy (`lib/my-plex/`) that finds no bytecode for the Python
running it says so in one line on stderr; root's `my-rollout go` compiles it.
So `my_plex.py` is not a command: started directly (`python3 my_plex.py ...`)
it refuses and names the launcher. A launcher whose modules are missing --
beside it or in `../lib/my-plex/` -- says that in one line too.

### Installing (`--install`, as root)

`--install` is the one my-plex command that runs as root. It does the one
privileged thing, then hands over to an ordinary run as the user my-plex
belongs to:

```bash
my-plex --install       # in a root shell, or a rollout step with `# user: root`
```

**As root: the firewall rules**, written through `my-little-snitch`, for
every remote my-plex connects to: `api.themoviedb.org`, `api4.thetvdb.com`
and `www.fernsehserien.de`, which it fetches from; `pypi.org` and
`files.pythonhosted.org`, where pip fetches the venv's two dependencies; and
the Plex server, both its API and its ssh endpoint. Behind an interactive
firewall the first connection to each is held behind an alert, and a
scheduled run has nobody to answer it -- without its rule, pip would be held
in the middle of the very first run. `my-plex --help install` lists them
all, from the one list the rules are written from. In this order:

1. `python3` is 3.10 or newer, or an ERROR names the one found.
2. A stored **deny** for that very remote -- any port, or its own -- that
   names my-plex's Python, `ssh` or `any` is removed: a deny beats an allow.
   A deny naming another program -- another Python minor too -- or another
   remote is somebody else's, and stays.
3. **Two rules per remote**: one naming the program that connects -- Python,
   or `ssh` for the ssh endpoint -- and one for `any` process connecting via
   it. Each rule's **owner** is `RUN_AS_USER` from the site config, else the
   user who ran sudo -- never root, who only writes them. With neither, or
   with a name that is root or no user of this machine, it is an ERROR.
4. **The drop**: `su -l <that user>`, so the rest runs as that user in a
   fresh login -- that user's HOME and PATH, nothing of root's environment --
   given the config root read when one was named.

A failure in 1-3 is an ERROR, and nothing is handed over. Root builds no
venv and writes nothing into its own home. As root, `--install` takes only
`--config FILE` and `-Q` beside it: root hands over `--install` alone, so
anything else would silently not run, and is an ERROR instead.

**Where each rule's remote comes from.** The ssh endpoint's host and port
are those of `PLEX_DB_REMOTE` -- never the ssh alias, which a firewall cannot
resolve, which root's ssh would look up in root's own ssh config, and which
does not exist yet on a fresh machine. The Plex API's is `PLEX_API_REMOTE`,
`'host[:port]'` (port 32400 when none is given): the server's address
without its token. As root no other key names it, because the token -- and
with it `PLEX_URL` and `PLEX_XML_URL` -- belongs in each user's own config;
without `PLEX_API_REMOTE`, root writes no API rule and says so. The rule
carries its port, because 32400 is not the default a rule assumes. For a
`*.plex.direct` server it names the **domain**: that host name carries the
server's own LAN IP, so a rule naming the host would stop matching -- back
into an alert -- the next time that IP changes. A bare IP becomes an
address rule, any other name a host rule.

**What root reads.** The site config alone, or a file named by
`$MY_PLEX_CONFIG` or `--config` -- each only as [Configuration](#configuration)
says root reads a file (a config under `/tmp` is refused). The keys of
`--install` belong in the site config; Configuration names them.

**Then, as that user: the ssh `Host` entry**, and nothing else. Every DB
query, file move and ffprobe runs `ssh <PLEX_DB_REMOTE_HOST>`, an alias; on
a machine where nobody wrote that alias by hand, each of them fails with
`Could not resolve hostname`. `--install` writes it from the site config:

```python
PLEX_DB_REMOTE = 'user@192.0.2.10'                              # or user@host:2222
PLEX_DB_REMOTE_IDENTITY = '~/.ssh/keys/plex-server,id_ed25519'  # optional
```

- `PLEX_DB_REMOTE` is the Plex server as you would reach it with ssh, the
  `user@host[:port]` you would type at a prompt; it becomes the block's
  `HostName`, `User` and -- with a `:port` -- `Port`. `--install` needs it,
  as the one thing it cannot invent: without it, root's half and yours each
  stop with an ERROR naming the config files read, before any rule or ssh
  file is written. Every other command still runs from defaults.
- `PLEX_DB_REMOTE_IDENTITY`, optional, names the key that logs in there when
  it is not one of ssh's default keys (`~/.ssh/id_ed25519`, `id_rsa`, ...):
  the block names it as its `IdentityFile`. `~` is each user's own home, so
  one value serves every user of the site. A key file that is not there
  stops the ssh half before any ssh file is written -- root's rules, written
  before the hand-over, stay; unset, the block names no key and ssh offers
  yours.
- `PLEX_DB_REMOTE_HOST` is the alias's name, `my-plex` by default -- the
  same on every machine, the entry `--install` wrote. Change it only if that
  name is already yours for something else.

It writes `~/.ssh/my-plex.conf`, a file it owns entirely, and ONE `Include`
line at the top of `~/.ssh/config`: ssh reads no other file in `~/.ssh` by
itself, so that line is what makes the block count. Both files are written
as a temp file renamed over the original -- a symlink followed to its
target, its mode kept -- so no ssh reads half a file. What it finds decides
the rest; `ssh -G <alias>` answers what the alias resolves to and connects
to nothing:

- the alias does not resolve, or `~/.ssh/my-plex.conf` gives it older
  values: that file is (re)written -- options carried over into it are
  kept -- and the `Include` added when missing;
- it resolves to exactly what the config says: nothing is written, and the
  values compared are printed;
- a `Host` block you wrote by hand in `~/.ssh/config` answers for it: that
  block is **moved** into `~/.ssh/my-plex.conf`, keeping every option
  my-plex does not generate (`ProxyJump`, `SetEnv`, an `IdentityFile` when
  `PLEX_DB_REMOTE_IDENTITY` is unset), with its old lines kept there as a
  dated comment -- so no machine stays configured its own way;
- it **stops** with an ERROR, nothing moved or written, where moving would
  mean guessing: the block names another host, user or port than
  `PLEX_DB_REMOTE` -- or another key than `PLEX_DB_REMOTE_IDENTITY` -- and
  only you know which is right; its `Host` line names other aliases too; or
  the alias resolves from somewhere my-plex does not edit (another
  `Include`, `/etc/ssh/ssh_config`, a `Match` block).

It ends with one real login, `ssh <alias> true` in BatchMode, and prints its
exit code: resolving proves nothing about a key. A failed login is an ERROR.

The run root hands over also rebuilds a venv that was built from another
Python minor, saying so in one line: root has just written rules naming this
`python3`, and to the firewall another minor is another program. A
`--install` you start yourself rebuilds nothing.

**Without `my-little-snitch`** -- no file at `LITTLE_SNITCH_CLI`, which
defaults to `/LINKS/sbin/my-little-snitch` -- there is nothing for root to
write: `--install` needs no root, runs as you, writes no rule, names the
hosts to allow in whatever firewall you run, and writes the ssh `Host`
entry. With it, a `--install` you start yourself is refused ("--install
needs root"): `littlesnitch` refuses anyone but root, even to list.

**Which Python the rules name.** The fetches use `urllib.request`, so the
interpreter opens the socket and is what a firewall sees. Root names the
base `python3` the launcher runs under, never a venv's: it exists before
any venv does, and a rule for a path that does not exist is refused. Two
consequences: the rules also cover other scripts run by that Python -- there
is no narrower form for a Python script -- and a Python minor upgrade needs
`--install` again, because `python@3.16` is another program than
`python@3.15`.

**Why two rules per remote.** Little Snitch attributes a connection to the
app *above* Python and calls Python the **via** program, so a rule naming
Python as the process does not match a run started from a shell, a session
or a job -- the alerts read `Terminal via Python`, with *"an existing rule
for any via-process was not applied to Python"*, while those process rules
were already stored. The second rule is for `any` process connecting *via*
that Python -- `any` rather than a list of apps, because my-plex is run from
all of them and enumerating them never ends.

**Every other command refuses root** (err 00001): as root, my-plex's venv,
cache, your config and zsh completion would land in `/var/root` instead of
your home, and nothing it does needs privilege. The runs that only PRINT
work as root, because they touch none of that: a bare `my-plex`, `--help
[WHAT]` (also `--help=WHAT`, `-H`, `-HWHAT`) and `--version`. A help flag
after `--` is a plain argument and asks for no help, and one bundled with
other flags (`-VH`) is refused as root. `--create-config` is refused although
its plain form only prints: `--create-config FILE` writes, and one flag is
not half-allowed. So is `--stamp-version`: it rewrites a file of the checkout
and amends a commit.

#### What it prints

A fresh machine, in a root shell. The site config, `/etc/my-plex.conf`, says
`RUN_AS_USER = 'plexuser'`, `PLEX_DB_REMOTE = 'user@192.0.2.10'` and
`PLEX_API_REMOTE = '192.0.2.10'`:

```
# my-plex --install
 >>> my-plex --install          (root: the firewall half)
    > user:    plexuser        (RUN_AS_USER, site: /etc/my-plex.conf)
    > process: /opt/homebrew/bin/python3
    > (the BASE Python the launcher runs under -- it exists before any
       venv; the rule also covers other scripts this Python runs)
    > and `ssh` for the Plex server: my-plex reads its DB and moves its
      files over ssh, so there the firewall names ssh
    > owner:   plexuser        (whose rule it is -- not root, who writes it)

 >>> FIRST, any DENY for the remotes below that names my-plex's Python,
     ssh or `any` -- a deny beats an allow:  none found
 >>> two rules per remote: the program itself, and `any` process via it
     (Little Snitch names a run from a shell "Terminal via Python")
   > api.themoviedb.org       [rc 0 0]  TMDB API: original-language backfill, --unmatched --resolve
   > api4.thetvdb.com         [rc 0 0]  TVDB API: episode data for --missing
   > www.fernsehserien.de     [rc 0 0]  episode data for German libraries (scraped; no API key)
   > pypi.org                 [rc 0 0]  pip, building the venv on a first run
   > files.pythonhosted.org   [rc 0 0]  pip again: where the wheels themselves come from
   > 192.0.2.10               [rc 0 0]  the PLEX SERVER's API -- every call, every --update-cache
   > 192.0.2.10               [rc 0 0]  the Plex server over SSH (my-plex) -- every direct DB read and every file operation
 >>> firewall half: 14 rule(s) written, 0 already there (7 remote(s) x 2)
    > a STORED rule is not a MATCHING rule: the proof is the next run
      getting through (my-little-snitch log /opt/homebrew/bin/python3)

 >>> dropping to plexuser for the rest -- nothing below this line runs as root
```

Then, as `plexuser` -- after the venv bootstrap's own lines, with pip's
output, since this machine has no venv yet:

```
 >>> my-plex --install          (as plexuser: the ssh half)
    > the firewall rules: root's half, done before it handed over

 >>> the ssh Host entry my-plex's own ssh goes through
    > alias 'my-plex' -> user@192.0.2.10   (PLEX_DB_REMOTE, site: /etc/my-plex.conf)
 >>> wrote /Users/plexuser/.ssh/my-plex.conf   [new]
 >>> added, at the top of /Users/plexuser/.ssh/config:  Include /Users/plexuser/.ssh/my-plex.conf
    > ssh -G my-plex: user@192.0.2.10 port 22
 >>> one login through it: ssh my-plex true   [rc 0]

 >>> SUMMARY  --install: firewall rules by root's half; ssh Host entry written
```

A second run writes nothing: root's verdict reads `0 rule(s) written, 14
already there`, the ssh half prints the values it compared with `[nothing
written]`, and the summary ends `ssh Host entry unchanged`.

### Requirements
- Python 3.10+ (uses `match/case`)
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

Configuration files are Python, run with `exec()`. my-plex reads up to
two, the later winning for a key both set:

1. **The site config**, the same for every user of a machine: every one of
   `<dir>/my-plex.conf` and `<dir>/my-plex` that exists, where `<dir>` is
   `CONFIG_SEARCH_DIR` from the site file `/LINKS/default/site.conf` (a
   `.GLOBAL` twin linked into a `global/` tree is read first), else the
   first of `/etc/my-plex.conf` and `/usr/local/etc/my-plex.conf`. Without
   a site file, only the latter two.
2. **Your config**: `~/.my-plex/my-plex.conf` or `~/.my-plex.conf`. Two
   different files there are an error -- merge them into one.

Each file runs with every value set before it defined, so yours can extend
a site value (`X = X + [...]`); a plain assignment replaces it whole. The
Plex token and API keys (`PLEX_XML_URL`, `PLEX_TOKEN`, `TVDB_API_KEY`,
`TMDB_API_KEY`) belong in your config only, and the keys of
`--install` -- `PLEX_DB_REMOTE`, `PLEX_DB_REMOTE_IDENTITY`,
`LITTLE_SNITCH_CLI`, `RUN_AS_USER` and `PLEX_API_REMOTE` -- in the site
config only: my-plex refuses them in the other. As root, a config file --
site or named -- is read only when root owns it, and every directory above
it, and neither group nor others can write them: a config is Python, and
root would run another user's code. A config file that cannot be read or fails to run stops the run;
`--help` and a bare `my-plex` only warn.

`$MY_PLEX_CONFIG` (a config for ONE run: a test, a CI job, a one-off), else
`--config FILE` / `-C FILE`, names a file that is read **alone** -- by that
run and by every my-plex it starts (a pipeline's phases), which get
`--config` as `$MY_PLEX_CONFIG_INHERITED`, read after their own `--config`:
a phase that names its own config keeps it. Such a path that is not there is an
**error**, never a fallback. A test run (`--run-tests`), and every my-plex
it starts, reads neither the site config nor yours -- only a file a test
names. `my-plex --help config` prints the read order from
the same code that reads.

`my-plex --config` prints the files read, in order, then one line per key
they set, with the layer that set it -- `-DD` names each key's file too:

```
# config files read, in order -- for a key both set, the later wins:
#   site   /LINKS/default/my-plex.conf -> ../global/etc/default/my-plex.conf
#   yours  /Users/you/.my-plex.conf
PLEX_DB_REMOTE             = 'user@192.0.2.10'            (site)
PLEX_XML_URL               = 'http://192.0.2.10:32400/library/sections?X-Plex-Token=<redacted>'   (yours)
TMDB_API_KEY               = <redacted, 32 chars>         (yours)
```

A link shows its own target, as `ls -l` does. A file the search chose but
did not read says why, e.g. `(points nowhere -- not read)` for a dangling
link. It never prints a secret: a secret-named key shows only its length, and
the token in a URL is cut out, whatever its case.

A key my-plex no longer reads (`DISK_MAP`, `PROBLEM_CATEGORIES_DISABLED`, ...)
stops every run, naming each file that sets it -- a link with its own target,
so a farm entry shows the file behind it -- delete it from all of them.

```python
# Required in the site config: the Plex server as you would ssh to it
PLEX_DB_REMOTE = 'user@192.0.2.10'
# Optional, site config: the key that logs in there, when not a default one
PLEX_DB_REMOTE_IDENTITY = '~/.ssh/keys/plex-server,id_ed25519'
# The ssh alias --install writes from it (the default)
PLEX_DB_REMOTE_HOST = 'my-plex'
# Site config, for --install as root: the user it hands over to (else the
# user who ran sudo), and the Plex server's API address, without the token
RUN_AS_USER = 'plexuser'
PLEX_API_REMOTE = '192.0.2.10:32400'

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
# Run the whole suite
my-plex --run-tests

# Run one scope
my-plex --run-tests disk-map
my-plex --run-tests commands
my-plex --run-tests duplicates

# Run the tests whose title matches -- what a change touches, in seconds
my-plex --run-tests TestRename.test_siblings

# unittest's own output
my-plex --unittest -v

# The tests that really FETCH -- off unless you ask for them
MY_PLEX_TEST_NETWORK=1 my-plex --run-tests TestTsvScrapersE2E
```

**A default run reaches no network.** Seven scraper tests fetch
api.themoviedb.org and www.fernsehserien.de for real; they skip unless
`MY_PLEX_TEST_NETWORK` is set, and each says so in its own skip line. Behind
an interactive firewall an unapproved connection does not fail — it **hangs**,
and a suite run under `my-rollout go` was killed at its 600s cap because of
it, so the copy was never offered. Nothing is deleted: set the variable and
they run exactly as before.

A FILTER is a scope name if one matches, otherwise part of a test title; a
FILTER that matches neither prints the scopes with their test counts. Exit 0
when every test passed, 1 otherwise.

It reports **TAP-style** -- the plan `1..N` first, then `ok K - title` /
`not ok K - title` per test as it ends, flushed, so a reader can draw progress
from the stream. `my-rollout go` reads exactly this: a pending copy whose
`--help` names `--run-tests` has its own suite run before the copy is offered,
so a copy that fails its tests is never promoted.

The suite lives in `my-plex_tests.py` and is loaded only by `--run-tests` /
`--unittest` -- never at import time, which is what once killed every command
on a deployed copy. It is looked for beside the modules: a checkout holds the
launcher, the modules and the suite side by side, and a deployed copy is
`bin/my-plex` with `my_plex_boot.py`, `my_plex.py` and `my-plex_tests.py` in
`lib/my-plex/` -- one request in `.my-rollout.local`, `++my-plex +
my_plex_boot.py my_plex.py my-plex_tests.py`, deploys them as one copy. The tool
tells the suite where the launcher and the modules are as it loads it, because
the tests run the one and read the others.

### Type checking

```bash
pyright --pythonpath ~/.python.venv/my-plex/bin/python3
```

`pyrightconfig.json` configures it.  The interpreter matters: my-plex runs
inside its own venv, and without it pyright cannot resolve `plexapi` or
`readchar` and reports those imports as errors.

`my-plex --run-tests typecheck` runs the part of this that is already green -- no
undefined and no possibly-unbound name in `my_plex_boot.py` and `my_plex.py` -- and is skipped when
pyright is not installed.  The remaining findings are listed in the project's
TODO.

## Version and release

```bash
my-plex --version              # v2.69 (build 1a2b3c4d5e6f, from commit 325612a)
my-plex --stamp-version        # analyze: what would be stamped
my-plex --stamp-version go     # record HEAD in SCRIPT_COMMIT, amend HEAD
```

- The **build id** is a hash of the launcher `my-plex`, `my_plex_boot.py` and
  `my_plex.py` together, so two installs that differ in any of them never
  report the same `--version`; compare installs by diffing it.
- `SCRIPT_COMMIT` names the commit the file was released from. It lags HEAD
  by one, because the stamp amends HEAD and a commit cannot contain its own sha.
- Release order: commit, `--stamp-version go`, push. The stamp refuses a
  commit that is already pushed, a HEAD that touches none of the three files,
  anything staged, or uncommitted edits to any of the three.
- A tagged version number is never reused: once HEAD has moved past the tag
  for `SCRIPT_VERSION`, bump it (`my-plex --run-tests version` enforces this).

## Contributing

Open Source — contributions are welcome.

## License

GPL-3.0-or-later (copyleft) -- see [LICENSE](LICENSE). Derivative works must be
released under a compatible license.
