# my-plex

Open Source script; Contributions are welcome.

- `1070` == highest used errCode
- `1001` == lowest used errCode

---

## CRITICAL CODING GUIDELINE FOR ALL FUTURE MODIFICATIONS

### SSH AND FILE OPERATION CENTRALIZATION

ALL SSH operations and file system operations MUST use the centralized function:

```python
my_plex_file_operation(operation, filepath, remote_host, **kwargs)
```

**NEVER** create direct SSH calls using `subprocess.run(['ssh', ...])`
**NEVER** use `os.path.exists()`, `shutil.move()`, `os.remove()` directly

If you need a new operation type:
1. ADD IT to `my_plex_file_operation()` function
2. Implement both remote (SSH) and local versions
3. Use `print_ssh_error()` for error handling

This ensures:
- Consistent error handling across all operations
- Automatic alternative path resolution (ALTERNATIVE_ROOTPATHS)
- Single source of truth for all file operations
- Easy maintenance and debugging

Supported operations: `CHECK`, `TRASH`, `RENAME`, `MOVE`, `REMOVE`, `LIST_DIR`

---

### DEBUG OUTPUT LEVELS PRINCIPLE

Use `DBG` and `DEEPDBG` flags consistently throughout the codebase:

**DBG** (Debug Mode - enabled with `-D` or `--debug`):
- Provides OVERVIEW of what's happening with SOME DETAILS
- Shows high-level flow: which functions are called, major decision points
- Shows key values: function parameters, important return values
- Shows step-by-step progress through complex operations
- Example: `"Step 1: Checking if file exists LOCALLY... result: True"`

**DEEPDBG** (Deep Debug Mode - enabled with `-DD` or `--deep-debug`):
- Provides ALL DETAILS including exact commands being executed
- Shows exact shell commands before execution (SSH, subprocess, etc.)
- Shows all intermediate values and transformations
- Shows detailed path resolution (original → escaped → final)
- Shows all alternative paths being checked
- Example:
  ```
  "Original filepath: /path/file.mkv"
  "Escaped filepath:  /path/file.mkv"
  "Full command: ssh host 'cat \"/path/file.mkv\"' | mpv -"
  ```

**USAGE PATTERN:**
```python
if DBG:
    print(f"{DBGPFX}Function called with param={value}")

if DEEPDBG:
    print(f"{DBGPFX}  Original value: {original}")
    print(f"{DBGPFX}  Transformed:    {transformed}")
    print(f"{DBGPFX}  Command: {cmd}")
```

**GUIDELINES:**
- Always use `DBGPFX` prefix for debug output
- Use 2-space indentation for DEEPDBG details under DBG overview
- Show commands BEFORE execution (helps with troubleshooting)
- DBG should be readable by users, DEEPDBG for developers

---

### TESTING AND REGRESSION PREVENTION PRINCIPLE

Whenever a bug is fixed in my-plex, a regression test MUST be added to the
test suite (`run_regression_tests` function) to prevent the bug from reoccurring.

**POLICY:**
- Every bug fix MUST include a corresponding test
- Run the test suite regularly during development: `my-plex --test`
- Tests should be run before committing significant changes
- The test suite should be continuously expanded to improve coverage

**TEST REQUIREMENTS:**
- Have a descriptive name and number (e.g., "Test 13: File Path Resolution")
- Include detailed comments explaining which bug it tests for
- Show clear PASS/FAIL/SKIP status with helpful output
- Increment passed/failed counters appropriately
- Include the root cause and fix description in comments

**EXAMPLE TEST STRUCTURE:**
```python
# Test N: Feature/Bug Description
print("\n[TEST N] Feature/Bug Description")
print("-" * 80)
try:
    # Bug fixed: <description of the bug>
    # Root cause: <what was causing the issue>
    # The fix: <what was changed to fix it>

    # Test implementation here
    if <test condition>:
        print(f"✓ PASS: <what passed>")
        passed += 1
    else:
        print(f"✗ FAIL: <what failed>")
        failed += 1
except Exception as e:
    print(f"✗ FAIL: Exception during test: {e}")
    failed += 1
```

**REGRESSION TEST EXAMPLES:**
- Test 13: File Path Resolution with ALTERNATIVE_ROOTPATHS
  Prevents regression where remote files with commas in path were incorrectly
  identified as local due to using `os.path.exists()` instead of `os.path.isfile()`

**WHY THIS MATTERS:**
- Prevents fixed bugs from reappearing in future changes
- Documents the fix for future developers
- Builds confidence in code changes
- Serves as executable documentation of expected behavior

---

### API vs DATABASE ARCHITECTURE

my-plex uses THREE data access tiers, in order of preference:

#### 1. CACHE (pickle file `~/.plex_media_cache.pkl`)
- Used by ALL non-update commands (`--list`, `--info`, `--broken`, `--duplicates`,
  `--verify-cache`, `--resolve`, etc.)
- No network, DB, or API access needed — fully offline capable
- Contains: `OBJ_BY_ID`, `OBJ_BY_LIBRARY`, `OBJ_BY_FILEPATH`, `OBJ_BY_MOVIE`,
  `OBJ_BY_SHOW`, `OBJ_BY_SHOW_EPISODES`, `OBJ_BY_COLLECTION`, `library_stats`

#### 2. PLEX DATABASE (SQLite via SSH or local access)
- Used by `--update-cache` for all data collection:
  - Library listing (`get_library_sections_from_database`)
  - Movie fetching (`fetch_movies_from_database`)
  - Show/episode fetching (`fetch_shows_from_database`)
  - Collection fetching (`_store_collections_from_database`)
  - Library stats/counts (`get_library_stats`)
  - Schema validation (`validate_plex_database_schema`)
- Also used for read-only checks: `--info` server existence, playlist detection
- 60x faster than API for bulk data collection

#### 3. PLEX API (plexapi Python library → Plex HTTP API)
- ONLY used for operations that MODIFY Plex server state:
  - Library scanning: `lib.update()`, `lib.refresh()`, `lib.reload()`
  - Item mutations: `media.delete()`, `media.markWatched()`, `media.markUnwatched()`
  - Label management: `media.addLabel()`, `media.removeLabel()`
  - Rating: `media.rate()`
  - Media analysis: `item.analyze()`
  - Metadata refresh: `media.refresh()`
  - Collection membership: `media.addCollection()`, `media.removeCollection()`
  - Playlist CRUD: `playlist.create()`, `playlist.addItems()`, `playlist.delete()`
- Also used for `resolve_plex_media_obj()` title/search fallback (stages 3-4)
  when cache-based lookup fails — reimplementing Plex search is not worth it
- Also used for `brute_force_search()` and `undo_operation()` (trash restore)
- Also used for `--info` (no args) server health check (API reachability + version)

**WHY API FOR WRITES:** The Plex SQLite database is effectively read-only from
external processes. Plex locks it for writes, and direct SQL modifications
would bypass Plex's internal consistency checks, caching, and event system.
All mutations MUST go through Plex's HTTP API (which plexapi wraps).
