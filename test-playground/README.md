# Test Playground

This directory contains test scripts, logs, and resolution artifacts used for testing the `my-plex` duplicate resolution and cache management functionality.

## Test Scripts

### Python Scripts

#### `test_with_timestamps.py`
Automated test script that monitors library timestamps throughout the full resolution cycle. Tests the complete workflow:
1. Resolve a duplicate
2. Verify no cache update is needed
3. Undo the resolution
4. Run `--update-cache`
5. Verify no cache update is needed

#### `test_timestamps_auto.py`
Similar to `test_with_timestamps.py` but with enhanced automation and timestamp monitoring. Verifies that cache timestamps are correctly set to `datetime.now() + 30s` after resolution operations.

#### `test_timestamp_margin.py`
Tests the 30-second safety margin for cache timestamps. Verifies that cache timestamps remain ahead of Plex timestamps after library scans.

#### `restore_cache_from_log.py`
Utility script to restore cache library timestamps from a previous log file. Useful for recovering from failed tests or reverting timestamp changes.

#### `resolve_test.py`
Basic automated resolution test script using `pexpect` to send choices to interactive prompts.

#### `show_first_dup.py`
Debugging utility that shows the first duplicate entry in the resolution interface. Used for quick inspection without processing all duplicates.

#### `show_first_choice.py`
Interactive script that displays the first duplicate and its resolution options, then exits without applying changes.

#### `resolve_arthur*.py` (multiple versions)
Series of test scripts specifically for resolving "Arthur and the Invisibles" duplicate:
- `resolve_arthur.py` - Initial version
- `resolve_arthur_v2.py` - Second iteration with improvements
- `resolve_arthur_v3.py` - Third iteration
- `resolve_arthur_final.py` - Final working version
- `resolve_arthur_interactive.py` - Interactive version with prompts

### Shell Scripts

#### `complete_test.sh`
Comprehensive test script that runs the full resolution cycle including verification steps.

#### `test_full_cycle.sh`
Similar to `complete_test.sh` but with additional logging and timestamp monitoring at each step.

#### `monitor_rebuild.sh`
Monitors cache rebuild operations and tracks library timestamps during the process.

## Test Logs

### Resolution Logs

#### `my-plex_--duplicates_--resolve_*.json`
JSON logs created by the resolution system. Each file contains:
- Timestamp of resolution session
- List of duplicates processed
- User choices and operations performed
- Final state of each resolution

Format: `my-plex_--duplicates_--resolve_YYYYMMDD_HHMMSS.json`

Notable logs:
- `20251229_112202.json` - Final successful resolution test with correct timestamps
- `20251229_110859.json` - Resolution test during timestamp fix verification
- `20251229_103441.json` - Test after implementing `datetime.now() + 30s` fix

### Test Output Logs

#### `step1_resolve.log`
Output from step 1 of the comprehensive test: resolving a duplicate.

#### `step2_verify.log`
Output from step 2: verifying no cache update is needed after resolution.

#### `resolve_test_output.log`
General resolution test output with timestamp monitoring.

#### `resolve_test_arthur.log`
Specific test output for Arthur and the Invisibles duplicate resolution.

#### `resolve_final_output.log`
Final resolution test output after all fixes were applied.

#### `resolve_first_choice.log`
Log of the first duplicate choice prompt and user interaction.

#### `resolve_output.log`
General resolution operation output log (older version).

#### `resolve_test.log`
Detailed resolution test log with debug information.

### Timestamp Verification Logs

#### `test_timestamp.log`
Basic timestamp test verifying cache timestamp behavior.

#### `test_timestamp_fix.log`
Test log after implementing the `datetime.now() + 30s` timestamp fix.

#### `timestamp_test.log`
Comprehensive timestamp test with before/after comparisons.

#### `timestamped_update_cache.log`
Logs timestamps during `--update-cache` operations.

#### `test_bottoms.log`
Timestamp test for "Bottoms (2023)" duplicate resolution.

#### `test_bottoms_final.log`
Final successful test output for Bottoms duplicate with correct timestamps.

### Cache and Update Logs

#### `test-update-cache.log`
Output from `--update-cache` command during testing (large file: 1.2 MB).

#### `update-cache-proof.log`
Proof-of-concept log showing correct `--update-cache` behavior (1.2 MB).

#### `test-list-duplicates.log`
Output from `--list-duplicates` command during testing.

#### `list-duplicates.log`
General duplicate listing output (129 KB).

#### `list-duplicates_resolve.log`
Combined duplicate listing and resolution output.

### Backup and Rebuild Logs

#### `test_backup.log`
Log of cache backup operations during testing.

#### `test_backup_resume.log`
Log of resumed backup operations after interruption.

#### `debug_from_scratch.log`
Comprehensive debug log from cache rebuild from scratch (57 MB - very detailed).

#### `fixed_from_scratch.log`
Log showing successful cache rebuild after fixes were applied.

#### `from_scratch_rebuild.log`
Cache rebuild log with detailed progress information.

