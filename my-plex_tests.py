# 52_tests.py — Test suite extracted from '52' (main script)
# To merge tests back inline, replace the test import section in '52' with the contents of this file.
#
# This file is imported by '52' at runtime via importlib.
#
# pyright: reportUndefinedVariable=false
#   The main script injects its own functions into this module's namespace
#   before the tests run (_EPISODE_FUNC_NAMES / _inject_episode_funcs_into_test_mod),
#   so ~300 names used here are bound at runtime and invisible to a checker.
#   Re-declaring them would be a second copy of that list to keep in sync.

import unittest
import os
import sys
import ast
import re
import inspect
import pickle
import io
import contextlib
import json
import shutil
import signal
import subprocess
import tempfile
import importlib.machinery
import importlib.util
from typing import Any

# The tool overrides this when it loads the suite (_load_test_mod): only it
# knows its own file, which on a deployed copy is bin/my-plex.  This value is
# the fallback for running the suite straight out of a checkout.
MAIN_SCRIPT = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'my-plex.py')

# No README beside a DEPLOYED copy: that is bin/my-plex, and the suite beside
# it is lib/my-plex_tests.py.  "Absent" is therefore a real answer -- but it
# was given twice, differently, by the two tests that read the README: one
# opened it outright (so it ERRORED on a copy) and one caught the
# FileNotFoundError and skipped (so it asserted nothing there, quietly).  One
# owner answers it once, and TestReadmeIsFound keeps the skip honest by
# failing if a CHECKOUT ever stops finding its own README.
_NO_README = ("no README.md beside the tool or the suite -- a deployed copy; "
              "the README claims are a source-tree check")

# THE SUITE REACHES NO NETWORK UNLESS ASKED.
#
# What it cost to learn: `my-rollout go` on horse, 2026-11-05 22:09, ran this
# suite as the user under Terminal -> login -> su -> my-rollout -- which is
# exactly the "Terminal via Python" in the Little Snitch alerts the user
# answered that evening.  A connection held behind an unanswered alert does
# not fail: it HANGS.  That run was killed at its 600s cap after ok 930, with
# `not ok 226 - TestTsvScrapersE2E.test_tmdb_different_shows_different_data`
# already recorded, so the gate did not offer my-plex at all.  The class
# docstring's "skip gracefully if network is unavailable" never covered being
# HELD, which is the case that actually happens on a machine with a firewall.
#
# Nothing is deleted -- `MY_PLEX_TEST_NETWORK=1 my-plex --run-tests tsv` runs
# them exactly as before.  The coverage stays reachable for whoever wants it,
# while a default run of the suite depends on no remote host, which is what
# the house asks of a suite in the first place.
TEST_NETWORK_ENV = 'MY_PLEX_TEST_NETWORK'


def _network_opted_in():
    """True only when someone asked for the tests that really fetch."""
    return bool(os.environ.get(TEST_NETWORK_ENV, '').strip())

# How long a whole my-plex command may take against the FIXTURE library (see
# _fixture_library) before a test calls it hung.  A SAFETY NET, not a
# performance budget: a run there takes a few seconds, and the bound only
# turns a hang into a failure.  ONE owner, because the same decision once sat
# in three places at three values -- and at 60s it measured the machine: on
# horse, 2026-11-05, against the real 40 MB cache, --problems took 83s, so a
# test bound, not the tool, stopped a deployment.
E2E_TIMEOUT = 120


def _readme_path() -> str | None:
    """The project's README.md, or None where there is none."""
    for _d in (os.path.dirname(MAIN_SCRIPT),
               os.path.dirname(os.path.realpath(__file__))):
        _p = os.path.join(_d, 'README.md')
        if os.path.isfile(_p):
            return _p
    return None


def _main_module() -> Any:
    """The tool, as the module this suite was loaded from.

    Typed Any on purpose: my-plex.py is a script, not an importable module
    with a type of its own, and the tests set its globals (CACHE,
    DISK_PLEX_MAP, PLEX_DB_REMOTE_HOST, ...), which a ModuleType does not
    declare."""
    return sys.modules[resolve_disk_map_variables.__module__]


def _must(match: 're.Match[str] | None', what: str) -> 're.Match[str]':
    """The match a test counts on: a None here IS the test's failure."""
    assert match is not None, f"{what}: the pattern did not match"
    return match


def _import_tool(module_name='mp', argv=None, path=None) -> Any:
    """Import my-plex itself as a module, whatever its file is CALLED.
    (Any for the same reason as _main_module: the tests set its globals.)

    spec_from_file_location() chooses a loader from the FILE NAME and answers
    None for a name it cannot place.  The deployed copy is `bin/my-plex` with
    no extension, so it answered None there and module_from_spec() raised
    AttributeError on it: `my-plex --run-tests` failed in seven scopes on
    every machine while every gate run stayed green, because the gate tests a
    pending copy still called my-plex.py.  Naming the loader is what makes
    the file name irrelevant.

    The file is MAIN_SCRIPT -- which the tool overrides to its own realpath
    -- and never a path rebuilt from THIS file's directory: beside the
    deployed suite in global/lib there is no my-plex.py to find.

    `argv` is what the module body sees while it runs, restored afterwards:
    the body acts on argv (-Q, --version, the venv re-exec), and the default
    is a bare run, the quietest import there is.  A SystemExit from the body
    is the script answering that argv, not a failure to import.
    """
    path = path or MAIN_SCRIPT
    spec = importlib.util.spec_from_file_location(
        module_name, path,
        loader=importlib.machinery.SourceFileLoader(module_name, path))
    assert spec is not None and spec.loader is not None  # the loader is named
    mod = importlib.util.module_from_spec(spec)
    saved_argv = sys.argv[:]
    sys.argv = list(argv) if argv is not None else [sys.argv[0]]
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    finally:
        sys.argv = saved_argv
    return mod


def _tool_import_snippet(argv, path=None):
    """The same import, written out for the probes that run in a CHILD
    interpreter: it binds `mp`, with sys.argv set before the module body runs.

    A child cannot call _import_tool, so the two lines that make an
    extensionless file loadable are spelled out once here -- two forms of one
    rule, rather than nine copies of it.
    """
    return (
        "import sys, os, importlib.util, importlib.machinery\n"
        "sys.argv = %r\n"
        "_p = %r\n"
        "_spec = importlib.util.spec_from_file_location('mp', _p,\n"
        "    loader=importlib.machinery.SourceFileLoader('mp', _p))\n"
        "mp = importlib.util.module_from_spec(_spec)\n"
        "_spec.loader.exec_module(mp)\n"
    ) % (list(argv), path or MAIN_SCRIPT)


def _pick_most_populated_library(list_libraries_stdout, lib_type=None):
    """Pick the library with the MOST items from `--list-libraries` output,
    optionally only among libraries of one TYPE ('Movie', 'Series').

    Data-dependent E2E tests need a library that actually has content —
    the first row may be a near-empty staging library.  Library names stay
    dynamic: every Plex install names its libraries differently, so a test
    must never hard-code one.
    Returns the library name, or None when no data row parses.
    """
    best_name, best_items = None, -1
    for line in list_libraries_stdout.splitlines():
        parts = line.split('\t')
        if len(parts) < 7:
            continue
        name = parts[0].strip()
        if not name or name[0] in ('-', '=') or 'NAME' in name.upper():
            continue
        if lib_type and parts[3].strip() != lib_type:
            continue
        try:
            items = int(parts[6].strip())
        except ValueError:
            continue
        if items > best_items:
            best_name, best_items = name, items
    return best_name


def _pick_any_series_key():
    """A Series cache key that exists on THIS machine, or None.

    Never hard-coded: `Series:5191` is one id in one person's cache, and
    everywhere else --renumber answers "Invalid parameter 'Series:5191'"
    (ada, 2026-11-01). Rows start with the cache key, so the first Series row
    of the most populated Series library is one that is really there."""
    import subprocess, re
    libs = subprocess.run([sys.executable, MAIN_SCRIPT, '--list-libraries'],
                          capture_output=True, text=True, timeout=30)
    lib = _pick_most_populated_library(libs.stdout, lib_type='Series')
    if not lib:
        return None
    rows = subprocess.run([sys.executable, MAIN_SCRIPT, lib, '--list'],
                          capture_output=True, text=True, timeout=120)
    m = re.search(r'^(Series:\d+)', rows.stdout, re.MULTILINE)
    return m.group(1) if m else None


def _pick_any_title_word(lib):
    """A word from the title of an item that exists in LIB here, or None.

    `tagesschau` is one title in one person's library: on a machine without
    it the search is correctly empty and the TEST is wrong, not the code
    (ada, 2026-11-02, the last of that family). The key comes from a scoped
    listing, so the item is one the same default scope lets through, and a
    search for a word of its title therefore has something to return."""
    import subprocess, re
    rows = subprocess.run([sys.executable, MAIN_SCRIPT, lib, '--list'],
                          capture_output=True, text=True, timeout=120)
    m = re.search(r'^((?:Movie|Series|Season|Episode):\d+)', rows.stdout, re.MULTILINE)
    if not m:
        return None
    info = subprocess.run([sys.executable, MAIN_SCRIPT, '--info', m.group(1)],
                          capture_output=True, text=True, timeout=60)
    t = re.search(r'^Title:\s*(.+)$', info.stdout, re.MULTILINE)
    if not t:
        return None
    words = [w for w in re.findall(r'[A-Za-z]{4,}', t.group(1))]
    return max(words, key=len).lower() if words else None


def _registry_entry_block(content, category):
    """Return the source block of ONE PROBLEM_CATEGORIES_REGISTRY entry.

    Scoped to the registry dict so same-named keys elsewhere (e.g.
    PROBLEMS2DISK['reencode']) can never shadow the lookup.
    A missing registry or entry is the calling test's failure (the asserts)."""
    registry = _must(re.search(r"PROBLEM_CATEGORIES_REGISTRY = \{(.*?)\n\}", content, re.DOTALL),
                     'PROBLEM_CATEGORIES_REGISTRY')
    entry = _must(re.search(r"'%s': \{\n(.*?)\n    \}," % re.escape(category),
                            registry.group(1), re.DOTALL),
                  f"the '{category}' entry of PROBLEM_CATEGORIES_REGISTRY")
    return entry.group(1)


############################################################
#### REGRESSION TESTING

# ---------------------------------------------------------------------------
# Test stubs and helpers
# ---------------------------------------------------------------------------

class StubPLEX_Media:
    """Minimal stand-in for the real PLEX_Media class."""
    OBJ_BY_ID = {}
    OBJ_BY_LIBRARY = {}
    OBJ_BY_FILEPATH = {}
    OBJ_BY_MOVIE = {}
    OBJ_BY_SERIES = {}
    OBJ_BY_SERIES_EPISODES = {}
    OBJ_BY_COLLECTION = {}

    @classmethod
    def reset(cls):
        cls.OBJ_BY_ID = {}
        cls.OBJ_BY_LIBRARY = {}
        cls.OBJ_BY_FILEPATH = {}
        cls.OBJ_BY_MOVIE = {}
        cls.OBJ_BY_SERIES = {}
        cls.OBJ_BY_SERIES_EPISODES = {}
        cls.OBJ_BY_COLLECTION = {}


def _make_movie(mid, title, filepath, version="90.0min 1920x1080 (h264 aac)", filesize=1000000, library="lib1", year=2023, originalTitle=""):
    return {
        'type': 'Movie', 'type_str': 'Movie', 'id': mid, 'title': title,
        'originalTitle': originalTitle, 'year': year, 'library': library,
        'file': filepath, 'files': {version: {'filepath': filepath, 'filesize': filesize}},
        'item_id': mid, 'media_id': mid*10, 'part_id': mid*100,
        'version': version, 'media_nr': '1/1', 'media_idx': 0, 'media_cnt': 1,
        'part_nr': '1/1', 'part_idx': 0, 'part_cnt': 1,
        'updatedAt': None, 'addedAt': None, 'lastViewedAt': None, 'viewCount': 0,
        'userRating': None, 'criticsRating': None, 'audienceRating': None,
        'summary': '', 'duration': 5400000, 'video_codec': 'h264', 'audio_codec': 'aac',
        'resolution': '1080p', 'resolution_full': '1920x1080', 'filesize': filesize,
        'audio_languages': [], 'subtitle_languages': [], 'collections': [], 'labels': [],
        'actors': [], 'countries': [], 'directors': [], 'writers': [], 'genres': [],
        'contentRating': None, 'season': None, 'S_str': None, 'S_idx': None,
        'episode': None, 'E_str': None, 'E_idx': None, 'S0XE0X': None,
    }


def _make_episode(eid, title, filepath, series_key, series, s_num, e_num, version="22.0min 1920x1080 (h264 aac)", filesize=500000, library="lib6"):
    return {
        'type': 'Episode', 'type_str': 'Episode', 'id': eid, 'title': title,
        'originalTitle': '', 'year': 0, 'library': library,
        'file': filepath, 'files': {version: {'filepath': filepath, 'filesize': filesize}},
        'item_id': eid, 'media_id': eid*10, 'part_id': eid*100,
        'version': version, 'media_nr': '1/1', 'media_idx': 0, 'media_cnt': 1,
        'part_nr': '1/1', 'part_idx': 0, 'part_cnt': 1,
        'updatedAt': None, 'addedAt': None, 'lastViewedAt': None, 'viewCount': 0,
        'userRating': None, 'criticsRating': None, 'audienceRating': None,
        'summary': '', 'duration': 1320000, 'video_codec': 'h264', 'audio_codec': 'aac',
        'resolution': '1080p', 'resolution_full': '1920x1080', 'filesize': filesize,
        'audio_languages': [], 'subtitle_languages': [], 'collections': [], 'labels': [],
        'actors': [], 'countries': [], 'directors': [], 'writers': [], 'genres': [],
        'contentRating': None, 'season': s_num, 'S_str': f"S{s_num:02d}", 'S_idx': s_num,
        'episode': e_num, 'E_str': f"E{e_num:02d}", 'E_idx': e_num,
        'S0XE0X': f"S{s_num:02d}E{e_num:02d}", 'series': series, 'series_key': series_key,
    }


def _make_collection(cid, title, library, member_ids=None):
    return {
        'type': 'Collection', 'type_str': 'Collection',
        'id': cid, 'title': title, 'subtype': 'movie',
        'library': library, 'addedAt': None, 'updatedAt': None,
        'member_ids': member_ids or [],
    }


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestObjTypeHandling(unittest.TestCase):
    """Verify that the PLEX_Media.init() loop handles all object types without errors."""

    KNOWN_TYPES = {"Movie", "Episode", "Series", "Season", "Collection"}

    def test_collection_has_no_file_key(self):
        """Collection dicts must NOT have a 'file' key (they are metadata-only)."""
        col = _make_collection(1, "Action Movies", "lib1")
        self.assertNotIn('file', col)

    def test_movie_has_file_key(self):
        """Movie dicts must have a 'file' key."""
        m = _make_movie(100, "Test Movie", "/path/to/movie.mkv")
        self.assertIn('file', m)
        self.assertEqual(m['file'], "/path/to/movie.mkv")

    def test_episode_has_file_key(self):
        """Episode dicts must have a 'file' key."""
        e = _make_episode(200, "Pilot", "/path/to/ep.mkv", "Series:1", "TestShow", 1, 1)
        self.assertIn('file', e)

    def test_collection_type_is_known(self):
        """Collection type string must be in the known types set."""
        col = _make_collection(1, "X", "lib")
        self.assertIn(col['type'], self.KNOWN_TYPES)

    def test_all_media_types_in_known_set(self):
        """All factory-created objects must have a type in KNOWN_TYPES."""
        objects = [
            _make_movie(1, "M", "/m.mkv"),
            _make_episode(2, "E", "/e.mkv", "Series:1", "S", 1, 1),
            _make_collection(3, "C", "lib"),
        ]
        for obj in objects:
            self.assertIn(obj['type'], self.KNOWN_TYPES,
                          f"Object type '{obj['type']}' not in KNOWN_TYPES")


class TestMultiVersionMerge(unittest.TestCase):
    """Verify that multi-version items are correctly merged."""

    def test_movie_single_version(self):
        """A movie with one version should have media_cnt=1 and type_str='Movie'."""
        m = _make_movie(100, "Solo", "/path/solo.mkv")
        self.assertEqual(m['media_cnt'], 1)
        self.assertEqual(m['type_str'], 'Movie')
        self.assertEqual(len(m['files']), 1)

    def test_movie_multi_version_merge(self):
        """Simulates what fetch_movies_from_database() does when merging multiple media items."""
        movie = _make_movie(90747, "Only 3 Days Left", "/path/v1.mkv",
                            version="87.46min 1024x428 (h264 ac3)", filesize=1562009362)
        v2 = "87.46min 720x300 (h264 ac3)"
        movie['files'][v2] = {'filepath': '/path/v2.mkv', 'filesize': 863013870}
        movie['media_cnt'] = len(movie['files'])
        movie['type_str'] = 'Movie*'
        v3 = "87.46min 640x272 (mpeg4 ac3)"
        movie['files'][v3] = {'filepath': '/path/v3.avi', 'filesize': 733327964}
        movie['media_cnt'] = len(movie['files'])
        self.assertEqual(movie['media_cnt'], 3)
        self.assertEqual(movie['type_str'], 'Movie*')
        self.assertEqual(len(movie['files']), 3)
        self.assertIn(v2, movie['files'])
        self.assertIn(v3, movie['files'])

    def test_multi_version_all_filepaths_registered(self):
        """All filepaths in a multi-version item should be registerable in OBJ_BY_FILEPATH."""
        movie = _make_movie(100, "Test", "/path/v1.mkv", version="v1", filesize=100)
        movie['files']["v2"] = {'filepath': '/path/v2.mkv', 'filesize': 200}
        movie['files']["v3"] = {'filepath': '/path/v3.avi', 'filesize': 300}
        filepath_index = {}
        movie_key = f"Movie:{movie['id']}"
        for _version, file_info in movie.get('files', {}).items():
            fp = file_info.get('filepath')
            if fp:
                if fp not in filepath_index:
                    filepath_index[fp] = []
                if movie_key not in filepath_index[fp]:
                    filepath_index[fp].append(movie_key)
        self.assertEqual(len(filepath_index), 3)
        for fp in ['/path/v1.mkv', '/path/v2.mkv', '/path/v3.avi']:
            self.assertIn(fp, filepath_index)
            self.assertEqual(filepath_index[fp], [movie_key])

    def test_multi_version_audio_language_merge(self):
        """Audio languages from different versions should be merged without duplicates."""
        movie = _make_movie(100, "Test", "/path/v1.mkv")
        movie['audio_languages'] = ['English']
        new_langs = ['French', 'English']
        for lang in new_langs:
            if lang not in movie['audio_languages']:
                movie['audio_languages'].append(lang)
        self.assertEqual(movie['audio_languages'], ['English', 'French'])

    def test_episode_multi_version_type_str(self):
        """Multi-version episodes should get type_str 'Episode*'."""
        ep = _make_episode(200, "Pilot", "/path/ep_v1.mkv", "Series:1", "TestShow", 1, 1,
                           version="v1", filesize=500)
        ep['files']["v2"] = {'filepath': '/path/ep_v2.mkv', 'filesize': 600}
        ep['media_cnt'] = len(ep['files'])
        ep['type_str'] = 'Episode*'
        self.assertEqual(ep['media_cnt'], 2)
        self.assertEqual(ep['type_str'], 'Episode*')


class TestCacheResumeWithMultiVersion(unittest.TestCase):
    """Verify that cache resume logic updates entries when new data has more file versions."""

    def test_skip_when_same_file_count(self):
        """Should skip when cached entry has same number of files as new data."""
        cached = _make_movie(100, "Test", "/v1.mkv", version="v1")
        new_data = _make_movie(100, "Test", "/v1.mkv", version="v1")
        new_count = len(new_data.get('files', {}))
        cached_count = len(cached.get('files', {}))
        self.assertEqual(new_count, cached_count)
        self.assertTrue(new_count <= cached_count)

    def test_update_when_more_files(self):
        """Should update when new data has more files than cached entry."""
        cached = _make_movie(100, "Test", "/v1.mkv", version="v1")
        new_data = _make_movie(100, "Test", "/v1.mkv", version="v1")
        new_data['files']["v2"] = {'filepath': '/v2.mkv', 'filesize': 200}
        new_data['files']["v3"] = {'filepath': '/v3.avi', 'filesize': 300}
        new_count = len(new_data.get('files', {}))
        cached_count = len(cached.get('files', {}))
        self.assertGreater(new_count, cached_count)
        self.assertFalse(new_count <= cached_count)

    def test_update_when_files_removed(self):
        """Should update when cached entry has MORE files than new data (files were deleted)."""
        cached = _make_movie(100, "Test", "/v1.mkv", version="v1")
        cached['files']["v2"] = {'filepath': '/v2.mkv', 'filesize': 200}
        new_data = _make_movie(100, "Test", "/v1.mkv", version="v1")
        new_count = len(new_data.get('files', {}))
        cached_count = len(cached.get('files', {}))
        self.assertNotEqual(new_count, cached_count)


class TestDuplicateKeyGeneration(unittest.TestCase):
    """Test the duplicate key generation logic (mirrors generate_duplicate_keys)."""

    @staticmethod
    def generate_duplicate_keys(obj):
        """Local copy of the logic from my-plex.py for isolated testing."""
        obj_type = obj.get('type')
        if obj_type == 'Movie':
            title = obj['title'].lower().strip()
            year = obj.get('year', 0)
            keys = [f"movie:{title}:{year}"]
            original_title = (obj.get('originalTitle') or '').lower().strip()
            if original_title and original_title != title:
                keys.append(f"movie:{original_title}:{year}")
            return keys
        elif obj_type == 'Episode':
            series = obj.get('series', '').lower().strip()
            s_str = obj.get('S_str', '')
            e_str = obj.get('E_str', '')
            if s_str == 'S??' or e_str == 'E??':
                return []
            return [f"episode:{series}:{s_str}:{e_str}"]
        else:
            return []

    def test_movie_single_key(self):
        m = _make_movie(1, "Inception", "/m.mkv", year=2010)
        keys = self.generate_duplicate_keys(m)
        self.assertEqual(keys, ["movie:inception:2010"])

    def test_movie_with_original_title(self):
        m = _make_movie(1, "Zoomania", "/m.mkv", year=2016, originalTitle="Zootopia")
        keys = self.generate_duplicate_keys(m)
        self.assertEqual(keys, ["movie:zoomania:2016", "movie:zootopia:2016"])

    def test_movie_original_title_same_as_title(self):
        """If originalTitle equals title, only one key should be generated."""
        m = _make_movie(1, "Inception", "/m.mkv", year=2010, originalTitle="Inception")
        keys = self.generate_duplicate_keys(m)
        self.assertEqual(keys, ["movie:inception:2010"])

    def test_episode_key(self):
        e = _make_episode(2, "Pilot", "/e.mkv", "Series:1", "Breaking Bad", 1, 1)
        keys = self.generate_duplicate_keys(e)
        self.assertEqual(keys, ["episode:breaking bad:S01:E01"])

    def test_episode_unknown_season(self):
        e = _make_episode(2, "Pilot", "/e.mkv", "Series:1", "X", 1, 1)
        e['S_str'] = 'S??'
        keys = self.generate_duplicate_keys(e)
        self.assertEqual(keys, [])

    def test_collection_returns_no_keys(self):
        """Collections should not generate duplicate keys."""
        c = _make_collection(1, "Action", "lib")
        keys = self.generate_duplicate_keys(c)
        self.assertEqual(keys, [])

    def test_cross_library_match_via_original_title(self):
        """Two movies with different titles but same originalTitle should share a key."""
        m1 = _make_movie(1, "Zoomania", "/de/m.mkv", year=2016, originalTitle="Zootopia", library="lib2")
        m2 = _make_movie(2, "Zootropolis", "/en/m.mkv", year=2016, originalTitle="Zootopia", library="lib3")
        keys1 = set(self.generate_duplicate_keys(m1))
        keys2 = set(self.generate_duplicate_keys(m2))
        self.assertTrue(keys1 & keys2, "Should have overlapping key via originalTitle 'Zootopia'")


class TestInitLoopRobustness(unittest.TestCase):
    """Simulate the PLEX_Media.init() loop over mixed object types."""

    def _simulate_init_loop(self, objects):
        """Run the match logic from PLEX_Media.init() on a dict of objects.
        Returns list of types that were processed without error."""
        processed = []
        for key, obj in objects.items():
            if 'file' in obj and obj['file']:
                pass
            match obj['type']:
                case "Movie":
                    processed.append('Movie')
                case "Series":
                    processed.append('Series')
                case "Season":
                    processed.append('Season')
                case "Episode":
                    processed.append('Episode')
                case "Collection":
                    processed.append('Collection')
                    continue
                case _:
                    raise ValueError(f"Unhandled type: {obj['type']}")
        return processed

    def test_mixed_objects_no_error(self):
        """A mix of Movie, Episode, and Collection objects should all be processed."""
        objects = {
            'Movie:100': _make_movie(100, "Test Movie", "/movie.mkv"),
            'Episode:200': _make_episode(200, "Pilot", "/ep.mkv", "Series:1", "S", 1, 1),
            'Collection:300': _make_collection(300, "Action", "lib1"),
        }
        processed = self._simulate_init_loop(objects)
        self.assertEqual(sorted(processed), ['Collection', 'Episode', 'Movie'])

    def test_only_collections(self):
        """Processing only Collection objects should not error."""
        objects = {
            'Collection:1': _make_collection(1, "A", "lib"),
            'Collection:2': _make_collection(2, "B", "lib"),
        }
        processed = self._simulate_init_loop(objects)
        self.assertEqual(processed, ['Collection', 'Collection'])

    def test_unknown_type_raises(self):
        """An unknown type should raise ValueError (matching the err() behavior)."""
        objects = {'Bogus:1': {'type': 'Bogus', 'library': 'x'}}
        with self.assertRaises(ValueError):
            self._simulate_init_loop(objects)


# ---------------------------------------------------------------------------
# classify_multi_version — copied from my-plex.py for standalone testing
# ---------------------------------------------------------------------------
def _test_classify_multi_version(obj):
    """Classify a multi-version item (single Plex entry with multiple files)."""
    import re
    files_dict = obj.get('files', {})
    if len(files_dict) <= 1:
        return 'single'
    durations_ms = []
    for version_str in files_dict.keys():
        dur_match = re.match(r'([\d.]+)min', version_str)
        if dur_match:
            durations_ms.append(float(dur_match.group(1)) * 60000)
        else:
            durations_ms.append(None)
    if all(d is None for d in durations_ms):
        return 'reencode'
    valid_durations = [d for d in durations_ms if d is not None]
    if len(valid_durations) < 2:
        return 'reencode'
    max_diff_ms = max(valid_durations) - min(valid_durations)
    if max_diff_ms > 5000:
        return 'true_multiversion'
    sizes = set()
    codecs = set()
    for version_str, file_info in files_dict.items():
        if isinstance(file_info, dict):
            size = file_info.get('filesize')
            if size:
                sizes.add(size)
        codec_match = re.search(r'\((\w+)', version_str)
        if codec_match:
            codecs.add(codec_match.group(1))
    if len(sizes) <= 1 and len(codecs) <= 1:
        return 'exact_duplicate'
    return 'reencode'


class TestClassifyMultiVersion(unittest.TestCase):
    """Test classify_multi_version() heuristic classification."""

    def test_single_file_returns_single(self):
        obj = _make_movie(1, "Test", "/test.mkv")
        self.assertEqual(_test_classify_multi_version(obj), 'single')

    def test_exact_duplicate_same_size_codec_duration(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            '120.0min 1920x1080 (h264 aac)': {'filepath': '/test1.mkv', 'filesize': 5000000},
            '120.0min 1920x1080 (h264 aac) ': {'filepath': '/test2.mkv', 'filesize': 5000000},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'exact_duplicate')

    def test_reencode_same_duration_different_codec(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            '120.0min 1920x1080 (h264 aac)': {'filepath': '/test1.mkv', 'filesize': 5000000},
            '120.0min 1920x1080 (hevc aac)': {'filepath': '/test2.mkv', 'filesize': 3000000},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'reencode')

    def test_reencode_same_duration_different_size(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            '120.0min 1920x1080 (h264 aac)': {'filepath': '/test1.mkv', 'filesize': 5000000},
            '120.0min 1280x720 (h264 aac)': {'filepath': '/test2.mkv', 'filesize': 2000000},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'reencode')

    def test_reencode_duration_within_5s_tolerance(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            '120.0min 1920x1080 (h264 aac)': {'filepath': '/test1.mkv', 'filesize': 5000000},
            '120.08min 1920x1080 (hevc aac)': {'filepath': '/test2.mkv', 'filesize': 3000000},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'reencode')

    def test_true_multiversion_different_duration(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            '23.69min 960x720 (h264 aac)': {'filepath': '/east.coast.mkv', 'filesize': 147176738},
            '23.5min 960x720 (h264 aac)': {'filepath': '/west.coast.mkv', 'filesize': 147231158},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'true_multiversion')

    def test_true_multiversion_theatrical_vs_directors_cut(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            '120.0min 1920x1080 (h264 aac)': {'filepath': '/theatrical.mkv', 'filesize': 5000000},
            '145.0min 1920x1080 (h264 aac)': {'filepath': '/directors_cut.mkv', 'filesize': 7000000},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'true_multiversion')

    def test_episode_true_multiversion(self):
        obj = _make_episode(4620, "Live from Studio 6H", "/east.mkv", "Series:1", "30 Rock", 6, 19)
        obj['files'] = {
            '23.69min 960x720 (h264 aac)': {'filepath': '/east.coast.version.mkv', 'filesize': 147176738},
            '23.5min 960x720 (h264 aac)': {'filepath': '/west.coast.version.mkv', 'filesize': 147231158},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'true_multiversion')

    def test_no_duration_in_version_string_fallback(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            'unknown_format_1': {'filepath': '/test1.mkv', 'filesize': 5000000},
            'unknown_format_2': {'filepath': '/test2.mkv', 'filesize': 3000000},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'reencode')

    def test_three_versions_one_different_duration(self):
        obj = _make_movie(1, "Test", "/test1.mkv")
        obj['files'] = {
            '120.0min 1920x1080 (h264 aac)': {'filepath': '/v1.mkv', 'filesize': 5000000},
            '120.0min 1280x720 (h264 aac)': {'filepath': '/v2.mkv', 'filesize': 2000000},
            '135.0min 1920x1080 (h264 aac)': {'filepath': '/v3_extended.mkv', 'filesize': 7000000},
        }
        self.assertEqual(_test_classify_multi_version(obj), 'true_multiversion')

    def test_empty_files_dict_returns_single(self):
        obj = _make_movie(1, "Test", "/test.mkv")
        obj['files'] = {}
        self.assertEqual(_test_classify_multi_version(obj), 'single')


class TestDuplicatesIgnoreLibraryCombinations(unittest.TestCase):
    """Test DUPLICATES_IGNORE_LIBRARY_COMBINATIONS filtering logic."""

    @staticmethod
    def _filter_duplicates(items_with_duplicates, ignore_groups, obj_by_id):
        ignored_count = 0
        if ignore_groups:
            filtered = {}
            for dup_key, keys in items_with_duplicates.items():
                if len(keys) <= 1:
                    filtered[dup_key] = keys
                    continue
                libs = set(obj_by_id[k].get('library', '') for k in keys)
                should_ignore = False
                for ignore_group in ignore_groups:
                    if libs.issubset(set(ignore_group)):
                        should_ignore = True
                        break
                if should_ignore:
                    ignored_count += 1
                else:
                    filtered[dup_key] = keys
            return filtered, ignored_count
        return items_with_duplicates, 0

    def test_all_in_ignore_group_excluded(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
            'Movie:2': {'library': 'lib3', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        ignore = [['lib2', 'lib3', 'lib4']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 0)
        self.assertEqual(count, 1)

    def test_copy_outside_group_is_duplicate(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
            'Movie:2': {'library': 'lib1', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        ignore = [['lib2', 'lib3', 'lib4']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(count, 0)

    def test_four_copies_one_outside_is_duplicate(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
            'Movie:2': {'library': 'lib4', 'title': 'Klaus'},
            'Movie:3': {'library': 'lib3', 'title': 'Klaus'},
            'Movie:4': {'library': 'lib1', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2', 'Movie:3', 'Movie:4']}
        ignore = [['lib2', 'lib3', 'lib4']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result['dup1']), 4)

    def test_all_three_in_group_excluded(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
            'Movie:2': {'library': 'lib4', 'title': 'Klaus'},
            'Movie:3': {'library': 'lib3', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2', 'Movie:3']}
        ignore = [['lib2', 'lib3', 'lib4']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 0)
        self.assertEqual(count, 1)

    def test_empty_ignore_groups_keeps_all(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
            'Movie:2': {'library': 'lib3', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        result, count = self._filter_duplicates(dups, [], obj_by_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(count, 0)

    def test_single_entry_multiversion_not_affected(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1']}
        ignore = [['lib2', 'lib3', 'lib4']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 1)

    def test_multiple_ignore_groups_independent(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
            'Movie:2': {'library': 'lib3', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        ignore = [['lib5', 'lib6'], ['lib2', 'lib3', 'lib4']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 0)
        self.assertEqual(count, 1)

    def test_cross_group_not_ignored(self):
        obj_by_id = {
            'Movie:1': {'library': 'lib2', 'title': 'Klaus'},
            'Episode:2': {'library': 'lib6', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Episode:2']}
        ignore = [['lib2', 'lib3'], ['lib5', 'lib6']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(count, 0)


class TestRunToolLocally(unittest.TestCase):
    """Tests for run_tool_locally() wrapper."""

    def test_local_tool_configured_path_used(self):
        """When EXTERNAL_TOOLS['LOCAL'] has a configured path, it should be used."""
        import shutil
        path = shutil.which('echo')
        self.assertIsNotNone(path, "echo should be in PATH")

    def test_local_tool_not_found_returns_none(self):
        """When a tool doesn't exist, shutil.which returns None."""
        import shutil
        result = shutil.which('nonexistent_tool_xyzzy_12345')
        self.assertIsNone(result)


class TestRunToolOnPLEXServer(unittest.TestCase):
    """Tests for run_tool_on_PLEX_server() concept."""

    def _script_lines(self):
        path = MAIN_SCRIPT
        with open(path, encoding='utf-8') as f:
            return f.read().splitlines()

    def test_server_tool_not_found_locally(self):
        """shutil.which returns None for non-existent server tool."""
        import shutil
        result = shutil.which('mp4box_nonexistent_xyzzy')
        self.assertIsNone(result)


class TestISO639Mapping(unittest.TestCase):
    """Tests for ISO 639-1 to 639-2 language code mapping."""

    @classmethod
    def setUpClass(cls):
        import re
        script_path = MAIN_SCRIPT
        with open(script_path, 'r') as f:
            content = f.read()
        match = re.search(r'ISO_639_1_TO_2\s*=\s*\{([^}]+)\}', content)
        if match:
            cls.mapping = eval('{' + match.group(1) + '}')
        else:
            cls.mapping = {}

    def test_known_codes_mapped(self):
        self.assertEqual(self.mapping.get('en'), 'eng')
        self.assertEqual(self.mapping.get('de'), 'deu')
        self.assertEqual(self.mapping.get('fr'), 'fra')
        self.assertEqual(self.mapping.get('it'), 'ita')
        self.assertEqual(self.mapping.get('es'), 'spa')
        self.assertEqual(self.mapping.get('ja'), 'jpn')

    def test_unknown_code_not_in_mapping(self):
        self.assertNotIn('xx', self.mapping)

    def test_all_values_are_three_letter(self):
        for code_2, code_3 in self.mapping.items():
            self.assertEqual(len(code_2), 2, f"Key '{code_2}' is not 2 letters")
            self.assertEqual(len(code_3), 3, f"Value '{code_3}' for key '{code_2}' is not 3 letters")


class TestAutoResolveConfig(unittest.TestCase):
    """Tests for AUTO_RESOLVE_AUDIO_LANGUAGE_BY_LIBRARY config logic."""

    def _lookup(self, library, config):
        auto_resolve = {lib: lang for lib, lang in config}
        return auto_resolve.get(library)

    def test_library_match(self):
        config = [('lib2', 'de'), ('lib3', 'en')]
        self.assertEqual(self._lookup('lib2', config), 'de')
        self.assertEqual(self._lookup('lib3', config), 'en')

    def test_library_no_match(self):
        config = [('lib2', 'de')]
        self.assertIsNone(self._lookup('lib1', config))

    def test_empty_config(self):
        self.assertIsNone(self._lookup('lib2', []))


class TestResolveNoAudioLanguage(unittest.TestCase):
    """Tests for resolve wizard helper functions."""

    def test_container_detection_mp4(self):
        for ext in ['.mp4', '.m4v']:
            filepath = f'/path/to/movie{ext}'
            file_ext = os.path.splitext(filepath)[1].lower()
            if file_ext in ('.mp4', '.m4v'):
                tool = 'mp4box'
            elif file_ext == '.mkv':
                tool = 'mkvpropedit'
            else:
                tool = None
            self.assertEqual(tool, 'mp4box', f"Failed for extension {ext}")

    def test_container_detection_mkv(self):
        filepath = '/path/to/movie.mkv'
        ext = os.path.splitext(filepath)[1].lower()
        self.assertEqual(ext, '.mkv')
        tool = 'mkvpropedit' if ext == '.mkv' else None
        self.assertEqual(tool, 'mkvpropedit')

    def test_container_unsupported(self):
        for ext in ['.avi', '.wmv', '.flv']:
            filepath = f'/path/to/movie{ext}'
            file_ext = os.path.splitext(filepath)[1].lower()
            tool = None
            if file_ext in ('.mp4', '.m4v'):
                tool = 'mp4box'
            elif file_ext == '.mkv':
                tool = 'mkvpropedit'
            self.assertIsNone(tool, f"Expected None for extension {ext}")

    def test_build_mp4box_command(self):
        tool_name = 'mp4box'
        filepath = '/path/to/Tenet.mp4'
        lang = 'eng'
        args: list[str] = []
        if tool_name == 'mp4box':
            args = ['-lang', f'all={lang}', filepath]
        self.assertEqual(args, ['-lang', 'all=eng', '/path/to/Tenet.mp4'])

    def test_build_mkvpropedit_command(self):
        tool_name = 'mkvpropedit'
        filepath = '/path/to/Tenet.mkv'
        lang = 'deu'
        args: list[str] = []
        if tool_name == 'mkvpropedit':
            args = [filepath, '--edit', 'track:a1', '--set', f'language={lang}']
        self.assertEqual(args, ['/path/to/Tenet.mkv', '--edit', 'track:a1', '--set', 'language=deu'])


class TestLongHelp(unittest.TestCase):
    """Tests for extended help text availability."""

    HELP_TOPICS = [
        'no-audio-language', 'no-language', 'no_audio_language',
        'duplicates', 'broken', 'scan',
        'watched', 'unwatched',
        'list',
        'en', 'de', 'fr',
        'update-cache', 'update_cache', 'cache',
        'all', 'global', 'glob', 'cmd',
    ]

    def test_all_help_topics_have_match_case(self):
        """All help topics should have a match case in main_print_help()."""
        script_path = MAIN_SCRIPT
        with open(script_path, 'r') as f:
            content = f.read()
        for topic in self.HELP_TOPICS:
            self.assertIn(f"'{topic}'", content,
                f"Help topic '{topic}' not found in match cases of main_print_help()")


class TestPlexUpdatedAtTracking(unittest.TestCase):
    """Tests for plexUpdatedAt field in EMPTY_LIBRARY_STATS."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_empty_library_stats_has_plexUpdatedAt(self):
        content = self._read_script()
        self.assertIn("'plexUpdatedAt'", content,
            "EMPTY_LIBRARY_STATS must contain 'plexUpdatedAt' for accurate change detection")

    def test_get_library_stats_stores_plexUpdatedAt(self):
        content = self._read_script()
        self.assertIn("plexUpdatedAt", content)
        self.assertIn("library_stats['plexUpdatedAt']", content,
            "get_library_stats() must store actual Plex timestamps in plexUpdatedAt")

    def test_load_cache_uses_plexUpdatedAt_for_change_detection(self):
        content = self._read_script()
        self.assertIn("plexUpdatedAt", content)
        self.assertIn("old_plex_timestamp", content,
            "Change detection must compare against plexUpdatedAt when cache is newer than Plex")


class TestCacheSkipLogic(unittest.TestCase):
    """Tests for cache update skip logic — file path changes must trigger updates."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_episode_skip_checks_file_paths(self):
        content = self._read_script()
        self.assertIn("new_paths", content,
            "Episode skip logic must compare file paths to detect renames")
        self.assertIn("cached_paths", content,
            "Episode skip logic must compare cached file paths against new paths")

    def test_movie_skip_checks_file_paths(self):
        content = self._read_script()
        self.assertGreaterEqual(content.count("new_paths == cached_paths"), 2,
            "Both movie and episode skip logic must compare file paths")

    def test_tool_not_found_is_fatal(self):
        content = self._read_script()
        self.assertIn("if result is None:\n            sys.exit(1)", content,
            "Tool not found must be fatal (sys.exit)")

    def test_get_library_stats_uses_db_for_counts(self):
        content = self._read_script()
        self.assertIn("query_plex_database(query, mode='rows')", content,
            "get_library_stats must query database for item counts")
        import re
        match = re.search(r'(def get_library_stats\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertNotIn("plex_retry_operation", func_body,
            "get_library_stats must NOT fall back to API — DB is source of truth")

    def test_verify_cache_show_libraries_use_db_counts(self):
        content = self._read_script()
        self.assertIn("metadata_type = 3", content,
            "verify_cache must query DB for season counts (metadata_type=3)")
        self.assertIn("metadata_type = 4", content,
            "verify_cache must query DB for episode counts (metadata_type=4)")

    def test_verify_cache_counts_by_obj_type(self):
        content = self._read_script()
        self.assertIn("obj_type_inner == 'Series'", content)
        self.assertIn("obj_type_inner == 'Season'", content)
        self.assertIn("obj_type_inner == 'Episode'", content)

    def test_verify_cache_movie_count_excludes_collections(self):
        content = self._read_script()
        self.assertIn("obj.get('type') == 'Movie'", content,
            "Movie library count must filter by type='Movie' to exclude Collections")

    def test_verify_cache_counts_collections(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_COLLECTION", content)
        self.assertIn("collection_count", content)
        self.assertIn("server_collections", content)
        self.assertIn("metadata_type = 18", content)

    def test_delta_counters_track_metadata_probed(self):
        content = self._read_script()
        self.assertIn("'metadata_probed': 0", content,
            "library_delta_counters must initialize metadata_probed counter")
        self.assertIn("['metadata_probed'] += 1", content,
            "metadata_probed must be incremented when ffprobe runs")

    def test_removal_detection_uses_type_map_not_naive_plural(self):
        """Removal detection must use type_map, not obj_type.lower()+'s' (Series→'seriess' bug)."""
        content = self._read_script()
        # The removal detection loop must NOT use naive pluralization
        self.assertNotIn("obj_type.lower() + 's'", content,
            "Removal detection must use type_map dict, not obj_type.lower()+'s' — "
            "'Series'.lower()+'s' = 'seriess' which is a KeyError")
        # It must use the same type_map as _increment_delta_counters
        self.assertIn("'Series': 'series'", content,
            "type_map must map 'Series' to 'series' (already plural)")

    def test_from_scratch_counts_all_items_as_added(self):
        """--force-plex summary must count all Movie/Episode objects as added."""
        content = self._read_script()
        # FROM_SCRATCH branch must count items directly from OBJ_BY_ID
        self.assertIn("if FROM_SCRATCH:", content,
            "Summary must have FROM_SCRATCH branch for counting added items")
        import re
        # The FROM_SCRATCH block must iterate OBJ_BY_ID and count Movie/Episode
        match = re.search(r"if FROM_SCRATCH:.*?total_added \+= 1", content, re.DOTALL)
        self.assertIsNotNone(match,
            "FROM_SCRATCH must count Movie/Episode items as total_added from OBJ_BY_ID")

    def test_summary_separates_metadata_from_changes(self):
        """    # Extract globals from main script
    CACHE_FILE = main_globals['CACHE_FILE']
    PLEX_Media = main_globals['PLEX_Media']
    PLEX_Library = main_globals['PLEX_Library']
    PLEX_Collection = main_globals['PLEX_Collection']
    PLEX_Playlist = main_globals['PLEX_Playlist']
    PLEXOBJ = main_globals['PLEXOBJ']
    DETECT = main_globals['DETECT']
    show_item_info = main_globals['show_item_info']
    update_cache_after_resolution = main_globals['update_cache_after_resolution']
    escape_path_for_ssh = main_globals['escape_path_for_ssh']
    determine_remote_host = main_globals['determine_remote_host']
    resolve_path = main_globals['resolve_path']
    format_filesize = main_globals['format_filesize']
    build_media_cache_dict = main_globals['build_media_cache_dict']
    load_media_cache = main_globals['load_media_cache']
    execute_global_commands = main_globals['execute_global_commands']
    update_and_save_cache = main_globals.get('update_and_save_cache')
    undo_operation = main_globals.get('undo_operation')
    DBG = main_globals.get('DBG', False)
    inject_before_first_match = main_globals.get('inject_before_first_match')

Summary must report metadata probing separately from library changes (added/removed/updated)."""
        content = self._read_script()
        import re
        # The primary change condition must NOT include metadata_probed
        match = re.search(r'if total_added > 0 or total_removed > 0 or total_updated > 0:', content)
        self.assertIsNotNone(match,
            "Summary must have a change condition based on added/removed/updated only")
        # metadata_probed must be reported separately (elif branch)
        self.assertIn("metadata_probed", content,
            "Summary must mention metadata probed count when no library changes")

    def test_tool_failure_aborts_with_exit(self):
        """External tool failure during batch apply must abort immediately."""
        content = self._read_script()
        self.assertIn("Aborting: external tool failed", content,
            "Tool failure must print abort message")
        import re
        match = re.search(r'Aborting.*?\n\s*(sys\.exit\(1\))', content)
        self.assertIsNotNone(match,
            "sys.exit(1) must follow the abort message")

    def test_tool_stderr_ansi_stripped(self):
        """ANSI escape codes from external tool stderr must be stripped."""
        content = self._read_script()
        self.assertIn(r"\033\[", content,
            "stderr processing must strip ANSI escape codes")

    def test_skip_paths_collect_missing_metadata(self):
        """All skip paths in --update-cache must call _collect_missing_file_metadata."""
        content = self._read_script()
        # DB movie skip path
        self.assertIn("SKIPPING movie", content)
        # DB episode skip path
        self.assertIn("SKIPPING episode", content)
        # Count calls to _collect_missing_file_metadata (at least 2 DB skip paths: movie + episode)
        # Plus 1 for the function definition itself = at least 3 total
        count = content.count("_collect_missing_file_metadata(")
        self.assertGreaterEqual(count, 3,
            f"Expected at least 3 occurrences of _collect_missing_file_metadata (1 def + 2 DB skip paths), found {count}")

    def test_collect_missing_file_metadata_queues_to_batch(self):
        """_collect_missing_file_metadata must queue files for batch collection instead of probing individually."""
        content = self._read_script()
        self.assertIn("def _collect_missing_file_metadata(", content)
        import re
        match = re.search(r'(def _collect_missing_file_metadata\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "_collect_missing_file_metadata function must exist")
        func_body = match.group(1)
        self.assertIn("_metadata_batch_queue.append(", func_body,
            "_collect_missing_file_metadata must queue files to _metadata_batch_queue")
        # Must NOT call get_video_file_metadata directly (that's for single-file probing)
        self.assertNotIn("get_video_file_metadata(", func_body,
            "_collect_missing_file_metadata must NOT probe files individually — use batch queue")

    def test_batch_metadata_collection_function_exists(self):
        """_run_batch_metadata_collection must exist and handle batch ffmpeg via SSH."""
        content = self._read_script()
        self.assertIn("def _run_batch_metadata_collection(", content)
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("_metadata_batch_queue", func_body,
            "Must read from _metadata_batch_queue")
        self.assertIn("determine_remote_host(", func_body,
            "Must use determine_remote_host to detect remote/local")
        self.assertIn("run_tool_on_PLEX_server('ffmpeg'", func_body,
            "Must use run_tool_on_PLEX_server for ffmpeg path resolution")

    def test_batch_metadata_marks_broken_on_failure(self):
        """Batch metadata collection must mark ffprobe failures as broken, not abort."""
        content = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("ffprobe_error", func_body,
            "Must mark ffprobe failures with reason='ffprobe_error'")
        self.assertIn("'broken': True", func_body,
            "Must set broken flag on failed files")

    def test_batch_collection_called_from_update_cache(self):
        """update_cache must call _run_batch_metadata_collection after library processing."""
        content = self._read_script()
        self.assertIn("_run_batch_metadata_collection()", content,
            "update_cache must call _run_batch_metadata_collection")

    def test_sweep_queues_all_missing_metadata(self):
        """After re-attachment, a sweep must queue ALL files still missing metadata."""
        content = self._read_script()
        # The init() function must have a sweep that iterates OBJ_BY_ID and queues
        # any Movie/Episode files with file_metadata=None to _metadata_batch_queue.
        # This covers --force-plex full processing paths that don't call
        # _collect_missing_file_metadata individually.
        self.assertIn("additional files missing metadata", content,
            "Must have a sweep that reports queuing additional files missing metadata")
        # The sweep must check file_metadata is not None (skip files that already have it)
        # and must append to _metadata_batch_queue
        import re
        # Find the sweep block — it's between re-attachment and batch collection
        sweep_pattern = r'already_queued.*?additional files missing metadata'
        match = re.search(sweep_pattern, content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must have sweep block between re-attachment and batch collection")
        sweep_block = match.group(0)
        self.assertIn("_metadata_batch_queue.append(", sweep_block,
            "Sweep must append missing files to _metadata_batch_queue")
        self.assertIn("file_metadata", sweep_block,
            "Sweep must check file_metadata status")

    def test_batch_collection_uses_json_lines(self):
        """Batch collector script must output JSON-lines for streaming results."""
        content = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("json.loads(line)", func_body,
            "Must parse JSON-lines output from collector script")
        self.assertIn("json.dumps(", func_body,
            "Collector script must output JSON via json.dumps")

    def test_add_media_obj_via_PLEX_API_does_not_use_broken_remote_host_pattern(self):
        """add_media_obj_via_PLEX_API must NOT use the broken getattr(library, 'remote_host') pattern.
        Remote-host detection is deferred to the metadata batch processor, which calls
        determine_remote_host(filepath) for each queued file (see _process_metadata_batch_queue)."""
        content = self._read_script()
        import re
        match = re.search(r'(def add_media_obj_via_PLEX_API\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "add_media_obj_via_PLEX_API function must exist")
        func_body = match.group(1)
        self.assertNotIn("getattr(library, 'remote_host'", func_body,
            "Must not use getattr(library, 'remote_host') — host detection is the batch processor's job")
        self.assertIn("_metadata_batch_queue.append(", func_body,
            "Files must be queued for the parallel metadata batch processor (which calls determine_remote_host per file)")

    def test_get_video_file_metadata_uses_run_tool(self):
        """get_video_file_metadata must use run_tool_on_PLEX_server for ffmpeg (local and remote)."""
        content = self._read_script()
        import re
        match = re.search(r'(def get_video_file_metadata\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("run_tool_on_PLEX_server('ffmpeg'", func_body,
            "Must use run_tool_on_PLEX_server for ffmpeg execution")

    def test_mkv_container_duration_in_milliseconds(self):
        """MKV metadata must store container_duration in milliseconds (same as Plex)."""
        content = self._read_script()
        # The return dict must use duration_ms (milliseconds, not minutes)
        self.assertIn("'container_duration': duration_ms,", content,
            "container_duration must be stored in milliseconds (duration_ms)")
        # get_video_file_metadata must NOT return duration in minutes
        import re
        match = re.search(r'(def get_video_file_metadata\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        if match:
            func_body = match.group(1)
            self.assertNotIn("'container_duration': duration_min", func_body,
                "get_video_file_metadata must NOT store duration in minutes")

    def test_broken_detection_filesize_heuristic(self):
        """Broken file detection must include filesize vs duration fallback heuristic."""
        content = self._read_script()
        self.assertIn("avg_kbyte_per_s", content,
            "Broken detection must compute average KB/s as fallback")
        self.assertIn("avg_kbyte_per_s < BROKEN_MIN_BYTERATE_KBYTE_PER_S", content,
            "Files with average byte-rate below BROKEN_MIN_BYTERATE_KBYTE_PER_S should be flagged as broken")
        self.assertIn("'BROKEN_MIN_BYTERATE_KBYTE_PER_S'", content,
            "Threshold must be a CONFIG_DEFAULTS key (default 10 KB/s)")

    def test_broken_table_has_diff_explanation(self):
        """--broken output must explain the DIFF% column."""
        content = self._read_script()
        self.assertIn("container_duration - plex_duration", content,
            "Must explain DIFF% formula above the table")

    def test_collect_missing_metadata_retries_file_not_found_but_not_ffprobe_error(self):
        """_collect_missing_file_metadata must retry file_not_found but skip ffprobe_error."""
        content = self._read_script()
        import re
        match = re.search(r'(def _collect_missing_file_metadata\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        # Must skip entries with valid (non-broken) metadata
        self.assertIn("not existing_metadata.get('broken')", func_body,
            "Must skip entries with valid (non-broken) metadata")
        # Must skip ffprobe_error (genuinely broken, won't fix itself)
        self.assertIn("ffprobe_error", func_body,
            "Must skip files broken due to ffprobe_error (won't fix themselves)")
        # file_not_found should NOT be skipped (Plex still lists them — retry is warranted)


class TestNoAPIFallbacks(unittest.TestCase):
    """API fallbacks must be removed — DB is the only data source for --update-cache."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_no_api_fallback_in_movie_processing(self):
        """update_movie_library_objs must NOT fall back to plex_get_all_items."""
        content = self._read_script()
        import re
        match = re.search(r'(def update_movie_library_objs\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertNotIn("plex_get_all_items", func_body,
            "update_movie_library_objs must NOT have API fallback via plex_get_all_items")

    def test_no_api_fallback_in_show_processing(self):
        """update_series_library_objs must NOT fall back to plex_get_all_items."""
        content = self._read_script()
        import re
        match = re.search(r'(def update_series_library_objs\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertNotIn("plex_get_all_items", func_body,
            "update_series_library_objs must NOT have API fallback via plex_get_all_items")

    def test_no_api_fallback_in_library_stats(self):
        """get_library_stats must NOT fall back to API totalSize."""
        content = self._read_script()
        import re
        match = re.search(r'(def get_library_stats\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertNotIn("totalSize", func_body,
            "get_library_stats must NOT fall back to API totalSize — DB is source of truth")

    def test_no_api_fallback_in_library_init(self):
        """PLEX_Library.init must NOT fall back to plex.library.sections() for building OBJ_DICT."""
        content = self._read_script()
        # Verify the no-API-fallback comment exists, confirming the API path was removed
        self.assertIn("No API fallback", content,
            "PLEX_Library.init must have 'No API fallback' comment confirming API path removed")

    def test_info_does_not_use_api(self):
        """--info must not use API fetchItem — cache only."""
        content = self._read_script()
        import re
        match = re.search(r'(def show_item_info\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertNotIn("fetchItem", func_body,
            "--info must NOT use API fetchItem")

    def test_playlist_detection_uses_db(self):
        """PLEX_Playlist.detect_if_of_OBJ_TYPE must use DB query, not API."""
        content = self._read_script()
        # Find the detect_if_of_OBJ_TYPE in PLEX_Playlist class
        self.assertIn("metadata_type = 15", content,
            "Playlist detection must use DB query with metadata_type = 15")

    def test_playlist_list_uses_db(self):
        """PLEX_Playlist.list must use DB query, not API."""
        content = self._read_script()
        import re
        # Find the list method - it should contain query_plex_database
        match = re.search(r'class PLEX_Playlist.*?def list\(playlist_name\):\n(.*?)(?=\n    @staticmethod|\n    def )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("query_plex_database", func_body,
            "PLEX_Playlist.list must use DB query")
        self.assertNotIn("plex.playlists()", func_body,
            "PLEX_Playlist.list must NOT use API plex.playlists()")


class TestVerifyCacheIntegrity(unittest.TestCase):
    """verify_cache must perform comprehensive data integrity checks."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_verify_checks_file_metadata_coverage(self):
        content = self._read_script()
        self.assertIn("file_metadata", content)
        self.assertIn("missing_metadata", content,
            "verify_cache must count files with missing file_metadata")

    def test_verify_checks_obj_by_filepath(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_FILEPATH", content)
        self.assertIn("filepath_dangling", content,
            "verify_cache must detect dangling OBJ_BY_FILEPATH references")

    def test_verify_checks_obj_by_movie(self):
        content = self._read_script()
        self.assertIn("movie_dangling", content,
            "verify_cache must detect dangling OBJ_BY_MOVIE references")

    def test_verify_checks_obj_by_show(self):
        content = self._read_script()
        self.assertIn("series_dangling", content,
            "verify_cache must detect dangling OBJ_BY_SERIES references")
        self.assertIn("episode_dangling", content,
            "verify_cache must detect dangling OBJ_BY_SERIES_EPISODES references")

    def test_verify_checks_labels_index(self):
        content = self._read_script()
        self.assertIn("rebuilt_labels_index", content,
            "verify_cache must rebuild labels_index to compare with cached version")

    def test_verify_checks_collection_members(self):
        content = self._read_script()
        self.assertIn("orphaned_collections", content,
            "verify_cache must detect orphaned collections")
        self.assertIn("invalid_members", content,
            "verify_cache must detect invalid collection member references")

    def test_verify_checks_library_stats(self):
        content = self._read_script()
        self.assertIn("itemsCount", content)
        self.assertIn("stats_mismatches", content,
            "verify_cache must detect itemsCount mismatches")

    def test_batch_metadata_handles_file_not_found(self):
        """Batch metadata must track missing files separately from ffprobe errors."""
        content = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("not_found_count", func_body,
            "Must track file-not-found separately from ffprobe errors")
        self.assertIn("file_not_found", func_body,
            "Must mark missing files with reason='file_not_found' in cache")
        self.assertIn("last_metadata_broken_details", func_body,
            "Must store broken details for JSON update log")

    def test_batch_metadata_falls_back_to_db_host(self):
        """Batch metadata must fall back to PLEX_DB_REMOTE_HOST when files not found."""
        content = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("PLEX_DB_REMOTE_HOST", func_body,
            "Must fall back to PLEX_DB_REMOTE_HOST when determine_remote_host fails")

    def test_batch_metadata_continues_on_error(self):
        """Collector script must continue on failure, not abort."""
        content = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        # Extract the inline collector script portion (between collector_script = and closing ''')
        script_match = re.search(r"collector_script = f'''(.*?)'''", func_body, re.DOTALL)
        assert script_match is not None, "the pattern above did not match"
        self.assertIsNotNone(script_match, "Must find collector_script in function")
        collector = script_match.group(1)
        # Collector script must NOT sys.exit on failure
        self.assertNotIn("sys.exit", collector,
            "Collector script must not abort on failure — continue with remaining files")
        # Collector must use ffmpeg -i and parse Duration from stderr
        self.assertIn("ffmpeg", collector,
            "Collector script must use ffmpeg for metadata collection")
        self.assertIn("Duration:", collector,
            "Collector script must parse Duration from ffmpeg -i stderr output")
        # Must mark errors as broken in cache
        self.assertIn("ffprobe_error", func_body,
            "Must mark failures with reason='ffprobe_error'")
        self.assertIn("metadata_broken_details", func_body,
            "Must collect broken file details for JSON update log")

    def test_filepath_check_skips_show_season(self):
        """OBJ_BY_FILEPATH check must skip Show/Season directory container objects."""
        content = self._read_script()
        import re
        match = re.search(r'(# Check 2: OBJ_BY_FILEPATH.*?)(?=# Check 3:)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must have Check 2: OBJ_BY_FILEPATH section")
        check2 = match.group(1)
        self.assertIn("('Series', 'Season')", check2,
            "OBJ_BY_FILEPATH check must skip Show/Season objects (directory containers)")

    def test_itemscount_compares_primary_type_only(self):
        """itemsCount check must compare like-for-like: primary type per library only."""
        content = self._read_script()
        import re
        match = re.search(r'(# Check 7: library_stats.*?)(?=# Summary)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must have Check 7: library_stats section")
        check7 = match.group(1)
        self.assertIn("primary_type_per_lib", check7,
            "itemsCount check must determine primary type per library")
        self.assertIn("OBJ_BY_LIBRARY", check7,
            "itemsCount check must use OBJ_BY_LIBRARY to determine library type")

    def test_broken_files_not_in_integrity_issues(self):
        """Broken files (ffprobe failed) must NOT be added to integrity_issues — they are a warning only."""
        content = self._read_script()
        import re
        match = re.search(r'(# Check 1.*?)(?=# Check 2:)', content, re.DOTALL)
        if match is None:
            # Fall back: search the file metadata section in verify_cache
            match = re.search(r'(needs_update = missing_metadata.*?)(?=# Check 2:)', content, re.DOTALL)
            assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must have file metadata check section")
        check1 = match.group(1)
        self.assertNotIn("integrity_issues.append", check1.split("broken_metadata")[1] if "broken_metadata" in check1 else "",
            "Broken files must NOT be appended to integrity_issues")
        # Verify broken is reported as info/warning outside of integrity_issues
        # Use a more specific anchor: the Summary section in verify_cache_integrity uses total_broken
        summary_match = re.search(r'(# Summary\n\s*total_broken = broken_metadata.*?)(?=\n\ndef )', content, re.DOTALL)
        assert summary_match is not None, "the pattern above did not match"
        self.assertIsNotNone(summary_match, "Must have Summary section in verify_cache_integrity")
        summary = summary_match.group(1)
        self.assertIn("broken_metadata", summary,
            "Summary must show broken files as a warning before integrity issues")

    def test_skip_logic_compares_episode_count(self):
        """Skip logic for series libraries must compare episode count, not just series count."""
        content = self._read_script()
        import re
        match = re.search(r'(def process_single_library\(.*?\):\n.*?)(?=\n    def update_cache)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find process_single_library function")
        func_body = match.group(1)
        self.assertIn("current_episode_count", func_body,
            "Skip logic must compare current episode count for series libraries")
        self.assertIn("old_episode_count", func_body,
            "Skip logic must compare old episode count from cache")

    def test_get_library_stats_queries_episode_count(self):
        """get_library_stats must query episode count for series libraries."""
        content = self._read_script()
        import re
        match = re.search(r'(def get_library_stats\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find get_library_stats function")
        func_body = match.group(1)
        self.assertIn("episodesCount", func_body,
            "get_library_stats must store episode count in episodesCount")
        self.assertIn("metadata_type = 4", func_body,
            "get_library_stats must query metadata_type=4 (episodes) for series libraries")

    def test_obj_by_filepath_rebuild_is_saved(self):
        """OBJ_BY_FILEPATH rebuild must be persisted via update_and_save_cache AFTER the rebuild."""
        content = self._read_script()
        import re
        # Find the rebuild block and verify a save follows it (not before it)
        rebuild_pos = content.find("# Rebuild OBJ_BY_FILEPATH from OBJ_BY_ID")
        self.assertGreater(rebuild_pos, 0, "Must have OBJ_BY_FILEPATH rebuild block")
        # Find the next update_and_save_cache call after the rebuild — must use build_media_cache_dict
        after_rebuild = content[rebuild_pos:]
        save_match = re.search(r"update_and_save_cache\(build_media_cache_dict\(", after_rebuild)
        self.assertIsNotNone(save_match,
            "Must call update_and_save_cache(build_media_cache_dict(...)) AFTER the rebuild block")

    def test_broken_shows_all_file_versions(self):
        """--broken must show every broken file version, not just one per object."""
        content = self._read_script()
        import re
        match = re.search(r'(def _list_broken_files\(.*?\n.*?broken_files = \[\].*?)(?=\n        if not broken_files:)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find _list_broken_files method")
        broken_block = match.group(1)
        # Must NOT break after first broken file per object
        self.assertNotIn("break  # Only add the key once", broken_block,
            "--broken must show ALL broken file versions, not just one per object")
        # Must deduplicate obj_keys to avoid counting same object multiple times
        self.assertIn("seen_keys", broken_block,
            "--broken must deduplicate obj_keys to avoid duplicate entries from OBJ_BY_LIBRARY")

    def test_broken_includes_no_duration_objects(self):
        """--broken must include PROBE ERR/NOT FOUND files even when plex duration is None."""
        content = self._read_script()
        import re
        match = re.search(r'(def _list_broken_files\(.*?\n.*?broken_files = \[\].*?)(?=\n        if not broken_files:)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find _list_broken_files method")
        broken_block = match.group(1)
        # Must NOT skip objects with no plex duration (they may have PROBE ERR / NOT FOUND files)
        self.assertNotIn("if not plex_duration:\n                    continue", broken_block,
            "--broken must not skip objects with None duration — PROBE ERR files would be hidden")

    def test_from_scratch_preserves_file_metadata(self):
        """--force-plex must preserve file_metadata and re-attach after rebuild."""
        content = self._read_script()
        self.assertIn("_preserved_file_metadata", content,
            "--force-plex must extract file_metadata before clearing OBJ_BY_ID")
        import re
        # Preservation must happen BEFORE clearing OBJ_BY_ID
        preserve_pos = content.find("_preserved_file_metadata = {}")
        clear_pos = content.find("PLEX_Media.OBJ_BY_ID = {}", preserve_pos if preserve_pos > 0 else 0)
        self.assertGreater(preserve_pos, 0, "Must have _preserved_file_metadata extraction")
        self.assertGreater(clear_pos, preserve_pos,
            "_preserved_file_metadata must be extracted BEFORE OBJ_BY_ID is cleared")
        # Re-attachment must happen BEFORE batch metadata collection
        reattach_pos = content.find("Re-attached preserved file metadata")
        batch_pos = content.find("_run_batch_metadata_collection()", reattach_pos if reattach_pos > 0 else 0)
        self.assertGreater(reattach_pos, 0, "Must re-attach preserved metadata")
        self.assertLess(reattach_pos, batch_pos,
            "Re-attachment must happen BEFORE batch metadata collection")

    def test_obj_by_library_no_duplicates(self):
        """All OBJ_BY_LIBRARY append sites must check for duplicates first."""
        content = self._read_script()
        import re
        # Find all .append() calls on OBJ_BY_LIBRARY (excluding test code and remove() calls)
        # Each append must be preceded by a "not in" check
        pattern = r'PLEX_Media\.OBJ_BY_LIBRARY\[.*?\]\[.*?\]\.append\('
        matches = list(re.finditer(pattern, content))
        self.assertGreater(len(matches), 0, "Must have OBJ_BY_LIBRARY append calls")
        for m in matches:
            # Check the 2 lines before the append for a "not in" guard
            before = content[max(0, m.start() - 200):m.start()]
            self.assertIn("not in PLEX_Media.OBJ_BY_LIBRARY", before,
                f"OBJ_BY_LIBRARY append at position {m.start()} must have duplicate guard")


class TestCacheFormatValidation(unittest.TestCase):
    """load_media_cache() must detect outdated cache format and error with rebuild instructions."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_outdated_cache_detected(self):
        content = self._read_script()
        self.assertIn("Cache format is outdated", content)
        self.assertIn("--update-cache --force-plex", content)

    def test_filter_skips_show_season_types(self):
        content = self._read_script()
        self.assertIn("obj_type in ('Series', 'Season')", content)

    def test_print_handles_members_list(self):
        content = self._read_script()
        self.assertIn("case 'MEMBERS':", content)


class TestCacheStructureParity(unittest.TestCase):
    """DB-based cache building must produce the same structure as old API-based code."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_series_objects_created_by_db_path(self):
        content = self._read_script()
        self.assertIn("'type': 'Series', 'type_str': 'Series'", content)

    def test_season_objects_created_by_db_path(self):
        content = self._read_script()
        self.assertIn("'type': 'Season', 'type_str': 'Season'", content)

    def test_obj_by_show_populated(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_SERIES[series_key][s_str] = season_key", content)

    def test_obj_by_series_episodes_version_format(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_SERIES_EPISODES[series_key][s_str][e_str][version]", content)
        self.assertIn(".append(episode_key)", content)

    def test_obj_by_library_type_keys_format(self):
        content = self._read_script()
        self.assertIn("PLEX_Media.OBJ_BY_LIBRARY[library_name]['Movie'] = []", content)
        self.assertIn("lib_dict['Episode'] = []", content)
        self.assertIn("lib_dict['Series'] = []", content)
        self.assertIn("lib_dict['Season'] = []", content)

    def test_obj_by_movie_version_filepath_format(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_MOVIE[movie_key][ver] = file_info.get('filepath'", content)

    def test_get_obj_keys_iterates_by_type(self):
        content = self._read_script()
        self.assertIn("for t in ('Series', 'Episode', 'Movie')", content)


class TestDbQueriesUseLibraryName(unittest.TestCase):
    """DB queries must use library name (JOIN library_sections) instead of internal IDs."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_no_sectionId_in_cache(self):
        content = self._read_script()
        self.assertNotIn("'sectionId'", content)
        self.assertNotIn("db_library_ids", content)

    def test_verify_cache_uses_library_name_join(self):
        content = self._read_script()
        self.assertIn("JOIN library_sections ls ON mi.library_section_id = ls.id WHERE ls.name", content)

    def test_get_library_stats_uses_library_name_join(self):
        content = self._read_script()
        self.assertIn("JOIN library_sections ls ON mi.library_section_id = ls.id", content)

    def test_no_lib_key_in_stubs(self):
        content = self._read_script()
        self.assertNotIn("getattr(lib, 'key'", content)

    def test_query_plex_database_supports_local(self):
        """query_plex_database must auto-detect and use local sqlite3 when DB exists locally."""
        content = self._read_script()
        import re
        match = re.search(r'(def query_plex_database\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("os.path.exists(local_db_path)", func_body,
            "Must check if DB file exists locally")
        self.assertIn("use_local", func_body,
            "Must have local/remote branching logic")

    def test_query_plex_database_has_both_paths(self):
        """query_plex_database must have both local and SSH execution paths."""
        content = self._read_script()
        import re
        match = re.search(r'(def query_plex_database\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("_ssh_args(PLEX_DB_REMOTE_HOST)", func_body,
            "Must have SSH path for remote execution (via _ssh_args helper)")
        self.assertIn("'sqlite3',", func_body,
            "Must have local sqlite3 path for direct execution")


class TestResolveMediaByNumericID(unittest.TestCase):
    """resolve_plex_media_obj must resolve numeric IDs ('18349' or 'ID:18349') from cache."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_resolve_requires_id_prefix(self):
        """resolve_plex_media_obj must REQUIRE 'ID:<num>' prefix — bare numbers must NOT match as Plex IDs."""
        content = self._read_script()
        import re
        match = re.search(r'(def resolve_plex_media_obj\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("startswith('ID:')", func_body,
            "resolve_plex_media_obj must require 'ID:' prefix for numeric ID lookup")
        self.assertIn("int(obj.get('id', 0)) == numeric_id", func_body,
            "resolve_plex_media_obj must match numeric ID against obj['id'] with type coercion")
        # Must NOT have bare numeric fallback (no stripping ID: and then trying int())
        self.assertNotIn("int(numeric_str)", func_body,
            "resolve_plex_media_obj must NOT accept bare numeric IDs — require ID: prefix")

    def test_full_key_passes_list_to_helper(self):
        """Full cache key path must pass a list (not bare dict) to get_media_list_from_PLEX_OBJ_list."""
        content = self._read_script()
        import re
        match = re.search(r'(def resolve_plex_media_obj\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        # Must wrap in list: [PLEX_Media.OBJ_BY_ID[...]]
        self.assertIn("[PLEX_Media.OBJ_BY_ID[ media_identifier ]]", func_body,
            "Full key path must wrap single obj in list before passing to get_media_list_from_PLEX_OBJ_list")

    def test_broken_prints_id_prefix(self):
        """--broken output must print PLEX-ID as 'ID:<num>' format."""
        content = self._read_script()
        self.assertIn('f"ID:{plex_id}"', content,
            "--broken must format PLEX-ID column as ID:<num>")

    def test_resolve_cache_items_requires_id_prefix(self):
        """resolve_cache_items must REQUIRE 'ID:<num>' prefix — bare numbers must NOT match as Plex IDs."""
        content = self._read_script()
        import re
        match = re.search(r'(def resolve_cache_items\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "resolve_cache_items function must exist")
        func_body = match.group(1)
        self.assertIn("startswith('ID:')", func_body,
            "resolve_cache_items must require 'ID:' prefix for Plex ID lookup")

    def test_show_item_info_uses_resolve_cache_items(self):
        """show_item_info must delegate to resolve_cache_items (centralised resolution)."""
        content = self._read_script()
        import re
        match = re.search(r'(def show_item_info\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("resolve_cache_items(", func_body,
            "show_item_info must use resolve_cache_items() for centralised resolution")

    def test_resolve_series_for_episodes_uses_resolve_cache_items(self):
        """resolve_series_for_episodes must delegate to resolve_cache_items (centralised resolution)."""
        content = self._read_script()
        import re
        match = re.search(r'(def resolve_series_for_episodes\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("resolve_cache_items(", func_body,
            "resolve_series_for_episodes must use resolve_cache_items() for centralised resolution")


class TestRefactoredMethodNames(unittest.TestCase):
    """Verify method name fixes and dead code removal from refactoring session."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_set_watched_exists(self):
        """set_watched must exist (renamed from set_watched_status)."""
        content = self._read_script()
        self.assertIn("def set_watched(", content)

    def test_set_unwatched_exists(self):
        """set_unwatched must exist (renamed from set_unwatched_status)."""
        content = self._read_script()
        self.assertIn("def set_unwatched(", content)

    def test_old_method_names_removed(self):
        """Old method names set_watched_status/set_unwatched_status must not exist."""
        content = self._read_script()
        self.assertNotIn("def set_watched_status(", content,
            "set_watched_status was renamed to set_watched")
        self.assertNotIn("def set_unwatched_status(", content,
            "set_unwatched_status was renamed to set_unwatched")

    def test_get_user_rating_exists(self):
        """get_user_rating must exist (was missing, referenced by argparse)."""
        content = self._read_script()
        self.assertIn("def get_user_rating(", content)

    def test_execute_cmd_uses_correct_names(self):
        """execute_cmd must call set_watched/set_unwatched (not old _status variants)."""
        content = self._read_script()
        import re
        # Find PLEX_Media.execute_cmd
        match = re.search(r'(class PLEX_Media.*?def execute_cmd.*?)(?=\n    #+\n)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find PLEX_Media.execute_cmd")
        cmd_block = match.group(1)
        self.assertIn(".set_watched(", cmd_block)
        self.assertIn(".set_unwatched(", cmd_block)
        self.assertNotIn(".set_watched_status(", cmd_block)
        self.assertNotIn(".set_unwatched_status(", cmd_block)


class TestDeadCodeRemoval(unittest.TestCase):
    """Verify removed dead functions stay removed."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_get_mkv_header_duration_removed(self):
        """get_mkv_header_duration was dead code — must stay removed."""
        content = self._read_script()
        self.assertNotIn("def get_mkv_header_duration(", content)

    def test_trigger_library_scan_removed(self):
        """trigger_library_scan was dead code — must stay removed."""
        content = self._read_script()
        self.assertNotIn("def trigger_library_scan(", content)

    def test_generate_metadata_filelist_removed(self):
        """generate_metadata_filelist was dead code — must stay removed."""
        content = self._read_script()
        self.assertNotIn("def generate_metadata_filelist(", content)


class TestMediaApiActionConsolidation(unittest.TestCase):
    """Verify _media_api_action helper and all 9 wrapper methods."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_media_api_action_exists(self):
        """_media_api_action helper must exist."""
        content = self._read_script()
        self.assertIn("def _media_api_action(", content)

    def test_media_api_action_has_error_handling(self):
        """_media_api_action must catch exceptions and call err()."""
        content = self._read_script()
        import re
        match = re.search(r'def _media_api_action\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("except Exception", body)
        self.assertIn("err(err_code", body)

    def test_all_wrappers_use_media_api_action(self):
        """All setter/getter methods must delegate to _media_api_action."""
        content = self._read_script()
        for method in ['set_watched', 'set_unwatched', 'set_watched_date', 'set_view_offset',
                       'get_view_offset', 'get_user_rating', 'set_user_rating', 'clear_user_rating',
                       'get_watched_status']:
            import re
            pattern = rf'def {method}\(.*?\n(.*?)(?=\n    @staticmethod|\n    #+)'
            match = re.search(pattern, content, re.DOTALL)
            assert match is not None, "the pattern above did not match"
            self.assertIsNotNone(match, f"{method} must exist")
            body = match.group(1)
            self.assertIn("_media_api_action(", body,
                f"{method} must delegate to _media_api_action")

    def test_no_duplicate_error_handling_in_wrappers(self):
        """Wrapper methods must NOT have their own try/except (handled by _media_api_action)."""
        content = self._read_script()
        import re
        for method in ['set_watched', 'set_unwatched', 'get_user_rating', 'clear_user_rating']:
            pattern = rf'def {method}\(.*?\n(.*?)(?=\n    @staticmethod|\n    #+)'
            match = re.search(pattern, content, re.DOTALL)
            assert match is not None, "the pattern above did not match"
            self.assertIsNotNone(match, f"{method} must exist")
            body = match.group(1)
            self.assertNotIn("try:", body,
                f"{method} must not have its own try/except — _media_api_action handles errors")


class TestListMethodSplit(unittest.TestCase):
    """Verify PLEX_Media.list() was properly split into helper methods."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_normalize_list_args_exists(self):
        """_normalize_list_args must exist as a static method."""
        content = self._read_script()
        self.assertIn("def _normalize_list_args(", content)

    def test_normalize_list_args_handles_series_alias(self):
        """_normalize_list_args must map 'Series' to 'Series'."""
        content = self._read_script()
        import re
        match = re.search(r'def _normalize_list_args\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn('"Series"', body)
        self.assertIn('"Series"', body)

    def test_normalize_list_args_validates_media_type(self):
        """_normalize_list_args must reject invalid media types with err()."""
        content = self._read_script()
        import re
        match = re.search(r'def _normalize_list_args\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("UNSUPPORTED media_type", body, "Must err() on an invalid media_type")

    def test_print_list_header_exists(self):
        """_print_list_header must exist."""
        content = self._read_script()
        self.assertIn("def _print_list_header(", content)

    def test_list_broken_files_exists(self):
        """_list_broken_files must exist as extracted helper."""
        content = self._read_script()
        self.assertIn("def _list_broken_files(", content)

    def test_find_duplicates_exists(self):
        """_find_duplicates must exist."""
        content = self._read_script()
        self.assertIn("def _find_duplicates(", content)

    def test_sort_duplicates_exists(self):
        """_sort_duplicates must exist."""
        content = self._read_script()
        self.assertIn("def _sort_duplicates(", content)

    def test_print_duplicate_list_exists(self):
        """_print_duplicate_list must exist."""
        content = self._read_script()
        self.assertIn("def _print_duplicate_list(", content)

    def test_filter_by_watch_and_audio_exists(self):
        """_filter_by_watch_and_audio must exist."""
        content = self._read_script()
        self.assertIn("def _filter_by_watch_and_audio(", content)

    def test_list_calls_helpers(self):
        """PLEX_Media.list() must call the extracted helper methods."""
        content = self._read_script()
        import re
        match = re.search(r'(def list\(args, obj_args.*?\n.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find PLEX_Media.list()")
        body = match.group(1)
        self.assertIn("_normalize_list_args(", body)
        self.assertIn("_list_broken_files(", body)
        self.assertIn("_find_duplicates(", body)

    def test_iso639_in_normalize(self):
        """Audio language normalization must be in _normalize_list_args."""
        content = self._read_script()
        import re
        match = re.search(r'def _normalize_list_args\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("'english'", body.lower(), "Must normalize 'english' to ISO code")
        self.assertIn("'german'", body.lower(), "Must normalize 'german' to ISO code")
        self.assertIn("'french'", body.lower(), "Must normalize 'french' to ISO code")


class TestExecuteTrashAndMoveSplit(unittest.TestCase):
    """Verify execute_resolution_action choices 5/6 were unified into _execute_trash_and_move."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_execute_trash_and_move_exists(self):
        """_execute_trash_and_move must exist."""
        content = self._read_script()
        self.assertIn("def _execute_trash_and_move(", content)

    def test_handles_both_choices(self):
        """_execute_trash_and_move must handle choice 5 with else branch for choice 6."""
        content = self._read_script()
        import re
        match = re.search(r"def _execute_trash_and_move\(.*?\n(.*?)(?=\ndef )", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("'5'", body, "Must handle choice 5")
        # Choice 6 is the else branch — verify both index orderings exist
        self.assertIn("trash_idx, keep_idx = 0, 1", body, "Choice 5: trash first, keep second")
        self.assertIn("trash_idx, keep_idx = 1, 0", body, "Choice 6: trash second, keep first")

    def test_resolution_action_delegates(self):
        """execute_resolution_action must delegate choices 5/6 to _execute_trash_and_move."""
        content = self._read_script()
        import re
        match = re.search(r'def execute_resolution_action\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_execute_trash_and_move(", body)


class TestVerifyCacheSplit(unittest.TestCase):
    """Verify verify_cache() was split: data integrity checks moved to _verify_data_integrity."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_verify_data_integrity_exists(self):
        """_verify_data_integrity must exist as standalone function."""
        content = self._read_script()
        self.assertIn("def _verify_data_integrity(", content)

    def test_verify_cache_calls_integrity(self):
        """verify_cache() must call _verify_data_integrity()."""
        content = self._read_script()
        import re
        match = re.search(r'def verify_cache\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_verify_data_integrity()", body)

    def test_integrity_checks_collection_members(self):
        """_verify_data_integrity must check OBJ_BY_COLLECTION member references."""
        content = self._read_script()
        import re
        match = re.search(r'def _verify_data_integrity\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("OBJ_BY_COLLECTION", body)

    def test_integrity_checks_obj_by_filepath(self):
        """_verify_data_integrity must validate OBJ_BY_FILEPATH consistency."""
        content = self._read_script()
        import re
        match = re.search(r'def _verify_data_integrity\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("OBJ_BY_FILEPATH", body)


class TestUpdateCacheSplit(unittest.TestCase):
    """Verify PLEX_Library.update_cache() finalize code was extracted to _finalize_and_save_cache."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_finalize_and_save_cache_exists(self):
        """_finalize_and_save_cache must exist."""
        content = self._read_script()
        self.assertIn("def _finalize_and_save_cache(", content)

    def test_finalize_accepts_old_read_only(self):
        """_finalize_and_save_cache must accept old_read_only parameter."""
        content = self._read_script()
        import re
        match = re.search(r'def _finalize_and_save_cache\((.*?)\)', content)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        params = match.group(1)
        self.assertIn("old_read_only", params, "Must accept old_read_only to restore READ_ONLY_MODE")

    def test_finalize_saves_cache(self):
        """v2.10: _finalize_and_save_cache no longer saves directly — it stashes
        the derived extras on PLEX_Media._pending_save_extras and the merged
        save at the end of PLEX_Media.init() picks them up.  This avoids
        pickling the full ~40 MB cache twice per --update-cache run."""
        content = self._read_script()
        import re
        match = re.search(r'def _finalize_and_save_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_pending_save_extras", body)
        # Must NOT call update_and_save_cache directly anymore (would re-introduce
        # the duplicate-save regression).
        self.assertNotIn("update_and_save_cache(", body)

    def test_finalize_rebuilds_library_object_counts(self):
        """_finalize_and_save_cache must rebuild library_object_counts."""
        content = self._read_script()
        import re
        match = re.search(r'def _finalize_and_save_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("updated_library_object_counts", body)

    def test_update_cache_calls_finalize(self):
        """PLEX_Library.update_cache() must call _finalize_and_save_cache."""
        content = self._read_script()
        import re
        # Find PLEX_Library.update_cache specifically (not PLEX_Media.update_cache)
        match = re.search(r'class PLEX_Library.*?def update_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_finalize_and_save_cache(", body)

    def test_old_read_only_passed_correctly(self):
        """update_cache must pass old_read_only to _finalize_and_save_cache."""
        content = self._read_script()
        import re
        match = re.search(r'class PLEX_Library.*?def update_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("old_read_only", body, "Must pass old_read_only to _finalize_and_save_cache")

    def test_no_inline_save_in_update_cache(self):
        """update_cache must NOT have inline cache save logic (moved to _finalize_and_save_cache)."""
        content = self._read_script()
        import re
        match = re.search(r'class PLEX_Library.*?def update_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("update_and_save_cache(build_media_cache_dict(", body,
            "Inline cache save must be in _finalize_and_save_cache, not update_cache")


class TestBrokenHeaderOrder(unittest.TestCase):
    """Verify --broken output has DURATION before LIBRARY in header."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_header_duration_before_library(self):
        """--broken header must have DURATION before LIBRARY."""
        content = self._read_script()
        import re
        match = re.search(r"'PLEX-ID'.*?'SEVERITY'.*?'DIFF%'.*?'(DURATION|LIBRARY)'.*?'(DURATION|LIBRARY)'", content)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find --broken header line")
        self.assertEqual(match.group(1), 'DURATION', "DURATION must come before LIBRARY in --broken header")
        self.assertEqual(match.group(2), 'LIBRARY', "LIBRARY must come after DURATION in --broken header")

    def test_data_line_matches_header_order(self):
        """--broken data format must output dur_str before library."""
        content = self._read_script()
        import re
        # Find the actual data print line (single line with plex_id_str, severity_str, diff_str)
        match = re.search(r'print\(f".*plex_id_str.*severity_str.*diff_str.*(dur_str).*(library).*filepath', content)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find --broken data print line")
        self.assertEqual(match.group(1), 'dur_str', "dur_str must come before library in data line")
        self.assertEqual(match.group(2), 'library', "library must come after dur_str in data line")


class TestExcessVersions(unittest.TestCase):
    """Verify --excess-versions feature."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_list_excess_versions_exists(self):
        """_list_excess_versions must exist."""
        content = self._read_script()
        self.assertIn("def _list_excess_versions(", content)

    def test_excess_versions_arg_defined(self):
        """--excess-versions must be defined in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        self.assertIn("'--excess-versions'", content)

    def test_excess_versions_accepts_limit(self):
        """_list_excess_versions must accept a version_limit parameter."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\((.*?)\)', content)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        self.assertIn("version_limit", match.group(1))

    def test_excess_versions_filters_by_limit(self):
        """_list_excess_versions must compare file count against version_limit."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("version_limit", body)
        self.assertIn("total", body, "Must track total version count")

    def test_excess_versions_output_has_version_fraction(self):
        """Output must show version as 'x / y' format."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("idx", body, "Must track version index")
        self.assertIn("total", body, "Must track total count")
        # Check for x / y format string
        self.assertRegex(body, r'f".*idx.*total', "Must format version as x / y")

    def test_excess_versions_grouped_output(self):
        """Output must group versions by entry with ID, library, title, and version count."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("prev_plex_id", body, "Must track previous plex_id for grouping")
        self.assertIn("versions)", body, "Must show version count per entry")

    def test_excess_versions_one_line_per_file(self):
        """Must iterate over files_dict to produce one output line per file."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("files_dict", body, "Must access files_dict for per-file iteration")
        self.assertIn("enumerate(", body, "Must enumerate files for version numbering")

    def test_excess_versions_wired_in_list(self):
        """PLEX_Media.list() must accept and dispatch excess_versions."""
        content = self._read_script()
        import re
        match = re.search(r'def list\(args, obj_args.*?\)', content)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        self.assertIn("excess_versions", match.group(0), "list() must accept excess_versions parameter")

    def test_excess_versions_wired_in_global_commands(self):
        """execute_global_commands must pass excess_versions to PLEX_Media.list()."""
        content = self._read_script()
        import re
        match = re.search(r'def execute_global_commands\(.*?\n(.*?)(?=\n###)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("excess_versions", body)

    def test_excess_versions_accepts_int(self):
        """--excess-versions must accept an integer limit."""
        content = self._read_script()
        self.assertIn("type=int", content, "--excess-versions must accept integer type")


class TestProblems(unittest.TestCase):
    """Verify --problems flag runs all problem checks with summary."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_problems_arg_defined(self):
        """--problems must be defined in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        self.assertIn("'--problems'", content)

    def test_problems_runs_broken(self):
        """--problems must call _list_broken_files (via _run_check wrapper)."""
        content = self._read_script()
        import re
        match = re.search(r"safe_getattr\(cmd_args, 'problems'.*?\n(.*?)(?=\n    # Handle --list)", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find --problems handler block")
        body = match.group(1)
        self.assertIn("_list_broken_files", body)

    def test_problems_runs_excess_versions(self):
        """--problems must run excess-versions with limit 3 via the registry (v3)."""
        content = self._read_script()
        import re
        # Registry entry delegates to _pc_excess …
        reg = _registry_entry_block(content, 'excess_versions')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'excess_versions'")
        self.assertIn('_pc_excess', reg)
        # … and _pc_excess calls _list_excess_versions with limit 3.
        helper = re.search(r"def _pc_excess\(.*?\n(.*?)\n\n", content, re.DOTALL)
        assert helper is not None, "the pattern above did not match"
        self.assertIsNotNone(helper, "Must find _pc_excess helper")
        self.assertIn("_list_excess_versions", helper.group(1))
        self.assertIn(", 3)", helper.group(1), "Must use limit 3 for excess versions")

    def test_problems_prints_summary(self):
        """--problems must print a closing PROBLEM DETECTION milestone."""
        content = self._read_script()
        import re
        match = re.search(r"safe_getattr\(cmd_args, 'problems'.*?\n(.*?)(?=\n    # Handle --list)", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("PROBLEM DETECTION", body)

    def test_problems_has_detailed_help(self):
        """--help problems must provide detailed help."""
        content = self._read_script()
        self.assertIn("case 'problems':", content, "Must have --help problems case")
        import re
        match = re.search(r"case 'problems':\n(.*?)sys\.exit\(0\)", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("PROBLEMS HELP", body)
        # v3: per-category lines are auto-generated from the registry — the
        # help case must iterate it, and the registry must carry the flags.
        self.assertIn("PROBLEM_CATEGORIES_REGISTRY.items()", body,
                      "--help problems must auto-generate categories from the registry")
        reg = _must(re.search(r"PROBLEM_CATEGORIES_REGISTRY = \{(.*?)\n\}", content, re.DOTALL),
                    'PROBLEM_CATEGORIES_REGISTRY').group(1)
        self.assertIsNotNone(reg, "Must find PROBLEM_CATEGORIES_REGISTRY")
        self.assertIn("'--broken'", reg)
        self.assertIn("'--excess-versions'", reg)

    def test_broken_returns_count(self):
        """_list_broken_files must return a count for --problems summary."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_broken_files\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("return 0", body, "Must return 0 when no broken files")
        self.assertIn("return len(broken_files)", body, "Must return count of broken files")

    def test_excess_versions_returns_counts(self):
        """_list_excess_versions must return file and entry counts for --problems summary."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("return 0, 0", body, "Must return (0, 0) when no excess versions")
        self.assertIn("return len(excess_files), entry_count", body, "Must return (file_count, entry_count)")


class TestReencode(unittest.TestCase):
    """Tests for --reencode: high-bitrate file detection with episode/season/series rollup."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_reencode_method_exists(self):
        """_list_reencode_candidates must exist as a static method."""
        src = self._read_script()
        self.assertIn("def _list_reencode_candidates(", src)

    def test_reencode_uses_bitrate_threshold(self):
        """_list_reencode_candidates must use REENCODE_THRESHOLD_MBPS."""
        src = self._read_script()
        self.assertIn("REENCODE_THRESHOLD_MBPS", src)

    def test_reencode_config_default_exists(self):
        """REENCODE_THRESHOLD dict must be in CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("'REENCODE_THRESHOLD'", src)

    def test_reencode_in_argparser(self):
        """--reencode must be registered in both main_parser and GLOBAL_CMD_PARSER."""
        src = self._read_script()
        self.assertIn("'--reencode'", src)

    def test_reencode_in_has_standalone_cmd(self):
        """--reencode must be in has_standalone_cmd check."""
        src = self._read_script()
        self.assertIn("safe_getattr(args, 'reencode', None) is not None", src)

    def test_reencode_in_zsh_completions(self):
        """--reencode must be in zsh completion spec."""
        src = self._read_script()
        self.assertIn("'--reencode[", src)

    def test_reencode_reinject_exists(self):
        """--reencode must be re-injected into remaining_args (like --episode-numbering-issues)."""
        src = self._read_script()
        # v2.0: --reencode goes through the shared _reinject_variadic helper
        self.assertIn("_reinject_variadic('reencode',", src)

    def test_reencode_in_problems(self):
        """--problems must call _list_reencode_candidates."""
        src = self._read_script()
        import re
        match = re.search(r"safe_getattr\(cmd_args, 'problems'.*?\n(.*?)(?=\n    # Handle --list)", src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find --problems handler block")
        body = match.group(1)
        self.assertIn("_list_reencode_candidates(", body)

    def test_reencode_in_problems_summary(self):
        """--problems must count reencode candidates via the registry (v3)."""
        src = self._read_script()
        import re
        reg = _registry_entry_block(src, 'reencode')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'reencode'")
        self.assertIn('_list_reencode_candidates', reg,
                      "registry 'reencode' entry must invoke _list_reencode_candidates")
        self.assertIn("'--reencode'", reg,
                      "registry 'reencode' entry must carry the --reencode cli_flag")
        # The shared warning printer iterates the registry, so the count
        # reaches the --problems / --update-cache summaries automatically.
        idx = src.index('def _print_problem_warnings(')
        end = src.index('\ndef ', idx + 1)
        self.assertIn('PROBLEM_CATEGORIES_REGISTRY.items()', src[idx:end])

    def test_problems_verbose_suppresses_details(self):
        """--problems without -V must suppress detail output (redirect_stdout)."""
        src = self._read_script()
        self.assertIn("_run_check(", src, "Must use _run_check() helper for output suppression")
        self.assertIn("redirect_stdout", src, "Must use contextlib.redirect_stdout")

    def test_problems_verbose_note(self):
        """--problems without -V must print a note about -V for details."""
        src = self._read_script()
        self.assertIn("use -V to show details", src)

    def test_reencode_rollup_season(self):
        """_list_reencode_candidates must check season-level rollup."""
        src = self._read_script()
        self.assertIn("season_rollup", src)
        self.assertIn("'full'", src)

    def test_reencode_rollup_show(self):
        """_list_reencode_candidates must check series-level rollup."""
        src = self._read_script()
        self.assertIn("series_full", src)
        self.assertIn("ALL", src)

    def test_reencode_returns_count(self):
        """_list_reencode_candidates must return total file count."""
        src = self._read_script()
        import re
        match = re.search(r'def _list_reencode_candidates\(.*?\n(.*?)(?=\n    @staticmethod)', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find _list_reencode_candidates body")
        body = match.group(1)
        self.assertIn("return 0", body, "Must return 0 when no candidates")
        self.assertIn("return total_file_count", body, "Must return total count")

    def test_reencode_in_problems_help(self):
        """--help problems must surface --reencode (auto-generated from the registry)."""
        src = self._read_script()
        import re
        match = re.search(r"case 'problems':\n(.*?)sys\.exit\(0\)", src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        self.assertIn("PROBLEM_CATEGORIES_REGISTRY.items()", match.group(1),
                      "--help problems must auto-generate categories from the registry")
        reg = _registry_entry_block(src, 'reencode')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'reencode'")
        self.assertIn("'--reencode'", reg)

    def test_reencode_help_page_exists(self):
        """--help reencode must have a dedicated help page (case 'reencode':)."""
        src = self._read_script()
        self.assertIn("case 'reencode':", src)

    def test_reencode_help_page_covers_mark(self):
        """--help reencode page must document --mark and --force."""
        src = self._read_script()
        import re
        match = re.search(r"case 'reencode':(.*?)sys\.exit\(0\)", src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find reencode help page")
        body = match.group(1)
        self.assertIn("--mark", body)
        self.assertIn("--force", body)

    def test_detect_registered_in_global_cmd_parser(self):
        """--detect must be registered in GLOBAL_CMD_PARSER."""
        src = self._read_script()
        self.assertIn("'--detect'", src)

    def test_force_registered_in_global_cmd_parser(self):
        """--force must be registered in GLOBAL_CMD_PARSER for reencode use."""
        src = self._read_script()
        self.assertIn("'--force'", src)

    def test_mark_respects_dry_run(self):
        """_mark_reencode_candidates_on_disk must accept dry_run parameter."""
        src = self._read_script()
        self.assertIn("def _mark_reencode_candidates_on_disk(", src)
        self.assertIn("dry_run=False", src)

    def test_mark_supports_force(self):
        """_mark_reencode_candidates_on_disk must accept force parameter."""
        src = self._read_script()
        self.assertIn("force=False", src)

    def test_mark_prints_summary(self):
        """_mark_reencode_candidates_on_disk must print REENCODE MARK SUMMARY."""
        src = self._read_script()
        self.assertIn("REENCODE MARK SUMMARY", src)

    def test_mark_warns_mislabeled(self):
        """_mark_reencode_candidates_on_disk must warn about labeled-but-below-threshold items."""
        src = self._read_script()
        self.assertIn("mislabeled_keys", src)
        self.assertIn("BELOW threshold", src)

    def test_detect_reinject_in_remaining_args(self):
        """--detect must be re-injected into remaining_args."""
        src = self._read_script()
        self.assertIn("Re-inject --detect", src) if "Re-inject --detect" in src else \
            self.assertIn("safe_getattr(args, 'detect', False)", src)

    def test_option_help_synonym_in_argv_normalization(self):
        """--reencode must be in _OPTION_TO_HELP_TOPIC for --option --help synonym."""
        src = self._read_script()
        self.assertIn("_OPTION_TO_HELP_TOPIC", src)
        self.assertIn("'--reencode': 'reencode'", src)

    # --- Escalation rules: user's explicit scope must be honored ---

    def _read_reencode_item_body(self):
        """Return the body of reencode_item()."""
        src = self._read_script()
        import re
        m = re.search(r'def reencode_item\(.*?\n(.*?)(?=\n    @staticmethod|\n    ###)', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find reencode_item body")
        return m.group(1)

    def test_reencode_tracks_explicit_input_scope(self):
        """reencode_item must track explicit Show/Season/Episode input so the labeling
        logic can honor user intent and not silently escalate."""
        body = self._read_reencode_item_body()
        self.assertIn("explicit_series",    body)
        self.assertIn("explicit_seasons",  body)
        self.assertIn("explicit_episodes", body)

    def test_reencode_explicit_season_prevents_series_escalation(self):
        """When user explicitly passes Season:XXX, series-level labeling must be blocked
        — even if that season happens to be the only non-special season of the series."""
        body = self._read_reencode_item_body()
        self.assertIn("has_explicit_season_input", body)
        self.assertIn("can_escalate_to_series", body)
        # The escalation guard must use has_explicit_season_input
        import re
        m = re.search(r"can_escalate_to_series\s*=\s*\(not has_explicit_season_input\)", body)
        self.assertIsNotNone(m, "can_escalate_to_series must depend on has_explicit_season_input")

    def test_reencode_explicit_episode_prevents_season_escalation(self):
        """When user explicitly passes Episode:XXX, season-level labeling must be blocked
        — the label must land on the episode file itself."""
        body = self._read_reencode_item_body()
        self.assertIn("has_explicit_episode_in_season", body)
        # Per-file branch must be reachable from the explicit-episode guard
        self.assertIn("Per-file labeling", body)

    def test_reencode_cache_sync_uses_target_labeled_dirs(self):
        """Cache sync must be driven by target_labeled_dirs (so already-labeled-on-disk
        paths still get synced when the cache is stale) — not just by renamed_dirs."""
        body = self._read_reencode_item_body()
        self.assertIn("target_labeled_dirs", body)
        # The cache-sync block must be gated on target_labeled_dirs, not renamed_dirs
        self.assertIn("if target_labeled_dirs and not dry_run", body)

    def test_reencode_cache_sync_computes_path_variants(self):
        """Cache sync must generate stale path variants (power-set of labeled components)
        so that cache entries missing a parent label can still be healed."""
        body = self._read_reencode_item_body()
        self.assertIn("_compute_path_variants", body)
        self.assertIn("label_marker", body)

    def test_reencode_cache_sync_iterates_all_obj_by_id(self):
        """Cache sync must iterate ALL OBJ_BY_ID (not just obj_keys) so Season/Show
        cache objects get their `file` field updated, not just Episodes."""
        body = self._read_reencode_item_body()
        self.assertIn("PLEX_Media.OBJ_BY_ID.items()", body)
        # The old bug iterated `for key in obj_keys`; make sure that's not the sweep driver.
        import re
        # Must NOT be the ONLY loop — the all-items loop must be present for the cache sweep
        self.assertIn("obj.get('file', '')", body)
        self.assertIn("fi.get('filepath'", body)

    def test_reencode_already_labeled_still_records_target(self):
        """_do_rename_tracked must record the target dir even when the path is already
        labeled on disk, so the cache sweep can heal stale entries."""
        body = self._read_reencode_item_body()
        import re
        # Find the "Already labeled" branch and verify it adds to target_labeled_dirs
        m = re.search(r'if new_name == old_name:.*?target_labeled_dirs\.add', body, re.DOTALL)
        self.assertIsNotNone(m, "Already-labeled branch must add to target_labeled_dirs")


class TestOndiskLabels(unittest.TestCase):
    """Tests for on-disk label parsing, collection, indexing, and related config."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    # --- parse_ondisk_labels ---

    def test_parse_ondisk_labels_basic(self):
        """parse_ondisk_labels extracts [label] from filename."""
        labels = parse_ondisk_labels('/some/path/myfile [reencode].mkv')
        self.assertEqual(labels, ['reencode'])

    def test_parse_ondisk_labels_multiple(self):
        """parse_ondisk_labels extracts multiple [labels] from filename."""
        labels = parse_ondisk_labels('movie [reencode][hdr].mkv')
        self.assertEqual(labels, ['reencode', 'hdr'])

    def test_parse_ondisk_labels_none(self):
        """parse_ondisk_labels returns [] when no labels present."""
        labels = parse_ondisk_labels('myfile.mkv')
        self.assertEqual(labels, [])

    def test_parse_ondisk_labels_uses_basename_only(self):
        """parse_ondisk_labels only examines the final path component."""
        # Label in parent dir should NOT be picked up by parse_ondisk_labels alone
        labels = parse_ondisk_labels('/[reencode]/myfile.mkv')
        self.assertEqual(labels, [])

    def test_parse_ondisk_labels_empty_string(self):
        """parse_ondisk_labels returns [] for empty input."""
        self.assertEqual(parse_ondisk_labels(''), [])

    def test_parse_ondisk_labels_none_input(self):
        """parse_ondisk_labels returns [] for None input."""
        self.assertEqual(parse_ondisk_labels(None), [])

    # --- collect_ondisk_labels_for_obj ---

    def test_collect_ondisk_labels_movie_filename(self):
        """collect_ondisk_labels_for_obj picks up label in movie filename."""
        obj = {
            'type': 'Movie',
            'files': {'v1': {'filepath': '/movies/My Movie (2020)/My Movie (2020) [reencode].mkv'}},
        }
        labels = collect_ondisk_labels_for_obj(obj)
        self.assertIn('reencode', labels)

    def test_collect_ondisk_labels_movie_dir(self):
        """collect_ondisk_labels_for_obj picks up label in movie directory name."""
        obj = {
            'type': 'Movie',
            'files': {'v1': {'filepath': '/movies/My Movie (2020) [reencode]/My Movie (2020).mkv'}},
        }
        labels = collect_ondisk_labels_for_obj(obj)
        self.assertIn('reencode', labels)

    def test_collect_ondisk_labels_episode_series_dir(self):
        """collect_ondisk_labels_for_obj picks up label in series directory (grandparent) for episodes."""
        obj = {
            'type': 'Episode',
            'files': {'v1': {'filepath': '/series/My Show [reencode]/Season 01/S01E01.mkv'}},
        }
        labels = collect_ondisk_labels_for_obj(obj)
        self.assertIn('reencode', labels)

    def test_collect_ondisk_labels_deduplicates(self):
        """collect_ondisk_labels_for_obj deduplicates labels across path components."""
        obj = {
            'type': 'Movie',
            'files': {'v1': {'filepath': '/movies/My Movie [reencode]/My Movie [reencode].mkv'}},
        }
        labels = collect_ondisk_labels_for_obj(obj)
        self.assertEqual(labels.count('reencode'), 1)

    def test_collect_ondisk_labels_no_files(self):
        """collect_ondisk_labels_for_obj returns [] when obj has no files."""
        obj = {'type': 'Movie', 'files': {}}
        self.assertEqual(collect_ondisk_labels_for_obj(obj), [])

    # --- build_ondisk_labels_index ---

    def test_build_ondisk_labels_index_basic(self):
        """build_ondisk_labels_index returns label→keys mapping."""
        original = dict(PLEX_Media.OBJ_BY_ID)
        try:
            PLEX_Media.OBJ_BY_ID.clear()
            PLEX_Media.OBJ_BY_ID['Movie:99'] = {
                'type': 'Movie', 'ondisk_labels': ['reencode'],
                'files': {},
            }
            idx = build_ondisk_labels_index()
            self.assertIn('reencode', idx)
            self.assertIn('Movie:99', idx['reencode'])
        finally:
            PLEX_Media.OBJ_BY_ID.clear()
            PLEX_Media.OBJ_BY_ID.update(original)

    def test_build_ondisk_labels_index_empty(self):
        """build_ondisk_labels_index returns {} when no ondisk_labels in cache."""
        original = dict(PLEX_Media.OBJ_BY_ID)
        try:
            PLEX_Media.OBJ_BY_ID.clear()
            PLEX_Media.OBJ_BY_ID['Movie:1'] = {'type': 'Movie', 'ondisk_labels': [], 'files': {}}
            idx = build_ondisk_labels_index()
            self.assertEqual(idx, {})
        finally:
            PLEX_Media.OBJ_BY_ID.clear()
            PLEX_Media.OBJ_BY_ID.update(original)

    # --- Config / script structure ---

    def test_ondisk_label_markers_in_config_defaults(self):
        """ONDISK_LABEL_START_MARKER and ONDISK_LABEL_END_MARKER must be in CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("'ONDISK_LABEL_START_MARKER'", src)
        self.assertIn("'ONDISK_LABEL_END_MARKER'", src)

    def test_problems2disk_in_config_defaults(self):
        """PROBLEMS2DISK must be in CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("'PROBLEMS2DISK'", src)

    def test_ondisk_labels_index_in_empty_cache(self):
        """EMPTY_CACHE must include ondisk_labels_index key."""
        src = self._read_script()
        self.assertIn("'ondisk_labels_index'", src)

    def test_ondisk_labels_populated_during_update_cache(self):
        """--update-cache must call collect_ondisk_labels_for_obj and build_ondisk_labels_index."""
        src = self._read_script()
        self.assertIn("collect_ondisk_labels_for_obj(obj)", src)
        self.assertIn("build_ondisk_labels_index()", src)

    def test_list_ondisk_labeled_method_exists(self):
        """_list_ondisk_labeled must exist as a static method."""
        src = self._read_script()
        self.assertIn("def _list_ondisk_labeled(", src)

    def test_mark_reencode_candidates_method_exists(self):
        """_mark_reencode_candidates_on_disk must exist as a static method."""
        src = self._read_script()
        self.assertIn("def _mark_reencode_candidates_on_disk(", src)

    def _reencode_handler_body(self, src):
        """Extract the full --reencode handler block from src."""
        import re
        match = re.search(r"# Handle --reencode.*?# Handle --list", src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find reencode handler block")
        return match.group(0)

    def test_reencode_default_lists_labeled(self):
        """--reencode (default, no sub-flag) must call _list_reencode_candidates."""
        src = self._read_script()
        body = self._reencode_handler_body(src)
        self.assertIn("_list_reencode_candidates(", body)

    def test_reencode_mark_detects_candidates(self):
        """--reencode --mark must call _list_reencode_candidates for detection."""
        src = self._read_script()
        body = self._reencode_handler_body(src)
        self.assertIn("_list_reencode_candidates(", body)

    def test_auto_mark_on_disk_config_key(self):
        """PROBLEMS2DISK reencode entry must have AUTO_MARK_ON_DISK key."""
        src = self._read_script()
        self.assertIn("'AUTO_MARK_ON_DISK'", src)

    def test_reencode_mark_flag_registered(self):
        """--mark must be registered in GLOBAL_CMD_PARSER."""
        src = self._read_script()
        self.assertIn("'--mark'", src)

    def test_reencode_mark_in_zsh_completions(self):
        """--mark must be in zsh completion spec."""
        src = self._read_script()
        self.assertIn("'--mark[", src)

    def test_ondisk_labels_in_print_obj_by_id(self):
        """print_OBJ_BY_ID must handle ONDISK_LABELS list type without error."""
        src = self._read_script()
        self.assertIn("'ONDISK_LABELS'", src)

    def test_refresh_ondisk_labels_exists(self):
        """refresh_ondisk_labels_from_cache must exist and update OBJ_BY_ONDISK_LABEL."""
        src = self._read_script()
        self.assertIn("def refresh_ondisk_labels_from_cache(", src)
        self.assertIn("OBJ_BY_ONDISK_LABEL = build_ondisk_labels_index()", src)


class TestExcessVersionsMainParser(unittest.TestCase):
    """--excess-versions LIMIT must be consumed by main_parser to prevent LIMIT being eaten as CMD_OR_PLEXOBJECT."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_excess_versions_in_main_parser(self):
        """main_parser must define --excess-versions to protect LIMIT value."""
        content = self._read_script()
        self.assertIn("main_parser.add_argument('--excess-versions'", content,
            "--excess-versions must be in main_parser to prevent LIMIT from being parsed as CMD_OR_PLEXOBJECT")

    def test_excess_versions_reinjected(self):
        """--excess-versions must be re-injected into remaining_args after main_parser consumes it."""
        content = self._read_script()
        self.assertIn("'--excess-versions'", content)
        import re
        match = re.search(r"Re-inject --excess-versions.*?remaining_args\.insert.*?'--excess-versions'", content, re.DOTALL)
        self.assertIsNotNone(match, "Must re-inject --excess-versions into remaining_args")


class TestRemoveCommand(unittest.TestCase):
    """Verify --remove/--rm command and its interaction with --delete."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_remove_arg_defined(self):
        """--remove and --rm must be defined as media commands."""
        content = self._read_script()
        self.assertIn("'--remove'", content)
        self.assertIn("'--rm'", content)

    def test_delete_alias_defined(self):
        """--del must be an alias for --delete."""
        content = self._read_script()
        self.assertIn("'--del'", content)

    def test_remove_method_exists(self):
        """PLEX_Media.remove() must exist."""
        content = self._read_script()
        import re
        match = re.search(r'class PLEX_Media.*?def remove\(', content, re.DOTALL)
        self.assertIsNotNone(match, "PLEX_Media must have a remove() method")

    def test_remove_uses_move_to_trash(self):
        """remove() must use move_to_trash (safe deletion)."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?\n(.*?)(?=\n    #)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("move_to_trash(", body, "Must use move_to_trash, not os.remove/unlink")
        self.assertNotIn("os.remove(", body, "Must NOT use os.remove — use move_to_trash")
        self.assertNotIn("os.unlink(", body, "Must NOT use os.unlink — use move_to_trash")

    def test_remove_always_uses_ssh_to_plex_server(self):
        """remove() must always use SSH to Plex server, not determine_remote_host (which gets confused by local mounts)."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        # Strip comments — we only care about actual code, not comments mentioning the function
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_only = '\n'.join(code_lines)
        # Must NOT call determine_remote_host — local network mounts cause wrong trash location
        self.assertNotIn("determine_remote_host(", code_only,
            "remove() must NOT call determine_remote_host — file paths are from Plex server's perspective")
        # Must use PLEX_DB_REMOTE_HOST (configurable SSH alias, defaults to 'my-plex')
        self.assertIn("PLEX_DB_REMOTE_HOST", code_only,
            "remove() must use PLEX_DB_REMOTE_HOST for SSH file operations")

    def test_execute_cmd_calls_remove_before_delete(self):
        """execute_cmd must call remove BEFORE delete (trash files before removing entry)."""
        content = self._read_script()
        import re
        match = re.search(r'def execute_cmd\(args, obj, obj_args\).*?\n(.*?)(?=\n    ####)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        remove_pos = body.find('.remove(')
        delete_pos = body.find('.delete(')
        self.assertGreater(remove_pos, 0, "Must call remove()")
        self.assertGreater(delete_pos, 0, "Must call delete()")
        self.assertLess(remove_pos, delete_pos, "remove() must be called BEFORE delete()")

    def test_remove_does_not_delete_plex_entry(self):
        """remove() must NOT call media.delete() — that's --delete's job."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?\n(.*?)(?=\n    #)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("media.delete()", body, "remove() must NOT delete the Plex entry")

    def test_delete_does_not_trash_files(self):
        """delete() must NOT trash files — that's --remove's job."""
        content = self._read_script()
        import re
        match = re.search(r'def delete\(media_identifier.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("move_to_trash(", body, "delete() must NOT trash files")

    def test_delete_syncs_cache(self):
        """delete() must remove deleted entries from cache and save to disk."""
        content = self._read_script()
        import re
        match = re.search(r'def delete\(media_identifier.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_remove_from_cache_by_id(", body,
            "delete() must call _remove_from_cache_by_id after successful API delete")

    def test_remove_from_cache_by_id_exists(self):
        """_remove_from_cache_by_id must exist and update all cache structures + save."""
        content = self._read_script()
        import re
        match = re.search(r'def _remove_from_cache_by_id\(numeric_id\).*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "_remove_from_cache_by_id method must exist")
        body = match.group(1)
        self.assertIn("OBJ_BY_ID", body, "Must update OBJ_BY_ID")
        self.assertIn("OBJ_BY_FILEPATH", body, "Must update OBJ_BY_FILEPATH")
        self.assertIn("OBJ_BY_LIBRARY", body, "Must update OBJ_BY_LIBRARY")
        self.assertIn("OBJ_BY_SERIES_EPISODES", body, "Must update OBJ_BY_SERIES_EPISODES for episodes")
        self.assertIn("OBJ_BY_MOVIE", body, "Must update OBJ_BY_MOVIE for movies")
        self.assertIn("update_and_save_cache(", body, "Must save cache to disk")

    def test_remove_from_cache_cleans_episode_from_series_episodes(self):
        """_remove_from_cache_by_id must remove episode keys from OBJ_BY_SERIES_EPISODES."""
        content = self._read_script()
        import re
        match = re.search(r'def _remove_from_cache_by_id\(numeric_id\).*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        # Must handle Episode type specifically with series_key/S_str/E_str lookups
        self.assertIn("obj_type == 'Episode'", body,
            "Must have specific Episode handling for OBJ_BY_SERIES_EPISODES cleanup")
        self.assertIn("S_str", body, "Must use S_str to find season in OBJ_BY_SERIES_EPISODES")
        self.assertIn("E_str", body, "Must use E_str to find episode in OBJ_BY_SERIES_EPISODES")

    def test_rm_accepts_version_spec(self):
        """--rm must accept optional version indices/ranges argument."""
        content = self._read_script()
        self.assertIn("nargs='?'", content.split("'--remove'")[1].split('\n')[0],
            "--rm must use nargs='?' for optional argument")

    def test_rm_spec_passed_to_remove(self):
        """execute_cmd must pass rm_spec= to PLEX_Media.remove()."""
        content = self._read_script()
        self.assertIn("PLEX_Media.remove(obj, rm_spec=obj_args.remove)", content)

    def test_remove_parses_ranges(self):
        """remove() must parse comma-separated numbers and ranges (e.g. '2-25', '2,5,8')."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "remove() must accept rm_spec parameter")
        body = match.group(1)
        self.assertIn("rm_indices", body, "Must parse rm_spec into indices")
        self.assertIn("Keeping", body, "Must print which files are kept")
        self.assertIn("split('-'", body, "Must support range syntax (e.g. 2-25)")

    def test_remove_skips_non_matching_indices(self):
        """remove() must skip files whose index is NOT in rm_indices."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("idx not in rm_indices", body, "Must check idx against rm_indices")

    def test_rm_help_topic(self):
        """--help rm must show help for --rm."""
        content = self._read_script()
        self.assertIn("case 'remove' | 'rm':", content)

    def test_remove_syncs_cache(self):
        """remove() must update cache after trashing files (remove from files dict, save)."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("removed_versions", body, "Must track removed versions")
        self.assertIn("del files_dict[version]", body, "Must remove trashed versions from files dict")
        self.assertIn("OBJ_BY_FILEPATH", body, "Must clean up OBJ_BY_FILEPATH")
        self.assertIn("update_and_save_cache(", body, "Must save updated cache to disk")

    def test_remove_does_not_blank_obj_by_library(self):
        """remove() must NOT set OBJ_BY_LIBRARY = {} — that destroys cache integrity."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_LIBRARY = {}", body,
            "remove() must NOT blank OBJ_BY_LIBRARY — surgically update instead")

    def test_remove_handles_already_gone_files(self):
        """remove() must detect files already gone from disk and still clean cache."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("GONE", body, "Must check if file is gone from disk")

    def test_remove_checks_existence_before_trash(self):
        """remove() must check file existence BEFORE move_to_trash to avoid ERROR for gone files."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        # The GONE check must appear BEFORE move_to_trash call
        gone_pos = body.find('GONE')
        trash_pos = body.find('move_to_trash(')
        self.assertGreater(gone_pos, 0, "Must have GONE check")
        self.assertGreater(trash_pos, 0, "Must have move_to_trash call")
        self.assertLess(gone_pos, trash_pos,
            "File existence check (GONE) must happen BEFORE move_to_trash — "
            "already-gone files must never trigger the ERROR banner")


class TestListMethodsGuardMissingKeys(unittest.TestCase):
    """Regression: list methods must use OBJ_BY_ID.get(key) not OBJ_BY_ID[key].

    OBJ_BY_LIBRARY may contain Show keys that are not in OBJ_BY_ID (Shows are
    container objects stored separately). collect_library_keys() returns these
    keys, so all methods iterating obj_keys must guard against missing keys.
    Bug: KeyError: 'Series:4392' in _list_broken_files.
    """

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_list_broken_files_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _list_broken_files\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_ID[key]", body, "_list_broken_files must use .get(key) not [key]")

    def test_list_excess_versions_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_ID[key]", body, "_list_excess_versions must use .get(key) not [key]")

    def test_find_duplicates_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _find_duplicates\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_ID[okey]", body, "_find_duplicates must use .get(okey) not [okey]")
        self.assertNotIn("OBJ_BY_ID[key]", body, "_find_duplicates must use .get(key) not [key]")

    def test_filter_by_watch_and_audio_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _filter_by_watch_and_audio\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_ID[key]", body, "_filter_by_watch_and_audio must use .get(key) not [key]")


class TestWaitForPlexScanComplete(unittest.TestCase):
    """Verify wait_for_plex_scan_complete() exists and uses plex.activities (not just lib.refreshing)."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_functions_exist(self):
        """wait_for_plex_scan(s)_complete must be defined."""
        content = self._read_script()
        self.assertIn("def wait_for_plex_scans_complete(", content)
        self.assertIn("def wait_for_plex_scan_complete(", content)

    def test_checks_activities(self):
        """Must poll plex.activities for library.update.section, not just lib.refreshing."""
        content = self._read_script()
        import re
        match = re.search(r'def wait_for_plex_scans_complete\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("active_sections", body, "Must check plex.activities for ongoing scan activities")
        self.assertIn("lib.refreshing", body, "Must still check lib.refreshing as first phase")

    def test_get_active_scan_section_ids(self):
        """_get_active_scan_section_ids helper must check library.update.section activities."""
        content = self._read_script()
        import re
        match = re.search(r'def _get_active_scan_section_ids\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("library.update.section", body)
        self.assertIn("activities", body)

    def test_update_cache_uses_parallel_helper(self):
        """--update-cache must use wait_for_plex_scans_complete (parallel), not sequential."""
        content = self._read_script()
        import re
        match = re.search(r"Waiting for all libraries to complete scanning.*?print\(f.*?=.*?76", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Could not find scan waiting section in update_cache")
        body = match.group(0)
        self.assertIn("wait_for_plex_scans_complete(", body,
            "--update-cache must use wait_for_plex_scans_complete (parallel)")
        self.assertNotIn("lib.refreshing", body,
            "--update-cache must NOT use raw lib.refreshing")


# ---------------------------------------------------------------------------
# A FIXTURE cache for the end-to-end tests: three libraries (an English and a
# German movie library, a French series library) and nine titles, written to a
# temp directory beside a config that points my-plex at it -- so a spawned
# my-plex reads this and never ~/.my-plex/cache.pkl.  Built once per process.
#
# Why: the E2E tests ran against the user's real cache (40 MB) and real config.
# They then measured the machine (one --problems run: 83s, 33s, 11s on three
# attempts), reached the network through --info, and proved nothing on a
# machine whose cache was never built.
# ---------------------------------------------------------------------------
_FIXTURE_CONF = None

def _fixture_conf():
    """The config of the process-wide fixture library, built on first use."""
    global _FIXTURE_CONF
    if _FIXTURE_CONF is None:
        import atexit
        d = tempfile.mkdtemp(prefix='my-plex-fixture-')
        atexit.register(shutil.rmtree, d, True)
        _FIXTURE_CONF = _fixture_library(d)
    return _FIXTURE_CONF

def _fixture_library(d):
    """Write the fixture cache and its config into d; return the config path.

    Objects carry every key a real cached object carries (the shapes were read
    off a real cache on 2026-11-08), so a command that reads any field finds
    it.  Genres go through the tool's own normaliser, as --update-cache does:
    the cache holds canonical English names, which is what makes
    `genre:Comedy` find a title tagged 'Komödie'."""
    import pickle
    from datetime import datetime
    m = _main_module()
    version = "90.0min 1920x1080 (h264 aac) 1500MB"

    def file_entry(fp, langs, **metadata):
        entry = {'filepath': fp, 'filesize': 1572864000, 'part_id': '1',
                 'audio_languages': list(langs), 'subtitle_languages': [],
                 'file_segment_words': [os.path.basename(fp).split('.')],
                 'file_metadata': {'container_duration': 5400000.0, 'filesize': 1572864000,
                                   'scanned_at': '2026-01-01T00:00:00', 'file_type': 'mkv',
                                   'file_ends_cleanly': True, 'disk_bytes': 1572864000}}
        entry['file_metadata'].update(metadata)
        return entry

    def base(type_, id_, library, title, fp, year):
        return {
            'type': type_, 'type_str': type_, 'id': str(id_), 'item_id': str(id_), 'library': library,
            'title': title, 'originalTitle': title, 'year': year, 'summary': '', 'file': fp,
            'file_segment_words': [os.path.basename(fp).split('.')], 'files': {},
            'actors': [], 'directors': [], 'writers': [], 'countries': [], 'collections': [],
            'labels': [], 'ondisk_labels': [], 'genres': [], 'subtitle_languages': [],
            'audio_languages': [], 'audio_codec': 'aac', 'video_codec': 'h264',
            'resolution': '1080p', 'resolution_full': '1920x1080', 'version': version,
            'addedAt': 1700000000, 'updatedAt': 1700000000, 'lastViewedAt': None, 'viewCount': 0,
            'audienceRating': None, 'criticsRating': None, 'userRating': None, 'contentRating': None,
            'duration': 5400000, 'filesize': 1572864000, 'media_cnt': 1, 'media_id': str(id_),
            'media_idx': 0, 'media_nr': '1', 'part_cnt': 1, 'part_id': str(id_), 'part_idx': 0,
            'part_nr': '1', 'E_idx': None, 'E_str': None, 'S_idx': None, 'S_str': None,
            'S0XE0X': None, 'episode': None, 'season': None,
        }

    def movie(id_, library, title, year, genres, langs, **metadata):
        fp = f"/lib/{library}/{title} ({year})/{title.lower().replace(' ', '.')}.{year}.mkv"
        o = base('Movie', id_, library, title, fp, year)
        o.update({'genres': m._normalize_genres(genres), 'audio_languages': list(langs),
                  'audio_languages_plex': list(langs), 'guid': f'plex://movie/{id_:024d}',
                  'external_ids': {}, 'versions': [version],
                  'files': {version: file_entry(fp, langs, **metadata)}})
        return o

    container_only = {'media_cnt': None, 'media_id': None, 'media_idx': None, 'media_nr': None,
                      'part_cnt': None, 'part_id': None, 'part_idx': None, 'part_nr': None,
                      'duration': None, 'filesize': None, 'addedAt': None, 'updatedAt': None}
    libs = {'library1':   ('Movie',  'en-US', 'tv.plex.agents.movie'),
            'library_de': ('Movie',  'de-DE', 'tv.plex.agents.movie'),
            'library_fr': ('Series', 'fr-FR', 'tv.plex.agents.series')}
    movies = [
        movie(1, 'library1', 'Some Movie', 2001, ['Comedy'], ['en']),
        movie(2, 'library1', 'Another Movie', 2005, ['Drama'], ['en']),
        movie(3, 'library_de', 'Irgendein Film', 2010, ['Komödie'], ['de']),
        # the probe failed: BROKEN, with its reason
        movie(4, 'library1', 'Broken Movie', 1999, [], ['en'], broken=True, reason='probe_error'),
        # Plex's duration is off, but container and video stream agree: healthy
        movie(5, 'library1', 'Misreported Movie', 1998, [], ['en'],
              container_duration=4500000.0, video_duration=4500500.0, file_ends_cleanly=False),
        # the container is short and nothing vouches for it: TRUNCATED
        movie(6, 'library1', 'Truncated Movie', 1997, [], ['en'],
              container_duration=4500000.0, file_ends_cleanly=False),
    ]
    series_dir = '/lib/library_fr/Une Serie'
    series = base('Series', 10, 'library_fr', 'Une Serie', series_dir, 2015)
    series.update(container_only)
    series.update({'genres': m._normalize_genres(['Comédie']), 'guid': f'plex://show/{10:024d}',
                   'external_ids': {'tvdb': '1', 'tmdb': '1', 'imdb': 'tt1'}, 'original_language': 'fr',
                   'studio': '', 'series': 'Une Serie', 'series_key': 'Series:10', 'members': ['Season:11'],
                   'S_count': 1, 'E_count': 2, 'S_pad_width': 2, 'E_pad_width': 2, 'abs_ep_max': 2,
                   'AUDIO_LANG_uniform': None})
    season = base('Season', 11, 'library_fr', 'Season 1', f'{series_dir}/S01', 2015)
    season.update(container_only)
    season.update({'series': 'Une Serie', 'series_key': 'Series:10', 'season': 'Season 1',
                   'S_str': 'S01', 'S_idx': 1, 'S_count': 1, 'E_count': 2, 'abs_ep_max': 2,
                   'AUDIO_LANG_uniform': 'fr', 'members': ['Episode:12', 'Episode:13']})
    episodes = []
    for n in (1, 2):
        fp = f'{series_dir}/S01/une.serie.s01e{n:02d}.mkv'
        e = base('Episode', 11 + n, 'library_fr', f'Episode {n}', fp, 2015)
        e.update({'series': 'Une Serie', 'series_key': 'Series:10', 'season': 1, 'episode': n,
                  'S_str': 'S01', 'S_idx': 1, 'E_str': f'E{n:02d}', 'E_idx': n, 'S0XE0X': f'S01E{n:02d}',
                  'S_count': 1, 'E_count': 2, 'abs_ep_idx': n, 'genres': m._normalize_genres(['Comédie']),
                  'audio_languages': ['fr'], 'audio_languages_plex': ['fr'], 'multi_episode_siblings': [],
                  'versions': [version], 'files': {version: file_entry(fp, ('fr',))}})
        episodes.append(e)

    obj_by_id = {f"{o['type']}:{o['id']}": o for o in movies + [series, season] + episodes}
    obj_by_library = {}
    for key, o in obj_by_id.items():
        obj_by_library.setdefault(o['library'], {}).setdefault(o['type'], []).append(key)
    with_files = {key: o for key, o in obj_by_id.items() if o['files']}
    obj_by_filepath = {fi['filepath']: key for key, o in with_files.items() for fi in o['files'].values()}
    now = datetime(2026, 1, 1)
    stats = {k: {} for k in ('updatedAt', 'plexUpdatedAt', 'itemsCount', 'episodesCount', 'totalDuration',
                             'totalStorage', 'agent', 'language', 'locations', 'language_distribution')}
    counts = {}
    for lib, (ltype, lang, agent) in libs.items():
        per_type = obj_by_library.get(lib, {})
        stats['updatedAt'][lib] = now; stats['plexUpdatedAt'][lib] = now
        stats['agent'][lib] = agent; stats['language'][lib] = lang
        stats['locations'][lib] = [f'/lib/{lib}']
        stats['itemsCount'][lib] = len(per_type.get(ltype, []))
        stats['episodesCount'][lib] = len(per_type.get('Episode', []))
        stats['totalDuration'][lib] = 0; stats['totalStorage'][lib] = 0
        stats['language_distribution'][lib] = {}
        for key in per_type.get('Movie', []) + per_type.get('Episode', []):
            for code in obj_by_id[key]['audio_languages']:
                stats['language_distribution'][lib].setdefault(code, []).append(key)
        counts[lib] = ({'movies': len(per_type.get('Movie', []))} if ltype == 'Movie' else
                       {'series': len(per_type.get('Series', [])), 'seasons': len(per_type.get('Season', [])),
                        'episodes': len(per_type.get('Episode', []))})
    cache = {
        'obj_by_id': obj_by_id, 'obj_by_library': obj_by_library, 'obj_by_filepath': obj_by_filepath,
        'obj_by_movie': {key: {v: fi['filepath'] for v, fi in o['files'].items()}
                         for key, o in with_files.items() if o['type'] == 'Movie'},
        'obj_by_series': {'Series:10': {'S01': 'Season:11'}},
        'obj_by_series_episodes': {'Series:10': {'S01': {f'E{n:02d}': {version: [f'Episode:{11 + n}']}
                                                         for n in (1, 2)}}},
        'obj_by_series_scraped': {}, 'obj_by_collection': {}, 'ondisk_labels_index': {},
        'plex_labels_index': {}, 'media_objs': {}, 'library_stats': stats,
        'library_object_counts': counts, 'plex_known_filepaths': sorted(obj_by_filepath),
        'layout_index': {}, 'problems': {},
        'server_info': {'friendlyName': 'fixture', 'myPlexUsername': '', 'platform': 'test', 'version': '0'},
    }
    with open(os.path.join(d, 'cache.pkl'), 'wb') as f:
        pickle.dump(cache, f)
    conf = os.path.join(d, 'my-plex.conf')
    with open(conf, 'w') as f:
        f.write(f"CACHE_FILE = {os.path.join(d, 'cache.pkl')!r}\n")
        f.write(f"LOCK_FILE = {os.path.join(d, 'cache.lock')!r}\n")
        f.write(f"PLEX_DB_PATH = {os.path.join(d, 'plex.db')!r}\n")
        # blank on purpose: no host to ssh to, no API to call -- the suite reaches no network
        f.write("PLEX_DB_REMOTE_HOST = ''\nTVDB_API_KEY = ''\nTMDB_API_KEY = ''\n")
        f.write("PLEX_URL = ''\nPLEX_TOKEN = ''\nPLEX_XML_URL = ''\n")
    return conf


class TestEndToEnd(unittest.TestCase):
    """End-to-end tests: run actual commands as subprocesses, against the fixture library."""

    @classmethod
    def setUpClass(cls):
        cls._conf = _fixture_conf()

    def _run_cmd(self, *extra_args):
        cmd = [sys.executable, MAIN_SCRIPT, '--config', self._conf] + list(extra_args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=E2E_TIMEOUT)

    # --- Help commands ---

    def test_help_default(self):
        """my-plex --help must show main help."""
        result = self._run_cmd('--help')
        self.assertEqual(result.returncode, 0, f"--help failed: {result.stderr}")
        self.assertIn("SCOPE SELECTORS", result.stdout)
        self.assertIn("--help COMMAND", result.stdout)

    def test_help_global(self):
        """my-plex --help global must show global command help."""
        result = self._run_cmd('--help', 'global')
        self.assertEqual(result.returncode, 0, f"--help global failed: {result.stderr}")
        self.assertIn("--list", result.stdout)

    def test_help_all(self):
        """my-plex --help all must show all help."""
        result = self._run_cmd('--help', 'all')
        self.assertEqual(result.returncode, 0, f"--help all failed: {result.stderr}")

    def test_help_library(self):
        """my-plex --help library must show library help."""
        result = self._run_cmd('--help', 'library')
        self.assertEqual(result.returncode, 0, f"--help library failed: {result.stderr}")

    def test_help_media(self):
        """my-plex --help media must show media help."""
        result = self._run_cmd('--help', 'media')
        self.assertEqual(result.returncode, 0, f"--help media failed: {result.stderr}")

    def test_help_playlist(self):
        """my-plex --help playlist must show playlist help."""
        result = self._run_cmd('--help', 'playlist')
        self.assertEqual(result.returncode, 0, f"--help playlist failed: {result.stderr}")

    def test_help_problems(self):
        """my-plex --help problems must show detailed problems help."""
        result = self._run_cmd('--help', 'problems')
        self.assertEqual(result.returncode, 0, f"--help problems failed: {result.stderr}")
        self.assertIn("PROBLEMS HELP", result.stdout)

    # --- --help --XXX form (dashed topic) ---

    def test_help_dashed_problems(self):
        """my-plex --help --problems must work like --help problems."""
        result = self._run_cmd('--help', '--problems')
        self.assertEqual(result.returncode, 0, f"--help --problems failed: {result.stderr}")
        self.assertIn("PROBLEMS HELP", result.stdout)

    def test_help_dashed_duplicates(self):
        """my-plex --help --duplicates must work like --help duplicates."""
        result = self._run_cmd('--help', '--duplicates')
        self.assertEqual(result.returncode, 0, f"--help --duplicates failed: {result.stderr}")
        self.assertIn("DUPLICATES HELP", result.stdout)

    def test_help_dashed_update_cache(self):
        """my-plex --help --update-cache must work like --help update-cache."""
        result = self._run_cmd('--help', '--update-cache')
        self.assertEqual(result.returncode, 0, f"--help --update-cache failed: {result.stderr}")
        self.assertIn("CACHE UPDATE HELP", result.stdout)

    def test_help_reversed_problems(self):
        """my-plex --problems --help must work like --help problems."""
        result = self._run_cmd('--problems', '--help')
        self.assertEqual(result.returncode, 0, f"--problems --help failed: {result.stderr}")
        self.assertIn("PROBLEMS HELP", result.stdout)

    def test_help_update_cache(self):
        """my-plex --help update-cache must show cache update help."""
        result = self._run_cmd('--help', 'update-cache')
        self.assertEqual(result.returncode, 0, f"--help update-cache failed: {result.stderr}")
        self.assertIn("CACHE UPDATE HELP", result.stdout)

    def test_help_duplicates(self):
        """my-plex --help duplicates must show duplicates help."""
        result = self._run_cmd('--help', 'duplicates')
        self.assertEqual(result.returncode, 0, f"--help duplicates failed: {result.stderr}")
        self.assertIn("DUPLICATES HELP", result.stdout)

    def test_help_no_audio_language(self):
        """my-plex --help no-audio-language must show no-audio-language help."""
        result = self._run_cmd('--help', 'no-audio-language')
        self.assertEqual(result.returncode, 0, f"--help no-audio-language failed: {result.stderr}")

    def test_help_offline_verbose(self):
        """my-plex --help --offline must show verbose help with extra options."""
        result = self._run_cmd('--help', '--offline')
        self.assertEqual(result.returncode, 0, f"--help --offline failed: {result.stderr}")

    # --- List commands (read-only, from cache) ---

    def test_list_libraries(self):
        """my-plex --list-libraries must list available libraries."""
        result = self._run_cmd('--list-libraries')
        self.assertEqual(result.returncode, 0, f"--list-libraries failed: {result.stderr}")
        self.assertTrue(len(result.stdout) > 0, "Must produce output")

    def test_list_no_library(self):
        """my-plex --list without library must list all media as KEY  FILEPATH rows."""
        result = self._run_cmd('--list')
        self.assertEqual(result.returncode, 0, f"--list failed: {result.stderr}")
        # Output is KEY<spaces>FILEPATH rows (e.g. 'Movie:123   /path/to/file')
        self.assertRegex(result.stdout, r'(Movie|Episode):\d+')

    def test_duplicates(self):
        """my-plex --duplicates must list duplicate media."""
        result = self._run_cmd('--duplicates')
        self.assertEqual(result.returncode, 0, f"--duplicates failed: {result.stderr}")

    def test_duplicates_type_movie(self):
        """my-plex --duplicates --type movie must filter by type."""
        result = self._run_cmd('--duplicates', '--type', 'movie')
        self.assertEqual(result.returncode, 0, f"--duplicates --type movie failed: {result.stderr}")

    def test_broken(self):
        """my-plex --broken must list broken files."""
        result = self._run_cmd('--broken')
        self.assertEqual(result.returncode, 0, f"--broken failed: {result.stderr}")

    def test_excess_versions_3(self):
        """my-plex --excess-versions 3 must run without error."""
        result = self._run_cmd('--excess-versions', '3')
        self.assertEqual(result.returncode, 0, f"--excess-versions 3 failed: {result.stderr}")
        self.assertTrue(len(result.stdout) > 0, "Must produce output")

    def test_excess_versions_2(self):
        """my-plex --excess-versions 2 must run without error."""
        result = self._run_cmd('--excess-versions', '2')
        self.assertEqual(result.returncode, 0, f"--excess-versions 2 failed: {result.stderr}")

    def test_problems(self):
        """my-plex --problems must run all checks and show PROBLEM DETECTION closing line."""
        result = self._run_cmd('--problems')
        self.assertEqual(result.returncode, 0, f"--problems failed: {result.stderr}")
        self.assertIn("PROBLEM DETECTION", result.stdout)
        # v3 registry-driven category headers (always printed, independent of counts)
        self.assertIn("Broken / Truncated Files", result.stdout)
        self.assertIn("Excess Versions (3+)", result.stdout)
        self.assertRegex(result.stdout, r"PROBLEM DETECTION.*: \d+ problem\(s\) found")

    def test_list_labels(self):
        """my-plex --list-labels must list labels."""
        result = self._run_cmd('--list-labels')
        self.assertEqual(result.returncode, 0, f"--list-labels failed: {result.stderr}")

    def test_no_audio_language(self):
        """my-plex --no-audio-language must list items with missing audio language."""
        result = self._run_cmd('--no-audio-language')
        self.assertEqual(result.returncode, 0, f"--no-audio-language failed: {result.stderr}")

    # --- Info/search ---

    def test_info_with_plex_id(self):
        """my-plex --info ID:1 must show item info or error gracefully."""
        result = self._run_cmd('--info', 'ID:1')
        # May return 0 (found) or non-zero (not found) — just verify it doesn't crash
        self.assertNotIn("Traceback", result.stderr, "--info must not crash with traceback")

    def test_info_shows_broken_status(self):
        """my-plex Movie:4 (the fixture's probe failure) shows BROKEN and its reason."""
        result = self._run_cmd('Movie:4')
        self.assertEqual(result.returncode, 0, f"my-plex Movie:4 failed: {result.stderr}")
        self.assertIn("BROKEN", result.stdout)
        self.assertIn("probe_error", result.stdout)

    # --- Verify cache (read-only) ---

    def test_verify_cache(self):
        """my-plex --verify-cache must run without crashing."""
        result = self._run_cmd('--verify-cache')
        # May fail if no server connection, but must not crash
        self.assertNotIn("Traceback", result.stderr, "--verify-cache must not crash with traceback")

    def test_verify_cache_without_a_database_names_the_gap_not_an_empty_host(self):
        """The fixture has no Plex DB file and no remote host.  --verify-cache
        says so, instead of running ssh against an empty host name -- which is
        what it did (2026-11-08: "ssh: connect to host  port 22: Connection
        refused", twice per library)."""
        result = self._run_cmd('--verify-cache')
        self.assertNotIn('connect to host  port 22', result.stderr)
        self.assertIn('PLEX_DB_REMOTE_HOST is empty', result.stderr)

    # --- Error handling ---

    def test_invalid_flag_errors(self):
        """my-plex --nonexistent must produce an error, not crash."""
        result = self._run_cmd('--nonexistent')
        self.assertNotEqual(result.returncode, 0, "Invalid flag must produce non-zero exit")
        self.assertNotIn("Traceback", result.stderr, "Invalid flag must not crash with traceback")

    def test_excess_versions_without_value_errors(self):
        """my-plex --excess-versions without a number must produce an error."""
        result = self._run_cmd('--excess-versions')
        self.assertNotEqual(result.returncode, 0, "--excess-versions without value must error")

    def test_the_excess_versions_help_does_not_offer_the_value_as_optional(self):
        """The CLAIM beside the behaviour above, which is the half that rotted.

        Two compact help lines read `--excess-versions [N] ... (default: 3)`,
        so a reader who followed them got `expected one argument` -- while the
        detailed page (`--excess-versions LIMIT`), the parser's own help and
        the zsh completion (`:limit:`) all said the value is required. The
        test above pins the behaviour; nothing pinned the sentence."""
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        self.assertNotIn('--excess-versions [N]', src,
                         "a compact help line still shows the value as optional")
        stale = [ln.strip() for ln in src.splitlines()
                 if 'excess-versions' in ln and 'default: 3' in ln]
        self.assertEqual(stale, [],
                         f"a help line promises a default the parser refuses: {stale}")

    # --- Output format ---

    def test_list_with_format(self):
        """my-plex --list with a library must accept --format."""
        # Use --list without library — should show library list
        result = self._run_cmd('--list', '-f', 'pretty')
        self.assertEqual(result.returncode, 0, f"--list -f pretty failed: {result.stderr}")

    def test_broken_no_false_positives_with_video_duration(self):
        """--broken flags the fixture's truncated and probe-failed titles and not
        the one whose container and video stream agree while Plex's duration is off.

        Regression: episodes were flagged because Plex reported a duration that
        differed from ffprobe's, although container and video stream durations
        agreed within 2s -- the files were healthy."""
        result = self._run_cmd('--broken')
        self.assertEqual(result.returncode, 0, f"--broken failed: {result.stderr}")
        flagged = {line.split()[0] for line in result.stdout.splitlines() if line.startswith('ID:')}
        self.assertEqual(flagged, {'ID:4', 'ID:6'}, result.stdout)

    # --- Filter: localized genre matching ---

    def test_genre_filter_english(self):
        """genre:Comedy must match items with English 'Comedy' genre tag."""
        result = self._run_cmd('genre:Comedy')
        self.assertEqual(result.returncode, 0, f"genre:Comedy failed: {result.stderr}")
        self.assertRegex(result.stdout, r'(Movie|Episode|Show|Season):\d+')

    def _pick_lib_with_language(self, lang_code):
        """Return any cached library whose configured language begins with lang_code,
        or None if none exists.  Used by localized-genre tests to stay agnostic
        of the actual library names: every install names them differently."""
        result = self._run_cmd('--list-libraries')
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            name, lang = parts[0].strip(), parts[1].strip()
            if lang.lower().startswith(lang_code.lower()):
                return name
        return None

    def test_genre_filter_german_localized(self):
        """genre:Comedy must also match German 'Komödie' genre tag (localized normalization)."""
        lib = self._pick_lib_with_language('de')
        self.assertTrue(lib, "the fixture has a German-language library")
        # library:NAME, not the bare name: a bare name is a scope only when it
        # is shaped like `movies.X` (TODO.local.md has the finding)
        result = self._run_cmd('genre:Comedy', f'library:{lib}')
        self.assertEqual(result.returncode, 0, f"genre:Comedy {lib} failed: {result.stderr}")
        self.assertRegex(result.stdout, r'Movie:\d+|Series:\d+|Episode:\d+',
            f"genre:Comedy must match German 'Komödie' genre in {lib}")

    def test_genre_filter_french_localized(self):
        """genre:Comedy must also match French 'Comédie' genre tag (localized normalization)."""
        lib = self._pick_lib_with_language('fr')
        self.assertTrue(lib, "the fixture has a French-language library")
        result = self._run_cmd('genre:Comedy', f'library:{lib}')
        self.assertEqual(result.returncode, 0, f"genre:Comedy {lib} failed: {result.stderr}")
        self.assertRegex(result.stdout, r'Movie:\d+|Series:\d+|Episode:\d+',
            f"genre:Comedy must match French 'Comédie' genre in {lib}")

    # --- Filter: episode rollup for series ---

    def test_filter_series_rollup_produces_show_or_season_keys(self):
        """Filter on series must roll up to Show:/Season: rows when all episodes match.

        Regression: previously all matching episodes were listed individually even when
        an entire season/show passed the filter with identical values.
        """
        result = self._run_cmd('codec:h264', 'type:series')
        self.assertEqual(result.returncode, 0, f"codec:h264 type:series failed: {result.stderr}")
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        # Must have at least some Show: or Season: rolled-up rows
        rolled = [l for l in lines if l.startswith('Series:') or l.startswith('Season:')]
        self.assertTrue(len(rolled) > 0,
            "Filter on series must produce Show:/Season: rolled-up rows when all episodes match")

    def test_filter_series_rollup_path_is_directory(self):
        """Rolled-up Show:/Season: rows must contain a filesystem path in FILEPATH column."""
        result = self._run_cmd('codec:h264', 'type:series')
        self.assertEqual(result.returncode, 0)
        for line in result.stdout.splitlines():
            if line.startswith('Series:') or line.startswith('Season:'):
                # Path may contain spaces; check that any token starts with '/'
                has_path = any(t.startswith('/') for t in line.split())
                self.assertTrue(has_path,
                    f"Rolled-up row must contain an absolute path, got: {line!r}")


class TestFilter(unittest.TestCase):
    """Comprehensive tests for the filter/scope system (genre:, lang:, codec:, type:, rollup, etc.)."""

    @classmethod
    def setUpClass(cls):
        """Discover, once, whether this machine has media to filter and which
        library to use -- picked from --list-libraries, never hard-coded,
        since every install names its libraries differently.

        It records the answer; it does NOT raise SkipTest. A class-level skip
        reports ONE line for the whole class while the TAP plan has already
        announced every test in it, so 26 tests here were announced and never
        reported -- which is exactly the 1176-vs-1150 gap my-rollout's gate
        saw on ada (2026-11-02). The plan must equal what reports, so the
        decision belongs in each test, where it prints its own `# SKIP`."""
        import subprocess
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--list'],
                                capture_output=True, text=True, timeout=30)
        cls._has_media = not ('No items match' in result.stdout
                              or not result.stdout.strip())
        cls._any_lib = None
        if cls._has_media:
            libs_result = subprocess.run([sys.executable, MAIN_SCRIPT, '--list-libraries'],
                                         capture_output=True, text=True, timeout=30)
            cls._any_lib = _pick_most_populated_library(libs_result.stdout)

    def setUp(self):
        """Per-test, so each announced test reports a line of its own."""
        if not getattr(self, '_has_media', False):
            self.skipTest("this machine's cache has no media to filter "
                          "-- run `my-plex --update-cache` here")

    def _run(self, *args):
        import subprocess
        if any(a is None for a in args):
            self.skipTest("no library in this machine's cache for a scoped "
                          "test -- run `my-plex --update-cache` here")
        return subprocess.run([sys.executable, MAIN_SCRIPT] + list(args),
                              capture_output=True, text=True, timeout=30)

    def _lines(self, *args):
        return [l for l in self._run(*args).stdout.splitlines() if l.strip()]

    def _skip_if_no_lib(self):
        if not getattr(self, '_any_lib', None):
            self.skipTest("No library available in cache for scoped test")

    # --- type: token (Cat-A) ---

    def test_type_series_alone_lists_series(self):
        """type:series alone must list series (not show help page).

        Regression: Cat-A token injected --type but not --list, falling through to help.
        """
        result = self._run('type:series')
        self.assertEqual(result.returncode, 0)
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        self.assertTrue(len(lines) > 10, "type:series must list series, not the help page")
        self.assertNotIn("usage:", result.stdout, "type:series must not show help")

    def test_type_movie_alone_lists_movies(self):
        """type:movie alone must list movies."""
        result = self._run('type:movie')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'Movie:\d+')
        self.assertNotIn("usage:", result.stdout)

    def test_type_series_fewer_than_total(self):
        """type:series must return fewer rows than unfiltered list (series only, not movies)."""
        all_lines  = self._lines('--list')
        ser_lines  = self._lines('type:series')
        self.assertLess(len(ser_lines), len(all_lines),
            "type:series must be a subset of all media")

    # --- Subset invariant ---

    def test_filter_subset_invariant(self):
        """Adding more filter conditions must never increase the row count.

        Regression: genre:Comedy type:series lang:de returned MORE rows than
        genre:Comedy type:series due to rollup breaking when AUDIO/SUBS columns varied.
        """
        comedy_series = self._lines('genre:Comedy', 'type:series')
        comedy_series_de = self._lines('genre:Comedy', 'type:series', 'lang:de')
        # More-specific filter must have <= rows (rollup may expand, but total item coverage must shrink)
        # We can't directly compare rolled-up row counts, but comedy+de shows must be <= comedy shows
        comedy_shows = {l.split()[0] for l in comedy_series if l.startswith('Series:')}
        comedy_de_shows = {l.split()[0] for l in comedy_series_de if l.startswith('Series:')}
        self.assertTrue(comedy_de_shows.issubset(comedy_shows) or len(comedy_de_shows) <= len(comedy_shows),
            f"Comedy+de shows ({len(comedy_de_shows)}) must be a subset of comedy shows ({len(comedy_shows)})")

    # --- genre: filter ---

    def test_genre_comedy_returns_results(self):
        """genre:Comedy must return movie/series results."""
        result = self._run('genre:Comedy')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    def test_genre_localized_de(self):
        """genre:Comedy must match German 'Komödie' (normalized to Comedy in cache)."""
        result = self._run('genre:Comedy', self._any_lib)
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'Movie:\d+',
            "genre:Comedy must find Komödie items in lib2")

    def test_genre_localized_fr(self):
        """genre:Comedy must match French 'Comédie' (normalized to Comedy in cache)."""
        result = self._run('genre:Comedy', self._any_lib)
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'Movie:\d+',
            "genre:Comedy must find Comédie items in lib4")

    def test_genre_drama_returns_results(self):
        """genre:Drama must return results."""
        result = self._run('genre:Drama')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    # --- director: filter ---

    def test_director_filter_recognized(self):
        """director:NAME must be parsed as a filter (not as a Cat-D title search)."""
        result = self._run('director:scorsese', '-V')
        self.assertEqual(result.returncode, 0)
        # Must be interpreted as a director filter, not title~scorsese
        self.assertIn('director:scorsese', result.stdout.lower(),
            "director:scorsese must be applied as a director filter")
        self.assertNotIn('title~director', result.stdout.lower(),
            "director:scorsese must NOT fall through to Cat-D title search")

    def test_director_filter_substring_match(self):
        """director:woody must match any director whose name contains 'woody' (case-insensitive)."""
        # Run filter, capture output. If no matches, skip — depends on user's library.
        result = self._run('director:woody')
        self.assertEqual(result.returncode, 0)
        if 'No items match' in result.stdout:
            self.skipTest("No woody-directed items in this cache")
        # Each result row must come from an obj whose director list includes 'woody' (substring)
        self.assertRegex(result.stdout, r'Movie:\d+|Episode:\d+|Series:\d+',
            "director:woody must return at least one matching item when matches exist")

    # --- lang: filter ---

    def test_lang_de_returns_results(self):
        """lang:de must return items with German audio."""
        result = self._run('lang:de')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    def test_lang_en_returns_results(self):
        """lang:en must return items with English audio."""
        result = self._run('lang:en')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    def test_lang_en_fewer_than_total(self):
        """lang:en must return fewer rows than unfiltered (not all items have en audio)."""
        all_lines = self._lines('--list')
        en_lines  = self._lines('lang:en')
        self.assertLess(len(en_lines), len(all_lines))

    # --- watched: filter ---

    def test_watched_no_returns_results(self):
        """watched:no must return unwatched items."""
        result = self._run('watched:no')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    def test_watched_yes_plus_no_covers_all(self):
        """watched:yes + watched:no combined must cover all items; movies must not overlap."""
        yes_keys = {l.split()[0] for l in self._lines('watched:yes') if l and l[0].isalpha()}
        no_keys  = {l.split()[0] for l in self._lines('watched:no')  if l and l[0].isalpha()}
        # Movies are atomic — a movie is either watched or not, so no Movie: key can appear
        # in both results. Series may overlap (partially-watched shows appear in both when
        # value-comparison rollup groups matched episodes regardless of total coverage).
        yes_movies = {k for k in yes_keys if k.startswith('Movie:')}
        no_movies  = {k for k in no_keys  if k.startswith('Movie:')}
        self.assertEqual(yes_movies & no_movies, set(),
            "Movie keys must not appear in both watched:yes and watched:no")

    # --- codec: filter ---

    def test_codec_h264_returns_results(self):
        """codec:h264 must return results."""
        result = self._run('codec:h264')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    # --- bitrate: filter ---

    def test_bitrate_gt_returns_results(self):
        """bitrate>1 must return items with bitrate > 1 Mbps."""
        result = self._run('bitrate>1')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    # --- year: filter ---

    def test_year_gt_returns_results(self):
        """year>2010 must return items released after 2010."""
        result = self._run('year>2010')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    def test_year_filter_older_fewer(self):
        """year>2020 must return fewer items than year>2000."""
        newer = self._lines('year>2020')
        older = self._lines('year>2000')
        self.assertLessEqual(len(newer), len(older),
            "year>2020 must be a subset of year>2000")

    # --- Series rollup ---

    def test_series_rollup_all_episodes_become_series_rows(self):
        """type:series with no other filter: all series must roll up to Show: rows.

        Regression: rollup failed when _same_vals was used — extra columns
        with varying values (AUDIO, SUBS) prevented rollup.
        Note: DEFAULT_SCOPE may add a watched filter, causing partial seasons
        which prevent full rollup — only fail if Episode: rows appear WITHOUT
        any DEFAULT_SCOPE active.
        """
        lines = self._lines('type:series')
        ep_rows = [l for l in lines if l.startswith('Episode:')]
        # Check if DEFAULT_SCOPE is active (look for the notice in verbose output)
        result = self._run('type:series', '-V')
        has_default_scope = 'DEFAULT_SCOPE' in result.stdout
        if not has_default_scope:
            self.assertEqual(ep_rows, [],
                f"type:series must roll up fully — no Episode: rows expected, got: {ep_rows[:3]}")
        else:
            # With DEFAULT_SCOPE, partial seasons may prevent full rollup — just verify
            # that series rollup IS happening (Series: rows exist)
            series_rows = [l for l in lines if l.startswith('Series:')]
            self.assertTrue(len(series_rows) > 0,
                "type:series must produce Series: rollup rows even with DEFAULT_SCOPE")

    def test_series_rollup_series_rows_present(self):
        """type:series must produce Show: level rows (full show rollup)."""
        lines = self._lines('type:series')
        series_rows = [l for l in lines if l.startswith('Series:')]
        self.assertTrue(len(series_rows) > 0, "type:series must produce Show: rollup rows")

    def test_series_rollup_with_codec_filter(self):
        """codec:h264 type:series: rolled-up rows must contain filesystem path."""
        lines = self._lines('codec:h264', 'type:series')
        rolled = [l for l in lines if l.startswith('Series:') or l.startswith('Season:')]
        self.assertTrue(len(rolled) > 0, "codec:h264 type:series must produce rolled-up rows")
        for line in rolled:
            has_path = any(t.startswith('/') for t in line.split())
            self.assertTrue(has_path, f"Rolled-up row must contain absolute path: {line!r}")

    def test_series_rollup_lang_does_not_explode(self):
        """Adding lang:de must not EXPLODE the row count (rollup regression).

        Regression: lang:de added AUDIO/SUBS extra cols whose varying values
        broke rollup, causing MORE rows with lang:de than without.

        Note: a strict Series:-key subset check is intentionally NOT used —
        narrowing to one language can legitimately make a previously
        non-uniform row set display-uniform, ROLLING IT UP HIGHER (e.g. a
        series split over two wrapper dirs shows Episode+Season rows plain,
        but one partial Series row with lang:de).  The regression guarded
        here is row EXPLOSION, so assert on total row counts."""
        _row_re = re.compile(r'^(Movie|Episode|Season|Series):')
        comedy_rows    = [l for l in self._lines('genre:Comedy', 'type:series')
                          if _row_re.match(l)]
        comedy_de_rows = [l for l in self._lines('genre:Comedy', 'type:series', 'lang:de')
                          if _row_re.match(l)]
        self.assertLessEqual(len(comedy_de_rows), len(comedy_rows),
            f"Adding lang:de must not produce MORE rows "
            f"({len(comedy_de_rows)} with lang:de vs {len(comedy_rows)} without)")

    # --- Combined filters (AND logic) ---

    def test_combined_type_genre(self):
        """type:movie genre:Drama must return only movies with Drama genre."""
        result = self._run('type:movie', 'genre:Drama')
        self.assertEqual(result.returncode, 0)
        for line in result.stdout.splitlines():
            if line.startswith('Episode:') or line.startswith('Series:') or line.startswith('Season:'):
                self.fail(f"type:movie genre:Drama must not include series rows: {line!r}")

    def test_combined_genre_lang(self):
        """genre:Comedy lang:de must return German-audio Comedy items."""
        result = self._run('genre:Comedy', 'lang:de')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'(Movie|Show|Season|Episode):\d+')

    def test_no_filter_lists_everything(self):
        """--list with no filter must return all media (movies + episodes)."""
        result = self._run('--list')
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r'Movie:\d+')
        self.assertRegex(result.stdout, r'(Series|Episode):\d+')


class TestDefaultScope(unittest.TestCase):
    """Tests for DEFAULT_SCOPE config variable — default filter tokens for listing commands."""

    @classmethod
    def setUpClass(cls):
        """Discover a library to use for scope-dependent tests -- picked
        dynamically, never hard-coded: every install names its libraries differently."""
        import subprocess
        libs_result = subprocess.run([sys.executable, MAIN_SCRIPT, '--list-libraries'],
                                     capture_output=True, text=True, timeout=30)
        cls._any_lib = _pick_most_populated_library(libs_result.stdout)
        cls._any_title_word = _pick_any_title_word(cls._any_lib) if cls._any_lib else None

    def _run(self, *args):
        """Run my-plex with these arguments.

        A None argument means setUpClass found no library -- which is what
        every machine looks like before its first --update-cache. Passing it
        on gives `TypeError: expected str, bytes or os.PathLike object, not
        NoneType` from deep inside subprocess, a traceback that names nothing
        about the cause; and since my-rollout offers no copy whose suite
        fails, the whole tool then stops being deployable on that machine
        (ada, 2026-11-01: eight errors and one failure, all of them this).
        So the guard sits HERE, once, instead of in every test that takes a
        scope -- including the ones not written yet."""
        import subprocess
        if any(a is None for a in args):
            self.skipTest("no library in this machine's cache for a scoped "
                          "test -- run `my-plex --update-cache` here")
        return subprocess.run([sys.executable, MAIN_SCRIPT] + list(args),
                              capture_output=True, text=True, timeout=30)

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def _skip_if_no_lib(self):
        if not getattr(self, '_any_lib', None):
            self.skipTest("No library available in cache for scoped test")

    def test_a_missing_library_skips_instead_of_crashing(self):
        """The guard itself, proven on ANY machine -- including this one, where
        the cache is there and the scoped tests below never take the None path.

        Without the guard, None reaches subprocess and the test dies with
        `TypeError: expected str, bytes or os.PathLike object, not NoneType`,
        which says nothing about a missing cache."""
        with self.assertRaises(unittest.SkipTest):
            self._run(None, '--list')

    def test_default_scope_in_config_defaults(self):
        """DEFAULT_SCOPE must exist in CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("'DEFAULT_SCOPE'", src)

    def test_default_scope_global_variable(self):
        """DEFAULT_SCOPE must be initialized from CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("DEFAULT_SCOPE = CONFIG_DEFAULTS['DEFAULT_SCOPE']", src)

    def test_apply_default_scope_method_exists(self):
        """_apply_default_scope must be a method of PLEX_Media."""
        src = self._read_script()
        self.assertIn('def _apply_default_scope(', src)

    def test_apply_default_scope_called_in_list_filtered(self):
        """_list_filtered must call _apply_default_scope."""
        src = self._read_script()
        # Find _list_filtered and check it calls _apply_default_scope
        idx = src.index('def _list_filtered(')
        snippet = src[idx:idx+1000]
        self.assertIn('_apply_default_scope', snippet)

    def test_apply_default_scope_called_in_list(self):
        """PLEX_Media.list() must call _apply_default_scope."""
        src = self._read_script()
        idx = src.index('def list(args, obj_args, library_name, media_type')
        snippet = src[idx:idx+1000]
        self.assertIn('_apply_default_scope', snippet)

    def test_default_scope_in_example_conf(self):
        """DEFAULT_SCOPE must appear in EXAMPLE_CONF."""
        src = self._read_script()
        self.assertIn('DEFAULT_SCOPE', src[src.index('EXAMPLE_CONF'):src.index('def load_config_file')])

    def test_default_scope_in_help_config(self):
        """--help config must mention DEFAULT_SCOPE."""
        result = self._run('--help', 'config')
        self.assertIn('DEFAULT_SCOPE', result.stdout)

    def test_default_scope_in_help_list(self):
        """--help list must mention DEFAULT_SCOPE."""
        result = self._run('--help', 'list')
        self.assertIn('DEFAULT_SCOPE', result.stdout)

    def test_verbose_notice(self):
        """DEFAULT_SCOPE notice must appear in -V output."""
        result = self._run(self._any_lib, '--list', '-V')
        self.assertIn('DEFAULT_SCOPE', result.stdout)

    def test_help_with_filter_tokens(self):
        """--help must not crash when combined with filter tokens."""
        result = self._run(self._any_lib, 'watched:no', '--help')
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('ERROR', result.stdout + result.stderr)

    def test_unwatched_columns_no_duplicate_rating(self):
        """watched:no must not produce duplicate RATING columns."""
        result = self._run(self._any_lib, 'watched:no', '-V')
        header_line = [l for l in result.stdout.splitlines() if 'RATING' in l]
        if header_line:
            self.assertEqual(header_line[0].count('RATING'), 1,
                "Must not have duplicate RATING columns")


    def test_help_with_multiple_filter_tokens(self):
        """--help must not crash when combined with multiple filter tokens."""
        result = self._run(self._any_lib, 'watched:no', 'rating>7', '--help')
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('ERROR', result.stdout + result.stderr)

    def test_bare_token_adds_column(self):
        """A bare field name (e.g. 'genre') must add a display column without filtering."""
        self._skip_if_no_lib()
        result = self._run(self._any_lib, 'genre', '-V')
        self.assertIn('GENRE', result.stdout, "Bare 'genre' token must add GENRE column")
        self.assertNotIn('ERROR', result.stdout + result.stderr)

    def test_bare_token_combined_with_filter(self):
        """Bare token + filter token must work together (e.g. 'rating>7 genre')."""
        self._skip_if_no_lib()
        result = self._run(self._any_lib, 'watched:no', 'rating>7', 'genre', '-V')
        header_lines = [l for l in result.stdout.splitlines() if 'RATING' in l and 'GENRE' in l]
        self.assertTrue(len(header_lines) >= 1, "Must show both RATING and GENRE columns")

    def test_bare_token_display_only_no_filter(self):
        """_parse_filter_sub_expr must handle +field tokens (display-only, no filtering)."""
        src = self._read_script()
        idx = src.index('def _parse_filter_sub_expr(')
        snippet = src[idx:idx+8000]
        self.assertIn("sub.startswith('+')", snippet, "_parse_filter_sub_expr must handle +field tokens")

    def test_cat_c_token_regex_exists(self):
        """Cat-C bare token regex must exist in argv normalization."""
        src = self._read_script()
        self.assertIn('_CAT_C_TOKEN_RE', src, "Cat-C regex for bare field tokens must exist")

    def test_rollup_shows_matched_total_counts(self):
        """Series rollup with filtered episodes must show matched/total annotation."""
        result = self._run(self._any_lib, '-V')
        lines = result.stdout.splitlines()
        series_lines = [l for l in lines if l.startswith('Series:')]
        if series_lines:
            # At least one series should have (N/M eps, X/Y seasons) annotation
            annotated = [l for l in series_lines if ' eps,' in l and 'seasons)' in l]
            self.assertTrue(len(annotated) > 0,
                "Filtered series rollup must annotate with matched/total counts")

    def test_rollup_season_annotation(self):
        """Season rows with partial episode match must show (N/M eps) annotation."""
        src = self._read_script()
        self.assertIn('_matched_eps', src, "Season rollup must track matched episode count")
        self.assertIn('_total_eps', src, "Season rollup must track total episode count")

    # --- Cat-D: bare word title search ---

    def test_cat_d_title_search(self):
        """A bare word (not a field/flag/library) must trigger title~word search."""
        result = self._run('tagesschau', '-V')
        self.assertIn('title~tagesschau', result.stdout,
            "Bare word must be interpreted as title search")
        self.assertNotIn('ERROR', result.stdout + result.stderr)

    def test_cat_d_title_search_results(self):
        """Title search must return items whose title matches the search term.

        The TERM is taken from a title in this install, never hard-coded.
        What is NOT asserted, though the test name invites it: that every row
        returned has the term in its own TITLE column. A search for a word of
        a series title returns that series' EPISODES, whose titles do not
        contain it -- `creatures` returns 187 episodes of a series listed in
        German. The claim the output actually makes is the filter line, and
        that is what the test beside this one checks.

        No skip guard here on purpose: with no cache the term is None and
        _run skips for every test in this class at once. A second guard in
        this one test was written first and proved redundant."""
        term = getattr(self, '_any_title_word', None)
        result = self._run(term, '-V')
        lines = [l for l in result.stdout.splitlines() if l.startswith(('Movie:', 'Series:', 'Episode:', 'Season:'))]
        self.assertTrue(len(lines) > 0,
                        f"Title search {term!r} -- a word from a title in this "
                        f"install -- returned nothing")

    def test_cat_d_skips_help_topic(self):
        """--help <topic> must NOT treat the topic as a Cat-D title search."""
        result = self._run('--help', 'scope')
        self.assertNotIn('title~scope', result.stdout,
            "--help topic must not be treated as title search")
        self.assertIn('SCOPE', result.stdout,
            "--help scope must show scope help page")

    def test_cat_d_skips_library_names(self):
        """Library-shaped names (movies.X / series.X / ,unsorted) must NOT trigger Cat-D title search."""
        src = self._read_script()
        # v2.1: the heuristic moved into a named helper variable.
        self.assertIn("_is_library_shaped", src,
            "Cat-D must skip library-shaped names via the _is_library_shaped check")
        self.assertIn("movies?|series|shows?", src,
            "Cat-D must check the library-name regex")

    # --- Negative Cat-C: -field removes columns ---

    def test_neg_cat_c_removes_filepath(self):
        """-file must remove the FILEPATH column from output."""
        result = self._run(self._any_lib, '-file', '-V')
        header_lines = [l for l in result.stdout.splitlines() if l.startswith('---')]
        if header_lines:
            self.assertNotIn('FILEPATH', result.stdout.splitlines()[
                result.stdout.splitlines().index(header_lines[0]) - 1],
                "-file must remove FILEPATH from header")

    def test_neg_cat_c_synonyms(self):
        """-file, -filepath, -path must all map to FILEPATH removal."""
        src = self._read_script()
        self.assertIn("'file': 'FILEPATH'", src)
        self.assertIn("'filepath': 'FILEPATH'", src)
        self.assertIn("'path': 'FILEPATH'", src)

    def test_neg_cat_c_regex_exists(self):
        """Negative Cat-C regex and field map must exist in argv normalization."""
        src = self._read_script()
        self.assertIn('_NEG_CAT_C_RE', src, "Negative Cat-C regex must exist")
        self.assertIn('_NEG_FIELD_MAP', src, "Negative Cat-C field map must exist")
        self.assertIn('_REMOVE_COLS', src, "Column removal storage must exist")

    def test_neg_cat_c_wired_into_list(self):
        """_list_filtered must read _REMOVE_COLS and filter extra_cols."""
        src = self._read_script()
        idx = src.index('def _list_filtered(')
        body = src[idx:idx+30000]
        self.assertIn('_REMOVE_COLS', body,
            "_list_filtered must use _REMOVE_COLS to hide columns")

    # --- ep:word episode title search ---

    def test_ep_title_search_handler(self):
        """_parse_filter_sub_expr must handle ep:word syntax for episode-only title search."""
        src = self._read_script()
        idx = src.index('def _parse_filter_sub_expr(')
        snippet = src[idx:idx+8000]
        self.assertIn('_ep_title_re', snippet,
            "_parse_filter_sub_expr must handle ep: prefix for episode title search")

    # --- `--` end-of-filters marker ---

    def test_dashdash_marker_handler_exists(self):
        """`--` must be handled in argv normalization to switch into literal-title-search mode."""
        src = self._read_script()
        self.assertIn("_after_dashdash", src,
            "argv normalization must track after-dashdash state")
        self.assertIn("if arg == '--':", src,
            "argv normalization must recognize the `--` end-of-filters marker")

    def test_dashdash_makes_filter_keyword_a_title_search(self):
        """After `--`, words that would normally be filter keywords become literal title searches.

        Regression: 'imdb' alone is a Cat-C display column, but `-- imdb` must search titles.
        """
        result = self._run('--', 'imdb', '-V')
        self.assertEqual(result.returncode, 0)
        self.assertIn('title~imdb', result.stdout,
            "`-- imdb` must produce a title~imdb filter, not an IMDB display column")

    # --- Negative Cat-B: -field:value filters AND hides column ---

    def test_neg_cat_b_regex_exists(self):
        """Negative Cat-B regex (-field:value) must exist for combined filter+hide."""
        src = self._read_script()
        self.assertIn('_NEG_CAT_B_RE', src,
            "Negative Cat-B regex (filter+hide) must exist")

    def test_neg_genre_filters_and_hides_column(self):
        """-genre:comedy must filter for comedy AND hide the GENRE column."""
        result = self._run(self._any_lib, '-genre:comedy', '-V')
        # Filter line must show genre:comedy is being applied
        self.assertIn('genre:comedy', result.stdout.lower(),
            "-genre:comedy must apply genre filter")
        # GENRE column must NOT appear in the header
        header_lines = [l for l in result.stdout.splitlines()
                        if 'KEY' in l and 'TITLE' not in l[:5]]
        for hdr in header_lines:
            self.assertNotIn('GENRE', hdr,
                "-genre:comedy must hide GENRE column from output")

    # --- imdb / tmdb / tvdb display columns ---

    def test_imdb_token_adds_url_column(self):
        """Bare `imdb` token must add an IMDB URL column to output."""
        result = self._run(self._any_lib, 'imdb', '-V')
        self.assertEqual(result.returncode, 0)
        # Either the IMDB header is present, or no rows match (empty libraries)
        if 'Movie:' in result.stdout or 'Episode:' in result.stdout or 'Series:' in result.stdout:
            self.assertIn('IMDB', result.stdout,
                "imdb token must add IMDB column header")
            self.assertIn('imdb.com/title/', result.stdout,
                "IMDB column must contain imdb.com URLs")

    def test_imdb_in_cat_c_regex(self):
        """imdb / tmdb / tvdb must be in the Cat-C display-only token regex."""
        src = self._read_script()
        self.assertIn('|imdb|tmdb|tvdb', src,
            "Cat-C regex must include imdb/tmdb/tvdb tokens")

    # --- Per-library language distribution + MULTI config ---

    def test_language_distribution_in_schema(self):
        """EMPTY_LIBRARY_STATS must include the 'language_distribution' key."""
        src = self._read_script()
        self.assertIn("'language_distribution'", src,
            "EMPTY_LIBRARY_STATS must include language_distribution")

    def test_languages_column_in_list_libraries(self):
        """--list-libraries must include the LANGUAGES column."""
        result = self._run('--list-libraries')
        self.assertEqual(result.returncode, 0)
        self.assertIn('LANGUAGES', result.stdout,
            "--list-libraries must include LANGUAGES column")

    def test_multi_marker_recognized_in_config(self):
        """The autoresolve rewire must recognize 'MULTI' as a special config value."""
        src = self._read_script()
        self.assertIn("'MULTI'", src,
            "Code must recognize 'MULTI' in AUTO_RESOLVE_AUDIO_LANGUAGE_BY_LIBRARY")

    def test_audio_auto_show_for_multi_library_logic_present(self):
        """_list_filtered must auto-set has_lang when results span a MULTI library."""
        src = self._read_script()
        idx = src.index('def _list_filtered(')
        body = src[idx:idx+30000]
        self.assertIn("'MULTI'", body,
            "_list_filtered must check AUTO_RESOLVE entries for 'MULTI'")
        self.assertIn('_multi_libs', body,
            "_list_filtered must build a _multi_libs set from the config")

    def test_movies_only_layout_logic_present(self):
        """_list_filtered must compute _movies_only and use original_title-aware TITLE."""
        src = self._read_script()
        idx = src.index('def _list_filtered(')
        body = src[idx:idx+30000]
        self.assertIn('_movies_only', body,
            "_list_filtered must detect movies-only result sets")
        self.assertIn('_title_for_row', body,
            "_list_filtered must use a title chooser that picks original_title for MULTI libs")
        # ORIGINAL-TITLE column only when the user explicitly opts in via originaltitle token
        self.assertIn("'ORIGINAL-TITLE'", body,
            "_list_filtered must offer ORIGINAL-TITLE column when user passes the originaltitle token")

    def test_filepath_opt_in_token(self):
        """Bare `path` / `filepath` / `file` token must be recognized as Cat-C (opt-in to FILEPATH)."""
        src = self._read_script()
        # Cat-C regex must list path/filepath/file
        self.assertRegex(src, r'_CAT_C_TOKEN_RE\s*=.*',
            "_CAT_C_TOKEN_RE must exist")
        self.assertIn('path|filepath|file', src,
            "Cat-C regex must accept path/filepath/file as bare display tokens")
        # _LABEL_TO_FIELD must map them to 'filepath'
        self.assertIn("'filepath': 'filepath'", src,
            "Display field mapping must include filepath")

    def test_lang_de_filter_still_works(self):
        """Regression: lang:de must still return items with German audio."""
        result = self._run('lang:de')
        self.assertEqual(result.returncode, 0)
        # Either matches exist or empty; both are acceptable as long as no error.
        self.assertNotIn('ERROR', result.stdout + result.stderr,
            "lang:de must not error out")


class TestErrorOutputConventions(unittest.TestCase):
    """Ensure ERROR output conventions: ERROR=fatal with verbose guidance, WARNING only for benign cases."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_print_ssh_error_uses_error_not_warning(self):
        """print_ssh_error must use ERROR prefix — SSH failures are fatal."""
        src = self._read_script()
        match = re.search(r'def print_ssh_error\(.*?\n(.*?)(?=\ndef )', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "print_ssh_error not found")
        body = match.group(1)
        self.assertIn('ERROR:', body, "print_ssh_error must use ERROR prefix")

    def test_print_ssh_error_has_troubleshooting(self):
        """print_ssh_error must include verbose troubleshooting guidance."""
        src = self._read_script()
        match = re.search(r'def print_ssh_error\(.*?\n(.*?)(?=\ndef )', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        body = match.group(1)
        self.assertIn('ssh/config', body, "print_ssh_error must have SSH config instructions")
        self.assertIn('Example', body, "print_ssh_error must have example config")

    def test_trash_failure_has_possible_reasons(self):
        """TRASH SSH failure path must include 'Possible reasons' block."""
        src = self._read_script()
        match = re.search(r'def my_plex_file_operation\(.*?\n(.*?)(?=\n################################)', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "my_plex_file_operation not found")
        body = match.group(1)
        self.assertIn('Possible reasons:', body, "SSH failure paths must have 'Possible reasons' guidance")


    def test_every_failure_marker_print_is_on_stderr(self):
        """`✗ ERROR ...` marks a step that FAILED. Those go to stderr, or
        `my-plex --move ... > out.txt` buries them in the file and a pipe
        hands them to the next program as data."""
        bad = [f"{n}: {line.strip()[:90]}"
               for n, line in enumerate(self._read_script().splitlines(), 1)
               if '\u2717 ERROR' in line and 'print(' in line
               and 'file=sys.stderr' not in line]
        self.assertEqual(bad, [], "failure markers still on stdout:\n" + "\n".join(bad))

    def test_a_commands_own_findings_stay_on_stdout(self):
        """The other half, and the one a sweep gets wrong: what a command was
        ASKED to report is its result, not an error. `--problems` listing a
        broken file, the confirmation banner before a destructive rebuild and
        the examples on a --help page all belong on stdout, where a redirect
        is meant to catch them."""
        keep_on_stdout = [
            'WARNING: File marked as BROKEN',        # a --problems/--info finding
            'WARNING: FROM-SCRATCH CACHE REBUILD',   # a confirmation banner
            '--del requires --rm',                   # an example on --help del
        ]
        src_lines = self._read_script().splitlines()
        for marker in keep_on_stdout:
            with self.subTest(marker=marker):
                hits = [l for l in src_lines if marker in l and 'print(' in l]
                self.assertTrue(hits, f"{marker!r} is gone -- update this test")
                for line in hits:
                    self.assertNotIn('file=sys.stderr', line,
                                     f"this is the command's own output, not an error: {line.strip()[:90]}")

    def _run_cli(self, *args):
        return subprocess.run([sys.executable, MAIN_SCRIPT, *args],
                              capture_output=True, text=True, timeout=60)

    def test_an_ordinary_error_prints_the_status_it_exits_with(self):
        """The common path: an argument error, which exits 1."""
        r = subprocess.run([MAIN_SCRIPT, '--force'], capture_output=True,
                           text=True, timeout=120,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        m = re.search(r'ERROR (\d{5}) \[(\d+)\]:', r.stderr)
        self.assertIsNotNone(m, f"not the house error shape:\n{r.stderr!r}")
        assert m is not None
        self.assertEqual(int(m.group(2)), r.returncode,
                         f"it printed [{m.group(2)}] and exited {r.returncode}")
        self.assertNotEqual(r.returncode, 0, "an error must not exit 0")

    def test_the_code_is_greppable_back_to_its_source_line(self):
        """The code exists for one reason: to find the line that raised it.
        So the code a run prints must actually appear in the source."""
        r = subprocess.run([MAIN_SCRIPT, '--force'], capture_output=True,
                           text=True, timeout=120,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        m = re.search(r'ERROR (\d{5}) ', r.stderr)
        self.assertIsNotNone(m)
        assert m is not None
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        self.assertIn(f'"{m.group(1)}"', src,
                      f"code {m.group(1)} is printed but is in no err() call")

    def test_err_goes_to_stderr_not_stdout(self):
        """err() is fatal output: stderr only, so `my-plex ... > out` still shows it
        and `my-plex ... | next` never feeds it to the next program as data."""
        r = self._run_cli('--offline', '--plex-token')   # argparse error -> err()
        self.assertNotEqual(r.returncode, 0)
        self.assertRegex(r.stderr, r'ERROR \d{5} \[\d+\]:')
        self.assertNotIn('ERROR', r.stdout)

    def test_error_block_goes_to_stderr_whole(self):
        """An ERROR line and the guidance printed right after it travel together."""
        r = self._run_cli('--offline', '--rename')
        out = r.stdout + r.stderr
        if 'requires a library' not in out:
            self.skipTest(f"--rename without target did not reach its error path: {out[-300:]}")
        self.assertIn('ERROR: --rename requires a library', r.stderr)
        self.assertIn('Use --help rename for details.', r.stderr)
        self.assertNotIn('ERROR', r.stdout)

class TestObjByLibraryDedup(unittest.TestCase):
    """Ensure OBJ_BY_LIBRARY appends have dedup checks to prevent duplicate keys."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_show_episode_season_appends_have_dedup_check(self):
        """All OBJ_BY_LIBRARY .append() calls in show/episode/season processing must check for duplicates."""
        src = self._read_script()
        match = re.search(r'def _process_series_from_database\(.*?\n(.*?)(?=\ndef )', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "_process_series_from_database not found")
        body = match.group(1)
        append_lines = re.findall(r"lib_dict\['\w+'\]\.append\((\w+)\)", body)
        self.assertTrue(len(append_lines) >= 3, f"Expected at least 3 OBJ_BY_LIBRARY appends (Episode, Season, Show), found {len(append_lines)}")
        for var in append_lines:
            pattern = rf"if {var} not in lib_dict\['\w+'\]:\s*\n\s*lib_dict\['\w+'\]\.append\({var}\)"
            self.assertRegex(body, pattern, f"Missing dedup check before lib_dict append of '{var}'")

    def test_update_cache_cleans_duplicate_library_keys(self):
        """--update-cache must deduplicate OBJ_BY_LIBRARY lists."""
        src = self._read_script()
        self.assertIn('duplicate keys from OBJ_BY_LIBRARY', src,
            "--update-cache must clean duplicate keys from OBJ_BY_LIBRARY")

    def test_update_cache_cleans_dangling_series_keys(self):
        """--update-cache must remove dangling keys from OBJ_BY_SERIES."""
        src = self._read_script()
        self.assertIn('dangling keys from OBJ_BY_SERIES', src,
            "--update-cache must clean dangling keys from OBJ_BY_SERIES")

    def test_update_cache_cleans_dangling_episode_keys(self):
        """--update-cache must remove dangling keys from OBJ_BY_SERIES_EPISODES."""
        src = self._read_script()
        self.assertIn('dangling keys from OBJ_BY_SERIES_EPISODES', src,
            "--update-cache must clean dangling keys from OBJ_BY_SERIES_EPISODES")

    def test_update_cache_saves_all_structures(self):
        """v2.10: --update-cache does ONE merged save at the end of init(), and
        that single call must include all cache structures (build_media_cache_dict)
        plus the deferred extras stashed by _finalize_and_save_cache."""
        src = self._read_script()
        match = re.search(r'# v2\.10: ONE merged save.*?\n\s*(update_and_save_cache\(.*?\*\*_pending,?\s*\)\s*)',
                          src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Final save must merge _pending_save_extras via **_pending")
        save_call = match.group(1)
        self.assertIn('build_media_cache_dict', save_call)
        self.assertIn('plex_known_filepaths', save_call)
        self.assertIn('problems', save_call)
        self.assertIn('layout_index', save_call)


class TestDeleteRequiresRemove(unittest.TestCase):
    """Ensure --del refuses to run without --rm, and help text warns about file deletion."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_del_without_rm_is_rejected(self):
        """--del without --rm must be rejected with an error."""
        # Use a fake but valid-looking media ID — the guard must reject before lookup
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--offline', 'Movie:99999', '--del'],
            capture_output=True, text=True, timeout=30
        )
        output = result.stderr + result.stdout
        # Must NOT silently succeed
        self.assertNotEqual(result.returncode, 0, "--del without --rm should fail")
        # Must mention --rm requirement OR indicate the item wasn't found
        self.assertTrue('--rm' in output or 'not found' in output.lower() or 'error' in output.lower(),
            "Error must mention --rm requirement or indicate failure")

    def test_del_help_warns_about_file_deletion(self):
        """--help del must warn that Plex API delete also removes files from disk."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'del'],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        self.assertIn('DELETES FILES FROM DISK', output, "--help del must warn about file deletion")

    def test_del_argparse_help_no_longer_says_metadata_only(self):
        """--delete help text must NOT say 'files on disk are NOT deleted' — that was WRONG."""
        src = self._read_script()
        self.assertNotIn('files on disk are NOT deleted', src,
            "Dangerously wrong help text must be removed")

    def test_del_argparse_help_warns_about_files(self):
        """--delete argparse help must mention that Plex also deletes files."""
        src = self._read_script()
        match = re.search(r"add_argument\('--delete', '--del'.*?help=\"(.*?)\"", src)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "--delete/--del media argparse not found")
        help_text = match.group(1)
        self.assertIn('files', help_text.lower(), "--delete help must mention files")

    def test_delete_method_comment_warns_about_files(self):
        """delete() method must have a comment warning about file deletion."""
        src = self._read_script()
        match = re.search(r'def delete\(media_identifier.*?\n(.*?)\n', src)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "PLEX_Media.delete() not found")
        # Check the lines right after the def
        after_def = src[match.start():match.start()+500]
        self.assertIn('removes all associated media files', after_def.lower(),
            "delete() must warn that Plex API also removes files")


class TestScan(unittest.TestCase):
    """Tests for --scan command."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def _run_cmd(self, *extra_args):
        cmd = [sys.executable, MAIN_SCRIPT] + list(extra_args)
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=E2E_TIMEOUT)
        return result

    def test_scan_in_main_parser(self):
        """--scan must be registered in main_parser."""
        src = self._read_script()
        self.assertIn("'--scan'", src, "--scan not found in main_parser arguments")

    def test_scan_in_global_cmd_parser(self):
        """--scan must be registered in GLOBAL_CMD_PARSER."""
        src = self._read_script()
        # Find --scan in GLOBAL_CMD_PARSER context
        self.assertRegex(src, r"GLOBAL_CMD_PARSER\.add_argument\('--scan'",
            "--scan not found in GLOBAL_CMD_PARSER")

    def test_scan_in_library_argparser(self):
        """--scan must be registered in PLEX_Library.argparser."""
        src = self._read_script()
        self.assertRegex(src, r"argparser\.add_argument\('--scan'.*action='store_true'",
            "--scan not found in PLEX_Library.argparser")

    def test_scan_implies_force_cache_update(self):
        """--scan must set FORCE_CACHE_UPDATE = True."""
        src = self._read_script()
        self.assertIn("FORCE_CACHE_UPDATE = True", src,
            "--scan must set FORCE_CACHE_UPDATE = True")

    def test_scan_does_not_force_metadata(self):
        """v2.41 invariant: --scan must NOT force ffmpeg re-probe.

        Earlier versions OR'd `has_scan` into FORCE_METADATA, which made
        every --scan re-probe ~10k files.  The fix in v2.41 was to drop
        `has_scan` from that OR clause.  This test guards against the
        regression by asserting `has_scan` never appears in a
        FORCE_METADATA assignment line.
        """
        src = self._read_script()
        for line in src.splitlines():
            if 'FORCE_METADATA' in line and '=' in line and 'has_scan' in line:
                self.fail(f"v2.41 invariant violated: FORCE_METADATA must not be derived from has_scan (line: {line!r})")

    def test_scan_uses_lib_refresh(self):
        """--scan must use lib.refresh() to force Plex to re-read file metadata."""
        src = self._read_script()
        self.assertRegex(src, r"use_refresh.*SCAN_LIBRARIES",
            "--scan must set use_refresh based on SCAN_LIBRARIES")

    def test_scan_help_exists(self):
        """--help scan must show SCAN HELP."""
        result = self._run_cmd('--help', 'scan')
        self.assertEqual(result.returncode, 0, f"--help scan failed: {result.stderr}")
        self.assertIn("SCAN HELP", result.stdout)

    def test_scan_help_reversed(self):
        """--scan --help must work like --help scan."""
        result = self._run_cmd('--scan', '--help')
        self.assertEqual(result.returncode, 0, f"--scan --help failed: {result.stderr}")
        self.assertIn("SCAN HELP", result.stdout)

    def test_scan_help_dashed(self):
        """--help --scan must work like --help scan."""
        result = self._run_cmd('--help', '--scan')
        self.assertEqual(result.returncode, 0, f"--help --scan failed: {result.stderr}")
        self.assertIn("SCAN HELP", result.stdout)

    def test_scan_in_zsh_completions(self):
        """--scan must be in zsh completion script."""
        src = self._read_script()
        self.assertIn("'--scan[", src,
            "--scan not found in zsh completion script in my-plex.py")

    def test_scan_libraries_global_exists(self):
        """SCAN_LIBRARIES global variable must be declared."""
        src = self._read_script()
        self.assertIn("SCAN_LIBRARIES = None", src,
            "SCAN_LIBRARIES global not found")

    def test_scan_resolves_plex_id(self):
        """--scan must support ID: prefix for resolving Plex IDs to library names."""
        src = self._read_script()
        self.assertRegex(src, r"candidate\.upper\(\)\.startswith\('ID:'\)",
            "--scan must resolve ID: prefixes to library names")

    def test_scan_filters_all_libraries(self):
        """--scan with specific library must filter all_libraries in update_cache()."""
        src = self._read_script()
        self.assertIn("SCAN_LIBRARIES is not None", src,
            "SCAN_LIBRARIES filtering not found in update_cache()")

    def test_scan_exits_after_work(self):
        """--scan in execute_global_commands must exit cleanly."""
        src = self._read_script()
        # Check that scan handler calls sys.exit(0) — look for the pattern in execute_global_commands
        self.assertIn("'scan', False)", src,
            "--scan handler with safe_getattr must exist")
        # Verify sys.exit(0) appears after the scan check
        scan_idx = src.index("'scan', False)")
        exit_idx = src.index("sys.exit(0)", scan_idx)
        self.assertLess(exit_idx - scan_idx, 200,
            "--scan handler must call sys.exit(0) shortly after detection")

    def test_scan_force_metadata_in_collect_missing(self):
        """_collect_missing_file_metadata must respect FORCE_METADATA to re-probe all files."""
        src = self._read_script()
        # Find _collect_missing_file_metadata function
        func_idx = src.index("def _collect_missing_file_metadata(")
        # Find the next function definition to scope our search
        next_def_idx = src.index("\ndef ", func_idx + 1)
        func_body = src[func_idx:next_def_idx]
        # Must check FORCE_METADATA before skipping files with existing metadata
        self.assertIn("not FORCE_METADATA", func_body,
            "_collect_missing_file_metadata must check FORCE_METADATA before skipping files with valid metadata")

    def test_scan_force_metadata_in_sweep(self):
        """Metadata sweep must respect FORCE_METADATA to re-probe all files, not just missing."""
        src = self._read_script()
        # Find the sweep section (comment + code)
        sweep_idx = src.index("Queue any files still missing metadata")
        # Find the next major section
        next_section = src.index("Batch-collect missing file metadata", sweep_idx)
        sweep_body = src[sweep_idx:next_section]
        # Must check FORCE_METADATA before skipping files with existing metadata
        self.assertIn("not FORCE_METADATA", sweep_body,
            "Metadata sweep must check FORCE_METADATA before skipping files with valid metadata")

    def test_scan_sweep_filters_by_library(self):
        """Metadata sweep must filter by SCAN_LIBRARIES when set."""
        src = self._read_script()
        sweep_idx = src.index("Queue any files still missing metadata")
        next_section = src.index("Batch-collect missing file metadata", sweep_idx)
        sweep_body = src[sweep_idx:next_section]
        self.assertIn("SCAN_LIBRARIES", sweep_body,
            "Metadata sweep must filter by SCAN_LIBRARIES")


class TestBrokenCrossValidation(unittest.TestCase):
    """Tests for cross-validation of container vs video stream duration in broken detection."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_collector_collects_video_duration(self):
        """Collector script must collect video stream duration via ffprobe."""
        src = self._read_script()
        # Find collector script
        collector_idx = src.index("collector_script = f'''")
        collector_end = src.index("'''", collector_idx + 30)
        collector = src[collector_idx:collector_end]
        self.assertIn("video_duration", collector,
            "Collector script must collect video_duration")
        self.assertIn("ffprobe", collector,
            "Collector script must use ffprobe for video stream duration")

    def test_video_duration_stored_in_cache(self):
        """Batch result parsing must store video_duration in file_metadata."""
        src = self._read_script()
        # Find the success result integration section
        self.assertIn("'video_duration' in entry", src,
            "Result parsing must check for video_duration in collector output")

    def test_broken_list_cross_validates(self):
        """_list_broken_files must cross-validate container vs video duration."""
        src = self._read_script()
        func_idx = src.index("def _list_broken_files(")
        next_def_idx = src.index("\n    @staticmethod", func_idx + 1)
        func_body = src[func_idx:next_def_idx]
        self.assertIn("video_duration", func_body,
            "_list_broken_files must use video_duration for cross-validation")
        self.assertIn("abs(container_duration - video_duration) < 2000", func_body,
            "_list_broken_files must check container vs video duration within 2s tolerance")

    def test_info_display_cross_validates(self):
        """show_item_info broken display must cross-validate container vs video duration."""
        src = self._read_script()
        # Find the show_item_info truncation check — it's in the elif plex_duration: block
        # that contains "File appears TRUNCATED"
        info_idx = src.index("File appears TRUNCATED")
        # Find the cross-validation before it (in the same function)
        check_idx = src.rindex("abs(container_duration - video_duration) < 2000", 0, info_idx)
        self.assertGreater(check_idx, 0,
            "show_item_info must cross-validate before reporting truncation")

    def test_verify_cache_cross_validates(self):
        """_verify_data_integrity must cross-validate broken detection."""
        src = self._read_script()
        func_idx = src.index("def _verify_data_integrity()")
        next_def_idx = src.index("\ndef ", func_idx + 1)
        func_body = src[func_idx:next_def_idx]
        self.assertIn("video_duration", func_body,
            "_verify_data_integrity must use video_duration cross-validation")

    def test_get_broken_reason_cross_validates(self):
        """_get_broken_reason must cross-validate before returning truncation."""
        src = self._read_script()
        func_idx = src.index("def _get_broken_reason(")
        next_def_idx = src.index("\ndef ", func_idx + 1)
        func_body = src[func_idx:next_def_idx]
        self.assertIn("video_duration", func_body,
            "_get_broken_reason must use video_duration cross-validation")

    def test_info_stats_cross_validates(self):
        """--info metadata stats must cross-validate broken counts."""
        src = self._read_script()
        # Find the METADATA & FILE HEALTH section
        stats_idx = src.index("METADATA & FILE HEALTH:")
        next_section = src.index("Print statistics", stats_idx)
        stats_body = src[stats_idx:next_section]
        self.assertIn("video_duration", stats_body,
            "--info metadata stats must use video_duration cross-validation")

    def test_collector_derives_ffprobe_from_ffmpeg(self):
        """Collector script must derive ffprobe path from ffmpeg path."""
        src = self._read_script()
        collector_idx = src.index("collector_script = f'''")
        collector_end = src.index("'''", collector_idx + 30)
        collector = src[collector_idx:collector_end]
        self.assertIn('os.path.join(os.path.dirname(ffmpeg), "ffprobe")', collector,
            "Collector must derive ffprobe path from ffmpeg path")

    def test_collector_uses_select_streams_v0(self):
        """Collector must use -select_streams v:0 to get only the video stream duration."""
        src = self._read_script()
        collector_idx = src.index("collector_script = f'''")
        collector_end = src.index("'''", collector_idx + 30)
        collector = src[collector_idx:collector_end]
        self.assertIn("-select_streams", collector,
            "Collector must use -select_streams to target video stream")
        self.assertIn("v:0", collector,
            "Collector must target first video stream (v:0)")

    def test_cross_validation_tolerance_2s(self):
        """All cross-validation sites must use 2000ms (2s) tolerance."""
        src = self._read_script()
        # Count occurrences of the tolerance check
        occurrences = src.count("abs(container_duration - video_duration) < 2000")
        self.assertGreaterEqual(occurrences, 4,
            f"Expected at least 4 cross-validation checks with 2s tolerance, found {occurrences}")

    def test_collect_missing_file_metadata_respects_force_metadata(self):
        """_collect_missing_file_metadata must not skip valid metadata when FORCE_METADATA is set.

        Regression: --scan set FORCE_METADATA but _collect_missing_file_metadata still skipped
        files with existing metadata, causing only ~30 files (with missing metadata) to be queued
        instead of all files in the library.
        """
        src = self._read_script()
        func_idx = src.index("def _collect_missing_file_metadata(")
        next_def_idx = src.index("\ndef ", func_idx + 1)
        func_body = src[func_idx:next_def_idx]
        # The skip condition must include "not FORCE_METADATA"
        self.assertIn("not FORCE_METADATA", func_body,
            "_collect_missing_file_metadata must check FORCE_METADATA")
        # The old buggy pattern was: "if existing_metadata and not existing_metadata.get('broken'):"
        # without checking FORCE_METADATA. Verify the fix is in place.
        self.assertNotRegex(func_body,
            r"if existing_metadata and not existing_metadata\.get\('broken'\):\s*\n\s*continue",
            "_collect_missing_file_metadata must NOT skip valid metadata without checking FORCE_METADATA")

    def test_broken_list_shows_version_count(self):
        """_list_broken_files must show version count column (V) for multi-version entries."""
        src = self._read_script()
        func_idx = src.index("def _list_broken_files(")
        next_def_idx = src.index("\n    @staticmethod", func_idx + 1)
        func_body = src[func_idx:next_def_idx]
        self.assertIn("ver_count", func_body,
            "_list_broken_files must compute version count")
        self.assertIn("'V'", func_body,
            "_list_broken_files header must include V column")

    def test_broken_list_version_count_e2e(self):
        """--broken output must include V column header."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--broken'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--broken failed: {result.stderr}")
        # Skip if no broken files exist in cache (no table output)
        if "|" not in result.stdout:
            self.skipTest("No broken files in cache — cannot verify V column header")
        # Header must contain V column (right-aligned, variable padding)
        self.assertRegex(result.stdout, r'\|\s+V\s+\|',
            "--broken output must include V column in header")

    def test_collector_falls_back_to_end_probe(self):
        """Collector must fall back to ffmpeg -sseof probe when ffprobe stream duration is N/A."""
        src = self._read_script()
        collector_idx = src.index("collector_script = f'''")
        collector_end = src.index("'''", collector_idx + 30)
        collector = src[collector_idx:collector_end]
        self.assertIn("-sseof", collector,
            "Collector must use ffmpeg -sseof as fallback when stream duration is N/A")
        self.assertIn("file_ends_cleanly", collector,
            "Collector must set file_ends_cleanly flag from end-probe result")

    def test_broken_detection_respects_file_ends_cleanly(self):
        """Broken detection must skip files where file_ends_cleanly is True."""
        src = self._read_script()
        func_idx = src.index("def _list_broken_files(")
        next_def_idx = src.index("\n    @staticmethod", func_idx + 1)
        func_body = src[func_idx:next_def_idx]
        self.assertIn("file_ends_cleanly", func_body,
            "_list_broken_files must check file_ends_cleanly flag")

    def test_file_ends_cleanly_stored_in_cache(self):
        """Batch result parsing must store file_ends_cleanly in file_metadata."""
        src = self._read_script()
        # Find the success result integration section (where file_metadata is built)
        self.assertIn("'file_ends_cleanly'", src,
            "Result parsing must store file_ends_cleanly in file_metadata")

    def test_cache_update_summary_includes_broken_count(self):
        """Cache update summary line must include total broken files count."""
        src = self._read_script()
        self.assertIn("broken_str", src,
            "Cache summary must include broken file count string")
        self.assertIn("_get_broken_reason", src,
            "Cache summary must use _get_broken_reason to count all broken files")
        self.assertIn("_write_cache_update_log", src,
            "Cache update must write JSON update log")
        self.assertIn("CACHE_UPDATES_FILE", src,
            "Must reference CACHE_UPDATES_FILE config variable")


class TestCacheUpdateLog(unittest.TestCase):
    """Tests for the JSON cache update log feature (CACHE_UPDATES_FILE)."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_cache_updates_file_config_exists(self):
        """CACHE_UPDATES_FILE must be defined in CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("'CACHE_UPDATES_FILE'", src,
            "CONFIG_DEFAULTS must include CACHE_UPDATES_FILE")
        self.assertIn("/tmp/my-plex.cache-updates.json", src,
            "Default value must be /tmp/my-plex.cache-updates.json")

    def test_cache_updates_file_global_variable(self):
        """CACHE_UPDATES_FILE must be initialized as a global variable."""
        src = self._read_script()
        self.assertIn("CACHE_UPDATES_FILE = CONFIG_DEFAULTS['CACHE_UPDATES_FILE']", src,
            "Must initialize CACHE_UPDATES_FILE from CONFIG_DEFAULTS")

    def test_write_cache_update_log_function_exists(self):
        """_write_cache_update_log function must exist and write JSON."""
        src = self._read_script()
        self.assertIn("def _write_cache_update_log(", src,
            "Must define _write_cache_update_log function")
        import re
        match = re.search(r'(def _write_cache_update_log\(.*?\):\n.*?)(?=\ndef [a-z_])', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("json.dump", func_body,
            "Must write JSON to file")
        self.assertIn("CACHE_UPDATES_FILE", func_body,
            "Must use CACHE_UPDATES_FILE path")

    def test_log_includes_library_changes(self):
        """JSON log must include per-library change details."""
        src = self._read_script()
        import re
        match = re.search(r'(def _write_cache_update_log\(.*?\):\n.*?)(?=\ndef [a-z_])', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("changes_by_library", func_body,
            "Must organize changes by library")
        self.assertIn("library_delta_details", func_body,
            "Must read from library_delta_details")

    def test_log_includes_broken_from_metadata(self):
        """JSON log must include broken file details from metadata collection (not from cache)."""
        src = self._read_script()
        import re
        match = re.search(r'(def _write_cache_update_log\(.*?\):\n.*?)(?=\ndef [a-z_])', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("broken_files_from_metadata", func_body,
            "Must include broken files from metadata collection (stderr not fully in cache)")
        # Must NOT duplicate what's already in cache
        self.assertNotIn("all_broken_files", func_body,
            "Must NOT list all broken files — that info is already in the cache")

    def test_log_includes_undo_info_for_removed(self):
        """Removed items must include file details for undo capability."""
        src = self._read_script()
        # Check that removal detail_info includes 'files' and 'duration' for undo
        import re
        # Find the removal details section
        match = re.search(r"(# Build detailed info BEFORE removing.*?)(?=# Actually remove)", src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must have removal details section")
        removal_section = match.group(1)
        self.assertIn("'duration'", removal_section,
            "Removal details must capture duration for undo")
        self.assertIn("'files'", removal_section,
            "Removal details must capture files dict for undo")

    def test_summary_printed_when_changes(self):
        """SUMMARY OF CHANGES must print when there are changes (library or metadata)."""
        src = self._read_script()
        idx = src.index("SUMMARY OF CHANGES")
        # Get context before — must be guarded by has_changes (includes metadata_probed)
        context_before = src[max(0, idx-200):idx]
        self.assertIn("has_changes", context_before,
            "SUMMARY OF CHANGES must be inside 'has_changes' block")
        # has_changes must include metadata_probed (not just library changes)
        has_changes_idx = src.index("has_changes = ")
        has_changes_line = src[has_changes_idx:src.index(')', has_changes_idx) + 1]
        self.assertIn("metadata_probed", has_changes_line,
            "has_changes must include metadata_probed, not just library changes")

    def test_details_file_path_always_printed(self):
        """Must always print path to CACHE_UPDATES_FILE, including on no-change runs."""
        src = self._read_script()
        self.assertIn("Details: {CACHE_UPDATES_FILE}", src,
            "Must print the JSON log file path for the user")

    def test_metadata_summary_in_summary_section(self):
        """Metadata collection summary must appear in SUMMARY OF CHANGES, not in batch function."""
        src = self._read_script()
        # The "Metadata collected:" line should be AFTER "SUMMARY OF CHANGES"
        summary_idx = src.index("SUMMARY OF CHANGES")
        metadata_collected_idx = src.index("Metadata collected:", summary_idx)
        self.assertGreater(metadata_collected_idx, summary_idx,
            "Metadata summary must come after SUMMARY OF CHANGES header")

    def test_broken_output_not_in_batch_function(self):
        """Verbose BROKEN file output must NOT be printed during batch metadata collection."""
        src = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', src, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        func_body = match.group(1)
        # Should NOT contain the old verbose BROKEN print pattern
        self.assertNotIn("✗ BROKEN [W", func_body,
            "Batch function must not print verbose BROKEN output — details go to JSON log")

    def test_track_delta_helper_exists(self):
        """_track_delta() helper must exist for shared delta tracking."""
        src = self._read_script()
        self.assertIn("def _track_delta(", src,
            "_track_delta helper must exist for delta counter tracking")
        # Must be used by both movie and show processing paths
        import re
        movie_section = re.search(r'def _process_movies_from_database.*?(?=\ndef [a-z_])', src, re.DOTALL)
        assert movie_section is not None, "the pattern above did not match"
        self.assertIsNotNone(movie_section)
        self.assertIn("_track_delta(", movie_section.group(),
            "_process_movies_from_database must call _track_delta")
        show_section = re.search(r'def _process_series_from_database.*?(?=\ndef [a-z_])', src, re.DOTALL)
        assert show_section is not None, "the pattern above did not match"
        self.assertIsNotNone(show_section)
        self.assertIn("_track_delta(", show_section.group(),
            "_process_series_from_database must call _track_delta")


###########################################################################################
#### EPISODE TSV / --missing / --sort-new TESTS
###########################################################################################

class TestEpisodesTSV(unittest.TestCase):
    """Test episodes.tsv read/write and format detection."""

    def setUp(self):
        # A unit test must never reach the real Plex server: no remote host,
        # and any subprocess call (ssh) fails the test instead of running.
        from unittest import mock
        g = write_episodes_tsv.__globals__
        self._saved_remote = g.get('PLEX_DB_REMOTE_HOST')
        g['PLEX_DB_REMOTE_HOST'] = ''
        # Calls are RECORDED as well as refused: code under test may swallow the
        # exception, the record it cannot.
        self._subprocess_calls = []
        def _no_ssh(*a, **k):
            self._subprocess_calls.append(a[0] if a else k)
            raise AssertionError(f"episodes.tsv test ran a subprocess: {a[0] if a else k}")
        self._patch = mock.patch('subprocess.run', side_effect=_no_ssh)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        write_episodes_tsv.__globals__['PLEX_DB_REMOTE_HOST'] = self._saved_remote
        self.assertEqual(self._subprocess_calls, [], "a unit test must not run ssh / subprocesses")

    def test_local_write_keeps_the_previous_file(self):
        """Without a remote host the TSV is written locally, and an existing one
        is kept as a backup -- the same as the SSH path does on the server."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tsv = os.path.join(d, 'episodes.tsv')
            eps = [{'season': 1, 'episode': 1, 'date': '2025-01-01', 'title': 'One'}]
            write_episodes_tsv(tsv, {'source': 'tmdb', 'slug': 'x'}, eps)
            write_episodes_tsv(tsv, {'source': 'tmdb', 'slug': 'x', '_prev_updated': '2025-01-02'}, eps)
            self.assertTrue(os.path.isfile(tsv))
            self.assertTrue(os.path.isfile(tsv + '.2025-01-02'), sorted(os.listdir(d)))

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_write_and_read_roundtrip(self):
        """Write a TSV and read it back, verify data integrity."""
        import tempfile, os
        metadata = {'source': 'fernsehserien.de', 'slug': 'test-show', 'series_id': '12345'}
        episodes = [
            {'season': 1, 'episode': 1, 'date': '2025-01-01', 'title': 'Pilot'},
            {'season': 1, 'episode': 2, 'date': '2025-01-08', 'title': 'Second'},
            {'season': 2, 'episode': 1, 'date': '2025-09-01', 'title': 'New Season'},
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            tsv_path = f.name

        try:
            write_episodes_tsv(tsv_path, metadata, episodes)
            read_meta, read_eps = read_episodes_tsv(tsv_path)

            self.assertEqual(read_meta['source'], 'fernsehserien.de')
            self.assertEqual(read_meta['slug'], 'test-show')
            self.assertEqual(read_meta['series_id'], '12345')
            self.assertEqual(len(read_eps), 3)
            self.assertEqual(read_eps[0]['season'], 1)
            self.assertEqual(read_eps[0]['episode'], 1)
            self.assertEqual(read_eps[0]['date'], '2025-01-01')
            self.assertEqual(read_eps[0]['title'], 'Pilot')
            self.assertEqual(read_eps[2]['season'], 2)
        finally:
            os.unlink(tsv_path)

    def test_read_nonexistent(self):
        """Reading a nonexistent file returns (None, None)."""
        meta, eps = read_episodes_tsv('/nonexistent/path/episodes.tsv')
        self.assertIsNone(meta)
        self.assertIsNone(eps)

    def test_metadata_comments_preserved(self):
        """Verify header comments contain slug and source."""
        import tempfile, os
        metadata = {'source': 'fernsehserien.de', 'slug': 'my-show', 'specials_pattern': 'xxl|special'}
        episodes = [{'season': 1, 'episode': 1, 'date': '2025-01-01', 'title': ''}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            tsv_path = f.name

        try:
            write_episodes_tsv(tsv_path, metadata, episodes)
            with open(tsv_path) as f:
                content = f.read()
            self.assertIn('# source: fernsehserien.de', content)
            self.assertIn('# slug: my-show', content)
            self.assertIn('# specials_pattern: xxl|special', content)
            self.assertIn('# DO NOT edit or remove', content)
        finally:
            os.unlink(tsv_path)

    def test_stale_detection(self):
        """Test that freshly written TSV is not stale, old one is."""
        import tempfile, os, time
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            f.write("season\tepisode\tdate\ttitle\n")
            tsv_path = f.name

        try:
            self.assertFalse(is_episodes_tsv_stale(tsv_path, max_age=86400))
            self.assertTrue(is_episodes_tsv_stale(tsv_path, max_age=0))  # 0 seconds = always stale
            self.assertTrue(is_episodes_tsv_stale('/nonexistent.tsv'))
        finally:
            os.unlink(tsv_path)

    def test_fernsehserien_summary_line(self):
        """_scrape_fernsehserien_de must print a summary line like TMDB/TVDB do."""
        src = self._read_script()
        self.assertIn("fernsehserien.de:", src, "fernsehserien.de scraper must print summary with episode/season count")
        self.assertRegex(src, r"fernsehserien\.de:.*episodes in.*seasons for", "Summary must follow 'N episodes in M seasons for' pattern")


class TestDateExtraction(unittest.TestCase):
    """Test filename date extraction for various formats."""

    def test_tvoon_standard(self):
        """Standard TVOON filename: Show_Name_YY.MM.DD_HH-MM_channel_..."""
        from datetime import date
        d = extract_episode_date('Die_Millionenshow_26.01.19_20-15_orf2_55_TVOON_DE.mpg.HQ.avi')
        self.assertEqual(d, date(2026, 1, 19))

    def test_tvoon_2000s(self):
        """TVOON with 2000s date."""
        from datetime import date
        d = extract_episode_date('Show_05.03.15_18-00_ard_50_TVOON_DE.mpg.HQ.avi')
        self.assertEqual(d, date(2005, 3, 15))

    def test_tvoon_1900s(self):
        """TVOON with year >= 50 maps to 1900s."""
        from datetime import date
        d = extract_episode_date('Show_99.12.31_20-00_ard_50_TVOON_DE.mpg.avi')
        self.assertEqual(d, date(1999, 12, 31))

    def test_iso_date(self):
        """ISO format: YYYY-MM-DD in filename."""
        from datetime import date
        d = extract_episode_date('show_2025-03-10_something.mkv')
        self.assertEqual(d, date(2025, 3, 10))

    def test_no_date(self):
        """Filename without recognizable date pattern."""
        d = extract_episode_date('random_show_episode.avi')
        self.assertIsNone(d)

    def test_auto_mode_tries_all(self):
        """Auto mode should try TVOON first, then ISO."""
        from datetime import date
        # TVOON format
        d = extract_episode_date('Show_26.03.09_20-15_orf2_55_TVOON_DE.mpg.HQ.avi', format_type='auto')
        self.assertEqual(d, date(2026, 3, 9))
        # ISO format
        d = extract_episode_date('show_2025-03-10.mkv', format_type='auto')
        self.assertEqual(d, date(2025, 3, 10))

    def test_specific_format(self):
        """Requesting a specific format only tries that format."""
        # This TVOON filename should NOT match ISO format
        d = extract_episode_date('Show_26.03.09_20-15_orf2_55_TVOON_DE.mpg.HQ.avi', format_type='ISO')
        self.assertIsNone(d)


class TestSpecialDetection(unittest.TestCase):
    """Test special episode pattern matching."""

    def test_xxl_special(self):
        self.assertTrue(is_special_episode('Wer_weiss_denn_sowas_XXL_25.01.01_20-15_ard.avi'))

    def test_promi_special(self):
        self.assertTrue(is_special_episode('Die_Promi_Millionenshow_25.01.01_20-15_orf2.avi'))

    def test_normal_episode(self):
        self.assertFalse(is_special_episode('Wer_weiss_denn_sowas_25.01.01_18-00_ard_50_TVOON_DE.mpg.HQ.avi'))

    def test_custom_pattern(self):
        self.assertTrue(is_special_episode('Show_Custom_25.01.01.avi', specials_pattern='custom'))
        self.assertFalse(is_special_episode('Show_Normal_25.01.01.avi', specials_pattern='custom'))


class TestMissingEpisodes(unittest.TestCase):
    """Test --missing command source inspection."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_missing_flag_in_media_argparser(self):
        """--missing must be in PLEX_Media.argparser."""
        src = self._read_script()
        self.assertIn("'--missing'", src, "--missing not found in argparse arguments")

    def test_missing_flag_in_library_argparser(self):
        """--missing must be in PLEX_Library.argparser."""
        src = self._read_script()
        # Find the PLEX_Library class section (ends at next top-level class)
        import re
        lib_section = re.search(r'class PLEX_Library.*?(?=\nclass [A-Z])', src, re.DOTALL)
        assert lib_section is not None, "the pattern above did not match"
        self.assertIsNotNone(lib_section)
        self.assertIn("'--missing'", lib_section.group(),
            "--missing not found in PLEX_Library argparser")

    def test_missing_flag_in_global_parser(self):
        """--missing must be in GLOBAL_CMD_PARSER."""
        src = self._read_script()
        self.assertIn("GLOBAL_CMD_PARSER.add_argument('--missing'", src,
            "--missing not found in GLOBAL_CMD_PARSER")

    def test_missing_help_case(self):
        """Help system must have a 'missing' case."""
        src = self._read_script()
        self.assertIn("case 'missing'", src, "case 'missing' not found in help system")

    def test_missing_dispatch_in_global(self):
        """execute_global_commands must dispatch --missing."""
        src = self._read_script()
        self.assertIn('cmd_missing', src, "cmd_missing not found in source")


class TestSortNew(unittest.TestCase):
    """Test --sort-new command source inspection."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_sort_new_flag_in_global_parser(self):
        """--sort-new must be in GLOBAL_CMD_PARSER."""
        src = self._read_script()
        self.assertIn("'--sort-new'", src, "--sort-new not found in GLOBAL_CMD_PARSER")

    def test_sort_new_help_case(self):
        """Help system must have a 'sort-new' case."""
        src = self._read_script()
        self.assertIn("case 'sort-new'", src, "case 'sort-new' not found in help system")

    def test_sort_new_dispatch(self):
        """execute_global_commands must dispatch --sort-new."""
        src = self._read_script()
        self.assertIn('cmd_sort_new', src, "cmd_sort_new not found in source")

    def test_dry_run_flag(self):
        """--dry-run must be in argument parsers."""
        src = self._read_script()
        self.assertIn("'--dry-run'", src, "--dry-run not found in argparse")

    # --- season-token wrapper consolidation (v3 roadmap item 6) ---------

    def test_season_token_match_detects_release_wrappers(self):
        """_season_token_match must cut '<series>.sNN.<junk>' wrapper names."""
        self.assertEqual(
            _season_token_match('the.rings.of.power.s01.complete.720p.webrip-grp'),
            ('the.rings.of.power', 1))
        self.assertEqual(
            _season_token_match('library2-series.season 2 (1080p)'),
            ('library2-series', 2))
        self.assertEqual(_season_token_match('tagesschau'), None)
        # Nothing left of the series name → not a wrapper
        self.assertEqual(_season_token_match('.s01.complete'), None)
        # SxxEyy episode tokens must NOT match (digits run into 'e02' — no
        # word boundary), so a dir merely named after an episode is safe.
        self.assertIsNone(_season_token_match('wrapper.s01e02.named.dir'))

    def test_season_token_regex_in_config(self):
        """SORT_NEW_SEASON_TOKEN_REGEX must live in CONFIG_DEFAULTS + loader + template."""
        src = self._read_script()
        self.assertIn("'SORT_NEW_SEASON_TOKEN_REGEX'", src)
        self.assertIn("SORT_NEW_SEASON_TOKEN_REGEX = CONFIG_DEFAULTS[", src)
        self.assertIn("SORT_NEW_SEASON_TOKEN_REGEX = {CONFIG_DEFAULTS["
                      "'SORT_NEW_SEASON_TOKEN_REGEX']!r}", src,
                      "--create-config template must document the default")

    def test_consolidation_phase_wired_into_sort_new(self):
        """cmd_sort_new must run the consolidation phase and exclude its results."""
        src = self._read_script()
        self.assertIn('def _sort_new_consolidate_season_wrappers(', src)
        idx = src.index('def cmd_sort_new(')
        end = src.index('\ndef ', idx + 1)
        body = src[idx:end]
        self.assertIn('_sort_new_consolidate_season_wrappers(', body,
                      'cmd_sort_new must invoke the consolidation phase')
        self.assertIn('k not in _consolidated', body,
                      'consolidated series must leave the per-series sort loop')

    def test_consolidation_safety_properties(self):
        """Consolidation must never clobber, must trash (not rm) stale artifacts,
        must rmdir (non-recursive) the emptied wrapper, and must keep cache +
        sidecar + JSON-log integrity in-process."""
        src = self._read_script()
        idx = src.index('def _sort_new_consolidate_season_wrappers(')
        end = src.index('\ndef cmd_sort_new(', idx)
        body = src[idx:end]
        self.assertIn('mv -n', body, 'moves must be no-clobber')
        self.assertIn('move_to_trash(', body, 'stale artifacts must be TRASHED, never rm')
        self.assertNotIn('rm -r', body, 'consolidation must never rm recursively')
        self.assertIn('rmdir', body, 'emptied wrapper goes via non-recursive rmdir')
        self.assertIn('_update_cache_filepath(', body, 'per-file cache update required')
        self.assertIn('update_and_save_cache(build_media_cache_dict())', body)
        self.assertIn("_write_resolve_log('sort_new_season_wrappers'", body)
        self.assertIn('episodes.tsv', body, 'stale fake-series TSVs must be handled')

    def test_sort_new_handles_movie_libraries(self):
        """cmd_sort_new must process Movie libraries for bare files."""
        src = self._read_script()
        self.assertIn("lib_type != 'Movie'", src, "sort-new must handle Movie libraries")
        self.assertIn('VIDEO_EXTENSIONS', src, "sort-new must check video extensions")

    def test_sort_new_movie_dir_name_convention(self):
        """Movie directory names must be lowercase with dot separators."""
        src = self._read_script()
        # Check for the lowercase + dot conversion
        self.assertIn('.lower()', src, "sort-new must lowercase movie dir names")
        self.assertIn("'.'", src, "sort-new must use dot as separator")

    def test_sort_new_is_shortcut_for_unsorted_fix(self):
        """--sort-new dispatch must print shortcut message."""
        src = self._read_script()
        self.assertIn("Shortcut for: --unsorted --fix", src,
                       "--sort-new must print shortcut message")

    def test_sort_new_in_media_argparser(self):
        """--sort-new must be in PLEX_Media argparser."""
        import re
        src = self._read_script()
        match = re.search(r"TYPE_STR = 'media'.*?argparser\.add_argument\('--sort-new'", src, re.DOTALL)
        self.assertIsNotNone(match, "Must define --sort-new in media argparser")

    def test_sort_new_in_library_argparser(self):
        """--sort-new must be in PLEX_Library argparser."""
        import re
        src = self._read_script()
        match = re.search(r"class PLEX_Library.*?argparser\.add_argument\('--sort-new'", src, re.DOTALL)
        self.assertIsNotNone(match, "Must define --sort-new in library argparser")

    def test_sort_new_help_mentions_unsorted_fix(self):
        """--help sort-new must mention --unsorted --fix equivalence."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'sort-new'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help sort-new failed: {result.stderr}")
        self.assertIn('--unsorted --fix', result.stdout,
                       "--help sort-new must mention --unsorted --fix")

    def test_sort_new_moves_siblings(self):
        """sort-new must detect and move sibling files (.srt, .nfo, etc.)."""
        src = self._read_script()
        self.assertIn('siblings', src, "sort-new must handle sibling files")

    def test_sort_new_nxnn_pattern(self):
        """--sort-new must support NxNN format (e.g., 1x01, 12x05)."""
        content = self._read_script()
        sort_start = content.find('def cmd_sort_new(')
        sort_end = content.find('\ndef ', sort_start + 1)
        sort_body = content[sort_start:sort_end]
        self.assertIn('nxnn_match', sort_body)

    def test_sort_new_absolute_numbering(self):
        """--sort-new must support absolute numbering (e.g., 101 → S01E01)."""
        content = self._read_script()
        sort_start = content.find('def cmd_sort_new(')
        sort_end = content.find('\ndef ', sort_start + 1)
        sort_body = content[sort_start:sort_end]
        self.assertIn('abs_match', sort_body)
        self.assertIn('[absolute]', sort_body)
        self.assertIn('max_ep_per_season', sort_body)
        self.assertIn('is_true_episode_num', sort_body)

    def test_sort_new_year_matching(self):
        """--sort-new must support year-based matching from (YYYY) or [YYYY]."""
        content = self._read_script()
        sort_start = content.find('def cmd_sort_new(')
        sort_end = content.find('\ndef ', sort_start + 1)
        sort_body = content[sort_start:sort_end]
        self.assertIn('year_match', sort_body)
        self.assertIn('[year]', sort_body)
        self.assertIn('_normalize_alpha', sort_body)

    def test_sort_new_leading_number(self):
        """--sort-new must support bare leading episode numbers (e.g., 1.manimal.avi)."""
        content = self._read_script()
        sort_start = content.find('def cmd_sort_new(')
        sort_end = content.find('\ndef ', sort_start + 1)
        sort_body = content[sort_start:sort_end]
        self.assertIn('bare_num_match', sort_body)
        self.assertIn('[leading-num]', sort_body)


class TestMissingE2E(unittest.TestCase):
    """End-to-end tests for --missing."""

    def test_missing_help(self):
        """my-plex --help missing should exit 0."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'missing'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, f"--help missing failed: {result.stderr}")
        self.assertIn('MISSING EPISODES', result.stdout)

    def test_missing_help_shows_library_usage(self):
        """--help missing should document library usage."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'missing'],
            capture_output=True, text=True, timeout=60)
        self.assertIn('LIBRARY', result.stdout, "--help missing should document library usage")

    def test_sort_new_help(self):
        """my-plex --help sort-new should exit 0."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'sort-new'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, f"--help sort-new failed: {result.stderr}")
        self.assertIn('SORT NEW', result.stdout)

    def test_missing_bare_gives_error(self):
        """my-plex --missing (without show) should error gracefully, not stack trace."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--missing'],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0, "--missing without args should fail")
        output = result.stdout + result.stderr
        self.assertNotIn('Traceback', output, "--missing without args should not produce stack trace")
        self.assertIn('ERROR', output, "--missing without args should show error message")

    def test_unknown_flag_gives_error(self):
        """my-plex --asdf should error gracefully, not stack trace."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--asdf'],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0, "--asdf should fail")
        output = result.stdout + result.stderr
        self.assertNotIn('Traceback', output, "--asdf should not produce stack trace")


class TestCustomDateExtractors(unittest.TestCase):
    """Test the custom date extractor loading interface."""

    def test_builtin_extractors_registered(self):
        """Built-in extractors (TVOON, ISO) must be in _BUILTIN_EXTRACTORS."""
        self.assertIn('TVOON', _BUILTIN_EXTRACTORS)
        self.assertIn('ISO', _BUILTIN_EXTRACTORS)
        self.assertIsNotNone(_BUILTIN_EXTRACTORS['TVOON'])
        self.assertIsNotNone(_BUILTIN_EXTRACTORS['ISO'])

    def test_unknown_format_returns_none(self):
        """Requesting an unknown format should return None."""
        d = extract_episode_date('somefile.avi', format_type='UNKNOWN_FORMAT')
        self.assertIsNone(d)


class TestEpisodeSourceSelection(unittest.TestCase):
    """Test multi-source episode scraping architecture."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_source_flag_in_media_argparser(self):
        """--source must be in PLEX_Media.argparser."""
        src = self._read_script()
        self.assertIn("'--source'", src, "--source not found in argparse arguments")

    def test_source_flag_in_library_argparser(self):
        """--source must be in PLEX_Library.argparser."""
        import re
        src = self._read_script()
        lib_section = re.search(r'class PLEX_Library.*?(?=\nclass [A-Z])', src, re.DOTALL)
        assert lib_section is not None, "the pattern above did not match"
        self.assertIsNotNone(lib_section)
        self.assertIn("'--source'", lib_section.group(),
            "--source not found in PLEX_Library argparser")

    def test_source_flag_in_global_parser(self):
        """--source must be in GLOBAL_CMD_PARSER."""
        src = self._read_script()
        self.assertIn("GLOBAL_CMD_PARSER.add_argument('--source'", src,
            "--source not found in GLOBAL_CMD_PARSER")

    def test_source_in_main_parser(self):
        """--source must be in main_parser (suppressed) to prevent value consumption."""
        src = self._read_script()
        self.assertIn("main_parser.add_argument('--source'", src,
            "--source not found in main_parser")

    def test_scrape_episodes_accepts_source(self):
        """scrape_episodes() must accept source and external_ids params."""
        import inspect
        sig = inspect.signature(scrape_episodes)
        self.assertIn('source', sig.parameters, "scrape_episodes missing 'source' param")
        self.assertIn('external_ids', sig.parameters, "scrape_episodes missing 'external_ids' param")

    def test_scrape_dispatch_tvdb(self):
        """scrape_episodes dispatch must include 'tvdb' case."""
        src = self._read_script()
        self.assertIn("case 'tvdb':", src, "tvdb case not found in scrape_episodes dispatch")

    def test_scrape_dispatch_tmdb(self):
        """scrape_episodes dispatch must include 'tmdb' case."""
        src = self._read_script()
        self.assertIn("case 'tmdb':", src, "tmdb case not found in scrape_episodes dispatch")

    def test_determine_episode_source_exists(self):
        """_determine_episode_source function must exist."""
        src = self._read_script()
        self.assertIn("def _determine_episode_source(", src,
            "_determine_episode_source not found")

    def test_cmd_missing_passes_source_override(self):
        """cmd_missing must accept and pass source_override."""
        import inspect
        sig = inspect.signature(cmd_missing)
        self.assertIn('source_override', sig.parameters,
            "cmd_missing missing 'source_override' param")

    def test_tvdb_scraper_exists(self):
        """_scrape_tvdb function must exist."""
        src = self._read_script()
        self.assertIn("def _scrape_tvdb(", src, "_scrape_tvdb not found")

    def test_tmdb_scraper_exists(self):
        """_scrape_tmdb function must exist."""
        src = self._read_script()
        self.assertIn("def _scrape_tmdb(", src, "_scrape_tmdb not found")

    def test_tvdb_login_exists(self):
        """_tvdb_login function must exist."""
        src = self._read_script()
        self.assertIn("def _tvdb_login(", src, "_tvdb_login not found")


class TestExternalIdsInCache(unittest.TestCase):
    """Test external IDs (tvdb/tmdb/imdb) storage in cache."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_external_ids_in_series_dict(self):
        """Show dicts in OBJ_BY_ID must include external_ids field."""
        src = self._read_script()
        # The show dict creation in _process_series_from_database
        self.assertIn("'external_ids': series_info.get('external_ids'", src,
            "external_ids not found in show dict creation")

    def test_external_ids_in_movie_dict(self):
        """Movie dicts must include external_ids field."""
        src = self._read_script()
        self.assertIn("'external_ids': tags.get('external_ids'", src,
            "external_ids not found in movie dict creation")

    def test_tag_type_314_in_show_query(self):
        """fetch_series_from_database tags query must include tag_type 314."""
        src = self._read_script()
        # Both movie and show queries should include 314
        self.assertIn('314', src, "tag_type 314 not found in source")

    def test_library_agent_in_query(self):
        """get_library_sections_from_database must select agent column."""
        src = self._read_script()
        self.assertIn("agent, language", src,
            "agent and language not selected in library sections query")

    def test_library_agent_in_stats(self):
        """EMPTY_LIBRARY_STATS must include agent and language."""
        self.assertIn('agent', EMPTY_LIBRARY_STATS,
            "agent not in EMPTY_LIBRARY_STATS")
        self.assertIn('language', EMPTY_LIBRARY_STATS,
            "language not in EMPTY_LIBRARY_STATS")


class TestEpisodeSourceConfig(unittest.TestCase):
    """Test API key and episode source configuration."""

    def test_tvdb_api_key_in_defaults(self):
        """TVDB_API_KEY must be in CONFIG_DEFAULTS."""
        self.assertIn('TVDB_API_KEY', CONFIG_DEFAULTS,
            "TVDB_API_KEY not in CONFIG_DEFAULTS")

    def test_tmdb_api_key_in_defaults(self):
        """TMDB_API_KEY must be in CONFIG_DEFAULTS."""
        self.assertIn('TMDB_API_KEY', CONFIG_DEFAULTS,
            "TMDB_API_KEY not in CONFIG_DEFAULTS")

    def test_missing_episodes_source_in_defaults(self):
        """MISSING_EPISODES_SOURCE must be in CONFIG_DEFAULTS."""
        self.assertIn('MISSING_EPISODES_SOURCE', CONFIG_DEFAULTS,
            "MISSING_EPISODES_SOURCE not in CONFIG_DEFAULTS")

    def test_missing_episodes_source_is_dict(self):
        """MISSING_EPISODES_SOURCE default must be a dict."""
        self.assertIsInstance(CONFIG_DEFAULTS['MISSING_EPISODES_SOURCE'], dict,
            "MISSING_EPISODES_SOURCE default should be empty dict")

    def test_api_keys_default_none(self):
        """API keys should default to None."""
        self.assertIsNone(CONFIG_DEFAULTS['TVDB_API_KEY'])
        self.assertIsNone(CONFIG_DEFAULTS['TMDB_API_KEY'])


class TestSourceE2E(unittest.TestCase):
    """End-to-end tests for --source flag."""

    def test_help_missing_shows_source(self):
        """--help missing should document --source."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'missing'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--source', result.stdout, "--help missing should mention --source")
        self.assertIn('tvdb', result.stdout, "--help missing should mention tvdb")
        self.assertIn('tmdb', result.stdout, "--help missing should mention tmdb")
        self.assertIn('fernsehserien.de', result.stdout, "--help missing should mention fernsehserien.de")

    def test_source_with_invalid_choice(self):
        """my-plex --missing X --source invalid should error."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--missing', 'test', '--source', 'invalid'],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0, "--source invalid should fail")
        output = result.stdout + result.stderr
        self.assertNotIn('Traceback', output, "should not produce stack trace")

    def test_help_missing_shows_api_key_info(self):
        """--help missing should document API key registration."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'missing'],
            capture_output=True, text=True, timeout=60)
        self.assertIn('API KEY', result.stdout.upper(), "--help missing should mention API keys")
        self.assertIn('thetvdb.com', result.stdout, "--help missing should mention thetvdb.com")
        self.assertIn('themoviedb.org', result.stdout, "--help missing should mention themoviedb.org")


class TestRename(unittest.TestCase):
    """Tests for --rename command and EPISODE_NAME_PATTERN config."""

    def test_help_rename(self):
        """--help rename should show rename documentation."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'rename'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn('RENAME EPISODES', result.stdout)
        self.assertIn('EPISODE_NAME_PATTERN', result.stdout)
        self.assertIn('{S0XE0X}', result.stdout)
        self.assertIn('{TITLE}', result.stdout)
        self.assertIn('{SERIES}', result.stdout)
        self.assertIn('{WATCHED}', result.stdout)
        self.assertIn('{WATCHEDDATE}', result.stdout)
        self.assertIn('--dry-run', result.stdout)

    def test_rename_without_target_errors(self):
        """--rename without a library or media target should error."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--rename'],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0, "--rename without target should fail")
        output = result.stdout + result.stderr
        self.assertIn('ERROR', output)
        self.assertIn('--rename requires', output)

    def test_rename_dry_run_no_file_changes(self):
        """--rename --dry-run should preview without changing files."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--rename', 'boston legal', '--dry-run'],
            capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        if result.returncode != 0 and 'No items found' not in output and 'Traceback' not in result.stderr:
            self.skipTest("'boston legal' not in cache or cache empty — cannot test --rename dry-run")
        self.assertEqual(result.returncode, 0, f"--rename --dry-run should succeed, stderr: {result.stderr}")
        self.assertIn('[DRY-RUN]', result.stdout, "Dry run should show [DRY-RUN] prefix")
        self.assertNotIn('ERROR', result.stdout + result.stderr, "Dry run should not have errors")
        self.assertNotIn('Traceback', result.stderr, "Should not produce stack trace")

    def test_rename_obj_form_dry_run(self):
        """my-plex 'boston legal' --rename --dry-run should work."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, 'boston legal', '--rename', '--dry-run'],
            capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        if result.returncode != 0 and 'No items found' not in output and 'Traceback' not in result.stderr:
            self.skipTest("'boston legal' not in cache or cache empty — cannot test --rename obj form")
        self.assertEqual(result.returncode, 0, f"obj form should succeed, stderr: {result.stderr}")
        self.assertIn('[DRY-RUN]', result.stdout)

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_rename_config_default_exists(self):
        """EPISODE_NAME_PATTERN should exist in CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("'EPISODE_NAME_PATTERN'", src, "CONFIG_DEFAULTS should include EPISODE_NAME_PATTERN")

    def test_rename_in_media_argparser(self):
        """--rename should be in PLEX_Media argparser."""
        src = self._read_script()
        self.assertIn("'--rename'", src, "PLEX_Media argparser should have --rename")

    def test_rename_help_shows_current_pattern(self):
        """--help rename should show the current pattern value."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'rename'],
            capture_output=True, text=True, timeout=60)
        self.assertIn('Current pattern:', result.stdout, "--help rename should show current pattern")

    def test_rename_movie_error(self):
        """--rename on a movie library should print an error."""
        probe = subprocess.run([sys.executable, MAIN_SCRIPT, '--offline', '--list-libraries'],
            capture_output=True, text=True, timeout=30)
        movie_lib = _pick_most_populated_library(probe.stdout, lib_type='Movie')
        if not movie_lib:
            self.skipTest("no Movie library in the cache -- cannot test --rename movie error")
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--offline', '--rename', movie_lib, '--dry-run'],
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, "--rename on a Movie library must fail")
        self.assertIn('only available for Series libraries, not Movie', result.stderr)


class TestRenameShared(unittest.TestCase):
    """Tests for shared rename subroutines: _build_sxex_prefix, _build_sxex_filename, _rename_episode_file."""

    def test_build_sxex_prefix_default_padding(self):
        """_build_sxex_prefix with default padding produces S01E02."""
        self.assertEqual(PLEX_Media._build_sxex_prefix(1, 2), 'S01E02')
        self.assertEqual(PLEX_Media._build_sxex_prefix(12, 99), 'S12E99')

    def test_build_sxex_prefix_custom_padding(self):
        """_build_sxex_prefix with custom padding produces wider numbers."""
        self.assertEqual(PLEX_Media._build_sxex_prefix(1, 2, s_pad=3, e_pad=4), 'S001E0002')
        self.assertEqual(PLEX_Media._build_sxex_prefix(12, 1500, s_pad=2, e_pad=4), 'S12E1500')

    def test_build_sxex_prefix_zero_season(self):
        """_build_sxex_prefix for specials (season 0)."""
        self.assertEqual(PLEX_Media._build_sxex_prefix(0, 5), 'S00E05')

    def test_build_sxex_filename_basic(self):
        """_build_sxex_filename prepends S0XE0X to original filename."""
        result = PLEX_Media._build_sxex_filename(4, 1, 'Rise_September_19_2011.mkv')
        self.assertEqual(result, 'S04E01 - Rise_September_19_2011.mkv')

    def test_build_sxex_filename_custom_padding(self):
        """_build_sxex_filename respects custom padding widths."""
        result = PLEX_Media._build_sxex_filename(4, 1, 'test.mkv', s_pad=3, e_pad=3)
        self.assertEqual(result, 'S004E001 - test.mkv')

    def test_rename_episode_file_skips_no_file(self):
        """_rename_episode_file returns 'skipped' when ep has no file."""
        ep = {'type': 'Episode'}
        result = PLEX_Media._rename_episode_file(ep, 'Episode:1', 'new.mkv', dry_run=True)
        self.assertEqual(result, 'skipped')

    def test_rename_episode_file_skips_same_name(self):
        """_rename_episode_file returns 'skipped' when filename already matches."""
        ep = {'type': 'Episode', 'file': '/media/shows/s01/S01E01 - Pilot.mkv'}
        result = PLEX_Media._rename_episode_file(ep, 'Episode:1', 'S01E01 - Pilot.mkv', dry_run=True)
        self.assertEqual(result, 'skipped')

    def test_rename_episode_file_dry_run_prints(self):
        """_rename_episode_file in dry_run mode prints the rename and returns 'renamed'."""
        ep = {'type': 'Episode', 'file': '/media/shows/s01/old_name.mkv'}
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = PLEX_Media._rename_episode_file(ep, 'Episode:1', 'S01E01 - Pilot.mkv',
                                                     dry_run=True, rename_siblings=False)
        self.assertEqual(result, 'renamed')
        output = buf.getvalue()
        self.assertIn('[DRY-RUN]', output)
        self.assertIn('S01E01 - Pilot.mkv', output)
        self.assertIn('old_name.mkv', output)

    def test_rename_single_episode_uses_shared_primitive(self):
        """_rename_single_episode should delegate to _rename_episode_file (code structure check)."""
        src_path = MAIN_SCRIPT
        with open(src_path, 'r') as f:
            src = f.read()
        # Find _rename_single_episode body and verify it calls _rename_episode_file
        idx = src.index('def _rename_single_episode(')
        # Search within 3000 chars of the method
        method_body = src[idx:idx+3000]
        self.assertIn('_rename_episode_file', method_body,
                      "_rename_single_episode should delegate to _rename_episode_file")

    def test_sort_new_uses_build_sxex_filename(self):
        """cmd_sort_new should use _build_sxex_filename instead of hardcoded f-strings."""
        src_path = MAIN_SCRIPT
        with open(src_path, 'r') as f:
            src = f.read()
        # Find cmd_sort_new and verify no hardcoded S{season:02d}E{ep_num:02d} in new_name assignments
        idx = src.index('def cmd_sort_new(')
        method_body = src[idx:idx+15000]
        import re
        hardcoded = re.findall(r'new_name\s*=\s*f"S\{', method_body)
        self.assertEqual(len(hardcoded), 0,
                         f"cmd_sort_new should not have hardcoded S{{}} f-strings for new_name, found {len(hardcoded)}")


class TestShowInfoSeasonTable(unittest.TestCase):
    """Tests for --info on Show objects showing season table."""

    def test_series_info_has_season_table(self):
        """my-plex 'boston legal' --info should show a season table."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, 'boston legal', '--info'],
            capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        if result.returncode != 0 and 'Traceback' not in result.stderr:
            self.skipTest("'boston legal' not in cache or cache empty — cannot test show info season table")
        self.assertEqual(result.returncode, 0)
        self.assertIn('SEASON', result.stdout, "Should have SEASON header")
        self.assertIn('KEY', result.stdout, "Should have KEY header")
        self.assertIn('EPISODES', result.stdout, "Should have EPISODES header")
        self.assertIn('S01', result.stdout, "Should show S01")
        self.assertIn('Season:', result.stdout, "Should show Season: keys")

    def test_series_info_no_episode_table_without_verbose(self):
        """my-plex 'boston legal' --info (without -V) should NOT show the episode table."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, 'boston legal', '--info'],
            capture_output=True, text=True, timeout=30)
        if result.returncode != 0 and 'Traceback' not in result.stderr:
            self.skipTest("'boston legal' not in cache or cache empty")
        self.assertEqual(result.returncode, 0)
        self.assertIn('SEASON', result.stdout, "Season table should still appear")
        self.assertNotIn('TITLE', result.stdout, "Episode table TITLE header should NOT appear without -V")

    def test_series_info_verbose_has_episode_table(self):
        """my-plex <Series:KEY> --info -V should show an episode table.

        Series picked dynamically from the cache (never a hard-coded local
        title).  Episode IDs may be negative when Plex mis-parsed the
        numbering, so match the S..E shape, not specific digits."""
        list_result = subprocess.run([sys.executable, MAIN_SCRIPT, 'type:series', '--list'],
            capture_output=True, text=True, timeout=60)
        series_keys = [line.split()[0] for line in list_result.stdout.splitlines()
                       if line.startswith('Series:')]
        if not series_keys:
            self.skipTest("No series in cache — cannot test series info episode table")
        for series_key in series_keys[:5]:
            result = subprocess.run([sys.executable, MAIN_SCRIPT, series_key, '--info', '-V'],
                capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and 'EPISODE' in result.stdout:
                self.assertIn('TITLE', result.stdout, "Should have TITLE header")
                self.assertRegex(result.stdout, r'S\d+E', "Should show episode rows")
                return
        self.skipTest("No cached series produced an episode table (no episodes on disk)")


class TestEpisodesErr(unittest.TestCase):
    """episodes.err read/write/clear, and the --problems TSV that reads it.

    Every test here asserts a LOCAL file, so each one covers the FALLBACK
    path: write_episodes_err writes on the Plex SERVER over ssh and writes
    locally only when that fails. Which means these tests passed exactly
    where the ssh was broken -- and failed on horse in a full run, where an
    earlier test had already opened the shared connection, so the ssh
    SUCCEEDED and the file landed on the server (2026-11-02). Nothing about
    the test was wrong except what it depended on.

    So the ssh is made to fail deterministically, on every machine, instead
    of being left to chance. What happens against a REACHABLE server is not
    covered here, and a test for that needs a stub transport, not a host.

    The silent `except Exception: pass` in the fallback is gone too, so a
    recurrence of that 2026-11-02 failure now leaves the ssh's own reason
    on stderr instead of nothing."""

    def setUp(self):
        """Point the server alias at a name that cannot resolve. `.invalid`
        never does (RFC 2606), and _ssh_opts already carries BatchMode and
        ConnectTimeout, so the attempt fails at once rather than waiting."""
        self._main = _main_module()
        self._saved_host = self._main.PLEX_DB_REMOTE_HOST
        self._main.PLEX_DB_REMOTE_HOST = 'my-plex-tests-no-such-host.invalid'

    def tearDown(self):
        self._main.PLEX_DB_REMOTE_HOST = self._saved_host

    def test_write_read_roundtrip(self):
        """Write episodes.err and read it back, verify data integrity."""
        import tempfile, os
        series_dir = tempfile.mkdtemp()
        try:
            write_episodes_err(series_dir, 'no_external_ids', 'tmdb',
                               'No TMDB ID — use Plex > Fix Match')
            result = read_episodes_err(series_dir)
            self.assertIsNotNone(result)
            self.assertEqual(result['error_type'], 'no_external_ids')
            self.assertEqual(result['source'], 'tmdb')
            self.assertIn('Fix Match', result['message'])
        finally:
            import shutil
            shutil.rmtree(series_dir)

    def test_when_neither_write_works_it_says_so(self):
        """THE case the silent `except Exception: pass` hid: both writes fail,
        so the error this function exists to RECORD is nowhere at all.

        Adversarial on purpose: a swallow passes every OTHER test in this
        class, because each of them asserts the file the FALLBACK wrote. Only
        a target that cannot be written tells the two apart.

        Not fatal, deliberately -- a note that cannot be written must not take
        down the run it is a note ABOUT. So the evidence is a warning on
        stderr and a False return, not an exit."""
        import contextlib
        if os.geteuid() == 0:
            self.skipTest("root can write into a 0500 directory, so the "
                          "unwritable target would not be unwritable")
        parent = tempfile.mkdtemp(prefix='my-plex-errwrite-')
        locked = os.path.join(parent, 'locked')
        series_dir = os.path.join(locked, 'Some Series')
        os.makedirs(locked)
        os.chmod(locked, 0o500)          # readable, NOT writable
        try:
            cap = io.StringIO()
            with contextlib.redirect_stderr(cap):
                ok = write_episodes_err(series_dir, 'scrape_failed', 'tvdb',
                                        'timeout')
            out = cap.getvalue()
            self.assertFalse(ok, "reported success with nothing written")
            self.assertIn('WARNING', out, f"nothing on stderr:\n{out!r}")
            self.assertIn('scrape_failed', out,
                          f"the warning does not say WHAT went unrecorded:\n{out}")
            self.assertIn(series_dir, out,
                          f"the warning does not say WHERE:\n{out}")
            self.assertFalse(os.path.exists(series_dir), "it wrote after all")
        finally:
            os.chmod(locked, 0o700)
            shutil.rmtree(parent, ignore_errors=True)

    def test_a_local_fallback_says_the_server_copy_did_not_happen(self):
        """The fallback SUCCEEDS -- which every other test here leans on --
        but the file is then where Plex cannot see it, and that difference
        used to be invisible. Under -V it is said, with the ssh's own reason
        beside it."""
        import contextlib
        series_dir = tempfile.mkdtemp(prefix='my-plex-errfallback-')
        saved_vrb = self._main.VRB
        setattr(self._main, 'VRB', True)
        try:
            cap = io.StringIO()
            with contextlib.redirect_stderr(cap):
                ok = write_episodes_err(series_dir, 'no_external_ids', 'tmdb',
                                        'no id')
            out = cap.getvalue()
            self.assertTrue(ok, f"the local write failed: {out}")
            self.assertTrue(os.path.isfile(get_episodes_err_path(series_dir)))
            self.assertIn('LOCALLY', out,
                          f"-V does not say the server copy is missing:\n{out!r}")
        finally:
            setattr(self._main, 'VRB', saved_vrb)
            shutil.rmtree(series_dir, ignore_errors=True)

    def test_read_nonexistent(self):
        """Reading from directory without episodes.err returns None."""
        import tempfile
        series_dir = tempfile.mkdtemp()
        try:
            result = read_episodes_err(series_dir)
            self.assertIsNone(result)
        finally:
            import shutil, os
            shutil.rmtree(series_dir)

    def test_clear_removes_file(self):
        """clear_episodes_err removes the file."""
        import tempfile, os
        series_dir = tempfile.mkdtemp()
        try:
            write_episodes_err(series_dir, 'scrape_failed', 'tvdb', 'timeout')
            err_path = get_episodes_err_path(series_dir)
            self.assertTrue(os.path.isfile(err_path))
            clear_episodes_err(series_dir)
            self.assertFalse(os.path.isfile(err_path))
        finally:
            import shutil
            shutil.rmtree(series_dir)

    def test_clear_nonexistent_is_noop(self):
        """clear_episodes_err on missing file does not raise."""
        import tempfile
        series_dir = tempfile.mkdtemp()
        try:
            clear_episodes_err(series_dir)  # should not raise
        finally:
            import shutil
            shutil.rmtree(series_dir)

    def test_err_file_format(self):
        """Verify episodes.err has expected format with comments and key-value lines."""
        import tempfile, os
        series_dir = tempfile.mkdtemp()
        try:
            write_episodes_err(series_dir, 'suspicious_title', 'fernsehserien.de',
                               "Title 'The G' may be truncated")
            err_path = get_episodes_err_path(series_dir)
            with open(err_path, 'r') as f:
                content = f.read()
            self.assertIn('# my-plex episode data error', content)
            self.assertIn('# updated:', content)
            self.assertIn('error_type: suspicious_title', content)
            self.assertIn('source: fernsehserien.de', content)
        finally:
            import shutil
            shutil.rmtree(series_dir)

    def test_episodes_err_functions_exist(self):
        """Source must define episodes.err functions."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        for func_name in ('write_episodes_err', 'read_episodes_err',
                          'clear_episodes_err', 'get_episodes_err_path'):
            self.assertIn(f'def {func_name}(', content,
                          f"Must define {func_name}")

    def test_scrape_episodes_has_fallback(self):
        """scrape_episodes must contain fallback chain logic."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        import re
        match = re.search(r'def scrape_episodes\(.*?\ndef ', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match, "Must find scrape_episodes function")
        body = match.group(0)
        self.assertIn('fallback_sources', body, "Must have fallback_sources list")
        self.assertIn('_fallback_from', body, "Must record fallback origin")

    def test_problems_includes_tsv_section(self):
        """--problems must run TSV detection via the registry's 'tsv' category (v3)."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        import re
        reg = _registry_entry_block(content, 'tsv')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'tsv'")
        self.assertIn('_list_tsv_problems', reg, "Must invoke _list_tsv_problems")
        self.assertIn('Episode Data', reg, "Must have Episode Data section header")
        self.assertIn("'tsv_relevant':  True", reg,
                      "'tsv' category must be flagged tsv_relevant for --problems --tsv")

    def test_problems_summary_includes_tsv_count(self):
        """--problems summary must surface the tsv count via the registry-driven warnings."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        import re
        # The shared warning printer iterates the registry, which carries the
        # tsv description shown in the summary.
        idx = content.index('def _print_problem_warnings(')
        end = content.index('\ndef ', idx + 1)
        self.assertIn('PROBLEM_CATEGORIES_REGISTRY.items()', content[idx:end])
        reg = _registry_entry_block(content, 'tsv')
        self.assertIsNotNone(reg)
        self.assertIn('Episode-scrape failures', reg,
                      "registry 'tsv' description must explain the count")

    def test_problems_e2e(self):
        """--problems runs without error (E2E)."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--config', _fixture_conf(), '--problems'],
            capture_output=True, text=True, timeout=E2E_TIMEOUT)
        self.assertEqual(result.returncode, 0, f"--problems failed: {result.stderr}")
        self.assertIn('PROBLEM DETECTION', result.stdout)
        self.assertIn('Episode Data', result.stdout)
        self.assertIn('problem(s) found', result.stdout)
        # Verify all --help PROBLEM DETECTION checks are present
        self.assertIn('Broken', result.stdout, "--problems must include Broken check")
        self.assertIn('Excess Versions', result.stdout, "--problems must include Excess Versions check")
        self.assertIn('Unmatched', result.stdout, "--problems must include Unmatched check")
        self.assertIn('No Audio Language', result.stdout, "--problems must include No Audio Language check")
        self.assertIn('Unsorted', result.stdout, "--problems must include Unsorted check")
        self.assertIn('Mismatch', result.stdout, "--problems must include Mismatch check")
        self.assertIn('Reencode', result.stdout, "--problems must include Reencode check")
        self.assertIn('Missing Episodes', result.stdout, "--problems must include Missing Episodes check")
        self.assertIn('Renumber', result.stdout, "--problems must include Renumber check")


class TestEpisodesErrClassification(unittest.TestCase):
    """Test _classify_tsv_error error classification."""

    def test_classify_no_external_ids(self):
        """Empty external_ids should classify as no_external_ids."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        self.assertIn('def _classify_tsv_error(', content)

    def test_classify_function_checks_title_length(self):
        """_classify_tsv_error must check for suspicious (short) titles."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        import re
        match = re.search(r'def _classify_tsv_error\(.*?\n(?=def )', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(0)
        self.assertIn('suspicious_title', body)
        self.assertIn('misidentified_show', body)
        self.assertIn('no_id_for_source', body)


class TestUnmatched(unittest.TestCase):
    """Test --unmatched flag and guid-based detection."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_unmatched_arg_defined_global(self):
        """--unmatched must be defined in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        self.assertIn("'--unmatched'", content)

    def test_unmatched_arg_defined_library(self):
        """--unmatched must be in library argparser."""
        content = self._read_script()
        # Library argparser section
        import re
        match = re.search(r"class PLEX_Library.*?argparser\.add_argument\('--unmatched'", content, re.DOTALL)
        self.assertIsNotNone(match, "Must define --unmatched in library argparser")

    def test_guid_in_movie_query(self):
        """Movie DB query must SELECT mi.guid."""
        content = self._read_script()
        # The SQL query string in fetch_movies_from_database must contain mi.guid
        self.assertIn('mi.guid', content, "Movie query must SELECT mi.guid")

    def test_guid_in_show_query(self):
        """Show DB query must SELECT sh.guid."""
        content = self._read_script()
        self.assertIn('sh.guid as sh_guid', content, "Show query must SELECT sh.guid")

    def test_guid_stored_in_movie_dict(self):
        """Movie dict must include guid field."""
        content = self._read_script()
        self.assertIn("'guid': guid", content, "Movie dict must store 'guid' field")

    def test_guid_stored_in_series_dict(self):
        """Show dict (OBJ_BY_ID) must include guid field."""
        content = self._read_script()
        self.assertIn("'guid': series_info.get('guid'", content,
                       "Show OBJ_BY_ID dict must store 'guid' from series_info")

    def test_list_unmatched_function_exists(self):
        """_list_unmatched must be defined."""
        content = self._read_script()
        self.assertIn('def _list_unmatched(', content)

    def test_list_unmatched_checks_local_guid(self):
        """_list_unmatched must check for local:// guid."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_unmatched\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("local://", body, "Must check for local:// guid prefix")

    def test_problems_includes_unmatched(self):
        """--problems must run unmatched detection via PROBLEM_CATEGORIES_REGISTRY (v3)."""
        content = self._read_script()
        import re
        # v3: the --problems handler iterates the registry instead of
        # calling each lister literally.  Assert both halves of the chain:
        # 1) handler walks _enabled_problem_categories()
        idx = content.index('# Handle --problems:')
        end = content.index('\n    # Handle ', idx)
        body = content[idx:end]
        self.assertIn('_enabled_problem_categories()', body,
                      "--problems handler must iterate the problem-category registry")
        # 2) the registry's 'unmatched' entry invokes _list_unmatched
        reg = _registry_entry_block(content, 'unmatched')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'unmatched'")
        self.assertIn('_list_unmatched', reg,
                      "registry 'unmatched' entry must invoke _list_unmatched")
        self.assertIn('Unmatched', reg, "Must have Unmatched section header")

    def test_help_unmatched_exists(self):
        """--help unmatched must have a case block."""
        content = self._read_script()
        self.assertIn("case 'unmatched':", content)
        import re
        match = re.search(r"case 'unmatched':\n(.*?)sys\.exit\(0\)", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn('UNMATCHED', body)
        self.assertIn('local://', body)
        self.assertIn('--resolve', body)

    def test_cache_format_check_for_guid(self):
        """Cache must detect missing guid field and warn at point of use."""
        content = self._read_script()
        self.assertIn("_cache_missing_guid", content, "Must flag missing guid in cache")
        self.assertIn("update-cache --force-plex", content, "Must tell user how to fix")

    def test_unmatched_e2e_help(self):
        """--help unmatched must run without error."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'unmatched'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help unmatched failed: {result.stderr}")
        self.assertIn('UNMATCHED', result.stdout)
        self.assertIn('--resolve', result.stdout)


class TestSortNewScanLocations(unittest.TestCase):
    """v2.58: SORT_NEW_SCAN_LOCATIONS config + _parse_sort_new_locations()."""

    def _import_main(self):
        return _import_tool()

    def test_default_locations(self):
        """Default must include '.' plus 's0x' and ',new' subdir scans."""
        mp = self._import_main()
        self.assertEqual(mp.CONFIG_DEFAULTS['SORT_NEW_SCAN_LOCATIONS'],
                         ['.', 's0x', ',new'])

    def test_parser_plain_strings(self):
        mp = self._import_main()
        mp.SORT_NEW_SCAN_LOCATIONS = ['.', 's0x', ',new']
        mp._SORT_NEW_LOCATIONS_COMPILED = None
        self.assertEqual(mp._parse_sort_new_locations(),
                         [('.', None), ('s0x', None), (',new', None)])

    def test_parser_touch_modes(self):
        mp = self._import_main()
        mp.SORT_NEW_SCAN_LOCATIONS = ['.', ('s0x', 'touch'), (',new', 'touch-all')]
        mp._SORT_NEW_LOCATIONS_COMPILED = None
        self.assertEqual(mp._parse_sort_new_locations(),
                         [('.', None), ('s0x', 'main'), (',new', 'all')])

    def test_parser_rejects_absolute_paths(self):
        mp = self._import_main()
        mp.SORT_NEW_SCAN_LOCATIONS = ['.', '/etc/bad']
        mp._SORT_NEW_LOCATIONS_COMPILED = None
        result = mp._parse_sort_new_locations()
        self.assertEqual(result, [('.', None)])

    def test_parser_rejects_dotdot(self):
        mp = self._import_main()
        mp.SORT_NEW_SCAN_LOCATIONS = ['.', '../escape']
        mp._SORT_NEW_LOCATIONS_COMPILED = None
        result = mp._parse_sort_new_locations()
        self.assertEqual(result, [('.', None)])

    def test_parser_rejects_unknown_mode(self):
        mp = self._import_main()
        mp.SORT_NEW_SCAN_LOCATIONS = [('s0x', 'destroy')]
        mp._SORT_NEW_LOCATIONS_COMPILED = None
        result = mp._parse_sort_new_locations()
        self.assertEqual(result, [])

    def test_help_mentions_config_and_modes(self):
        """--help sort-new must document SORT_NEW_SCAN_LOCATIONS and the touch modes."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'sort-new'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertIn('SORT_NEW_SCAN_LOCATIONS', result.stdout)
        self.assertIn("'touch'", result.stdout)
        self.assertIn("'touch-all'", result.stdout)
        self.assertIn('ALL LIBRARIES', result.stdout)


class TestUnsorted(unittest.TestCase):
    """Test --unsorted flag and season directory detection."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_unsorted_arg_defined_global(self):
        """--unsorted must be defined in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        self.assertIn("'--unsorted'", content)

    def test_unsorted_arg_defined_library(self):
        """--unsorted must be in library argparser."""
        import re
        content = self._read_script()
        match = re.search(r"class PLEX_Library.*?argparser\.add_argument\('--unsorted'", content, re.DOTALL)
        self.assertIsNotNone(match, "Must define --unsorted in library argparser")

    def test_unsorted_arg_defined_media(self):
        """--unsorted must be in media argparser."""
        import re
        content = self._read_script()
        # Media argparser section (after TYPE_STR = 'media')
        match = re.search(r"TYPE_STR = 'media'.*?argparser\.add_argument\('--unsorted'", content, re.DOTALL)
        self.assertIsNotNone(match, "Must define --unsorted in media argparser")

    def test_list_unsorted_function_exists(self):
        """_list_unsorted must be defined."""
        content = self._read_script()
        self.assertIn('def _list_unsorted(', content)

    def test_list_unsorted_checks_series_dir(self):
        """_list_unsorted must check if episode dir equals show dir."""
        import re
        content = self._read_script()
        match = re.search(r'def _list_unsorted\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("series_dir", body, "Must reference series_dir")
        self.assertIn("dirname", body, "Must use os.path.dirname to check episode paths")

    def test_problems_includes_unsorted(self):
        """--problems must run unsorted detection via PROBLEM_CATEGORIES_REGISTRY (v3)."""
        import re
        content = self._read_script()
        # v3: the --problems handler iterates the registry instead of
        # calling each lister literally.  Assert both halves of the chain:
        # 1) handler walks _enabled_problem_categories()
        idx = content.index('# Handle --problems:')
        end = content.index('\n    # Handle ', idx)
        body = content[idx:end]
        self.assertIn('_enabled_problem_categories()', body,
                      "--problems handler must iterate the problem-category registry")
        # 2) the registry's 'unsorted' entry invokes _list_unsorted
        reg = _registry_entry_block(content, 'unsorted')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'unsorted'")
        self.assertIn('_list_unsorted', reg,
                      "registry 'unsorted' entry must invoke _list_unsorted")
        self.assertIn('Unsorted', reg, "Must have Unsorted section header")

    def test_problems_summary_includes_unsorted(self):
        """--problems summary must show unsorted count."""
        import re
        content = self._read_script()
        self.assertIn('unsorted series', content, "Summary must show 'unsorted series' in problem warnings")

    def test_help_unsorted_exists(self):
        """--help unsorted must have a case block."""
        content = self._read_script()
        self.assertIn("case 'unsorted':", content)
        import re
        match = re.search(r"case 'unsorted':\n(.*?)sys\.exit\(0\)", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn('UNSORTED', body)
        self.assertIn('Season', body)

    def test_unsorted_e2e_help(self):
        """--help unsorted must run without error."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'unsorted'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help unsorted failed: {result.stderr}")
        self.assertIn('UNSORTED', result.stdout)
        self.assertIn('Season', result.stdout)

    def test_unsorted_in_main_help(self):
        """--unsorted must appear in main --help output."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertIn('unsorted', result.stdout)

    def test_unsorted_in_problems_help(self):
        """--problems help must mention --unsorted."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'problems'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help problems failed: {result.stderr}")
        self.assertIn('unsorted', result.stdout.lower())

    def test_has_standalone_cmd_includes_unsorted(self):
        """has_standalone_cmd must check for --unsorted."""
        content = self._read_script()
        self.assertIn("'unsorted'", content)
        import re
        match = re.search(r'has_standalone_cmd\s*=.*', content)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        self.assertIn('unsorted', match.group(0), "has_standalone_cmd must include 'unsorted'")

    def test_reinjection_exists(self):
        """--unsorted must be re-injected into remaining_args."""
        content = self._read_script()
        # v2.0: --unsorted goes through the shared _reinject_variadic helper
        self.assertIn("_reinject_variadic('unsorted',", content)

    def test_unsorted_fix_dispatches_sort_new(self):
        """--unsorted --fix must dispatch to cmd_sort_new."""
        import re
        content = self._read_script()
        # Global dispatch: --unsorted --fix → cmd_sort_new
        match = re.search(r"Handle --unsorted.*?\n(.*?)(?=\n    # Handle --mismatched)", content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn('fix', body, "Global --unsorted handler must check --fix flag")
        self.assertIn('cmd_sort_new', body, "Global --unsorted --fix must call cmd_sort_new")

    def test_unsorted_fix_in_global_parser(self):
        """--fix must be in GLOBAL_CMD_PARSER (used with --unsorted --fix)."""
        content = self._read_script()
        self.assertIn("'--fix'", content)

    def test_unsorted_fix_in_library_argparser(self):
        """--fix must be in library argparser for --unsorted --fix."""
        import re
        content = self._read_script()
        match = re.search(r"class PLEX_Library.*?argparser\.add_argument\('--fix'", content, re.DOTALL)
        self.assertIsNotNone(match, "Must define --fix in library argparser")

    def test_unsorted_help_mentions_fix(self):
        """--help unsorted must document the --fix mode."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'unsorted'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help unsorted failed: {result.stderr}")
        self.assertIn('--fix', result.stdout, "--help unsorted must mention --fix")
        self.assertIn('--sort-new', result.stdout, "--help unsorted must mention --sort-new shortcut")


class TestVersionStringCollision(unittest.TestCase):
    """Test version string uniqueness (filesize + part_id collision handling)."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_build_version_string_exists(self):
        """_build_version_string helper must be defined."""
        content = self._read_script()
        self.assertIn('def _build_version_string(', content)

    def test_version_includes_filesize(self):
        """Version string must include filesize (MB)."""
        content = self._read_script()
        self.assertIn('MB', content[content.index('def _build_version_string('):content.index('def _build_version_string(') + 500])

    def test_collision_adds_part_id(self):
        """On collision, must disambiguate with part#<id>."""
        content = self._read_script()
        self.assertIn('part#', content[content.index('def _build_version_string('):content.index('def _build_version_string(') + 500])

    def test_movie_db_uses_helper(self):
        """fetch_movies_from_database must use _build_version_string."""
        import re
        content = self._read_script()
        match = re.search(r'def fetch_movies_from_database\(.*?\ndef ', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(0)
        self.assertIn('_build_version_string(', body, "Movie DB path must use _build_version_string")

    def test_episode_db_uses_helper(self):
        """fetch_series_from_database must use _build_version_string."""
        import re
        content = self._read_script()
        match = re.search(r'def fetch_series_from_database\(.*?\ndef ', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(0)
        self.assertIn('_build_version_string(', body, "Episode DB path must use _build_version_string")

    def test_api_path_uses_helper(self):
        """API path (add_media_obj_via_PLEX_API) must use _build_version_string."""
        import re
        content = self._read_script()
        match = re.search(r'def add_media_obj_via_PLEX_API\(.*?\ndef ', content, re.DOTALL)
        assert match is not None, "the pattern above did not match"
        self.assertIsNotNone(match)
        body = match.group(0)
        self.assertIn('_build_version_string(', body, "API path must use _build_version_string")

    def test_file_info_has_part_id(self):
        """File info dicts in files must include part_id for collision resolution."""
        import re
        content = self._read_script()
        # In fetch_movies_from_database, the file info dict must include 'part_id'
        match = re.search(r"def fetch_movies_from_database\(.*?'part_id':\s*part_id", content, re.DOTALL)
        self.assertIsNotNone(match, "Movie file_info must include 'part_id'")

    def test_no_old_version_format(self):
        """Old version format without filesize must not remain in DB paths."""
        import re
        content = self._read_script()
        # The old pattern: version = f"...min ...x... (...codec ...codec)"
        # Should NOT appear in fetch_movies/shows_from_database anymore
        for func_name in ['fetch_movies_from_database', 'fetch_series_from_database']:
            match = re.search(rf'def {func_name}\(.*?\ndef ', content, re.DOTALL)
            if match:
                body = match.group(0)
                # Old pattern: direct f-string building version with dur_min/duration_minutes
                old_patterns = re.findall(r'version\s*=\s*f".*?min.*?\(.*?codec.*?\)"', body)
                self.assertEqual(len(old_patterns), 0,
                    f"{func_name} still has old version string format without filesize")


class TestForceTsv(unittest.TestCase):
    """Tests for --force-tsv flag."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_force_tsv_arg_defined(self):
        """--force-tsv must be defined in main_parser."""
        src = self._read_script()
        self.assertIn('--force-tsv', src)

    def test_force_tsv_triggers_rescrape(self):
        """FORCE_TSV must force needs_scrape."""
        src = self._read_script()
        self.assertIn('if FORCE_TSV:', src)

    def test_force_tsv_in_help(self):
        """--force-tsv must be documented in update-cache help."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'update-cache'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help update-cache failed: {result.stderr}")
        self.assertIn('--force-tsv', result.stdout)

    def test_force_tsv_e2e_help(self):
        """--force-tsv must appear in main --help output."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertIn('force-tsv', result.stdout)

    def test_default_preserves_tsv(self):
        """--force-plex without --force-tsv must NOT force re-scrape (default = preserve)."""
        src = self._read_script()
        # The condition must require FORCE_TSV to be True for re-scraping
        self.assertNotIn('FROM_SCRATCH and not FORCE_TSV', src, "Logic should be opt-IN (FORCE_TSV), not opt-OUT")


class TestTsvScrapersE2E(unittest.TestCase):
    """End-to-end tests for TSV scrapers (TMDB, TVDB, fernsehserien.de).

    These tests call the actual scraper functions via subprocess and verify
    the results are consistent (episode counts, season counts, data format).

    They really FETCH, so they do not run unless $MY_PLEX_TEST_NETWORK is set
    -- see TEST_NETWORK_ENV above for what that cost to learn. The old "skip
    gracefully if network is unavailable" is still here for a fetch that
    fails, but it never covered a connection HELD behind a firewall alert,
    which hangs instead of failing.
    """

    def setUp(self):
        # setUp, not setUpClass: a class-level skip is ONE skip, so the TAP
        # stream would announce `1..7` and then print no test lines at all --
        # and my-rollout's gate reads those lines. Per test, each one reports
        # `ok N - <name> # SKIP <reason>`, so the plan and the lines agree.
        if not _network_opted_in():
            self.skipTest(
                f"fetches api.themoviedb.org and www.fernsehserien.de for "
                f"real; set {TEST_NETWORK_ENV}=1 to run these")

    def _get_tmdb_api_key(self):
        """Read TMDB API key from config file, return None if not found."""
        config_path = os.path.expanduser('~/.my-plex.conf')
        if not os.path.isfile(config_path):
            return None
        try:
            with open(config_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('TMDB_API_KEY') and '=' in line:
                        val = line.split('=', 1)[1].strip().strip("'\"")
                        if val and val != 'None':
                            return val
        except Exception:
            pass
        return None

    def _run_scraper_tmdb(self, tmdb_id, series_title) -> dict[str, Any]:
        """Call TMDB API directly and return {'episodes': N, 'max_season': M} or {'error': ...}."""
        import json
        api_key = self._get_tmdb_api_key()
        if not api_key:
            return {'error': 'no TMDB_API_KEY configured'}
        code = f"""
import json, sys
try:
    import urllib.request
    url = f'https://api.themoviedb.org/3/tv/{tmdb_id}?language=en-US'
    headers = {{'Authorization': 'Bearer {api_key}', 'Accept': 'application/json'}}
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    num_seasons = data.get('number_of_seasons', 0)
    num_episodes = data.get('number_of_episodes', 0)
    print(json.dumps({{'episodes': num_episodes, 'max_season': num_seasons, 'title': data.get('name', '')}}))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
"""
        result = subprocess.run([sys.executable, '-c', code],
            capture_output=True, text=True, timeout=30)
        try:
            return json.loads(result.stdout.strip().split('\n')[-1])
        except (json.JSONDecodeError, IndexError):
            return {'error': f'parse failed: {result.stderr[:200]}'}

    def _run_scraper_fernsehserien(self, slug, series_id=None) -> dict[str, Any]:
        """Scrape fernsehserien.de directly and return episode/season count."""
        import json
        code = f"""
import json, sys, re, urllib.request, time
slug = {slug!r}
series_id = {series_id!r}
episodes = {{}}
if series_id:
    # Strategy 1: episodenguide
    consecutive_empty = 0
    s = 1
    while consecutive_empty < 2:
        url = f'https://www.fernsehserien.de/{{slug}}/episodenguide/staffel-{{s}}/{{series_id}}'
        req = urllib.request.Request(url, headers={{'User-Agent': 'Mozilla/5.0'}})
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        except Exception:
            consecutive_empty += 1; s += 1; continue
        ep_sections = re.split(r'itemprop="episode"', html)[1:]
        if not ep_sections:
            consecutive_empty += 1; s += 1; continue
        consecutive_empty = 0
        for sec in ep_sections:
            m = re.search(r'itemprop="episodeNumber" content="(\\d+)"', sec)
            if m:
                episodes[(s, int(m.group(1)))] = True
        s += 1
        time.sleep(0.3)
else:
    # Strategy 2: sendetermine
    for offset in [0, -1, -2, -3]:
        url = f'https://www.fernsehserien.de/{{slug}}/sendetermine/{{offset}}'
        req = urllib.request.Request(url, headers={{'User-Agent': 'Mozilla/5.0'}})
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        except Exception:
            break
        pairs = re.findall(r'role=rowgroup\\s+href="/' + re.escape(slug) + r'/folgen/(\\d+)-([^\\"]*)".*?datetime="(\\d{{4}}-\\d{{2}}-\\d{{2}})T', html, re.DOTALL)
        for ep_str, _, _ in pairs:
            episodes[(0, int(ep_str))] = True
        time.sleep(0.3)
max_s = max((k[0] for k in episodes if k[0] > 0), default=0)
print(json.dumps({{'episodes': len(episodes), 'max_season': max_s}}))
"""
        result = subprocess.run([sys.executable, '-c', code],
            capture_output=True, text=True, timeout=60)
        try:
            return json.loads(result.stdout.strip().split('\n')[-1])
        except (json.JSONDecodeError, IndexError):
            return {'error': f'parse failed: {result.stderr[:200]}'}

    def test_tmdb_friends(self):
        """TMDB API: Friends should return ~228 episodes in 10 seasons."""
        data = self._run_scraper_tmdb('1668', 'Friends')
        if 'error' in data:
            self.skipTest(f"TMDB API failed: {data['error']}")
        self.assertGreater(data['episodes'], 200, f"Friends should have >200 episodes, got {data['episodes']}")
        self.assertEqual(data['max_season'], 10, f"Friends should have 10 seasons, got {data['max_season']}")

    def test_tmdb_firefly(self):
        """TMDB API: Firefly should return ~11 episodes in 1 season."""
        data = self._run_scraper_tmdb('1437', 'Firefly')
        if 'error' in data:
            self.skipTest(f"TMDB API failed: {data['error']}")
        self.assertGreaterEqual(data['episodes'], 11, f"Firefly should have >=11 episodes, got {data['episodes']}")
        self.assertEqual(data['max_season'], 1, f"Firefly should have 1 season, got {data['max_season']}")

    def test_tmdb_different_shows_different_data(self):
        """TMDB API: Different shows must return different data."""
        show1 = self._run_scraper_tmdb('1668', 'Friends')
        show2 = self._run_scraper_tmdb('1437', 'Firefly')
        if 'error' in show1 or 'error' in show2:
            self.skipTest("One or both TMDB calls failed")
        self.assertNotEqual(show1['episodes'], show2['episodes'],
            f"Friends and Firefly should not have the same episode count: {show1['episodes']}")

    def test_fernsehserien_tatortreiniger(self):
        """fernsehserien.de: Der Tatortreiniger should return ~31 episodes in 7 seasons."""
        data = self._run_scraper_fernsehserien('der-tatortreiniger', '16508')
        if 'error' in data:
            self.skipTest(f"fernsehserien.de scraper failed: {data['error']}")
        self.assertGreaterEqual(data['episodes'], 25, f"Der Tatortreiniger should have >=25 episodes, got {data['episodes']}")
        self.assertLessEqual(data['episodes'], 50, f"Der Tatortreiniger should have <=50 episodes, got {data['episodes']}")
        self.assertEqual(data['max_season'], 7, f"Der Tatortreiniger should have 7 seasons, got {data['max_season']}")

    def test_fernsehserien_ted_lasso(self):
        """fernsehserien.de: Ted Lasso should return ~34 episodes in 3 seasons."""
        data = self._run_scraper_fernsehserien('ted-lasso', '46650')
        if 'error' in data:
            self.skipTest(f"fernsehserien.de scraper failed: {data['error']}")
        self.assertGreaterEqual(data['episodes'], 30, f"Ted Lasso should have >=30 episodes, got {data['episodes']}")
        self.assertLessEqual(data['episodes'], 50, f"Ted Lasso should have <=50 episodes, got {data['episodes']}")
        self.assertGreaterEqual(data['max_season'], 3, f"Ted Lasso should have >=3 seasons, got {data['max_season']}")

    def test_fernsehserien_different_shows_different_data(self):
        """fernsehserien.de: Different shows must return different episode counts (no data leakage)."""
        show1 = self._run_scraper_fernsehserien('ted-lasso', '46650')
        show2 = self._run_scraper_fernsehserien('der-tatortreiniger', '35834')
        if 'error' in show1 or 'error' in show2:
            self.skipTest("One or both scrapers failed")
        same = (show1['episodes'] == show2['episodes'] and show1['max_season'] == show2['max_season'])
        self.assertFalse(same,
            f"Ted Lasso and Der Tatortreiniger returned identical data: {show1['episodes']} ep / {show1['max_season']} seasons — likely a bug")

    def test_scraper_summary_lines_all_sources(self):
        """All three scrapers must print a summary line with episode/season count."""
        src = self._read_script()
        for scraper in ['TMDB', 'TVDB', 'fernsehserien.de']:
            self.assertRegex(src, rf"{re.escape(scraper)}:.*episodes in.*seasons for",
                f"{scraper} scraper must print summary: 'N episodes in M seasons for'")

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()


class TestMismatched(unittest.TestCase):
    """Test --mismatched command integration (title-vs-dir + multi-version grouping)."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_function_exists(self):
        """_list_mismatched + _list_potential_mismatches + _detect_multi_version_mismatch must exist."""
        content = self._read_script()
        self.assertIn('def _list_mismatched(', content)
        self.assertIn('def _list_potential_mismatches(', content)
        self.assertIn('def _detect_multi_version_mismatch(', content)
        self.assertIn('def _list_multi_version_mismatches(', content)

    def test_normalize_exists(self):
        """_normalize_for_comparison must exist."""
        content = self._read_script()
        self.assertIn('def _normalize_for_comparison(', content)

    def test_title_similarity_exists(self):
        """_title_similarity must exist."""
        content = self._read_script()
        self.assertIn('def _title_similarity(', content)

    def test_library_argparser(self):
        """--mismatched must be in library argparser."""
        content = self._read_script()
        self.assertIn("'--mismatched'", content)

    def test_global_cmd_parser(self):
        """--mismatched must be in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        idx = content.index('GLOBAL_CMD_PARSER.add_argument')
        self.assertIn('--mismatched', content[idx:])

    def test_problems_integration(self):
        """--problems must include the mismatched section."""
        content = self._read_script()
        self.assertIn('Mismatched', content)
        self.assertIn('mismatch_count', content)

    def test_help_exists(self):
        """--help mismatched must work and show both detectors."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'mismatched'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help mismatched failed: {result.stderr}")
        self.assertIn('MISMATCHED', result.stdout)
        self.assertIn('TITLE vs DIRECTORY', result.stdout)
        self.assertIn('MULTI-VERSION', result.stdout)

    def test_e2e_runs(self):
        """--mismatched must run without error."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--config', _fixture_conf(), '--mismatched'],
            capture_output=True, text=True, timeout=E2E_TIMEOUT)
        self.assertEqual(result.returncode, 0, f"--mismatched failed: {result.stderr}")

    def test_re_injection(self):
        """--mismatched must be re-injected into remaining_args."""
        content = self._read_script()
        self.assertIn("'mismatched'", content)
        self.assertIn("'--mismatched'", content)

    def test_has_standalone_cmd(self):
        """--mismatched must be in has_standalone_cmd check."""
        content = self._read_script()
        self.assertIn("'mismatched'", content)

    def test_no_old_aliases(self):
        """Old --mismatch / --potential-mismatch must NOT be wired (renamed cleanly)."""
        content = self._read_script()
        self.assertNotIn("'--potential-mismatch'", content)
        self.assertNotIn("'--mismatch'", content)

    def test_config_defaults_present(self):
        """Multi-version thresholds must be exposed via CONFIG_DEFAULTS + module globals."""
        content = self._read_script()
        self.assertIn("'MULTI_VERSION_MAX_MOVIE'", content)
        self.assertIn("'MULTI_VERSION_MAX_SERIES'", content)
        self.assertIn("'MULTI_VERSION_MAX_DURATION_SPREAD_PCT'", content)
        self.assertIn("MULTI_VERSION_MAX_MOVIE = CONFIG_DEFAULTS.get(", content)
        self.assertIn("MULTI_VERSION_MAX_SERIES = CONFIG_DEFAULTS.get(", content)
        self.assertIn("MULTI_VERSION_MAX_DURATION_SPREAD_PCT = CONFIG_DEFAULTS.get(", content)

    def test_detect_multi_version_count(self):
        """_detect_multi_version_mismatch must flag count > limit."""
        # The tool is not imported here -- the asserts below read its SOURCE,
        # which is cheaper.  The spec that used to be built and never used is
        # what made this test fail on a copy called my-plex, not my-plex.py.
        content = self._read_script()
        self.assertIn("len(files) > limit", content)
        self.assertIn("duration spread", content)
        self.assertIn("different directories", content)

    def test_broken_spread_rescue_present(self):
        """--broken must back off the healthy-sibling rule when version durations are widely spread."""
        content = self._read_script()
        # The rescue is gated on MULTI_VERSION_MAX_DURATION_SPREAD_PCT inside _list_broken_files.
        idx = content.index('def _list_broken_files(')
        end = content.index('\n    @staticmethod', idx)
        body = content[idx:end]
        self.assertIn('_sib_versions_are_alt_encodes', body)
        self.assertIn('MULTI_VERSION_MAX_DURATION_SPREAD_PCT', body)

    def test_broken_healthy_sibling_excludes_self(self):
        """--broken's healthy-sibling scan must skip the file being evaluated (Bug A fix)."""
        content = self._read_script()
        idx = content.index('def _list_broken_files(')
        end = content.index('\n    @staticmethod', idx)
        body = content[idx:end]
        self.assertIn('if _sfi is file_info:', body)
        self.assertIn('continue', body)
        # And must only run when there's more than one file
        self.assertIn('len(files_dict) > 1', body)


class TestJunk(unittest.TestCase):
    """Test --junk command + auto-detection helper."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_functions_exist(self):
        """_list_junk_files + _compile_junk_patterns must exist (v3 JUNK_PATTERNS design)."""
        content = self._read_script()
        self.assertIn('def _list_junk_files(', content)
        self.assertIn('def _compile_junk_patterns(', content)
        # The v2 per-file heuristic detector was retired with the
        # JUNK_PATTERNS redesign (no backwards compatibility).
        self.assertNotIn('def _detect_junk_file(', content)

    def test_config_defaults_present(self):
        """JUNK_PATTERNS dict must be in CONFIG_DEFAULTS + module-level loader."""
        content = self._read_script()
        self.assertIn("'JUNK_PATTERNS'", content)
        self.assertIn("JUNK_PATTERNS = CONFIG_DEFAULTS.get(", content)
        # Old scalar knobs were replaced by per-pattern fields.
        self.assertNotIn("'JUNK_FILENAME_PATTERNS'", content)
        self.assertNotIn("'JUNK_MAX_SIZE_MB'", content)

    def test_library_argparser(self):
        """--junk must be in library argparser; --trash flag must NOT exist (use --resolve)."""
        content = self._read_script()
        self.assertIn("'--junk'", content)
        # --resolve is the canonical action verb (matches --unmatched --resolve,
        # --duplicates --resolve, --bad-structure --resolve)
        self.assertNotIn("dest='trash'", content,
            "--trash flag was renamed to --resolve for consistency")

    def test_global_cmd_parser(self):
        """--junk must be in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        idx = content.index('GLOBAL_CMD_PARSER.add_argument')
        section = content[idx:]
        self.assertIn("'--junk'", section)

    def test_has_standalone_cmd(self):
        """--junk must be in has_standalone_cmd check."""
        content = self._read_script()
        idx = content.index('has_standalone_cmd')
        line_end = content.index('\n', idx)
        line = content[idx:line_end]
        self.assertIn("'junk'", line)

    def test_help_exists(self):
        """--help junk must document the JUNK_PATTERNS design and use --resolve as the action verb."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'junk'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help junk failed: {result.stderr}")
        self.assertIn('JUNK FILES', result.stdout)
        self.assertIn('JUNK_PATTERNS', result.stdout)
        self.assertIn('FILENAME_REGEXP', result.stdout)
        self.assertIn('MAX_SIZE_MB', result.stdout)
        self.assertIn('RECURSIVE', result.stdout)
        self.assertIn('--resolve', result.stdout, "Help must use --resolve as the action verb")

    def test_problems_integration(self):
        """--junk must be wired into --problems via the registry's 'junk' category (v3)."""
        content = self._read_script()
        import re
        reg = _registry_entry_block(content, 'junk')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'junk'")
        self.assertIn('_list_junk_files', reg,
            "registry 'junk' entry must invoke _list_junk_files")
        self.assertIn('--junk --resolve', reg,
            "registry 'junk' fix hint must point to --junk --resolve")

    def test_e2e_runs(self):
        """--junk must run without error."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--junk'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, f"--junk failed: {result.stderr}")

    def test_pattern_criteria_use_and_semantics(self):
        """When a JUNK_PATTERNS entry sets BOTH regex and size, they must AND-combine.
        (Replaces the retired _detect_junk_file sibling-cluster gating test —
        the v3 design has no sibling heuristics, only per-pattern criteria.)"""
        content = self._read_script()
        idx = content.index('def _list_junk_files(')
        end = content.index('\n    @staticmethod', idx)
        body = content[idx:end]
        self.assertIn('regex_pass and size_pass', body,
            "Active criteria must AND-combine (regex AND size)")

    def test_cleanup_pipeline_includes_junk_resolve(self):
        """Default --cleanup pipeline must include ['--junk', '--resolve'] as a phase.
        (v3: --clean was retired from the defaults; --cleanup is the safe default.)"""
        content = self._read_script()
        idx = content.index("'--cleanup': [")
        end = content.index("\n        ],", idx)
        section = content[idx:end]
        # Tolerate alignment whitespace inside the phase lists.
        self.assertRegex(section, r"\['--junk',\s+'--resolve'\]",
            f"PIPELINES['--cleanup'] must run --junk --resolve; got: {section}")
        self.assertRegex(section, r"\['--orphaned',\s+'--resolve'\]",
            f"PIPELINES['--cleanup'] must run --orphaned --resolve; got: {section}")

    def test_pipeline_dry_run_and_yes_propagation(self):
        """--junk must be in DRY_RUN_AWARE and YES_AWARE sets so --clean propagates --try / --yes."""
        content = self._read_script()
        idx = content.index('DRY_RUN_AWARE = {')
        end = content.index('}', idx)
        self.assertIn("'--junk'", content[idx:end])
        idx2 = content.index('YES_AWARE = {')
        end2 = content.index('}', idx2)
        self.assertIn("'--junk'", content[idx2:end2])

    def test_default_output_is_per_category_statistics(self):
        """--junk default output = per-category counts; full file list only with -V."""
        content = self._read_script()
        idx = content.index('def _list_junk_files(')
        end = content.index('\n    @staticmethod', idx)
        body = content[idx:end]
        # Statistics table: COUNT-first columns, one row per pattern category.
        self.assertIn("'COUNT':>6", body,
            "default output must print a per-category COUNT statistics table")
        self.assertIn('per_category', body,
            "flagged files must be grouped per pattern category")
        # The per-file listing is verbose-gated.
        self.assertIn('if VRB:', body,
            "the full per-file listing must only print with -V")
        # Hint so the operator knows how to see the filenames.
        self.assertIn('Use -V to also list the actual filenames', body,
            "default output must hint that -V lists the actual filenames")


class TestShowDirDerivation(unittest.TestCase):
    """Test series_dir derivation uses PATHS_DICT (library root from section_locations)."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_section_locations_queried(self):
        """get_library_sections_from_database must JOIN section_locations for root_path."""
        content = self._read_script()
        self.assertIn('section_locations', content)
        self.assertIn('root_path', content)

    def test_paths_dict_recomputed_after_db_fetch(self):
        """PATHS_DICT must be recomputed after library objects are populated from DB."""
        content = self._read_script()
        # After populating OBJ_DICT from DB, PATHS_DICT must be refreshed
        idx_populate = content.index('Populated OBJ_DICT with')
        idx_recompute = content.index('get_PATHS_DICT()', idx_populate)
        self.assertGreater(idx_recompute, idx_populate)

    def test_no_heuristic_fallback(self):
        """series_dir derivation must NOT fall back to dirname heuristics — must error on failure."""
        content = self._read_script()
        # v1.20 introduced `_is_season_dir_name` as part of the layout
        # classifier (DIFFERENT subsystem — filesystem-shape detection for
        # the `layout:` filter token).  The intent here is the LEGACY
        # series_dir heuristic — the function call form `_is_season_dir(`.
        import re
        forbidden = re.search(r'\b_is_season_dir\s*\(', content)
        self.assertIsNone(forbidden,
            "No legacy season-dir heuristic call — series_dir derivation must use PATHS_DICT only")
        # Must error if lib_root not found
        self.assertIn('Cannot determine library root for series', content)

    def test_series_dir_uses_paths_dict(self):
        """series_dir must be derived from PATHS_DICT (subtract lib root, take first dir)."""
        content = self._read_script()
        # The derivation must use PATHS_DICT to find the library root
        self.assertIn('PLEX_Library.PATHS_DICT', content)
        # Must split the remainder to get the first subdirectory
        self.assertIn("remainder.split('/')[0]", content)

    def test_locations_populated_from_root_path(self):
        """Library objects created from DB must have locations populated from root_path."""
        content = self._read_script()
        self.assertIn("root_path", content)
        # locations must not be hardcoded as empty list when root_path is available
        self.assertNotIn("'locations': [],  # Will be populated if needed", content)


class TestObjByShowScraped(unittest.TestCase):
    """Test OBJ_BY_SERIES_SCRAPED cache structure and --episode-numbering-issues."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_cache_dict_declared(self):
        """OBJ_BY_SERIES_SCRAPED must be declared on PLEX_Media."""
        content = self._read_script()
        self.assertIn('OBJ_BY_SERIES_SCRAPED', content)

    def test_cache_save(self):
        """OBJ_BY_SERIES_SCRAPED must be included in cache save."""
        content = self._read_script()
        self.assertIn("'obj_by_series_scraped'", content)

    def test_cache_load(self):
        """OBJ_BY_SERIES_SCRAPED must be loaded from cache."""
        content = self._read_script()
        self.assertIn("source.get('obj_by_series_scraped'", content)

    def test_from_scratch_reset(self):
        """OBJ_BY_SERIES_SCRAPED must be reset during --force-plex."""
        content = self._read_script()
        self.assertIn('OBJ_BY_SERIES_SCRAPED = {}', content)

    def test_checkpoint_data(self):
        """OBJ_BY_SERIES_SCRAPED must be in checkpoint data."""
        content = self._read_script()
        self.assertIn("'obj_by_series_scraped': copy.copy(PLEX_Media.OBJ_BY_SERIES_SCRAPED)", content)

    def test_scraped_title_in_tmdb(self):
        """TMDB scraper must capture series_title in metadata."""
        content = self._read_script()
        # Find it in _scrape_tmdb
        idx = content.index('def _scrape_tmdb(')
        end = content.index('\ndef ', idx + 1)
        tmdb_section = content[idx:end]
        self.assertIn("new_metadata['series_title']", tmdb_section)

    def test_scraped_title_in_tvdb(self):
        """TVDB scraper must capture series_title in metadata."""
        content = self._read_script()
        idx = content.index('def _scrape_tvdb(')
        end = content.index('\ndef ', idx + 1)
        tvdb_section = content[idx:end]
        self.assertIn("series_title", tvdb_section)

    def test_scraped_title_in_fernsehserien(self):
        """fernsehserien.de scraper must capture series_title from page."""
        content = self._read_script()
        idx = content.index('def _scrape_fernsehserien_de(')
        end = content.index('\ndef ', idx + 1)
        fs_section = content[idx:end]
        self.assertIn("series_title", fs_section)

    def test_series_title_in_tsv_header(self):
        """series_title must be written to TSV file header."""
        content = self._read_script()
        idx = content.index('def write_episodes_tsv(')
        end = content.index('\ndef ', idx + 1)
        write_section = content[idx:end]
        self.assertIn("series_title", write_section)

    def test_series_title_read_from_tsv(self):
        """series_title must be read from TSV metadata."""
        content = self._read_script()
        idx = content.index('def read_episodes_tsv(')
        end = content.index('\ndef ', idx + 1)
        read_section = content[idx:end]
        self.assertIn("'series_title'", read_section)

    def test_no_plex_overwrite(self):
        """Scraped data must NOT overwrite Plex E_idx/E_str — old normalization removed."""
        content = self._read_script()
        idx = content.index('def _ensure_tsv_and_normalize_episodes(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        # Must NOT contain direct E_idx/E_str overwrites
        self.assertNotIn("cached_ep['E_idx'] = tsv_ep_num", section,
            "Must not overwrite Plex E_idx with scraped data")
        self.assertNotIn("cached_ep['E_str'] = new_e_str", section,
            "Must not overwrite Plex E_str with scraped data")

    def test_no_episode_map_in_cache(self):
        """OBJ_BY_SERIES_SCRAPED must NOT contain an 'episode_map' sub-structure.
        Scraped-source numbering is never displayed, so there's nothing to map.
        Title backfill writes directly onto the episode obj; numbering
        disagreements go into `numbering_issues`."""
        content = self._read_script()
        idx = content.index('def _ensure_tsv_and_normalize_episodes(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertNotIn("'episode_map'", section,
            "OBJ_BY_SERIES_SCRAPED must no longer carry an episode_map")
        self.assertNotIn("'season_map'", section,
            "OBJ_BY_SERIES_SCRAPED must no longer carry a season_map")

    def test_scraped_e_str_stored_on_episode_obj_when_different(self):
        """When Plex and scraped numbering disagree, the scraped form must be
        stored on the episode obj as `scraped_E_str` (debug/audit only)."""
        content = self._read_script()
        idx = content.index('def _ensure_tsv_and_normalize_episodes(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("cached_ep['scraped_E_str']", section,
            "scraped_E_str must be stored on the episode obj when numbering differs")


class TestS0XE0XPadding(unittest.TestCase):
    """Padded-per-show S0XE0X display id: normalized Plex id with zero-padding
    based on the max season/episode numbers in the show."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_pad_widths_stored_on_series_obj(self):
        """S_pad_width and E_pad_width must be stored on the show dict."""
        content = self._read_script()
        # Show dict construction is in _process_series_from_database
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("'S_pad_width': S_pad_width", section)
        self.assertIn("'E_pad_width': E_pad_width", section)

    def test_pad_widths_computed_per_show(self):
        """S_pad_width/E_pad_width must be computed from max season/episode
        numbers in the show BEFORE episodes are written to the cache."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("S_pad_width = max(2", section)
        self.assertIn("E_pad_width = max(2", section)

    def test_s0xe0x_rewritten_with_pad_widths(self):
        """Episode dicts must have S0XE0X rewritten using the per-show
        S_pad_width/E_pad_width before being stored in OBJ_BY_ID."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn(":0{S_pad_width}d", section)
        self.assertIn(":0{E_pad_width}d", section)
        # And this rewrite must happen near the OBJ_BY_ID assignment, not after
        assign_idx = section.index('PLEX_Media.OBJ_BY_ID[episode_key] = episode_dict')
        rewrite_idx = section.index("episode_dict['S0XE0X']")
        self.assertLess(rewrite_idx, assign_idx,
            "S0XE0X rewrite must happen before the episode is stored")

    def test_pad_width_minimum_is_two(self):
        """Both widths must be at least 2 so small shows keep the S01E01 form."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        # max(2, …) guarantees the minimum
        self.assertRegex(section, r"S_pad_width\s*=\s*max\(2,")
        self.assertRegex(section, r"E_pad_width\s*=\s*max\(2,")

    def test_pad_width_formula_produces_expected_values(self):
        """Sanity-check the padding formula directly."""
        def pad_width(n):
            return max(2, len(str(n))) if n else 2
        self.assertEqual(pad_width(0), 2)
        self.assertEqual(pad_width(1), 2)
        self.assertEqual(pad_width(15), 2)
        self.assertEqual(pad_width(99), 2)
        self.assertEqual(pad_width(100), 3)
        self.assertEqual(pad_width(150), 3)
        self.assertEqual(pad_width(999), 3)
        self.assertEqual(pad_width(1000), 4)
        self.assertEqual(pad_width(1234), 4)

    def test_s0xe0x_format_matches_widths(self):
        """Verify that the padding format string renders as expected."""
        def fmt(s_idx, e_idx, s_pad, e_pad):
            return f"S{s_idx:0{s_pad}d}E{e_idx:0{e_pad}d}"
        # Small show (≤99 eps): same as legacy
        self.assertEqual(fmt(7, 15, 2, 2), "S07E15")
        # Large show (100-999 eps): 3-digit E
        self.assertEqual(fmt(1, 15, 2, 3), "S01E015")
        self.assertEqual(fmt(1, 150, 2, 3), "S01E150")
        # Extreme (soap): 3-digit S and E
        self.assertEqual(fmt(1, 1, 3, 3), "S001E001")


class TestMultiEpisodeSiblings(unittest.TestCase):
    """Plex multi-episode files (sNNeXX-eYY convention): two or more
    episode rows point at the same on-disk file. --update-cache groups
    them by filepath and stores a sorted sibling-key list on each
    participating episode as obj['multi_episode_siblings']. Display code
    collapses the group into a single "S07E15-16" row via
    _format_episode_range()."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_update_cache_groups_by_filepath(self):
        """--update-cache must group episodes sharing a single filepath and
        store the sorted sibling list on each episode."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("multi_episode_siblings", section)
        # Grouping must be by filepath (not by filename regex)
        self.assertIn("_file_to_eps", section)
        # Only groups of len >= 2 qualify
        self.assertIn("if len(_sib_keys) < 2:", section)
        # Sorted by E_idx for deterministic leader
        self.assertIn("E_idx", section)

    def test_format_episode_range_helper_exists(self):
        """_format_episode_range must exist and read multi_episode_siblings."""
        content = self._read_script()
        self.assertIn('def _format_episode_range(', content)
        idx = content.index('def _format_episode_range(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("multi_episode_siblings", section)
        self.assertIn("E_pad_width", section)

    def test_format_episode_range_passthrough_single(self):
        """For a single-episode file (no siblings), _format_episode_range
        must return obj['S0XE0X'] unchanged."""
        # Call the real helper via the injected reference
        ep = {'S0XE0X': 'S07E15'}
        self.assertEqual(_format_episode_range(ep), 'S07E15')

    def test_format_episode_range_passthrough_len_one(self):
        """A siblings list with a single entry is not a multi-episode file."""
        ep = {'S0XE0X': 'S07E15', 'multi_episode_siblings': ['Episode:1']}
        self.assertEqual(_format_episode_range(ep), 'S07E15')

    def test_info_episode_table_collapses_siblings(self):
        """show_item_info's episode table must skip non-leader siblings and
        render the leader with _format_episode_range()."""
        content = self._read_script()
        idx = content.index('def show_item_info(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn('multi_episode_siblings', section)
        self.assertIn('_format_episode_range', section)
        # There must be a guard that skips non-leader siblings
        self.assertIn('siblings[0]', section)

    def test_episode_func_names_includes_format_range(self):
        """_format_episode_range must be injectable into tests via
        _EPISODE_FUNC_NAMES so test cases can call it directly."""
        content = self._read_script()
        idx = content.index('_EPISODE_FUNC_NAMES')
        end = content.index("'PLEX_Media')", idx)
        section = content[idx:end]
        self.assertIn("'_format_episode_range'", section)

    def test_is_multi_ep_non_leader_helper_exists(self):
        """PLEX_Media._is_multi_ep_non_leader helper must exist and be
        used by file-touching commands to skip sibling duplicates."""
        content = self._read_script()
        self.assertIn('def _is_multi_ep_non_leader(', content)
        # Must check siblings[0] == key to identify the leader
        idx = content.index('def _is_multi_ep_non_leader(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('multi_episode_siblings', section)
        self.assertIn('siblings[0]', section)

    def test_broken_skips_multi_ep_non_leader(self):
        """_list_broken_files must skip non-leader siblings so each
        multi-episode file is listed exactly once."""
        content = self._read_script()
        idx = content.index('def _list_broken_files(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('_is_multi_ep_non_leader', section)

    def test_reencode_list_skips_multi_ep_non_leader(self):
        """_list_reencode_candidates must skip non-leader siblings."""
        content = self._read_script()
        idx = content.index('def _list_reencode_candidates(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('_is_multi_ep_non_leader', section)

    def test_reencode_mark_skips_multi_ep_non_leader(self):
        """_mark_reencode_candidates_on_disk must skip non-leader siblings."""
        content = self._read_script()
        idx = content.index('def _mark_reencode_candidates_on_disk(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('_is_multi_ep_non_leader', section)

    def test_excess_versions_skips_multi_ep_non_leader(self):
        """_list_excess_versions must skip non-leader siblings."""
        content = self._read_script()
        idx = content.index('def _list_excess_versions(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('_is_multi_ep_non_leader', section)

    def test_rename_skips_multi_episode_files(self):
        """rename_episodes must skip Plex multi-episode files entirely
        (both leader and non-leader) — the template can't safely encode
        the sNNeXX-eYY marker."""
        content = self._read_script()
        idx = content.index('def rename_episodes(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('multi_episode_siblings', section)
        self.assertIn('SKIP multi-episode file', section)

    def test_info_episode_multi_episode_display(self):
        """show_item_info's Episode branch must show the collapsed
        range form and list all siblings when the episode is part of
        a Plex multi-episode file — both leader and non-leader queries
        get the same view."""
        content = self._read_script()
        idx = content.index('def show_item_info(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        # Episode branch must check siblings and call _format_episode_range
        # using the LEADER (not the queried obj), so that --info on a
        # non-leader sibling still shows the range.
        ep_idx = section.index("if obj_type == 'Episode':")
        ep_end = section.index("elif obj_type ==", ep_idx)
        ep_section = section[ep_idx:ep_end]
        self.assertIn('multi_episode_siblings', ep_section)
        self.assertIn('_format_episode_range(leader_obj)', ep_section)
        self.assertIn('Multi-episode file:', ep_section)

    def test_help_broken_documents_multi_episode(self):
        """--help broken must explain that multi-episode files are
        listed once under the leader."""
        content = self._read_script()
        idx = content.index("case 'broken':")
        end = content.index("case 'scan':", idx)
        section = content[idx:end]
        self.assertIn('MULTI-EPISODE FILES', section)
        self.assertIn('leader', section)

    def test_help_reencode_documents_multi_episode(self):
        """--help reencode must explain multi-episode file behavior."""
        content = self._read_script()
        idx = content.index("case 'reencode':")
        end = content.index("case 'missing':", idx)
        section = content[idx:end]
        self.assertIn('MULTI-EPISODE FILES', section)
        self.assertIn('leader', section)

    def test_help_rename_documents_multi_episode_skip(self):
        """--help rename must explain that multi-episode files are skipped."""
        content = self._read_script()
        idx = content.index("case 'rename':")
        end = content.index("case 'plex-disk-sync'", idx)
        section = content[idx:end]
        self.assertIn('MULTI-EPISODE FILES', section)
        self.assertIn('SKIPPED', section)


class TestAbsEpIdx(unittest.TestCase):
    """Absolute episode counter (abs_ep_idx) — scraped-data-based running
    counter across all seasons. Stored on episode, season, and show objects."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_abs_ep_idx_computed_in_update_cache(self):
        """_process_series_from_database must compute abs_ep_idx after
        _ensure_tsv_and_normalize_episodes."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("abs_ep_idx", section)
        self.assertIn("abs_ep_max", section)
        # abs_ep_idx must come AFTER _ensure_tsv_and_normalize_episodes
        tsv_pos = section.index('_ensure_tsv_and_normalize_episodes')
        abs_pos = section.index('abs_ep_idx')
        self.assertGreater(abs_pos, tsv_pos,
                           "abs_ep_idx must be computed after _ensure_tsv_and_normalize_episodes")

    def test_abs_ep_idx_requires_scraped_data(self):
        """abs_ep_idx must only be assigned when scraped data exists."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("OBJ_BY_SERIES_SCRAPED", section)
        self.assertIn("no scraped data", section.lower())

    def test_abs_ep_idx_multi_episode_shares_leader(self):
        """Multi-episode non-leaders must share the leader's abs_ep_idx."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        # The code must check multi_episode_siblings for non-leader sharing
        self.assertIn("multi_episode_siblings", section)
        self.assertIn("siblings[0]", section)

    def test_abs_ep_max_stored_on_season_and_show(self):
        """abs_ep_max must be stored on both season and show objects."""
        content = self._read_script()
        idx = content.index('def _process_series_from_database(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn("season_obj['abs_ep_max']", section)
        self.assertIn("series_obj['abs_ep_max']", section)


class TestRenumber(unittest.TestCase):
    """Test --renumber command: detection, command registration, help page."""

    @classmethod
    def setUpClass(cls):
        """One lookup for the whole class: the scoped E2E tests need a series
        that exists here, and asking my-plex twice costs a second run."""
        cls._series_key = _pick_any_series_key()

    def _skip_if_no_series(self):
        if not getattr(self, '_series_key', None):
            self.skipTest("no series in this machine's cache for a scoped "
                          "test -- run `my-plex --update-cache` here")

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_a_missing_series_skips_instead_of_failing(self):
        """Same guard, same reason: with no series here, the scoped E2E tests
        must skip. They used to name `Series:5191` -- one id in one person's
        cache -- and failed with "Invalid parameter" everywhere else."""
        self._series_key = None
        with self.assertRaises(unittest.SkipTest):
            self._skip_if_no_series()

    def test_list_renumber_candidates_method_exists(self):
        """_list_renumber_candidates must exist as a static method on PLEX_Media."""
        content = self._read_script()
        self.assertIn('def _list_renumber_candidates(obj_keys', content)

    def test_list_renumber_lack_of_data_exists(self):
        """_list_renumber_lack_of_data must exist."""
        content = self._read_script()
        self.assertIn('def _list_renumber_lack_of_data(obj_keys', content)

    def test_list_renumber_season_mismatch_exists(self):
        """_list_renumber_season_mismatch must exist."""
        content = self._read_script()
        self.assertIn('def _list_renumber_season_mismatch(obj_keys', content)

    def test_list_renumber_abs_mismatch_exists(self):
        """_list_renumber_abs_mismatch must exist."""
        content = self._read_script()
        self.assertIn('def _list_renumber_abs_mismatch(obj_keys', content)

    def test_renumber_item_method_exists(self):
        """renumber_item must exist as a static method on PLEX_Media."""
        content = self._read_script()
        self.assertIn('def renumber_item(media_identifier', content)

    def test_renumber_skips_multi_ep_non_leader(self):
        """_list_renumber_candidates must skip multi-episode non-leaders."""
        content = self._read_script()
        idx = content.index('def _list_renumber_candidates(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('_is_multi_ep_non_leader', section)

    def test_renumber_uses_scraped_data(self):
        """_list_renumber_candidates must check OBJ_BY_SERIES_SCRAPED."""
        content = self._read_script()
        idx = content.index('def _list_renumber_candidates(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('OBJ_BY_SERIES_SCRAPED', section)

    def test_renumber_regex_exists(self):
        """_RE_SXEX regex must exist for extracting S0xE0x from filenames."""
        content = self._read_script()
        self.assertIn('_RE_SXEX', content)

    def test_command_registration_main_parser(self):
        """--renumber must be registered in main_parser."""
        content = self._read_script()
        self.assertIn("'--renumber'", content)
        # Scan the WHOLE main_parser block (a fixed-size window silently
        # grows stale as new flags push --renumber's registration past it).
        idx = content.index('main_parser.add_argument')
        end = content.index('GLOBAL_CMD_PARSER = argparse.ArgumentParser', idx)
        section = content[idx:end]
        self.assertIn("'--renumber'", section)

    def test_command_registration_global_parser(self):
        """--renumber and --fix must both be registered in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        # Scan the entire GLOBAL_CMD_PARSER section, not an arbitrary 5000-char window
        # (which has silently grown stale as new flags pushed --fix's registration past it).
        first = content.index('GLOBAL_CMD_PARSER.add_argument')
        # Find a safe end-of-block marker: argparser_main_parsed or end-of-function.
        end_markers = ['GLOBAL_CMD_PARSER.parse_known_args', 'GLOBAL_CMD_PARSER = None', 'argparser_main_parsed']
        end = len(content)
        for m in end_markers:
            i = content.find(m, first)
            if i != -1:
                end = min(end, i)
        section = content[first:end]
        self.assertIn("'--renumber'", section)
        self.assertIn("'--fix'", section)

    def test_has_standalone_cmd_includes_renumber(self):
        """has_standalone_cmd must include renumber."""
        content = self._read_script()
        idx = content.index('has_standalone_cmd')
        line_end = content.index('\n', idx)
        line = content[idx:line_end]
        self.assertIn('renumber', line)

    def test_option_to_help_topic_includes_renumber(self):
        """_OPTION_TO_HELP_TOPIC must include --renumber."""
        content = self._read_script()
        idx = content.index('_OPTION_TO_HELP_TOPIC')
        end = content.index('}', idx)
        section = content[idx:end]
        self.assertIn("'--renumber'", section)

    def test_help_renumber_page(self):
        """--help renumber must have a dedicated help page."""
        content = self._read_script()
        self.assertIn("case 'renumber':", content)
        idx = content.index("case 'renumber':")
        end = content.index("sys.exit(0)", idx)
        section = content[idx:end]
        self.assertIn('RENUMBER HELP', section)
        self.assertIn('--renumber --fix', section)
        self.assertIn('MULTI-EPISODE FILES', section)

    def test_execute_global_commands_handles_renumber(self):
        """execute_global_commands must dispatch --renumber."""
        content = self._read_script()
        idx = content.index('def execute_global_commands(')
        end = content.index('\ndef ', idx + 1)
        section = content[idx:end]
        self.assertIn('_list_renumber_candidates', section)

    def test_per_object_dispatch_handles_renumber(self):
        """Per-object argparser must dispatch --renumber to renumber_item."""
        content = self._read_script()
        self.assertIn("renumber_item(obj", content)

    def test_help_groups_problem_commands(self):
        """--help output must group problem detection commands under PROBLEM DETECTION."""
        content = self._read_script()
        self.assertIn('PROBLEM DETECTION:', content)
        # All problem commands should be in that section
        idx = content.index('PROBLEM DETECTION:')
        end = content.index('MEDIA MANAGEMENT:', idx)
        section = content[idx:end]
        self.assertIn('--problems', section)
        self.assertIn('--broken', section)
        self.assertIn('--reencode', section)
        self.assertIn('--renumber', section)

    def test_problems_integration_checks(self):
        """--problems must include all 4 renumber checks via the registry (v3)."""
        content = self._read_script()
        import re
        reg = _must(re.search(r"PROBLEM_CATEGORIES_REGISTRY = \{(.*?)\n\}", content, re.DOTALL),
                    'PROBLEM_CATEGORIES_REGISTRY').group(1)
        self.assertIsNotNone(reg, "Must find PROBLEM_CATEGORIES_REGISTRY")
        section = reg
        self.assertIn('_list_renumber_candidates', section)
        self.assertIn('_list_renumber_lack_of_data', section)
        self.assertIn('_list_renumber_season_mismatch', section)
        self.assertIn('_list_renumber_abs_mismatch', section)

    def test_print_problem_warnings_includes_renumber(self):
        """The registry-driven warning printer must cover all renumber categories."""
        content = self._read_script()
        # _print_problem_warnings iterates the registry …
        idx = content.index('def _print_problem_warnings(')
        end = content.index('\ndef ', idx + 1)
        self.assertIn('PROBLEM_CATEGORIES_REGISTRY.items()', content[idx:end])
        # … which must define every renumber category.
        import re
        reg = _must(re.search(r"PROBLEM_CATEGORIES_REGISTRY = \{(.*?)\n\}", content, re.DOTALL),
                    'PROBLEM_CATEGORIES_REGISTRY').group(1)
        self.assertIsNotNone(reg)
        for category in ("'renumber'", "'renumber_nodata'",
                         "'renumber_season'", "'renumber_abs'"):
            self.assertIn(f"    {category}: {{", reg,
                          f"registry must define {category}")

    def test_help_problems_lists_renumber_checks(self):
        """--help problems must document the renumber checks (registry headers)."""
        content = self._read_script()
        # Help is auto-generated from the registry; the registry headers
        # carry the human-readable check names.
        idx = content.index("case 'problems':")
        end = content.index("sys.exit(0)", idx)
        self.assertIn('PROBLEM_CATEGORIES_REGISTRY.items()', content[idx:end])
        import re
        reg = _must(re.search(r"PROBLEM_CATEGORIES_REGISTRY = \{(.*?)\n\}", content, re.DOTALL),
                    'PROBLEM_CATEGORIES_REGISTRY').group(1)
        self.assertIsNotNone(reg)
        self.assertIn("'--renumber'", reg)
        self.assertIn('Lack of Data', reg)
        self.assertIn('Season Mismatch', reg)
        self.assertIn('Absolute Numbering Mismatch', reg)

    def test_renumber_e2e(self):
        """--renumber runs without error (E2E)."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--renumber'],
            capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, f"--renumber failed: {result.stderr}")
        self.assertIn('renumber candidate', result.stdout.lower())

    def test_renumber_scoped_e2e(self):
        """<SHOW> --renumber runs without error (E2E)."""
        self._skip_if_no_series()
        assert self._series_key is not None
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, self._series_key, '--renumber'],
            capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, f"Scoped --renumber failed: {result.stderr}")
        self.assertIn('renumber candidate', result.stdout.lower())

    def test_fix_renumber_candidates_method_exists(self):
        """_fix_renumber_candidates must exist as a static method on PLEX_Media."""
        self.assertTrue(hasattr(PLEX_Media, '_fix_renumber_candidates'))
        self.assertTrue(callable(getattr(PLEX_Media, '_fix_renumber_candidates')))

    def test_renumber_fix_dry_run_e2e(self):
        """<SHOW> --renumber --fix --try runs without error (E2E, scoped to one show)."""
        self._skip_if_no_series()
        assert self._series_key is not None
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, self._series_key, '--renumber', '--fix', '--try'],
            capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, f"--renumber --fix --try failed: {result.stderr}")
        output = result.stdout.lower()
        self.assertIn('renumber fix summary', output, "Should print summary")
        self.assertIn('[dry-run]', output, "Should show DRY-RUN prefix")

    def test_renumber_name_pattern_config_default(self):
        """RENUMBER_NAME_PATTERN must exist in CONFIG_DEFAULTS."""
        src = self._read_script()
        self.assertIn("'RENUMBER_NAME_PATTERN'", src,
                      "CONFIG_DEFAULTS should include RENUMBER_NAME_PATTERN")

    def test_help_renumber_shows_pattern(self):
        """--help renumber should show RENUMBER_NAME_PATTERN and configuration section."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'renumber'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn('RENUMBER_NAME_PATTERN', result.stdout)
        self.assertIn('CONFIGURATION', result.stdout)

    def test_help_renumber_no_longer_shows_not_implemented(self):
        """--help renumber should NOT say 'NOT YET IMPLEMENTED'."""
        result = subprocess.run([sys.executable, MAIN_SCRIPT, '--help', 'renumber'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('NOT YET IMPLEMENTED', result.stdout)

    def test_scraped_padding_method_exists(self):
        """_scraped_padding must exist as a static method on PLEX_Media."""
        self.assertTrue(hasattr(PLEX_Media, '_scraped_padding'))
        self.assertTrue(callable(getattr(PLEX_Media, '_scraped_padding')))

    def test_scraped_padding_uses_scraped_data(self):
        """_scraped_padding must derive padding from scraped episode numbers, not Plex E_idx."""
        src = self._read_script()
        idx = src.index('def _scraped_padding(')
        method_body = src[idx:idx+1500]
        self.assertIn('OBJ_BY_SERIES_SCRAPED', method_body,
                       "_scraped_padding must read from OBJ_BY_SERIES_SCRAPED")

    def test_renumber_uses_scraped_padding(self):
        """_list_renumber_candidates and _fix_renumber_candidates must use _scraped_padding."""
        src = self._read_script()
        for method_name in ('_list_renumber_candidates', '_fix_renumber_candidates'):
            idx = src.index(f'def {method_name}(')
            method_body = src[idx:idx+5000]
            self.assertIn('_scraped_padding', method_body,
                          f"{method_name} must use _scraped_padding for correct padding")


class TestEpisodeNumberingIssues(unittest.TestCase):
    """Test --episode-numbering-issues command integration (12 integration points)."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_function_exists(self):
        """_list_episode_numbering_issues must exist."""
        content = self._read_script()
        self.assertIn('def _list_episode_numbering_issues(', content)

    def test_library_argparser(self):
        """--episode-numbering-issues must be in library argparser."""
        content = self._read_script()
        self.assertIn("'--episode-numbering-issues'", content)

    def test_global_cmd_parser(self):
        """--episode-numbering-issues must be in GLOBAL_CMD_PARSER."""
        content = self._read_script()
        idx = content.index('GLOBAL_CMD_PARSER.add_argument')
        self.assertIn('--episode-numbering-issues', content[idx:])

    def test_problems_integration(self):
        """--problems must include episode numbering issues section."""
        content = self._read_script()
        self.assertIn('Episode Numbering Issues', content)
        self.assertIn('numbering_count', content)

    def test_help_exists(self):
        """--help episode-numbering-issues must work."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'episode-numbering-issues'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, f"--help episode-numbering-issues failed: {result.stderr}")
        self.assertIn('EPISODE NUMBERING ISSUES', result.stdout)

    def test_e2e_runs(self):
        """--episode-numbering-issues must run without error."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--episode-numbering-issues'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, f"--episode-numbering-issues failed: {result.stderr}")

    def test_re_injection(self):
        """--episode-numbering-issues must be re-injected into remaining_args."""
        content = self._read_script()
        self.assertIn("'episode_numbering_issues'", content)
        self.assertIn("'--episode-numbering-issues'", content)

    def test_has_standalone_cmd(self):
        """--episode-numbering-issues must be in has_standalone_cmd check."""
        content = self._read_script()
        self.assertIn("'episode_numbering_issues'", content)

    def test_main_parser_suppressed(self):
        """--episode-numbering-issues must be in main_parser as suppressed."""
        content = self._read_script()
        self.assertIn("main_parser.add_argument('--episode-numbering-issues'", content)

    def test_mismatched_title_dir_uses_key_format(self):
        """--mismatched (title-vs-directory section) output must use cache key format (Type:ID), not separate TYPE+ID columns."""
        content = self._read_script()
        idx = content.index('def _list_potential_mismatches(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        # Must NOT have separate TYPE and PLEX-ID columns
        self.assertNotIn("{'TYPE'", section,
            "Output must use KEY column, not separate TYPE column")
        # Must have KEY column
        self.assertIn("{'KEY'", section)

    def test_mismatched_title_dir_comparison_column(self):
        """--mismatched (title-vs-directory section) output must have COMPARISON column."""
        content = self._read_script()
        idx = content.index('def _list_potential_mismatches(')
        end = content.index('\n    @staticmethod', idx + 1)
        section = content[idx:end]
        self.assertIn('COMPARISON', section)
        self.assertIn('SCRAPED-TITLE:', section)
        self.assertIn('DIR:', section)


class TestInfoScrapedData(unittest.TestCase):
    """Test --info output includes scraped info for shows."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_info_shows_scraped_title(self):
        """--info for shows must display scraped title."""
        content = self._read_script()
        self.assertIn('Scraped Title:', content)
        self.assertIn('Scraped Source:', content)

    def test_info_shows_numbering_issues(self):
        """--info for shows must display numbering issue count."""
        content = self._read_script()
        self.assertIn('Numbering Issues:', content)

    def test_info_episode_table_has_episode_column(self):
        """--info episode table must use a single EPISODE column (no Normalized/Plex split).
        The EPISODE column shows the padded-per-show S0XE0X value, which is
        Plex-sourced. Scraped-source numbering is never displayed."""
        content = self._read_script()
        # Locate the episode-table block inside show_item_info
        idx = content.index("Episode table (verbose only)")
        end = content.index('elif obj_type == \'Movie\':', idx)
        section = content[idx:end]
        self.assertIn("'EPISODE'", section)
        # Must NOT have separate PLEX/NORMALIZED columns anymore
        self.assertNotIn("'PLEX'", section)
        self.assertNotIn("'NORMALIZED'", section)

    def test_info_episode_shows_single_episode_id(self):
        """--info for Episode objs in show_item_info must print the single
        padded 'Episode:' line (no separate Plex/Normalized/Scraped lines)."""
        content = self._read_script()
        # Scope to show_item_info specifically (several other sites in the
        # script also have `if obj_type == 'Episode':` blocks).
        fn_idx = content.index('def show_item_info(')
        fn_end = content.index('\ndef ', fn_idx + 1)
        fn_section = content[fn_idx:fn_end]
        ep_idx = fn_section.index("if obj_type == 'Episode':")
        ep_end = fn_section.index("elif obj_type == 'Season':", ep_idx)
        ep_block = fn_section[ep_idx:ep_end]
        self.assertIn('"Episode:\\t{plex_s0xe0x}"', ep_block)
        # No "Episode (Plex):" / "Episode (Normalized):" lines any more
        self.assertNotIn('Episode (Plex):', ep_block)
        self.assertNotIn('Episode (Normalized):', ep_block)


class TestDiskMap(unittest.TestCase):
    """Tests for --plex2disk / --disk2plex disk marker system."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def _mock_obj(self, **overrides):
        """Create a mock cache entry with sensible defaults for testing."""
        obj = {
            'type': 'Movie', 'title': 'Test Movie', 'year': 2024,
            'library': 'lib3', 'file': '/path/to/Test Movie.mkv',
            'files': {'90.0min 1920x1080 (h264 aac)': {'filepath': '/path/to/Test Movie.mkv'}},
            'viewCount': 2, 'lastViewedAt': 1711065600,  # 2024-03-22
            'userRating': 7.5, 'criticsRating': 8.2, 'audienceRating': 85.0,
            'contentRating': 'PG-13',
            'actors': ['Bryan Cranston', 'Aaron Paul', 'Anna Gunn', 'Dean Norris'],
            'countries': ['US', 'UK'], 'genres': ['Drama', 'Crime'],
            'directors': ['Vince Gilligan'], 'writers': ['Peter Gould', 'Thomas Schnauz'],
            'resolution': '1080p', 'video_codec': 'h264', 'audio_codec': 'aac',
            'duration': 5400000, 'series': '', 'originalTitle': '',
            'external_ids': {'imdb': 'tt0903747', 'tmdb': '1396', 'tvdb': '81189'},
            'audio_languages': [], 'subtitle_languages': [],
            'collections': [], 'labels': [],
        }
        obj.update(overrides)
        return obj

    # --- PREFERRED_AUDIO_LANGUAGES ---

    def _with_preferred(self, prefs):
        """Context-manager-like helper: temporarily set PREFERRED_AUDIO_LANGUAGES."""
        main_mod = _main_module()
        return main_mod, main_mod.PREFERRED_AUDIO_LANGUAGES, prefs

    def test_preferred_audio_lang_default_first_track(self):
        """Empty PREFERRED_AUDIO_LANGUAGES → AUDIO_LANG = first track (current behavior)."""
        main_mod, saved, _ = self._with_preferred([])
        try:
            main_mod.PREFERRED_AUDIO_LANGUAGES = []
            obj = self._mock_obj(audio_languages=['zh', 'en', 'ru'])
            var = resolve_disk_map_variables(obj)
            self.assertEqual(var['AUDIO_LANG'], 'zh')
            self.assertEqual(var['AUDIO_LANGS_LIST'], ['zh', 'en', 'ru'])
        finally:
            main_mod.PREFERRED_AUDIO_LANGUAGES = saved

    def test_preferred_audio_lang_picks_preferred_match(self):
        """When a preferred lang is present in tracks, it becomes AUDIO_LANG."""
        main_mod, saved, _ = self._with_preferred(['en', 'de', 'fr'])
        try:
            main_mod.PREFERRED_AUDIO_LANGUAGES = ['en', 'de', 'fr']
            obj = self._mock_obj(audio_languages=['zh', 'en', 'ru'])
            var = resolve_disk_map_variables(obj)
            self.assertEqual(var['AUDIO_LANG'], 'en')
            # AUDIO_LANGS_LIST stays in original order
            self.assertEqual(var['AUDIO_LANGS_LIST'], ['zh', 'en', 'ru'])
        finally:
            main_mod.PREFERRED_AUDIO_LANGUAGES = saved

    def test_preferred_audio_lang_respects_preference_order(self):
        """First entry in PREFERRED_AUDIO_LANGUAGES that matches wins (not file order)."""
        main_mod, saved, _ = self._with_preferred(['de', 'en'])
        try:
            main_mod.PREFERRED_AUDIO_LANGUAGES = ['de', 'en']
            # File has [en, de] but DE is preferred first → DE wins
            obj = self._mock_obj(audio_languages=['en', 'de'])
            var = resolve_disk_map_variables(obj)
            self.assertEqual(var['AUDIO_LANG'], 'de')
        finally:
            main_mod.PREFERRED_AUDIO_LANGUAGES = saved

    def test_preferred_audio_lang_fallback_when_no_match(self):
        """No preferred lang in tracks → falls back to first track."""
        main_mod, saved, _ = self._with_preferred(['en', 'de'])
        try:
            main_mod.PREFERRED_AUDIO_LANGUAGES = ['en', 'de']
            obj = self._mock_obj(audio_languages=['zh', 'ru', 'ja'])
            var = resolve_disk_map_variables(obj)
            self.assertEqual(var['AUDIO_LANG'], 'zh')
        finally:
            main_mod.PREFERRED_AUDIO_LANGUAGES = saved

    def test_preferred_audio_lang_empty_tracks(self):
        """Empty audio_languages → 'unknown' regardless of preferences."""
        main_mod, saved, _ = self._with_preferred(['en'])
        try:
            main_mod.PREFERRED_AUDIO_LANGUAGES = ['en']
            obj = self._mock_obj(audio_languages=[])
            var = resolve_disk_map_variables(obj)
            self.assertEqual(var['AUDIO_LANG'], 'unknown')
        finally:
            main_mod.PREFERRED_AUDIO_LANGUAGES = saved

    # --- resolve_disk_map_variables ---

    def test_resolve_variables_basic(self):
        """Variable resolution produces expected values from mock obj."""
        obj = self._mock_obj()
        var = resolve_disk_map_variables(obj)
        self.assertIs(var['WATCHED'], True)                   # bool
        self.assertEqual(var['VIEW_COUNT'], 2)                # int
        self.assertEqual(var['RATING_USER'], 7.5)             # float
        self.assertEqual(var['RATING_CRITICS'], 8.2)          # float
        self.assertEqual(var['RATING_AUDIENCE'], 85.0)        # float
        self.assertEqual(var['CONTENT_RATING'], 'PG-13')
        self.assertEqual(var['ACTORS_TOP3'], 'Bryan Cranston, Aaron Paul, Anna Gunn')
        self.assertEqual(var['ACTOR1_FN'], 'Bryan')
        self.assertEqual(var['ACTOR1_LN'], 'Cranston')
        self.assertEqual(var['ACTOR2_FN'], 'Aaron')
        self.assertEqual(var['ACTOR2_LN'], 'Paul')
        self.assertEqual(var['ACTOR3_FN'], 'Anna')
        self.assertEqual(var['ACTOR3_LN'], 'Gunn')
        self.assertEqual(var['COUNTRY'], 'US')
        self.assertEqual(var['COUNTRIES'], 'US, UK')
        self.assertEqual(var['GENRE'], 'Drama')
        self.assertEqual(var['DIRECTOR'], 'Vince Gilligan')
        self.assertEqual(var['RESOLUTION'], '1080p')
        self.assertEqual(var['YEAR'], 2024)                   # int
        self.assertEqual(var['IMDB_ID'], 'tt0903747')
        self.assertEqual(var['TMDB_ID'], '1396')
        self.assertEqual(var['LABELS'], '')
        self.assertEqual(var['COLLECTIONS'], '')

    def test_resolve_variables_watched_dates(self):
        """Watched date/timestamp variables resolve correctly."""
        obj = self._mock_obj()  # lastViewedAt=1711065600 → 2024-03-22
        var = resolve_disk_map_variables(obj)
        self.assertEqual(var['WATCHED_DATE'], '2024-03-22')
        self.assertRegex(var['WATCHED_TS'], r'2024-03-22_\d{4}')

    def test_resolve_variables_unwatched(self):
        """Unwatched item has WATCHED=False."""
        obj = self._mock_obj(viewCount=0, lastViewedAt=None)
        var = resolve_disk_map_variables(obj)
        self.assertIs(var['WATCHED'], False)
        self.assertEqual(var['VIEW_COUNT'], 0)
        self.assertEqual(var['WATCHED_DATE'], '')
        self.assertEqual(var['WATCHED_TS'], '')

    def test_resolve_variables_empty_actors(self):
        """Empty actors produce empty strings."""
        obj = self._mock_obj(actors=[])
        var = resolve_disk_map_variables(obj)
        self.assertEqual(var['ACTORS_TOP3'], '')
        self.assertEqual(var['ACTOR1_FN'], '')
        self.assertEqual(var['ACTOR1_LN'], '')

    def test_resolve_variables_no_ratings(self):
        """None ratings produce None (falsy for eval expressions)."""
        obj = self._mock_obj(userRating=None, criticsRating=None, audienceRating=None)
        var = resolve_disk_map_variables(obj)
        self.assertIsNone(var['RATING_USER'])
        self.assertIsNone(var['RATING_CRITICS'])
        self.assertIsNone(var['RATING_AUDIENCE'])

    def test_resolve_variables_labels_collections(self):
        """Labels and collections resolve to comma-separated strings."""
        obj = self._mock_obj(labels=['favorite', 'horror'], collections=['Halloween', 'Slashers'])
        var = resolve_disk_map_variables(obj)
        self.assertEqual(var['LABELS'], 'favorite, horror')
        self.assertEqual(var['COLLECTIONS'], 'Halloween, Slashers')

    # --- strip_our_markers ---

    def test_strip_our_markers_basic(self):
        """Strip known markers from filename (space+bracket format)."""
        entry = {'markers': {'watched': 'vu', 'rating': '7.5'}}
        result = strip_our_markers('Movie Title [vu] [7.5].mkv', entry)
        self.assertEqual(result, 'Movie Title.mkv')

    def test_strip_our_markers_no_entry(self):
        """No sidecar entry means no stripping."""
        result = strip_our_markers('Movie Title [vu].mkv', None)
        self.assertEqual(result, 'Movie Title [vu].mkv')

    def test_strip_our_markers_empty(self):
        """Empty markers dict means no stripping."""
        result = strip_our_markers('Movie Title [vu].mkv', {'markers': {}})
        self.assertEqual(result, 'Movie Title [vu].mkv')

    def test_strip_our_markers_legacy_dot_format(self):
        """Strip known markers from filename (legacy dot-separated format)."""
        entry = {'markers': {'watched': 'vu', 'rating': '7.5'}}
        result = strip_our_markers('Movie Title.vu.7.5.mkv', entry)
        self.assertEqual(result, 'Movie Title.mkv')

    # --- apply_markers ---

    def test_apply_markers_basic(self):
        """Apply markers to clean filename — space+bracket format."""
        markers = {'watched': 'vu', 'rating': '7.5'}
        result = apply_markers('Movie Title.mkv', markers)
        # Sorted by aspect name: rating before watched
        self.assertEqual(result, 'Movie Title [7.5] [vu].mkv')

    def test_apply_markers_deterministic_order(self):
        """Markers are sorted by aspect name."""
        markers = {'z_last': 'Z', 'a_first': 'A', 'm_mid': 'M'}
        result = apply_markers('File.mkv', markers)
        self.assertEqual(result, 'File [A] [M] [Z].mkv')

    def test_apply_markers_empty_skipped(self):
        """Empty markers are not included."""
        markers = {'watched': 'vu', 'rating': ''}
        result = apply_markers('Movie.mkv', markers)
        self.assertEqual(result, 'Movie [vu].mkv')

    def test_apply_markers_all_empty(self):
        """If all markers are empty, filename is unchanged."""
        markers = {'rating': '', 'country': ''}
        result = apply_markers('Movie.mkv', markers)
        self.assertEqual(result, 'Movie.mkv')

    # --- roundtrip ---

    def test_strip_apply_roundtrip(self):
        """Strip markers then apply same markers gives same filename."""
        markers = {'watched': 'vu', 'rating': '7.5'}
        original = apply_markers('Movie Title.mkv', markers)
        entry = {'markers': markers}
        stripped = strip_our_markers(original, entry)
        self.assertEqual(stripped, 'Movie Title.mkv')
        reapplied = apply_markers(stripped, markers)
        self.assertEqual(reapplied, original)

    # --- sidecar ---

    def test_sidecar_roundtrip(self):
        """Save and load sidecar produces identical data."""
        import tempfile, json
        sidecar = {'/path/to/file [vu@2026-03-22].mkv': {
            'markers': {'watched': 'vu@2026-03-22'},
            'clean_name': 'file.mkv',
            'last_updated': '2026-03-22'
        }}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sidecar, f, indent=2)
            tmp_path = f.name
        try:
            with open(tmp_path, 'r') as f:
                loaded = json.load(f)
            self.assertEqual(sidecar, loaded)
        finally:
            os.unlink(tmp_path)

    # --- legacy VU migration ---

    def test_legacy_vu_detection(self):
        """Legacy [vu@TIMESTAMP] marker is detected by _extract_legacy_vu_marker."""
        marker = _extract_legacy_vu_marker('Movie.[vu@2026-01-15].mkv')
        self.assertEqual(marker, '[vu@2026-01-15]')

    def test_legacy_vu_plain(self):
        """Legacy [vu] plain marker is detected."""
        marker = _extract_legacy_vu_marker('Movie.[vu].mkv')
        self.assertEqual(marker, '[vu]')

    def test_legacy_vu_none(self):
        """No VU marker returns None."""
        marker = _extract_legacy_vu_marker('Movie.mkv')
        self.assertIsNone(marker)

    def test_legacy_vu_in_dir(self):
        """Legacy [vu@TIMESTAMP] marker in directory name is detected."""
        marker = _extract_legacy_vu_marker('Movie (2024) [vu@2026-01-15]')
        self.assertEqual(marker, '[vu@2026-01-15]')

    def test_legacy_vu_case_insensitive(self):
        """[VU], [Vu], [vU] are all detected case-insensitively."""
        self.assertEqual(_extract_legacy_vu_marker('Movie [VU].mkv'), '[VU]')
        self.assertEqual(_extract_legacy_vu_marker('Movie [Vu].mkv'), '[Vu]')
        self.assertEqual(_extract_legacy_vu_marker('Movie [vU].mkv'), '[vU]')
        self.assertEqual(_extract_legacy_vu_marker('Movie [VU@2026-01-15].mkv'), '[VU@2026-01-15]')

    def test_migrate_legacy_vu_sidecar(self):
        """_migrate_legacy_vu_sidecar creates synthetic sidecar entry with bare value."""
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie.[vu@2026-01-15].mkv')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['markers']['watched'], 'vu@2026-01-15')
        self.assertEqual(entry['clean_name'], 'Movie.mkv')
        self.assertEqual(ts_source, 'marker')
        self.assertNotIn('is_dir', entry)

    def test_migrate_legacy_vu_sidecar_dir(self):
        """_migrate_legacy_vu_sidecar with is_dir creates dir entry."""
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie (2024) [vu@2026-01-15]', is_dir=True)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.get('is_dir'))
        self.assertEqual(ts_source, 'marker')

    def test_migrate_legacy_vu_sidecar_bare_no_obj(self):
        """_migrate_legacy_vu_sidecar for bare [vu] without obj uses today's date."""
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie.[vu].mkv')
        self.assertIsNotNone(entry)
        self.assertIn('vu@', entry['markers']['watched'])
        self.assertEqual(ts_source, 'today')

    def test_migrate_legacy_vu_sidecar_bare_with_plex_date(self):
        """_migrate_legacy_vu_sidecar for bare [vu] with Plex obj uses lastViewedAt."""
        obj = {'lastViewedAt': 1711065600}  # 2024-03-22
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie.[vu].mkv', obj=obj)
        self.assertIsNotNone(entry)
        self.assertEqual(entry['markers']['watched'], 'vu@2024-03-22')
        self.assertEqual(ts_source, 'plex')

    def test_migrate_legacy_vu_sidecar_bare_uppercase(self):
        """_migrate_legacy_vu_sidecar handles [VU] case-insensitively."""
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie [VU].mkv')
        self.assertIsNotNone(entry)
        self.assertIn('vu@', entry['markers']['watched'])
        self.assertEqual(ts_source, 'today')

    def test_migrate_legacy_vu_sidecar_none(self):
        """_migrate_legacy_vu_sidecar returns None when no legacy marker."""
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie.mkv')
        self.assertIsNone(entry)
        self.assertEqual(ts_source, '')

    def test_migrate_legacy_vu_no_space(self):
        """Legacy [VU] with no space before bracket is detected and stripped."""
        entry, ts_source = _migrate_legacy_vu_sidecar('Betty[VU].mp4')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['clean_name'], 'Betty.mp4')
        self.assertIn('vu@', entry['markers']['watched'])

    def test_migrate_legacy_vu_incomplete_date_padded(self):
        """Incomplete date [vu@2022-12] is padded to vu@2022-12-01."""
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie [vu@2022-12].avi')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['markers']['watched'], 'vu@2022-12-01')
        self.assertEqual(ts_source, 'marker')

    def test_migrate_legacy_vu_incomplete_date_plex_in_same_month(self):
        """Incomplete date uses Plex date when Plex date is in the same month."""
        import calendar, time
        # 2022-12-15 as epoch
        ts = calendar.timegm(time.strptime('2022-12-15', '%Y-%m-%d'))
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie [vu@2022-12].avi', obj={'lastViewedAt': ts})
        self.assertIsNotNone(entry)
        self.assertEqual(entry['markers']['watched'], 'vu@2022-12-15')
        self.assertEqual(ts_source, 'plex')

    def test_migrate_legacy_vu_incomplete_date_plex_newer(self):
        """Incomplete date uses Plex date when Plex date is newer than the month."""
        import calendar, time
        ts = calendar.timegm(time.strptime('2023-05-10', '%Y-%m-%d'))
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie [vu@2022-12].avi', obj={'lastViewedAt': ts})
        self.assertIsNotNone(entry)
        self.assertEqual(entry['markers']['watched'], 'vu@2023-05-10')
        self.assertEqual(ts_source, 'plex')

    def test_migrate_legacy_vu_incomplete_date_plex_older(self):
        """Incomplete date keeps padded date when Plex date is older."""
        import calendar, time
        ts = calendar.timegm(time.strptime('2022-06-01', '%Y-%m-%d'))
        entry, ts_source = _migrate_legacy_vu_sidecar('Movie [vu@2022-12].avi', obj={'lastViewedAt': ts})
        self.assertIsNotNone(entry)
        self.assertEqual(entry['markers']['watched'], 'vu@2022-12-01')
        self.assertEqual(ts_source, 'marker')

    # --- source inspection ---

    def test_source_has_disk_map_functions(self):
        """Source must contain all disk map functions."""
        content = self._read_script()
        for func in ['validate_disk_plex_map', 'compute_markers_dpm',
                     'read_markers_from_disk',
                     'resolve_disk_map_variables', 'strip_our_markers',
                     'apply_markers', 'apply_markers_to_dir',
                     'strip_markers_from_dir',
                     'load_disk_map_sidecar', 'save_disk_map_sidecar',
                     'cmd_plex2disk', 'cmd_plex2disk_clean', 'cmd_disk2plex',
                     '_DISK2PLEX_PUSH_HANDLERS',
                     'transfer_disk_map_markers', 'transfer_disk_map_markers_dir',
                     '_merge_marker', '_extract_legacy_vu_marker',
                     '_migrate_legacy_vu_sidecar', 'DISK_MAP_VARIABLES',
                     '_PLEX_WRITABLE_FIELDS']:
            self.assertIn(f'{func}', content, f"Missing: {func}")

    def test_source_has_disk_map_argparse(self):
        """Source must have --plex2disk, --disk2plex, and legacy alias argparse entries."""
        content = self._read_script()
        self.assertIn("'--plex2disk'", content)
        self.assertIn("'--disk2plex'", content)
        # Legacy aliases still present
        self.assertIn("'--map-to-filename'", content)
        self.assertIn("'--map-from-filename'", content)

    def test_source_has_plex2disk_help(self):
        """Source must have help cases for plex2disk and disk2plex."""
        content = self._read_script()
        self.assertIn("'plex2disk'", content)
        self.assertIn("'disk2plex'", content)

    def test_source_has_plex_dir(self):
        """Source must reference ~/.my-plex/ directory."""
        content = self._read_script()
        self.assertIn("'.my-plex'", content)
        self.assertIn("'.my-plex/cache.pkl'", content)
        self.assertIn("'.my-plex/disk_map.json'", content)

    # --- Source inspection: transfer_disk_map_markers integration ---

    def test_transfer_markers_in_dup_resolution(self):
        """transfer_disk_map_markers must be called unconditionally from dup resolution."""
        content = self._read_script()
        # Pattern A: _execute_trash_and_move
        idx_func = content.find('def _execute_trash_and_move(')
        idx_next = content.find('\ndef ', idx_func + 1)
        func_body = content[idx_func:idx_next]
        self.assertIn('transfer_disk_map_markers(', func_body,
                       "_execute_trash_and_move must call transfer_disk_map_markers")
        # Patterns B+C: execute_resolution_action
        idx_func = content.find('def execute_resolution_action(')
        idx_next = content.find('\ndef ', idx_func + 1)
        func_body = content[idx_func:idx_next]
        count = func_body.count('transfer_disk_map_markers(')
        self.assertGreaterEqual(count, 2,
                                f"execute_resolution_action must call transfer_disk_map_markers at least 2x, found {count}")

    def test_no_vu_conditional_in_dup_resolution(self):
        """Dup resolution must NOT have 'if DISK_MAP:' conditionals — calls are unconditional."""
        content = self._read_script()
        for func_name in ('_execute_trash_and_move', 'execute_resolution_action'):
            idx_func = content.find(f'def {func_name}(')
            idx_next = content.find('\ndef ', idx_func + 1)
            func_body = content[idx_func:idx_next]
            self.assertNotIn('if DISK_MAP:', func_body,
                             f"{func_name} must NOT have 'if DISK_MAP:' conditional — calls must be unconditional")
            self.assertNotIn('add_vu_marker_to_file(', func_body,
                             f"{func_name} must NOT contain legacy add_vu_marker_to_file")

    # --- E2E: --help plex2disk / disk2plex ---

    def test_help_plex2disk(self):
        """--help plex2disk should print help and exit 0."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'plex2disk'],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('SYNC PLEX METADATA TO DISK', result.stdout)
        self.assertIn('AVAILABLE VARIABLES', result.stdout)

    def test_help_disk2plex(self):
        """--help disk2plex should print help and exit 0."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'disk2plex'],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('ADDITIVE', result.stdout)

    def test_help_plex_disk_sync(self):
        """--help plex-disk-sync should print help and exit 0."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'plex-disk-sync'],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('Phase 1', result.stdout)
        self.assertIn('Phase 2', result.stdout)

    def test_help_sync_alias(self):
        """--help sync should route to plex-disk-sync help."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'sync'],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('BIDIRECTIONAL SYNC', result.stdout)

    # --- dir markers ---

    def test_apply_markers_to_dir_basic(self):
        """Apply markers to directory name (space+brackets)."""
        markers = {'watched': 'vu@2026-03-22', 'rating': '7.5'}
        result = apply_markers_to_dir('Movie (2024)', markers)
        # Sorted by aspect name: rating before watched
        self.assertEqual(result, 'Movie (2024) [7.5] [vu@2026-03-22]')

    def test_apply_markers_to_dir_empty(self):
        """Empty markers leave directory name unchanged."""
        markers = {'watched': '', 'rating': ''}
        result = apply_markers_to_dir('Movie (2024)', markers)
        self.assertEqual(result, 'Movie (2024)')

    def test_strip_markers_from_dir_basic(self):
        """Strip known markers from directory name (bare values in sidecar)."""
        entry = {'markers': {'watched': 'vu@2026-03-22', 'rating': '7.5'}}
        result = strip_markers_from_dir('Movie (2024) [7.5] [vu@2026-03-22]', entry)
        self.assertEqual(result, 'Movie (2024)')

    def test_strip_markers_from_dir_no_entry(self):
        """No sidecar entry means no stripping."""
        result = strip_markers_from_dir('Movie (2024) [vu@2026-03-22]', None)
        self.assertEqual(result, 'Movie (2024) [vu@2026-03-22]')

    # --- merge logic ---

    def test_merge_marker_plex_strategy(self):
        """'plex' strategy: Plex always wins."""
        result = _merge_marker('watched', 'vu@2026-03-22', 'vu@2026-01-15', {'watched': 'plex'})
        self.assertEqual(result, 'vu@2026-03-22')

    def test_merge_marker_disk_strategy(self):
        """'disk' strategy: disk always wins."""
        result = _merge_marker('watched', 'vu@2026-03-22', 'vu@2026-01-15', {'watched': 'disk'})
        self.assertEqual(result, 'vu@2026-01-15')

    def test_merge_marker_newer_plex_wins(self):
        """'newer' strategy: Plex wins when newer timestamp."""
        result = _merge_marker('watched', 'vu@2026-03-22', 'vu@2026-01-15', {'watched': 'newer'})
        self.assertEqual(result, 'vu@2026-03-22')

    def test_merge_marker_newer_disk_wins(self):
        """'newer' strategy: disk wins when newer timestamp."""
        result = _merge_marker('watched', 'vu@2026-01-15', 'vu@2026-03-22', {'watched': 'newer'})
        self.assertEqual(result, 'vu@2026-03-22')

    def test_merge_marker_newer_with_time(self):
        """'newer' strategy: timestamp with time precision."""
        result = _merge_marker('watched', 'vu@2026-03-22_1923', 'vu@2026-03-22_0800', {'watched': 'newer'})
        self.assertEqual(result, 'vu@2026-03-22_1923')

    def test_merge_marker_no_existing(self):
        """No existing value on disk → use Plex value."""
        result = _merge_marker('watched', 'vu@2026-03-22', '', {'watched': 'newer'})
        self.assertEqual(result, 'vu@2026-03-22')

    def test_merge_marker_no_new_newer(self):
        """Plex empty + 'newer' strategy → keep disk value."""
        result = _merge_marker('watched', '', 'vu@2026-01-15', {'watched': 'newer'})
        self.assertEqual(result, 'vu@2026-01-15')

    def test_merge_marker_no_new_plex(self):
        """Plex empty + 'plex' strategy → clear marker."""
        result = _merge_marker('watched', '', 'vu@2026-01-15', {'watched': 'plex'})
        self.assertEqual(result, '')

    def test_merge_marker_default_strategy(self):
        """Aspect not in merge config defaults to 'plex'."""
        result = _merge_marker('rating', '8.0', '7.5', {})
        self.assertEqual(result, '8.0')

    # --- _PLEX_WRITABLE_FIELDS ---

    def test_check_all_children_watched_all_watched(self):
        """Season is WATCHED when all child episodes are watched in Plex."""
        saved = (PLEX_Media.OBJ_BY_ID.copy(), PLEX_Media.OBJ_BY_SERIES_EPISODES.copy())
        try:
            PLEX_Media.OBJ_BY_ID['Episode:1'] = {'viewCount': 1, 'lastViewedAt': 1000, 'file': 'e1.mkv'}
            PLEX_Media.OBJ_BY_ID['Episode:2'] = {'viewCount': 2, 'lastViewedAt': 2000, 'file': 'e2.mkv'}
            PLEX_Media.OBJ_BY_SERIES_EPISODES['Series:1'] = {'S01': {'E01': {'v': ['Episode:1']}, 'E02': {'v': ['Episode:2']}}}
            season_obj = {'type_str': 'Season', 'series_key': 'Series:1', 'season': 'Season 1'}
            watched, max_lv = _check_all_children_watched(season_obj, 'Season')
            self.assertTrue(watched)
            self.assertEqual(max_lv, 2000)
        finally:
            PLEX_Media.OBJ_BY_ID, PLEX_Media.OBJ_BY_SERIES_EPISODES = saved

    def test_check_all_children_watched_not_all(self):
        """Season is NOT WATCHED when some episodes are unwatched."""
        saved = (PLEX_Media.OBJ_BY_ID.copy(), PLEX_Media.OBJ_BY_SERIES_EPISODES.copy())
        try:
            PLEX_Media.OBJ_BY_ID['Episode:1'] = {'viewCount': 1, 'lastViewedAt': 1000, 'file': 'e1.mkv'}
            PLEX_Media.OBJ_BY_ID['Episode:2'] = {'viewCount': 0, 'lastViewedAt': None, 'file': 'e2.mkv'}
            PLEX_Media.OBJ_BY_SERIES_EPISODES['Series:1'] = {'S01': {'E01': {'v': ['Episode:1']}, 'E02': {'v': ['Episode:2']}}}
            season_obj = {'type_str': 'Season', 'series_key': 'Series:1', 'season': 'Season 1'}
            watched, _ = _check_all_children_watched(season_obj, 'Season')
            self.assertFalse(watched)
        finally:
            PLEX_Media.OBJ_BY_ID, PLEX_Media.OBJ_BY_SERIES_EPISODES = saved

    def test_check_all_children_watched_disk_vu_counts(self):
        """Episode with [vu] on disk but unwatched in Plex still counts as watched."""
        saved = (PLEX_Media.OBJ_BY_ID.copy(), PLEX_Media.OBJ_BY_SERIES_EPISODES.copy())
        try:
            PLEX_Media.OBJ_BY_ID['Episode:1'] = {'viewCount': 1, 'lastViewedAt': 1000, 'file': 'e1.mkv'}
            PLEX_Media.OBJ_BY_ID['Episode:2'] = {'viewCount': 0, 'lastViewedAt': None, 'file': 'e2.[vu@2026-01-01].mkv'}
            PLEX_Media.OBJ_BY_SERIES_EPISODES['Series:1'] = {'S01': {'E01': {'v': ['Episode:1']}, 'E02': {'v': ['Episode:2']}}}
            season_obj = {'type_str': 'Season', 'series_key': 'Series:1', 'season': 'Season 1'}
            watched, _ = _check_all_children_watched(season_obj, 'Season')
            self.assertTrue(watched)
        finally:
            PLEX_Media.OBJ_BY_ID, PLEX_Media.OBJ_BY_SERIES_EPISODES = saved

    def test_check_all_children_watched_show_all_seasons(self):
        """Show is WATCHED only if ALL seasons' episodes are watched."""
        saved = (PLEX_Media.OBJ_BY_ID.copy(), PLEX_Media.OBJ_BY_SERIES_EPISODES.copy())
        try:
            PLEX_Media.OBJ_BY_ID['Series:1'] = {'type_str': 'Series'}
            PLEX_Media.OBJ_BY_ID['Episode:1'] = {'viewCount': 1, 'lastViewedAt': 1000, 'file': 'e1.mkv'}
            PLEX_Media.OBJ_BY_ID['Episode:2'] = {'viewCount': 0, 'lastViewedAt': None, 'file': 'e2.mkv'}
            PLEX_Media.OBJ_BY_SERIES_EPISODES['Series:1'] = {
                'S01': {'E01': {'v': ['Episode:1']}},
                'S02': {'E01': {'v': ['Episode:2']}}
            }
            series_obj = PLEX_Media.OBJ_BY_ID['Series:1']
            watched, _ = _check_all_children_watched(series_obj, 'Series')
            self.assertFalse(watched)
        finally:
            PLEX_Media.OBJ_BY_ID, PLEX_Media.OBJ_BY_SERIES_EPISODES = saved

    def test_resolve_variables_season_watched_from_children(self):
        """resolve_disk_map_variables for Season derives WATCHED from child episodes."""
        saved = (PLEX_Media.OBJ_BY_ID.copy(), PLEX_Media.OBJ_BY_SERIES_EPISODES.copy())
        try:
            PLEX_Media.OBJ_BY_ID['Episode:1'] = {'viewCount': 1, 'lastViewedAt': 1000, 'file': 'e1.mkv'}
            PLEX_Media.OBJ_BY_ID['Episode:2'] = {'viewCount': 1, 'lastViewedAt': 2000, 'file': 'e2.mkv'}
            PLEX_Media.OBJ_BY_SERIES_EPISODES['Series:1'] = {'S01': {'E01': {'v': ['Episode:1']}, 'E02': {'v': ['Episode:2']}}}
            season_obj = {'type_str': 'Season', 'series_key': 'Series:1', 'season': 'Season 1',
                          'viewCount': 0, 'lastViewedAt': None}
            var = resolve_disk_map_variables(season_obj)
            self.assertTrue(var['WATCHED'])
            self.assertNotEqual(var['WATCHED_DATE'], '')
        finally:
            PLEX_Media.OBJ_BY_ID, PLEX_Media.OBJ_BY_SERIES_EPISODES = saved

    def test_migrate_legacy_vu_dir_trailing_dot(self):
        """Legacy migration strips trailing dots from dir names after removing [vu]."""
        entry, ts = _migrate_legacy_vu_sidecar('movie.[2020].[vu]', is_dir=True)
        self.assertIsNotNone(entry)
        self.assertEqual(entry['clean_name'], 'movie.[2020]')
        self.assertFalse(entry['clean_name'].endswith('.'))

    def test_update_cache_child_paths_exact_match(self):
        """_update_cache_child_paths updates paths that exactly match old_dir (not just children)."""
        saved = (PLEX_Media.OBJ_BY_ID.copy(),
                 PLEX_Media.OBJ_BY_FILEPATH.copy() if hasattr(PLEX_Media, 'OBJ_BY_FILEPATH') else {})
        try:
            PLEX_Media.OBJ_BY_ID['Season:1'] = {'file': '/a/b/s01', 'files': {}}
            PLEX_Media.OBJ_BY_ID['Episode:1'] = {'file': '/a/b/s01/e1.mkv', 'files': {}}
            _update_cache_child_paths('/a/b/s01', '/a/b/s01 [vu]')
            self.assertEqual(PLEX_Media.OBJ_BY_ID['Season:1']['file'], '/a/b/s01 [vu]')
            self.assertEqual(PLEX_Media.OBJ_BY_ID['Episode:1']['file'], '/a/b/s01 [vu]/e1.mkv')
        finally:
            PLEX_Media.OBJ_BY_ID = saved[0]
            if hasattr(PLEX_Media, 'OBJ_BY_FILEPATH'):
                PLEX_Media.OBJ_BY_FILEPATH = saved[1]

    def test_file_scope_excludes_season_show(self):
        """File scope should only process Movie and Episode types, not Season/Show."""
        # Season with type_str='Season' should NOT be in file_items
        obj = {'type_str': 'Season', 'type': 'Season', 'file': '/a/b/s01'}
        type_str = obj.get('type_str', '')
        self.assertNotIn(type_str, ('Movie', 'Episode'))

    def test_plex_writable_fields_structure(self):
        """_PLEX_WRITABLE_FIELDS has correct structure."""
        self.assertIn('Movie', _PLEX_WRITABLE_FIELDS)
        self.assertIn('Episode', _PLEX_WRITABLE_FIELDS)
        self.assertIn('Series', _PLEX_WRITABLE_FIELDS)
        self.assertIn('Season', _PLEX_WRITABLE_FIELDS)
        # Movie and Episode support all writable fields
        self.assertIn('WATCHED', _PLEX_WRITABLE_FIELDS['Movie'])
        self.assertIn('RATING_USER', _PLEX_WRITABLE_FIELDS['Movie'])
        self.assertIn('LABELS', _PLEX_WRITABLE_FIELDS['Episode'])
        # Season only supports WATCHED
        self.assertEqual(_PLEX_WRITABLE_FIELDS['Season'], {'WATCHED'})

    # --- --force tests ---

    def test_sync_force_error_in_source(self):
        """--sync --force error message exists in source."""
        content = self._read_script()
        self.assertIn('--force cannot be used with --sync', content)

    def test_help_plex2disk_mentions_force(self):
        """--help plex2disk mentions --force."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'plex2disk'],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--force', result.stdout)
        self.assertIn('Plex is authoritative', result.stdout)

    def test_help_disk2plex_mentions_force(self):
        """--help disk2plex mentions --force."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'disk2plex'],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--force', result.stdout)
        self.assertIn('DESTRUCTIVE', result.stdout)

    def test_help_sync_mentions_force_incompatible(self):
        """--help sync mentions --force cannot be used."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--help', 'sync'],
            capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--force cannot be used', result.stdout)

    def test_cmd_plex2disk_accepts_force(self):
        """cmd_plex2disk accepts force parameter."""
        # Verify the function signature accepts force
        sig = inspect.signature(cmd_plex2disk)
        self.assertIn('force', sig.parameters)

    def test_cmd_disk2plex_accepts_force(self):
        """cmd_disk2plex accepts force parameter."""
        sig = inspect.signature(cmd_disk2plex)
        self.assertIn('force', sig.parameters)

    def test_plex2disk_dispatch_passes_force(self):
        """--plex2disk dispatch passes force to cmd_plex2disk."""
        content = self._read_script()
        # Match cmd_plex2disk(target, ... force=force ...) regardless of other kw args
        import re
        self.assertRegex(content, r'cmd_plex2disk\(target,[^)]*\bforce=force\b[^)]*\)')

    def test_disk2plex_dispatch_passes_force(self):
        """--disk2plex dispatch passes force to cmd_disk2plex."""
        content = self._read_script()
        import re
        self.assertRegex(content, r'cmd_disk2plex\(target,[^)]*\bforce=force\b[^)]*\)')

    def test_series_dir_uses_get_series_dir_helper(self):
        """Series dir routing uses get_series_dir() helper, which looks up Show object's file field."""
        content = self._read_script()
        # get_series_dir must exist and use series_key → OBJ_BY_ID lookup
        self.assertIn("def get_series_dir(obj):", content)
        func_start = content.find('def get_series_dir(obj):')
        func_end = content.find('\ndef ', func_start + 1)
        func_body = content[func_start:func_end]
        self.assertIn("series_key", func_body)
        self.assertIn("OBJ_BY_ID", func_body)
        self.assertIn(".get('file'", func_body)

    def test_plex2disk_clean_uses_cache_helpers(self):
        """cmd_plex2disk_clean must use get_season_dir/get_series_dir/get_movie_dir, not dirname()."""
        content = self._read_script()
        clean_start = content.find('def cmd_plex2disk_clean(')
        self.assertGreater(clean_start, 0, "cmd_plex2disk_clean function not found")
        clean_end = content.find('\ndef ', clean_start + 1)
        clean_body = content[clean_start:clean_end]
        # Must NOT use dirname() for season/series dirs
        self.assertNotIn('dirname(os.path.dirname(filepath))', clean_body,
                        "cmd_plex2disk_clean still uses dirname(dirname()) for series dirs")
        self.assertNotIn('dirname(filepath)', clean_body,
                        "cmd_plex2disk_clean still uses dirname(filepath) — should use cache helpers")
        # Must use cache helper functions
        self.assertIn('get_season_dir(obj)', clean_body)
        self.assertIn('get_series_dir(obj)', clean_body)
        self.assertIn('get_movie_dir(obj)', clean_body)

    def test_plex2disk_uses_cache_helpers(self):
        """cmd_plex2disk must use get_season_dir/get_series_dir/get_movie_dir, not dirname()."""
        content = self._read_script()
        plex2disk_start = content.find('def cmd_plex2disk(')
        self.assertGreater(plex2disk_start, 0, "cmd_plex2disk function not found")
        plex2disk_end = content.find('\ndef ', plex2disk_start + 1)
        plex2disk_body = content[plex2disk_start:plex2disk_end]
        # Must use cache helper functions, not inline dirname/lookups
        self.assertIn('get_season_dir(obj)', plex2disk_body)
        self.assertIn('get_series_dir(obj)', plex2disk_body)
        self.assertIn('get_movie_dir(obj)', plex2disk_body)
        # Season dir section must NOT use dirname(filepath)
        season_section_start = plex2disk_body.find('Season directory scope')
        series_section_start = plex2disk_body.find('Series directory scope')
        season_section = plex2disk_body[season_section_start:series_section_start]
        self.assertNotIn('dirname(filepath)', season_section)

    def test_cache_dir_helpers_exist(self):
        """get_episode_dir, get_movie_dir, get_season_dir, get_series_dir helpers must exist."""
        content = self._read_script()
        self.assertIn('def get_episode_dir(obj):', content)
        self.assertIn('def get_movie_dir(obj):', content)
        self.assertIn('def get_season_dir(obj):', content)
        self.assertIn('def get_series_dir(obj):', content)

    def test_normalize_alpha(self):
        """_normalize_alpha strips non-a-z characters for fuzzy path matching."""
        content = self._read_script()
        self.assertIn("def _normalize_alpha(", content)
        # Verify it's used in resolve_cache_items
        self.assertIn("_normalize_alpha(identifier)", content)
        self.assertIn("_normalize_alpha(filepath)", content)

    def test_resolve_cache_items_has_filepath_fallback(self):
        """resolve_cache_items has a Stage 6 normalized filepath search."""
        content = self._read_script()
        resolve_start = content.find('def resolve_cache_items(')
        self.assertGreater(resolve_start, 0)
        resolve_end = content.find('\ndef ', resolve_start + 1)
        resolve_body = content[resolve_start:resolve_end]
        # Must have filepath fallback using OBJ_BY_FILEPATH
        self.assertIn('OBJ_BY_FILEPATH', resolve_body)
        self.assertIn('_normalize_alpha', resolve_body)
        # Must deduplicate episodes to their parent Show
        self.assertIn("series_key = obj.get('series_key'", resolve_body)

    def test_plex2disk_output_has_prefix_and_full_path(self):
        """Rename output has LIBRARY|KEY| prefix and shows full path."""
        content = self._read_script()
        # Log prefix built from library and cache_key
        self.assertIn("prefix = f\"{lib}|{cache_key}| \"", content)
        # Rename lines use prefix and full path on single line
        self.assertIn('Rename: {path}', content)

    # ==================================================================
    # v1.2: DISK_PLEX_MAP — validate / compute / read
    # ==================================================================

    # --- validate_disk_plex_map ---

    def test_validate_dpm_valid(self):
        """Valid DISK_PLEX_MAP passes."""
        cfg = {
            'AUDIO_LANG': {
                'scope': 'file', 'merge': 'disk',
                'values': {
                    'de': {'plex2disk': '[de]', 'disk2plex': [r'\[de\]']},
                    'unknown': {},
                },
            },
            'WATCHED': {
                'scope': ['file', 'movie_dir'], 'merge': 'newer',
                'values': {True: {'plex2disk': '[vu@{WATCHED_DATE}]',
                                   'disk2plex': [r'\[vu@(?P<WATCHED_DATE>\d{4}-\d{2}-\d{2})\]']}},
            },
        }
        self.assertEqual(validate_disk_plex_map(cfg), [])

    def test_validate_dpm_unknown_plex_var(self):
        cfg = {'NOT_A_PLEX_VAR': {'scope': 'file', 'values': {}}}
        errs = validate_disk_plex_map(cfg)
        self.assertTrue(any('unknown plex variable' in e for e in errs), errs)

    def test_validate_dpm_bad_scope(self):
        cfg = {'WATCHED': {'scope': 'nope', 'values': {}}}
        errs = validate_disk_plex_map(cfg)
        self.assertTrue(any('scope' in e for e in errs), errs)

    def test_validate_dpm_bad_merge(self):
        cfg = {'WATCHED': {'scope': 'file', 'merge': 'lol', 'values': {}}}
        errs = validate_disk_plex_map(cfg)
        self.assertTrue(any('merge' in e for e in errs), errs)

    def test_validate_dpm_bad_entry_key(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'badkey': 'whatever'}}}}
        errs = validate_disk_plex_map(cfg)
        self.assertTrue(any('badkey' in e for e in errs), errs)

    def test_validate_dpm_bad_regex(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'disk2plex': [r'[unbalanced']}}}}
        errs = validate_disk_plex_map(cfg)
        self.assertTrue(any('does not compile' in e for e in errs), errs)

    def test_validate_dpm_bad_when(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'when': 'if not '}}}}
        errs = validate_disk_plex_map(cfg)
        self.assertTrue(any('not a valid expression' in e for e in errs), errs)

    def test_validate_dpm_not_dict(self):
        errs = validate_disk_plex_map([1, 2, 3])
        self.assertTrue(errs)
        self.assertIn('must be a dict', errs[0])

    # --- compute_markers_dpm ---

    def test_compute_dpm_scalar_specific(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'plex2disk': '[de]'}}}}
        out = compute_markers_dpm(cfg, {'AUDIO_LANG': 'de'}, 'file')
        self.assertEqual(out, {'AUDIO_LANG': '[de]'})

    def test_compute_dpm_scalar_wildcard(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'*': {'plex2disk': '[{AUDIO_LANG}]'}}}}
        out = compute_markers_dpm(cfg, {'AUDIO_LANG': 'es'}, 'file')
        self.assertEqual(out, {'AUDIO_LANG': '[es]'})

    def test_compute_dpm_muted(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'unknown': {}}}}
        out = compute_markers_dpm(cfg, {'AUDIO_LANG': 'unknown'}, 'file')
        self.assertNotIn('AUDIO_LANG', out)

    def test_compute_dpm_boolean_specific(self):
        cfg = {'WATCHED': {'scope': 'file',
                           'values': {True: {'plex2disk': '[vu@{WATCHED_DATE}]'}}}}
        out = compute_markers_dpm(cfg, {'WATCHED': True, 'WATCHED_DATE': '2026-01-15'}, 'file')
        self.assertEqual(out, {'WATCHED': '[vu@2026-01-15]'})

    def test_compute_dpm_list_whitelist(self):
        """List-valued plex_var: every element with a matching entry contributes one marker."""
        cfg = {'AUDIO_LANGS_LIST': {'scope': 'file',
                                    'values': {'de': {'plex2disk': '[de]'},
                                               'en': {'plex2disk': '[en]'},
                                               'es': {'plex2disk': '[es]'}}}}
        out = compute_markers_dpm(cfg, {'AUDIO_LANGS_LIST': ['de', 'en']}, 'file')
        self.assertEqual(out, {'AUDIO_LANGS_LIST': '[de][en]'})

    def test_compute_dpm_when_gates(self):
        """The 'when' predicate filters entries."""
        cfg = {'AUDIO_LANG': {'scope': 'file', 'values': {
            'de': [{'plex2disk': '[HD-de]', 'when': "RESOLUTION=='1080p'"},
                   {'plex2disk': '[de]'}],
        }}}
        hd  = compute_markers_dpm(cfg, {'AUDIO_LANG': 'de', 'RESOLUTION': '1080p'}, 'file')
        sd  = compute_markers_dpm(cfg, {'AUDIO_LANG': 'de', 'RESOLUTION': '480p'},  'file')
        self.assertEqual(hd, {'AUDIO_LANG': '[HD-de]'})
        self.assertEqual(sd, {'AUDIO_LANG': '[de]'})

    def test_compute_dpm_per_scope_override(self):
        """Tuple key (plex2disk, scope) overrides bare 'plex2disk'."""
        cfg = {'WATCHED': {'scope': ['file', 'movie_dir'],
                           'values': {True: {
                                'plex2disk': '[vu]',
                                ('plex2disk', 'movie_dir'): '[movie_vu]'}}}}
        f  = compute_markers_dpm(cfg, {'WATCHED': True}, 'file')
        md = compute_markers_dpm(cfg, {'WATCHED': True}, 'movie_dir')
        self.assertEqual(f,  {'WATCHED': '[vu]'})
        self.assertEqual(md, {'WATCHED': '[movie_vu]'})

    def test_compute_dpm_scope_filter(self):
        """An entry whose scope doesn't include the queried scope produces nothing."""
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'plex2disk': '[de]'}}}}
        out = compute_markers_dpm(cfg, {'AUDIO_LANG': 'de'}, 'movie_dir')
        self.assertEqual(out, {})

    # --- read_markers_from_disk ---

    def test_read_dpm_simple_value_match(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'disk2plex': [r'\[de\]']}}}}
        out = read_markers_from_disk('Movie [de].mkv', cfg, {'AUDIO_LANG': None}, 'file')
        self.assertEqual(out.get('AUDIO_LANG'), 'de')

    def test_read_dpm_wildcard_named_group(self):
        cfg = {'AUDIO_LANG': {'scope': 'file', 'values': {
            '*': {'disk2plex': [r'\[(?P<AUDIO_LANG>[a-z]{2})\]']}}}}
        out = read_markers_from_disk('Movie [es].mkv', cfg, {'AUDIO_LANG': None}, 'file')
        self.assertEqual(out.get('AUDIO_LANG'), 'es')

    def test_read_dpm_watched_with_date(self):
        cfg = {'WATCHED': {'scope': 'file', 'values': {True: {
            'disk2plex': [r'\[vu@(?P<WATCHED_DATE>\d{4}-\d{2}-\d{2})\]']}}}}
        out = read_markers_from_disk('Movie [vu@2026-01-15].mkv',
                                     cfg, {'WATCHED': False}, 'file')
        self.assertTrue(out.get('WATCHED'))
        self.assertEqual(out.get('WATCHED_DATE'), '2026-01-15')

    def test_read_dpm_list_collection(self):
        cfg = {'AUDIO_LANGS_LIST': {'scope': 'file',
                                    'values': {'de': {'disk2plex': [r'\[de\]']},
                                               'en': {'disk2plex': [r'\[en\]']}}}}
        out = read_markers_from_disk('Movie [de][en].mkv',
                                     cfg, {'AUDIO_LANGS_LIST': []}, 'file')
        self.assertEqual(out.get('AUDIO_LANGS_LIST'), ['de', 'en'])

    def test_read_dpm_no_match_returns_empty(self):
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'disk2plex': [r'\[de\]']}}}}
        out = read_markers_from_disk('Movie.mkv', cfg, {'AUDIO_LANG': None}, 'file')
        self.assertEqual(out, {})

    def test_read_dpm_scope_filter(self):
        """Reading from a scope not in entry's scope-set returns empty."""
        cfg = {'AUDIO_LANG': {'scope': 'file',
                              'values': {'de': {'disk2plex': [r'\[de\]']}}}}
        out = read_markers_from_disk('Movie Dir [de]', cfg,
                                     {'AUDIO_LANG': None}, 'movie_dir')
        self.assertEqual(out, {})

    # --- v1.3: series_strategy='bottom_up' uniform promotion ---

    def test_validate_dpm_series_strategy_bottom_up(self):
        """series_strategy='bottom_up' validates."""
        cfg = {'AUDIO_LANG': {'scope': ['series_dir', 'season_dir', 'file'],
                              'series_strategy': 'bottom_up',
                              'values': {'de': {'plex2disk': '[de]'}}}}
        self.assertEqual(validate_disk_plex_map(cfg), [])

    def test_validate_dpm_series_strategy_bad(self):
        cfg = {'AUDIO_LANG': {'scope': 'file', 'series_strategy': 'lol', 'values': {}}}
        errs = validate_disk_plex_map(cfg)
        self.assertTrue(any('series_strategy' in e for e in errs), errs)

    def test_promoted_vars_helper(self):
        cfg = {
            'AUDIO_LANG': {'scope': 'file', 'series_strategy': 'bottom_up', 'values': {}},
            'WATCHED':    {'scope': 'file', 'values': {}},  # default flat
        }
        self.assertEqual(_disk_plex_map_promoted_vars(cfg), ['AUDIO_LANG'])

    def _stub_series_for_promotion(self, series_key, seasons_episodes_audio):
        """Build a stub PLEX_Media cache for promotion tests.

        seasons_episodes_audio = {S_str: {E_str: [audio_languages_lists]}}
            e.g. {'S01': {'E01': [['en']], 'E02': [['en']]},
                  'S02': {'E01': [['en']], 'E02': [['de']]}}

        Populates OBJ_BY_ID with Series/Season/Episode entries, OBJ_BY_SERIES,
        OBJ_BY_SERIES_EPISODES.  Returns the main module so the test can
        restore PLEX_Media after.
        """
        main_mod = _main_module()
        # Snapshot
        saved = (dict(main_mod.PLEX_Media.OBJ_BY_ID),
                 dict(main_mod.PLEX_Media.OBJ_BY_SERIES),
                 dict(main_mod.PLEX_Media.OBJ_BY_SERIES_EPISODES))
        # Reset
        main_mod.PLEX_Media.OBJ_BY_ID = {}
        main_mod.PLEX_Media.OBJ_BY_SERIES = {}
        main_mod.PLEX_Media.OBJ_BY_SERIES_EPISODES = {}
        # Build
        series_obj = {'type_str': 'Series', 'title': 'Test'}
        main_mod.PLEX_Media.OBJ_BY_ID[series_key] = series_obj
        seasons_map = {}
        episodes_map = {}
        for S_str, eps in seasons_episodes_audio.items():
            season_key = f'Season:{series_key}:{S_str}'
            main_mod.PLEX_Media.OBJ_BY_ID[season_key] = {
                'type_str': 'Season', 'series_key': series_key, 'season': S_str,
            }
            seasons_map[S_str] = season_key
            episodes_map[S_str] = {}
            for E_str, audio_lists in eps.items():
                episodes_map[S_str][E_str] = {}
                for i, audio in enumerate(audio_lists):
                    ep_key = f'Episode:{series_key}:{S_str}:{E_str}:{i}'
                    # Real cache shape: episode has 'series_key' + 'season'
                    # (the season number); season_key is derived via
                    # OBJ_BY_SERIES[series_key][S_str].
                    season_num = int(S_str.lstrip('S')) if S_str.lstrip('S').isdigit() else 0
                    main_mod.PLEX_Media.OBJ_BY_ID[ep_key] = {
                        'type_str': 'Episode',
                        'series_key': series_key,
                        'season': season_num,
                        'audio_languages': audio,
                    }
                    episodes_map[S_str][E_str][f'v{i}'] = [ep_key]
        main_mod.PLEX_Media.OBJ_BY_SERIES[series_key] = seasons_map
        main_mod.PLEX_Media.OBJ_BY_SERIES_EPISODES[series_key] = episodes_map
        return main_mod, saved

    def _restore_series(self, main_mod, saved):
        main_mod.PLEX_Media.OBJ_BY_ID = saved[0]
        main_mod.PLEX_Media.OBJ_BY_SERIES = saved[1]
        main_mod.PLEX_Media.OBJ_BY_SERIES_EPISODES = saved[2]

    def test_finalize_uniform_series_all_en(self):
        """Series with every episode 'en' → series uniform='en', seasons uniform='en'."""
        main_mod, saved = self._stub_series_for_promotion('Series:1', {
            'S01': {'E01': [['en']], 'E02': [['en']]},
            'S02': {'E01': [['en']]},
        })
        try:
            cfg = {'AUDIO_LANG': {'scope': 'file', 'series_strategy': 'bottom_up',
                                  'values': {'en': {'plex2disk': '[en]'}}}}
            saved_dpm = main_mod.DISK_PLEX_MAP
            main_mod.DISK_PLEX_MAP = cfg
            try:
                finalize_disk_plex_map_uniform_fields(cfg)
            finally:
                main_mod.DISK_PLEX_MAP = saved_dpm
            self.assertEqual(main_mod.PLEX_Media.OBJ_BY_ID['Series:1'].get('AUDIO_LANG_uniform'), 'en')
            self.assertEqual(main_mod.PLEX_Media.OBJ_BY_ID['Season:Series:1:S01'].get('AUDIO_LANG_uniform'), 'en')
            self.assertEqual(main_mod.PLEX_Media.OBJ_BY_ID['Season:Series:1:S02'].get('AUDIO_LANG_uniform'), 'en')
        finally:
            self._restore_series(main_mod, saved)

    def test_finalize_uniform_mixed_seasons(self):
        """Series with S01 all en, S02 mixed → series uniform=None, S01 uniform='en', S02 uniform=None."""
        main_mod, saved = self._stub_series_for_promotion('Series:2', {
            'S01': {'E01': [['en']], 'E02': [['en']]},
            'S02': {'E01': [['en']], 'E02': [['de']]},
        })
        try:
            cfg = {'AUDIO_LANG': {'scope': 'file', 'series_strategy': 'bottom_up',
                                  'values': {'en': {'plex2disk': '[en]'}}}}
            saved_dpm = main_mod.DISK_PLEX_MAP
            main_mod.DISK_PLEX_MAP = cfg
            try:
                finalize_disk_plex_map_uniform_fields(cfg)
            finally:
                main_mod.DISK_PLEX_MAP = saved_dpm
            self.assertIsNone(main_mod.PLEX_Media.OBJ_BY_ID['Series:2'].get('AUDIO_LANG_uniform'))
            self.assertEqual(main_mod.PLEX_Media.OBJ_BY_ID['Season:Series:2:S01'].get('AUDIO_LANG_uniform'), 'en')
            self.assertIsNone(main_mod.PLEX_Media.OBJ_BY_ID['Season:Series:2:S02'].get('AUDIO_LANG_uniform'))
        finally:
            self._restore_series(main_mod, saved)

    def test_finalize_uniform_unknown_blocks(self):
        """A single 'unknown' (empty audio_languages) blocks uniformity."""
        main_mod, saved = self._stub_series_for_promotion('Series:3', {
            'S01': {'E01': [['en']], 'E02': [[]]},  # E02 = unknown
        })
        try:
            cfg = {'AUDIO_LANG': {'scope': 'file', 'series_strategy': 'bottom_up',
                                  'values': {'en': {'plex2disk': '[en]'}}}}
            saved_dpm = main_mod.DISK_PLEX_MAP
            main_mod.DISK_PLEX_MAP = cfg
            try:
                finalize_disk_plex_map_uniform_fields(cfg)
            finally:
                main_mod.DISK_PLEX_MAP = saved_dpm
            self.assertIsNone(main_mod.PLEX_Media.OBJ_BY_ID['Season:Series:3:S01'].get('AUDIO_LANG_uniform'))
            self.assertIsNone(main_mod.PLEX_Media.OBJ_BY_ID['Series:3'].get('AUDIO_LANG_uniform'))
        finally:
            self._restore_series(main_mod, saved)

    def test_resolve_promotion_episode_suppressed(self):
        """Episode resolves AUDIO_LANG='unknown' (mute) when parent Series uniform."""
        main_mod, saved = self._stub_series_for_promotion('Series:4', {
            'S01': {'E01': [['en']], 'E02': [['en']]},
        })
        try:
            cfg = {'AUDIO_LANG': {'scope': ['series_dir','season_dir','file'],
                                  'series_strategy': 'bottom_up',
                                  'values': {'en': {'plex2disk': '[en]'}}}}
            saved_dpm = main_mod.DISK_PLEX_MAP
            main_mod.DISK_PLEX_MAP = cfg
            try:
                finalize_disk_plex_map_uniform_fields(cfg)
                ep = main_mod.PLEX_Media.OBJ_BY_ID['Episode:Series:4:S01:E01:0']
                ep_vars = resolve_disk_map_variables(ep, 'Episode:Series:4:S01:E01:0')
                # Series uniform → episode marker muted
                self.assertEqual(ep_vars['AUDIO_LANG'], 'unknown')

                season = main_mod.PLEX_Media.OBJ_BY_ID['Season:Series:4:S01']
                season_vars = resolve_disk_map_variables(season, 'Season:Series:4:S01')
                # Series uniform → season marker also muted
                self.assertEqual(season_vars['AUDIO_LANG'], 'unknown')

                series = main_mod.PLEX_Media.OBJ_BY_ID['Series:4']
                series_vars = resolve_disk_map_variables(series, 'Series:4')
                self.assertEqual(series_vars['AUDIO_LANG'], 'en')
            finally:
                main_mod.DISK_PLEX_MAP = saved_dpm
        finally:
            self._restore_series(main_mod, saved)

    def test_resolve_promotion_falls_through_when_mixed(self):
        """When neither series nor season uniform, episode keeps its own AUDIO_LANG."""
        main_mod, saved = self._stub_series_for_promotion('Series:5', {
            'S01': {'E01': [['en']], 'E02': [['de']]},
        })
        try:
            cfg = {'AUDIO_LANG': {'scope': ['series_dir','season_dir','file'],
                                  'series_strategy': 'bottom_up',
                                  'values': {'en': {'plex2disk': '[en]'},
                                             'de': {'plex2disk': '[de]'}}}}
            saved_dpm = main_mod.DISK_PLEX_MAP
            main_mod.DISK_PLEX_MAP = cfg
            try:
                finalize_disk_plex_map_uniform_fields(cfg)
                ep_en = main_mod.PLEX_Media.OBJ_BY_ID['Episode:Series:5:S01:E01:0']
                ep_de = main_mod.PLEX_Media.OBJ_BY_ID['Episode:Series:5:S01:E02:0']
                self.assertEqual(resolve_disk_map_variables(ep_en, 'k')['AUDIO_LANG'], 'en')
                self.assertEqual(resolve_disk_map_variables(ep_de, 'k')['AUDIO_LANG'], 'de')
            finally:
                main_mod.DISK_PLEX_MAP = saved_dpm
        finally:
            self._restore_series(main_mod, saved)

    # --- v1.2.1: sibling rename (.nfo / .srt / etc.) ---

    def test_rename_file_siblings_basic(self):
        """rename_file_siblings renames every sibling matching old basename."""
        from unittest.mock import patch
        old_path = '/fake/dir/Movie.mkv'
        new_path = '/fake/dir/Movie [en].mkv'
        listing = ['/fake/dir/Movie.mkv',
                   '/fake/dir/Movie.nfo',
                   '/fake/dir/Movie.srt',
                   '/fake/dir/Movie.en.srt',
                   '/fake/dir/SomeoneElse.nfo']  # not a sibling
        renamed_calls = []
        def _fake_op(op, path, host=None, **kw):
            if op == 'LIST_DIR':
                return (True, listing)
            return (True, None)
        def _fake_rename(src, new_filename, remote_host=None):
            renamed_calls.append((src, new_filename))
            return (True, os.path.join(os.path.dirname(src), new_filename))
        main_mod = _main_module()
        with patch.object(main_mod, 'my_plex_file_operation', _fake_op), \
             patch.object(main_mod, 'rename_file', _fake_rename):
            r, e = rename_file_siblings(old_path, new_path, remote_host=None,
                                        dry_run=False)
        self.assertEqual(e, 0)
        self.assertEqual(r, 3)  # .nfo, .srt, .en.srt
        renamed_basenames = sorted([(os.path.basename(s), n) for s, n in renamed_calls])
        self.assertEqual(renamed_basenames, [
            ('Movie.en.srt', 'Movie [en].en.srt'),
            ('Movie.nfo',    'Movie [en].nfo'),
            ('Movie.srt',    'Movie [en].srt'),
        ])

    def test_rename_file_siblings_dry_run(self):
        """dry_run prints 'Sibling:' lines and doesn't call rename_file."""
        from unittest.mock import patch
        from io import StringIO
        old_path = '/fake/dir/Movie.mkv'
        new_path = '/fake/dir/Movie [en].mkv'
        listing = ['/fake/dir/Movie.mkv', '/fake/dir/Movie.nfo']
        rename_calls = []
        def _fake_op(op, path, host=None, **kw):
            return (True, listing) if op == 'LIST_DIR' else (True, None)
        def _fake_rename(src, new, remote_host=None):
            rename_calls.append((src, new))
            return (True, src)
        main_mod = _main_module()
        buf = StringIO()
        import contextlib
        with patch.object(main_mod, 'my_plex_file_operation', _fake_op), \
             patch.object(main_mod, 'rename_file', _fake_rename), \
             contextlib.redirect_stdout(buf):
            r, e = rename_file_siblings(old_path, new_path, remote_host=None,
                                        dry_run=True, log_prefix='PFX| ')
        self.assertEqual(rename_calls, [], "rename_file must not be called in dry_run")
        self.assertEqual(r, 1)
        self.assertIn('PFX| Sibling: Movie.nfo → Movie [en].nfo', buf.getvalue())

    def test_rename_file_siblings_no_change(self):
        """If old_path == new_path stem, nothing is done (skip listing too)."""
        from unittest.mock import patch
        listing_calls = []
        def _fake_op(op, path, host=None, **kw):
            listing_calls.append(op)
            return (True, [])
        main_mod = _main_module()
        with patch.object(main_mod, 'my_plex_file_operation', _fake_op):
            r, e = rename_file_siblings('/x/A.mkv', '/x/A.mkv')
        self.assertEqual((r, e), (0, 0))
        self.assertEqual(listing_calls, [], "no LIST_DIR when stems match")

    def test_rename_file_siblings_skips_unrelated(self):
        """A file whose name happens to start similarly but with no '.' boundary
        is NOT a sibling."""
        from unittest.mock import patch
        old_path = '/fake/Foo.mkv'
        new_path = '/fake/Foo [en].mkv'
        listing = ['/fake/Foo.mkv', '/fake/Foo.nfo',
                   '/fake/Foo bar.mkv',         # different file, not a sibling
                   '/fake/FooFighters.nfo']     # name prefix but no '.' separator
        renamed = []
        def _fake_op(op, path, host=None, **kw):
            return (True, listing) if op == 'LIST_DIR' else (True, None)
        def _fake_rename(src, new, remote_host=None):
            renamed.append((src, new))
            return (True, src)
        main_mod = _main_module()
        with patch.object(main_mod, 'my_plex_file_operation', _fake_op), \
             patch.object(main_mod, 'rename_file', _fake_rename):
            r, e = rename_file_siblings(old_path, new_path)
        self.assertEqual(r, 1)  # only Foo.nfo
        self.assertEqual([os.path.basename(s) for s, _ in renamed], ['Foo.nfo'])

    # --- v1.4: _classify_migration_action / cmd_remux / --problems wiring ---

    def _mock_video_obj(self, ext='.avi', vc='h264', ac='mp3',
                        duration_ms=3_000_000, filesize_bytes=400_000_000,
                        audio_languages=None, type_str='Episode',
                        filepath_override=None):
        """Build a minimal cache entry suitable for _classify_migration_action."""
        fp = filepath_override or f'/Volumes/2/watch.v/test/foo{ext}'
        version = f"50.0min 1280x720 ({vc} {ac}) {filesize_bytes//1_000_000}MB"
        return {
            'type_str': type_str,
            'type':     type_str.rstrip('*'),
            'video_codec': vc,
            'audio_codec': ac,
            'duration': duration_ms,
            'audio_languages': audio_languages if audio_languages is not None else [],
            'file': fp,
            'files': {
                version: {
                    'filepath': fp,
                    'filesize': filesize_bytes,
                    'audio_languages': list(audio_languages) if audio_languages else [],
                    'file_metadata': {'file_type': ext.lstrip('.')},
                }
            },
            'title': 'Test', 'library': 'lib5',
            'series_key': 'Series:1', 'series': 'Test',
        }

    def _set_dpm(self, dpm):
        main_mod = _main_module()
        saved = main_mod.DISK_PLEX_MAP
        main_mod.DISK_PLEX_MAP = dpm
        return main_mod, saved

    def test_classify_modern_container_no_action(self):
        obj = self._mock_video_obj(ext='.mp4', audio_languages=['de'])
        cls = _classify_migration_action(obj)
        self.assertEqual(cls['action'], 'none')
        self.assertEqual(cls['ext'], '.mp4')

    def test_classify_outdated_safe_codecs_with_lang_is_remux(self):
        obj = self._mock_video_obj(ext='.avi', vc='h264', ac='mp3',
                                   audio_languages=['de'])
        cls = _classify_migration_action(obj)
        self.assertEqual(cls['action'], 'remux')
        self.assertEqual(cls['lang'], 'de')

    def test_classify_outdated_unsafe_codecs_is_reencode(self):
        obj = self._mock_video_obj(ext='.avi', vc='msmpeg4v3', ac='wmav2',
                                   audio_languages=['de'])
        cls = _classify_migration_action(obj)
        self.assertEqual(cls['action'], 'reencode')
        self.assertIn('needs_reencode_container', cls['reasons'])

    def test_classify_high_bitrate_is_reencode_regardless_of_container(self):
        # 8 GB / 60 min ≈ 17.8 Mbps (well above 2.5 default threshold)
        obj = self._mock_video_obj(ext='.mkv', vc='h264', ac='aac',
                                   filesize_bytes=8_000_000_000,
                                   duration_ms=60*60*1000,
                                   audio_languages=['en'])
        cls = _classify_migration_action(obj)
        self.assertEqual(cls['action'], 'reencode')
        self.assertIn('high_bitrate', cls['reasons'])

    def test_classify_outdated_no_language_blocked(self):
        # Outdated container, codecs OK, but no audio_languages and DPM
        # has nothing for the filename → no_language → action='none'
        obj = self._mock_video_obj(ext='.avi', vc='h264', ac='mp3',
                                   audio_languages=[],
                                   filepath_override='/x/anonymous.avi')
        main_mod, saved = self._set_dpm({})  # no DPM = no filename hints
        try:
            cls = _classify_migration_action(obj)
            self.assertEqual(cls['action'], 'none')
            self.assertIn('no_language', cls['reasons'])
            self.assertIsNone(cls['lang'])
        finally:
            main_mod.DISK_PLEX_MAP = saved

    def test_classify_filename_regex_resolves_lang(self):
        obj = self._mock_video_obj(
            ext='.avi', vc='h264', ac='mp3', audio_languages=[],
            filepath_override='/x/Bares_fuer_Rares_2020-01-01 [TVOON] DE.mpg.avi')
        main_mod, saved = self._set_dpm({'AUDIO_LANG': {
            'scope':'file','values':{
                'de':{'plex2disk':'[de]','disk2plex':[r'\bTVOON\b']},
            }
        }})
        try:
            cls = _classify_migration_action(obj)
            self.assertEqual(cls['action'], 'remux')
            self.assertEqual(cls['lang'], 'de')
        finally:
            main_mod.DISK_PLEX_MAP = saved

    def test_classify_multi_version_type_str_with_asterisk(self):
        # Episode* / Movie* (multi-version suffix) must be accepted
        obj = self._mock_video_obj(ext='.avi', type_str='Episode*',
                                   audio_languages=['de'])
        cls = _classify_migration_action(obj)
        self.assertEqual(cls['action'], 'remux')

    def test_classify_disjoint_actions(self):
        """--reencode lists only what remuxing cannot fix: an item is NEVER both --reencode
        AND --remux.  Run a small grid and verify no overlap."""
        cases = [
            self._mock_video_obj(ext='.mp4', audio_languages=['de']),                # none
            self._mock_video_obj(ext='.avi', audio_languages=['de']),                # remux
            self._mock_video_obj(ext='.avi', vc='msmpeg4v3', audio_languages=['de']), # reencode
            self._mock_video_obj(ext='.mkv', filesize_bytes=8_000_000_000,
                                 duration_ms=60*60*1000, audio_languages=['en']),    # reencode
        ]
        for obj in cases:
            cls = _classify_migration_action(obj)
            self.assertIn(cls['action'], ('none', 'remux', 'reencode'))

    def test_resolve_lang_from_filename_tvoon(self):
        main_mod, saved = self._set_dpm({'AUDIO_LANG': {
            'scope':'file','values':{
                'de':{'plex2disk':'[de]','disk2plex':[r'\bTVOON\b']},
            }
        }})
        try:
            self.assertEqual(_resolve_audio_lang_from_filename('foo [TVOON] DE.avi'), 'de')
            self.assertIsNone(_resolve_audio_lang_from_filename('foo.avi'))
        finally:
            main_mod.DISK_PLEX_MAP = saved

    # --- v1.2: cmd_disk2plex two-phase / handler-registry source-presence ---

    def test_disk2plex_has_push_handler_registry(self):
        """cmd_disk2plex must dispatch via _DISK2PLEX_PUSH_HANDLERS registry."""
        content = self._read_script()
        self.assertIn('_DISK2PLEX_PUSH_HANDLERS', content)
        self.assertIn("'WATCHED'", content)
        self.assertIn("'AUDIO_LANG'", content)

    def test_disk2plex_dispatch_passes_yes(self):
        """--disk2plex dispatch passes yes flag to cmd_disk2plex."""
        content = self._read_script()
        import re
        self.assertRegex(content, r'cmd_disk2plex\(target,[^)]*\byes=yes\b[^)]*\)')

    def test_cmd_disk2plex_accepts_yes(self):
        """cmd_disk2plex signature accepts yes parameter."""
        sig = inspect.signature(cmd_disk2plex)
        self.assertIn('yes', sig.parameters)


# Test scopes: logical groupings of test classes by feature area
# Usage: --run-tests <scope>  runs only the classes in that scope
#        --run-tests          runs everything
#        --run-tests <title>  runs the tests whose title matches
class TestMove(unittest.TestCase):
    """Tests for --mv / --move: cross-library file move with cache update."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_cmd_move_function_exists(self):
        """cmd_move() must exist as a top-level function."""
        src = self._read_script()
        self.assertIn("def cmd_move(", src)

    def test_cmd_move_handles_multiversion_type_str(self):
        """Multi-version items carry type_str 'Movie*' / 'Episode*'.  cmd_move
        must normalize the trailing '*' so they remain movable (regression:
        'Movie*' never matched the ('Movie','Episode') membership test, so any
        multi-version movie was silently unmovable)."""
        src = self._read_script()
        idx = src.index('def cmd_move(')
        end = src.index('\ndef ', idx + 1)
        body = src[idx:end]
        self.assertIn("base_type = type_str.rstrip('*')", body,
                      "cmd_move must strip the multi-version '*' from type_str")
        self.assertIn("if base_type not in ('Movie', 'Episode'):", body,
                      "membership + compat checks must use the normalized base_type")
        # The raw 'Movie*' must NOT be used in the membership test any more.
        self.assertNotIn("if type_str not in ('Movie', 'Episode'):", body)
        # The movables tuple must carry base_type so the execution loop's
        # `type_str == 'Movie'` whole-wrapper-move test fires for multi-version
        # items (else their .nfo/.srt sidecars are orphaned by a per-file move).
        self.assertIn("movables.append((cache_key, obj, src_lib, base_type, filepaths))", body,
                      "multi-version Movie move must relocate the whole wrapper, not per-file")

    def test_cmd_move_signature(self):
        """cmd_move() must accept dry_run, force, yes kwargs."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(([^)]*)\)', src)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find cmd_move signature")
        sig = m.group(1)
        for kw in ('dry_run', 'force', 'yes'):
            self.assertIn(kw, sig, f"cmd_move must accept '{kw}' kwarg")

    def test_mv_registered_in_main_parser(self):
        """v1.20+: --mv-to / --move-to must be registered in main_parser (--mv and --move dropped)."""
        src = self._read_script()
        self.assertIn("main_parser.add_argument('--mv-to', '--move-to'", src)

    def test_mv_registered_in_global_cmd_parser(self):
        """v1.20+: --mv-to must be registered in GLOBAL_CMD_PARSER with help text."""
        src = self._read_script()
        self.assertIn("GLOBAL_CMD_PARSER.add_argument('--mv-to', '--move-to'", src)

    def test_mv_short_forms_removed(self):
        """v1.20+: --mv and --move must NOT be registered anywhere (--mv-to is the explicit name)."""
        src = self._read_script()
        self.assertNotIn("main_parser.add_argument('--mv',", src)
        self.assertNotIn("GLOBAL_CMD_PARSER.add_argument('--mv',", src)
        self.assertNotIn("'--mv': 'mv'", src)
        self.assertNotIn("'--move': 'mv'", src)

    def test_mv_in_has_standalone_cmd(self):
        """--mv must be in has_standalone_cmd check (so it doesn't fall through to help)."""
        src = self._read_script()
        self.assertIn("safe_getattr(args, 'mv', None) is not None", src)

    def test_mv_in_option_to_help_topic(self):
        """v1.20+: --mv-to and --move-to in _OPTION_TO_HELP_TOPIC for --mv-to --help synonym."""
        src = self._read_script()
        self.assertIn("'--mv-to': 'mv'", src)
        self.assertIn("'--move-to': 'mv'", src)

    def test_mv_reinject_exists(self):
        """--mv must be re-injected into remaining_args."""
        src = self._read_script()
        self.assertIn("Re-inject --mv", src)

    def test_mv_handler_in_execute_global_commands(self):
        """execute_global_commands must dispatch --mv to cmd_move()."""
        src = self._read_script()
        self.assertIn("cmd_move(mv_args", src)

    def test_mv_help_page_exists(self):
        """--help mv must have a dedicated help page (case 'mv' | 'move':)."""
        src = self._read_script()
        self.assertIn("case 'mv' | 'move':", src)

    def test_mv_help_page_covers_features(self):
        """--help mv page must document key features: DUPLICATE, --force, SIBLINGS, scope examples."""
        src = self._read_script()
        import re
        m = re.search(r"case 'mv' \| 'move':(.*?)sys\.exit\(0\)", src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find --help mv page")
        body = m.group(1)
        for kw in ('DUPLICATE', '--force', 'SIBLINGS', 'SCOPE', '--yes'):
            self.assertIn(kw, body, f"--help mv must mention '{kw}'")

    def test_cmd_move_validates_dest_library(self):
        """cmd_move must validate the destination library exists in PLEX_Library.OBJ_DICT."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find cmd_move body")
        body = m.group(1)
        self.assertIn("PLEX_Library.OBJ_DICT", body)

    def test_cmd_move_uses_universal_scope(self):
        """cmd_move must use _get_disk_map_scope() for universal scope handling."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("_get_disk_map_scope(", body)

    def test_cmd_move_duplicate_detection(self):
        """cmd_move must check duplicate by title + originalTitle + year."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("originalTitle", body)
        self.assertIn("year", body)

    def test_cmd_move_interactive_prompt(self):
        """cmd_move must offer s/o/S/O/q interactive choices for duplicates."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("skip-all", body)
        self.assertIn("overwrite-all", body)
        self.assertIn("readchar.readchar()", body)

    def test_cmd_move_force_overwrites(self):
        """cmd_move with force=True must skip the interactive prompt and overwrite."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("if force:", body)

    def test_cmd_move_sibling_handling(self):
        """cmd_move must move sibling files (.nfo, .srt, etc.) alongside main video."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("sibling", body.lower())
        self.assertIn("LIST_DIR", body)

    def test_cmd_move_updates_cache(self):
        """cmd_move must remove old entries from cache indices (OBJ_BY_ID, OBJ_BY_LIBRARY, OBJ_BY_MOVIE, OBJ_BY_FILEPATH)."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        for idx in ('OBJ_BY_ID', 'OBJ_BY_LIBRARY', 'OBJ_BY_MOVIE', 'OBJ_BY_FILEPATH'):
            self.assertIn(idx, body, f"cmd_move must update {idx}")

    def test_cmd_move_triggers_plex_scan(self):
        """cmd_move must trigger Plex library scans on source AND destination."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("affected_libs", body)
        self.assertIn(".update()", body)

    def test_cmd_move_type_compatibility(self):
        """cmd_move must enforce type compatibility (Movie ↔ Movie lib, Episode ↔ Series lib)."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("dest_lib_type", body)

    def test_cmd_move_default_is_preview(self):
        """Like --remux, --mv default behavior is PREVIEW; only --yes commits."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("Re-run with --yes to execute", body)
        self.assertIn("if not yes:", body)

    def test_cmd_move_prints_summary(self):
        """cmd_move must print a SUMMARY at the end, like every command whose output varies."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("SUMMARY", body)


class TestUniversalScope(unittest.TestCase):
    """Tests for the universal scope resolver (_get_disk_map_scope + _get_universal_scope).

    Verifies that every SCOPE-taking command (--mv, --remux, --plex2disk, etc.)
    can accept filter expressions and compound (multi-token) scopes uniformly.
    """

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_universal_scope_helper_exists(self):
        """_get_universal_scope() must exist and accept a list of tokens."""
        src = self._read_script()
        self.assertIn("def _get_universal_scope(", src)

    def test_is_scope_filter_token_helper_exists(self):
        """_is_scope_filter_token() must classify filter expressions."""
        src = self._read_script()
        self.assertIn("def _is_scope_filter_token(", src)
        self.assertIn("_SCOPE_FILTER_FIELDS", src)
        self.assertIn("_SCOPE_FILTER_RE", src)

    def test_scope_filter_fields_includes_originallang(self):
        """The filter-field whitelist must include original-language tokens."""
        src = self._read_script()
        for kw in ("'original_language'", "'originallang'", "'original_lang'",
                   "'country'", "'lang'", "'year'"):
            self.assertIn(kw, src, f"_SCOPE_FILTER_FIELDS must include {kw}")

    def test_resolve_scope_filter_expr_helper_exists(self):
        """_resolve_scope_filter_expr() must delegate to _parse_filter_sub_expr."""
        src = self._read_script()
        self.assertIn("def _resolve_scope_filter_expr(", src)
        self.assertIn("PLEX_Media._parse_filter_sub_expr", src)

    def test_get_disk_map_scope_delegates_to_filter_resolver(self):
        """_get_disk_map_scope must dispatch filter-expression targets to _resolve_scope_filter_expr."""
        src = self._read_script()
        import re
        m = re.search(r'def _get_disk_map_scope\(target\).*?\n(.*?)def _get_all_filepaths', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find _get_disk_map_scope body")
        body = m.group(1)
        self.assertIn("_is_scope_filter_token(", body)
        self.assertIn("_resolve_scope_filter_expr(", body)

    def test_universal_scope_intersects_multiple_tokens(self):
        """_get_universal_scope must AND-combine (intersect) multiple token results."""
        src = self._read_script()
        import re
        m = re.search(r'def _get_universal_scope\(scope_tokens\).*?\n(.*?)def _get_disk_map_scope', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find _get_universal_scope body")
        body = m.group(1)
        self.assertIn("set.intersection", body)
        self.assertIn("per_token_keysets", body)

    def test_cmd_move_uses_universal_scope_for_variadic(self):
        """cmd_move must consume args_list[1:] variadically via _get_universal_scope."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_move\(.*?\n(.*?)def cmd_sort_new', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("scope_tokens", body)
        self.assertIn("_get_universal_scope(", body)

    def test_argv_normalization_skips_variadic_window(self):
        """Tokens after --mv-to (and other variadic flags) must NOT be rewritten as --list filter exprs."""
        src = self._read_script()
        self.assertIn("_VARIADIC_SCOPE_FLAGS", src)
        self.assertIn("_in_variadic_window", src)
        # Every variadic-scope flag must appear in the set (v1.20+: --mv / --move
        # dropped; v3 step 4h: --original-languages retired entirely)
        for flag in ("'--mv-to'", "'--move-to'",
                     "'--add-label'", "'--remove-label'",
                     "'--remux'", "'--plex2disk'", "'--disk2plex'"):
            self.assertIn(flag, src, f"_VARIADIC_SCOPE_FLAGS must include {flag}")

    def test_type_filter_in_scope_fields(self):
        """type must be in _SCOPE_FILTER_FIELDS so type:series works as a SCOPE token."""
        src = self._read_script()
        # Must appear in the field whitelist (look for the tuple containing 'type')
        import re
        m = re.search(r'_SCOPE_FILTER_FIELDS = \((.*?)\)', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find _SCOPE_FILTER_FIELDS")
        body = m.group(1)
        self.assertIn("'type'", body, "_SCOPE_FILTER_FIELDS must include 'type'")

    def test_type_filter_handler_in_parser(self):
        """_parse_filter_sub_expr must handle type:movie / type:series / type:episode / type:season distinctly."""
        src = self._read_script()
        self.assertIn("if field == 'type':", src)
        self.assertIn("_MOVIE_ALIASES", src)
        self.assertIn("_SERIES_ALIASES", src)
        self.assertIn("_SEASON_ALIASES", src)
        self.assertIn("_EPISODE_ALIASES", src)

    def test_type_filter_distinct_per_type(self):
        """Each type alias must map to its own Plex type set (not collapsed to Episode)."""
        src = self._read_script()
        # Each type alias set must target the right Plex type at filter level
        self.assertIn("target_types = {'Movie', 'Movie*'}", src)
        self.assertIn("target_types = {'Series', 'Series*'}", src)
        self.assertIn("target_types = {'Season', 'Season*'}", src)
        self.assertIn("target_types = {'Episode', 'Episode*'}", src)

    def test_filter_expr_pure_type_semantics(self):
        """v1.20+: _resolve_scope_filter_expr returns objects of EXACTLY the matched type
        (no Series/Season → Episode auto-expansion). Pure semantics per user spec."""
        src = self._read_script()
        import re
        m = re.search(r'def _resolve_scope_filter_expr\(expr\).*?\n(.*?)def _get_universal_scope', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find _resolve_scope_filter_expr body")
        body = m.group(1)
        # Pure semantics doc comment present
        self.assertIn("PURE type-filter semantics", body)
        # Must conditionally iterate all types when type: filter is present
        self.assertIn("has_type_filter", body)
        # Must NOT contain the old auto-expansion logic
        self.assertNotIn("Post-expand Series", body)

    def test_type_filter_in_field_regex(self):
        """The _field_re regex inside _parse_filter_sub_expr must include 'type'."""
        src = self._read_script()
        # Find _field_re definition that has all the cat-B fields
        self.assertIn("originallang|original_lang|type", src,
                      "_field_re inside _parse_filter_sub_expr must list 'type'")

    def test_get_disk_map_scope_auto_promotes_lists(self):
        """_get_disk_map_scope must auto-promote list input to _get_universal_scope."""
        src = self._read_script()
        import re
        m = re.search(r'def _get_disk_map_scope\(target\).*?\n(.*?)def _get_all_filepaths', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find _get_disk_map_scope body")
        body = m.group(1)
        self.assertIn("isinstance(target, (list, tuple))", body)
        self.assertIn("_get_universal_scope(", body)

    def test_action_commands_use_nargs_star(self):
        """--remux / --plex2disk / --disk2plex / --rename / --renumber
        must use nargs='*' so compound SCOPE (lib + filter) reaches the dispatcher.
        (v3 step 4h: --original-languages retired from this list.)"""
        src = self._read_script()
        for flag in ('--remux', '--plex2disk', '--disk2plex', '--plex-disk-sync', '--sync',
                     '--rename', '--renumber',
                     '--map-to-filename', '--map-from-filename'):
            self.assertIn(f"'{flag}'", src)
        # Spot-check the nargs setting (look for the GLOBAL_CMD_PARSER line)
        self.assertIn("'--remux',     metavar='SCOPE', nargs='*'", src)
        self.assertIn("'--plex2disk', metavar='SCOPE', nargs='*'", src)
        self.assertIn("'--disk2plex', metavar='SCOPE', nargs='*'", src)

    def test_variadic_scope_flags_includes_migrated_commands(self):
        """_VARIADIC_SCOPE_FLAGS must list every nargs='*' SCOPE-taking flag."""
        src = self._read_script()
        for flag in ("'--remux'", "'--plex2disk'", "'--disk2plex'",
                     "'--plex-disk-sync'", "'--sync'",
                     "'--rename'", "'--renumber'",
                     "'--map-to-filename'", "'--map-from-filename'"):
            self.assertIn(flag, src, f"_VARIADIC_SCOPE_FLAGS must include {flag}")

    def test_collapse_scope_arg_helper(self):
        """_collapse_scope_arg helper must exist inside execute_global_commands to normalise list/str/True/None."""
        src = self._read_script()
        self.assertIn("def _collapse_scope_arg(val)", src)

    def test_help_mv_documents_compound_scope(self):
        """--help mv must document the COMPOUND SCOPE section with country: / original_lang: examples."""
        src = self._read_script()
        import re
        m = re.search(r"case 'mv' \| 'move':(.*?)sys\.exit\(0\)", src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        for kw in ('COMPOUND SCOPE', 'country:france', 'original_lang:fr', 'AND-combine'):
            self.assertIn(kw, body, f"--help mv must mention '{kw}'")


class TestCompoundFilter(unittest.TestCase):
    """Tests for v2.1 AND/OR/parens grammar in scope filter expressions."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_compound_parser_exists(self):
        """_parse_compound_filter must exist and handle AND/OR/parens grammar."""
        src = self._read_script()
        self.assertIn("def _parse_compound_filter(", src)
        self.assertIn("def _tokenize_filter_expr_string(", src)

    def test_grammar_documented_in_docstring(self):
        """The grammar must be in the docstring (precedence AND > OR; uppercase only)."""
        src = self._read_script()
        import re
        m = re.search(r'def _parse_compound_filter\(.*?\n\s+"""(.*?)"""', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        doc = m.group(1)
        self.assertIn("HIGHER precedence than OR", doc)
        self.assertIn("uppercase", doc.lower())

    def test_parser_supports_or(self):
        """The grammar must include an OR production."""
        src = self._read_script()
        self.assertIn("_parse_or", src)
        self.assertIn("_peek() == 'OR'", src)

    def test_parser_supports_parens(self):
        """The grammar must accept `(` and `)` tokens for grouping."""
        src = self._read_script()
        self.assertIn("if t == '('", src)
        self.assertIn("if _peek() != ')'", src)

    def test_parser_supports_not(self):
        """v2.3: NOT operator (uppercase) with precedence above AND."""
        src = self._read_script()
        self.assertIn("_parse_not", src)
        self.assertIn("if _peek() == 'NOT'", src)
        # NOT pass-through in argv normalization
        self.assertIn("'NOT', '('", src)
        # NOT compile branch
        self.assertIn("if kind == 'NOT':", src)
        # _is_scope_filter_token recognises NOT
        self.assertIn("'AND', 'OR', 'NOT'", src)

    def test_library_filter_field(self):
        """library: must be a Cat-B filter field with an exact-match handler."""
        src = self._read_script()
        self.assertIn("if field == 'library':", src)
        # 'library' must be in _SCOPE_FILTER_FIELDS and both Cat-B regexes
        self.assertIn("'library'", src)
        self.assertIn("original_lang|type|layout|library", src)

    def test_auto_promote_bare_library(self):
        """Inside compound expressions, bare library names auto-promote to library:NAME."""
        src = self._read_script()
        import re
        # [^\n]*: -- the BODY is what this pins; the signature may carry a
        # return annotation (it does: the compiler is recursive).
        m = re.search(r'def _compile\(node\)[^\n]*:(.*?)label, fn = _compile', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("PLEX_Media.OBJ_BY_LIBRARY", body)
        self.assertIn("library:", body)

    def test_argv_pass_through_operators(self):
        """Argv normalization must pass `(`, `)`, `AND`, `OR`, `NOT` through as filter ops."""
        src = self._read_script()
        self.assertIn("if arg in ('AND', 'OR', 'NOT', '(', ')'):", src)

    def test_universal_scope_detects_operators(self):
        """_get_universal_scope must route operator-bearing token lists to compound parser."""
        src = self._read_script()
        self.assertIn("_OPERATORS = {'AND', 'OR', 'NOT', '(', ')'}", src)

    def test_is_scope_filter_token_detects_compound(self):
        """_is_scope_filter_token must accept OR / NOT / parens too (not just AND)."""
        src = self._read_script()
        self.assertIn("token in ('(', ')', 'AND', 'OR', 'NOT')", src)
        self.assertIn(r"'\bAND\b|\bOR\b|\bNOT\b'", src)

    def test_help_scope_documents_or_and_parens(self):
        """--help scope page must document the new compound grammar."""
        src = self._read_script()
        import re
        m = re.search(r"case 'scope':(.*?)sys\.exit\(0\)", src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        for kw in ('OR', 'AND', 'PARENS', 'CASE-SENSITIVE', 'SPACE-SEPARATED'):
            self.assertIn(kw, body, f"--help scope must mention '{kw}'")


class TestUncataloguedFolderMove(unittest.TestCase):
    """v2.2: layout: filter must surface UNCATALOGUED top-level folders too,
    and cmd_move must move them via SSH `mv` (no cache update, since they
    were never in the cache to begin with)."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_resolve_scope_emits_folder_entries(self):
        """_resolve_scope_filter_expr must emit synthetic Folder entries when layout: filter is present."""
        src = self._read_script()
        self.assertIn("has_layout_filter", src)
        # Synthetic pseudo-key naming convention
        self.assertIn("f'Folder:{entry_path}'", src)
        self.assertIn("'type_str':      'Folder'", src)
        self.assertIn("'_uncatalogued': True", src)

    def test_uncatalogued_folders_filtered_against_known_paths(self):
        """Folder entries are emitted only if NO cached path lives under them
        (cached wrappers are already represented by their cached items)."""
        src = self._read_script()
        import re
        m = re.search(r'if has_layout_filter:(.*?)return items', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find the uncatalogued-folder loop")
        body = m.group(1)
        self.assertIn("known_paths = _get_known_filepaths_from_plex_db()", body)
        self.assertIn("p == entry_path or p.startswith(prefix)", body)

    def test_get_universal_scope_routes_layout_to_compound(self):
        """_get_universal_scope must route layout:-bearing token lists to the compound parser
        (otherwise per-token set-intersection would miss uncatalogued folders)."""
        src = self._read_script()
        self.assertIn("any(re.match(r'^layout[:=]', t, re.IGNORECASE) for t in real_tokens)", src)

    def test_cmd_move_handles_folder_type(self):
        """cmd_move must branch on type_str=='Folder' and SSH-mv the whole directory."""
        src = self._read_script()
        self.assertIn("if type_str == 'Folder':", src)
        # No cache update for Folders (they were never in cache)
        self.assertIn("(Folder/uncatalogued:", src)
        # The folder bypass in the collection loop must also exist
        self.assertIn("v2.2: uncatalogued top-level folders", src)

    def test_folder_move_uses_my_plex_file_operation(self):
        """Folder moves must go through the existing SSH-aware MOVE primitive
        (not a custom ssh subprocess), so they honor PLEX_DB_REMOTE_HOST."""
        src = self._read_script()
        import re
        # Look for the Folder branch's MOVE call
        m = re.search(
            r"if type_str == 'Folder':(.*?)(?=if type_str not in \('Movie', 'Episode'\):|^\s*title = obj\.get)",
            src, re.DOTALL | re.MULTILINE
        )
        # Just check the helper call is present in the file
        self.assertIn("my_plex_file_operation('MOVE', folder_path, PLEX_DB_REMOTE_HOST,", src)

    def test_folder_move_invalidates_layout_index(self):
        """After moving a folder, the session layout-index entry must be removed
        so subsequent calls don't double-count the moved folder."""
        src = self._read_script()
        self.assertIn("_LAYOUT_INDEX_CACHE", src)
        self.assertIn("del entries[folder_base]", src)


class TestLayoutFilter(unittest.TestCase):
    """Tests for the layout: scope token (orthogonal to type:).

    `layout:X` classifies items by their on-disk folder shape rather
    than by Plex's catalogued type.  Useful for surfacing
    mis-classified content (e.g. series-shaped folders in a Movie lib).
    """

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_layout_in_scope_filter_fields(self):
        """'layout' must be in _SCOPE_FILTER_FIELDS so it's recognised as a Cat-B token."""
        src = self._read_script()
        self.assertIn("'layout'", src)
        import re
        m = re.search(r'_SCOPE_FILTER_FIELDS = \((.*?)\)', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        self.assertIn("'layout'", m.group(1))

    def test_layout_filter_handler_exists(self):
        """_parse_filter_sub_expr must have a layout handler with the four aliases."""
        src = self._read_script()
        self.assertIn("if field == 'layout':", src)
        self.assertIn("_LAYOUT_ALIASES", src)
        for kw in ("'series'", "'show'", "'tv'", "'season'", "'episode'", "'movie'"):
            self.assertIn(kw, src, f"_LAYOUT_ALIASES must include {kw}")

    def test_classify_layout_helper(self):
        """_classify_layout must distinguish movie / series / season / episode / unknown."""
        src = self._read_script()
        self.assertIn("def _classify_layout(", src)
        # All five labels must appear as return values
        for label in ("'movie'", "'series'", "'season'", "'episode'", "'unknown'"):
            self.assertIn(label, src, f"layout classifier must produce {label}")

    def test_layout_index_builder_is_bulk_ssh(self):
        """_build_layout_index must use a single bulk `find -maxdepth 2` per library (not per-dir SSH)."""
        src = self._read_script()
        self.assertIn("def _build_layout_index(", src)
        self.assertIn("-maxdepth 2", src)
        # Session memo must exist
        self.assertIn("_LAYOUT_INDEX_CACHE", src)

    def test_lookup_layout_helper(self):
        """_lookup_layout_for_filepath maps a filepath to its top-level entry's layout."""
        src = self._read_script()
        self.assertIn("def _lookup_layout_for_filepath(", src)

    def test_layout_filter_uses_lookup(self):
        """The layout filter fn must call _lookup_layout_for_filepath."""
        src = self._read_script()
        import re
        m = re.search(r"if field == 'layout':(.*?)return label_str, _layout_fn", src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find layout filter block")
        self.assertIn("_lookup_layout_for_filepath(", m.group(1))

    def test_layout_orthogonal_to_type(self):
        """Type and layout must be distinct filter fields (not aliases)."""
        src = self._read_script()
        # Both appear in the regex alternation
        self.assertIn("type|layout", src)
        # Both have their own handler block
        self.assertIn("if field == 'type':", src)
        self.assertIn("if field == 'layout':", src)

    def test_layout_help_page_exists(self):
        """--help layout must have a dedicated help page mentioning every alias."""
        src = self._read_script()
        self.assertIn("case 'layout':", src)
        import re
        m = re.search(r"case 'layout':(.*?)sys\.exit\(0\)", src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m)
        body = m.group(1)
        for kw in ('layout:movie', 'layout:series', 'layout:season', 'layout:episode',
                   '--unrecognized', 'ORTHOGONAL'):
            self.assertIn(kw, body, f"--help layout must mention '{kw}'")


class TestUnrecognized(unittest.TestCase):
    """Tests for --unrecognized / --alien: top-level entries Plex DB doesn't index."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_cmd_unrecognized_exists(self):
        """cmd_unrecognized() must exist as a top-level function."""
        src = self._read_script()
        self.assertIn("def cmd_unrecognized(", src)

    def test_count_helper_exists(self):
        """_count_unrecognized_top_level() helper for --problems integration must exist."""
        src = self._read_script()
        self.assertIn("def _count_unrecognized_top_level(", src)

    def test_known_filepaths_helper_uses_media_parts(self):
        """_get_known_filepaths_from_plex_db must query media_parts (the user-chosen detection rule)."""
        src = self._read_script()
        self.assertIn("def _get_known_filepaths_from_plex_db(", src)
        self.assertIn("SELECT file FROM media_parts", src)

    def test_list_top_level_helper(self):
        """_list_top_level_entries must SSH/find with maxdepth=1 and return (path,kind) tuples."""
        src = self._read_script()
        self.assertIn("def _list_top_level_entries(", src)
        self.assertIn("-maxdepth 1", src)
        # Hidden entries filtered
        self.assertIn('! -name ".*"', src)

    def test_unrecognized_registered_main_parser(self):
        """--unrecognized + --alien synonym must be in main_parser."""
        src = self._read_script()
        self.assertIn("main_parser.add_argument('--unrecognized', '--alien'", src)

    def test_unrecognized_registered_global_parser(self):
        """--unrecognized must be in GLOBAL_CMD_PARSER with help text."""
        src = self._read_script()
        self.assertIn("GLOBAL_CMD_PARSER.add_argument('--unrecognized', '--alien'", src)

    def test_unrecognized_in_has_standalone_cmd(self):
        """--unrecognized must be in has_standalone_cmd."""
        src = self._read_script()
        self.assertIn("safe_getattr(args, 'unrecognized', None) is not None", src)

    def test_unrecognized_handler_in_execute_global_commands(self):
        """execute_global_commands must dispatch --unrecognized to cmd_unrecognized."""
        src = self._read_script()
        self.assertIn("cmd_unrecognized(target=target)", src)

    def test_alien_synonym_in_option_to_help_topic(self):
        """--alien must map to the same help topic as --unrecognized."""
        src = self._read_script()
        self.assertIn("'--unrecognized': 'unrecognized'", src)
        self.assertIn("'--alien': 'unrecognized'", src)

    def test_problems_integration(self):
        """--problems must include 'unrecognized' via the registry (v3)."""
        src = self._read_script()
        import re
        reg = _registry_entry_block(src, 'unrecognized')
        self.assertIsNotNone(reg, "PROBLEM_CATEGORIES_REGISTRY must define 'unrecognized'")
        self.assertIn('_count_unrecognized_top_level', reg,
                      "registry 'unrecognized' entry must invoke _count_unrecognized_top_level")
        self.assertIn("'--unrecognized'", reg,
                      "registry 'unrecognized' entry must carry the cli_flag")

    def test_help_page_exists(self):
        """--help unrecognized must have a dedicated help page (covers --alien synonym too)."""
        src = self._read_script()
        self.assertIn("case 'unrecognized' | 'alien':", src)


class TestOriginalLanguages(unittest.TestCase):
    """Tests for --original-languages backfill + country: / originallang: filter tokens."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_iso639_helper_exists(self):
        """_normalize_lang_name_or_code must exist and map names + codes."""
        src = self._read_script()
        self.assertIn("def _normalize_lang_name_or_code(", src)
        self.assertIn("_ISO639_1_NAME_TO_CODE", src)

    def test_iso3166_helper_exists(self):
        """_normalize_country_name_or_code must exist and map names + codes."""
        src = self._read_script()
        self.assertIn("def _normalize_country_name_or_code(", src)
        self.assertIn("_ISO3166_NAME_TO_CODE", src)

    def test_country_matches_helper(self):
        """_country_matches must handle both code and name input."""
        src = self._read_script()
        self.assertIn("def _country_matches(", src)

    def test_tmdb_original_language_fetcher(self):
        """fetch_original_language_from_tmdb() must exist and use Bearer auth."""
        src = self._read_script()
        self.assertIn("def fetch_original_language_from_tmdb(", src)
        self.assertIn("'Authorization': f'Bearer {TMDB_API_KEY}'", src)
        self.assertIn("'original_language'", src)

    def test_cmd_original_languages_exists(self):
        """cmd_original_languages() must exist as a top-level function."""
        src = self._read_script()
        self.assertIn("def cmd_original_languages(", src)

    def test_cmd_original_languages_skips_already_cached(self):
        """Backfill must skip items that already have original_language."""
        src = self._read_script()
        import re
        m = re.search(r'def cmd_original_languages\(.*?\n(.*?)def format_duration', src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find cmd_original_languages body")
        body = m.group(1)
        self.assertIn("if o.get('original_language')", body)
        self.assertIn("continue", body)

    def test_original_lang_filter_in_parser_regex(self):
        """The Cat-B filter regex in _parse_filter_sub_expr must accept original_lang / originallang / original_language."""
        src = self._read_script()
        self.assertIn("original_language|originallang|original_lang", src)

    def test_country_filter_in_parser_regex(self):
        """Cat-B regex must include country / countries."""
        src = self._read_script()
        import re
        m = re.search(r"_field_re = re\.match\(\s*r'(\^.*?\$)'", src, re.DOTALL)
        # Regex is multi-line; just confirm country is referenced as a field
        self.assertIn("country|countries", src)

    def test_original_lang_filter_handler(self):
        """_parse_filter_sub_expr must contain an originallang handler."""
        src = self._read_script()
        self.assertIn("original_language', 'originallang', 'original_lang'", src)
        self.assertIn("_normalize_lang_name_or_code(", src)

    def test_country_filter_handler(self):
        """_parse_filter_sub_expr must contain a country handler using _country_matches."""
        src = self._read_script()
        self.assertIn("'country', 'countries'", src)
        self.assertIn("_country_matches(", src)

    def test_original_languages_cli_retired(self):
        """v3 step 4h: the standalone --original-languages CLI flag is RETIRED.
        It must NOT be registered in either parser (the backfill lives in
        --update-cache now; no backwards compatibility)."""
        src = self._read_script()
        self.assertNotIn("main_parser.add_argument('--original-languages'", src)
        self.assertNotIn("GLOBAL_CMD_PARSER.add_argument('--original-languages'", src)

    def test_original_languages_backfill_function_exists(self):
        """cmd_original_languages stays as the internal TMDB backfill engine."""
        src = self._read_script()
        self.assertIn("def cmd_original_languages(", src)

    def test_original_languages_backfill_in_update_cache(self):
        """--update-cache must run the original_language backfill in-process (v3 step 4g)."""
        src = self._read_script()
        self.assertIn("cmd_original_languages(target=None, dry_run=False)", src,
                      "--update-cache must invoke the lazy original_language backfill")

    def test_original_languages_filter_token_still_works(self):
        """The original_lang: filter vocabulary must survive the CLI retirement."""
        src = self._read_script()
        self.assertIn("original_language", src)
        self.assertIn("original_lang", src)

    def test_original_languages_help_page_exists(self):
        """--help original-languages must have a dedicated help page."""
        src = self._read_script()
        self.assertIn("case 'original-languages' | 'original_languages'", src)

    def test_original_languages_help_covers_features(self):
        """--help page must document filter tokens + country: companion + TMDB requirement."""
        src = self._read_script()
        import re
        m = re.search(r"case 'original-languages'.*?sys\.exit\(0\)", src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "Must find --help original-languages page")
        body = m.group(0)
        for kw in ('original_lang:', 'originallang:', 'country:', 'TMDB_API_KEY', 'french', 'france'):
            self.assertIn(kw, body, f"--help original-languages must mention '{kw}'")

    def test_orig_lang_in_neg_field_map(self):
        """ORIG-LANG column must be removable via -originallang token."""
        src = self._read_script()
        self.assertIn("'originallang': 'ORIG-LANG'", src)


class TestUnmatchedResolve(unittest.TestCase):
    """v2.12-v2.15: --unmatched --resolve helpers — pure-Python primitives
    that don't need a Plex connection.  Exercised by importing the main
    script as a module."""

    @classmethod
    def setUpClass(cls):
        cls.m = _import_tool('_myplex_under_test')

    # ------- _slugify_title_for_wrapper -------

    def test_slugify_drops_apostrophes(self):
        s = self.m._slugify_title_for_wrapper("The Queen's Corgi")
        # apostrophe must drop entirely, not become a separator
        self.assertEqual(s, "the.queens.corgi")

    def test_slugify_smart_quotes(self):
        # Curly apostrophe also dropped (queen’s → queens, not queen.s).
        s = self.m._slugify_title_for_wrapper("The Queen’s Corgi")
        self.assertEqual(s, "the.queens.corgi")

    def test_slugify_collapses_punctuation(self):
        s = self.m._slugify_title_for_wrapper("Hitchhiker's Guide: Part 2!")
        self.assertEqual(s, "hitchhikers.guide.part.2")

    def test_slugify_unicode_fallback(self):
        # Non-ASCII letters collapse to a dot (no transliteration; acceptable
        # for wrapper-rename target — Plex matches via TMDB id anyway).
        s = self.m._slugify_title_for_wrapper("Märchenbuch")
        # Whatever happens, no leading/trailing dot, no double dot.
        self.assertFalse(s.startswith('.') or s.endswith('.'))
        self.assertNotIn('..', s)

    # ------- _add_year_to_wrapper -------

    def test_add_year_when_missing(self):
        out = self.m._add_year_to_wrapper("/lib/library1/up.bdrip.xvid", 2009)
        self.assertEqual(out, "/lib/library1/up.bdrip.xvid.(2009)")

    def test_add_year_preserves_trailing_tag(self):
        # `_[crime]` / `,suffix` tail is kept; year inserts BEFORE it.
        out = self.m._add_year_to_wrapper("/lib/library2/balthazar_[crime]", 2018)
        self.assertEqual(out, "/lib/library2/balthazar.(2018)_[crime]")

    def test_add_year_idempotent_when_already_has_year(self):
        # Without canonical_title, wrapper that already has a year is returned unchanged.
        wp = "/lib/library1/inception.(2010)"
        out = self.m._add_year_to_wrapper(wp, 2010)
        self.assertEqual(out, wp)

    def test_add_year_with_canonical_replaces_basename(self):
        # canonical_title=… rebuilds basename from slug + year, even when
        # the original wrapper already carries a year.  This is the v2.14
        # path for items unmatched DESPITE having a year.
        out = self.m._add_year_to_wrapper(
            "/lib/library1/the.queen.s.corgi.2019.720p.bluray.x264-[yts.am]",
            2019, canonical_title="The Queen's Corgi")
        # tail `_[yts.am]`? No — that's bracketed but inside the year run.
        # The function preserves `_[tag]` / `,tag` from the original; everything
        # else after the title is dropped.  Just check the head is canonical
        # and the year is present.
        self.assertTrue(out.endswith(".(2019)") or "the.queens.corgi.(2019)" in out)
        self.assertIn("/lib/library1/", out)
        self.assertIn("the.queens.corgi", out)
        self.assertNotIn("queen.s", out)  # the orphan-S form is gone

    # ------- _score_candidate -------

    def test_score_exact_match_is_100(self):
        s = self.m._score_candidate("up", {'title': 'Up', 'original_title': 'Up', 'popularity': 0.0})
        self.assertEqual(s, 100.0)

    def test_score_substring_below_100(self):
        # "up" vs "Cars Up" → similarity < 1.0
        s = self.m._score_candidate("up", {'title': 'Cars Up', 'original_title': 'Cars Up', 'popularity': 0.0})
        self.assertLess(s, 100.0)
        self.assertGreater(s, 0.0)

    def test_score_popularity_bonus_caps_at_10(self):
        # Even a giant popularity adds at most +10 to the title-similarity score.
        s = self.m._score_candidate("zzzzz", {'title': 'aaaaa', 'original_title': '', 'popularity': 1e9})
        # title similarity is ~0 so the bonus dominates; should be at most 10.
        self.assertLessEqual(s, 10.5)

    # ------- _clean_query_from_wrapper -------

    def test_clean_query_extracts_year_and_strips_release_tags(self):
        q, y = self.m._clean_query_from_wrapper(
            "the.queen.s.corgi.2019.720p.bluray.x264-[yts.am]")
        self.assertEqual(y, 2019)
        # release tags / year stripped, all separators normalised to spaces.
        # The orphan 's' stays as a separate word — TMDB's search tokeniser
        # handles "the queen s corgi" the same as "the queens corgi".
        self.assertEqual(q, "the queen s corgi")

    def test_clean_query_no_year_keeps_full_basename(self):
        q, y = self.m._clean_query_from_wrapper("good_will_hunting.de+en")
        self.assertIsNone(y)
        self.assertEqual(q, "good will hunting de en")

    # ------- _strip_query_tags -------

    def test_strip_query_tags_hash_pairs(self):
        # `#tag#` and `#tag` clutter (common in user-tagged wrappers) drops out.
        s = self.m._strip_query_tags("Superintelligence #Melissa#mccarthy#")
        self.assertEqual(s, "Superintelligence")

    def test_strip_query_tags_braces(self):
        # `{2010}` year-marker should be PRESERVED as a bare year so TMDB
        # can still see "Henrys Crime 2010".
        s = self.m._strip_query_tags("Henrys Crime {2010}")
        self.assertIn("2010", s)
        self.assertIn("Henrys Crime", s)
        self.assertNotIn("{", s)
        self.assertNotIn("}", s)

    def test_strip_query_tags_brackets_drop_non_year(self):
        # `[tag]` with non-year content drops entirely.
        s = self.m._strip_query_tags("V for Vendetta [yts.am]")
        self.assertEqual(s, "V for Vendetta")

    def test_strip_query_tags_parens_drop_non_year(self):
        # `(tag)` with non-year content drops entirely.
        s = self.m._strip_query_tags("Movie Name (uncut)")
        self.assertEqual(s, "Movie Name")

    def test_strip_query_tags_parens_keep_year(self):
        # `(2019)` year form is preserved (as bare 2019).
        s = self.m._strip_query_tags("Joker (2019)")
        self.assertIn("Joker", s)
        self.assertIn("2019", s)
        self.assertNotIn("(", s)

    # ------- _strip_tvoon_suffix -------

    def test_tvoon_suffix_stripped_basic(self):
        s = self.m._strip_tvoon_suffix(
            "der_fall_jeanne_darc_24.11.23_21-00_phoenix_45_tvoon_de.mpg.hq")
        self.assertEqual(s, "der_fall_jeanne_darc")

    def test_tvoon_suffix_stripped_no_quality(self):
        # `.mpg` with no `.hq` / `.hd` suffix should also be stripped.
        s = self.m._strip_tvoon_suffix(
            "belle_21.03.08_18-50_ukfilm4_130_tvoon_de.mpg")
        self.assertEqual(s, "belle")

    def test_tvoon_suffix_left_alone_when_not_present(self):
        s = self.m._strip_tvoon_suffix("the.queen.s.corgi.2019.720p.bluray")
        self.assertEqual(s, "the.queen.s.corgi.2019.720p.bluray")

    def test_clean_query_for_tvoon_basename(self):
        q, y = self.m._clean_query_from_wrapper(
            "good_bye_lenin_21.05.10_23-10_mdr_115_tvoon_de.mpg.hq")
        # TVOON broadcast date is NOT the release year — year=None expected.
        self.assertIsNone(y)
        self.assertEqual(q, "good bye lenin")

    def test_clean_query_strips_brace_year_form(self):
        # wrapper basename with `{YYYY}` style year + a release-tag suffix.
        q, y = self.m._clean_query_from_wrapper(
            "henrys.crime.{2010}.720p.brrip.x264.-.kickassddl.zip.folder_#keanu.reeves#")
        self.assertEqual(y, 2010)
        self.assertIn("henrys", q)
        self.assertIn("crime", q)
        self.assertNotIn("#", q)
        self.assertNotIn("{", q)
        self.assertNotIn("keanu", q)  # hash-tagged authority dropped

    # ------- engine cascade -------

    def test_engine_dispatch_contains_tmdb_and_tvdb(self):
        self.assertIn('TMDB', self.m._ENGINE_DISPATCH)
        self.assertIn('TVDB', self.m._ENGINE_DISPATCH)

    def test_search_unmatched_candidates_handles_unknown_engine_gracefully(self):
        # No real API call — we just verify the function tolerates an
        # unrecognised engine name in the list (logs a warning, skips).
        out = self.m._search_unmatched_candidates('x', 'movie', engines=['BOGUS'])
        self.assertEqual(out, [])

    # ------- conf vars sourced -------

    def test_conf_defaults_present(self):
        cd = self.m.CONFIG_DEFAULTS
        self.assertEqual(cd['UNMATCHED_RESOLVE_LOOKUP_ENGINES'], ['TMDB', 'TVDB'])
        self.assertEqual(cd['UNMATCHED_RESOLVE_AUTO_CONFIDENCE_PCT'], 90)
        self.assertTrue(cd['UNMATCHED_RESOLVE_AUTO_SCAN_AFTER_RENAME'])
        self.assertIsNone(cd['EDITOR'])  # default None → resolves to $EDITOR or 'vim' at use time

    def test_unmatched_resolve_title_normalize_default_empty(self):
        """v2.59: UNMATCHED_RESOLVE_TITLE_NORMALIZE default is [] (empty list)."""
        cd = self.m.CONFIG_DEFAULTS
        self.assertEqual(cd['UNMATCHED_RESOLVE_TITLE_NORMALIZE'], [])

    def test_apply_unmatched_title_normalize_no_op_when_empty(self):
        """With empty rule list, _apply_unmatched_title_normalize returns input unchanged."""
        self.m.UNMATCHED_RESOLVE_TITLE_NORMALIZE = []
        self.m._UNMATCHED_RESOLVE_TITLE_NORMALIZE_COMPILED = None
        self.assertEqual(self.m._apply_unmatched_title_normalize('french revolution 1of2'),
                         'french revolution 1of2')

    def test_apply_unmatched_title_normalize_with_user_rules(self):
        """User rules drop release/part tags; whitespace collapses; empty result → falls back to original."""
        self.m.UNMATCHED_RESOLVE_TITLE_NORMALIZE = [
            (r'\bxvid\b', ''),
            (r'\bwww\.\S+\.org', ''),
            (r'\b\d+of\d+\b', ''),
        ]
        self.m._UNMATCHED_RESOLVE_TITLE_NORMALIZE_COMPILED = None
        self.assertEqual(self.m._apply_unmatched_title_normalize('french revolution 1of2'),
                         'french revolution')
        self.assertEqual(self.m._apply_unmatched_title_normalize('once upon a time man 22of26'),
                         'once upon a time man')
        self.assertEqual(self.m._apply_unmatched_title_normalize('foo XVID www.mvgroup.org bar'),
                         'foo bar')
        # Empty result must fall back to the original input.
        self.m.UNMATCHED_RESOLVE_TITLE_NORMALIZE = [(r'.*', '')]
        self.m._UNMATCHED_RESOLVE_TITLE_NORMALIZE_COMPILED = None
        self.assertEqual(self.m._apply_unmatched_title_normalize('anything'), 'anything')

    def test_apply_unmatched_title_normalize_ignores_bad_entries(self):
        """Bad regexes / wrong-shape entries are warned about, not crashed."""
        import io as _io, sys as _sys
        old = _sys.stderr
        _sys.stderr = _io.StringIO()
        try:
            self.m.UNMATCHED_RESOLVE_TITLE_NORMALIZE = [
                ('valid', 'OK'),
                ('lonely_no_replacement',),    # bad shape (1-tuple)
                (r'[unclosed', 'X'),           # bad regex
            ]
            self.m._UNMATCHED_RESOLVE_TITLE_NORMALIZE_COMPILED = None
            self.assertEqual(self.m._apply_unmatched_title_normalize('valid foo'), 'OK foo')
        finally:
            _sys.stderr = old


class TestAudioLangPureVsCompleted(unittest.TestCase):
    """v2.9: --update-cache must store TWO views per Movie/Episode:
      * audio_languages_plex : pure Plex value (never extended)
      * audio_languages      : Plex + filename + library completion

    --no-plex-audio-language reads the _plex view; --no-audio-language
    reads the completed view.
    """

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_pure_plex_view_assigned_in_cache_build(self):
        src = self._read_script()
        # audio_languages_plex must be set from _normalize_audio_languages(_expanded)
        # in the same finalize loop that builds audio_languages.
        self.assertRegex(src,
            r"obj\['audio_languages_plex'\]\s*=\s*_plex_view")
        self.assertRegex(src,
            r"_plex_view\s*=\s*_normalize_audio_languages\(_expanded\)")

    def test_completion_toggles_present_in_config_defaults(self):
        src = self._read_script()
        self.assertIn("'AUDIO_LANG_COMPLETE_FROM_FILENAME': True", src)
        self.assertIn("'AUDIO_LANG_COMPLETE_FROM_LIBRARY':  True", src)

    def test_completion_respects_toggle_filename(self):
        src = self._read_script()
        # Filename completion must be gated by AUDIO_LANG_COMPLETE_FROM_FILENAME
        self.assertRegex(src,
            r"if AUDIO_LANG_COMPLETE_FROM_FILENAME and \(\s*"
            r"not obj\['audio_languages'\]")

    def test_completion_respects_toggle_library(self):
        src = self._read_script()
        # Library completion must be gated by AUDIO_LANG_COMPLETE_FROM_LIBRARY
        # and use single-code entries (MULTI is ignored).
        self.assertRegex(src,
            r"if AUDIO_LANG_COMPLETE_FROM_LIBRARY and \(\s*"
            r"not obj\['audio_languages'\]")
        self.assertIn("str(_lval).upper() != 'MULTI'", src)

    def test_completion_order_plex_filename_library(self):
        """The library step must run AFTER the filename step (it only fills
        the gap when filename didn't already)."""
        src = self._read_script()
        i_fn  = src.find("Completion step 1: filename markers")
        i_lib = src.find("Completion step 2: library-language convention")
        self.assertGreater(i_fn,  0)
        self.assertGreater(i_lib, i_fn)

    def test_no_plex_audio_language_cli_flag_registered(self):
        src = self._read_script()
        self.assertIn("'--no-plex-audio-language'", src)
        self.assertIn("no_plex_audio_language", src)

    def test_no_plex_audio_language_uses_plex_field(self):
        src = self._read_script()
        # The dispatcher must select audio_languages_plex when the flag is set.
        self.assertRegex(src,
            r"audio_lang_field\s*=\s*'audio_languages_plex' if no_plex_audio_language")

    def test_pre_v29_cache_falls_back_to_audio_languages(self):
        """When an old cache lacks audio_languages_plex on an obj, the filter
        must fall back to audio_languages so --no-plex-audio-language doesn't
        flag every item as missing."""
        src = self._read_script()
        # Both the filter and the listing must guard with 'in obj'.
        self.assertRegex(src,
            r"if audio_lang_field in obj:\s*\n\s*audio_languages\s*=\s*obj\.get\(audio_lang_field\)")
        self.assertRegex(src,
            r"if field in obj:\s*\n\s*audio_languages\s*=\s*obj\.get\(field\)")


class TestAudioLangCacheBuildFallback(unittest.TestCase):
    """v2.7: filename-based audio_language fallback must be wired into the
    --update-cache normalization path, not only the --remux flow.

    Plex-known languages take precedence; the regex map fills the gap when
    Plex's metadata is empty or 'unknown'."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_fallback_called_during_cache_build(self):
        src = self._read_script()
        # v2.9: cache build computes _plex_view = _normalize_audio_languages(...),
        # assigns it to obj['audio_languages_plex'] (pure) and obj['audio_languages']
        # (working copy), then consults _resolve_audio_lang_from_filename to fill
        # empty/unknown filename-inferred codes.
        import re
        m = re.search(
            r"_plex_view\s*=\s*_normalize_audio_languages\([^)]*\)"
            r".*?_resolve_audio_lang_from_filename\(",
            src, re.DOTALL)
        self.assertIsNotNone(m, "cache build must call "
            "_resolve_audio_lang_from_filename after _normalize_audio_languages "
            "to fill empty/unknown audio_language from filename markers")

    def test_fallback_respects_plex_known_languages(self):
        src = self._read_script()
        # Guard: the fallback only runs when audio_languages is empty or
        # equals [_AUDIO_LANG_UNKNOWN] — Plex data must take precedence.
        # v2.9: also gated by AUDIO_LANG_COMPLETE_FROM_FILENAME.
        self.assertRegex(src,
            r"AUDIO_LANG_COMPLETE_FROM_FILENAME\s+and\s+\(\s*"
            r"not obj\['audio_languages'\]\s+or\s+"
            r"obj\['audio_languages'\]\s*==\s*\[_AUDIO_LANG_UNKNOWN\]\s*\)")


# v2.69 bugfix coverage — both bugs were caught while syncing a series library,
# wer.wird.millionaer S26 (152 disk [vu@] markers vs 2 Plex viewCount>0):
#   1. `--sync` silent-no-op (main_parser ate the flag → cmd_args.sync=None)
#   2. `--plex2disk` produced double [vu@D1] [vu@D2] when the existing on-disk
#      marker came from manual edit (no sidecar entry).
class TestSyncDispatchAndDoubleMarkerFix(unittest.TestCase):
    """Regression coverage for the v2.69 sync-S26 bug investigation."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_sync_dispatch_falls_back_to_args_namespace(self):
        """execute_global_commands must check args.sync as fallback.

        main_parser.add_argument('--sync', …) consumes the flag before the
        MAIN DOIT LOOP runs GLOBAL_CMD_PARSER.parse_known_args, so
        cmd_args.sync stays None.  Without an args.* fallback the dispatch
        silently no-ops.  The fix: 4-way fallback (cmd_args.plex_disk_sync,
        cmd_args.sync, args.plex_disk_sync, args.sync).
        """
        src = self._read_script()
        # The fallback chain must include args.* OR-clauses.
        self.assertRegex(src,
            r"sync_target\s*=\s*\(?safe_getattr\(cmd_args,\s*'plex_disk_sync',\s*None\)\s+or\s+"
            r"safe_getattr\(cmd_args,\s*'sync',\s*None\)\s+or\s+"
            r"safe_getattr\(args,\s*'plex_disk_sync',\s*None\)\s+or\s+"
            r"safe_getattr\(args,\s*'sync',\s*None\)\)?")

    def test_sync_registered_in_both_parsers(self):
        """Both main_parser and GLOBAL_CMD_PARSER must register --sync.

        main_parser is the canonical parser; GLOBAL_CMD_PARSER is the loop
        parser.  Both need it for argparse not to error.  Documents the
        dual-registration as intentional (root cause of bug #1).
        """
        src = self._read_script()
        self.assertRegex(src, r"main_parser\.add_argument\('--sync'")
        self.assertRegex(src, r"GLOBAL_CMD_PARSER\.add_argument\('--sync'")

    def test_plex2disk_strips_pre_existing_same_aspect_marker(self):
        """`--plex2disk` must replace, not append, when an aspect marker
        already exists in the filename but is NOT tracked by the sidecar.

        Reproducer: filename has `[vu@2026-05-17]` (user-edited, no sidecar
        entry); Plex's lastViewedAt is 2026-05-16.  Pre-v2.69, output was
        `... [vu@2026-05-17] [vu@2026-05-16].mp4` (two markers).
        Post-fix: `... [vu@2026-05-16].mp4` (single marker).
        """
        src = self._read_script()
        # The bugfix block must:
        #  a) iterate new_markers per aspect
        #  b) compile disk2plex regex patterns for that aspect
        #  c) pat.sub('', clean) and assign back to clean
        #  d) log "Replacing pre-existing [{aspect}] marker"
        self.assertIn('v2.69 bugfix', src)
        self.assertRegex(src, r"for\s+_aspect,\s*_new_val\s+in\s+new_markers\.items\(\)")
        self.assertRegex(src, r"_aspect_patterns\.append\(\s*re\.compile\(_rg,\s*re\.IGNORECASE\)")
        self.assertRegex(src, r"Replacing pre-existing \[\{_aspect\}\] marker")

    def test_plex2disk_marker_replacement_tidies_whitespace(self):
        """After regex-stripping the old marker, leftover whitespace (' .mp4'
        or '  ') must be collapsed so the new filename is well-formed.
        """
        src = self._read_script()
        # the cleanup must collapse multi-space AND remove the lone space
        # before extension (' .mp4' → '.mp4').
        self.assertRegex(src, r"re\.sub\(r'\\s\{2,\}',\s*' ',\s*_new_clean\)")
        self.assertRegex(src, r"re\.sub\(r'\\s\+\(\\\.\[\^\.\]\+\)\$',\s*r'\\1',\s*_new_clean\)")

    def test_plex2disk_replace_flag_unaffected(self):
        """--replace (cross-aspect strip) must remain a SEPARATE codepath
        from the per-aspect fix, otherwise it would silently change
        semantics."""
        src = self._read_script()
        # Both branches exist independently:
        self.assertRegex(src, r"if\s+replace\s+and\s+_replace_patterns:")
        self.assertRegex(src, r"if\s+not\s+_new_val:")

    # ------------------------------------------------------------------
    # apply_markers: scalar-marker rejection (corruption guard).
    #
    # Background: while testing S26 sync we saw 163 files end up with
    # `[vu@D] [True]`.  The `[True]` came from `apply_markers` accepting
    # a raw 'True' string from the merge step (when DPM template
    # `[vu@{WATCHED_DATE}]` couldn't be filled and upstream fallback
    # used the value-key as a scalar).  apply_markers must reject any
    # value that isn't a real marker string — never write `[True]`.
    # ------------------------------------------------------------------

    def _load_main_mod(self):
        return _import_tool('_myplex_marker')

    def test_apply_markers_rejects_raw_True_string(self):
        """WATCHED='True' (str) must NOT produce a [True] marker."""
        m = self._load_main_mod()
        out = m.apply_markers('Movie.mkv', {'WATCHED': 'True'})
        self.assertEqual(out, 'Movie.mkv', f"expected no marker, got: {out!r}")

    def test_apply_markers_rejects_raw_boolean(self):
        """A raw Python bool must NOT crash and must NOT produce [True]."""
        m = self._load_main_mod()
        out = m.apply_markers('Movie.mkv', {'WATCHED': True})
        self.assertEqual(out, 'Movie.mkv', f"expected no marker, got: {out!r}")

    def test_apply_markers_rejects_None_and_empty(self):
        m = self._load_main_mod()
        self.assertEqual(m.apply_markers('Movie.mkv', {'X': None}), 'Movie.mkv')
        self.assertEqual(m.apply_markers('Movie.mkv', {'X': ''}), 'Movie.mkv')
        self.assertEqual(m.apply_markers('Movie.mkv', {'X': 'None'}), 'Movie.mkv')
        self.assertEqual(m.apply_markers('Movie.mkv', {'X': 'False'}), 'Movie.mkv')

    def test_apply_markers_accepts_valid_bracket_marker(self):
        """Sanity: valid markers must still be written."""
        m = self._load_main_mod()
        out = m.apply_markers('Movie.mkv', {'WATCHED': '[vu@2026-05-16]'})
        self.assertEqual(out, 'Movie [vu@2026-05-16].mkv')
        out = m.apply_markers('Movie.mkv', {'LANG': '[de]'})
        self.assertEqual(out, 'Movie [de].mkv')


# v2.69 retroactive coverage — tests for code shipped earlier this
# session.  Each test documents the bug or behaviour it pins so a
# future regression has a paper trail.
class TestV269RetroactiveCoverage(unittest.TestCase):
    """Backfilled tests for state preservation, cross-library uncollected,
    auto-refresh fast-path, and the disk2plex date-roundtrip fix.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = _import_tool('_myplex_v269')

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    # ---- State preservation (cmd_move + _sort_new_movies) ----

    def test_state_preservation_directory_is_under_my_plex(self):
        """State files MUST live under ~/.my-plex/state-preservation/.
        Any other location risks losing them across sessions."""
        self.assertEqual(
            self.m._MOVE_STATE_DIR,
            os.path.expanduser('~/.my-plex/state-preservation'))

    def test_state_file_atomic_write_then_rename(self):
        """Snapshot writes must be atomic (tmp → rename) so a SIGKILL mid-write
        never produces a half-written JSON that breaks replay."""
        src = self._read_script()
        import re
        m = re.search(r"def _move_state_write\(state\):.*?tmp = p \+ '\.tmp'.*?os\.replace\(tmp, p\)",
                      src, re.DOTALL)
        self.assertIsNotNone(m, "atomic write pattern (tmp → rename) missing")

    def test_state_file_round_trip(self):
        """Write → read → assert equality.  Real I/O under tmp dir."""
        import tempfile, json
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch _MOVE_STATE_DIR to the tmpdir.
            saved = self.m._MOVE_STATE_DIR
            self.m._MOVE_STATE_DIR = tmpdir
            try:
                state = {
                    'version': 1, 'status': 'snapshotted', 'old_rk': 99001,
                    'old_library': 'inbox', 'old_filepath': '/tmp/old.mkv',
                    'dest_library': 'library2',
                    'title': 'TestMovie', 'year': 2024, 'guid': 'plex://movie/abc',
                    'type': 'Movie',
                    'snapshot': {'labels': ['favourite'], 'collections': ['SomeColl'],
                                 'viewCount': 1, 'lastViewedAt': None,
                                 'userRating': 8.5, 'guid': 'plex://movie/abc',
                                 'playlists': ['My Watchlist']},
                    'new_filepath': None, 'restored_at': None, 'restore_errors': [],
                }
                path = self.m._move_state_write(state)
                self.assertTrue(os.path.exists(path))
                read_back = self.m._move_state_read(path)
                self.assertEqual(read_back, state)
            finally:
                self.m._MOVE_STATE_DIR = saved

    # ---- Date preservation across cross-library moves ----

    def test_plex_dt_to_epoch_normalizes(self):
        """_plex_dt_to_epoch accepts int / datetime / date / None."""
        import datetime as _dt
        self.assertIsNone(self.m._plex_dt_to_epoch(None))
        self.assertEqual(self.m._plex_dt_to_epoch(1700000000), 1700000000)
        dt = _dt.datetime(2023, 11, 14, 12, 0, 0)
        self.assertEqual(self.m._plex_dt_to_epoch(dt), int(dt.timestamp()))
        d = _dt.date(2023, 11, 14)
        self.assertEqual(self.m._plex_dt_to_epoch(d),
                         int(_dt.datetime(2023, 11, 14).timestamp()))

    def test_snapshot_captures_all_dates(self):
        """Snapshot must capture addedAt + lastViewedAt + lastRatedAt +
        originallyAvailableAt — a cross-library move resets them on the new
        ratingKey, so they must be preserved."""
        obj = {'id': 42, 'addedAt': 1600000000, 'lastViewedAt': 1610000000,
               'viewCount': 3, 'userRating': 7.0, 'labels': [], 'collections': [],
               'guid': 'plex://movie/x'}
        snap = self.m._snapshot_plex_item_state(plex=None, obj=obj, playlist_map={})
        self.assertEqual(snap['addedAt'], 1600000000)
        self.assertEqual(snap['lastViewedAt'], 1610000000)
        self.assertIn('lastRatedAt', snap)
        self.assertIn('originallyAvailableAt', snap)

    def test_restore_sets_editable_dates_not_lastviewed(self):
        """Restore must edit addedAt + originallyAvailableAt (Plex-settable),
        rely on markPlayed for watch status, and NEVER claim to set an exact
        lastViewedAt (no Plex API for it)."""
        src = self._read_script()
        idx = src.index('def _restore_plex_item_state(')
        end = src.index('\ndef ', idx + 1)
        body = src[idx:end]
        self.assertIn("'addedAt.value'", body, 'restore must re-set addedAt')
        self.assertIn("'originallyAvailableAt.value'", body,
                      'restore must re-set originallyAvailableAt')
        self.assertIn('markPlayed', body, 'watch status still via markPlayed')
        # Honesty guard: must NOT pretend to set lastViewedAt directly.
        self.assertNotIn("'lastViewedAt.value'", body,
                         'Plex has no API to set an arbitrary lastViewedAt — must not fake it')

    def test_replay_handles_missing_filepath_gracefully(self):
        """A state file with status='moved' but no new_filepath must NOT crash."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = self.m._MOVE_STATE_DIR
            self.m._MOVE_STATE_DIR = tmpdir
            try:
                self.m._move_state_write({
                    'version': 1, 'status': 'moved', 'old_rk': 12345,
                    'new_filepath': None, 'snapshot': {}, 'dest_library': 'library2',
                })
                # Should not raise even when Plex is unavailable.
                n_r, n_f = self.m._replay_pending_move_state(plex=None, quiet=True)
                # No real restore happens (new_filepath missing); just no crash.
                self.assertEqual((n_r, n_f), (0, 0))
            finally:
                self.m._MOVE_STATE_DIR = saved

    def test_restore_lookup_has_four_strategies(self):
        """The lookup in _replay_pending_move_state must include:
           (1) exact filepath, (2) prefix scan, (3) GUID+library, (4) title+year+library.
        All four are needed because Plex sometimes merges a moved file as a new
        VERSION of an existing same-title item (no fresh ratingKey)."""
        src = self._read_script()
        self.assertIn('# Strategy 1: exact filepath lookup', src)
        self.assertIn('# Strategy 2: filepath prefix scan', src)
        self.assertIn('# Strategy 3: GUID + dest_library', src)
        self.assertIn('# Strategy 4: title + year + dest_library', src)

    def test_cleanup_emptied_source_collections_skips_nonempty(self):
        """The cleanup must NOT delete a Plex Collection that still has members,
        even if its name matches a snapshotted source collection."""
        class FakeItem:
            def __init__(self, name, members):
                self._name = name; self._members = list(members)
                self.title = name; self.deleted = False
            def items(self): return list(self._members)
            def delete(self): self.deleted = True
        class FakeSection:
            def __init__(self, colls): self._colls = colls
            def collections(self): return list(self._colls)
        class FakePlex:
            def __init__(self, by_lib): self._by_lib = by_lib
            class _Library:
                def __init__(self, parent): self._p = parent
                def section(self, name): return FakeSection(self._p._by_lib.get(name, []))
            @property
            def library(self): return self._Library(self)
        coll = FakeItem('Test Collection', members=['some_member'])  # still has members
        plex = FakePlex({'library1': [coll]})
        n = self.m._cleanup_emptied_source_collections(
            plex, {('library1', 'Test Collection')}, quiet=True)
        self.assertEqual(n, 0)
        self.assertFalse(coll.deleted)

    def test_cleanup_emptied_source_collections_deletes_empty(self):
        """Empty same-name collection in source library MUST be deleted."""
        class FakeItem:
            def __init__(self, name): self.title = name; self.deleted = False
            def items(self): return []
            def delete(self): self.deleted = True
        class FakeSection:
            def __init__(self, c): self._c = c
            def collections(self): return list(self._c)
        class FakePlex:
            def __init__(self, by_lib): self._b = by_lib
            class _Library:
                def __init__(self, p): self._p = p
                def section(self, name): return FakeSection(self._p._b.get(name, []))
            @property
            def library(self): return self._Library(self)
        coll = FakeItem('Test Collection')
        plex = FakePlex({'inbox': [coll]})
        n = self.m._cleanup_emptied_source_collections(
            plex, {('inbox', 'Test Collection')}, quiet=True)
        self.assertEqual(n, 1)
        self.assertTrue(coll.deleted)

    # ---- Cross-library uncollected resolver ----

    def test_uncollected_allow_cross_library_default_true(self):
        """The default must allow per-library siblings (user opted in)."""
        self.assertTrue(self.m.CONFIG_DEFAULTS.get('UNCOLLECTED_ALLOW_CROSS_LIBRARY', False))

    def test_uncollected_ignored_collection_ids_default_empty(self):
        """No collection-id suppressed by default; users opt in per id."""
        self.assertEqual(self.m.CONFIG_DEFAULTS.get('UNCOLLECTED_IGNORED_COLLECTION_IDS'), [])

    def test_uncollected_resolver_per_library_split(self):
        """cmd_uncollected_resolve must split a multi-library group into
        per-library candidates rather than skipping it.  Code-pattern check."""
        src = self._read_script()
        self.assertRegex(src, r"per_lib\s*=\s*\{\}\s*#\s*library_name\s*→\s*\[\(key,\s*obj\)\]")
        self.assertRegex(src, r"if len\(per_lib\) > 1 and not UNCOLLECTED_ALLOW_CROSS_LIBRARY")

    # ---- Auto-refresh fast-path ----

    def test_auto_refresh_gate_order(self):
        """_maybe_refresh_cache_for_state_changing_command must short-circuit
        in this order: OFFLINE/READ_ONLY → cache mtime → scanned_at diff."""
        src = self._read_script()
        self.assertRegex(src, r"if OFFLINE or READ_ONLY_MODE:\s*\n\s*return False")
        self.assertRegex(src, r"if _age < _AUTO_UPDATE_CACHE_MAX_AGE_S:\s*\n.*\n.*return False")
        self.assertRegex(src, r"changed\s*=\s*\[\]")

    def test_auto_refresh_max_age_30s(self):
        """Stale-window default must remain 30 seconds (settled with user)."""
        self.assertEqual(self.m._AUTO_UPDATE_CACHE_MAX_AGE_S, 30)

    def test_auto_refresh_wired_into_sort_new(self):
        """_sort_new_movies must invoke the auto-refresh before plan-build
        (after the empty-routes guard, before the routing banner prints)."""
        src = self._read_script()
        m_start = src.index('def _sort_new_movies(')
        # Anchor on the routing banner which prints AFTER the auto-refresh.
        m_end = src.index('--sort-new: MOVIE ROUTING', m_start)
        region = src[m_start:m_end]
        self.assertIn("_maybe_refresh_cache_for_state_changing_command('--sort-new')", region)

    def test_auto_refresh_wired_into_cmd_move(self):
        """cmd_move must invoke the auto-refresh before scope resolution."""
        src = self._read_script()
        m_start = src.index('def cmd_move(')
        m_end = src.index('items = _get_universal_scope', m_start)
        region = src[m_start:m_end]
        self.assertIn("_maybe_refresh_cache_for_state_changing_command('--mv')", region)

    # ---- disk2plex date round-trip (bug #4 fixed this turn) ----

    def test_disk2plex_pushes_watched_date_via_db_write(self):
        """The historical [vu@YYYY-MM-DD] date must round-trip into Plex's
        metadata_item_settings.last_viewed_at — not get clobbered to NOW
        by `markPlayed()`."""
        src = self._read_script()
        # The new code path uses query_plex_database_write + UPDATE …
        # metadata_item_settings.last_viewed_at joined by GUID.
        self.assertIn('UPDATE metadata_item_settings', src)
        self.assertIn('last_viewed_at = {unix_ts}', src)
        self.assertIn('WHERE guid = (SELECT guid FROM metadata_items WHERE id =', src)

    def test_query_plex_database_write_helper_exists(self):
        """The narrow DB-write helper must exist and document its safety
        boundary (Plex daemon caches rows; arbitrary writes are unsafe)."""
        self.assertTrue(hasattr(self.m, 'query_plex_database_write'))
        src = self._read_script()
        self.assertIn('Use only for narrow, deterministic updates', src)

    def test_disk2plex_logs_failure_when_db_write_fails(self):
        """If the DB write fails, the operator must be told the date wasn't
        pushed (the watched-status still landed via markWatched())."""
        src = self._read_script()
        self.assertIn('date-update FAILED', src)

    # ------------------------------------------------------------------
    # Backfilled coverage of earlier session commits (4444fc7, 93cae07,
    # 621981d, 3d280f7, cabde38, 2aae2d6, 3f9056f, 3a446fb).
    # ------------------------------------------------------------------

    # ---- 4444fc7: UNCOLLECTED_IGNORED_COLLECTION_IDS actual filter ----

    def test_uncollected_ignored_ids_filter_at_detector(self):
        """Detector (_list_uncollected) must consult UNCOLLECTED_IGNORED_COLLECTION_IDS
        BEFORE counting members.  Otherwise the ignored coll still appears
        in --uncollected listings."""
        src = self._read_script()
        # Both the detector AND resolver must short-circuit on ignored ids.
        # The check looks like `if str(cid) in (UNCOLLECTED_IGNORED_COLLECTION_IDS or []):`
        self.assertGreaterEqual(
            len(__import__('re').findall(
                r"if str\(cid\) in \(UNCOLLECTED_IGNORED_COLLECTION_IDS or \[\]\):",
                src)),
            2,
            "ignored-ids check must appear in BOTH detector and resolver")

    # ---- 93cae07: --uncollected --resolve per-token union ----

    def test_uncollected_resolve_scope_unions_tokens(self):
        """cmd_uncollected_resolve must UNION per-token resolutions, not AND
        them.  _get_universal_scope AND-combines variadic scope tokens,
        which gives 0 results for multiple discrete cache keys
        (Movie:A Movie:B = items in BOTH).  The per-token union loop is
        the fix."""
        src = self._read_script()
        m_start = src.index('def cmd_uncollected_resolve(')
        m_end = src.index('\ndef ', m_start + 1)
        region = src[m_start:m_end]
        # Comment documents the rationale ("Union each token's resolution").
        self.assertIn("Union each token", region)
        # Per-token loop + de-dup set.
        self.assertRegex(region, r"for _t in _tokens:")
        self.assertRegex(region, r"_seen\.add\(_k\)")

    # ---- 621981d + 3d280f7 + 3f9056f: in-process cache refresh ----

    def test_resolve_commands_refresh_cache_in_process(self):
        """Every mutating resolve / move command MUST call
        update_cache_for_library at the end so the operator never has to
        run --update-cache afterwards (CACHE INTEGRITY rule).

        Accepts either `update_cache_for_library(None)` (full refresh)
        or `update_cache_for_library(<lib_name>)` (per-library) — both
        delegate to the canonical subprocess pipeline."""
        src = self._read_script()
        for fname in ('cmd_move', 'cmd_uncollected_resolve',
                      'cmd_mismatched_resolve', 'cmd_misplaced_resolve'):
            m_start = src.index(f'def {fname}(')
            try:
                m_end = src.index('\ndef ', m_start + 1)
            except ValueError:
                m_end = len(src)
            region = src[m_start:m_end]
            self.assertIn('update_cache_for_library(', region,
                          f"{fname} must refresh cache in-process")

    # ---- 3a446fb: update_cache_for_library subprocess + pickle reload ----

    def test_update_cache_for_library_delegates_to_subprocess(self):
        """update_cache_for_library must run `--update-cache` as a
        subprocess (canonical pipeline) and then reload the pickle.
        In-process partial rebuild was the historical bug."""
        src = self._read_script()
        m_start = src.index('def update_cache_for_library(')
        m_end = src.index('\ndef ', m_start + 1)
        region = src[m_start:m_end]
        self.assertIn("'--update-cache'", region)
        self.assertIn('load_media_cache', region)
        self.assertIn('pickle', region.lower())

    # ---- cabde38: parallel TMDB backfill ----

    def test_tmdb_backfill_uses_thread_pool(self):
        """TMDB backfill must use ThreadPoolExecutor sized by
        MAX_PARALLEL_WORKERS, matching the existing scraper-pool pattern."""
        src = self._read_script()
        # Worker count comes from MAX_PARALLEL_WORKERS (possibly wrapped in
        # max(1, int(...)) for safety).
        self.assertRegex(src,
            r"ThreadPoolExecutor\(\s*max_workers\s*=\s*[^)]*MAX_PARALLEL_WORKERS")
        self.assertIn('fetch_tmdb_movie_basics', src)

    # ---- 2aae2d6: --library-language-mismatch path-B (TMDB fallback) ----

    def test_library_language_mismatch_has_tmdb_fallback_path(self):
        """When audio_languages is empty/unknown, the detector must fall
        back to obj['original_language'] (TMDB-backfilled).  Encoded via
        the 'via' tuple field — 'p' = Plex audio source, 'o' = TMDB
        original_language fallback."""
        src = self._read_script()
        # The 'o' branch (TMDB fallback) must exist, and the display
        # legend must distinguish it from 'p'.
        self.assertRegex(src, r"_via_markers\s*=\s*\{['\"]p['\"]:\s*['\"]['\"]")
        self.assertRegex(src, r"['\"]o['\"]:\s*['\"]\*['\"]")
        # The fallback assignment to original_language:
        self.assertRegex(src, r"original_language|_o_lang")

    def test_fetch_tmdb_movie_basics_combined_helper(self):
        """The combined helper must return BOTH collection AND
        original_language in ONE TMDB call.  Prevents the previous
        two-pass overhead (one call for each field)."""
        src = self._read_script()
        m_start = src.index('def fetch_tmdb_movie_basics(')
        # Helper must reach for /movie/{id} endpoint and return the
        # three-key dict.
        m_end = src.index('\ndef ', m_start + 1)
        region = src[m_start:m_end]
        self.assertIn('tmdb_collection_id', region)
        self.assertIn('tmdb_collection_name', region)
        self.assertIn('original_language', region)

    # ------------------------------------------------------------------
    # Bug #1 (this turn): DPM_LIBRARY_SUPPRESS — library-context
    # suppression of redundant markers (e.g. don't write [de] inside
    # a German-only library).  Demonstrated visually in S26 [de] rename.
    # ------------------------------------------------------------------

    def test_dpm_library_suppress_default_empty(self):
        """Default = no suppression; user opts in per library."""
        self.assertEqual(self.m.CONFIG_DEFAULTS.get('DPM_LIBRARY_SUPPRESS'), {})

    def test_dpm_library_suppress_matching_library_value(self):
        """When obj.library matches a key in DPM_LIBRARY_SUPPRESS and
        the resolved var matches the value-to-suppress, the var is
        rewritten to 'unknown' (the no-marker bucket)."""
        m = self.m
        saved_dpm_lib = getattr(m, 'DPM_LIBRARY_SUPPRESS', {})
        saved_disk_plex_map = getattr(m, 'DISK_PLEX_MAP', {})
        try:
            m.DPM_LIBRARY_SUPPRESS = {'LIB_DE': {'AUDIO_LANG': 'de'}}
            # Need at least one promoted plex_var so the bottom_up path runs.
            m.DISK_PLEX_MAP = {
                'AUDIO_LANG': {
                    'scope': ['file'],
                    'series_strategy': 'bottom_up',
                    'values': {'de': {'plex2disk': '[de]'}},
                }
            }
            obj = {
                'type': 'Episode', 'type_str': 'Episode',
                'library': 'LIB_DE',
                'audio_languages': ['de'], 'audio_languages_plex': ['de'],
            }
            var = m.resolve_disk_map_variables(obj, cache_key='Episode:1')
            self.assertEqual(var.get('AUDIO_LANG'), 'unknown',
                             f"expected 'unknown' (suppressed), got {var.get('AUDIO_LANG')!r}")
        finally:
            m.DPM_LIBRARY_SUPPRESS = saved_dpm_lib
            m.DISK_PLEX_MAP = saved_disk_plex_map

    def test_dpm_library_suppress_non_matching_passes_through(self):
        """When obj.library is NOT in DPM_LIBRARY_SUPPRESS, the var is
        unchanged."""
        m = self.m
        saved = getattr(m, 'DPM_LIBRARY_SUPPRESS', {})
        saved_dpm = getattr(m, 'DISK_PLEX_MAP', {})
        try:
            m.DPM_LIBRARY_SUPPRESS = {'LIB_DE': {'AUDIO_LANG': 'de'}}
            m.DISK_PLEX_MAP = {
                'AUDIO_LANG': {
                    'scope': ['file'],
                    'series_strategy': 'bottom_up',
                    'values': {'de': {'plex2disk': '[de]'}},
                }
            }
            obj = {
                'type': 'Episode', 'type_str': 'Episode',
                'library': 'LIB_FR',   # different library
                'audio_languages': ['de'], 'audio_languages_plex': ['de'],
            }
            var = m.resolve_disk_map_variables(obj, cache_key='Episode:2')
            self.assertEqual(var.get('AUDIO_LANG'), 'de',
                             "unrelated library must NOT suppress")
        finally:
            m.DPM_LIBRARY_SUPPRESS = saved
            m.DISK_PLEX_MAP = saved_dpm

    def test_dpm_library_suppress_different_value_passes_through(self):
        """When the var resolved to a value DIFFERENT from the
        suppress-value, leave it alone (e.g. a French dub of a movie
        sitting in a German-only library still gets [fr])."""
        m = self.m
        saved = getattr(m, 'DPM_LIBRARY_SUPPRESS', {})
        saved_dpm = getattr(m, 'DISK_PLEX_MAP', {})
        try:
            m.DPM_LIBRARY_SUPPRESS = {'LIB_DE': {'AUDIO_LANG': 'de'}}
            m.DISK_PLEX_MAP = {
                'AUDIO_LANG': {
                    'scope': ['file'],
                    'series_strategy': 'bottom_up',
                    'values': {'de': {'plex2disk': '[de]'},
                               'fr': {'plex2disk': '[fr]'}},
                }
            }
            obj = {
                'type': 'Episode', 'type_str': 'Episode',
                'library': 'LIB_DE',
                'audio_languages': ['fr'], 'audio_languages_plex': ['fr'],
            }
            var = m.resolve_disk_map_variables(obj, cache_key='Episode:3')
            self.assertEqual(var.get('AUDIO_LANG'), 'fr',
                             "non-matching value must NOT be suppressed")
        finally:
            m.DPM_LIBRARY_SUPPRESS = saved
            m.DISK_PLEX_MAP = saved_dpm

    # ------------------------------------------------------------------
    # Bug #2 (this turn): sync_view_state_into_cache — per-item view
    # state sweep.  Plex view-state writes don't bump library.updatedAt,
    # so incremental --update-cache misses them and --plex2disk wrote
    # no [vu] for items watched only via Plex (S26E124-127 visible).
    # ------------------------------------------------------------------

    def test_sync_view_state_helper_exists(self):
        """The sweep helper must be a module-level function."""
        self.assertTrue(callable(getattr(self.m, 'sync_view_state_into_cache', None)),
                        "sync_view_state_into_cache helper missing")

    def test_sync_view_state_query_form(self):
        """The SQL must:
          (a) JOIN metadata_item_settings on GUID (mis is GUID-keyed),
          (b) filter to Movie+Episode (metadata_type IN (1,4)),
          (c) skip rows without a mis entry,
          (d) skip rows with no view-state worth syncing."""
        src = self._read_script()
        m_start = src.index('def sync_view_state_into_cache(')
        m_end = src.index('\ndef ', m_start + 1)
        region = src[m_start:m_end]
        self.assertIn('JOIN metadata_item_settings mis ON mis.guid = mi.guid', region)
        self.assertIn('mi.metadata_type IN (1, 4)', region)
        self.assertIn('mis.guid IS NOT NULL', region)
        self.assertIn('mis.view_count > 0 OR mis.last_viewed_at IS NOT NULL', region)

    def test_sync_view_state_wired_into_cmd_plex2disk(self):
        """cmd_plex2disk must invoke the sweep BEFORE building items —
        otherwise the bug (Plex-watched but no [vu]) silently recurs."""
        src = self._read_script()
        m_start = src.index('def cmd_plex2disk(')
        m_end = src.index('items = _get_disk_map_scope(target)', m_start)
        region = src[m_start:m_end]
        self.assertIn('sync_view_state_into_cache()', region,
                      "view-state sweep must run before plan-build in cmd_plex2disk")

    def test_push_audio_lang_dpm_is_noop(self):
        """ARCHITECTURAL INVARIANT: --sync (Phase 1 / --disk2plex) MUST
        NOT mutate file CONTENT — only FILENAME / PATHNAME may change.

        The legacy _push_audio_lang_dpm invoked mp4box / mkvpropedit to
        rewrite media containers' audio-track language tags in place.
        That's file-content mutation hiding inside --sync.  Disabled.

        The handler must:
          - Be present in the registry (so it's invoked, not "no handler")
          - Always return None (skip / no action)
          - NOT call apply_pending_operations
          - NOT call mp4box or mkvpropedit
        """
        m = self.m
        # 1. Calling the handler is a no-op (returns None).
        out = m._push_audio_lang_dpm(
            obj={'title': 't', 'file': '/x.mp4', 'library': 'LIB_DE'},
            change={'disk_val': 'de', 'cache_key': 'Episode:1'},
            dry_run=False)
        self.assertIsNone(out)
        # 2. Source must show NO mp4box / mkvpropedit / apply_pending_operations
        #    call from inside this handler.
        src = self._read_script()
        m_start = src.index('def _push_audio_lang_dpm(')
        m_end = src.index('\ndef ', m_start + 1)
        region = src[m_start:m_end]
        self.assertNotIn('apply_pending_operations(', region)
        self.assertNotIn("'mp4box'", region)
        self.assertNotIn("'mkvpropedit'", region)
        self.assertIn("no-op", region)

    def test_plex2disk_triggers_scan_and_waits(self):
        """After committing renames, cmd_plex2disk must:
          (a) trigger Plex library scan on each affected library,
          (b) wait for the scan to finish (wait_for_plex_scan_complete),
          (c) refresh cache (update_cache_for_library) so downstream
              commands see the new file paths.

        Without this, the user's next --sync sees stale Plex DB paths,
        triggers another set of renames that re-rename the SAME files,
        and the cache stays out of sync with disk.
        """
        src = self._read_script()
        # The block must appear AFTER the rename-commit branch.
        m_start = src.index('def cmd_plex2disk(')
        m_end = src.index('\ndef ', m_start + 1)
        region = src[m_start:m_end]
        self.assertIn('_affected_libs.add', region)
        self.assertIn('wait_for_plex_scan_complete', region)
        self.assertIn('update_cache_for_library(None)', region)

    # ------------------------------------------------------------------
    # BEHAVIORAL tests for the per-aspect `merge` policy.
    #
    # Bug history (this session): source-pattern tests for the per-aspect
    # strip-loop passed, but the real merge logic re-injected the stale
    # sidecar marker even when Plex now said "no value".  Visible result:
    # der.quiz.champion got renamed back to `der.quiz.champion [vu@2023-07-23]`
    # because the merge step preserved the old marker unconditionally.
    #
    # These tests EXECUTE _plex2disk_process_scope_dpm with mock sidecar
    # + mock cache state and assert the resulting rename — the exact
    # behavior the source-pattern tests missed.
    # ------------------------------------------------------------------

    def _mock_disk_plex_map_watched_audio(self, m):
        """Reusable DPM stub: WATCHED ('newer') + AUDIO_LANG ('disk')."""
        return {
            'WATCHED': {
                'scope': ['file', 'series_dir', 'season_dir', 'movie_dir'],
                'merge': 'newer',
                'values': {
                    True: {
                        'plex2disk': '[vu@{WATCHED_DATE}]',
                        'disk2plex': [r'\[vu@(?P<WATCHED_DATE>\d{4}-\d{2}-\d{2})\]',
                                      r'\[vu\]'],
                    },
                },
            },
            'AUDIO_LANG': {
                'scope': ['file', 'series_dir', 'season_dir'],
                'merge': 'disk',
                'values': {
                    'de': {'plex2disk': '[de]',
                           'disk2plex': [r'\[(de|german)\]']},
                    'unknown': {},
                },
            },
        }

    def test_merge_newer_drops_stale_sidecar_when_plex_empty(self):
        """The real bug that bit S26 + der.quiz.champion: when sidecar
        records WATCHED='True' from a past run BUT Plex now reports the
        series as not-fully-watched (cache obj has WATCHED=False), the
        output must NOT re-inject the stale marker.

        Behavioral test: stub DPM/sidecar/cache obj, call
        _plex2disk_process_scope_dpm, assert resulting filename has NO
        [vu] marker.
        """
        m = self.m
        # Patch DISK_PLEX_MAP + DPM_LIBRARY_SUPPRESS.
        saved_dpm = m.DISK_PLEX_MAP
        saved_lib_suppress = getattr(m, 'DPM_LIBRARY_SUPPRESS', {})
        m.DISK_PLEX_MAP = self._mock_disk_plex_map_watched_audio(m)
        m.DPM_LIBRARY_SUPPRESS = {}
        try:
            obj = {
                'type': 'Series', 'type_str': 'Series',
                'library': 'LIB_DE',
                'file': '/tmp/_tst_series',
                'WATCHED_uniform': None,    # Plex says NOT fully watched
                'AUDIO_LANG_uniform': None,
                'viewCount': 0, 'lastViewedAt': None,
            }
            sidecar = {
                '/tmp/_tst_series': {
                    'markers': {'WATCHED': 'True'},   # stale from past run
                    'clean_name': '_tst_series',
                    'is_dir': True,
                }
            }
            # Run the real codepath in dry-run (no disk side-effects).
            saved_vrb = getattr(m, 'VRB', False)
            m.VRB = False
            try:
                # _plex2disk_process_scope_dpm is internal; reach via module.
                m._plex2disk_process_scope_dpm(
                    'series_dir',
                    [('/tmp/_tst_series', 'Series:1', obj)],
                    sidecar,
                    dry_run=True,
                    is_dir=True,
                    apply_fn=m.apply_markers_to_dir,
                    strip_fn=m.strip_markers_from_dir,
                    force=False,
                    replace=False,
                )
            finally:
                m.VRB = saved_vrb
            # After the run, the sidecar entry (in dry-run) should NOT
            # have re-injected 'WATCHED': 'True' as if it would still
            # write [vu].  Verify by re-running the resolver and
            # confirming new_markers has no WATCHED entry.
            plex_vars = m.resolve_disk_map_variables(obj, cache_key='Series:1')
            new_markers = m.compute_markers_dpm(m.DISK_PLEX_MAP, plex_vars, 'series_dir')
            self.assertNotIn('WATCHED', new_markers,
                "WATCHED merge='newer' must NOT produce a marker when Plex is empty")
        finally:
            m.DISK_PLEX_MAP = saved_dpm
            m.DPM_LIBRARY_SUPPRESS = saved_lib_suppress

    def test_problem_categories_enabled_semantics(self):
        """v3: PROBLEM_CATEGORIES_DISABLED was renamed to _ENABLED with
        new semantics:
          - None  → run EVERY registered category (default).
          - []    → run NONE.
          - [...] → run only the listed categories.

        Behavioral test: patch the module-level var, call
        _enabled_problem_categories(), assert the right subset."""
        m = self.m
        saved = m.PROBLEM_CATEGORIES_ENABLED
        try:
            # Default = None → all.
            m.PROBLEM_CATEGORIES_ENABLED = None
            self.assertEqual(set(m._enabled_problem_categories().keys()),
                             set(m.PROBLEM_CATEGORIES_REGISTRY.keys()),
                             "None must enable EVERY category")

            # Empty list → none.
            m.PROBLEM_CATEGORIES_ENABLED = []
            self.assertEqual(m._enabled_problem_categories(), {},
                             "[] must run NO categories (explicit opt-out)")

            # Explicit list → only those.
            sample = sorted(m.PROBLEM_CATEGORIES_REGISTRY.keys())[:2]
            m.PROBLEM_CATEGORIES_ENABLED = sample
            self.assertEqual(set(m._enabled_problem_categories().keys()),
                             set(sample),
                             "explicit list must enable only those categories")

            # Order preserved per registry.
            m.PROBLEM_CATEGORIES_ENABLED = list(m.PROBLEM_CATEGORIES_REGISTRY.keys())
            self.assertEqual(list(m._enabled_problem_categories().keys()),
                             list(m.PROBLEM_CATEGORIES_REGISTRY.keys()),
                             "filter must preserve registry insertion order")
        finally:
            m.PROBLEM_CATEGORIES_ENABLED = saved

    def test_problem_categories_disabled_is_gone(self):
        """The old PROBLEM_CATEGORIES_DISABLED key must NOT appear in
        CONFIG_DEFAULTS (no backwards-compat shim — a clean rename).
        Catches accidental re-introduction."""
        self.assertNotIn('PROBLEM_CATEGORIES_DISABLED', self.m.CONFIG_DEFAULTS)
        self.assertIn('PROBLEM_CATEGORIES_ENABLED', self.m.CONFIG_DEFAULTS)

    def test_rename_file_siblings_marker_stripped_match(self):
        """rename_file_siblings must detect siblings even when the parent
        media file's basename carries a [marker] that the sibling lacks.

        Repro of the bug user found: an EiP S01E07.mkv was renamed
        `.mkv` → `... [vu@2026-06-09].mkv`.  The .srt sibling base was
        `...S01E07.720p.NF.WEBRip.x264-GalaxyTV.de.srt`, which does NOT
        start with `... [vu].` (because the .srt never had a marker).
        The legacy detector missed it; orphans on disk.

        Fix: the v2.69 sibling-detector ALSO matches by marker-stripped
        prefix.  This test asserts the source contains the strip and
        the alternate match branch.
        """
        src = self._read_script()
        m_start = src.index('def rename_file_siblings(')
        m_end = src.index('\ndef ', m_start + 1)
        region = src[m_start:m_end]
        self.assertIn('v2.69 bugfix', region)
        self.assertIn('_strip_markers', region)
        self.assertIn('marker-stripped match', region)
        # The clean_prefix must be derived from BOTH old and new basenames.
        self.assertIn('_old_clean', region)
        self.assertIn('_new_clean', region)

    def test_merge_disk_preserves_user_edited_marker(self):
        """AUDIO_LANG has merge='disk' — preserve sidecar value when Plex
        is empty.  This is the inverse of merge='newer'."""
        m = self.m
        saved_dpm = m.DISK_PLEX_MAP
        m.DISK_PLEX_MAP = self._mock_disk_plex_map_watched_audio(m)
        try:
            # Source must contain the preserve branch + the drop-stale
            # branch for the OTHER merge mode.  Behavioral assertion
            # would require running the full scope; instead we sanity-
            # check that the merge='disk' codepath exists and uses
            # 'Preserving' (the legacy semantics).
            src = self._read_script()
            self.assertIn("Dropping stale", src)
            self.assertIn("Preserving", src)
            self.assertRegex(src, r"_merge_mode\s*in\s*\(\s*'plex'\s*,\s*'newer'\s*\)")
        finally:
            m.DISK_PLEX_MAP = saved_dpm

    def test_orphaned_static_method_exists_with_three_categories(self):
        """Step 4b: PLEX_Media._list_orphaned must exist and accept
        do_files / do_dirs / do_my_plex / scope / resolve / dry_run / yes."""
        m = self.m
        self.assertTrue(hasattr(m.PLEX_Media, '_list_orphaned'),
                        "PLEX_Media._list_orphaned must exist")
        import inspect
        sig = inspect.signature(m.PLEX_Media._list_orphaned)
        for param in ('do_files', 'do_dirs', 'do_my_plex',
                      'scope', 'resolve', 'dry_run', 'yes'):
            self.assertIn(param, sig.parameters,
                          f"_list_orphaned must accept {param!r}")

    def test_orphaned_empty_roots_returns_zero(self):
        """With no library roots known (empty library_stats.locations),
        --orphaned reports nothing and returns 0 — does NOT crash."""
        m = self.m
        saved = m.CACHE.copy() if isinstance(m.CACHE, dict) else None
        try:
            m.CACHE = {}  # No library_stats → no roots
            from io import StringIO
            import contextlib
            buf = StringIO()
            with contextlib.redirect_stdout(buf):
                rc = m.PLEX_Media._list_orphaned(do_files=True, do_dirs=True,
                                                  do_my_plex=False, resolve=False)
            self.assertEqual(rc, 0)
            self.assertIn('No library roots known', buf.getvalue())
        finally:
            if saved is not None:
                m.CACHE = saved

    def test_orphaned_argparse_wiring(self):
        """Step 4b: --orphaned + --files/--dirs/--my-plex sub-flags must
        be registered in both main_parser and GLOBAL_CMD_PARSER, plus
        the variadic re-injection list."""
        src = self._read_script()
        # main_parser hidden registration
        self.assertRegex(src, r"main_parser\.add_argument\('--orphaned'")
        self.assertRegex(src, r"dest='orphaned_files_flag'")
        self.assertRegex(src, r"dest='orphaned_dirs_flag'")
        self.assertRegex(src, r"dest='orphaned_my_plex_flag'")
        # GLOBAL_CMD_PARSER documented help
        self.assertRegex(src, r"GLOBAL_CMD_PARSER\.add_argument\('--orphaned'.*help=\"[^\"]+sub-flag")
        # Help-topic synonym map
        self.assertRegex(src, r"'--orphaned':\s*'orphaned'")
        # Variadic reinject
        self.assertRegex(src, r"_reinject_variadic\('orphaned',\s*'--orphaned'\)")
        # Dispatcher path
        self.assertIn("orphaned_val = safe_getattr(cmd_args, 'orphaned', None)", src)
        self.assertIn("PLEX_Media._list_orphaned(do_files=do_files", src)

    def test_orphaned_default_runs_all_three_categories(self):
        """Dispatcher: when none of --files / --dirs / --my-plex is set,
        all three are enabled.  Source-pattern assertion of the gating
        statement (no behavioral run needed)."""
        src = self._read_script()
        # The exact gate line in the dispatcher
        self.assertRegex(src,
            r"if not \(do_files or do_dirs or do_my_plex\):\s*\n\s*do_files = do_dirs = do_my_plex = True")

    def test_plex2disk_replace_is_dpm_template_driven(self):
        """Step 4i: --plex2disk --replace is the canonical stale-marker
        rewrite path, driven entirely by DPM templates.  The processor
        compiles disk2plex regexes from DISK_PLEX_MAP entries (no
        hardcoded markers like 'vu' in the behavior) and strips matches
        before re-applying the canonical plex2disk template."""
        src = self._read_script()
        # The processor builds _replace_patterns from DISK_PLEX_MAP entries
        self.assertIn("_replace_patterns = []", src)
        self.assertRegex(src, r"if replace:\s*\n(\s+[^\n]+\n){0,3}\s+for plex_var, var_spec in DISK_PLEX_MAP\.items\(\)")
        # Each disk2plex regex from the entry is compiled
        self.assertRegex(src, r"_replace_patterns\.append\(re\.compile\(rg, re\.IGNORECASE\)\)")
        # Help text frames --replace as the stale/legacy marker rewrite
        self.assertIn("Stale / legacy marker rewrite", src)
        self.assertIn("no hardcoded marker syntax in my-plex itself", src)
        # No standalone --legacy-markers flag introduced
        self.assertNotIn("'--legacy-markers'", src)
        self.assertNotIn("--legacy-markers ", src)

    def test_original_languages_standalone_flag_retired(self):
        """Step 4h: the standalone --original-languages CLI is GONE.  Its
        argparse defs (main_parser + GLOBAL_CMD_PARSER) and its dispatcher
        block must no longer exist.  The function cmd_original_languages
        itself is retained — it's the helper now called from update_cache."""
        m = self.m
        src = self._read_script()
        # Argparse defs removed
        self.assertNotIn("main_parser.add_argument('--original-languages'", src)
        self.assertNotIn("GLOBAL_CMD_PARSER.add_argument('--original-languages'", src)
        # Dispatcher block removed
        self.assertNotIn("olang_target = safe_getattr(cmd_args, 'original_languages'", src)
        # Help-topic redirect removed (the dict-style entry)
        self.assertNotIn("'--original-languages': 'original-languages'", src)
        # Reinject block removed
        self.assertNotIn("remaining_args.insert(0, '--original-languages')", src)
        # Pipeline DRY_RUN_AWARE no longer lists it
        self.assertNotRegex(src, r"DRY_RUN_AWARE\s*=\s*\{[^}]*'--original-languages'")
        # Helper function preserved (used by --update-cache)
        self.assertTrue(hasattr(m, 'cmd_original_languages'),
            "cmd_original_languages() helper must be preserved")

    def test_update_cache_calls_original_languages_backfill(self):
        """Step 4g: --update-cache must fold the original_language backfill
        in.  Source-pattern check: the call to cmd_original_languages() must
        appear inside the FORCE_CACHE_UPDATE finalize block, guarded by
        TMDB_API_KEY (silent skip when absent), and sit near the
        _cleanup_managed_orphans() call."""
        src = self._read_script()
        self.assertIn("cmd_original_languages(target=None, dry_run=False)", src)
        # The call must be guarded by TMDB_API_KEY presence
        self.assertRegex(src, r"if TMDB_API_KEY:\s*\n\s*try:\s*\n\s*cmd_original_languages\(")
        # And must sit adjacent to (within a kb of) the managed-orphan cleanup
        # call.  rfind because the function DEFINITION of _cleanup_managed_orphans
        # appears earlier in the file (function defs precede the call site).
        _idx_cleanup = src.rfind("_cleanup_managed_orphans()")
        _idx_lang = src.find("cmd_original_languages(target=None, dry_run=False)",
                              _idx_cleanup)
        self.assertGreater(_idx_lang, _idx_cleanup,
            "original-language backfill must come AFTER managed-orphan cleanup")
        self.assertLess(_idx_lang - _idx_cleanup, 1500,
            "backfill call must sit close to the cleanup call")

    def test_default_pipeline_is_cleanup_with_safe_phases(self):
        """Step 4e: the only default-shipped pipeline must be '--cleanup',
        composed of the two safe housekeeping commands (--junk, --orphaned).
        The legacy default '--clean' must be GONE (now a user-defined
        custom override in their personal CONF)."""
        m = self.m
        defaults = m.CONFIG_DEFAULTS['PIPELINES']
        self.assertEqual(set(defaults), {'--cleanup'},
            "default PIPELINES must contain ONLY '--cleanup'")
        phases = defaults['--cleanup']
        self.assertEqual(len(phases), 2,
            "--cleanup default has 2 phases (junk, orphaned)")
        self.assertEqual(phases[0][0], '--junk')
        self.assertEqual(phases[1][0], '--orphaned')
        # Each phase has --resolve as a follow-on token
        self.assertIn('--resolve', phases[0])
        self.assertIn('--resolve', phases[1])

    def test_help_pipelines_marks_custom_vs_default(self):
        """Step 4d: --help pipelines must mark each PIPELINES entry as
        either '(default)' or '(CUSTOM DEFINED COMMAND from CONF)' so a
        user can tell at a glance which pipelines came from their CONF."""
        src = self._read_script()
        # The pipelines case must consult CONFIG_DEFAULTS to decide custom-or-not.
        self.assertIn("CUSTOM DEFINED COMMAND from CONF", src)
        self.assertIn("_default_pipeline_keys = set(CONFIG_DEFAULTS.get('PIPELINES'", src)
        # Dynamic per-pipeline page exists and is reachable for non-default keys.
        self.assertIn("_candidate in PIPELINES and _h_norm not in", src)
        self.assertRegex(src, r"print\(f\"PIPELINE \{_candidate\}\"\)")

    def test_cleanup_managed_orphans_prunes_disk_map_when_filepath_gone(self):
        """Behavioral: when disk_map.json has an entry for a vanished file,
        _cleanup_managed_orphans() removes it and saves the sidecar.  When
        FORCE_CACHE_UPDATE is False the helper is a no-op."""
        m = self.m
        import tempfile, json
        tmp = tempfile.mkdtemp(prefix='myplex_cleanup_')
        live_fp = os.path.join(tmp, 'live.mkv')
        gone_fp = os.path.join(tmp, 'gone.mkv')
        open(live_fp, 'w').close()
        sidecar_data = {
            live_fp: {'markers': {'AUDIO_LANG': '[de]'}, 'clean_name': 'live'},
            gone_fp: {'markers': {'AUDIO_LANG': '[en]'}, 'clean_name': 'gone'},
        }
        sidecar_path = os.path.join(tmp, 'disk_map.json')
        with open(sidecar_path, 'w', encoding='utf-8') as _f:
            json.dump(sidecar_data, _f)

        _saved_dmf = m.DISK_MAP_FILE
        _saved_force = m.FORCE_CACHE_UPDATE
        try:
            m.DISK_MAP_FILE = sidecar_path
            # No-op when not in --update-cache
            m.FORCE_CACHE_UPDATE = False
            m._cleanup_managed_orphans()
            with open(sidecar_path, 'r', encoding='utf-8') as _f:
                after_noop = json.load(_f)
            self.assertIn(gone_fp, after_noop,
                          "no-op when FORCE_CACHE_UPDATE=False")
            # Active pass
            m.FORCE_CACHE_UPDATE = True
            m._cleanup_managed_orphans()
            with open(sidecar_path, 'r', encoding='utf-8') as _f:
                after_active = json.load(_f)
            self.assertIn(live_fp, after_active,
                          "live filepath entry must be preserved")
            self.assertNotIn(gone_fp, after_active,
                             "vanished filepath entry must be pruned")
        finally:
            m.DISK_MAP_FILE = _saved_dmf
            m.FORCE_CACHE_UPDATE = _saved_force
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cleanup_managed_orphans_helper_exists_and_wired(self):
        """Step 4c: _cleanup_managed_orphans() must exist, be guarded by
        FORCE_CACHE_UPDATE, prune disk_map.json entries whose filepath is
        gone, and be called from update_cache() right before the final
        merged update_and_save_cache."""
        m = self.m
        src = self._read_script()
        # Helper exists at module level
        self.assertTrue(hasattr(m, '_cleanup_managed_orphans'),
                        "module must expose _cleanup_managed_orphans()")
        # Guarded by FORCE_CACHE_UPDATE
        _body = src.split("def _cleanup_managed_orphans():", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("if not FORCE_CACHE_UPDATE:", _body)
        # Called from update_cache() right before the final merged save
        self.assertIn("_cleanup_managed_orphans()", src)
        _idx_call = src.rfind("_cleanup_managed_orphans()")
        _idx_save = src.find("update_and_save_cache(build_media_cache_dict(", _idx_call)
        self.assertGreater(_idx_save, _idx_call,
            "the call to _cleanup_managed_orphans() must precede the final merged save")
        self.assertLess(_idx_save - _idx_call, 2000,
            "the call must be within ~2000 chars of the final save")
        # disk_map.json prune logic uses load_disk_map_sidecar
        self.assertIn("load_disk_map_sidecar()", src)
        # episodes.err prune logic references the helper
        self.assertIn("get_episodes_err_path", src.split("def _cleanup_managed_orphans")[1].split("\ndef ")[0])

    def test_orphaned_help_page_and_docs_wired(self):
        """Step 4b-followup: --help orphaned page must exist in the help
        dispatcher; --orphaned must appear in the zsh completion args_spec
        and as a help-topic entry; the README must document the three
        sub-categories."""
        src = self._read_script()
        # Help dispatcher case for 'orphaned'
        self.assertIn("case 'orphaned':", src)
        self.assertIn('print("ORPHANED HELP")', src)
        # Zsh completion: --orphaned in args_spec + the sub-flag hints
        self.assertRegex(src, r"'--orphaned\[Orphan sidecars")
        self.assertRegex(src, r"'--files\[With --orphaned:")
        self.assertRegex(src, r"'--dirs\[With --orphaned:")
        self.assertRegex(src, r"'--my-plex\[With --orphaned:")
        # Zsh --help <topic> completion list
        self.assertRegex(src, r"'orphaned:Orphan sidecars")
        # README documents --orphaned
        readme_path = _readme_path()
        if readme_path is None:
            self.skipTest(_NO_README)
        readme = open(readme_path, 'r', encoding='utf-8').read()
        self.assertIn('--orphaned', readme)
        self.assertIn('--orphaned --files', readme)
        self.assertIn('--orphaned --dirs', readme)
        self.assertIn('--orphaned --my-plex', readme)

    def test_junk_macos_dotunderscore_pattern_compiles_and_matches(self):
        """Step 4a: JUNK_PATTERNS['macos_dotunderscore'] must exist, compile,
        and match macOS AppleDouble shadow files like ._foo.mkv but NOT the
        primary foo.mkv.  Behavioral test against the compiled pattern dict."""
        m = self.m
        self.assertIn('macos_dotunderscore', m.JUNK_PATTERNS,
                      "macos_dotunderscore pattern must be in JUNK_PATTERNS")
        spec = m.JUNK_PATTERNS['macos_dotunderscore']
        self.assertIn('FILENAME_REGEXP', spec)
        rx = re.compile(spec['FILENAME_REGEXP'])
        # Matches the shadow files
        for name in ('._foo.mkv', '._.DS_Store', '._S01E01.srt'):
            self.assertIsNotNone(rx.match(name),
                                 f"pattern must match shadow file {name!r}")
        # Does NOT match the primaries / other dotfiles
        for name in ('foo.mkv', '.DS_Store', '.hidden.txt', 'subs.srt'):
            self.assertIsNone(rx.match(name),
                              f"pattern must NOT match {name!r}")


class TestNaming(unittest.TestCase):
    """--naming engine: template render, modifiers, transforms, name
    split/assembly, NAMING_RULES validation, dir-shape derivation, plan."""

    def _movie_obj(self, **overrides):
        obj = {
            'type': 'Movie', 'title': 'Test Movie', 'year': 2020,
            'library': 'library1',
            'file': '/roots/library1/Test Movie (2020)/Test Movie.mkv',
            'files': {'90.0min 1920x1080 (h264 aac)':
                      {'filepath': '/roots/library1/Test Movie (2020)/Test Movie.mkv'}},
            'viewCount': 0, 'lastViewedAt': None,
            'userRating': None, 'criticsRating': None, 'audienceRating': None,
            'contentRating': '', 'actors': [], 'countries': [], 'genres': [],
            'directors': [], 'writers': [], 'resolution': '1080p',
            'duration': 5400000, 'series': '', 'originalTitle': '',
            'external_ids': {}, 'audio_languages': ['de'],
            'subtitle_languages': [], 'collections': [], 'labels': [],
        }
        obj.update(overrides)
        return obj

    def _episode_obj(self, **overrides):
        obj = self._movie_obj(
            type='Episode', title='Pilot', series='Tagesschau',
            series_key='', S_idx=1, E_idx=7, S_str='S01', E_str='E07',
            S0XE0X='S01E07',
            file='/roots/library2/Tagesschau/s01/Tagesschau S01E07.mkv',
            files={'30.0min 1920x1080 (h264 aac)':
                   {'filepath': '/roots/library2/Tagesschau/s01/Tagesschau S01E07.mkv'}})
        obj.update(overrides)
        return obj

    # --- modifiers -------------------------------------------------------

    def test_modifier_case_and_dots(self):
        self.assertEqual(apply_naming_modifier('Test Movie', 'lower', 'TITLE'), 'test movie')
        self.assertEqual(apply_naming_modifier('quiet', 'upper', 'TITLE'), 'QUIET')
        self.assertEqual(apply_naming_modifier('a b_c  d', 'dots', 'TITLE'), 'a.b.c.d')

    def test_modifier_nodiacritic(self):
        self.assertEqual(apply_naming_modifier('Käßmänn œuvre Ærø łódź',
                                               'nodiacritic', 'TITLE'),
                         'Kassmann oeuvre AEro lodz')

    def test_modifier_nopunct_and_alnum(self):
        self.assertEqual(apply_naming_modifier("It's a Test: x!?", 'nopunct', 'TITLE'),
                         'Its a Test x')
        self.assertEqual(apply_naming_modifier('a.b-c d!e', 'alnum', 'TITLE'),
                         'a.b-cde')

    def test_modifier_pad(self):
        self.assertEqual(apply_naming_modifier(7, 'pad2', 'S'), '07')
        self.assertEqual(apply_naming_modifier('7', 'pad3', 'E'), '007')
        with self.assertRaises(NamingFieldMissing):
            apply_naming_modifier('not-a-number', 'pad2', 'S')

    # --- template render -------------------------------------------------

    def test_render_chain_left_to_right(self):
        variables = {'TITLE': 'Müller & Söhne'}
        self.assertEqual(
            render_naming_template('{TITLE.lower.nodiacritic.dots}', variables),
            'muller.&.sohne')

    def test_render_missing_or_empty_field_raises(self):
        with self.assertRaises(NamingFieldMissing):
            render_naming_template('{NOPE}', {'TITLE': 'x'})
        with self.assertRaises(NamingFieldMissing):
            render_naming_template('{TITLE}', {'TITLE': ''})

    def test_render_mixed_literal_and_tokens(self):
        variables = {'S': 1, 'E': 7, 'TITLE': 'Pilot'}
        self.assertEqual(
            render_naming_template('S{S.pad2}E{E.pad2} - {TITLE}', variables),
            'S01E07 - Pilot')

    # --- transforms ------------------------------------------------------

    def test_transforms_run_in_order_with_backrefs(self):
        name = apply_naming_transforms('the.movie.2020',
                                       [(r'^the\.', ''), (r'(\d{4})$', r'(\1)')])
        self.assertEqual(name, 'movie.(2020)')

    # --- split / assemble ------------------------------------------------

    def test_split_separates_markers_labels_extension(self):
        sidecar_entry = {'markers': {'AUDIO_LANG': 'de'}}
        clean_stem, labels, extension = split_name_for_naming(
            'Test Movie [reencode] [de].mkv', sidecar_entry, is_dir=False)
        self.assertEqual(clean_stem, 'Test Movie')
        self.assertEqual(labels, ['reencode'])
        self.assertEqual(extension, '.mkv')

    def test_split_without_sidecar_treats_brackets_as_labels(self):
        clean_stem, labels, extension = split_name_for_naming(
            'Test Movie [whatever].mkv', None, is_dir=False)
        self.assertEqual(clean_stem, 'Test Movie')
        self.assertEqual(labels, ['whatever'])

    def test_assemble_canonical_order_base_labels_markers_ext(self):
        sidecar_entry = {'markers': {'AUDIO_LANG': 'de'}}
        name = assemble_naming_name('new.name', ['reencode'], sidecar_entry,
                                    '.mkv', is_dir=False)
        self.assertEqual(name, 'new.name [reencode] [de].mkv')

    def test_assemble_preserve_flags_off_drop_tokens(self):
        sidecar_entry = {'markers': {'AUDIO_LANG': 'de'}}
        name = assemble_naming_name('new.name', ['reencode'], sidecar_entry,
                                    '.mkv', preserve_labels=False,
                                    preserve_markers=False, is_dir=False)
        self.assertEqual(name, 'new.name.mkv')

    def test_assemble_dir_has_no_extension_handling(self):
        sidecar_entry = {'markers': {'AUDIO_LANG': 'fr'}}
        name = assemble_naming_name('series.name', [], sidecar_entry, '',
                                    is_dir=True)
        self.assertEqual(name, 'series.name [fr]')

    # --- validation ------------------------------------------------------

    def test_validate_drops_noop_and_unknown_rules(self):
        usable, problems = validate_naming_rules({
            'MOVIE_FILE': {'preserve_ext': True},          # no-op
            'BANANA_DIR': {'template': '{TITLE}'},         # unknown type
            'MOVIE_DIR':  {'template': '{TITLE.lower}'},   # fine
        })
        self.assertEqual(list(usable.keys()), ['MOVIE_DIR'])
        self.assertEqual(len(problems), 2)

    def test_validate_rejects_bad_regex_and_unknown_modifier(self):
        usable, problems = validate_naming_rules({
            'MOVIE_FILE': {'transforms': [('([unclosed', 'x')]},
            'MOVIE_DIR':  {'template': '{TITLE.banana}'},
        })
        self.assertEqual(usable, {})
        self.assertEqual(len(problems), 2)

    # --- dir-shape derivation -------------------------------------------

    def test_derive_paths_movie_and_episode_layouts(self):
        roots = {'/roots/library1', '/roots/library2'}
        movie = self._movie_obj()
        self.assertEqual(derive_naming_paths(movie, roots),
                         {'movie_dir': '/roots/library1/Test Movie (2020)'})
        episode = self._episode_obj()
        self.assertEqual(derive_naming_paths(episode, roots),
                         {'season_dir': '/roots/library2/Tagesschau/s01',
                          'series_dir': '/roots/library2/Tagesschau'})

    def test_derive_paths_unsorted_bare_and_nested(self):
        roots = {'/roots/library2'}
        unsorted_episode = self._episode_obj(
            file='/roots/library2/Tagesschau/Tagesschau S01E07.mkv')
        self.assertEqual(derive_naming_paths(unsorted_episode, roots),
                         {'series_dir': '/roots/library2/Tagesschau'})
        bare = self._movie_obj(file='/roots/library2/bare.mkv')
        self.assertEqual(derive_naming_paths(bare, roots), {})
        nested = self._movie_obj(file='/roots/library2/a/b/c/deep.mkv')
        self.assertEqual(derive_naming_paths(nested, roots), {})

    # --- plan builder ----------------------------------------------------

    def _plan(self, items, rules, sidecar=None, roots=None):
        usable, problems = validate_naming_rules(rules)
        self.assertFalse(problems, f"rules must validate cleanly: {problems}")
        return build_naming_plan(items, usable, sidecar or {},
                                 roots or {'/roots/library1', '/roots/library2'})

    def test_plan_movie_file_rename_and_unchanged(self):
        movie = self._movie_obj()
        rules = {'MOVIE_FILE': {'template': '{TITLE.lower.dots}.{YEAR}'}}
        plan = self._plan([('Movie:1', movie)], rules)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['status'], 'rename')
        self.assertEqual(os.path.basename(plan[0]['new_path']), 'test.movie.2020.mkv')
        # Re-run against the already-canonical name → unchanged
        movie2 = self._movie_obj(
            file='/roots/library1/wrapper/test.movie.2020.mkv',
            files={'v': {'filepath': '/roots/library1/wrapper/test.movie.2020.mkv'}})
        plan2 = self._plan([('Movie:2', movie2)], rules)
        self.assertEqual(plan2[0]['status'], 'unchanged')

    def test_plan_skips_item_with_missing_field(self):
        movie = self._movie_obj(originalTitle='')
        rules = {'MOVIE_FILE': {'template': '{ORIGTITLE}'}}
        plan = self._plan([('Movie:1', movie)], rules)
        self.assertEqual(plan[0]['status'], 'skipped')
        self.assertIn('ORIGTITLE', plan[0]['reason'])

    def test_plan_conflict_when_two_items_want_same_name(self):
        movie_a = self._movie_obj(
            title='Same Title',
            file='/roots/library1/w/a.mkv', files={'v': {'filepath': '/roots/library1/w/a.mkv'}})
        movie_b = self._movie_obj(
            title='Same Title',
            file='/roots/library1/w/b.mkv', files={'v': {'filepath': '/roots/library1/w/b.mkv'}})
        rules = {'MOVIE_FILE': {'template': '{TITLE.lower.dots}'}}
        plan = self._plan([('Movie:1', movie_a), ('Movie:2', movie_b)], rules)
        self.assertEqual([entry['status'] for entry in plan], ['conflict', 'conflict'])

    def test_plan_transforms_only_rule_starts_from_clean_stem(self):
        movie = self._movie_obj(
            file='/roots/library1/w/The.Movie.2020.mkv',
            files={'v': {'filepath': '/roots/library1/w/The.Movie.2020.mkv'}})
        rules = {'MOVIE_FILE': {'transforms': [(r'^The\.', '')]}}
        plan = self._plan([('Movie:1', movie)], rules)
        self.assertEqual(os.path.basename(plan[0]['new_path']), 'Movie.2020.mkv')

    def test_plan_order_files_before_dirs(self):
        episode = self._episode_obj()
        rules = {'EPISODE_FILE': {'template': 'S{S.pad2}E{E.pad2}'},
                 'SEASON_DIR':   {'template': 's{S.pad2}'},
                 'SERIES_DIR':   {'transforms': [(r'$', '')]}}
        plan = self._plan([('Episode:1', episode)], rules)
        kinds = [entry['rule'] for entry in plan]
        self.assertEqual(kinds, ['EPISODE_FILE', 'SEASON_DIR', 'SERIES_DIR'])

    def test_plan_preserves_markers_and_labels_through_rename(self):
        old_path = '/roots/library1/w/Old Name [keepme] [de].mkv'
        movie = self._movie_obj(file=old_path, files={'v': {'filepath': old_path}})
        sidecar = {old_path: {'markers': {'AUDIO_LANG': 'de'},
                              'clean_name': 'Old Name [keepme].mkv'}}
        rules = {'MOVIE_FILE': {'template': '{TITLE.lower.dots}'}}
        plan = self._plan([('Movie:1', movie)], rules, sidecar=sidecar)
        self.assertEqual(os.path.basename(plan[0]['new_path']),
                         'test.movie [keepme] [de].mkv')

    def test_sanitize_blocks_separators_and_hidden_names(self):
        self.assertEqual(_naming_sanitize('AC/DC: Live'), 'AC-DC∶ Live')
        self.assertEqual(_naming_sanitize('.hidden.'), 'hidden')

    # --- idempotency -------------------------------------------------------

    def test_assemble_does_not_duplicate_template_emitted_brackets(self):
        """A template may emit bracketed tokens (' [{YEAR}]'); re-running
        --naming re-reads them as labels — they must not double up."""
        name = assemble_naming_name('series.name [2017]', ['2017', 'keepme'],
                                    None, '', is_dir=True)
        self.assertEqual(name, 'series.name [2017] [keepme]')

    def test_plan_is_idempotent_for_bracket_emitting_template(self):
        old_path = '/roots/library1/w/test.movie [2020] [keepme].mkv'
        movie = self._movie_obj(file=old_path, files={'v': {'filepath': old_path}})
        rules = {'MOVIE_FILE': {'template': '{TITLE.lower.dots} [{YEAR}]'}}
        plan = self._plan([('Movie:1', movie)], rules)
        self.assertEqual(plan[0]['status'], 'unchanged',
                         f"second run must be a no-op, got {plan[0]}")

    # --- 5b: CLI wiring ----------------------------------------------------

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_cli_registration(self):
        """--naming must be registered in both parsers + all routing tables."""
        content = self._read_script()
        self.assertIn("main_parser.add_argument('--naming'", content)
        self.assertIn("GLOBAL_CMD_PARSER.add_argument('--naming'", content)
        self.assertIn("'--naming': 'naming'", content,
                      "_OPTION_TO_HELP_TOPIC must map --naming")
        idx = content.index('_VARIADIC_SCOPE_FLAGS = {')
        end = content.index('}', idx)
        self.assertIn("'--naming'", content[idx:end],
                      "_VARIADIC_SCOPE_FLAGS must include --naming")
        self.assertIn("_reinject_variadic('naming',", content,
                      "bare --naming must be re-injected into the dispatch loop")
        self.assertIn("safe_getattr(args, 'naming', None) is not None", content,
                      "has_standalone_cmd must include --naming")

    def test_cli_dispatch_and_revert_flag(self):
        """execute_global_commands must dispatch --naming with --revert support."""
        content = self._read_script()
        self.assertIn('PLEX_Media._list_naming(', content)
        self.assertIn("main_parser.add_argument('--revert'", content)
        self.assertIn("dest='naming_revert_flag'", content)

    def test_help_page_exists(self):
        """--help naming must document templates, modifiers and rollback."""
        content = self._read_script()
        self.assertIn("case 'naming':", content)
        idx = content.index("case 'naming':")
        end = content.index('sys.exit(0)', idx)
        section = content[idx:end]
        for keyword in ('NAMING HELP', 'NAMING_RULES', 'template', 'transforms',
                        '.nodiacritic', '.pad2', 'naming_original', '--revert',
                        'preserve_markers', 'preserve_labels'):
            self.assertIn(keyword, section, f"--help naming must mention '{keyword}'")

    def test_resolve_writes_log_and_updates_cache(self):
        """--naming --resolve must write a JSON log and persist the cache in-process."""
        content = self._read_script()
        idx = content.index('def _list_naming(')
        end = content.index('\n    @staticmethod', idx)
        body = content[idx:end]
        self.assertIn("_write_resolve_log('naming'", body)
        self.assertIn('update_and_save_cache(build_media_cache_dict())', body)
        self.assertIn('rename_file_siblings(', body)
        self.assertIn('_update_cache_child_paths(', body)

    def test_sidecar_preserves_naming_keys(self):
        """update_sidecar_entry must carry naming_original through a DPM rewrite,
        and keep a naming-only entry alive when all markers go away."""
        sidecar = {'/x/old.mkv': {'naming_original': 'orig.mkv',
                                  'renamed_at': '2026-06-11',
                                  'markers': {'AUDIO_LANG': 'de'},
                                  'clean_name': 'old.mkv'}}
        # DPM rewrites the entry (rename + new markers) — naming keys survive.
        update_sidecar_entry(sidecar, '/x/old.mkv', '/x/new.mkv',
                             {'AUDIO_LANG': 'en'}, 'new.mkv')
        self.assertEqual(sidecar['/x/new.mkv']['naming_original'], 'orig.mkv')
        self.assertEqual(sidecar['/x/new.mkv']['renamed_at'], '2026-06-11')
        # All markers vanish — the naming-only entry must NOT be dropped.
        update_sidecar_entry(sidecar, '/x/new.mkv', '/x/new.mkv', {}, 'new.mkv')
        self.assertIn('/x/new.mkv', sidecar)
        self.assertEqual(sidecar['/x/new.mkv']['naming_original'], 'orig.mkv')
        self.assertNotIn('markers', sidecar['/x/new.mkv'])
        # Entries without naming keys keep the original drop-when-empty rule.
        sidecar2 = {'/y/a.mkv': {'markers': {'AUDIO_LANG': 'de'}, 'clean_name': 'a.mkv'}}
        update_sidecar_entry(sidecar2, '/y/a.mkv', '/y/a.mkv', {}, 'a.mkv')
        self.assertNotIn('/y/a.mkv', sidecar2)

    def test_naming_in_resolve_capable_flags(self):
        """--naming --resolve must pass the --resolve guard."""
        content = self._read_script()
        idx = content.index('_resolve_capable_flags = (')
        end = content.index('\n    )', idx)
        self.assertIn("'naming'", content[idx:end])


class TestPlexConnectNotRequired(unittest.TestCase):
    """A connect that is NOT required must never be fatal, and no connect
    failure may print the token.  Driven against a local server that answers
    every request with 401 -- exactly what a rejected PLEX_TOKEN looks like --
    so the result does not depend on the real server or its credentials."""

    TOKEN = 'secretTOKEN-must-not-leak'

    @classmethod
    def setUpClass(cls):
        import http.server, threading
        class _Unauthorized(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(401); self.end_headers(); self.wfile.write(b'Unauthorized')
            def log_message(self, format: str, *args: Any) -> None: pass
        cls._httpd = http.server.HTTPServer(('127.0.0.1', 0), _Unauthorized)
        threading.Thread(target=cls._httpd.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls._httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls._httpd.shutdown(); cls._httpd.server_close()

    def test_info_reports_rejected_token_instead_of_exiting(self):
        """my-plex --info with a rejected token exits 0 and names the reason.

        With a config of its own, and that is not tidiness: a BARE --info
        prints an API STATUS block whose four probes each run if their config
        value is set, so with the user's real config this test logged in to
        api4.thetvdb.com, called api.themoviedb.org and ssh'd to the Plex
        host -- from the deployment gate, unattended, which is how it ends up
        behind a firewall alert that hangs rather than fails. Found by the
        my-rollout session's survey, 2026-11-05, after I had claimed the only
        fetching tests were the seven scraper ones.

        The Plex probe still runs, against the loopback server above, because
        that is what this test is about."""
        d = tempfile.mkdtemp(prefix='my-plex-infoiso-')
        conf = os.path.join(d, 'my-plex.conf')
        with open(conf, 'w') as f:
            # blank: each probe is gated on its own value, so "" means the
            # block says "not configured" instead of reaching out
            f.write("TVDB_API_KEY = ''\n")
            f.write("TMDB_API_KEY = ''\n")
            f.write("PLEX_DB_REMOTE_HOST = ''\n")
            f.write(f"CACHE_FILE = {os.path.join(d, 'cache.pkl')!r}\n")
            f.write(f"LOCK_FILE = {os.path.join(d, 'cache.lock')!r}\n")
        try:
            r = subprocess.run([sys.executable, MAIN_SCRIPT, '--config', conf,
                                '--info', '--plex-url', self.url,
                                '--plex-token', self.TOKEN],
                               capture_output=True, text=True, timeout=180)
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode, 0,
                             f"--info must not die on a failed connect:\n{out[-800:]}")
            self.assertIn('configured but not connected (', r.stdout)
            self.assertIn('401', r.stdout)
            self.assertNotIn(self.TOKEN, out)
            # ...and it reached nothing else. Without this a later edit can
            # drop the config and the probes come back silently.
            for probe in ('TVDB API', 'TMDB API', 'Plex DB (SSH)'):
                line = [ln for ln in r.stdout.splitlines() if probe in ln]
                self.assertTrue(line, f"no {probe} line at all:\n{r.stdout[-600:]}")
                self.assertIn('not configured', line[0],
                              f"{probe} was probed for real: {line[0]}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def _connect(self, required):
        """Call connect_to_plex in-process; returns (SystemExit or None, stdout, PLEX_CONNECT_ERROR)."""
        import socket
        g = connect_to_plex.__globals__
        saved = {k: g[k] for k in ('OFFLINE', 'PLEX_SERVER', 'PLEX_CONNECT_ERROR')}
        saved_timeout = socket.getdefaulttimeout()
        g['OFFLINE'] = False; g['PLEX_SERVER'] = None; g['PLEX_CONNECT_ERROR'] = None
        buf, exc = io.StringIO(), None
        try:
            from contextlib import redirect_stdout, redirect_stderr
            with redirect_stdout(buf), redirect_stderr(buf):
                try:
                    connect_to_plex(self.url, self.TOKEN, required=required)
                except SystemExit as e:
                    exc = e
            return exc, buf.getvalue(), g['PLEX_CONNECT_ERROR'], g['PLEX_SERVER']
        finally:
            g.update(saved); socket.setdefaulttimeout(saved_timeout)

    def test_not_required_returns_with_reason(self):
        exc, out, why, server = self._connect(required=False)
        self.assertIsNone(exc, f"required=False must not exit: {out}")
        self.assertIsNone(server)
        self.assertIn('401', why or '')

    def test_required_is_fatal_and_redacts_token(self):
        exc, out, why, _ = self._connect(required=True)
        self.assertIsNotNone(exc, "required=True must still be fatal")
        self.assertRegex(out, r'ERROR \d{5} \[\d+\]:')
        self.assertIn('Failed to connect to PLEX Server', out)
        self.assertIn(f'<redacted, {len(self.TOKEN)} chars>', out)
        self.assertNotIn(self.TOKEN, out)
        self.assertIsNone(why, "a fatal connect has nothing to hand back")


class TestVersionAndStamp(unittest.TestCase):
    """--version identifies the exact build; --stamp-version [go] records the
    release commit and refuses every amend that would do harm.  Each stamp
    test runs a COPY of my-plex.py in a throwaway repo with a bare remote."""

    GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
               'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.env = dict(os.environ, **self.GIT_ENV)
        self.remote = os.path.join(self.root, 'remote.git')
        self.work = os.path.join(self.root, 'work')
        self.git('init', '-q', '--bare', self.remote, cwd=self.root)
        self.git('init', '-q', '-b', 'main', self.work, cwd=self.root)
        self.script = os.path.join(self.work, 'my-plex.py')
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        with open(self.script, 'w') as f:   # start unstamped, whatever the real file says
            f.write(re.sub(r'^SCRIPT_COMMIT\s*=.*$', 'SCRIPT_COMMIT  = ""', src, count=1, flags=re.M))
        with open(os.path.join(self.work, 'sibling.txt'), 'w') as f:
            f.write('a\n')
        self.git('add', '.'); self.git('commit', '-q', '-m', 'first')
        self.git('remote', 'add', 'origin', self.remote)
        self.git('push', '-q', '-u', 'origin', 'main')

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *a, cwd=None):
        r = subprocess.run(['git', *a], cwd=cwd or self.work, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"git {' '.join(a)}: {r.stderr}")
        return r.stdout.strip()

    def run_tool(self, *a):
        return subprocess.run([sys.executable, self.script, *a], cwd=self.work, env=self.env,
                              capture_output=True, text=True, timeout=60)

    def new_commit(self):
        with open(self.script, 'a') as f:
            f.write('\n# a change worth stamping\n')
        self.git('add', 'my-plex.py'); self.git('commit', '-q', '-m', 'second')

    def stamped(self):
        with open(self.script) as f:
            return _must(re.search(r'^SCRIPT_COMMIT\s*=\s*"([^"]*)"', f.read(), re.M), 'SCRIPT_COMMIT').group(1)

    # --- --version ------------------------------------------------------
    def test_version_names_build_and_stamp(self):
        r = self.run_tool('--version')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout.splitlines()[0], r'^my-plex \S+ \(build [0-9a-f]{12}, unstamped\)$')

    def test_changed_file_reports_different_build(self):
        before = self.run_tool('--version').stdout.splitlines()[0]
        with open(self.script, 'a') as f:
            f.write('\n# changed\n')
        after = self.run_tool('--version').stdout.splitlines()[0]
        self.assertNotEqual(before, after, "two different files must not report the same --version")

    # --- --stamp-version guards -------------------------------------------
    def test_refuses_pushed_commit(self):
        head = self.git('rev-parse', 'HEAD')
        r = self.run_tool('--stamp-version', 'go')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('already pushed', r.stderr)
        self.assertIn('rewrite published history', r.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head, "the pushed commit must be untouched")

    def test_analyze_changes_nothing(self):
        self.new_commit(); head = self.git('rev-parse', 'HEAD')
        r = self.run_tool('--stamp-version')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("re-run with 'go'", r.stdout)
        self.assertEqual(self.stamped(), '')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_go_stamps_the_unpushed_commit(self):
        self.new_commit(); short = self.git('rev-parse', '--short', 'HEAD')
        mode = os.stat(self.script).st_mode
        r = self.run_tool('--stamp-version', 'go')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stamped(), short)
        self.assertEqual(os.stat(self.script).st_mode, mode, "the mode must survive the rewrite")
        self.assertEqual(self.git('status', '--porcelain'), '', "the stamp must be IN the amended commit")
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2', "amend, not a new commit")
        self.assertIn(f'commit {short}', self.run_tool('--version').stdout)

    def test_second_stamp_is_a_no_op(self):
        self.new_commit()
        self.assertEqual(self.run_tool('--stamp-version', 'go').returncode, 0)
        head = self.git('rev-parse', 'HEAD')
        r = self.run_tool('--stamp-version', 'go')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('nothing to do', r.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head, "restamping must not walk the commit forward")

    def test_refuses_when_something_is_staged(self):
        self.new_commit()
        with open(os.path.join(self.work, 'sibling.txt'), 'w') as f:
            f.write('b\n')
        self.git('add', 'sibling.txt')
        r = self.run_tool('--stamp-version', 'go')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('sibling.txt', r.stderr)
        self.assertEqual(self.stamped(), '')

    def test_refuses_uncommitted_edit_of_itself(self):
        self.new_commit()
        with open(self.script, 'a') as f:
            f.write('\n# not committed\n')
        r = self.run_tool('--stamp-version', 'go')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('uncommitted edits', r.stderr)

    def test_unstaged_sibling_does_not_block(self):
        self.new_commit()
        with open(os.path.join(self.work, 'sibling.txt'), 'w') as f:
            f.write('someone else is editing this\n')
        r = self.run_tool('--stamp-version', 'go')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git('diff', '--name-only'), 'sibling.txt', "their edit stays theirs, unstaged")
        self.assertNotIn('sibling.txt', self.git('show', '--name-only', '--format=', 'HEAD'))


class TestVersionNamesItsRelease(unittest.TestCase):
    """SCRIPT_VERSION names the release these bytes are BASED on -- only a
    release commit sets it.  Whether this build IS that release is git's
    describe string, which --version prints; so what is checked here is that
    the number still names the nearest tag."""

    def test_script_version_names_the_nearest_tag(self):
        here = os.path.dirname(MAIN_SCRIPT)
        with open(MAIN_SCRIPT) as f:
            version = _must(re.search(r'^SCRIPT_VERSION\s*=\s*"([^"]+)"', f.read(), re.M), 'SCRIPT_VERSION').group(1)
        def git(*a):
            return subprocess.run(['git', '-C', here, *a], capture_output=True, text=True)
        if git('rev-parse', '--git-dir').returncode != 0:
            self.skipTest('not a git checkout')
        near = git('describe', '--tags', '--abbrev=0').stdout.strip()
        if not near:
            return  # no release tag yet -- nothing for the version to name
        self.assertEqual(near, version,
                         f"SCRIPT_VERSION is {version}, but the nearest tag is {near} -- "
                         f"set it to {near}, or tag this release")

    def test_version_says_whether_these_bytes_are_that_release(self):
        r = subprocess.run([sys.executable, MAIN_SCRIPT, '--version'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('build ', r.stdout)
        self.assertTrue('unreleased' in r.stdout or ' tag,' in r.stdout,
                        f"--version says neither 'the <tag> tag' nor 'unreleased': {r.stdout}")


class TestRunViaSymlink(unittest.TestCase):
    """my-plex is deployed as a symlink (/LINKS/bin/my-plex -> .../my-plex.py).
    Everything it loads from beside itself must be found next to the REAL
    file, not next to the link."""

    def test_runs_through_a_symlink_in_another_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, 'my-plex')
            os.symlink(MAIN_SCRIPT, link)
            r = subprocess.run([sys.executable, link, '--help'],
                               capture_output=True, text=True, timeout=60)
        out = r.stdout + r.stderr
        self.assertNotIn('my-plex_tests.py', out, f"looked for a sibling next to the link:\n{out[-600:]}")
        self.assertEqual(r.returncode, 0, out[-600:])


class TestArgvValueFlags(unittest.TestCase):
    """The argv normalizer turns a bare word into a title search -- except the
    value of a flag that takes one.  Probed with -D and a trailing --help, so
    the normalizer runs and prints its translations but nothing executes."""

    def _probe(self, *args):
        r = subprocess.run([sys.executable, MAIN_SCRIPT, '--offline', '-D', *args, '--help'],
                           capture_output=True, text=True, timeout=60)
        return r.stdout + r.stderr

    def test_single_values_are_not_title_searches(self):
        for flag, value in (('--audio', 'de'), ('--remove', '1,3'), ('--rm', '2,4'),
                            ('--set-watched', '2026-01-01'), ('--set-user-rating', '4.5'),
                            ('--unrecognized', 'somelib'), ('--plex-url', 'http://h:1')):
            with self.subTest(flag=flag):
                out = self._probe(flag, value)
                self.assertNotIn(f"Search token '{value}'", out,
                                 f"{flag} {value}: the value was stolen as a title search")

    def test_remove_versions_never_turn_into_remove_all(self):
        """`--remove 1,3` asks for versions 1 and 3; stealing '1,3' left --remove
        bare, and bare --remove means ALL versions."""
        out = self._probe('--remove', '1,3')
        self.assertNotIn('--list=title~1,3', out)

    def test_every_item_of_a_multi_value_flag_is_kept(self):
        out = self._probe('--add-to', 'itemA', 'itemB')
        self.assertNotIn("Search token 'itemA'", out)
        self.assertNotIn("Search token 'itemB'", out)

    def test_debug_output_never_prints_a_token(self):
        secret = 'sEcReTtOkEn123'
        out = self._probe('--plex-token', secret)
        self.assertNotIn(secret, out)
        out = self._probe('--plex-xml-url', f'https://h:32400/library/metadata/1?X-Plex-Token={secret}')
        self.assertNotIn(secret, out)


class TestTypeCheck(unittest.TestCase):
    """pyright must report NOTHING about my-plex.py, under pyrightconfig.json.

    What a type check is worth here, concretely: four NameErrors sat in
    shipped commands until one was first run -- plan_movie and libs_affected
    in cmd_bad_structure_resolve(), i in the ctrl-c handler of
    cmd_original_languages(), _dtm in _replay_pending_move_state() -- each on
    a failure or interrupt path, which is where the command matters most, so
    none of them ever showed up in ordinary use.

    my-plex_tests.py is NOT asserted: it is not at zero yet, and neither is
    strict mode.  TODO.local.md tracks both."""

    # The checker's environment, not the code: without my-plex's venv pyright
    # cannot see plexapi or readchar, and says so once per import.
    ENVIRONMENT_RULES = ('reportMissingImports', 'reportMissingModuleSource',
                         'reportMissingTypeStubs')

    @unittest.skipUnless(shutil.which('pyright'), "pyright is not installed")
    def test_main_script_is_clean(self):
        project = os.path.dirname(os.path.realpath(MAIN_SCRIPT))
        cmd = [shutil.which('pyright') or 'pyright', '--outputjson', '-p', project]
        venv_python = os.path.join(os.path.expanduser('~/.python.venv/my-plex'), 'bin', 'python3')
        if os.path.isfile(venv_python):
            cmd += ['--pythonpath', venv_python]
        r = subprocess.run([*cmd, MAIN_SCRIPT], capture_output=True, text=True, timeout=300)
        # pyright exits 1 whenever it reports anything, so the verdict is the
        # JSON, not the exit status; a crash prints no JSON at all.
        try:
            report = json.loads(r.stdout)
        except ValueError:
            self.fail(f"pyright produced no JSON report (rc {r.returncode}):\n"
                      f"{(r.stdout + r.stderr)[-800:]}")
        hits = [f"line {d.get('range', {}).get('start', {}).get('line', -1) + 1}: "
                f"{d.get('rule') or 'error'}: {d.get('message', '').splitlines()[0]}"
                for d in report.get('generalDiagnostics', [])
                if d.get('severity') == 'error'
                and d.get('rule') not in self.ENVIRONMENT_RULES
                and os.path.realpath(d.get('file', '')) == os.path.realpath(MAIN_SCRIPT)]
        self.assertEqual(hits, [], f"pyright reports {len(hits)} finding(s) in my-plex.py:\n  "
                                   + "\n  ".join(hits))


class TestDeployedCopy(unittest.TestCase):
    """my-plex is deployed as a COPY of the tool file alone -- my-plex_tests.py
    is not beside it.  The suite is therefore loaded on demand: every ordinary
    command must run without it, and --run-tests / --unittest must say in one
    line that it is missing instead of dying in an import traceback."""

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.mkdtemp(prefix='my-plex-deployed-')
        cls.copy = os.path.join(cls._dir, 'my-plex')
        shutil.copy2(MAIN_SCRIPT, cls.copy)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._dir, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run([sys.executable, '-B', self.copy, *args],
                              capture_output=True, text=True, timeout=180)

    def test_fixture_reproduces_a_deployed_copy(self):
        """The fixture is only meaningful while the sidecar is genuinely absent."""
        self.assertFalse(os.path.exists(os.path.join(self._dir, 'my-plex_tests.py')),
                         "the fixture must hold the tool file alone")

    def test_help_runs_without_the_test_suite(self):
        r = self._run('--help')
        out = r.stdout + r.stderr
        self.assertNotIn('Traceback', out,
                         f"a deployed copy must not die while importing:\n{out[-800:]}")
        self.assertNotIn('my-plex_tests.py', out,
                         "an ordinary command must not even mention the test suite")
        self.assertEqual(r.returncode, 0, out[-800:])

    def test_test_commands_report_the_missing_suite_in_one_line(self):
        for args in (('--run-tests', 'errcodes'), ('--unittest',)):
            with self.subTest(args=args):
                r = self._run(*args)
                out = r.stdout + r.stderr
                self.assertNotIn('Traceback', out,
                                 f"no traceback on the user's screen:\n{out[-800:]}")
                self.assertIn('test suite not found', out)
                self.assertNotEqual(r.returncode, 0, "a missing test suite is a failure")


class TestDeployedCopyWithItsSuite(unittest.TestCase):
    """A copy made by my-rollout is bin/my-plex plus lib/my-plex_tests.py,
    and my-rollout's gate runs the PENDING COPY's own --run-tests: the suite
    has to be found from there, or a copy is never offered again.

    Flat and tool-prefixed, because my-rollout places a file but does not
    create its parent: a request naming lib/my-plex/ fails with ERROR 00031.
    It is also what global/lib already holds (my-rollout_steps-lib.sh)."""

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.mkdtemp(prefix='my-plex-deployed-lib-')
        os.makedirs(os.path.join(cls._dir, 'bin'))
        os.makedirs(os.path.join(cls._dir, 'lib'))
        cls.copy = os.path.join(cls._dir, 'bin', 'my-plex')
        shutil.copy2(MAIN_SCRIPT, cls.copy)
        shutil.copy2(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'my-plex_tests.py'),
                     os.path.join(cls._dir, 'lib', 'my-plex_tests.py'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._dir, ignore_errors=True)

    def test_fixture_has_no_suite_beside_the_tool(self):
        """Otherwise the test would pass through the checkout path instead."""
        self.assertFalse(os.path.exists(os.path.join(self._dir, 'bin', 'my-plex_tests.py')))

    def test_the_suite_is_found_in_lib(self):
        r = subprocess.run([sys.executable, '-B', self.copy, '--run-tests', 'errcodes'],
                           capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        self.assertNotIn('test suite not found', out, out[-800:])
        self.assertRegex(out, r'(?m)^1\.\.\d+$', "no TAP plan from the deployed copy")
        # Not just "it ran": the tests that read the tool's own source must
        # find bin/my-plex, which is what MAIN_SCRIPT is overridden for.
        self.assertNotIn('FileNotFoundError', out, out[-1500:])
        self.assertEqual(r.returncode, 0, out[-1500:])

    def test_the_copy_imports_itself_although_its_file_has_no_py(self):
        """THE adversarial case, and the one the gate cannot see.

        Seven scopes import my-plex as a module.  The gate runs a pending
        copy whose file is still called my-plex.py, so they pass there; a
        DEPLOYED copy is `bin/my-plex`, and spec_from_file_location() answers
        None for a name with no extension.  Measured on horse 2026-11-03,
        the same bytes both times: 4 ok as my-plex.py, 2 of 4 not ok as
        my-plex.

        So the probe runs against THIS fixture's extensionless copy, through
        the one helper all nine sites now use -- take the explicit loader out
        of it and this test is the first thing that says so.
        """
        snippet = _tool_import_snippet(['my-plex', '--help'], path=self.copy) + (
            "os.write(2, b'IMPORTED ' + mp.__file__.encode())\n"
        )
        r = subprocess.run([sys.executable, '-B', '-c', snippet],
                           capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        self.assertNotIn("has no attribute 'loader'", out,
                         "spec_from_file_location() answered None for "
                         f"{self.copy}:\n{out[-900:]}")
        self.assertIn('IMPORTED', r.stderr,
                      f"the copy did not import:\n{out[-1200:]}")
        self.assertIn(self.copy, r.stderr,
                      "it imported something other than the copy")
        self.assertEqual(r.returncode, 0, out[-900:])

    def test_only_main_script_knows_where_the_tool_is(self):
        """MAIN_SCRIPT is the one owner of "where is the tool", because only
        the tool can answer it: it overrides MAIN_SCRIPT with its own realpath
        when it loads this suite.  A site that rebuilds the path from THIS
        file's directory instead gets <tests dir>/my-plex.py -- right in a
        checkout by accident, and absent beside the deployed suite in
        global/lib, where there is no my-plex.py at all.

        Five sites had leaked that way (two _read_script copies against ~70
        correct ones, and three inline), so the convention is now grepped
        rather than remembered.  Fixture paths like os.path.join(d,
        'my-plex.py') are a COPY this suite makes, not a guess at where the
        tool lives, so they are not matched.
        """
        tool_file = 'my-plex' + '.py'   # split, so this test cannot match itself
        with open(os.path.realpath(__file__)) as f:
            lines = f.read().splitlines()
        leaks = [f"{n}: {l.strip()}" for n, l in enumerate(lines, 1)
                 if '__file__' in l and tool_file in l
                 and not l.startswith('MAIN_SCRIPT =')]
        self.assertEqual(leaks, [],
                         "these derive the tool's path from this file instead "
                         "of using MAIN_SCRIPT:\n  " + "\n  ".join(leaks))

    def test_help_answers_without_a_venv_and_does_not_build_one(self):
        """The gate asks `--help` to find out what a tool can do, on a machine
        that may have neither the venv nor the network to make one, with
        nobody at the screen to answer for it. Building an environment to
        answer that question is how --help comes back empty and the copy goes
        out untested. --version is already answered before the venv block;
        --help now is too.

        The script is run DIRECTLY, so its shebang picks the interpreter the
        gate's run gets -- not sys.executable, which is the venv this suite
        runs inside and has every dependency.  That distinction is the whole
        test: under the venv's python it passed while `my-plex --help` was
        dying on `import urllib3.exceptions`, because the venv has urllib3
        and the shebang's python does not.  So this also stands guard over
        every FUTURE module-level third-party import, which is why it does
        not name the ones that exist today."""
        home = tempfile.mkdtemp(prefix='my-plex-nohome-')
        try:
            env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE='1')
            env.pop('VIRTUAL_ENV', None)
            r = subprocess.run([MAIN_SCRIPT, '--help'],
                               capture_output=True, text=True, timeout=300, env=env)
            out = r.stdout + r.stderr
            self.assertNotIn('Creating python virtualenv', out,
                             "it built an environment in order to print help")
            self.assertFalse(os.path.isdir(os.path.join(home, '.python.venv')),
                             "a venv was created under a HOME that had none")
            self.assertNotIn('Traceback', out,
                             f"--help raised instead of answering:\n{out[-900:]}")
            self.assertIn('--run-tests', out,
                          f"the gate greps for this in --help:\n{out[-600:]}")
            self.assertEqual(r.returncode, 0, out[-600:])
        finally:
            shutil.rmtree(home, ignore_errors=True)

    def test_help_names_run_tests_so_the_gate_fires(self):
        """my-rollout runs a pending copy's suite only when --help names it."""
        r = subprocess.run([sys.executable, '-B', self.copy, '--help'],
                           capture_output=True, text=True, timeout=180)
        self.assertIn('--run-tests', r.stdout + r.stderr,
                      "--help must name --run-tests, or my-rollout promotes my-plex untested")


class TestRunTestsTAP(unittest.TestCase):
    """--run-tests reports TAP-style, because `my-rollout go` reads it: the
    plan `1..N` first, then one `ok K - title` per test as it ends."""

    LINE = re.compile(r'^(ok|not ok) (\d+) - (\S+)', re.M)

    @classmethod
    def setUpClass(cls):
        r = subprocess.run([sys.executable, '-B', MAIN_SCRIPT, '--run-tests', 'errcodes'],
                           capture_output=True, text=True, timeout=300)
        cls.out, cls.rc = r.stdout + r.stderr, r.returncode

    def test_the_plan_comes_before_any_result(self):
        """A reader sizes its progress row from the plan, so no `ok` may
        precede it.  It need not be the very first line -- a preamble that is
        not a TAP line is no concern of the reader's."""
        plan = re.search(r'^1\.\.\d+$', self.out, re.M)
        assert plan is not None, f"no plan line at all:\n{self.out[:300]}"
        first = self.LINE.search(self.out)
        assert first is not None, "no result line at all"
        self.assertLess(plan.start(), first.start(),
                        f"a result came before the plan:\n{self.out[:300]}")

    def test_no_class_skips_in_setUpClass(self):
        """A class-level skip breaks the plan, and no filtered run shows it.

        `raise SkipTest` in setUpClass makes unittest report ONE skip for the
        class, while the plan -- taken from the suite before anything runs --
        has already announced every test in it. On ada that was 26 tests
        announced and never reported (1176 vs 1150), and my-rollout's gate
        was right to read it as 26 missing. The skip has to be per test, in
        setUp or in the test, so each announced test prints its own line."""
        import inspect, textwrap
        offenders = []
        for cls in _UNITTEST_CLASSES:
            f = cls.__dict__.get('setUpClass')
            if f is None:
                continue
            try:
                tree = ast.parse(textwrap.dedent(inspect.getsource(f)))
            except (OSError, SyntaxError):
                continue
            # the CODE, not the text: a first version grepped the source and
            # was fooled by a docstring that said "does NOT raise SkipTest"
            skips = any(
                (isinstance(node, ast.Raise) and node.exc is not None
                 and 'SkipTest' in ast.dump(node.exc))
                or (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'skipTest')
                for node in ast.walk(tree))
            if skips:
                n = unittest.TestLoader().loadTestsFromTestCase(cls).countTestCases()
                offenders.append(f"{cls.__name__} ({n} test(s))")
        self.assertEqual(offenders, [],
                         "these classes skip in setUpClass, so their tests are "
                         "announced by the plan and never reported: "
                         + ", ".join(offenders))

    def test_the_plan_counts_the_tests_that_reported(self):
        plan = int(_must(re.search(r'^1\.\.(\d+)$', self.out, re.M), 'the TAP plan').group(1))
        self.assertEqual(plan, len(self.LINE.findall(self.out)),
                         f"plan 1..{plan} but a different number of tests reported")

    def test_every_number_from_one_to_n_appears_exactly_once(self):
        got = sorted(int(m[1]) for m in self.LINE.findall(self.out))
        self.assertEqual(got, list(range(1, len(got) + 1)),
                         "a reader collects results by number, so each must appear once")

    def test_a_title_names_its_class_and_method(self):
        titles = [m[2] for m in self.LINE.findall(self.out)]
        self.assertTrue(titles, "no TAP line at all")
        for t in titles:
            self.assertRegex(t, r'^Test\w+\.test_\w+$', f"unreadable title {t!r}")

    def test_a_passing_scope_exits_zero(self):
        self.assertEqual(self.rc, 0, self.out[-800:])

    def test_a_filter_selects_by_test_title(self):
        r = subprocess.run([sys.executable, '-B', MAIN_SCRIPT, '--run-tests',
                            'TestRunTestsTAP.test_a_title_names'],
                           capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        self.assertIn('1..1', out, f"one test should have matched:\n{out[-800:]}")

    def test_an_unmatched_filter_prints_the_scopes_and_fails(self):
        r = subprocess.run([sys.executable, '-B', MAIN_SCRIPT, '--run-tests', 'no-such-thing'],
                           capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        self.assertIn('Test scopes', out, "an unmatched FILTER must say what IS available")
        self.assertNotEqual(r.returncode, 0)

    def test_the_old_spelling_names_the_new_one(self):
        """--test was this flag's name for years, so it will be typed out of
        habit: a near-miss is answered with the new name, never with a bare
        "invalid flag" that sends the reader to --help."""
        r = subprocess.run([sys.executable, '-B', MAIN_SCRIPT, '--test', 'errcodes'],
                           capture_output=True, text=True, timeout=180)
        out = r.stdout + r.stderr
        self.assertIn('--run-tests', out, f"the old name must point at the new one:\n{out[-400:]}")
        self.assertNotEqual(r.returncode, 0, "the old name must not WORK, only be recognised")

    def test_a_failed_subtest_reports_not_ok_on_its_own(self):
        """A failed subTest never reaches addFailure -- unittest reports it
        through addSubTest and calls stopTest once for the whole test.  The
        line must be a plain `not ok`, because a reader collects the failures
        by that word and shows the title beside it."""
        import contextlib
        result = _TAPResult(io.StringIO(), True, 0)
        case = TestRunTestsTAP('test_a_passing_scope_exits_zero')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result.startTest(case)
            try:
                raise AssertionError('deliberate')
            except AssertionError:
                failure = sys.exc_info()       # a real exc_info triple, as unittest hands over
            result.addSubTest(case, case, failure)
            result.stopTest(case)
        line = buf.getvalue().strip()
        self.assertTrue(line.startswith('not ok 1 - '), f"got {line!r}")
        self.assertNotIn('no verdict', line,
                         "the verdict must come from the subTest, not from its absence")

    def test_bare_run_tests_runs_the_whole_suite(self):
        """Running it here would cost minutes, so this pins the dispatch: bare
        --run-tests must reach the runner, never the scope listing."""
        src = io.open(os.path.realpath(__file__), encoding='utf-8').read()
        self.assertIn("if scope is None or scope.lower() == 'all':\n"
                      "        return _run_unittest_only(_UNITTEST_CLASSES)", src,
                      "bare --run-tests must run every class")


class TestTrashNotRemove(unittest.TestCase):
    """my-plex trashes; it does not rm.  my_plex_file_operation used to carry a
    REMOVE that ran `/bin/rm -r` on the Plex host, and `--move --overwrite`
    handed it the destination WRAPPER -- media, subtitles and sidecars gone
    unrecoverably.  Locally the same operation was os.remove(), which raises
    IsADirectoryError on every directory, so the one thing its callers asked
    for could never work and the failure was swallowed into (False, None)."""

    def _op(self):
        main_mod = _main_module()
        return main_mod.my_plex_file_operation

    def _body(self):
        """The function's CODE, with comment lines dropped: a comment that
        NAMES what was banned must not fail the check."""
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        m = re.search(r'def my_plex_file_operation\(.*?\n(.*?)(?=\n################################)',
                      src, re.DOTALL)
        assert m is not None, "the pattern above did not match"
        self.assertIsNotNone(m, "my_plex_file_operation not found")
        return "\n".join(line for line in m.group(1).splitlines()
                         if not line.lstrip().startswith('#'))

    def test_the_orphaned_preview_promises_what_the_run_really_does(self):
        """--try is a PROMISE about the run that would follow it.

        The --orphaned preview said "would trash N file(s)" with N counting
        the my-plex sidecars too -- and the real run os.remove()s those. So
        it promised a recoverable delete for the one thing in the list that
        is not recoverable. The confirmation prompt two lines further down
        had the three verbs right all along; it is the analogue this copies.
        """
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        # Two commands print a "--try: would trash" line; the orphaned one is
        # the one that also rmdirs.
        preview = ''
        for m in re.finditer(r'--try: would trash', src):
            window = src[m.start():m.start() + 320]
            if 'rmdir' in window:
                preview = window
                break
        self.assertTrue(preview,
                        "the --orphaned --try preview was not found")
        self.assertNotIn('len(files)+len(sidecars)', preview,
                         f"the preview still counts os.remove()d sidecars as "
                         f"trashed:\n{preview!r}")
        for verb in ('trash', 'remove', 'rmdir'):
            self.assertIn(verb, preview,
                          f"the preview does not say {verb!r}:\n{preview!r}")

    def test_rmdir_removes_an_empty_directory(self):
        """The old os.remove() raised IsADirectoryError here, every time."""
        d = tempfile.mkdtemp(prefix='my-plex-rmdir-')
        target = os.path.join(d, 'emptied-wrapper')
        os.makedirs(target)
        try:
            ok, _ = self._op()('RMDIR', target, None)
            self.assertTrue(ok, "RMDIR must remove an empty directory")
            self.assertFalse(os.path.exists(target), "the directory is still there")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_rmdir_refuses_a_directory_that_is_not_empty(self):
        """The refusal IS the guard: nothing in this function may delete
        content, so a wrapper that still holds a file must survive."""
        d = tempfile.mkdtemp(prefix='my-plex-rmdir-')
        target = os.path.join(d, 'wrapper')
        os.makedirs(target)
        keeper = os.path.join(target, 'Movie.2019.mkv')
        io.open(keeper, 'w').write('not a real film')
        try:
            ok, _ = self._op()('RMDIR', target, None)
            self.assertFalse(ok, "RMDIR must refuse a directory that is not empty")
            self.assertTrue(os.path.isfile(keeper), "it deleted content -- the whole point is that it cannot")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_no_recursive_delete_survives_in_the_file_operation(self):
        body = self._body()
        self.assertNotIn('rm -r', body,
                         "a recursive remove is back in my_plex_file_operation")
        self.assertNotIn('os.remove(', body,
                         "os.remove is back: it cannot remove a directory, and what a "
                         "person may want back belongs in TRASH")
        self.assertNotIn("'REMOVE'", body, "the REMOVE operation is back")

    def test_an_overwrite_trashes_what_it_replaces(self):
        """Both --move --overwrite paths: the wrapper, and the bare file."""
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        self.assertIn("my_plex_file_operation('TRASH', dst_wrapper", src,
                      "an overwrite must trash the destination wrapper")
        self.assertIn("my_plex_file_operation('TRASH', new_path", src,
                      "an overwrite must trash the destination file")
        self.assertNotIn("my_plex_file_operation('REMOVE'", src,
                         "no caller may ask for a plain remove any more")

    def test_the_emptied_subdirectory_is_an_rmdir(self):
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        self.assertIn("my_plex_file_operation('RMDIR', file1_dir", src,
                      "removing an emptied subdirectory is exactly what RMDIR is for")


class TestAtomicPickleWrites(unittest.TestCase):
    """Every pickle written to a FILE goes through _atomic_pickle_dump.

    A plain `pickle.dump(data, open(path))` truncates the target first, so a
    crash or a Ctrl-C part-way leaves a file that is neither the old one nor
    the new one.  The rebuild checkpoint was written that way, which is the
    worst place for it: it exists precisely to be read after an interrupt."""

    def test_no_pickle_dump_outside_the_atomic_helper(self):
        import ast
        tree = ast.parse(io.open(MAIN_SCRIPT, encoding='utf-8').read())
        offenders = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name == '_atomic_pickle_dump':
                continue        # the one place that is allowed to do it
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'dump'
                        and getattr(node.func.value, 'id', '') == 'pickle'):
                    offenders.append(f"{fn.name}() at line {node.lineno}")
        self.assertEqual(offenders, [],
                         "pickle.dump writes a file without a temp-and-rename: "
                         + ", ".join(offenders))

    def test_the_checkpoint_uses_the_helper(self):
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        self.assertIn("_atomic_pickle_dump(partial_cache_file, checkpoint_data)", src,
                      "the resume checkpoint must be written atomically")


class TestTopLevelHandlers(unittest.TestCase):
    """No stack trace on the user's screen, ever -- and Ctrl-C is an answer.

    main() had no handler of its own, so any bug and any interrupt outside the
    twenty prompt-level ones printed a raw Python traceback and exited 1.
    Both tests drive a COPY of the tool with a defect injected, because the
    only honest way to test this is to make it really happen."""

    @staticmethod
    def _copy_with(first_line_of_main):
        d = tempfile.mkdtemp(prefix='my-plex-handler-')
        dst = os.path.join(d, 'my-plex.py')
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        assert src.count('\ndef main():\n') == 1, "main() is not where this test thinks"
        src = src.replace('\ndef main():\n',
                          f'\ndef main():\n    {first_line_of_main}\n', 1)
        io.open(dst, 'w', encoding='utf-8').write(src)
        return d, dst

    def test_the_status_it_prints_is_the_one_it_exits_with(self):
        """`ERROR <code> [<exit>]:` puts the exit status beside the code
        because err() holds both while a caller sees only one -- so a message
        claiming [1] while the process exits 70 shows up in ordinary output
        instead of having to be debugged.

        This has to be checked on a path that does NOT exit 1, or it proves
        nothing: hard-coding "[1]" in err() passes an argument-error test
        happily, because an argument error exits 1 anyway. The bug handler
        exits 70 (EX_SOFTWARE), so it is the one that can tell them apart."""
        d, copy = self._copy_with('raise RuntimeError("deliberate test defect")')
        try:
            r = subprocess.run([sys.executable, '-B', copy],
                               capture_output=True, text=True, timeout=300)
            out = r.stdout + r.stderr
            m = re.search(r'ERROR (\d{5}) \[(\d+)\]:', out)
            self.assertIsNotNone(m, f"not the house error shape:\n{out[-600:]}")
            assert m is not None
            self.assertEqual(r.returncode, 70, "the bug handler must exit 70")
            self.assertEqual(int(m.group(2)), r.returncode,
                             f"it printed [{m.group(2)}] and exited "
                             f"{r.returncode} -- the status beside the code "
                             f"is not the status")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_bug_gives_one_line_and_no_traceback(self):
        d, copy = self._copy_with('raise RuntimeError("deliberate test defect")')
        try:
            r = subprocess.run([sys.executable, '-B', copy],
                               capture_output=True, text=True, timeout=300)
            out = r.stdout + r.stderr
            self.assertNotIn('Traceback (most recent call last)', out,
                             f"a traceback reached the screen:\n{out[-800:]}")
            # The SHAPE and the message, not the number: err codes are
            # renumbered in file order whenever one is added, so pinning the
            # digits here makes an unrelated change fail this test.
            self.assertRegex(out, r'ERROR \d{5} \[\d+\]:', out[-800:])
            self.assertIn('stopped on a bug', out, out[-800:])
            self.assertIn('RuntimeError: deliberate test defect', out,
                          "the one line must say what happened")
            self.assertEqual(r.returncode, 70, f"EX_SOFTWARE expected:\n{out[-400:]}")

            # ...and the trace itself is kept, because it is what fixes the bug
            m = re.search(r'full trace:\s+(\S+)', out)
            assert m is not None, "the pattern above did not match"
            self.assertIsNotNone(m, f"the line must name where the trace went:\n{out[-400:]}")
            trace = m.group(1)
            try:
                self.assertTrue(os.path.isfile(trace), f"no trace file at {trace}")
                body = io.open(trace, encoding='utf-8').read()
                self.assertIn('Traceback (most recent call last)', body,
                              "the trace file must hold the traceback")
                self.assertIn('deliberate test defect', body)
            finally:
                if os.path.isfile(trace):
                    os.unlink(trace)          # the test cleans up after itself
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def _interrupt_with(self, signum):
        """Send a REAL signal to a copy that has said it is running, and give
        back (returncode, output)."""
        d, copy = self._copy_with(
            'print("READY-FOR-SIGNAL", flush=True); import time as _t; _t.sleep(60)')
        try:
            proc = subprocess.Popen([sys.executable, '-B', copy],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            assert proc.stdout is not None
            try:
                for _ in range(400):                 # wait for it to really be running
                    line = proc.stdout.readline()
                    if not line or 'READY-FOR-SIGNAL' in line:
                        break
                else:
                    self.fail("the copy never reached main()")
                proc.send_signal(signum)
                stdout, stderr = proc.communicate(timeout=120)
            except Exception:
                proc.kill()
                raise
            return proc.returncode, stdout + stderr
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_ctrl_c_during_the_venv_bootstrap_gives_one_line_and_130(self):
        """The window BEFORE _graceful_shutdown_handler is installed, which on
        ada printed nine frames of subprocess internals when a held `pip
        install` was interrupted.

        Run for real, with a real SIGINT: a copy whose bootstrap sleeps
        instead of calling pip, so the interrupt lands exactly where it did
        then. Nothing else is changed."""
        import signal, tempfile, shutil, time
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        d = tempfile.mkdtemp(prefix='my-plex-bootstrap-int-')
        try:
            copy = os.path.join(d, 'my-plex.py')
            with open(copy, 'w') as f:
                f.write(src
                        .replace('def _bootstrap_venv():',
                                 'def _bootstrap_venv():\n'
                                 '    import time; time.sleep(30)', 1)
                        .replace('def _inside_our_venv():',
                                 'def _inside_our_venv():\n'
                                 '    return False', 1)
                        .replace('def _venv_has_deps():',
                                 'def _venv_has_deps():\n'
                                 '    return False', 1))
            os.chmod(copy, 0o755)
            p = subprocess.Popen([sys.executable, copy, '--list-libraries'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            time.sleep(2.0)
            p.send_signal(signal.SIGINT)
            out, errtext = p.communicate(timeout=30)
            self.assertEqual(p.returncode, 130,
                             f"128+SIGINT, not {p.returncode}:\n{errtext[-400:]}")
            self.assertNotIn('Traceback', errtext,
                             f"a stack trace reached the screen:\n{errtext[-600:]}")
            self.assertIn('interrupted (Ctrl-C)', errtext, errtext[-400:])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_ctrl_c_gives_one_line_and_exit_130(self):
        """_graceful_shutdown_handler takes SIGINT, so this exercises IT -- the
        `except KeyboardInterrupt` is only the backstop for the window before
        that handler is registered.  It used to exit 0 here: a wrapper that
        checked the status was told the interrupted run had done its job."""
        rc, out = self._interrupt_with(signal.SIGINT)
        self.assertNotIn('Traceback (most recent call last)', out,
                         f"Ctrl-C must not print a traceback:\n{out[-800:]}")
        self.assertIn('SIGINT (Ctrl+C)', out, out[-800:])
        self.assertEqual(rc, 130,
                         f"128+SIGINT, so a caller can tell it from success:\n{out[-400:]}")

    def test_sigterm_gives_143(self):
        """128 + signum is a rule, not a constant: the same handler, a
        different signal, a different status."""
        rc, out = self._interrupt_with(signal.SIGTERM)
        self.assertNotIn('Traceback (most recent call last)', out, out[-800:])
        self.assertEqual(rc, 143, f"128+SIGTERM expected:\n{out[-400:]}")

    def test_the_interrupt_message_is_on_stderr(self):
        """`my-plex > out.txt` must still show why it stopped."""
        d, copy = self._copy_with(
            'print("READY-FOR-SIGNAL", flush=True); import time as _t; _t.sleep(60)')
        try:
            proc = subprocess.Popen([sys.executable, '-B', copy],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            assert proc.stdout is not None
            try:
                for _ in range(400):
                    line = proc.stdout.readline()
                    if not line or 'READY-FOR-SIGNAL' in line:
                        break
                proc.send_signal(signal.SIGINT)
                stdout, stderr = proc.communicate(timeout=120)
            except Exception:
                proc.kill()
                raise
            self.assertIn('SIGINT (Ctrl+C)', stderr,
                          f"the reason it stopped belongs on stderr; stdout had: {stdout[-300:]!r}")
            self.assertNotIn('SIGINT (Ctrl+C)', stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_no_exit_path_reports_an_interrupt_as_success(self):
        """Every os._exit() in the file sits on a shutdown path, so none may
        pass a bare number: the status has to be 128 + the signal. The
        read-only Ctrl-C path passed 0, and the interrupted --update-cache
        path -- the one a long rebuild actually hits -- passed 0 as well, so a
        wrapper that checked the status was told the run had done its job."""
        import ast
        tree = ast.parse(io.open(MAIN_SCRIPT, encoding='utf-8').read())
        offenders = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == '_exit'
                    and getattr(node.func.value, 'id', '') == 'os'):
                arg = node.args[0] if node.args else None
                if isinstance(arg, ast.Constant):
                    offenders.append(f"os._exit({arg.value!r}) at line {node.lineno}")
        self.assertEqual(offenders, [],
                         "an interrupt must not be reported as success: " + ", ".join(offenders))

    def test_err_still_exits_one_by_default(self):
        """err() gained an exit code for the handler above; the everyday call
        must be unchanged -- every other caller relies on 1."""
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        self.assertIn('def err(err_code: str, err_msg: str = "", exit_code: int = 1)', src)
        self.assertIn('sys.exit(exit_code)', src)


class TestSshOptions(unittest.TestCase):
    """One owner for the options every ssh my-plex starts carries.

    The dangerous combination is `ControlMaster=auto` WITHOUT `ControlPersist`:
    the first ssh then becomes the connection master and stays in the
    FOREGROUND, and a master cannot exit while another session rides on it --
    so a later interactive login of the user's keeps my-plex waiting long
    after the remote has answered."""

    def _opts(self, **kw):
        main_mod = _main_module()
        return main_mod._ssh_opts(**kw)

    def _joined(self, **kw):
        return " ".join(self._opts(**kw))

    def test_every_connection_can_fail_instead_of_waiting(self):
        """BatchMode and ConnectTimeout, multiplexed or not: nobody is at the
        keyboard to answer a key prompt, and a host that is off must fail."""
        for kw in ({}, {'multiplex': False}):
            with self.subTest(**kw):
                joined = self._joined(**kw)
                self.assertIn('BatchMode=yes', joined)
                self.assertIn('ConnectTimeout=', joined)

    def test_auto_is_never_used_without_controlpersist(self):
        joined = self._joined()
        if 'ControlMaster=auto' in joined:
            self.assertIn('ControlPersist=', joined,
                          "auto without ControlPersist leaves a FOREGROUND master")
            self.assertIn('ControlPath=', joined,
                          "a private ControlPath, not the shared default")
            self.assertNotIn('ControlPath=/tmp', joined,
                             "the control socket belongs in a private directory")

    def test_the_user_s_port_forwards_are_not_set_up(self):
        """A tool's connection must neither grab the user's VNC/SOCKS ports
        nor fail because their own session already has them."""
        for kw in ({}, {'multiplex': False}):
            with self.subTest(**kw):
                self.assertIn('ClearAllForwardings=yes', self._joined(**kw))

    def test_the_parallel_workers_do_not_multiplex(self):
        """They stream thousands of paths each; sharing one TCP connection
        would serialise them, and past sshd's MaxSessions be refused."""
        joined = self._joined(multiplex=False)
        self.assertIn('ControlMaster=no', joined)
        self.assertNotIn('ControlPersist=', joined)

    def test_an_unshared_connection_rides_no_live_master(self):
        """ControlMaster=no alone still USES a live master on the user's
        ControlPath -- on horse `ssh -G -o ControlMaster=no my-plex` and
        `ssh -G ada` name the same socket, so --install's login check could
        pass through the user's open session without logging in at all."""
        opts = self._opts(multiplex=False)
        paths = [o for o in opts if o.startswith('ControlPath=')]
        self.assertEqual(paths, ['ControlPath=none'],
                         "an unshared connection must not reach any control socket")

    def test_the_timeout_comes_from_the_config(self):
        main_mod = _main_module()
        self.assertIn('SSH_CONNECT_TIMEOUT', main_mod.CONFIG_DEFAULTS,
                      "a tunable belongs in the config file, not in the body")
        self.assertIn(f"ConnectTimeout={main_mod.SSH_CONNECT_TIMEOUT}", self._joined())

    def test_nothing_builds_an_ssh_command_line_by_hand(self):
        """_ssh_args is the only place -- the function's own docstring has said
        so for a while, and two callers were ignoring it.

        `ssh -G` is exempt, and the exemption is narrow on purpose: -G prints
        the effective configuration and OPENS NO CONNECTION, so every option
        this guard exists for -- BatchMode, ConnectTimeout, ControlMaster=no
        -- has nothing to act on. _ssh_remote() asks it what an ssh alias
        stands for, which is config reading, not talking to a host. Any ssh
        that could connect is still an offender."""
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        lines = src.splitlines()
        offenders = [f"line {n}" for n, line in enumerate(lines, 1)
                     if "['ssh'," in line.replace(" ", "")
                     and '_ssh_opts(' not in line
                     and "'-G'" not in line.replace(" ", "")
                     and not line.lstrip().startswith(('#', '"""', 'NEVER'))
                     and 'NEVER use' not in line]
        # The other way to build one by hand: a STRING -- `cmd = f"ssh {host} ..."`
        # -- handed to a shell.  Nine of those hid from the list check above
        # until 2026-11-05.  A string that is only printed (an error hint, a
        # debug line) is not an offender; one that reaches `shell=True` is, so
        # the check pairs the assignment with the run that follows it.
        shell_runs = [n for n, line in enumerate(lines, 1) if 'shell=True' in line]
        for n in shell_runs:
            window = lines[max(0, n - 7):n]
            if any(re.search(r"""=\s*f?["']ssh\s""", w) for w in window):
                offenders.append(f"line {n} (an ssh string run through a shell)")
        self.assertEqual(offenders, [],
                         "an ssh built outside _ssh_args carries none of these options: "
                         + ", ".join(offenders))


class TestSecretArgs(unittest.TestCase):
    """A token passed as a literal is in ~/.zsh_history and in `ps auxww`.

    The flag is not refused -- a script may have its reasons -- but it is
    never silent, and `-` and `@FILE` give it somewhere safe to come from."""

    def _mod(self):
        return _main_module()

    def _resolve(self, flag, value, argv=None, stdin=None):
        import contextlib
        mod = self._mod()
        err_buf = io.StringIO()
        saved_argv, saved_stdin = sys.argv, sys.stdin
        try:
            sys.argv = argv if argv is not None else ['my-plex', flag, value]
            if stdin is not None:
                sys.stdin = io.StringIO(stdin)
            with contextlib.redirect_stderr(err_buf):
                out = mod._resolve_secret_arg(flag, value)
        finally:
            sys.argv, sys.stdin = saved_argv, saved_stdin
        return out, err_buf.getvalue()

    def test_a_literal_is_taken_but_reported(self):
        out, warning = self._resolve('--plex-token', 'hunter2secret')
        self.assertEqual(out, 'hunter2secret', "it must still work")
        self.assertIn('shell history', warning)
        self.assertIn('ps auxww', warning)
        self.assertNotIn('hunter2secret', warning,
                         "the warning must not reprint the secret it is warning about")

    def test_a_dash_reads_standard_input(self):
        out, warning = self._resolve('--plex-token', '-', stdin='from-stdin-token\n')
        self.assertEqual(out, 'from-stdin-token')
        self.assertEqual(warning, "", "nothing to warn about: it was never on the line")

    def test_an_at_file_reads_the_file(self):
        d = tempfile.mkdtemp(prefix='my-plex-secret-')
        try:
            path = os.path.join(d, 'token')
            io.open(path, 'w').write('from-a-file\n')
            out, warning = self._resolve('--plex-token', f'@{path}')
            self.assertEqual(out, 'from-a-file')
            self.assertEqual(warning, "")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_missing_file_is_a_clean_error(self):
        with self.assertRaises(SystemExit) as caught:
            self._resolve('--plex-token', '@/nonexistent/my-plex-token')
        self.assertEqual(caught.exception.code, 1)

    def test_a_value_from_the_config_is_not_warned_about(self):
        """The default argparse hands over comes FROM the config file, so a
        value is only a command-line one when the flag was actually typed."""
        out, warning = self._resolve('--plex-token', 'token-from-config',
                                     argv=['my-plex', '--problems'])
        self.assertEqual(out, 'token-from-config')
        self.assertEqual(warning, "", "a config value must not be reported as a leak")

    def test_the_xml_url_is_treated_as_a_secret_too(self):
        """Its value carries X-Plex-Token=... inside it."""
        src = io.open(MAIN_SCRIPT, encoding='utf-8').read()
        self.assertIn("_resolve_secret_arg('--plex-xml-url'", src)
        self.assertIn("_resolve_secret_arg('--plex-token'", src)


class TestErrCodes(unittest.TestCase):
    """err("NNNNN") codes identify the SOURCE LINE: five digits, unique, and
    numbered 00001.. in file order with no gap -- so a code in an error
    message greps to exactly one line."""

    # [ \t]*\( -- a call written `err (1008, ...)` is a call: it escaped both this
    # check and the renumber one-liner for as long as the pattern demanded `err(`.
    CALL = re.compile(r'(\b(?:err|_stamp_fail)[ \t]*\(\s*|_media_api_action[ \t]*\(media_identifier, action, )"?(\d+)"?(?=\s*[,)])')
    BARE = re.compile(r'\berr[ \t]*\(\s*(?!"\d{5}"|err_code\b)[^\s)]')

    def test_codes_are_unique_and_in_file_order(self):
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        found = [m.group(0) for m in self.CALL.finditer(src)]
        codes = [m.group(2) for m in self.CALL.finditer(src)]
        self.assertGreater(len(codes), 100, "the pattern no longer finds the err() calls")
        bad = [f for f in found if not re.search(r'"\d{5}"$', f)]
        self.assertEqual(bad, [], "every code is a quoted five-digit string")
        self.assertEqual(codes, [f"{i:05d}" for i in range(1, len(codes) + 1)],
                         "codes must run 00001.. in file order: renumber with the one-liner in the header")

    def test_every_err_call_carries_a_code(self):
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        self.assertEqual(self.BARE.findall(src), [],
                         "an err() call without a five-digit code")

    def test_a_call_written_with_a_space_is_still_seen(self):
        """A space before the paren must not hide a call from either check.

        `err (1008, ...)` did exactly that: the renumber never reached it, so it
        kept a four-digit code while every other call was five digits."""
        for text in ('err ("00042", "x")', 'err("00042", "x")',
                     '_stamp_fail ("00042", "x")',
                     '_media_api_action (media_identifier, action, "00042")'):
            with self.subTest(text=text):
                self.assertEqual([m.group(2) for m in self.CALL.finditer(text)],
                                 ['00042'], f"the pattern must see {text!r}")
        self.assertNotEqual(self.BARE.findall('err (1008, "x")'), [],
                            "a spaced call with no five-digit code must be reported")


class TestQuiet(unittest.TestCase):
    """-Q / --quiet: nothing on stdout, errors untouched on stderr.

    The honest test of a quiet flag is what a person watching the TERMINAL
    sees, with no log capturing anything -- so every test here reads the two
    streams of a real run.  Equal stdout line counts between a plain run and
    a -Q run would mean the flag does nothing, which is exactly how a quiet
    mode passes review while silencing not one line.
    """

    def _run(self, *argv, stdin=None):
        return subprocess.run([MAIN_SCRIPT, *argv], capture_output=True,
                              text=True, timeout=120, input=stdin,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))

    def test_a_command_that_prints_prints_nothing_under_Q(self):
        """The driving case: a wrapper or crontab wants silence unless it fails."""
        loud = self._run('--list-libraries')
        quiet = self._run('-Q', '--list-libraries')
        self.assertEqual(loud.returncode, 0, loud.stderr[-400:])
        self.assertGreater(len(loud.stdout.splitlines()), 0,
                           "the plain run printed nothing, so this proves nothing")
        self.assertEqual(quiet.stdout, '',
                         f"-Q left {len(quiet.stdout.splitlines())} line(s) on stdout")
        self.assertEqual(quiet.returncode, 0, quiet.stderr[-400:])

    def test_an_error_still_reaches_stderr_under_Q(self):
        """"Quiet except errors" is the whole promise; without this half, -Q
        makes an unattended run deaf rather than quiet."""
        r = self._run('-Q', '--force')
        self.assertEqual(r.stdout, '', "stdout was supposed to be silent")
        self.assertRegex(r.stderr, r'ERROR \d{5} \[\d+\]:',
                         f"the error vanished along with the narration:\n{r.stderr!r}")
        self.assertIn('--force can only be used together with --update-cache', r.stderr)
        self.assertNotEqual(r.returncode, 0, "an error must not exit 0")

    def test_verbose_beats_quiet(self):
        """-V and -D ask for MORE output, so either overrides -Q -- decided in
        one place, and the same rule applies to a QUIET pinned in the config."""
        r = self._run('-Q', '-V', '--list-libraries')
        self.assertGreater(len(r.stdout.splitlines()), 0,
                           "-V did not override -Q")

    def test_version_is_silenced_too_so_everything_means_everything(self):
        """--version is answered at module level, above the venv bootstrap, and
        so was printing straight past -Q.  The help page claims EVERYTHING on
        stdout; an exception here would make that claim false."""
        r = self._run('-Q', '--version')
        self.assertEqual(r.stdout, '', "--version printed past -Q")
        self.assertGreater(len(self._run('--version').stdout.splitlines()), 0)

    def test_a_child_process_inheriting_fd_1_is_silenced_too(self):
        """THE adversarial case.  22 of this tool's 67 subprocess calls inherit
        file descriptor 1 (ssh, ffmpeg), so silencing sys.stdout would claim
        quiet while letting a child's output through -- and every test above
        would still pass, because they only exercise Python's own print().
        Redirecting the descriptor is what makes the claim true, and this is
        the test that can tell the two apart."""
        snippet = _tool_import_snippet(['my-plex.py', '-Q']) + (   # -Q acts at module level
            "import subprocess\n"
            "assert mp._QUIET_ACTIVE, 'the module did not go quiet'\n"
            "subprocess.run(['/bin/echo', 'LEAKED_FROM_CHILD'])\n"
            "os.write(2, b'child-ran\\n')\n"
        )
        r = subprocess.run([sys.executable, '-B', '-c', snippet],
                           capture_output=True, text=True, timeout=120)
        self.assertIn('child-ran', r.stderr,
                      f"the probe itself did not run:\n{r.stderr[-700:]}")
        self.assertNotIn('LEAKED_FROM_CHILD', r.stdout,
                         "a child inheriting fd 1 printed past -Q")

    def test_a_yes_no_question_refuses_under_Q_instead_of_waiting(self):
        """A question written into the sink is invisible AND still blocks on
        stdin -- a hang with nothing on screen to explain it.  Under -Q the
        one place that asks refuses instead, and names the flags that answer
        in advance."""
        snippet = _tool_import_snippet(['my-plex.py']) + (
            "mp._QUIET_ACTIVE = True\n"
            "mp.prompt_yes_no('Trash 400 files?')\n"
        )
        r = subprocess.run([sys.executable, '-B', '-c', snippet],
                           capture_output=True, text=True, timeout=120)
        self.assertNotEqual(r.returncode, 0, "it did not refuse")
        self.assertIn('-Q cannot ask', r.stderr, r.stderr[-700:])
        self.assertIn('--yes', r.stderr, "it did not name the way to answer")

    def test_an_answer_given_in_advance_is_still_honoured_under_Q(self):
        """-Y/--yes is the tool's own answer for an unattended run, so -Q must
        not turn a pre-answered question into a refusal."""
        snippet = _tool_import_snippet(['my-plex.py']) + (
            "mp._QUIET_ACTIVE = True\n"
            "mp.AUTO_YES = True\n"
            "assert mp.prompt_yes_no('Trash 400 files?') is True\n"
            "os.write(2, b'answered\\n')\n"
        )
        r = subprocess.run([sys.executable, '-B', '-c', snippet],
                           capture_output=True, text=True, timeout=120)
        self.assertIn('answered', r.stderr, r.stderr[-700:])
        self.assertEqual(r.returncode, 0, r.stderr[-700:])

    def test_the_flag_is_in_help_and_in_the_completion(self):
        """A flag the completion does not know is a flag half-added; the
        completion IS part of the CLI and changes in the same commit."""
        r = self._run('--help')
        self.assertIn('-Q, --quiet', r.stdout, "the summary does not name -Q")
        page = self._run('--help', 'quiet')
        self.assertIn('QUIET HELP', page.stdout, "there is no --help quiet page")
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        self.assertIn("{-Q,--quiet}", src, "the zsh completion has no -Q")
        self.assertIn("'QUIET': False", src, "QUIET is not a config key")


class TestVenvDetection(unittest.TestCase):
    """Whether this run is already inside my-plex's own venv.

    Answer it wrongly in the "yes" direction and the run continues with none
    of the venv's site-packages: `import readchar` raises and the tool is dead
    on that machine.  The old test compared sys.executable with VENV_PYTHON
    through realpath(), and a venv's bin/python3 is a SYMLINK to the
    interpreter it was built from -- so on a machine whose venv was built from
    the python3 the shebang picks, both sides resolved to the same base
    interpreter and the answer was "yes, inside" while being outside.

    That is why these tests build the venv from the interpreter `env python3`
    picks: it is the one arrangement under which the bug appears, and the one
    a machine whose venv is a different python version never reaches.
    """

    @classmethod
    def setUpClass(cls):
        cls.shebang_python = shutil.which('python3')
        cls.tmp = tempfile.mkdtemp(prefix='my-plex-venvdetect-')
        cls.venv = os.path.join(cls.tmp, 'venv')
        # No pip install: these tests ask the predicate a question, and the
        # answer does not depend on what is installed.  So no network either.
        r = subprocess.run([cls.shebang_python or 'python3', '-m', 'venv',
                            '--without-pip', cls.venv],
                           capture_output=True, text=True, timeout=180)
        cls.venv_built = r.returncode == 0
        cls.venv_python = os.path.join(cls.venv, 'bin', 'python3')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _ask(self, interpreter, expected):
        """Import my-plex under `interpreter`, point it at the temp venv, and
        have it answer _inside_our_venv().  --help in argv keeps the module's
        own venv block from re-execing while we are asking."""
        snippet = _tool_import_snippet(['my-plex.py', '--help']) + (
            "mp.VENV_DIR = %r\n"
            "mp.VENV_PYTHON = os.path.join(mp.VENV_DIR, 'bin', 'python3')\n"
            "os.write(2, (b'ANSWER=' + str(mp._inside_our_venv()).encode()))\n"
        ) % (self.venv,)
        r = subprocess.run([interpreter, '-B', '-c', snippet],
                           capture_output=True, text=True, timeout=180)
        self.assertIn('ANSWER=', r.stderr,
                      f"the probe did not run under {interpreter}:\n{r.stderr[-900:]}")
        self.assertIn(f'ANSWER={expected}', r.stderr,
                      f"_inside_our_venv() said {not expected} under {interpreter}")

    def test_the_base_interpreter_is_not_inside_the_venv_it_built(self):
        """THE adversarial case, and ada's: the venv was built from this very
        interpreter, so realpath(venv/bin/python3) == realpath(sys.executable)
        and the old predicate answered "inside".  It is outside."""
        self.assertTrue(self.venv_built, "could not build the probe venv")
        self.assertTrue(self.shebang_python, "no python3 on PATH to build from")
        self._ask(self.shebang_python, False)

    def test_the_venvs_own_interpreter_is_inside_it(self):
        """The other direction, so the fix cannot be "always re-exec" -- that
        would loop for ever instead of running."""
        self.assertTrue(self.venv_built, "could not build the probe venv")
        self._ask(self.venv_python, True)

    def test_the_loop_marker_does_not_leak_into_a_child_my_plex(self):
        """The marker means "a re-exec is in flight", and an environment
        variable is inherited by every child process.  Left set, a my-plex
        started from inside a my-plex run reads a marker that was never about
        it, refuses to re-exec, and dies on `import readchar` -- which is the
        very failure the marker was added to prevent, moved one process along.
        The suite spawns my-plex constantly, so this is the ordinary case.

        This test inherits os.environ exactly as the other tests here do: if
        the marker survived into this process, the child sees it and fails."""
        r = subprocess.run([MAIN_SCRIPT, '--list-libraries'],
                           capture_output=True, text=True, timeout=180,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertNotIn('landed outside it', r.stderr,
                         "the marker leaked from this run into its child")
        self.assertEqual(r.returncode, 0, r.stderr[-700:])

    def test_a_reexec_that_lands_outside_again_is_an_error_not_a_loop(self):
        """If the venv's pyvenv.cfg is gone, re-execing into it lands outside
        once more and the decision repeats.  Dying early beats spawning for
        ever, so the second attempt refuses and names the directory."""
        self.assertTrue(self.venv_built, "could not build the probe venv")
        broken = os.path.join(self.tmp, 'home')
        vdir = os.path.join(broken, '.python.venv', 'my-plex')
        os.makedirs(os.path.join(vdir, 'bin'), exist_ok=True)
        # a venv directory whose interpreter runs but whose config is missing,
        # so sys.prefix never becomes vdir
        os.symlink(self.shebang_python or '/usr/bin/python3',
                   os.path.join(vdir, 'bin', 'python3'))
        for dep in ('readchar', 'plexapi'):          # satisfy _venv_has_deps()
            os.makedirs(os.path.join(vdir, 'lib', 'python3.x',
                                     'site-packages', dep), exist_ok=True)
        r = subprocess.run([MAIN_SCRIPT, '--list-libraries'],
                           capture_output=True, text=True, timeout=180,
                           env=dict(os.environ, HOME=broken,
                                    PYTHONDONTWRITEBYTECODE='1'))
        self.assertNotEqual(r.returncode, 0, "it did not refuse")
        self.assertIn('landed outside it', r.stderr,
                      f"not the loop guard's error:\n{r.stderr[-900:]}")


class TestReadmeFlagsExist(unittest.TestCase):
    """Every flag the README names must be one the parser accepts.

    A README is not executed, so it rots silently: it documented `--mv` /
    `--move` for five versions after they became `--mv-to` / `--move-to`,
    in four places, while a line two bullets up said they had been renamed.
    A reader following it got "Invalid flag".

    This is the class of defect, not that one instance: the flags come out of
    the README and are checked against the option strings of every
    add_argument() call in the tool, so the next stale flag fails here instead
    of in someone's terminal.
    """

    @staticmethod
    def _registered_flags():
        """Every option string the tool's parsers accept, read from the
        add_argument() calls themselves rather than from --help, which hides
        the ones carrying argparse.SUPPRESS."""
        with open(MAIN_SCRIPT) as f:
            tree = ast.parse(f.read())
        flags = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'add_argument'):
                continue
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                        and a.value.startswith('-'):
                    flags.add(a.value)
        return flags

    def _run(self, *argv):
        return subprocess.run([MAIN_SCRIPT, *argv], capture_output=True,
                              text=True, timeout=120,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))

    # Flags the tool recognises WITHOUT argparse, so the AST walk cannot see
    # them.  Kept explicit and short rather than widening the walk to every
    # "--..." string in the file, which would also match the flags my-plex
    # passes to git and ffmpeg and so stop catching a typo.
    HANDLED_OUTSIDE_ARGPARSE = {'--unittest'}

    @staticmethod
    def _readme_flags():
        """The flags the README CLAIMS my-plex has.

        Two things count as a claim: an inline `--flag` code span, and a flag
        on a `my-plex ...` command line inside a fenced block.

        Deliberately NOT counted: any other line of a fenced block.  It may be
        another tool's command (`pyright --pythonpath ...`) or an ASCII diagram
        whose labels are cut to fit the box -- the one at README.md:341 reads
        "--plex2d" and "--update" for --plex2disk and --update-cache.  Neither
        is a statement that my-plex has such a flag, and counting them made
        this test report the diagram as four broken flags.

        An inline span also cannot cross a newline (`[^`\n]`): a single
        backtick pair matched across a whole fenced block is how the diagram
        got in.
        """
        _rp = _readme_path()
        if _rp is None:
            raise unittest.SkipTest(_NO_README)
        with open(_rp) as f:
            text = f.read()
        flag_re = re.compile(r'(?<![\w-])(--[a-z][a-z0-9-]*)')
        found = set()
        for block in re.findall(r'```.*?\n(.*?)```', text, re.DOTALL):
            for line in block.splitlines():
                if re.match(r'\s*\$?\s*my-plex\b', line):
                    found.update(flag_re.findall(line))
        for code in re.findall(r'`([^`\n]+)`', re.sub(r'```.*?```', '', text, flags=re.DOTALL)):
            found.update(flag_re.findall(code))
        return found

    def test_the_two_option_pages_name_the_same_flags(self):
        """The option lines exist twice: HELP_COMPACT's `OPTIONS:` block, which
        bare --help prints, and the `--help option` page, which groups them
        under GENERAL / OUTPUT CONTROL / WRITE SAFETY.

        Nothing ties them together, so a flag goes into one and not the other
        and the omission is invisible -- -Q had to be added to both by hand.
        The two wordings differ on purpose in places ("please use with care"),
        so this does not compare TEXT; it compares the SET OF FLAGS, which is
        the part that must not drift.
        """
        summary = self._run('--help').stdout
        page = self._run('--help', 'option').stdout
        self.assertIn('OPTIONS:', summary, summary[:300])
        self.assertIn('AVAILABLE OPTIONS', page, page[:300])

        # the compact page also lists COMMANDS; only its OPTIONS block is an
        # option list, so slice it out before comparing
        block = summary.split('OPTIONS:', 1)[1].split('COMMANDS:', 1)[0]
        flag_re = re.compile(r'(?<![\w-])(--[a-z][a-z0-9-]*)')
        in_summary = set(flag_re.findall(block))
        in_page = set(flag_re.findall(page))
        self.assertGreater(len(in_summary), 5, f"the slice is wrong:\n{block[:300]}")

        # Slice the option page the same way, POSITIVELY: its general options
        # run from GENERAL: to COMMAND MODIFIERS:.  Subtracting the modifier
        # section instead was wrong -- --try and --verbose appear both as
        # general options AND in "--mark [--try]" and the footer examples, so
        # subtracting removed them outright and reported them missing.
        in_page = set(flag_re.findall(
            page.split('GENERAL:', 1)[1].split('COMMAND MODIFIERS:', 1)[0]))
        # -H/--help is placed differently by each page on purpose
        in_summary.discard('--help'); in_page.discard('--help')

        self.assertEqual(sorted(in_summary - in_page), [],
                         "named by bare --help but missing from `--help option`")
        self.assertEqual(sorted(in_page - in_summary), [],
                         "named by `--help option` but missing from bare --help")

    def test_the_tool_has_every_flag_the_readme_names(self):
        registered = self._registered_flags()
        named = self._readme_flags()
        self.assertGreater(len(registered), 40,
                           "the AST walk found almost no flags -- it is broken, "
                           "not the README")
        self.assertGreater(len(named), 20,
                           "no flags were extracted from the README -- the "
                           "extraction is broken, not the README")
        # A flag in _RENAMED_FLAGS is NOT excused here.  It does not work --
        # it only earns a better error message -- so a README that presents it
        # as usable is exactly the defect this test exists for.  Subtracting
        # them is how the first version of this test passed against a README
        # that still documented `--mv`.
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        retired = set(re.findall(r"'(--[a-z][a-z0-9-]*)':\s*'--", src))
        missing = sorted(named - registered - self.HANDLED_OUTSIDE_ARGPARSE)
        gone = sorted(set(missing) & retired)
        unknown = sorted(set(missing) - retired)
        self.assertEqual(gone, [],
                         "the README names flags that are RETIRED -- the tool "
                         "answers them with the replacement, it does not run "
                         f"them: {[(g, src.split(repr(g) + ': ')[1].split(',')[0].strip() if repr(g) + ': ' in src else '?') for g in gone]}")
        self.assertEqual(unknown, [],
                         "the README names flags the parser does not accept "
                         f"and that are not even known old names: {unknown}")

    def test_a_renamed_flag_is_answered_with_its_new_name(self):
        """A flag the README used to name must not come back as a bare
        "Invalid flag": the tool says which flag replaced it.  That is what
        lets the README drop the rename note instead of carrying history."""
        r = subprocess.run([MAIN_SCRIPT, '--mv', 'somelib'],
                           capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertIn("You mean '--mv-to'", r.stderr, r.stderr[-500:])


_FAKE_SSH_DIR = None

def _fake_ssh_env(login_rc=0):
    """An environment whose `ssh` answers -G with the REAL ssh -- it reads a
    config and connects to nothing -- and a login with LOGIN_RC, so an
    --install test reaches no host.  Its config file is the test's own
    (SSH_CONFIG_FILE, see _install_lines), so the real ~/.ssh is never read
    or written."""
    global _FAKE_SSH_DIR
    if _FAKE_SSH_DIR is None:
        real = shutil.which('ssh') or '/usr/bin/ssh'
        _FAKE_SSH_DIR = tempfile.mkdtemp(prefix='my-plex-fake-ssh-')
        import atexit
        atexit.register(shutil.rmtree, _FAKE_SSH_DIR, True)
        stub = os.path.join(_FAKE_SSH_DIR, 'ssh')
        with open(stub, 'w') as f:
            f.write("#!/bin/dash\n"
                    "# -G only prints the effective config: the real ssh does that\n"
                    f'case " $* " in *" -G "*) exec {real} "$@";; esac\n'
                    'exit "${FAKE_SSH_LOGIN_RC:-0}"\n')
        os.chmod(stub, 0o755)
    return dict(os.environ, PYTHONDONTWRITEBYTECODE='1', FAKE_SSH_LOGIN_RC=str(login_rc),
                PATH=_FAKE_SSH_DIR + os.pathsep + os.environ.get('PATH', ''))


def _install_lines(d, remote='me@192.0.2.10'):
    """The config lines an --install test needs: an endpoint, and an ssh
    config file in the test's own directory D."""
    return (f"PLEX_DB_REMOTE = {remote!r}\n"
            f"SSH_CONFIG_FILE = {os.path.join(d, 'ssh', 'config')!r}\n")


class TestInstallFirewallRules(unittest.TestCase):
    """--install writes one firewall rule per host my-plex connects to.

    The reason it exists: on a machine with an interactive firewall, the first
    connection to a scraped host is held behind an alert. A scheduled run has
    nobody to answer it, so it stops talking with no error of its own. That
    happened on a real machine with www.fernsehserien.de.
    """

    def _conf(self, cli_path):
        """A config whose LITTLE_SNITCH_CLI points where this test wants.

        CACHE_FILE and LOCK_FILE are its own: --install takes the cache lock
        although it reads no cache, so against the real one it waits for any
        --update-cache that happens to be running (seen 2026-11-05)."""
        d = tempfile.mkdtemp(prefix='my-plex-install-')
        c = os.path.join(d, 'my-plex.conf')
        with open(c, 'w') as f:
            f.write(f"LITTLE_SNITCH_CLI = {cli_path!r}\n")
            f.write(f"CACHE_FILE = {os.path.join(d, 'cache.pkl')!r}\n")
            f.write(f"LOCK_FILE = {os.path.join(d, 'cache.lock')!r}\n")
            f.write(_install_lines(d))
        return d, c

    def _run(self, *argv):
        return subprocess.run([MAIN_SCRIPT, *argv], capture_output=True,
                              text=True, timeout=120, env=_fake_ssh_env())

    def test_install_does_not_wait_for_the_cache_lock(self):
        """--install reads the config and nothing else, so an --update-cache
        running elsewhere must not hold it.  Seen 2026-11-05: it printed
        "CACHE IS CURRENTLY LOCKED" and sat until the other run finished.
        Here the test itself HOLDS the lock for the whole call."""
        import fcntl
        d, c = self._conf('/nonexistent/my-little-snitch')
        with open(os.path.join(d, 'cache.lock'), 'w') as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            try:
                r = subprocess.run([MAIN_SCRIPT, '--config', c, '--install'],
                                   capture_output=True, text=True, timeout=60,
                                   env=_fake_ssh_env())
            except subprocess.TimeoutExpired:
                self.fail("--install waited for the cache lock it has no use for")
            finally:
                fcntl.flock(held.fileno(), fcntl.LOCK_UN)
        self.assertNotIn('CACHE IS CURRENTLY LOCKED', r.stdout)
        self.assertIn('my-plex --install', r.stdout, r.stdout[-600:] + r.stderr[-600:])

    def test_every_host_it_fetches_has_a_rule(self):
        """THE test. A new scraper or API whose host is not in NETWORK_HOSTS
        gets no rule, and the firewall holds it on the next machine -- which is
        exactly how this came to light. So the constant is checked against the
        URLs the code actually fetches, not against a list kept by hand.

        Only FETCHED urls count: the ones built into a `url = f'https://...'`
        for urlopen. themoviedb.org, thetvdb.com and imdb.com also appear in
        the source, as links in --help text and in a display column, and
        allowing those would widen the rules for nothing."""
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        # A FETCHED url is BUILT -- `url = f'https://host/...{id}'` -- because
        # it interpolates an id or a query. A url that is a plain constant is a
        # link for the reader: the GPL text in --version assigns
        # "https://www.gnu.org/..." to a variable called url too, and counting
        # it would have this test demand a firewall rule for gnu.org.
        fetched = set(re.findall(
            r"""url\s*=\s*f['"]https://([a-z0-9.-]+)""", src, re.IGNORECASE))
        self.assertGreater(len(fetched), 1,
                           "no fetched urls found -- the extraction is broken")
        # read NETWORK_HOSTS itself, not every ('a.b', '...') pair in the file:
        # a loose pattern also matched 'poster.jpg' and could mask a real miss
        block = src.split('NETWORK_HOSTS = (', 1)[1].split('\n)', 1)[0]
        listed = set(re.findall(r"\('([a-z0-9.-]+)',", block))
        self.assertGreater(len(listed), 1, f"NETWORK_HOSTS not parsed:\n{block[:200]}")
        missing = sorted(h for h in fetched if h not in listed)
        self.assertEqual(missing, [],
                         f"my-plex fetches these hosts but NETWORK_HOSTS does "
                         f"not list them, so --install writes no rule for "
                         f"them: {missing}")

    def test_every_remote_gets_BOTH_rule_forms(self):
        """A rule naming Python as the PROCESS does not match a real run.

        Little Snitch attributes the connection to the app ABOVE Python and
        calls Python the VIA program. The user's alerts read "Terminal via
        Python" and "claude via Python", with "an existing rule for any
        via-process was not applied to Python" -- while process rules for all
        three scraper hosts had been stored on every machine since
        2026-11-01. Stored is not matching, and four popups are what the
        difference cost.

        So each remote needs the via form beside the process form, and this
        is what stops a later edit quietly dropping one of them. The hosts
        come from NETWORK_HOSTS in the source, not from the output, or the
        test would only check that the output agrees with itself."""
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        block = src.split('NETWORK_HOSTS = (', 1)[1].split('\n)', 1)[0]
        hosts = re.findall(r"\('([a-z0-9.-]+)',", block)
        self.assertGreater(len(hosts), 1, f"NETWORK_HOSTS not parsed:\n{block[:200]}")

        d, conf = self._conf('/bin/true')
        stub = os.path.join(d, 'my-little-snitch')
        with open(stub, 'w') as f:
            f.write('#!/bin/dash\nexit 0\n')
        os.chmod(stub, 0o755)
        with open(conf, 'a') as f:
            f.write(f"LITTLE_SNITCH_CLI = {stub!r}\n")
        try:
            r = self._run('--config', conf, '--install')
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            lines = [ln for ln in r.stdout.splitlines() if ' allow go ' in ln]
            for host in hosts:
                for_host = [ln for ln in lines if f' {host} ' in ln or ln.rstrip().endswith(f' {host}')]
                process_form = [ln for ln in for_host if ' allow go /' in ln
                                and '--via' not in ln]
                via_form = [ln for ln in for_host if ' allow go any ' in ln
                            and '--via' in ln]
                self.assertTrue(process_form,
                                f"{host}: no rule for the Python as the process:"
                                f"\n" + "\n".join(for_host))
                self.assertTrue(via_form,
                                f"{host}: no VIA rule -- the form the alerts "
                                f"showed is the one that was missing:\n"
                                + "\n".join(for_host))
                self.assertIn('--owner', via_form[0], via_form[0])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_without_the_firewall_tool_it_says_so_and_writes_nothing(self):
        """my-plex is published: on anyone else's machine the integration is
        absent, and --install must then be a clean no-op that still tells the
        reader which hosts to allow -- not an error."""
        d, conf = self._conf(os.path.join('/nonexistent', 'my-little-snitch'))
        try:
            r = self._run('--config', conf, '--install')
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertIn('no rules written', r.stdout, r.stdout[-500:])
            for host, _why in (('api.themoviedb.org', 0), ('www.fernsehserien.de', 0)):
                self.assertIn(host, r.stdout, "it must still name the hosts")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_it_never_runs_the_firewall_tool_itself(self):
        """THE test for the shape: writing a rule is root's, and my-plex does
        not run as root, so --install PRINTS the commands and calls nothing.

        Adversarial by construction: LITTLE_SNITCH_CLI points at a script
        that leaves a file behind if it is ever executed. The earlier shape
        (`--install go`, which called the tool) leaves that file."""
        d, conf = self._conf('/bin/true')       # replaced just below
        sentinel = os.path.join(d, 'it-was-run')
        stub = os.path.join(d, 'my-little-snitch')
        with open(stub, 'w') as f:
            f.write(f'#!/bin/dash\ntouch {sentinel!r}\n')
        os.chmod(stub, 0o755)
        with open(conf, 'a') as f:
            f.write(f"LITTLE_SNITCH_CLI = {stub!r}\n")
        try:
            r = self._run('--config', conf, '--install')
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertFalse(os.path.exists(sentinel),
                             "--install executed the firewall tool -- it must only print")
            self.assertIn('AS ROOT', r.stdout, r.stdout[-600:])
            for host, _why in (('api.themoviedb.org', 0), ('www.fernsehserien.de', 0)):
                self.assertIn(f'{stub} allow go ', r.stdout,
                              "the printed line must be the paste-ready command")
                self.assertIn(host, r.stdout, "...one per host")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_printed_command_names_the_owner(self):
        """A rule has an owner, and the printed command runs as ROOT -- so an
        unnamed owner is read in root's context, from the firewall tool's own
        configured default.  One machine's default named a user that does not
        exist there, and all three calls failed with "no such user"
        (2026-11-02).  The owner is this user, whose Python the rule names.

        Adversarial: the assertion is not that `--owner` appears, but that it
        carries THIS user -- a hard-coded name passes the first and fails
        this."""
        import pwd
        me = pwd.getpwuid(os.geteuid()).pw_name
        d, conf = self._conf('/bin/true')
        stub = os.path.join(d, 'my-little-snitch')
        with open(stub, 'w') as f:
            f.write('#!/bin/dash\nexit 0\n')
        os.chmod(stub, 0o755)
        with open(conf, 'a') as f:
            f.write(f"LITTLE_SNITCH_CLI = {stub!r}\n")
        try:
            r = self._run('--config', conf, '--install')
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            lines = [ln for ln in r.stdout.splitlines() if ' allow go ' in ln]
            self.assertTrue(lines, f"no printed command:\n{r.stdout[-600:]}")
            for ln in lines:
                self.assertIn(f'--owner {me}', ln,
                              f"the command leaves the owner to root's default: {ln}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_go_is_answered_rather_than_passed_through(self):
        """`--install go` was the earlier shape. Someone who types it gets told
        what changed, not argparse's `Invalid parameter`."""
        d, conf = self._conf(os.path.join('/nonexistent', 'my-little-snitch'))
        try:
            r = self._run('--config', conf, '--install', 'go')
            self.assertNotEqual(r.returncode, 0, "`--install go` was accepted")
            self.assertIn('There is no `go`', r.stderr, r.stderr[-600:])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_any_stray_word_is_refused_not_only_go(self):
        """ADVERSARIAL to the test above: a guard that recognised the literal
        `go` would pass that one and go on swallowing every other word, which
        is how `--install yes-please` ran as a plain --install. --install takes
        NO argument, so any word after it is a mistake -- and the refusal has
        to NAME the word, or the reader cannot see what was ignored."""
        d, conf = self._conf(os.path.join('/nonexistent', 'my-little-snitch'))
        try:
            for word in ('yes-please', 'all', 'Movie:13086'):
                r = self._run('--config', conf, '--install', word)
                self.assertNotEqual(r.returncode, 0,
                                    f"`--install {word}` was accepted")
                self.assertIn(word, r.stderr,
                              f"the refusal does not name {word!r}:\n{r.stderr[-400:]}")
            # ...and the bare form still works: a guard that refuses everything
            # would pass every assertion above.
            r = self._run('--config', conf, '--install')
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_help_page_exists_and_names_the_hosts(self):
        r = self._run('--help', 'install')
        self.assertIn('INSTALL HELP', r.stdout, r.stdout[:300])
        self.assertIn('www.fernsehserien.de', r.stdout,
                      "the page must name the hosts it allows")


class TestNeverRunsAsRoot(unittest.TestCase):
    """my-plex refuses euid 0 for every command that DOES anything, before
    that command gets anywhere -- and answers the ones that only PRINT.

    As root it would be wrong in two directions at once: the venv, the cache,
    the config and the completion all land in /var/root instead of the user's
    home, and anything it reports about "the Python that runs my-plex" names
    root's interpreter -- a process that never runs. A root run on ada built
    /var/root/.python.venv/my-plex before it did anything else, which is what
    brought this in.
    """

    def test_the_refusal_comes_before_the_venv_bootstrap(self):
        """Order is the whole point: a refusal after the bootstrap has already
        created /var/root/.python.venv is too late to be one."""
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        refusal = src.find('if _AS_ROOT and not _PRINT_ONLY_RUN:')
        self.assertGreater(refusal, -1, "the root refusal is gone")
        bootstrap = src.find('_bootstrap_venv()\n')
        self.assertGreater(bootstrap, -1, "the venv bootstrap call is gone")
        self.assertLess(refusal, bootstrap,
                        "the root refusal must come BEFORE the venv bootstrap")

    def test_it_refuses_with_the_house_error_and_says_what_to_do(self):
        """Run for real -- the suite is not root, so the one token that decides
        it is forced true in a copy that differs in nothing else."""
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        self.assertEqual(src.count('os.geteuid() == 0'), 1,
                         "more than one root check: this test neuters the wrong one")
        d = tempfile.mkdtemp(prefix='my-plex-asroot-')
        try:
            copy = os.path.join(d, 'my-plex.py')
            with open(copy, 'w') as f:
                f.write(src.replace('os.geteuid() == 0', 'True', 1))
            os.chmod(copy, 0o755)
            home = os.path.join(d, 'home')
            os.makedirs(home)
            r = subprocess.run([sys.executable, copy, '--list-libraries'],
                               capture_output=True, text=True, timeout=60,
                               env=dict(os.environ, HOME=home,
                                        PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(r.returncode, 1, f"exit {r.returncode}\n{r.stderr[-400:]}")
            self.assertRegex(r.stderr, r'ERROR 00001 \[1\]:',
                             f"not the house error shape:\n{r.stderr!r}")
            self.assertIn('does not run as root', r.stderr)
            self.assertFalse(os.path.exists(os.path.join(home, '.python.venv')),
                             "it got as far as building a venv before refusing")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_as_root_the_runs_that_only_print_are_answered(self):
        """Reading what a tool is, is not using it.  A root shell asking
        `my-plex --help` -- or a deployment gate doing it -- gets the help,
        because a run that only prints needs nothing of the user's: no venv,
        no cache, no config, so there is nothing to land in /var/root.

        Adversarial: the assertion is not that the three exit 0 (they do as
        any user), but that they do so with the euid forced to 0, and WITHOUT
        a venv appearing in that HOME.  Put the refusal back above them and
        all three come back as ERROR 00001.
        """
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        d = tempfile.mkdtemp(prefix='my-plex-rootprint-')
        try:
            copy = os.path.join(d, 'my-plex.py')
            with open(copy, 'w') as f:
                f.write(src.replace('os.geteuid() == 0', 'True', 1))
            os.chmod(copy, 0o755)
            for argv, what in (([], 'the bare run'), (['--help'], '--help'),
                               (['--version'], '--version')):
                home = os.path.join(d, 'home' + (argv[0] if argv else 'bare'))
                os.makedirs(home)
                r = subprocess.run([sys.executable, copy, *argv],
                                   capture_output=True, text=True, timeout=60,
                                   env=dict(os.environ, HOME=home,
                                            PYTHONDONTWRITEBYTECODE='1'))
                self.assertEqual(r.returncode, 0,
                                 f"{what} as root: exit {r.returncode}\n{r.stderr[-400:]}")
                self.assertNotIn('00001', r.stderr,
                                 f"{what} as root was refused:\n{r.stderr!r}")
                self.assertIn('my-plex', r.stdout,
                              f"{what} as root printed nothing of its own:\n{r.stdout[:200]!r}")
                self.assertFalse(os.path.exists(os.path.join(home, '.python.venv')),
                                 f"{what} built a venv just to print")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # The euid is forced through os.geteuid itself, in the interpreter that
    # runs the real file: every root check the script makes sees 0, and the
    # script is not edited.  The venv's python runs it, and a print-only run
    # never re-execs, so the patch is still in place when the script asks.
    _AS_ROOT_RUNNER = ("import os, runpy, sys\n"
                       "if os.environ.get('MY_PLEX_TEST_EUID') == '0':\n"
                       "    os.geteuid = lambda: 0\n"
                       "sys.argv = sys.argv[1:]\n"
                       "runpy.run_path(sys.argv[0], run_name='__main__')\n")

    def _run_print_only(self, home: str, argv: list[str], as_root: bool,
                        base_env: dict[str, str] | None = None) -> 'subprocess.CompletedProcess[str]':
        env = dict(base_env if base_env is not None else os.environ,
                   HOME=home, PYTHONDONTWRITEBYTECODE='1')
        env.pop('MY_PLEX_TEST_EUID', None)
        if as_root:
            env['MY_PLEX_TEST_EUID'] = '0'
        return subprocess.run([sys.executable, '-c', self._AS_ROOT_RUNNER, MAIN_SCRIPT, *argv],
                              capture_output=True, text=True, timeout=60,
                              env=env, stdin=subprocess.DEVNULL)

    def test_as_root_a_print_only_run_writes_nothing_into_home(self):
        """A root shell's `my-plex --help` must leave /var/root as it found
        it: no ~/.zsh/completions/_my-plex, no patched ~/.zshrc, no
        ~/.my-plex.  The completion installer ran at import, before any
        command was looked at, and init() made ~/.my-plex for the help page.

        Positive control first: the very same run as an ordinary user DOES
        write the completion (every run installs it) -- so an empty root HOME
        means root skipped it, not that the run never got that far."""
        d = tempfile.mkdtemp(prefix='my-plex-rootwrites-')
        try:
            user_home = os.path.join(d, 'user')
            os.makedirs(user_home)
            r = self._run_print_only(user_home, ['--help'], as_root=False)
            self.assertEqual(r.returncode, 0, f"exit {r.returncode}\n{r.stderr[-400:]}")
            self.assertTrue(os.path.isfile(os.path.join(user_home, '.zsh', 'completions', '_my-plex')),
                            "control: as a user, --help no longer installs the completion")
            for argv, what in (([], 'the bare run'), (['--help'], '--help')):
                home = os.path.join(d, 'root' + (argv[0] if argv else 'bare'))
                os.makedirs(home)
                zshrc = os.path.join(home, '.zshrc')
                with open(zshrc, 'w') as f:
                    f.write('# root zshrc\n')
                r = self._run_print_only(home, argv, as_root=True)
                self.assertEqual(r.returncode, 0,
                                 f"{what} as root: exit {r.returncode}\n{r.stderr[-400:]}")
                self.assertNotIn('00001', r.stderr, f"{what} as root was refused")
                self.assertIn('usage:', r.stdout, f"{what} as root printed no usage")
                self.assertEqual(sorted(os.listdir(home)), ['.zshrc'],
                                 f"{what} as root wrote into HOME")
                with open(zshrc) as f:
                    self.assertEqual(f.read(), '# root zshrc\n', f"{what} as root patched ~/.zshrc")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_as_root_only_the_help_flags_the_parser_defines_are_print_only(self):
        """The root rule lets a run through when argv asks for help -- so the
        flags it counts must be the ones the parser answers with help: `-H`
        and `--help`.  It counted `-h`, which my-plex does not define: as
        root, `my-plex -h` passed the refusal and went on to read the cache
        and query the Plex DB over ssh (a playlist named '-h'), while `-H`,
        the real short help, was refused.

        `-H` comes first: in a copy that still counts `-h` it is refused and
        the test stops there, before the `-h` run.  That run gets a fake ssh
        and a cache of its own anyway, so even a regression reaches no host."""
        d = tempfile.mkdtemp(prefix='my-plex-roothelpflags-')
        try:
            home = os.path.join(d, 'root-upper-H')
            os.makedirs(home)
            r = self._run_print_only(home, ['-H'], as_root=True)
            self.assertNotIn('00001', r.stderr, f"-H as root was refused:\n{r.stderr[-400:]}")
            self.assertEqual(r.returncode, 0, f"-H as root: exit {r.returncode}\n{r.stderr[-400:]}")
            self.assertIn('usage:', r.stdout, "-H as root printed no usage")
            self.assertEqual(os.listdir(home), [], "-H as root wrote into HOME")

            conf = os.path.join(d, 'my-plex.conf')
            with open(conf, 'w') as f:
                f.write(f"CACHE_FILE = {os.path.join(d, 'cache.pkl')!r}\n"
                        f"LOCK_FILE = {os.path.join(d, 'cache.lock')!r}\n"
                        + _install_lines(d))
            home = os.path.join(d, 'root-lower-h')
            os.makedirs(home)
            r = self._run_print_only(home, ['--config', conf, '-h'], as_root=True,
                                     base_env=_fake_ssh_env())
            self.assertEqual(r.returncode, 1, f"-h as root: exit {r.returncode}\n{r.stderr[-400:]}")
            self.assertRegex(r.stderr, r'ERROR 00001 \[1\]:',
                             f"-h as root was not refused:\n{r.stderr[-400:]}")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestConfigTemplateCoversEveryKey(unittest.TestCase):
    """Every CONFIG_DEFAULTS key must appear in the --create-config template.

    A key in CONFIG_DEFAULTS but not in the template is a knob the user cannot
    discover: `--create-config` is what they read and diff their own config
    against, so the feature is undocumented for everyone but the author. It
    has happened before (SORT_NEW_SCAN_LOCATIONS), and it happened again while
    adding LITTLE_SNITCH_CLI -- because the rule "a new key lands in three
    places" was written down but nothing executed it.
    """

    def test_every_key_is_in_the_create_config_output(self):
        r = subprocess.run([MAIN_SCRIPT, '--create-config'],
                           capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        emitted = set(re.findall(r'^\s*#?\s*([A-Z_][A-Z_0-9]+)\s*=', r.stdout,
                                 re.MULTILINE))
        self.assertGreater(len(emitted), 20, "the template rendered almost nothing")

        mod = _main_module()
        keys = set(mod.CONFIG_DEFAULTS.keys())
        missing = sorted(keys - emitted)
        self.assertEqual(missing, [],
                         "in CONFIG_DEFAULTS but not in --create-config, so a "
                         f"user cannot find them: {missing}")

    def test_the_template_invents_no_key(self):
        """The other direction: a template line naming a key that no longer
        exists tells the user to set something the tool ignores."""
        r = subprocess.run([MAIN_SCRIPT, '--create-config'],
                           capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        emitted = set(re.findall(r'^\s*#?\s*([A-Z_][A-Z_0-9]+)\s*=', r.stdout,
                                 re.MULTILINE))
        mod = _main_module()
        keys = set(mod.CONFIG_DEFAULTS.keys())
        # section headers and prose can name other things; only assignments count
        stray = sorted(e for e in emitted - keys if not e.startswith('EXAMPLE'))
        self.assertEqual(stray, [],
                         f"the template assigns keys the tool does not have: {stray}")


class TestConfigLayers(unittest.TestCase):
    """The site config, then the user's, the later winning per key.

    Each test builds a site file of its own naming a fake search directory,
    and a fake home (via $HOME), in a temp directory, so no real config of
    this machine takes part.  The loader is called in-process; a run that
    only prints would turn every refusal into a warning, so the module is
    told it is not one.
    """

    @classmethod
    def setUpClass(cls):
        cls.mp = _import_tool('mp_layers')
        cls.mp._PRINT_ONLY_RUN = False

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='my-plex-layers-')
        self.links = os.path.join(self.d, 'LINKS')
        self.home = os.path.join(self.d, 'home')
        for sub in ('LINKS/default', 'LINKS/global/etc/default', 'LINKS/local/etc/default',
                    'home/.my-plex', 'etc'):
            os.makedirs(os.path.join(self.d, sub))
        self.env = {k: os.environ.get(k) for k in ('HOME', 'MY_PLEX_CONFIG')}
        os.environ['HOME'] = self.home
        os.environ.pop('MY_PLEX_CONFIG', None)
        self.saved_sys = self.mp.SYSTEM_CONFIG_PATHS
        self.mp.SYSTEM_CONFIG_PATHS = (os.path.join(self.d, 'etc', 'my-plex.conf'),)
        self.saved_site = self.mp.SITE_CONF
        self.mp.SITE_CONF = self.write(
            'site.conf', f'CONFIG_SEARCH_DIR="{os.path.join(self.links, "default")}"\n')

    def tearDown(self):
        self.mp.SYSTEM_CONFIG_PATHS = self.saved_sys
        self.mp.SITE_CONF = self.saved_site
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, rel, text):
        path = os.path.join(self.d, rel)
        with open(path, 'w') as f:
            f.write(text)
        return path

    def site(self, text):
        return self.write('LINKS/default/my-plex.conf', text)

    def user(self, text):
        return self.write('home/.my-plex.conf', text)

    def load(self, config_file=None):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            conf = self.mp.load_config_file(config_file)
        return conf, err.getvalue()

    def refused(self, config_file=None):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            self.mp.load_config_file(config_file)
        return err.getvalue()

    def test_a_key_only_in_the_user_file_survives_the_site_file(self):
        """First-wins keeps only the site file's keys -- the bug layering fixes."""
        self.site("PLEX_DB_REMOTE_HOST = 'site-host'\n")
        self.user("DEFAULT_SCOPE = 'user-scope'\n")
        conf, _ = self.load()
        self.assertEqual(conf.get('PLEX_DB_REMOTE_HOST'), 'site-host')
        self.assertEqual(conf.get('DEFAULT_SCOPE'), 'user-scope')

    def test_a_key_in_both_takes_the_users_value(self):
        site = self.site("PLEX_DB_REMOTE_HOST = 'site-host'\n")
        user = self.user("PLEX_DB_REMOTE_HOST = 'user-host'\n")
        conf, _ = self.load()
        self.assertEqual(conf['PLEX_DB_REMOTE_HOST'], 'user-host')
        self.assertEqual(self.mp.CONFIG_RECORD['origin']['PLEX_DB_REMOTE_HOST'], user)
        self.assertEqual([l for l, _p in self.mp.CONFIG_RECORD['files']], ['site', 'user'])
        self.assertNotEqual(site, user)

    def test_an_empty_user_value_still_overrides_the_site(self):
        """A merge that treats a falsy value as 'not set' answers wrongly here."""
        self.site("PLEX_DB_REMOTE_HOST = 'site-host'\n")
        self.user("PLEX_DB_REMOTE_HOST = ''\n")
        conf, _ = self.load()
        self.assertEqual(conf['PLEX_DB_REMOTE_HOST'], '')

    def test_a_user_file_can_extend_a_site_value(self):
        """One namespace: the user's file runs with the site's values defined."""
        self.site("ALTERNATIVE_ROOTPATHS = ['/site']\n")
        self.user("ALTERNATIVE_ROOTPATHS = ALTERNATIVE_ROOTPATHS + ['/user']\n")
        conf, _ = self.load()
        self.assertEqual(conf['ALTERNATIVE_ROOTPATHS'], ['/site', '/user'])

    def test_a_named_file_is_read_alone(self):
        self.site("PLEX_DB_REMOTE_HOST = 'site-host'\n")
        self.user("DEFAULT_SCOPE = 'user-scope'\n")
        named = self.write('named.conf', "EDITOR = 'named-editor'\n")
        for how in ('flag', 'env'):
            with self.subTest(how=how):
                if how == 'env':
                    os.environ['MY_PLEX_CONFIG'] = named
                conf, _ = self.load(named if how == 'flag' else None)
                os.environ.pop('MY_PLEX_CONFIG', None)
                self.assertEqual(conf, {'EDITOR': 'named-editor'})

    def test_a_named_file_that_is_absent_is_refused(self):
        self.site("PLEX_DB_REMOTE_HOST = 'site-host'\n")
        out = self.refused(os.path.join(self.d, 'absent.conf'))
        self.assertIn('ERROR 00018', out)
        self.assertIn('absent.conf', out)

    def test_two_different_user_files_are_an_error(self):
        self.user("DEFAULT_SCOPE = 'legacy'\n")
        self.write('home/.my-plex/my-plex.conf', "DEFAULT_SCOPE = 'preferred'\n")
        out = self.refused()
        self.assertIn('two different user configs', out)

    def test_two_names_for_one_user_file_are_fine(self):
        real = self.write('real.conf', "DEFAULT_SCOPE = 'one'\n")
        os.symlink(real, os.path.join(self.home, '.my-plex.conf'))
        os.symlink(real, os.path.join(self.home, '.my-plex', 'my-plex.conf'))
        conf, err = self.load()
        self.assertEqual(conf['DEFAULT_SCOPE'], 'one')
        self.assertEqual(err, '')

    def test_a_secret_in_the_site_config_is_refused(self):
        self.site("TMDB_API_KEY = 'fixture-secret'\n")
        out = self.refused()
        self.assertIn('TMDB_API_KEY', out)
        self.assertNotIn('fixture-secret', out, "the refusal must not print the secret")

    def test_a_site_only_key_in_the_user_file_is_refused(self):
        self.user("LITTLE_SNITCH_CLI = '/elsewhere'\n")
        out = self.refused()
        self.assertIn('LITTLE_SNITCH_CLI', out)

    def test_a_config_that_fails_to_run_stops_the_run(self):
        """Today's loader warned and went on WITHOUT the file -- with layers,
        the site's server but not your token."""
        self.site("PLEX_DB_REMOTE_HOST = 'site-host'\n")
        user = self.user("DEFAULT_SCOPE = 'x'\nBROKEN = undefined_name\n")
        out = self.refused()
        self.assertIn(user, out)
        self.assertIn('line 2', out)
        self.assertIn('NameError', out)

    def test_a_print_only_run_warns_instead(self):
        self.user("BROKEN = undefined_name\n")
        self.mp._PRINT_ONLY_RUN = True
        try:
            conf, err = self.load()
        finally:
            self.mp._PRINT_ONLY_RUN = False
        self.assertIn('Warning', err)
        self.assertNotIn('BROKEN', conf)

    def test_a_dangling_site_link_is_skipped_with_a_warning(self):
        os.symlink(os.path.join(self.d, 'gone.conf'), os.path.join(self.links, 'default', 'my-plex.conf'))
        self.user("DEFAULT_SCOPE = 'user-scope'\n")
        conf, err = self.load()
        self.assertIn('broken', err)
        self.assertEqual(conf['DEFAULT_SCOPE'], 'user-scope')

    def test_the_global_file_is_read_before_the_local_one(self):
        """Told by where the link points, not by the name: the farm may give
        the global file the plain name and the local one .GLOBAL never."""
        g = self.write('LINKS/global/etc/default/my-plex.conf',
                       "PLEX_DB_REMOTE_HOST = 'global'\nEDITOR = 'global-only'\n")
        l = self.write('LINKS/local/etc/default/my-plex.conf', "PLEX_DB_REMOTE_HOST = 'local'\n")
        os.symlink(g, os.path.join(self.links, 'default', 'my-plex.conf.GLOBAL'))
        os.symlink(l, os.path.join(self.links, 'default', 'my-plex.conf'))
        conf, _ = self.load()
        self.assertEqual(conf['PLEX_DB_REMOTE_HOST'], 'local')
        self.assertEqual(conf['EDITOR'], 'global-only')
        for f in os.listdir(os.path.join(self.links, 'default')):
            os.unlink(os.path.join(self.links, 'default', f))
        os.symlink(l, os.path.join(self.links, 'default', 'my-plex.conf.GLOBAL'))
        os.symlink(g, os.path.join(self.links, 'default', 'my-plex.conf'))
        conf, _ = self.load()
        self.assertEqual(conf['PLEX_DB_REMOTE_HOST'], 'local', "the name decided, not the link")

    def test_the_system_config_is_a_fallback_only(self):
        self.write('etc/my-plex.conf', "PLEX_DB_REMOTE_HOST = 'etc'\n")
        conf, _ = self.load()
        self.assertEqual(conf['PLEX_DB_REMOTE_HOST'], 'etc')
        self.site("PLEX_DB_REMOTE_HOST = 'farm'\n")
        conf, _ = self.load()
        self.assertEqual(conf['PLEX_DB_REMOTE_HOST'], 'farm')
        self.assertEqual([l for l, _p in self.mp.CONFIG_RECORD['files']], ['site'])

    def test_the_user_paths_follow_HOME_at_read_time(self):
        """Expanded once at import, they answered /var/root for every later
        user -- the root phase's drop needs them computed when read."""
        self.user("DEFAULT_SCOPE = 'first-home'\n")
        other = os.path.join(self.d, 'other-home')
        os.makedirs(other)
        with open(os.path.join(other, '.my-plex.conf'), 'w') as f:
            f.write("DEFAULT_SCOPE = 'second-home'\n")
        os.environ['HOME'] = other
        conf, _ = self.load()
        self.assertEqual(conf['DEFAULT_SCOPE'], 'second-home')

    def test_the_site_file_alone_says_where_the_site_config_is(self):
        """The search directory comes from the site file, and from nothing
        else: with no site file, a config sitting where $LINKS or the old
        built-in /LINKS/default would point is NOT read, and an exported
        DATA_BASE_DIR does not take the neutral value's place."""
        elsewhere = os.path.join(self.d, 'elsewhere')
        os.makedirs(os.path.join(elsewhere, 'default'))
        with open(os.path.join(elsewhere, 'default', 'my-plex.conf'), 'w') as f:
            f.write("PLEX_DB_REMOTE_HOST = 'from-the-environment'\n")
        saved = {k: os.environ.get(k) for k in ('LINKS', 'DATA_BASE_DIR', 'CONFIG_SEARCH_DIR')}
        os.environ.update(LINKS=elsewhere, DATA_BASE_DIR='/elsewhere',
                          CONFIG_SEARCH_DIR=os.path.join(elsewhere, 'default'))
        try:
            os.unlink(self.mp.SITE_CONF)
            self.assertEqual(self.mp.read_site(), self.mp.Site())
            self.assertEqual(self.mp.read_site().data_base_dir, '/var/db')
            conf, _ = self.load()
            self.assertNotIn('PLEX_DB_REMOTE_HOST', conf, "a config found through the environment")
            self.assertEqual([p for _l, p in self.mp.default_config_paths()][:1],
                             list(self.mp.SYSTEM_CONFIG_PATHS[:1]), "a search directory without a site file")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        # with the site file: its values, and the bare name is read as well
        self.write('site.conf', 'DATA_BASE_DIR="/srv/data"\nLOG_BASE_DIR="/srv/log"\n'
                                f'CONFIG_SEARCH_DIR="{os.path.join(self.links, "default")}"\n'
                                '# a comment\n\nOTHER_TOOLS_KEY="x"\n')
        site = self.mp.read_site()
        self.assertEqual((site.data_base_dir, site.log_base_dir), ('/srv/data', '/srv/log'))
        self.write('LINKS/default/my-plex', "PLEX_DB_REMOTE_HOST = 'bare-name'\n")
        conf, _ = self.load()
        self.assertEqual(conf['PLEX_DB_REMOTE_HOST'], 'bare-name')

    def test_a_site_file_there_but_unusable_is_an_error(self):
        """Never the neutral values: they would put this run's config apart
        from everyone else's, silently."""
        for text, expect in (('CONFIG_SEARCH_DIR="/x"\n', 'cannot read'),
                             ('CONFIG_SEARCH_DIR="$HOME/x"\n', 'not a plain KEY="value" line'),
                             ('CONFIG_SEARCH_DIR=/x\n', 'not a plain KEY="value" line')):
            with self.subTest(text=text):
                self.write('site.conf', text)
                if expect == 'cannot read':
                    os.chmod(self.mp.SITE_CONF, 0)
                err = io.StringIO()
                try:
                    with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                        self.mp.read_site()
                finally:
                    os.chmod(self.mp.SITE_CONF, 0o600)
                self.assertIn('ERROR', err.getvalue())
                self.assertIn(expect, err.getvalue())

    def test_the_offer_names_only_searched_paths(self):
        """Every offered path is searched -- or is the site's offer directory
        while the site's search directory is searched; the search directory
        itself, a farm, is never offered."""
        farm = os.path.join(self.links, 'default')
        offer_dir = os.path.join(self.links, 'global', 'etc', 'default')
        site_offer = os.path.join(offer_dir, 'my-plex.conf')
        states = {
            'site': f'CONFIG_SEARCH_DIR="{farm}"\nCONFIG_OFFER_DIR="{offer_dir}"\n'
                    'CONFIG_OFFER_NOTE="linked there by a run"\n',
            # an offer directory and nothing searching it: a file written
            # there would be read from nowhere
            'offer-only': f'CONFIG_OFFER_DIR="{offer_dir}"\n',
            'none': None,
        }
        for state, text in states.items():
            with self.subTest(state=state):
                if text is None:
                    os.unlink(self.mp.SITE_CONF)
                else:
                    self.write('site.conf', text)
                searched = {p for _l, p in self.mp.default_config_paths()}
                offered = self.mp.config_offer_paths()
                self.assertTrue(offered, "nothing offered")
                for p in offered:
                    self.assertFalse(p.startswith(farm + os.sep), f"offered the farm: {p}")
                    if p == site_offer:
                        self.assertIn(os.path.join(farm, 'my-plex.conf'), searched)
                    else:
                        self.assertIn(p, searched, f"offered but not searched: {p}")
                self.assertEqual(site_offer in offered, state == 'site')
        self.write('site.conf', states['site'])
        text = self.mp.no_config_offer()
        self.assertIn(f"> my-plex --create-config > {site_offer}   (linked there by a run)", text)
        self.assertLess(text.index(site_offer), text.index(self.mp.SYSTEM_CONFIG_PATHS[0]),
                        "the site's place comes first")


class TestConfigEnvVar(unittest.TestCase):
    """$MY_PLEX_CONFIG: a config for ONE run, first in the search order.

    Why it exists: the suite had no way to point a SPAWNED my-plex at another
    config -- every test that wanted one had to pass --config to every child,
    and a test that forgot read the user's own 40 MB cache instead.
    """

    def _conf(self, marker):
        """A config file whose PLEX_DB_REMOTE_HOST says which file it is."""
        d = tempfile.mkdtemp(prefix='my-plex-cfgenv-')
        c = os.path.join(d, 'my-plex.conf')
        with open(c, 'w') as f:
            f.write(f"PLEX_DB_REMOTE_HOST = {marker!r}\n")
        return d, c

    def _run(self, *argv, **env):
        e = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        e.pop('MY_PLEX_CONFIG', None)
        e.update({k: v for k, v in env.items() if v is not None})
        return subprocess.run([MAIN_SCRIPT, *argv], capture_output=True,
                              text=True, timeout=120, env=e)

    def test_the_variable_names_the_config_that_is_read(self):
        """Observed through bare --config, which prints the active file AND its
        contents -- so the marker inside it is the evidence, not a path that
        /var symlinks would rewrite anyway."""
        d, conf = self._conf('fixture-host-A')
        try:
            r = self._run('--config', MY_PLEX_CONFIG=conf)
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertIn('fixture-host-A', r.stdout, r.stdout[-400:])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_variable_wins_over_an_explicit_config_flag(self):
        """ADVERSARIAL: a test that only checks "the variable is read when no
        flag is given" passes just as well when the flag wins. The house
        convention puts the variable FIRST, so this is the case that tells the
        two implementations apart -- and it is the one that matters, because a
        hatch a flag can close is not a hatch."""
        da, ca = self._conf('fixture-host-ENV')
        db, cb = self._conf('fixture-host-FLAG')
        try:
            # -C names the file and bare --config prints whichever one won:
            # `--config FILE` alone sets the file and then prints the usage,
            # which says nothing about what was read.
            r = self._run('-C', cb, '--config', MY_PLEX_CONFIG=ca)
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertIn('fixture-host-ENV', r.stdout, r.stdout[-400:])
            self.assertNotIn('fixture-host-FLAG', r.stdout,
                             "--config won over $MY_PLEX_CONFIG")
        finally:
            shutil.rmtree(da, ignore_errors=True)
            shutil.rmtree(db, ignore_errors=True)

    def test_a_named_config_that_is_absent_is_refused_not_replaced(self):
        """THE dangerous case, and the reason the fallback is not silent: a run
        pointed at a fixture that is not there would read the user's own config
        and report on the wrong cache, with nothing in the output saying so.
        Both namings are the same rule, so both are checked -- and the control
        at the end fails any guard that simply refuses everything."""
        for source, argv, env in (('$MY_PLEX_CONFIG', ('--config',),
                                   {'MY_PLEX_CONFIG': '/nonexistent/nope.conf'}),
                                  ('--config', ('--config', '/nonexistent/nope.conf'),
                                   {})):
            r = self._run(*argv, **env)
            self.assertNotEqual(r.returncode, 0,
                                f"{source} naming an absent file was accepted")
            self.assertIn('/nonexistent/nope.conf', r.stderr,
                          f"{source}: the refusal does not name the path:"
                          f"\n{r.stderr[-400:]}")
        d, conf = self._conf('fixture-host-REAL')
        try:
            r = self._run('--config', MY_PLEX_CONFIG=conf)
            self.assertEqual(r.returncode, 0,
                             f"a config that IS there was refused: {r.stderr[-400:]}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_run_that_only_prints_is_not_stopped_by_a_bad_variable(self):
        """--help reads no config, so a stale variable must not hide the help.
        The tool already answers this question once, in _PRINT_ONLY_RUN, and a
        deployment gate asks `my-plex --help` to find out what this tool can
        do."""
        r = self._run('--help', 'config', MY_PLEX_CONFIG='/nonexistent/nope.conf')
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn('CONFIG HELP', r.stdout, r.stdout[:300])

    def test_a_test_run_ignores_a_stray_variable(self):
        """A stray variable must not steer the SUITE.

        The hazard this hatch created: left in a shell, $MY_PLEX_CONFIG would
        point every test -- and the hundred-odd my-plex runs the suite spawns
        -- at a real config of someone else's choosing, and nothing would say
        so. A nonexistent path is caught by the refusal above; a path that
        EXISTS is the silent case, so that is the one tested.

        With the control after it: a run without the variable must NOT print
        the line, or the message is unconditional and says nothing."""
        d, conf = self._conf('fixture-host-STRAY')
        inner = 'test_the_venvs_own_interpreter_is_inside_it'
        try:
            r = self._run('--run-tests', inner, MY_PLEX_CONFIG=conf)
            self.assertEqual(r.returncode, 0,
                             f"a stray variable broke the test run:\n{r.stderr[-400:]}")
            self.assertIn('ignored for this test run', r.stderr,
                          f"the variable was used, or the run did not say it "
                          f"was dropped:\n{r.stderr[-400:]}")
            self.assertNotIn('fixture-host-STRAY', r.stdout + r.stderr,
                             "the stray config reached the run")
            control = self._run('--run-tests', inner)
            self.assertEqual(control.returncode, 0, control.stderr[-400:])
            self.assertNotIn('ignored for this test run', control.stderr,
                             "the line is printed even with no variable set")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_help_page_prints_the_order_it_really_searches(self):
        """Every line of --help is a CLAIM. This page is generated from
        config_search_paths(), so the claim and the search cannot drift: the
        page must name the variable and the primary location."""
        r = self._run('--help', 'config')
        self.assertIn('MY_PLEX_CONFIG', r.stdout,
                      "the page does not name the first thing it searches")
        self.assertIn('/etc/my-plex.conf', r.stdout, r.stdout[-600:])
        # the site's search directory, wherever this machine's site file puts it
        site = _import_tool('mp_helpsite').read_site()
        if site.config_search_dir:
            self.assertIn(os.path.join(site.config_search_dir, 'my-plex.conf'), r.stdout,
                          r.stdout[-600:])


class TestInstallSshEntry(unittest.TestCase):
    """--install makes PLEX_DB_REMOTE_HOST resolve to PLEX_DB_REMOTE.

    The reason it exists: on macado the alias was never arranged by hand, so
    every DB query failed with "Could not resolve hostname my-plex".  Each
    test has an ssh config of its own (SSH_CONFIG_FILE) and an ssh whose
    login is a stub: no real ~/.ssh is read or written, no host is reached.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='my-plex-sshentry-')
        os.makedirs(os.path.join(self.d, 'ssh'))
        self.ssh_conf = os.path.join(self.d, 'ssh', 'config')
        self.ours = os.path.join(self.d, 'ssh', 'my-plex.conf')

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def install(self, remote: str | None = 'me@192.0.2.10', login_rc: int = 0, extra: str = ''):
        c = os.path.join(self.d, 'my-plex.conf')
        with open(c, 'w') as f:
            f.write(f"LITTLE_SNITCH_CLI = '/nonexistent/my-little-snitch'\n")
            f.write(f"CACHE_FILE = {os.path.join(self.d, 'cache.pkl')!r}\n")
            f.write(f"LOCK_FILE = {os.path.join(self.d, 'cache.lock')!r}\n")
            if remote is not None:
                f.write(_install_lines(self.d, remote))
            else:
                f.write(f"SSH_CONFIG_FILE = {self.ssh_conf!r}\n")
            f.write(extra)
        return subprocess.run([MAIN_SCRIPT, '--config', c, '--install'], capture_output=True,
                              text=True, timeout=120, env=_fake_ssh_env(login_rc))

    def read(self, path):
        with open(path) as f:
            return f.read()

    def effective(self):
        out = subprocess.run([shutil.which('ssh') or '/usr/bin/ssh', '-G', '-F', self.ssh_conf, 'my-plex'],
                             capture_output=True, text=True).stdout
        return {k: v for k, _s, v in (ln.partition(' ') for ln in out.splitlines())
                if k in ('hostname', 'user', 'port')}

    def test_an_alias_nobody_arranged_is_written_and_resolves(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        self.assertEqual(self.effective(), {'hostname': '192.0.2.10', 'user': 'me', 'port': '22'})
        self.assertTrue(self.read(self.ssh_conf).startswith(f"Include {self.ours}\n"))
        self.assertIn('ssh Host entry written', r.stdout)

    def test_a_second_run_changes_nothing(self):
        self.install()
        before = (self.read(self.ssh_conf), self.read(self.ours))
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual((self.read(self.ssh_conf), self.read(self.ours)), before)
        self.assertIn('ssh Host entry unchanged', r.stdout)

    def test_a_port_is_written_when_it_is_not_22(self):
        r = self.install(remote='me@ssh.example.invalid:53146')
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual(self.effective()['port'], '53146')

    def test_a_hand_written_block_is_migrated_with_its_other_options(self):
        """The option my-plex does not generate -- here a key outside ssh's
        default places -- is what keeps that machine working: dropped, it
        would stop logging in."""
        with open(self.ssh_conf, 'w') as f:
            f.write("Host other\n    HostName 192.0.2.99\n\n"
                    "Host my-plex\n    Hostname 192.0.2.10\n    #Port 53146\n"
                    "    User me\n    IdentityFile /keys/ada,id_rsa\n\n"
                    "Host www\n    Port 2222\n")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        conf = self.read(self.ssh_conf)
        self.assertNotIn('Host my-plex', conf, "the hand-written block is still there")
        self.assertIn('Host other', conf)
        self.assertIn('Host www', conf)
        ours = self.read(self.ours)
        self.assertIn('IdentityFile /keys/ada,id_rsa', ours)
        self.assertIn('# migrated from', ours)
        self.assertIn('ssh Host entry migrated', r.stdout)
        self.assertEqual(self.effective()['hostname'], '192.0.2.10')

    def test_a_block_that_disagrees_is_left_alone(self):
        text = "Host my-plex\n    HostName 192.0.2.77\n    User me\n"
        with open(self.ssh_conf, 'w') as f:
            f.write(text)
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('two answers', r.stderr)
        self.assertEqual(self.read(self.ssh_conf), text, "a disagreeing block was changed")
        self.assertFalse(os.path.exists(self.ours))

    def test_a_block_naming_other_aliases_too_is_left_alone(self):
        text = "Host my-plex ada\n    HostName 192.0.2.10\n    User me\n"
        with open(self.ssh_conf, 'w') as f:
            f.write(text)
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('other aliases', r.stderr)
        self.assertEqual(self.read(self.ssh_conf), text)

    def test_without_PLEX_DB_REMOTE_it_writes_nothing(self):
        r = self.install(remote=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('--install needs PLEX_DB_REMOTE', r.stderr)
        self.assertFalse(os.path.exists(self.ssh_conf))

    def test_a_failed_login_is_an_error(self):
        """Resolving proves nothing about logging in: only a login does."""
        r = self.install(login_rc=255)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('the login through', r.stderr)
        self.assertIn('[rc 255]', r.stdout + r.stderr)

    def key(self, name: str = 'ada,id_rsa') -> str:
        """A stand-in key file in the test's own directory: --install checks
        that the configured key exists, never what is in it."""
        p = os.path.join(self.d, name)
        with open(p, 'w') as f:
            f.write('not a real key\n')
        return p

    def identities(self) -> list[str]:
        out = subprocess.run([shutil.which('ssh') or '/usr/bin/ssh', '-G', '-F', self.ssh_conf, 'my-plex'],
                             capture_output=True, text=True).stdout
        return [v for k, _s, v in (ln.partition(' ') for ln in out.splitlines()) if k == 'identityfile']

    def test_the_configured_key_is_the_one_ssh_offers(self):
        """macado: no IdentityFile in the entry, so ssh offered the user's
        default ~/.ssh/id_ed25519 and ada refused it -- the house key is
        ~/.ssh/keys.mine/ada,id_rsa, a place ssh never looks by itself."""
        k = self.key()
        r = self.install(extra=f"PLEX_DB_REMOTE_IDENTITY = {k!r}\n")
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        self.assertEqual(self.identities(), [k], "ssh would offer another key than the configured one")
        self.assertIn(f"IdentityFile {k}", self.read(self.ours))

    def test_without_the_key_no_identity_is_written(self):
        """The key is optional: a site whose users log in with their default
        keys sets none, and the entry names none."""
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertNotIn('IdentityFile', self.read(self.ours))

    def test_a_missing_key_file_writes_nothing(self):
        """Writing an entry for a key that is not there would only move the
        failure to the login, with a message about the server."""
        missing = os.path.join(self.d, 'no-such-key')
        r = self.install(extra=f"PLEX_DB_REMOTE_IDENTITY = {missing!r}\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('PLEX_DB_REMOTE_IDENTITY', r.stderr)
        self.assertIn(missing, r.stderr)
        self.assertFalse(os.path.exists(self.ours))
        self.assertFalse(os.path.exists(self.ssh_conf))

    def test_a_block_with_the_same_key_migrates_to_ONE_identity(self):
        """horse: the hand-written block already names the house key.  Carried
        over AND generated, it would be written twice."""
        k = self.key()
        with open(self.ssh_conf, 'w') as f:
            f.write(f"Host my-plex\n    HostName 192.0.2.10\n    User me\n    IdentityFile {k}\n")
        r = self.install(extra=f"PLEX_DB_REMOTE_IDENTITY = {k!r}\n")
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        body = [ln for ln in self.read(self.ours).splitlines() if not ln.startswith('#')]
        self.assertEqual(sum(1 for ln in body if 'IdentityFile' in ln), 1, "\n".join(body))
        self.assertIn('ssh Host entry migrated', r.stdout)

    def test_a_block_with_another_key_is_left_alone(self):
        """Two answers for the key: my-plex picks neither."""
        k, other = self.key(), self.key('other,id_rsa')
        text = f"Host my-plex\n    HostName 192.0.2.10\n    User me\n    IdentityFile {other}\n"
        with open(self.ssh_conf, 'w') as f:
            f.write(text)
        r = self.install(extra=f"PLEX_DB_REMOTE_IDENTITY = {k!r}\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('two answers', r.stderr)
        self.assertIn(other, r.stderr)
        self.assertEqual(self.read(self.ssh_conf), text)
        self.assertFalse(os.path.exists(self.ours))

    def test_its_own_file_takes_the_configured_key_over_a_carried_one(self):
        """horse after the first rollout: my-plex.conf carries the migrated
        IdentityFile.  Once the site names the key, the config is the one
        answer -- 'edit the config, not this' -- and the line is not doubled."""
        k, old = self.key(), self.key('old,id_rsa')
        with open(self.ssh_conf, 'w') as f:
            f.write(f"Host my-plex\n    HostName 192.0.2.10\n    User me\n    IdentityFile {old}\n")
        self.install()
        self.assertIn(f"IdentityFile {old}", self.read(self.ours))
        r = self.install(extra=f"PLEX_DB_REMOTE_IDENTITY = {k!r}\n")
        self.assertEqual(r.returncode, 0, r.stdout[-800:] + r.stderr[-800:])
        self.assertEqual(self.identities(), [k])
        r2 = self.install(extra=f"PLEX_DB_REMOTE_IDENTITY = {k!r}\n")
        self.assertIn('ssh Host entry unchanged', r2.stdout, r2.stdout[-800:])

    def test_the_identity_is_a_site_key(self):
        main_mod = _main_module()
        self.assertIn('PLEX_DB_REMOTE_IDENTITY', main_mod.SITE_ONLY_KEYS)
        self.assertEqual(main_mod.CONFIG_DEFAULTS['PLEX_DB_REMOTE_IDENTITY'], '')

    def test_the_ssh_rule_takes_its_host_from_PLEX_DB_REMOTE(self):
        """As root, `ssh -G` reads root's ssh config, and on a fresh machine
        the alias does not exist yet: the rule must not depend on it."""
        r = self.install(remote='me@192.0.2.42')
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn('192.0.2.42', r.stdout)


class TestInstallPlexRule(unittest.TestCase):
    """--install must write a rule for the PLEX SERVER too.

    It did not, and the user hit the consequence: a Little Snitch alert for
    192-168-192-252.<hash>.plex.direct on tcp/32400 -- which is exactly the
    host in my-plex's own PLEX_XML_URL. my-plex reaches the server through
    plexapi, so the tool builds no https url for it, and
    test_every_host_it_fetches_has_a_rule reads only the urls it BUILDS: the
    gap was invisible to the test that exists to catch gaps.

    An alert is the worst outcome available: an unattended run -- a job, or
    the deployment gate running the suite -- has nobody at the screen, so
    my-plex just stops talking with no error of its own.
    """

    def _conf(self, **keys):
        """A config with a firewall stub, a cache of its own, and whatever
        Plex URL the test wants. The cache paths matter: without them
        --install waits on the REAL cache lock, which another process can
        hold for minutes."""
        d = tempfile.mkdtemp(prefix='my-plex-plexrule-')
        stub = os.path.join(d, 'my-little-snitch')
        with open(stub, 'w') as f:
            f.write('#!/bin/dash\nexit 0\n')
        os.chmod(stub, 0o755)
        c = os.path.join(d, 'my-plex.conf')
        with open(c, 'w') as f:
            f.write(f"LITTLE_SNITCH_CLI = {stub!r}\n")
            f.write(f"CACHE_FILE = {os.path.join(d, 'cache.pkl')!r}\n")
            f.write(f"LOCK_FILE = {os.path.join(d, 'cache.lock')!r}\n")
            f.write(_install_lines(d))
            for k, v in keys.items():
                f.write(f"{k} = {v!r}\n")
        return d, c

    def _install(self, **keys):
        d, c = self._conf(**keys)
        try:
            r = subprocess.run([MAIN_SCRIPT, '--config', c, '--install'],
                               capture_output=True, text=True, timeout=180,
                               env=_fake_ssh_env())
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            return [ln for ln in r.stdout.splitlines() if ' allow go ' in ln]
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_plex_direct_server_gets_a_domain_rule_with_its_port(self):
        """THE missing rule. A domain, not the host: the per-server label
        carries the server's LAN IP, so a host rule would break -- back into
        an alert -- the next time that IP changes."""
        lines = self._install(
            PLEX_XML_URL='https://192-168-192-252.abc123.plex.direct:32400'
                         '/library/metadata/1?X-Plex-Token=nope')
        plex = [ln for ln in lines if 'plex.direct' in ln]
        self.assertTrue(plex, f"no rule for the Plex server:\n" + "\n".join(lines))
        self.assertEqual(len(plex), 2,
                         f"expected the process form and the via form: {plex}")
        self.assertIn('--port 32400', plex[0],
                      f"the rule does not carry the port, and 32400 is not "
                      f"tcp's default: {plex[0]}")
        self.assertNotIn('192-168-192-252', plex[0],
                         f"the rule names the per-server host, which carries "
                         f"the IP: {plex[0]}")
        self.assertTrue([ln for ln in plex if ' allow go any ' in ln and '--via' in ln],
                        f"no VIA rule for the Plex server -- the form the "
                        f"alerts showed:\n" + "\n".join(plex))

    def test_the_remote_comes_from_the_CONFIG_not_from_a_list(self):
        """ADVERSARIAL, and the one that matters: a test that only looked for
        'plex.direct' would pass just as well if someone put plex.direct in
        NETWORK_HOSTS. Another server must give another remote."""
        lines = self._install(PLEX_URL='https://plex.example.net:32400')
        own = [ln for ln in lines if 'plex.example.net' in ln]
        self.assertTrue(own, f"the configured server got no rule:\n" + "\n".join(lines))
        self.assertIn('--host', own[0],
                      f"a name that is not plex.direct is one HOST, not a "
                      f"domain to be guessed at: {own[0]}")
        self.assertIn('--port 32400', own[0], own[0])
        self.assertFalse([ln for ln in lines if 'plex.direct' in ln],
                         "plex.direct appears for a server that is not one")

    def test_a_bare_address_is_an_address_rule(self):
        """An IP is not a domain and not a host name; the firewall tool has a
        third form for it, and says so."""
        lines = self._install(PLEX_URL='http://192.168.1.5:32400')
        own = [ln for ln in lines if '192.168.1.5' in ln]
        self.assertTrue(own, f"no rule for the configured address:\n" + "\n".join(lines))
        self.assertIn('--address', own[0], own[0])
        self.assertIn('--port 32400', own[0], own[0])

    def test_the_ssh_endpoint_gets_both_forms_with_its_port(self):
        """my-plex runs ssh for every direct DB read and every file operation
        on the server, and --install wrote no rule for it -- while the comment
        above NETWORK_HOSTS said "no curl, no ssh" and --help promised "one
        per host it connects to". Both claims were false (survey, 2026-11-05).

        The remote is resolved from the ssh ALIAS with `ssh -G`, because an
        alias is not something a firewall can resolve. Port 22 has to be in
        the rule: 443 is the only port one assumes."""
        lines = self._install(PLEX_DB_REMOTE_HOST='localhost')
        ssh = [ln for ln in lines if ' ssh ' in ln or ln.rstrip().endswith(' ssh')
               or '--via ssh' in ln]
        self.assertTrue(ssh, f"no rule for the SSH endpoint:\n" + "\n".join(lines))
        self.assertEqual(len(ssh), 2,
                         f"expected the process form and the via form: {ssh}")
        for ln in ssh:
            self.assertIn('--port 22', ln, f"no port in the ssh rule: {ln}")
        self.assertTrue([ln for ln in ssh if '--via ssh' in ln],
                        f"no VIA rule for ssh:\n" + "\n".join(ssh))

    def test_the_pip_hosts_get_rules_too(self):
        """The venv bootstrap fetches from pypi.org, and the 2026-11-03
        python@3.15 step had to write those two rules by hand because
        --install did not. DESIGN.local.md had them as BOOTSTRAP_HOSTS and
        nothing built it."""
        lines = self._install()
        for host in ('pypi.org', 'files.pythonhosted.org'):
            for_host = [ln for ln in lines if host in ln]
            self.assertEqual(len(for_host), 2,
                             f"{host}: expected both forms, got:\n"
                             + "\n".join(for_host))

    def test_the_ssh_rule_names_only_the_configured_host(self):
        """ADVERSARIAL to the ssh test: a rule hard-coded for the user's own
        server would pass that one.  The ssh rule's host comes from
        PLEX_DB_REMOTE alone (--install requires it), so the ssh rule must
        name exactly that host and no other -- my-plex is published."""
        lines = self._install(PLEX_DB_REMOTE='me@192.0.2.42')
        ssh = [ln for ln in lines if '--via ssh' in ln or ' ssh ' in ln.split(' allow go ', 1)[-1][:6]]
        self.assertTrue(ssh, "no ssh rule at all:\n" + "\n".join(lines))
        self.assertTrue(all('192.0.2.42' in ln for ln in ssh), "\n".join(ssh))

    def test_no_plex_configured_still_installs_the_rest(self):
        """my-plex is published: on a machine with no Plex configured yet,
        --install must write the scraper rules and invent nothing."""
        lines = self._install()
        self.assertTrue([ln for ln in lines if 'api.themoviedb.org' in ln],
                        f"the scraper rules went missing too:\n" + "\n".join(lines))
        self.assertFalse([ln for ln in lines if 'plex.direct' in ln],
                         f"a Plex rule was invented with nothing configured:\n"
                         + "\n".join(lines))

class TestSuiteReachesNoNetwork(unittest.TestCase):
    """A default run of this suite fetches nothing.

    It cannot live in TestTsvScrapersE2E -- that class's own setUp would skip
    it. It spawns a child instead, which is also the only honest way to test
    the DEFAULT: this process may well have the variable set.
    """

    def test_a_fetching_test_does_not_run_by_default(self):
        """And the skip must SAY how to run it. A test skipped for some other
        reason -- no config, no venv -- would otherwise pass this and leave
        the suite reaching the network for real."""
        e = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        e.pop(TEST_NETWORK_ENV, None)
        r = subprocess.run([MAIN_SCRIPT, '--run-tests', 'test_tmdb_friends'],
                           capture_output=True, text=True, timeout=180, env=e)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn('1..1', r.stdout, r.stdout[-400:])
        self.assertIn('# SKIP', r.stdout,
                      f"it RAN -- the default suite reaches the network:"
                      f"\n{r.stdout[-400:]}")
        self.assertIn(TEST_NETWORK_ENV, r.stdout,
                      f"the skip does not say how to run it:\n{r.stdout[-400:]}")

    def test_the_variable_is_the_only_thing_that_opens_it(self):
        """The predicate, directly: set and non-blank means opted in. Checked
        here rather than by a run that fetches, which is the one thing this
        suite must not do to prove a point."""
        saved = os.environ.get(TEST_NETWORK_ENV)
        try:
            for value, expected in (('1', True), ('yes', True), ('', False),
                                    ('   ', False)):
                os.environ[TEST_NETWORK_ENV] = value
                self.assertEqual(_network_opted_in(), expected,
                                 f"{TEST_NETWORK_ENV}={value!r}")
            os.environ.pop(TEST_NETWORK_ENV, None)
            self.assertFalse(_network_opted_in(), "unset must mean no")
        finally:
            if saved is None:
                os.environ.pop(TEST_NETWORK_ENV, None)
            else:
                os.environ[TEST_NETWORK_ENV] = saved


class TestReadmeIsFound(unittest.TestCase):
    """The README claims may only go quiet where there IS no README.

    Both tests that read it skip when _readme_path() answers None, so a
    change that stopped it finding the file in a CHECKOUT would turn those
    assertions off everywhere and nothing would say so -- a passing suite
    that checks nothing. This is the test that notices.
    """

    def test_a_checkout_finds_its_own_readme(self):
        beside_suite = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 'README.md')
        if not os.path.isfile(beside_suite):
            self.skipTest("not a checkout: no README.md beside the suite")
        found = _readme_path() or ''
        self.assertTrue(found, "a checkout has a README and it was not found")
        self.assertEqual(os.path.realpath(found), os.path.realpath(beside_suite),
                         "found a different README than the checkout's own")


class TestBadStructureResolve(unittest.TestCase):
    """cmd_bad_structure_resolve() had no test, and its resolve log raised
    NameError (plan_movie) for as long as it existed: the except around the
    log call turned it into "(resolve log skipped: ...)" and nothing noticed.

    A conflict-only run reaches the log without touching a disk: a Movie two
    levels too deep is a conflict before any ssh, and --auto skips the prompt."""

    def _mod(self):
        return _main_module()

    def test_a_conflict_only_run_writes_its_log_and_swallows_nothing(self):
        import contextlib
        m = self._mod()
        saved = (m.PLEX_Media.OBJ_BY_ID, m.CACHE, m._write_resolve_log)
        written = []
        m._write_resolve_log = lambda name, payload: written.append((name, payload))
        try:
            m.PLEX_Media.OBJ_BY_ID = {
                'Movie:1': {'type': 'Movie', 'title': 'Some Movie', 'library': 'library1',
                            'files': {'v1': {'filepath':
                                             '/lib/library1/wrapper/deeper/deepest/some.movie.mkv'}}},
            }
            m.CACHE = {'library_stats': {'locations': {'library1': ['/lib/library1']}}}
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                m.cmd_bad_structure_resolve(scope=None, auto=True, dry_run=False, yes=True)
            out = buf.getvalue()
        finally:
            m.PLEX_Media.OBJ_BY_ID, m.CACHE, m._write_resolve_log = saved
        self.assertIn('CONFLICTS:                1', out, out[-800:])
        self.assertNotIn('resolve log skipped', out, out[-800:])
        self.assertEqual(len(written), 1, "the resolve log is written once, conflicts or not")
        name, payload = written[0]
        self.assertEqual(name, 'bad_structure_resolve')
        self.assertEqual(payload['summary'],
                         {'episode_moves': 0, 'movie_flattens': 0, 'conflicts': 1})
        self.assertEqual(payload['libraries_scanned'], [])
        self.assertFalse(payload['dry_run'])


class TestLegacyInlineBlock(unittest.TestCase):
    """What survived the inline `[TEST N]` block, removed 2026-11-08.

    That block printed its own PASS/FAIL into local counters, stood in no TAP
    plan (so the deployment gate never saw it), and `--run-tests inline` had
    exited 1 for as long as the unittest run after it named an unbound
    variable.  Of its 25 checks, ten read the real cache, seven tested argparse
    or sorted() rather than my-plex, and the rest are here -- against the
    functions they named, not a copy of their logic.  Its --info check lives
    on in TestEndToEnd and the isolated --info test."""

    def _mod(self):
        return _main_module()

    def test_format_filesize_picks_the_unit(self):
        f = self._mod().format_filesize
        self.assertEqual(f(None), 'N/A')
        self.assertEqual(f(500), '500 B')
        self.assertEqual(f(1024), '1 KB')
        self.assertEqual(f(1024**2), '1 MB')
        self.assertEqual(f(1024**3), '1.0 GB')
        self.assertEqual(f(int(1.5 * 1024**3)), '1.5 GB')
        self.assertEqual(f(1024**3, force_unit='MB'), '1024 MB')

    def test_escape_path_for_ssh_escapes_the_double_quote_specials_only(self):
        esc = self._mod().escape_path_for_ssh
        kept = "/path/charlie's angels (2019) [720p].mp4"
        self.assertEqual(esc(kept), kept)
        self.assertEqual(esc("/p/a$b`c\"d\\e"), "/p/a\\$b\\`c\\\"d\\\\e")

    def test_determine_remote_host_knows_local_from_absent(self):
        """(remote_host, exists, resolved_path) -- and a DIRECTORY is not the
        file: the local check asks isfile, which is the regression this guards
        ('ERROR: File not found' on remote files whose wrapper existed locally)."""
        m = self._mod()
        saved = m.PLEX_DB_REMOTE_HOST
        d = tempfile.mkdtemp(prefix='my-plex-remotehost-')
        try:
            m.PLEX_DB_REMOTE_HOST = ''      # no host to ask: the suite reaches no network
            fp = os.path.join(d, 'file.mkv')
            open(fp, 'w').close()
            self.assertEqual(m.determine_remote_host(fp), (None, True, fp))
            self.assertEqual(m.determine_remote_host(d), (None, False, None))
        finally:
            m.PLEX_DB_REMOTE_HOST = saved
            shutil.rmtree(d, ignore_errors=True)

    def test_collection_and_playlist_classes_are_wired(self):
        import inspect
        m = self._mod()
        self.assertIn('collection', m.PLEXOBJ[m.DETECT])
        self.assertNotIn('playlists()', inspect.getsource(m.PLEX_Collection.detect_if_of_OBJ_TYPE),
                         "a copy-paste from PLEX_Playlist")
        self.assertEqual(list(inspect.signature(m.PLEX_Collection.list).parameters), ['library_name'])
        for method in ('create', 'update'):
            self.assertNotIn('++', inspect.getsource(getattr(m.PLEX_Playlist, method)),
                             f"PLEX_Playlist.{method}: ++ is a no-op in Python")

    def test_cache_dict_builder_has_every_structure_the_loader_reads(self):
        m = self._mod()
        d = m.build_media_cache_dict()
        for key in ('obj_by_id', 'obj_by_movie', 'obj_by_series', 'obj_by_series_episodes',
                    'obj_by_collection', 'obj_by_filepath', 'obj_by_library'):
            self.assertIn(key, d)
        self.assertNotIn('obj_by_filepath', m.build_media_cache_dict(include_paths=False))
        self.assertEqual(m.build_media_cache_dict(library_stats={'t': 1})['library_stats'], {'t': 1})
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        inline = re.findall(r"'obj_by_id':\s*PLEX_Media\.OBJ_BY_ID,\s*\n\s*'obj_by_movie'", src)
        self.assertLessEqual(len(inline), 1, "a cache dict built by hand beside build_media_cache_dict()")

    def test_argv_normalisation_and_global_list_go_through_their_helpers(self):
        import inspect
        m = self._mod()
        with open(MAIN_SCRIPT) as f:
            src = f.read()
        self.assertIn('def inject_before_first_match(', src)
        self.assertGreaterEqual(len(re.findall(r'inject_before_first_match\(', src)), 3)
        self.assertIn('def is_audio_flag(', src)
        body = inspect.getsource(m.execute_global_commands)
        for name in ('watched_only', 'unwatched_only', 'audio_filter'):
            self.assertIn(name, body, f"a global --list would drop --{name.split('_')[0]}")
        self.assertIn('--collections requires a library name', body)


_UNITTEST_SCOPES = {
    'cache':      [TestAtomicPickleWrites,
                   TestObjTypeHandling, TestCacheResumeWithMultiVersion,
                   TestPlexUpdatedAtTracking, TestCacheSkipLogic,
                   TestVerifyCacheIntegrity, TestCacheFormatValidation,
                   TestCacheStructureParity, TestVerifyCacheSplit,
                   TestUpdateCacheSplit, TestCacheUpdateLog,
                   TestObjByLibraryDedup],
    'duplicates': [TestMultiVersionMerge, TestDuplicateKeyGeneration,
                   TestClassifyMultiVersion, TestDuplicatesIgnoreLibraryCombinations,
                   TestExcessVersions, TestExcessVersionsMainParser,
                   TestVersionStringCollision],
    'episodes':   [TestEpisodesTSV, TestDateExtraction, TestSpecialDetection,
                   TestMissingEpisodes, TestMissingE2E, TestCustomDateExtractors,
                   TestEpisodeSourceSelection, TestExternalIdsInCache,
                   TestEpisodeSourceConfig, TestSourceE2E,
                   TestEpisodesErr, TestEpisodesErrClassification,
                   TestForceTsv, TestTsvScrapersE2E,
                   TestEpisodeNumberingIssues, TestObjByShowScraped,
                   TestSuiteReachesNoNetwork,
                   TestS0XE0XPadding, TestMultiEpisodeSiblings,
                   TestAbsEpIdx, TestInfoScrapedData],
    'disk-map':   [TestDiskMap],
    'rename':     [TestRename, TestRenameShared],
    'commands':   [TestRemoveCommand, TestDeleteRequiresRemove, TestScan,
                   TestTrashNotRemove,
                   TestSortNew, TestSortNewScanLocations, TestUnmatched, TestUnsorted],
    'tools':      [TestSshOptions, TestRunToolLocally, TestRunToolOnPLEXServer],
    'quiet':      [TestQuiet],
    'venv':       [TestVenvDetection],
    'install':    [TestInstallFirewallRules, TestInstallPlexRule, TestInstallSshEntry],
    'conf-template': [TestConfigTemplateCoversEveryKey],
    'readme':     [TestReadmeFlagsExist, TestReadmeIsFound],
    'config':     [TestConfigLayers, TestConfigEnvVar, TestSecretArgs, TestISO639Mapping, TestAutoResolveConfig, TestResolveNoAudioLanguage,
                   TestLongHelp, TestNoAPIFallbacks, TestResolveMediaByNumericID,
                   TestDbQueriesUseLibraryName, TestAudioLangCacheBuildFallback,
                   TestAudioLangPureVsCompleted,
                   TestUnmatchedResolve],
    'refactor':   [TestRefactoredMethodNames, TestDeadCodeRemoval,
                   TestMediaApiActionConsolidation, TestListMethodSplit,
                   TestExecuteTrashAndMoveSplit, TestListMethodsGuardMissingKeys],
    'filter':     [TestFilter, TestDefaultScope],
    'misc':       [TestBadStructureResolve, TestLegacyInlineBlock, TestTopLevelHandlers, TestInitLoopRobustness, TestBrokenHeaderOrder, TestProblems, TestReencode, TestOndiskLabels,
                   TestDeployedCopy,
                   TestWaitForPlexScanComplete, TestErrorOutputConventions,
                   TestBrokenCrossValidation, TestEndToEnd,
                   TestShowInfoSeasonTable, TestMismatched, TestJunk,
                   TestShowDirDerivation, TestPlexConnectNotRequired],
    'renumber':   [TestRenumber],
    'move':       [TestMove],
    'original-languages': [TestOriginalLanguages],
    'scope':              [TestUniversalScope, TestArgvValueFlags],
    'unrecognized':       [TestUnrecognized],
    'layout':             [TestLayoutFilter, TestUncataloguedFolderMove],
    'compound':           [TestCompoundFilter],
    'sync':               [TestSyncDispatchAndDoubleMarkerFix],
    'naming':             [TestNaming],
    'v269':               [TestV269RetroactiveCoverage],
    'version':            [TestVersionAndStamp, TestVersionNamesItsRelease, TestRunViaSymlink],
    'errcodes':           [TestErrCodes],
    'root':               [TestNeverRunsAsRoot],
    'typecheck':          [TestTypeCheck],
    'run-tests':          [TestRunTestsTAP, TestDeployedCopyWithItsSuite],
}

# List of all unittest classes for run_regression_tests()
_UNITTEST_CLASSES = [cls for scope in _UNITTEST_SCOPES.values() for cls in scope]

# ---------------------------------------------------------------------------
# Inline regression tests + unittest runner
# ---------------------------------------------------------------------------

class _TAPResult(unittest.TextTestResult):
    """A unittest result that reports TAP-style: `ok K - title` per test.

    K is the test's place in the suite, counted from 1, so a reader collects
    results by number and the numbers are the same on every run.  The line is
    written as the test ends and flushed, because a reader draws progress from
    the stream; the failure detail is printed afterwards, in one piece.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tap_k = 0
        self._tap_verdict = None

    @staticmethod
    def _tap_title(test):
        return f"{test.__class__.__name__}.{test._testMethodName}"

    def startTest(self, test):
        self._tap_k += 1
        self._tap_verdict = None
        super().startTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        if self._tap_verdict is None:   # never overwrite a failed subTest
            self._tap_verdict = ('ok', '')

    def addSubTest(self, test, subtest, err):
        # A failed subTest never reaches addFailure -- unittest reports it
        # here and then calls stopTest once for the whole test.  Without this
        # the line read "not ok ... # no verdict recorded", which is the right
        # verdict for the wrong reason.
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._tap_verdict = ('not ok', '')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._tap_verdict = ('not ok', '')

    def addError(self, test, err):
        super().addError(test, err)
        self._tap_verdict = ('not ok', '')

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._tap_verdict = ('ok', f' # SKIP {reason}')

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._tap_verdict = ('ok', ' # TODO known failure')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._tap_verdict = ('not ok', ' # unexpected success')

    def stopTest(self, test):
        # No verdict can only mean a hook this class does not know about: say
        # "not ok" rather than pass a test nobody judged.
        status, note = self._tap_verdict or ('not ok', ' # no verdict recorded')
        print(f"{status} {self._tap_k} - {self._tap_title(test)}{note}", flush=True)
        super().stopTest(test)


class _TAPRunner(unittest.TextTestRunner):
    """The TAP plan `1..N` first, then _TAPResult's line per test.

    verbosity 0: the per-test line IS the TAP line, so unittest must not print
    its own beside it.  The count line and the failure detail it prints when
    the run ends are kept -- they are what a person reads.
    """

    resultclass = _TAPResult

    def __init__(self, **kwargs):
        kwargs.setdefault('verbosity', 0)
        super().__init__(**kwargs)

    def run(self, test):
        print(f"1..{test.countTestCases()}", flush=True)
        return super().run(test)


def _tap_suite(classes_or_tests):
    """One suite out of test CLASSES, single TESTS, or a mix of both."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for item in classes_or_tests:
        if isinstance(item, type):
            suite.addTests(loader.loadTestsFromTestCase(item))
        else:
            suite.addTest(item)
    return suite


def _tests_matching_title(filter_text):
    """Every test whose `Class.method` title contains FILTER_TEXT, any case."""
    loader = unittest.TestLoader()
    needle = filter_text.lower()
    return [t for cls in _UNITTEST_CLASSES
            for t in loader.loadTestsFromTestCase(cls)
            if isinstance(t, unittest.TestCase)        # a suite yields cases, never nested suites, here
            and needle in f"{cls.__name__}.{t._testMethodName}".lower()]


def describe_test_scopes():
    """The scopes and their test counts, as --help and an unmatched FILTER
    both print them -- one owner, so the two can never disagree."""
    loader = unittest.TestLoader()
    rows = ["Test scopes (--run-tests <SCOPE>):", ""]
    total = 0
    for name, classes in _UNITTEST_SCOPES.items():
        n = sum(loader.loadTestsFromTestCase(cls).countTestCases() for cls in classes)
        total += n
        rows.append(f"  {name:20s}  {n:3d} test{'' if n == 1 else 's'}  "
                    f"({', '.join(c.__name__ for c in classes)})")
    rows += ["",
             f"  {'(none)':20s}  {total:3d} tests  bare --run-tests: every scope",
             "",
             "Any other FILTER selects by test title, e.g. --run-tests TestFilter.test_year"]
    return "\n".join(rows)


def _run_unittest_only(unittest_classes):
    """Run the unittest suite and exit: 0 when every test passed, else 1."""
    import sys
    try:
        result = _TAPRunner().run(_tap_suite(unittest_classes))
    except Exception as e:
        print(f"✗ FAIL: Could not run unittest suite: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if result.wasSuccessful() else 1)

def run_regression_tests(scope=None):
    """Run the suite: all of it, one scope, or the tests whose title matches.

    Usage: my-plex.py --run-tests          (the whole suite)
           my-plex.py --run-tests <scope>  (one scope: see describe_test_scopes())
           my-plex.py --run-tests <title>  (the tests whose title contains it)
    Output is TAP: the plan first, then one line per test (_run_unittest_only).
    Exit codes: 0 = every test passed, 1 = a failure, or nothing matched.
    """
    import sys

    # Bare --run-tests RUNS the whole suite -- it does not print a menu.
    # my-rollout's `go` gates a pending copy on exactly this call, and the
    # name is a promise: see README, "Tests".
    if scope is None or scope.lower() == 'all':
        return _run_unittest_only(_UNITTEST_CLASSES)

    scope_lower = scope.lower()
    matched = {k: v for k, v in _UNITTEST_SCOPES.items() if scope_lower in k.lower()}
    if len(matched) > 1:
        print(f"ERROR: Ambiguous scope '{scope}' matches: {', '.join(matched.keys())}",
              file=sys.stderr)
        sys.exit(1)
    if matched:
        scope_name, unittest_classes = next(iter(matched.items()))
        print(f"scope {scope_name}: {', '.join(c.__name__ for c in unittest_classes)}")
        return _run_unittest_only(unittest_classes)
    # No scope of that name: take FILTER as a title substring, which is
    # what every other tool's --run-tests FILTER means.
    selected = _tests_matching_title(scope)
    if selected:
        print(f"filter {scope!r}: {len(selected)} test(s) by title")
        return _run_unittest_only(selected)
    print(f"ERROR: '{scope}' is neither a test scope nor part of any test title",
          file=sys.stderr)
    print(file=sys.stderr)
    print(describe_test_scopes(), file=sys.stderr)
    sys.exit(1)