### Verification Logs

#### `final_verification.log`
Final verification step output confirming all systems are synchronized.

#### `full_test_output.log`
Complete test suite output with all verification steps.

#### `first_dup_output.log`
Output showing first duplicate entry details.

#### `final_timestamped_cache.log`
Cache state with timestamps after final successful test.

### Miscellaneous Logs

#### `check-arthur-duplicates.log`
Quick check for Arthur and the Invisibles duplicate status.

#### `fresh_update_cache.log`
Output from fresh cache update operation.

#### `partitioned_update_cache.log`
Log showing partitioned library update process with worker threads.

## Known Issues

### TypeError in Early Resolution Attempts
Some early logs (e.g., from Dec 28) show a TypeError at [52:8459](../52#L8459):
```
TypeError: string indices must be integers, not 'str'
multi_version_files = [(ver, file_info['filepath']) for ver, file_info in files_dict.items()]
                                ~~~~~~~~~^^^^^^^^^^^^
```

**Context**: This error occurred during the "For loop exited. Expected 118 duplicates, processed through dup_idx=1" issue where the resolution loop was exiting prematurely.

**Status**: This was an earlier bug related to the cache format migration from old format (version: filepath string) to new format (version: {filepath: ..., filesize: ...}). The code expected the new format but encountered old cached data.

**Note**: Current code handles both formats correctly. This error appears in historical logs but is not reproducible with current code + updated cache.

## Key Test Scenarios

### Timestamp Fix Verification (Dec 29, 2025)
Tests verifying the critical fix where cache timestamps must be set to `datetime.now() + timedelta(seconds=30)` instead of using Plex timestamps:
- `test_timestamps_auto.py` + `timestamp_test.log`
- `test_with_timestamps.py`
- Verified that resolution no longer triggers false cache update prompts

**Context from chat history**: User observed that all libraries showed the same timestamp (10:34:42) and questioned:
> "Please explain how it can be that all libraries were updated in the exact same second"

This led to investigation of:
1. Whether Plex has per-library timestamps (confirmed: YES, via PlexAPI source code)
2. Whether `--update-cache` scans all libraries or only changed ones (Answer: ALL libraries in parallel)
3. Why `--list-duplicates --resolve` was prompting for cache updates immediately after (Answer: timestamp race condition)

**Key discovery**: The user pushed to read actual PlexAPI source code:
> "You need to (a) read the actual plex python api source code to know what plex can or cannot do!"

This confirmed Plex DOES have per-library `updatedAt` timestamps at `~/.python.venv/my-plex/lib/python3.14/site-packages/plexapi/library.py:434,453`

### Full Resolution Cycle
Complete workflow tests ensuring DISK, PLEX, and CACHE remain synchronized:
1. Resolve duplicate → 2. Verify no update needed → 3. Undo → 4. Update cache → 5. Verify no update needed

Scripts: `test_full_cycle.sh`, `complete_test.sh`
Logs: `step1_resolve.log`, `step2_verify.log`, `final_verification.log`

**User's explicit requirement**:
> "During this: [...] please consider ALL libraries in step 2 and 5. NONE of ALL libraries should need an update!"

This requirement drove the development of comprehensive timestamp monitoring tests.

### Specific Duplicate Tests
Tests for particular movies that exhibited issues:
- **A Great Friend (2023)**: First test case, user requested:
  > "please run --list-duplicates --resolve And chose '4' in order to KEEP [1] Movie: A Great Friend (2023). Then 'A'pply"

- **Bottoms (2023)**: Used for timestamp fix verification (`test_bottoms.log`, `test_bottoms_final.log`)

- **Arthur and the Invisibles**: Multiple test iterations (`resolve_arthur*.py` series)

### Library Scanning Behavior
**Question from chat**: "During --list-duplicates --resolve do you update only the libraries that were changed or ALL of them?"

**Answer**: Only modified libraries are scanned (code at [52:4086-4091](../52#L4086-L4091)), unlike `--update-cache` which scans ALL libraries in parallel.

**User's concern**: "But the fact that all libraries had the same TIMESTAMP in PLEX seems to suggest you are wrong."

**Explanation**: When `--update-cache` runs, it uses ThreadPoolExecutor to scan all libraries in parallel ([52:6911-6976](../52#L6911-L6976)), which is why they can have very similar timestamps. The resolution code only scans affected libraries.

## Important Fixes Documented

### Fix: Cache Timestamp Race Condition (Commit 781c047)
**Problem**: After `--list-duplicates --resolve`, subsequent commands prompted for cache updates even though libraries were just scanned.

**Root Cause**: Using Plex timestamps which continue to drift after scan operations complete. Plex continues updating timestamps asynchronously even after library.update() returns.

**Solution**: Use `datetime.now() + timedelta(seconds=30)` RIGHT BEFORE saving cache, not Plex timestamp + 30s.

**Evolution of the Fix** (from chat history):
1. **First attempt (Commit 9eeda3e)**: Fetch Plex timestamp after scan and save to cache
   - Problem: Still used Plex timestamp which could drift

2. **Second attempt (Commit 659aa8b)**: Added 30s to Plex timestamp
   - Code: `cache_timestamp = plex_timestamp + timedelta(seconds=30)`
   - Problem: Using Plex timestamp as base is unreliable

3. **Third attempt (Commit 4b1b522)**: Modified `get_library_stats()` to add 30s
   - Problem: Violated principle that `get_library_stats()` should return TRUTH
   - User feedback: "get_library_stats() should NEVER change values but display the TRUTH from the library"

4. **Final correct fix (Commit 781c047)**:
   - Reverted `get_library_stats()` to return actual Plex values (no modifications)
   - Changed resolution code to use `datetime.now() + timedelta(seconds=30)`
   - User guidance: "take the REAL time before quitting + 30s and set the cache timestamp to this value"
   - Matched existing correct implementation in `--update-cache` at lines 869-880

**Key Insight**: The 30-second buffer must be based on CURRENT TIME when saving cache, not on Plex's timestamp. This ensures cache timestamp is always ahead of any Plex timestamp drift.

**Evidence**:
- Before fix: `test_timestamp.log` showing false cache update prompts
- After fix: `test_bottoms_final.log`, `timestamp_test.log` showing no prompts
- Verification: All 5-step comprehensive tests passed (resolve → verify → undo → update → verify)

**User's Testing Requirements**:
> "please repeat and monitor all library timestamps in PLEX and in CACHE for your test!"
> 1. Do the resolve (you decide)
> 2. Run another --list-updates to check that there is NO Cache update necessary
> 3. Undo the resolution by moving the file back from the trash
> 4. Run --update-cache to ensure that DISK, PLEX and CACHE are in sync
> 5. Run --list-updates to check that there is NO Cache update necessary

All steps verified successfully with `test_timestamps_auto.py` and `test_with_timestamps.py`.

### Code Locations
- Resolution timestamp fix: [52:4171-4180](../52#L4171-L4180)
- Update-cache timestamp fix: [52:869-880](../52#L869-L880) (this was already correct!)
- get_library_stats() (returns TRUTH): [52:1876-1898](../52#L1876-L1898)
- Modified libraries tracking: [52:4001-4036](../52#L4001-L4036)
- Selective library scanning: [52:4086-4091](../52#L4086-L4091)

## Usage Notes

1. Most scripts use `pexpect` for automated interaction with `my-plex` prompts
2. Logs are timestamped to track progression of fixes
3. JSON resolution logs are the authoritative record of what operations were performed
4. Large logs (>1 MB) contain complete cache rebuild information with all metadata

## Development Methodology from Chat History

### Iterative Problem Solving
The timestamp fix went through 4 iterations before reaching the correct solution. Each failure led to deeper understanding:

1. Initial assumption: Fetch Plex timestamp after scan
2. First correction: Add buffer to Plex timestamp
3. Second correction: Add buffer in get_library_stats()
4. Final insight: Use current time, not Plex time

### User-Driven Verification
The user insisted on comprehensive testing:
- "please repeat and monitor all library timestamps in PLEX and in CACHE"
- Required verification of ALL libraries, not just modified ones
- Demanded proof through automated test scripts with logging

### Key Principles Established

**Separation of Concerns**:
> "get_library_stats() should NEVER change values but display the TRUTH from the library"

Functions that fetch data must return actual values. Transformations happen at save time, not fetch time.

**Timestamp Strategy**:
> "take the REAL time before quitting + 30s and set the cache timestamp to this value"

Use `datetime.now()` at save time, not Plex's timestamp which can drift due to asynchronous operations.

**Trust but Verify**:
> "You need to (a) read the actual plex python api source code to know what plex can or cannot do!"

Don't infer API behavior from client code. Read the actual source to understand capabilities.

### Testing Approach

Created parameterized test script based on user request:
> "You had created in the past already a TEST script. Please commit the test script to GIT this time and parametrize it."

Result: `test_resolve_duplicate.py` (committed in parent directory) with:
- `--choice` parameter for automated selection
- `--apply` flag for apply vs. quit
- `--debug` flag for verbose output
- `--timeout` parameter for long operations
- `--output-log` for capturing results

## Cleanup History

Files resolved and then undone during testing (per user request: "Did you undo all duplicates that YOU resolved today?"):
- A Great Friend (2023)
- Bottoms (2023)
- Changing Lanes (2002)
- Chinatown (1974)
- Les Choses Simples (2023)

All were restored from trash and cache was updated to ensure DISK/PLEX/CACHE synchronization.

User confirmed with: "is --update-cache using parallel workers?" (Answer: Yes, ThreadPoolExecutor)

## Organization

Per user request:
> "please move all your scripts and log output from /tmp into a test-playground folder within: /Users/MINE/data/src/,py/prj/my-plex"

All test artifacts moved from `/tmp` to this organized test-playground directory on Dec 29, 2025.

This README was created and will be maintained going forward to document all test artifacts and their purpose.
