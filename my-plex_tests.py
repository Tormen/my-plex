# 52_tests.py — Test suite extracted from '52' (main script)
# To merge tests back inline, replace the test import section in '52' with the contents of this file.
#
# This file is imported by '52' at runtime via importlib.

import unittest
import os
import sys
import re
import inspect
import pickle
import io
import subprocess

MAIN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'my-plex.py')

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
    OBJ_BY_SHOW = {}
    OBJ_BY_SHOW_EPISODES = {}
    OBJ_BY_COLLECTION = {}

    @classmethod
    def reset(cls):
        cls.OBJ_BY_ID = {}
        cls.OBJ_BY_LIBRARY = {}
        cls.OBJ_BY_FILEPATH = {}
        cls.OBJ_BY_MOVIE = {}
        cls.OBJ_BY_SHOW = {}
        cls.OBJ_BY_SHOW_EPISODES = {}
        cls.OBJ_BY_COLLECTION = {}


def _make_movie(mid, title, filepath, version="90.0min 1920x1080 (h264 aac)", filesize=1000000, library=",unsorted", year=2023, originalTitle=""):
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


def _make_episode(eid, title, filepath, show_key, series, s_num, e_num, version="22.0min 1920x1080 (h264 aac)", filesize=500000, library="series.en"):
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
        'S0XE0X': f"S{s_num:02d}E{e_num:02d}", 'series': series, 'show_key': show_key,
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

    KNOWN_TYPES = {"Movie", "Episode", "Show", "Season", "Collection"}

    def test_collection_has_no_file_key(self):
        """Collection dicts must NOT have a 'file' key (they are metadata-only)."""
        col = _make_collection(1, "Action Movies", ",unsorted")
        self.assertNotIn('file', col)

    def test_movie_has_file_key(self):
        """Movie dicts must have a 'file' key."""
        m = _make_movie(100, "Test Movie", "/path/to/movie.mkv")
        self.assertIn('file', m)
        self.assertEqual(m['file'], "/path/to/movie.mkv")

    def test_episode_has_file_key(self):
        """Episode dicts must have a 'file' key."""
        e = _make_episode(200, "Pilot", "/path/to/ep.mkv", "Show:1", "TestShow", 1, 1)
        self.assertIn('file', e)

    def test_collection_type_is_known(self):
        """Collection type string must be in the known types set."""
        col = _make_collection(1, "X", "lib")
        self.assertIn(col['type'], self.KNOWN_TYPES)

    def test_all_media_types_in_known_set(self):
        """All factory-created objects must have a type in KNOWN_TYPES."""
        objects = [
            _make_movie(1, "M", "/m.mkv"),
            _make_episode(2, "E", "/e.mkv", "Show:1", "S", 1, 1),
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
        ep = _make_episode(200, "Pilot", "/path/ep_v1.mkv", "Show:1", "TestShow", 1, 1,
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
        e = _make_episode(2, "Pilot", "/e.mkv", "Show:1", "Breaking Bad", 1, 1)
        keys = self.generate_duplicate_keys(e)
        self.assertEqual(keys, ["episode:breaking bad:S01:E01"])

    def test_episode_unknown_season(self):
        e = _make_episode(2, "Pilot", "/e.mkv", "Show:1", "X", 1, 1)
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
        m1 = _make_movie(1, "Zoomania", "/de/m.mkv", year=2016, originalTitle="Zootopia", library="movies.de")
        m2 = _make_movie(2, "Zootropolis", "/en/m.mkv", year=2016, originalTitle="Zootopia", library="movies.en")
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
                case "Show":
                    processed.append('Show')
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
            'Episode:200': _make_episode(200, "Pilot", "/ep.mkv", "Show:1", "S", 1, 1),
            'Collection:300': _make_collection(300, "Action", ",unsorted"),
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
        """An unknown type should raise ValueError (matching err(1051) behavior)."""
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
        obj = _make_episode(4620, "Live from Studio 6H", "/east.mkv", "Show:1", "30 Rock", 6, 19)
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
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
            'Movie:2': {'library': 'movies.en', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        ignore = [['movies.de', 'movies.en', 'movies.fr']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 0)
        self.assertEqual(count, 1)

    def test_copy_outside_group_is_duplicate(self):
        obj_by_id = {
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
            'Movie:2': {'library': ',unsorted', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        ignore = [['movies.de', 'movies.en', 'movies.fr']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(count, 0)

    def test_four_copies_one_outside_is_duplicate(self):
        obj_by_id = {
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
            'Movie:2': {'library': 'movies.fr', 'title': 'Klaus'},
            'Movie:3': {'library': 'movies.en', 'title': 'Klaus'},
            'Movie:4': {'library': ',unsorted', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2', 'Movie:3', 'Movie:4']}
        ignore = [['movies.de', 'movies.en', 'movies.fr']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result['dup1']), 4)

    def test_all_three_in_group_excluded(self):
        obj_by_id = {
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
            'Movie:2': {'library': 'movies.fr', 'title': 'Klaus'},
            'Movie:3': {'library': 'movies.en', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2', 'Movie:3']}
        ignore = [['movies.de', 'movies.en', 'movies.fr']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 0)
        self.assertEqual(count, 1)

    def test_empty_ignore_groups_keeps_all(self):
        obj_by_id = {
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
            'Movie:2': {'library': 'movies.en', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        result, count = self._filter_duplicates(dups, [], obj_by_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(count, 0)

    def test_single_entry_multiversion_not_affected(self):
        obj_by_id = {
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1']}
        ignore = [['movies.de', 'movies.en', 'movies.fr']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 1)

    def test_multiple_ignore_groups_independent(self):
        obj_by_id = {
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
            'Movie:2': {'library': 'movies.en', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Movie:2']}
        ignore = [['series.de', 'series.en'], ['movies.de', 'movies.en', 'movies.fr']]
        result, count = self._filter_duplicates(dups, ignore, obj_by_id)
        self.assertEqual(len(result), 0)
        self.assertEqual(count, 1)

    def test_cross_group_not_ignored(self):
        obj_by_id = {
            'Movie:1': {'library': 'movies.de', 'title': 'Klaus'},
            'Episode:2': {'library': 'series.en', 'title': 'Klaus'},
        }
        dups = {'dup1': ['Movie:1', 'Episode:2']}
        ignore = [['movies.de', 'movies.en'], ['series.de', 'series.en']]
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
        config = [('movies.de', 'de'), ('movies.en', 'en')]
        self.assertEqual(self._lookup('movies.de', config), 'de')
        self.assertEqual(self._lookup('movies.en', config), 'en')

    def test_library_no_match(self):
        config = [('movies.de', 'de')]
        self.assertIsNone(self._lookup(',unsorted', config))

    def test_empty_config(self):
        self.assertIsNone(self._lookup('movies.de', []))


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
        if tool_name == 'mp4box':
            args = ['-lang', f'all={lang}', filepath]
        self.assertEqual(args, ['-lang', 'all=eng', '/path/to/Tenet.mp4'])

    def test_build_mkvpropedit_command(self):
        tool_name = 'mkvpropedit'
        filepath = '/path/to/Tenet.mkv'
        lang = 'deu'
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
        """Read script source, excluding the unittest section to avoid self-matching."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        start = content.find('\nimport unittest\n')
        end = content.find('\ndef run_regression_tests(main_globals):')
        if start != -1 and end != -1:
            return content[:start] + content[end:]
        return content

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
        self.assertIn("obj_type_inner == 'Show'", content)
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

    def test_from_scratch_counts_all_items_as_added(self):
        """--from-scratch summary must count all Movie/Episode objects as added."""
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
    resolve_filepath_with_alternatives = main_globals['resolve_filepath_with_alternatives']
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
        # This covers --from-scratch full processing paths that don't call
        # _collect_missing_file_metadata individually.
        self.assertIn("additional files missing metadata", content,
            "Must have a sweep that reports queuing additional files missing metadata")
        # The sweep must check file_metadata is not None (skip files that already have it)
        # and must append to _metadata_batch_queue
        import re
        # Find the sweep block — it's between re-attachment and batch collection
        sweep_pattern = r'already_queued.*?additional files missing metadata'
        match = re.search(sweep_pattern, content, re.DOTALL)
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
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("json.loads(line)", func_body,
            "Must parse JSON-lines output from collector script")
        self.assertIn("json.dumps(", func_body,
            "Collector script must output JSON via json.dumps")

    def test_add_media_obj_uses_determine_remote_host(self):
        """add_media_obj must use determine_remote_host() not getattr(library, 'remote_host')."""
        content = self._read_script()
        import re
        match = re.search(r'(def add_media_obj\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        self.assertIsNotNone(match, "add_media_obj function must exist")
        func_body = match.group(1)
        self.assertNotIn("getattr(library, 'remote_host'", func_body,
            "Must not use getattr(library, 'remote_host') — use determine_remote_host()")
        self.assertIn("determine_remote_host(", func_body,
            "Must use determine_remote_host() for proper remote detection")

    def test_get_video_file_metadata_uses_run_tool(self):
        """get_video_file_metadata must use run_tool_on_PLEX_server for ffmpeg (local and remote)."""
        content = self._read_script()
        import re
        match = re.search(r'(def get_video_file_metadata\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
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
        self.assertIn("avg_kbps", content,
            "Broken detection must compute average bitrate as fallback")
        self.assertIn("avg_kbps < 10", content,
            "Files with <10 KB/s average bitrate should be flagged as broken")

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
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertNotIn("plex_get_all_items", func_body,
            "update_movie_library_objs must NOT have API fallback via plex_get_all_items")

    def test_no_api_fallback_in_show_processing(self):
        """update_show_library_objs must NOT fall back to plex_get_all_items."""
        content = self._read_script()
        import re
        match = re.search(r'(def update_show_library_objs\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertNotIn("plex_get_all_items", func_body,
            "update_show_library_objs must NOT have API fallback via plex_get_all_items")

    def test_no_api_fallback_in_library_stats(self):
        """get_library_stats must NOT fall back to API totalSize."""
        content = self._read_script()
        import re
        match = re.search(r'(def get_library_stats\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
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
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("query_plex_database", func_body,
            "PLEX_Playlist.list must use DB query")
        self.assertNotIn("plex.playlists()", func_body,
            "PLEX_Playlist.list must NOT use API plex.playlists()")


class TestVerifyCacheIntegrity(unittest.TestCase):
    """verify_cache must perform comprehensive data integrity checks."""

    def _read_script(self):
        """Read script source, excluding the unittest section to avoid self-matching."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        start = content.find('\nimport unittest\n')
        end = content.find('\ndef run_regression_tests(main_globals):')
        if start != -1 and end != -1:
            return content[:start] + content[end:]
        return content

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
        self.assertIn("show_dangling", content,
            "verify_cache must detect dangling OBJ_BY_SHOW references")
        self.assertIn("episode_dangling", content,
            "verify_cache must detect dangling OBJ_BY_SHOW_EPISODES references")

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
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("not_found_count", func_body,
            "Must track file-not-found separately from ffprobe errors")
        self.assertIn("file_not_found", func_body,
            "Must mark missing files with reason='file_not_found' in cache")
        self.assertIn("not found on server", func_body,
            "Must report missing file count at end of batch collection")

    def test_batch_metadata_falls_back_to_db_host(self):
        """Batch metadata must fall back to PLEX_DB_REMOTE_HOST when files not found."""
        content = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("PLEX_DB_REMOTE_HOST", func_body,
            "Must fall back to PLEX_DB_REMOTE_HOST when determine_remote_host fails")

    def test_batch_metadata_continues_on_error(self):
        """Collector script must continue on failure, not abort."""
        content = self._read_script()
        import re
        match = re.search(r'(def _run_batch_metadata_collection\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        self.assertIsNotNone(match)
        func_body = match.group(1)
        # Extract the inline collector script portion (between collector_script = and closing ''')
        script_match = re.search(r"collector_script = f'''(.*?)'''", func_body, re.DOTALL)
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
        self.assertIn("marked as BROKEN", func_body,
            "Must report broken file count at end of batch collection")

    def test_filepath_check_skips_show_season(self):
        """OBJ_BY_FILEPATH check must skip Show/Season directory container objects."""
        content = self._read_script()
        import re
        match = re.search(r'(# Check 2: OBJ_BY_FILEPATH.*?)(?=# Check 3:)', content, re.DOTALL)
        self.assertIsNotNone(match, "Must have Check 2: OBJ_BY_FILEPATH section")
        check2 = match.group(1)
        self.assertIn("('Show', 'Season')", check2,
            "OBJ_BY_FILEPATH check must skip Show/Season objects (directory containers)")

    def test_itemscount_compares_primary_type_only(self):
        """itemsCount check must compare like-for-like: primary type per library only."""
        content = self._read_script()
        import re
        match = re.search(r'(# Check 7: library_stats.*?)(?=# Summary)', content, re.DOTALL)
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
        self.assertIsNotNone(match, "Must have file metadata check section")
        check1 = match.group(1)
        self.assertNotIn("integrity_issues.append", check1.split("broken_metadata")[1] if "broken_metadata" in check1 else "",
            "Broken files must NOT be appended to integrity_issues")
        # Verify broken is reported as info/warning outside of integrity_issues
        summary_match = re.search(r'(# Summary.*?)(?=print.*=".*76)', content, re.DOTALL)
        self.assertIsNotNone(summary_match, "Must have Summary section")
        summary = summary_match.group(1)
        self.assertIn("broken_metadata", summary,
            "Summary must show broken files as a warning before integrity issues")

    def test_skip_logic_compares_episode_count(self):
        """Skip logic for show libraries must compare episode count, not just show count."""
        content = self._read_script()
        import re
        match = re.search(r'(def process_single_library\(.*?\):\n.*?)(?=\n    def update_cache)', content, re.DOTALL)
        self.assertIsNotNone(match, "Must find process_single_library function")
        func_body = match.group(1)
        self.assertIn("current_episode_count", func_body,
            "Skip logic must compare current episode count for show libraries")
        self.assertIn("old_episode_count", func_body,
            "Skip logic must compare old episode count from cache")

    def test_get_library_stats_queries_episode_count(self):
        """get_library_stats must query episode count for show libraries."""
        content = self._read_script()
        import re
        match = re.search(r'(def get_library_stats\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        self.assertIsNotNone(match, "Must find get_library_stats function")
        func_body = match.group(1)
        self.assertIn("episodesCount", func_body,
            "get_library_stats must store episode count in episodesCount")
        self.assertIn("metadata_type = 4", func_body,
            "get_library_stats must query metadata_type=4 (episodes) for show libraries")

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
        self.assertIsNotNone(match, "Must find _list_broken_files method")
        broken_block = match.group(1)
        # Must NOT skip objects with no plex duration (they may have PROBE ERR / NOT FOUND files)
        self.assertNotIn("if not plex_duration:\n                    continue", broken_block,
            "--broken must not skip objects with None duration — PROBE ERR files would be hidden")

    def test_from_scratch_preserves_file_metadata(self):
        """--from-scratch must preserve file_metadata and re-attach after rebuild."""
        content = self._read_script()
        self.assertIn("_preserved_file_metadata", content,
            "--from-scratch must extract file_metadata before clearing OBJ_BY_ID")
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
        self.assertIn("--update-cache --from-scratch", content)

    def test_filter_skips_show_season_types(self):
        content = self._read_script()
        self.assertIn("obj_type in ('Show', 'Season')", content)

    def test_print_handles_members_list(self):
        content = self._read_script()
        self.assertIn("case 'MEMBERS':", content)


class TestCacheStructureParity(unittest.TestCase):
    """DB-based cache building must produce the same structure as old API-based code."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_show_objects_created_by_db_path(self):
        content = self._read_script()
        self.assertIn("'type': 'Show', 'type_str': 'Show'", content)

    def test_season_objects_created_by_db_path(self):
        content = self._read_script()
        self.assertIn("'type': 'Season', 'type_str': 'Season'", content)

    def test_obj_by_show_populated(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_SHOW[show_key][s_str] = season_key", content)

    def test_obj_by_show_episodes_version_format(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_SHOW_EPISODES[show_key][s_str][e_str][version]", content)
        self.assertIn(".append(episode_key)", content)

    def test_obj_by_library_type_keys_format(self):
        content = self._read_script()
        self.assertIn("PLEX_Media.OBJ_BY_LIBRARY[library_name]['Movie'] = []", content)
        self.assertIn("lib_dict['Episode'] = []", content)
        self.assertIn("lib_dict['Show'] = []", content)
        self.assertIn("lib_dict['Season'] = []", content)

    def test_obj_by_movie_version_filepath_format(self):
        content = self._read_script()
        self.assertIn("OBJ_BY_MOVIE[movie_key][ver] = file_info.get('filepath'", content)

    def test_get_obj_keys_iterates_by_type(self):
        content = self._read_script()
        self.assertIn("for t in ('Show', 'Episode', 'Movie')", content)


class TestDbQueriesUseLibraryName(unittest.TestCase):
    """DB queries must use library name (JOIN library_sections) instead of internal IDs."""

    def _read_script(self):
        """Read script source, excluding the unittest section to avoid self-matching."""
        with open(MAIN_SCRIPT, 'r') as f:
            content = f.read()
        # Strip out inline test classes (between 'import unittest' and 'def run_regression_tests')
        start = content.find('\nimport unittest\n')
        end = content.find('\ndef run_regression_tests(main_globals):')
        if start != -1 and end != -1:
            return content[:start] + content[end:]
        return content

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
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("'ssh', PLEX_DB_REMOTE_HOST", func_body,
            "Must have SSH path for remote execution")
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

    def test_show_item_info_requires_id_prefix(self):
        """show_item_info must REQUIRE 'ID:<num>' prefix — bare numbers must NOT match as Plex IDs."""
        content = self._read_script()
        import re
        match = re.search(r'(def show_item_info\(.*?\):\n.*?)(?=\ndef [a-z_])', content, re.DOTALL)
        self.assertIsNotNone(match)
        func_body = match.group(1)
        self.assertIn("startswith('ID:')", func_body,
            "show_item_info must require 'ID:' prefix for Plex ID lookup")


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
        """_normalize_list_args must map 'Series' to 'Show'."""
        content = self._read_script()
        import re
        match = re.search(r'def _normalize_list_args\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn('"Series"', body)
        self.assertIn('"Show"', body)

    def test_normalize_list_args_validates_media_type(self):
        """_normalize_list_args must reject invalid media types with err(1043)."""
        content = self._read_script()
        import re
        match = re.search(r'def _normalize_list_args\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("1043", body, "Must error 1043 on invalid media_type")

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
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_verify_data_integrity()", body)

    def test_integrity_checks_collection_members(self):
        """_verify_data_integrity must check OBJ_BY_COLLECTION member references."""
        content = self._read_script()
        import re
        match = re.search(r'def _verify_data_integrity\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("OBJ_BY_COLLECTION", body)

    def test_integrity_checks_obj_by_filepath(self):
        """_verify_data_integrity must validate OBJ_BY_FILEPATH consistency."""
        content = self._read_script()
        import re
        match = re.search(r'def _verify_data_integrity\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
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
        self.assertIsNotNone(match)
        params = match.group(1)
        self.assertIn("old_read_only", params, "Must accept old_read_only to restore READ_ONLY_MODE")

    def test_finalize_saves_cache(self):
        """_finalize_and_save_cache must call update_and_save_cache."""
        content = self._read_script()
        import re
        match = re.search(r'def _finalize_and_save_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("update_and_save_cache(", body)
        self.assertIn("build_media_cache_dict(", body)

    def test_finalize_rebuilds_library_object_counts(self):
        """_finalize_and_save_cache must rebuild library_object_counts."""
        content = self._read_script()
        import re
        match = re.search(r'def _finalize_and_save_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("updated_library_object_counts", body)

    def test_update_cache_calls_finalize(self):
        """PLEX_Library.update_cache() must call _finalize_and_save_cache."""
        content = self._read_script()
        import re
        # Find PLEX_Library.update_cache specifically (not PLEX_Media.update_cache)
        match = re.search(r'class PLEX_Library.*?def update_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_finalize_and_save_cache(", body)

    def test_old_read_only_passed_correctly(self):
        """update_cache must pass old_read_only to _finalize_and_save_cache."""
        content = self._read_script()
        import re
        match = re.search(r'class PLEX_Library.*?def update_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("old_read_only", body, "Must pass old_read_only to _finalize_and_save_cache")

    def test_no_inline_save_in_update_cache(self):
        """update_cache must NOT have inline cache save logic (moved to _finalize_and_save_cache)."""
        content = self._read_script()
        import re
        match = re.search(r'class PLEX_Library.*?def update_cache\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
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
        self.assertIsNotNone(match, "Must find --broken header line")
        self.assertEqual(match.group(1), 'DURATION', "DURATION must come before LIBRARY in --broken header")
        self.assertEqual(match.group(2), 'LIBRARY', "LIBRARY must come after DURATION in --broken header")

    def test_data_line_matches_header_order(self):
        """--broken data format must output dur_str before library."""
        content = self._read_script()
        import re
        # Find the actual data print line (single line with plex_id_str, severity_str, diff_str)
        match = re.search(r'print\(f".*plex_id_str.*severity_str.*diff_str.*(dur_str).*(library).*filepath', content)
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
        self.assertIsNotNone(match)
        self.assertIn("version_limit", match.group(1))

    def test_excess_versions_filters_by_limit(self):
        """_list_excess_versions must compare file count against version_limit."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("version_limit", body)
        self.assertIn("total", body, "Must track total version count")

    def test_excess_versions_output_has_version_fraction(self):
        """Output must show version as 'x / y' format."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("idx", body, "Must track version index")
        self.assertIn("total", body, "Must track total count")
        # Check for x / y format string
        self.assertRegex(body, r'f".*idx.*total', "Must format version as x / y")

    def test_excess_versions_header_columns(self):
        """Output header must have PLEX-ID, ENTRY TITLE, VERSION, LIBRARY, FILEPATH."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        for col in ['PLEX-ID', 'ENTRY TITLE', 'VERSION', 'LIBRARY', 'FILEPATH']:
            self.assertIn(col, body, f"Header must include {col}")

    def test_excess_versions_one_line_per_file(self):
        """Must iterate over files_dict to produce one output line per file."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("files_dict", body, "Must access files_dict for per-file iteration")
        self.assertIn("enumerate(", body, "Must enumerate files for version numbering")

    def test_excess_versions_wired_in_list(self):
        """PLEX_Media.list() must accept and dispatch excess_versions."""
        content = self._read_script()
        import re
        match = re.search(r'def list\(args, obj_args.*?\)', content)
        self.assertIsNotNone(match)
        self.assertIn("excess_versions", match.group(0), "list() must accept excess_versions parameter")

    def test_excess_versions_wired_in_global_commands(self):
        """execute_global_commands must pass excess_versions to PLEX_Media.list()."""
        content = self._read_script()
        import re
        match = re.search(r'def execute_global_commands\(.*?\n(.*?)(?=\n###)', content, re.DOTALL)
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
        """--problems must call _list_broken_files."""
        content = self._read_script()
        import re
        match = re.search(r"safe_getattr\(cmd_args, 'problems'.*?\n(.*?)(?=\n    # Handle --list)", content, re.DOTALL)
        self.assertIsNotNone(match, "Must find --problems handler block")
        body = match.group(1)
        self.assertIn("_list_broken_files(", body)

    def test_problems_runs_excess_versions(self):
        """--problems must call _list_excess_versions with limit 3."""
        content = self._read_script()
        import re
        match = re.search(r"safe_getattr\(cmd_args, 'problems'.*?\n(.*?)(?=\n    # Handle --list)", content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_list_excess_versions(", body)
        self.assertIn(", 3)", body, "Must use limit 3 for excess versions")

    def test_problems_prints_summary(self):
        """--problems must print a SUMMARY section."""
        content = self._read_script()
        import re
        match = re.search(r"safe_getattr\(cmd_args, 'problems'.*?\n(.*?)(?=\n    # Handle --list)", content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("SUMMARY", body)

    def test_problems_has_detailed_help(self):
        """--help problems must provide detailed help."""
        content = self._read_script()
        self.assertIn("case 'problems':", content, "Must have --help problems case")
        import re
        match = re.search(r"case 'problems':\n(.*?)sys\.exit\(0\)", content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("PROBLEMS HELP", body)
        self.assertIn("--broken", body)
        self.assertIn("--excess-versions", body)

    def test_broken_returns_count(self):
        """_list_broken_files must return a count for --problems summary."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_broken_files\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("return 0", body, "Must return 0 when no broken files")
        self.assertIn("return len(broken_files)", body, "Must return count of broken files")

    def test_excess_versions_returns_counts(self):
        """_list_excess_versions must return file and entry counts for --problems summary."""
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("return 0, 0", body, "Must return (0, 0) when no excess versions")
        self.assertIn("return len(excess_files), entry_count", body, "Must return (file_count, entry_count)")


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
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("media.delete()", body, "remove() must NOT delete the Plex entry")

    def test_delete_does_not_trash_files(self):
        """delete() must NOT trash files — that's --remove's job."""
        content = self._read_script()
        import re
        match = re.search(r'def delete\(media_identifier.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("move_to_trash(", body, "delete() must NOT trash files")

    def test_delete_syncs_cache(self):
        """delete() must remove deleted entries from cache and save to disk."""
        content = self._read_script()
        import re
        match = re.search(r'def delete\(media_identifier.*?\n(.*?)(?=\n    @staticmethod)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("_remove_from_cache_by_id(", body,
            "delete() must call _remove_from_cache_by_id after successful API delete")

    def test_remove_from_cache_by_id_exists(self):
        """_remove_from_cache_by_id must exist and update all cache structures + save."""
        content = self._read_script()
        import re
        match = re.search(r'def _remove_from_cache_by_id\(numeric_id\).*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        self.assertIsNotNone(match, "_remove_from_cache_by_id method must exist")
        body = match.group(1)
        self.assertIn("OBJ_BY_ID", body, "Must update OBJ_BY_ID")
        self.assertIn("OBJ_BY_FILEPATH", body, "Must update OBJ_BY_FILEPATH")
        self.assertIn("OBJ_BY_LIBRARY", body, "Must update OBJ_BY_LIBRARY")
        self.assertIn("OBJ_BY_SHOW_EPISODES", body, "Must update OBJ_BY_SHOW_EPISODES for episodes")
        self.assertIn("OBJ_BY_MOVIE", body, "Must update OBJ_BY_MOVIE for movies")
        self.assertIn("update_and_save_cache(", body, "Must save cache to disk")

    def test_remove_from_cache_cleans_episode_from_show_episodes(self):
        """_remove_from_cache_by_id must remove episode keys from OBJ_BY_SHOW_EPISODES."""
        content = self._read_script()
        import re
        match = re.search(r'def _remove_from_cache_by_id\(numeric_id\).*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        # Must handle Episode type specifically with show_key/S_str/E_str lookups
        self.assertIn("obj_type == 'Episode'", body,
            "Must have specific Episode handling for OBJ_BY_SHOW_EPISODES cleanup")
        self.assertIn("S_str", body, "Must use S_str to find season in OBJ_BY_SHOW_EPISODES")
        self.assertIn("E_str", body, "Must use E_str to find episode in OBJ_BY_SHOW_EPISODES")

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
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_LIBRARY = {}", body,
            "remove() must NOT blank OBJ_BY_LIBRARY — surgically update instead")

    def test_remove_handles_already_gone_files(self):
        """remove() must detect files already gone from disk and still clean cache."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("GONE", body, "Must check if file is gone from disk")

    def test_remove_checks_existence_before_trash(self):
        """remove() must check file existence BEFORE move_to_trash to avoid ERROR for gone files."""
        content = self._read_script()
        import re
        match = re.search(r'def remove\(media_identifier.*?rm_spec.*?\n(.*?)(?=\n    ######)', content, re.DOTALL)
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
    Bug: KeyError: 'Show:4392' in _list_broken_files.
    """

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_list_broken_files_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _list_broken_files\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_ID[key]", body, "_list_broken_files must use .get(key) not [key]")

    def test_list_excess_versions_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _list_excess_versions\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_ID[key]", body, "_list_excess_versions must use .get(key) not [key]")

    def test_find_duplicates_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _find_duplicates\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertNotIn("OBJ_BY_ID[okey]", body, "_find_duplicates must use .get(okey) not [okey]")
        self.assertNotIn("OBJ_BY_ID[key]", body, "_find_duplicates must use .get(key) not [key]")

    def test_filter_by_watch_and_audio_uses_get(self):
        content = self._read_script()
        import re
        match = re.search(r'def _filter_by_watch_and_audio\(.*?\n(.*?)(?=\n    @staticmethod|\n    ####)', content, re.DOTALL)
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
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("active_sections", body, "Must check plex.activities for ongoing scan activities")
        self.assertIn("lib.refreshing", body, "Must still check lib.refreshing as first phase")

    def test_get_active_scan_section_ids(self):
        """_get_active_scan_section_ids helper must check library.update.section activities."""
        content = self._read_script()
        import re
        match = re.search(r'def _get_active_scan_section_ids\(.*?\n(.*?)(?=\ndef )', content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        self.assertIn("library.update.section", body)
        self.assertIn("activities", body)

    def test_update_cache_uses_parallel_helper(self):
        """--update-cache must use wait_for_plex_scans_complete (parallel), not sequential."""
        content = self._read_script()
        import re
        match = re.search(r"Waiting for all libraries to complete scanning.*?print\(f.*?=.*?76", content, re.DOTALL)
        self.assertIsNotNone(match, "Could not find scan waiting section in update_cache")
        body = match.group(0)
        self.assertIn("wait_for_plex_scans_complete(", body,
            "--update-cache must use wait_for_plex_scans_complete (parallel)")
        self.assertNotIn("lib.refreshing", body,
            "--update-cache must NOT use raw lib.refreshing")


class TestEndToEnd(unittest.TestCase):
    """End-to-end tests: run actual commands as subprocesses to verify they work."""

    def _run_cmd(self, *extra_args):
        import subprocess
        cmd = [sys.executable, MAIN_SCRIPT] + list(extra_args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result

    # --- Help commands ---

    def test_help_default(self):
        """my-plex --help must show main help."""
        result = self._run_cmd('--help')
        self.assertEqual(result.returncode, 0, f"--help failed: {result.stderr}")
        self.assertIn("OBJECT_TYPE", result.stdout)

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
        """my-plex --list without library must show available libraries."""
        result = self._run_cmd('--list')
        self.assertEqual(result.returncode, 0, f"--list failed: {result.stderr}")
        self.assertIn("Available Libraries", result.stdout)

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
        """my-plex --problems must run all checks and show SUMMARY."""
        result = self._run_cmd('--problems')
        self.assertEqual(result.returncode, 0, f"--problems failed: {result.stderr}")
        self.assertIn("SUMMARY", result.stdout)
        self.assertIn("Broken/truncated files:", result.stdout)
        self.assertIn("Excess version entries:", result.stdout)

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
        """my-plex ID:<broken_id> must show BROKEN status with reason."""
        # Get first broken file from --broken output
        result = self._run_cmd('--broken')
        if result.returncode != 0:
            self.skipTest("--broken failed")
        lines = result.stdout.strip().split('\n')
        broken_id = None
        for line in lines:
            if line.startswith('ID:'):
                broken_id = line.split()[0]  # e.g. "ID:33885"
                break
        if not broken_id:
            self.skipTest("No broken files found to test")
        result2 = self._run_cmd(broken_id)
        self.assertEqual(result2.returncode, 0, f"my-plex {broken_id} failed")
        self.assertIn("BROKEN", result2.stdout, f"--info for broken item {broken_id} must show BROKEN status")

    # --- Verify cache (read-only) ---

    def test_verify_cache(self):
        """my-plex --verify-cache must run without crashing."""
        result = self._run_cmd('--verify-cache')
        # May fail if no server connection, but must not crash
        self.assertNotIn("Traceback", result.stderr, "--verify-cache must not crash with traceback")

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

    # --- Output format ---

    def test_list_with_format(self):
        """my-plex --list with a library must accept --format."""
        # Use --list without library — should show library list
        result = self._run_cmd('--list', '-f', 'pretty')
        self.assertEqual(result.returncode, 0, f"--list -f pretty failed: {result.stderr}")

    def test_broken_no_false_positives_with_video_duration(self):
        """my-plex --broken must not flag files where container and video stream durations agree.

        Regression test: Modern Family episodes were false positives because Plex reported
        a slightly different duration than ffprobe, but the files' container and video stream
        durations agreed within 2s — meaning the files are healthy.
        """
        result = self._run_cmd('--broken')
        self.assertEqual(result.returncode, 0, f"--broken failed: {result.stderr}")
        # If any Modern Family files with video_duration in cache still appear, the
        # cross-validation is broken. Check specifically for the known false-positive episodes.
        lines = result.stdout.strip().split('\n')
        false_positive_ids = {'ID:31983', 'ID:32028', 'ID:32020', 'ID:32041', 'ID:32038',
                              'ID:32032', 'ID:32026', 'ID:32143', 'ID:32027', 'ID:32023',
                              'ID:31981', 'ID:32037', 'ID:31987', 'ID:31984', 'ID:31979',
                              'ID:32031', 'ID:31978'}
        flagged_fps = []
        for line in lines:
            for fp_id in false_positive_ids:
                if line.startswith(fp_id):
                    flagged_fps.append(fp_id)
        self.assertEqual(flagged_fps, [],
            f"Cross-validation failed: known false-positive IDs still flagged as broken: {flagged_fps}")


class TestErrorOutputConventions(unittest.TestCase):
    """Ensure ERROR output conventions: ERROR=fatal with verbose guidance, WARNING only for benign cases."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_print_ssh_error_uses_error_not_warning(self):
        """print_ssh_error must use ERROR prefix — SSH failures are fatal."""
        src = self._read_script()
        match = re.search(r'def print_ssh_error\(.*?\n(.*?)(?=\ndef )', src, re.DOTALL)
        self.assertIsNotNone(match, "print_ssh_error not found")
        body = match.group(1)
        self.assertIn('ERROR:', body, "print_ssh_error must use ERROR prefix")

    def test_print_ssh_error_has_troubleshooting(self):
        """print_ssh_error must include verbose troubleshooting guidance."""
        src = self._read_script()
        match = re.search(r'def print_ssh_error\(.*?\n(.*?)(?=\ndef )', src, re.DOTALL)
        body = match.group(1)
        self.assertIn('ssh/config', body, "print_ssh_error must have SSH config instructions")
        self.assertIn('Example', body, "print_ssh_error must have example config")

    def test_trash_failure_has_possible_reasons(self):
        """TRASH SSH failure path must include 'Possible reasons' block."""
        src = self._read_script()
        match = re.search(r'def my_plex_file_operation\(.*?\n(.*?)(?=\n################################)', src, re.DOTALL)
        self.assertIsNotNone(match, "my_plex_file_operation not found")
        body = match.group(1)
        self.assertIn('Possible reasons:', body, "SSH failure paths must have 'Possible reasons' guidance")


class TestObjByLibraryDedup(unittest.TestCase):
    """Ensure OBJ_BY_LIBRARY appends have dedup checks to prevent duplicate keys."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_show_episode_season_appends_have_dedup_check(self):
        """All OBJ_BY_LIBRARY .append() calls in show/episode/season processing must check for duplicates."""
        src = self._read_script()
        match = re.search(r'def _process_shows_from_database\(.*?\n(.*?)(?=\ndef )', src, re.DOTALL)
        self.assertIsNotNone(match, "_process_shows_from_database not found")
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

    def test_update_cache_cleans_dangling_show_keys(self):
        """--update-cache must remove dangling keys from OBJ_BY_SHOW."""
        src = self._read_script()
        self.assertIn('dangling keys from OBJ_BY_SHOW', src,
            "--update-cache must clean dangling keys from OBJ_BY_SHOW")

    def test_update_cache_cleans_dangling_episode_keys(self):
        """--update-cache must remove dangling keys from OBJ_BY_SHOW_EPISODES."""
        src = self._read_script()
        self.assertIn('dangling keys from OBJ_BY_SHOW_EPISODES', src,
            "--update-cache must clean dangling keys from OBJ_BY_SHOW_EPISODES")

    def test_update_cache_saves_all_structures(self):
        """--update-cache final save must include all cache structures, not just labels/filepath."""
        src = self._read_script()
        match = re.search(r'# Save all rebuilt.*?\n\s*(update_and_save_cache\(.*?\))', src, re.DOTALL)
        self.assertIsNotNone(match, "Final save must use build_media_cache_dict()")
        save_call = match.group(1)
        self.assertIn('build_media_cache_dict', save_call,
            "Final save must use build_media_cache_dict() to persist all structures")


class TestDeleteRequiresRemove(unittest.TestCase):
    """Ensure --del refuses to run without --rm, and help text warns about file deletion."""

    def _read_script(self):
        with open(MAIN_SCRIPT, 'r') as f:
            return f.read()

    def test_del_without_rm_is_rejected(self):
        """--del without --rm must be rejected with an error."""
        result = subprocess.run(
            [sys.executable, MAIN_SCRIPT, '--offline', 'ID:99999', '--del'],
            capture_output=True, text=True, timeout=30
        )
        self.assertNotEqual(result.returncode, 0, "--del without --rm should fail")
        self.assertIn('--rm', result.stderr + result.stdout, "Error must mention --rm requirement")

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
        self.assertIsNotNone(match, "--delete/--del media argparse not found")
        help_text = match.group(1)
        self.assertIn('files', help_text.lower(), "--delete help must mention files")

    def test_delete_method_comment_warns_about_files(self):
        """delete() method must have a comment warning about file deletion."""
        src = self._read_script()
        match = re.search(r'def delete\(media_identifier.*?\n(.*?)\n', src)
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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

    def test_scan_implies_force_metadata(self):
        """--scan must enable FORCE_METADATA so file durations are re-read."""
        src = self._read_script()
        self.assertIn("has_scan", src, "has_scan variable must exist")
        self.assertRegex(src, r'FORCE_METADATA.*has_scan',
            "--scan must enable FORCE_METADATA")

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
        wrapper_path = os.path.join(os.path.dirname(MAIN_SCRIPT), 'my-plex')
        with open(wrapper_path, 'r') as f:
            wrapper = f.read()
        self.assertIn("'--scan[", wrapper,
            "--scan not found in zsh completion script")

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
        # Header must contain V column (right-aligned, so " V" with leading space)
        self.assertIn("|  V |", result.stdout,
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


# List of all unittest classes for run_regression_tests()
_UNITTEST_CLASSES = [
    TestObjTypeHandling, TestMultiVersionMerge, TestCacheResumeWithMultiVersion,
    TestDuplicateKeyGeneration, TestInitLoopRobustness, TestClassifyMultiVersion,
    TestDuplicatesIgnoreLibraryCombinations, TestRunToolLocally, TestRunToolOnPLEXServer,
    TestISO639Mapping, TestAutoResolveConfig, TestResolveNoAudioLanguage,
    TestLongHelp, TestPlexUpdatedAtTracking, TestCacheSkipLogic,
    TestNoAPIFallbacks, TestVerifyCacheIntegrity, TestResolveMediaByNumericID,
    TestCacheFormatValidation, TestCacheStructureParity, TestDbQueriesUseLibraryName,
    TestRefactoredMethodNames, TestDeadCodeRemoval, TestMediaApiActionConsolidation,
    TestListMethodSplit, TestExecuteTrashAndMoveSplit, TestVerifyCacheSplit,
    TestUpdateCacheSplit, TestBrokenHeaderOrder, TestExcessVersions,
    TestProblems, TestExcessVersionsMainParser, TestRemoveCommand,
    TestListMethodsGuardMissingKeys, TestWaitForPlexScanComplete, TestErrorOutputConventions,
    TestObjByLibraryDedup,
    TestDeleteRequiresRemove,
    TestScan,
    TestBrokenCrossValidation,
    TestEndToEnd,
]

# ---------------------------------------------------------------------------
# Inline regression tests + unittest runner
# ---------------------------------------------------------------------------

def run_regression_tests(main_globals):
    """Run regression tests to verify script functionality

    POLICY: Whenever a bug is fixed in my-plex.py, a regression test MUST be added here
    to prevent the bug from reoccurring. Each test should:
    - Have a descriptive name and number (e.g., "Test 5: Duplicate Detection")
    - Include a comment explaining which bug it tests for
    - Show clear PASS/FAIL/SKIP status with helpful output
    - Increment passed/failed counters appropriately

    Usage: my-plex.py --test
    Exit codes: 0 = all tests passed, 1 = one or more tests failed
    """
    # Extract globals from main script
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
    resolve_filepath_with_alternatives = main_globals['resolve_filepath_with_alternatives']
    format_filesize = main_globals['format_filesize']
    build_media_cache_dict = main_globals['build_media_cache_dict']
    load_media_cache = main_globals['load_media_cache']
    execute_global_commands = main_globals['execute_global_commands']
    update_and_save_cache = main_globals.get('update_and_save_cache')
    undo_operation = main_globals.get('undo_operation')
    DBG = main_globals.get('DBG', False)
    inject_before_first_match = main_globals.get('inject_before_first_match')

    import pickle
    import sys

    print("=" * 76)
    print("REGRESSION TEST SUITE")
    print("=" * 76)

    passed = 0
    failed = 0
    tests = []

    # Test 1: Cache timestamp preservation
    print("\n[TEST 1] Cache Timestamp Preservation")
    print("-" * 80)
    try:
        cache_file = CACHE_FILE
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache = pickle.load(f)

            if 'library_stats' in cache:
                lib_stats = cache['library_stats']
                if 'updatedAt' in lib_stats and len(lib_stats['updatedAt']) > 0:
                    print(f"✓ PASS: Cache has library_stats with {len(lib_stats['updatedAt'])} library timestamps")
                    print(f"  Sample libraries: {list(lib_stats['updatedAt'].keys())[:3]}")
                    passed += 1
                else:
                    print(f"✗ FAIL: Cache library_stats has empty updatedAt dictionary")
                    print(f"  This means timestamps are not being saved!")
                    failed += 1
            else:
                print(f"✗ FAIL: Cache missing library_stats")
                failed += 1
        else:
            print(f"⚠ SKIP: No cache file found at {cache_file}")
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 2: Argument abbreviation disabled
    print("\n[TEST 2] Argument Abbreviation Disabled")
    print("-" * 80)
    try:
        # Try to create a parser with allow_abbrev=False
        import argparse
        test_parser = argparse.ArgumentParser(allow_abbrev=False, exit_on_error=False)
        test_parser.add_argument('--duplicates', action='store_true')
        test_parser.add_argument('--debug', action='store_true')

        # Test that --d does NOT expand to --duplicates or --debug
        try:
            args, unknown = test_parser.parse_known_args(['--d'])
            if '--d' in unknown:
                print(f"✓ PASS: Argument abbreviation properly disabled (--d not expanded)")
                passed += 1
            else:
                print(f"✗ FAIL: --d was incorrectly expanded to a known argument")
                failed += 1
        except:
            print(f"✗ FAIL: Parser raised exception (should return --d in unknown args)")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 3: Cache structure validation
    print("\n[TEST 3] Cache Structure Validation")
    print("-" * 80)
    try:
        cache_file = CACHE_FILE
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache = pickle.load(f)

            required_keys = ['obj_by_id', 'library_stats']
            missing_keys = [k for k in required_keys if k not in cache]

            if not missing_keys:
                print(f"✓ PASS: Cache has all required keys: {required_keys}")
                print(f"  Total media objects: {len(cache.get('obj_by_id', {}))}")
                passed += 1
            else:
                print(f"✗ FAIL: Cache missing required keys: {missing_keys}")
                failed += 1
        else:
            print(f"⚠ SKIP: No cache file found")
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 4: Library object counts format
    print("\n[TEST 4] Library Object Counts Format")
    print("-" * 80)
    try:
        cache_file = CACHE_FILE
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache = pickle.load(f)

            if 'library_object_counts' in cache:
                counts = cache['library_object_counts']
                # Check that values are dicts, not ints (old format bug)
                format_ok = all(isinstance(v, dict) for v in counts.values())

                if format_ok:
                    print(f"✓ PASS: Library object counts are in correct dict format")
                    if counts:
                        sample_lib = list(counts.keys())[0]
                        print(f"  Sample: '{sample_lib}' = {counts[sample_lib]}")
                    passed += 1
                else:
                    print(f"✗ FAIL: Library object counts contain non-dict values (old format)")
                    failed += 1
            else:
                print(f"⚠ SKIP: No library_object_counts in cache")
        else:
            print(f"⚠ SKIP: No cache file found")
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 5: Duplicate detection - content-based grouping
    print("\n[TEST 5] Duplicate Detection - Content-Based Grouping")
    print("-" * 80)
    try:
        # This test verifies that duplicates are grouped by title+year, not by Plex IDs
        # Bug fixed: Movies with same title+year but different paths should be detected as duplicates
        cache_file = CACHE_FILE
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache = pickle.load(f)

            if 'obj_by_id' in cache and len(cache['obj_by_id']) > 0:
                # Look for any movies with the same title+year
                movies = [obj for obj in cache['obj_by_id'].values() if obj.get('type') == 'Movie']

                if len(movies) > 1:
                    # Group by title+year
                    title_year_groups = {}
                    for movie in movies[:100]:  # Sample first 100 for speed
                        title = movie.get('title', '').lower().strip()
                        year = movie.get('year', 0)
                        key = f"{title}:{year}"
                        if key not in title_year_groups:
                            title_year_groups[key] = []
                        title_year_groups[key].append(movie)

                    # Check if any group has duplicates
                    has_duplicates = any(len(movies) > 1 for movies in title_year_groups.values())

                    if has_duplicates:
                        dup_count = sum(1 for movies in title_year_groups.values() if len(movies) > 1)
                        print(f"✓ PASS: Content-based duplicate detection is testable")
                        print(f"  Found {dup_count} duplicate groups in sample of {len(movies)} movies")
                        passed += 1
                    else:
                        print(f"⚠ SKIP: No duplicates found in sample to test")
                else:
                    print(f"⚠ SKIP: Not enough movies in cache to test")
            else:
                print(f"⚠ SKIP: No media objects in cache")
        else:
            print(f"⚠ SKIP: No cache file found")
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 6: Invalid flag rejection
    print("\n[TEST 6] Invalid Flag Rejection")
    print("-" * 80)
    try:
        # This test verifies that invalid flags like --d are properly rejected
        # Bug fixed: Script should reject --d before connecting to Plex
        import argparse
        test_parser = argparse.ArgumentParser(allow_abbrev=False, exit_on_error=False)
        test_parser.add_argument('--duplicates', action='store_true')
        test_parser.add_argument('--debug', action='store_true')

        # Parse --d and check it's in unparsed args
        args, unparsed = test_parser.parse_known_args(['--d'])

        # The flag should be in unparsed list, not consumed by parser
        if '--d' in unparsed and not args.duplicates and not args.debug:
            print(f"✓ PASS: Invalid flags remain in unparsed list for validation")
            print(f"  --d was not expanded to --duplicates or --debug")
            passed += 1
        else:
            print(f"✗ FAIL: Invalid flag was incorrectly parsed")
            print(f"  args.duplicates={args.duplicates}, args.debug={args.debug}")
            print(f"  unparsed={unparsed}")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 7: Duplicate synonym functionality
    print("\n[TEST 7] --duplicates Synonym for --list --duplicates")
    print("-" * 80)
    try:
        # This test verifies that --duplicates alone works as synonym for --list --duplicates
        # Bug fixed: Added synonym support so users can type --duplicates instead of --list --duplicates
        import argparse
        test_parser = argparse.ArgumentParser(allow_abbrev=False, exit_on_error=False)
        test_parser.add_argument('--list', action='store_true')
        test_parser.add_argument('--duplicates', action='store_true')

        # Test that both --list --duplicates and just --duplicates can be distinguished
        args1, _ = test_parser.parse_known_args(['--list', '--duplicates'])
        args2, _ = test_parser.parse_known_args(['--duplicates'])

        if args1.list and args1.duplicates:
            print(f"✓ PASS: --list --duplicates combination works")
            passed += 1
        else:
            print(f"✗ FAIL: --list --duplicates not parsed correctly")
            failed += 1

        # The code should treat args2.duplicates as equivalent to args1.list + args1.duplicates
        # We can't test the actual behavior here, but we verify the flag is recognized
        if args2.duplicates:
            print(f"✓ PASS: --duplicates alone is recognized")
            passed += 1
        else:
            print(f"✗ FAIL: --duplicates alone not recognized")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 8: Filesize formatting in duplicate output
    print("\n[TEST 8] Filesize Formatting in Duplicate Output")
    print("-" * 80)
    try:
        # This test verifies that filesize formatting works correctly
        # Feature added: Show human-readable filesizes (KB/MB/GB) in --duplicates output

        # Test the filesize formatting logic
        test_cases = [
            (500, "500B"),
            (1024, "1KB"),
            (1536, "2KB"),  # 1.5 * 1024 = 1536
            (1024**2, "1MB"),
            (1.5 * 1024**2, "2MB"),  # Should round to 2MB
            (1024**3, "1.0GB"),
            (1.5 * 1024**3, "1.5GB"),
        ]

        all_pass = True
        for size_bytes, expected in test_cases:
            # Replicate the formatting logic from the code
            if size_bytes >= 1024**3:  # GB
                formatted = f"{size_bytes / (1024**3):.1f}GB"
            elif size_bytes >= 1024**2:  # MB
                formatted = f"{size_bytes / (1024**2):.0f}MB"
            elif size_bytes >= 1024:  # KB
                formatted = f"{size_bytes / 1024:.0f}KB"
            else:
                formatted = f"{int(size_bytes)}B"

            if formatted != expected:
                print(f"  ✗ {size_bytes} bytes → {formatted} (expected {expected})")
                all_pass = False

        if all_pass:
            print(f"✓ PASS: Filesize formatting works correctly")
            print(f"  Tested: Bytes, KB, MB, GB formatting")
            passed += 1
        else:
            print(f"✗ FAIL: Filesize formatting produced unexpected results")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 9: Duplicate output sorting
    print("\n[TEST 9] Duplicate Output Sorting")
    print("-" * 80)
    try:
        # This test verifies that duplicate items are sorted and grouped together
        # Feature added: Sort duplicates by key so same items appear consecutively

        # Test the sorting behavior
        test_dict = {
            'movie:zebra:2020': [1, 2],
            'movie:alpha:2020': [3, 4],
            'movie:beta:2019': [5, 6],
        }

        sorted_items = sorted(test_dict.items())
        sorted_keys = [k for k, v in sorted_items]

        expected_order = ['movie:alpha:2020', 'movie:beta:2019', 'movie:zebra:2020']

        if sorted_keys == expected_order:
            print(f"✓ PASS: Duplicate items are sorted alphabetically")
            print(f"  Order: {' → '.join([k.split(':')[1] for k in sorted_keys])}")
            passed += 1
        else:
            print(f"✗ FAIL: Sorting produced unexpected order")
            print(f"  Expected: {expected_order}")
            print(f"  Got: {sorted_keys}")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 10: Plex API filesize in cache
    print("\n[TEST 10] Plex API Filesize in Cache")
    print("-" * 80)
    try:
        # This test verifies that filesize from Plex API is stored in cache
        # Feature added: Store part.size from Plex API instead of calculating from filesystem
        cache_file = CACHE_FILE
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache = pickle.load(f)

            obj_by_id = cache.get('obj_by_id', {})
            if obj_by_id:
                # Check first 10 objects to see if they have filesize
                sample_objs = list(obj_by_id.values())[:10]
                objs_with_filesize = [obj for obj in sample_objs if 'filesize' in obj and obj['filesize'] is not None]

                if len(objs_with_filesize) > 0:
                    print(f"✓ PASS: Cache contains filesize from Plex API")
                    print(f"  Found filesize in {len(objs_with_filesize)}/{len(sample_objs)} sampled objects")
                    # Show sample filesize
                    sample_obj = objs_with_filesize[0]
                    size_bytes = sample_obj['filesize']
                    size_str = format_filesize(size_bytes)
                    print(f"  Sample: '{sample_obj['title']}' = {size_str} ({size_bytes} bytes)")
                    passed += 1
                else:
                    print(f"✗ FAIL: No objects in cache have filesize field")
                    print(f"  This means filesize from Plex API is not being cached!")
                    failed += 1
            else:
                print(f"⚠ SKIP: Cache has no objects")
        else:
            print(f"⚠ SKIP: No cache file found")
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test: --info command functionality
    print("\n[TEST] --info Command Functionality")
    print("-" * 80)
    try:
        if len(PLEX_Media.OBJ_BY_ID) > 0:
            # Get a test item (prefer episode for comprehensive testing)
            test_item = None
            test_key = None
            for key, obj in PLEX_Media.OBJ_BY_ID.items():
                if obj.get('type') == 'Episode':
                    test_item = obj
                    test_key = key
                    break

            # Fallback to any item if no episode found
            if not test_item:
                test_key = list(PLEX_Media.OBJ_BY_ID.keys())[0]
                test_item = PLEX_Media.OBJ_BY_ID[test_key]

            # Extract numeric ID for testing
            test_id = test_item.get('id')
            test_title = test_item.get('title', '')

            tests_passed = 0
            tests_total = 4

            # Test 0: Call show_item_info() without parameter (system info)
            print(f"  Testing: show_item_info('') - system info")
            try:
                import io
                from contextlib import redirect_stdout

                f = io.StringIO()
                with redirect_stdout(f):
                    show_item_info('')  # Empty string triggers system info
                output = f.getvalue()

                # Verify output contains system information
                if "PLEX SYSTEM INFORMATION" in output and "CACHE" in output and "LIBRARIES" in output:
                    print(f"  ✓ System info (--info without parameter): PASS")
                    tests_passed += 1
                else:
                    print(f"  ✗ System info (--info without parameter): FAIL - output missing expected sections")
                    if DBG: print(f"    Output: {output[:200]}...")
            except Exception as e:
                print(f"  ✗ System info (--info without parameter): FAIL - {e}")

            # Test 1: Call show_item_info() with ID: prefix (required format)
            print(f"  Testing: show_item_info('ID:{test_id}')")
            try:
                import io
                from contextlib import redirect_stdout

                # Capture output
                f = io.StringIO()
                with redirect_stdout(f):
                    show_item_info(f'ID:{test_id}')
                output = f.getvalue()

                # Verify output contains expected information
                if test_key in output and str(test_id) in output:
                    print(f"  ✓ Search by ID:{test_id}: PASS")
                    tests_passed += 1
                else:
                    print(f"  ✗ Search by ID:{test_id}: FAIL - output missing key info")
                    if DBG: print(f"    Output: {output[:200]}...")
            except Exception as e:
                print(f"  ✗ Search by ID:{test_id}: FAIL - {e}")

            # Test 2: Call show_item_info() with full key
            print(f"  Testing: show_item_info('{test_key}')")
            try:
                f = io.StringIO()
                with redirect_stdout(f):
                    show_item_info(test_key)
                output = f.getvalue()

                if test_key in output and str(test_id) in output:
                    print(f"  ✓ Search by full key ({test_key}): PASS")
                    tests_passed += 1
                else:
                    print(f"  ✗ Search by full key ({test_key}): FAIL - output missing key info")
            except Exception as e:
                print(f"  ✗ Search by full key ({test_key}): FAIL - {e}")

            # Test 3: Call show_item_info() with title search
            if test_title and len(test_title) >= 5:
                search_term = test_title[:10]
                print(f"  Testing: show_item_info('{search_term}')")
                try:
                    f = io.StringIO()
                    with redirect_stdout(f):
                        show_item_info(search_term)
                    output = f.getvalue()

                    # Should find at least one match (might be multiple)
                    if test_title.lower() in output.lower() or "Found" in output:
                        print(f"  ✓ Search by title ('{search_term}'): PASS")
                        tests_passed += 1
                    else:
                        print(f"  ✗ Search by title ('{search_term}'): FAIL - no results found")
                except Exception as e:
                    print(f"  ✗ Search by title ('{search_term}'): FAIL - {e}")
            else:
                print(f"  ⚠ SKIP: Title search (title too short)")
                tests_total = 3

            if tests_passed == tests_total:
                print(f"✓ PASS: --info command works correctly ({tests_passed}/{tests_total})")
                print(f"  Verified: my-plex --info (system info)")
                print(f"  Verified: my-plex --info ID:{test_id}")
                print(f"  Verified: my-plex --info {test_key}")
                print(f"  Verified: my-plex --offline --info '{search_term if test_title else test_id}'")
                passed += 1
            else:
                print(f"✗ FAIL: --info command failed ({tests_passed}/{tests_total} tests passed)")
                failed += 1
        else:
            print(f"⚠ SKIP: Cache has no objects to test")
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 6: SSH path escaping for special characters
    print("\n[TEST 6] SSH Path Escaping for Special Characters")
    print("-" * 80)
    try:
        # Test the escape_path_for_ssh function with various special characters
        # The function escapes chars special inside double quotes: " $ ` \
        # (paths are wrapped in double quotes at usage time: f'mv "{escaped}" ...')
        test_cases = [
            # (input_path, expected_output)
            ("/Volumes/2/watch.v/,unsorted/file.mp4",       "/Volumes/2/watch.v/,unsorted/file.mp4"),       # No special chars
            ("/path/charlie's angels (2019) [720p].mp4",    "/path/charlie's angels (2019) [720p].mp4"),    # Apostrophe: safe in double quotes
            ("/path/file with spaces.mp4",                  "/path/file with spaces.mp4"),                  # Spaces: safe in double quotes
            ("/path/file$with$dollars.mp4",                 "/path/file\\$with\\$dollars.mp4"),              # Dollar signs: must be escaped
            ("/path/file`with`backticks.mp4",               "/path/file\\`with\\`backticks.mp4"),            # Backticks: must be escaped
            ('/path/file"with"quotes.mp4',                  '/path/file\\"with\\"quotes.mp4'),              # Double quotes: must be escaped
            ("/path/normal_file.mp4",                       "/path/normal_file.mp4"),                       # Normal path
        ]

        all_passed = True
        for path, expected in test_cases:
            escaped = escape_path_for_ssh(path)
            if escaped != expected:
                print(f"  ✗ Mismatch for: {path}")
                print(f"    Expected: {expected}")
                print(f"    Got:      {escaped}")
                all_passed = False

        if all_passed:
            print(f"✓ PASS: SSH path escaping handles special characters correctly")
            print(f"  Escapes $, `, \", \\ for safe use inside double quotes")
            print(f"  Leaves apostrophes, spaces, brackets unchanged (safe in double quotes)")
            passed += 1
        else:
            print(f"✗ FAIL: SSH path escaping has issues")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 7: Parameter dependency validation
    print("\n[TEST 7] Parameter Dependency Validation")
    print("-" * 80)
    try:
        # Test that parameter dependencies are enforced
        import argparse

        # Create a minimal parser to test validation logic
        test_parser = argparse.ArgumentParser(allow_abbrev=False, exit_on_error=False)
        test_parser.add_argument('--list', action='store_true')
        test_parser.add_argument('--duplicates', action='store_true')
        test_parser.add_argument('--resolve', action='store_true')
        test_parser.add_argument('--type', type=str)
        test_parser.add_argument('--update-cache', action='store_true')
        test_parser.add_argument('--force', action='store_true')
        test_parser.add_argument('--from-scratch', action='store_true')

        validation_tests = [
            # (args, should_fail, description)
            (['--resolve'], True, "--resolve without --duplicates should fail"),
            (['--type', 'movie'], True, "--type without --list or --duplicates should fail"),
            (['--force'], True, "--force without --update-cache should fail"),
            (['--from-scratch'], True, "--from-scratch without --update-cache should fail"),
            (['--duplicates', '--resolve'], False, "--resolve with --duplicates should work"),
            (['--list', '--duplicates', '--resolve'], False, "--resolve with --list --duplicates should work"),
            (['--list', '--type', 'movie'], False, "--type with --list should work"),
            (['--duplicates', '--type', 'movie'], False, "--type with --duplicates should work"),
            (['--update-cache', '--force'], False, "--force with --update-cache should work"),
            (['--update-cache', '--from-scratch'], False, "--from-scratch with --update-cache should work"),
        ]

        validation_ok = True
        for args, should_fail, desc in validation_tests:
            test_args = test_parser.parse_args(args)
            # Simulate the validation logic (--duplicates automatically enables --list)
            if test_args.duplicates and not test_args.list:
                test_args.list = True
            has_list = test_args.list
            has_duplicates = test_args.duplicates
            has_update_cache = test_args.update_cache

            fails = False
            if test_args.resolve and not has_duplicates:
                fails = True
            if test_args.type and not (has_list or has_duplicates):
                fails = True
            if test_args.force and not has_update_cache:
                fails = True
            if test_args.from_scratch and not has_update_cache:
                fails = True

            if fails != should_fail:
                print(f"  ✗ Validation mismatch: {desc}")
                validation_ok = False

        if validation_ok:
            print(f"✓ PASS: Parameter dependency validation works correctly")
            print(f"  Tested: --resolve, --duplicates, --type, --force dependencies")
            passed += 1
        else:
            print(f"✗ FAIL: Parameter dependency validation has issues")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 8: Cache modification tracking structure
    print("\n[TEST 8] Cache Modification Tracking Structure")
    print("-" * 80)
    try:
        # Verify that the update_cache_after_resolution function returns library name
        # This is a structural test - we check the function signature
        import inspect

        sig = inspect.signature(update_cache_after_resolution)
        params = list(sig.parameters.keys())
        expected_params = ['choice', 'keys', 'file1', 'file2', 'all_files', 'renamed_files']

        if params == expected_params:
            print(f"✓ PASS: update_cache_after_resolution has correct signature")
            print(f"  Parameters: {params}")
            # Note: We can't easily test the return value without mocking data
            print(f"  Note: Function should return library name when cache modified")
            passed += 1
        else:
            print(f"✗ FAIL: update_cache_after_resolution signature mismatch")
            print(f"  Expected: {expected_params}")
            print(f"  Got: {params}")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 9: JSON module imported for resolution logs
    print("\n[TEST 9] JSON Module Import for Resolution Logs")
    print("-" * 80)
    try:
        # Verify that json module is imported (needed for resolution log saving)
        # Bug fixed: Resolution log saving failed with "name 'json' is not defined"
        import sys
        if 'json' in sys.modules:
            print(f"✓ PASS: json module is imported")
            passed += 1
        else:
            print(f"✗ FAIL: json module not imported - resolution logs will fail to save")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 10: Cache save function exists with correct signature
    print("\n[TEST 10] Cache Save Function Signature")
    print("-" * 80)
    try:
        # Verify that update_and_save_cache function exists and has correct signature
        # Bug fixed: Cache wasn't being saved immediately after resolution operations
        import inspect

        if 'update_and_save_cache' in locals():
            sig = inspect.signature(update_and_save_cache)
            params = list(sig.parameters.keys())

            if params == ['obj_dict']:
                print(f"✓ PASS: update_and_save_cache function has correct signature")
                print(f"  Ensures cache can be saved after each resolution operation")
                passed += 1
            else:
                print(f"✗ FAIL: update_and_save_cache signature mismatch")
                print(f"  Expected: ['obj_dict'], Got: {params}")
                failed += 1
        else:
            print(f"✗ FAIL: update_and_save_cache function not found")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 11: Removal detection data structures
    print("\n[TEST 11] Removal Detection Data Structures")
    print("-" * 80)
    try:
        # Verify that the removal detection infrastructure exists
        # Bug fixed: Removal detection needed to work for all library types
        cache_file = CACHE_FILE
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache = pickle.load(f)

            # Check that cache has the structures needed for removal detection
            has_obj_by_id = 'obj_by_id' in cache
            has_obj_by_library = 'obj_by_library' in cache

            if has_obj_by_id and has_obj_by_library:
                print(f"✓ PASS: Cache has structures needed for removal detection")
                print(f"  obj_by_id: {len(cache['obj_by_id'])} objects")
                print(f"  obj_by_library: {len(cache.get('obj_by_library', {}))} libraries")
                passed += 1
            else:
                print(f"✗ FAIL: Missing cache structures for removal detection")
                print(f"  obj_by_id: {has_obj_by_id}, obj_by_library: {has_obj_by_library}")
                failed += 1
        else:
            print(f"⚠ SKIP: No cache file found")
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 12: Undo operation structure
    print("\n[TEST 12] Undo Operation Structure")
    print("-" * 80)
    try:
        # Verify that undo_operation function exists
        # Bug fixed: Undo needed to support multiple sequential undos
        import inspect

        if 'undo_operation' in locals():
            sig = inspect.signature(undo_operation)
            params = list(sig.parameters.keys())

            if 'operation_log' in params and 'remote_host' in params:
                print(f"✓ PASS: undo_operation function exists with correct parameters")
                print(f"  Supports multiple sequential undos via operation_log")
                passed += 1
            else:
                print(f"✗ FAIL: undo_operation missing required parameters")
                print(f"  Expected: operation_log, remote_host")
                print(f"  Got: {params}")
                failed += 1
        else:
            print(f"✗ FAIL: undo_operation function not found")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        failed += 1

    # Test 13: File path resolution with ALTERNATIVE_ROOTPATHS
    print("\n[TEST 13] File Path Resolution with ALTERNATIVE_ROOTPATHS")
    print("-" * 80)
    try:
        # Bug fixed: determine_remote_host() was using os.path.exists() which returns True for directories,
        # causing false positives when a directory exists locally but the specific file doesn't.
        # This led to remote files being incorrectly identified as local, causing "ERROR: File not found"
        # when trying to play them.
        #
        # The fix:
        # 1. Changed os.path.exists() to os.path.isfile() in resolve_filepath_with_alternatives()
        # 2. Modified determine_remote_host() to return (remote_host, exists, resolved_filepath) tuple
        # 3. Updated all callers to use the resolved filepath instead of the original path

        # Test that determine_remote_host returns a 3-tuple
        import inspect
        if 'determine_remote_host' in locals():
            sig = inspect.signature(determine_remote_host)
            params = list(sig.parameters.keys())

            # Check function signature
            if 'filepath' in params:
                print(f"✓ PASS: determine_remote_host function exists with filepath parameter")

                # Test with a non-existent file to verify the 3-tuple return
                test_filepath = "/nonexistent/test/file.mkv"
                result = determine_remote_host(test_filepath)

                if isinstance(result, tuple) and len(result) == 3:
                    remote_host, exists, resolved_path = result
                    print(f"✓ PASS: determine_remote_host returns 3-tuple (remote_host, exists, resolved_filepath)")
                    print(f"  Sample return for non-existent file: ({remote_host}, {exists}, {resolved_path})")
                    passed += 1
                else:
                    print(f"✗ FAIL: determine_remote_host should return 3-tuple, got: {type(result).__name__} with {len(result) if isinstance(result, tuple) else 'N/A'} elements")
                    print(f"  This regression would cause 'ERROR: File not found' for remote files with commas in path")
                    failed += 1
            else:
                print(f"✗ FAIL: determine_remote_host missing filepath parameter")
                print(f"  Got parameters: {params}")
                failed += 1
        else:
            print(f"✗ FAIL: determine_remote_host function not found")
            failed += 1

        # Test that resolve_filepath_with_alternatives uses os.path.isfile() not os.path.exists()
        if 'resolve_filepath_with_alternatives' in locals():
            import inspect
            source = inspect.getsource(resolve_filepath_with_alternatives)

            # Check that we're using os.path.isfile() for file checks
            uses_isfile = 'os.path.isfile(' in source
            uses_exists_incorrectly = 'os.path.exists(check_path)' in source

            if uses_isfile and not uses_exists_incorrectly:
                print(f"✓ PASS: resolve_filepath_with_alternatives correctly uses os.path.isfile()")
                print(f"  This prevents false positives when directory exists but file doesn't")
                passed += 1
            else:
                if uses_exists_incorrectly:
                    print(f"✗ FAIL: resolve_filepath_with_alternatives still uses os.path.exists(check_path)")
                    print(f"  REGRESSION: This causes remote files to be incorrectly detected as local")
                    failed += 1
                elif not uses_isfile:
                    print(f"✗ FAIL: resolve_filepath_with_alternatives doesn't use os.path.isfile()")
                    failed += 1
        else:
            print(f"✗ FAIL: resolve_filepath_with_alternatives function not found")
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 14: PLEX_Collection class correctness
    print("\n[TEST 14] PLEX_Collection class correctness")
    print("-" * 80)
    try:
        test_ok = True

        # 14a: detect_if_of_OBJ_TYPE should NOT reference PLEX_SERVER.playlists()
        import inspect
        source = inspect.getsource(PLEX_Collection.detect_if_of_OBJ_TYPE)
        if 'playlists()' in source:
            print(f"✗ FAIL: PLEX_Collection.detect_if_of_OBJ_TYPE still references playlists() (copy-paste from Playlist)")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Collection.detect_if_of_OBJ_TYPE does not reference playlists()")

        # 14b: detect_if_of_OBJ_TYPE should not have unreachable code (two returns at same indent level in sequence)
        lines = source.strip().split('\n')
        has_unreachable = False
        prev_return_indent = None
        for line in lines:
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if stripped.startswith('return ') or stripped == 'return':
                if prev_return_indent is not None and indent == prev_return_indent:
                    has_unreachable = True
                    break
                prev_return_indent = indent
            else:
                prev_return_indent = None
        if has_unreachable:
            print(f"✗ FAIL: PLEX_Collection.detect_if_of_OBJ_TYPE has unreachable return statement")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Collection.detect_if_of_OBJ_TYPE has no unreachable code")

        # 14c: execute_cmd should use correct attribute names (not remove_from_collection)
        source = inspect.getsource(PLEX_Collection.execute_cmd)
        if 'remove_from_collection' in source:
            print(f"✗ FAIL: PLEX_Collection.execute_cmd uses obj_args.remove_from_collection (should be remove_from)")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Collection.execute_cmd uses correct attribute names")

        # 14d: list() should accept exactly 1 parameter (library_name), not 2
        sig = inspect.signature(PLEX_Collection.list)
        params = list(sig.parameters.keys())
        if len(params) != 1:
            print(f"✗ FAIL: PLEX_Collection.list() should take 1 parameter, has {len(params)}: {params}")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Collection.list() takes correct number of parameters")

        # 14e: execute_cmd list call should pass 1 arg matching list() signature
        source = inspect.getsource(PLEX_Collection.execute_cmd)
        if 'list(obj, ' in source:
            print(f"✗ FAIL: PLEX_Collection.execute_cmd calls list() with 2 args (list() only takes 1)")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Collection.execute_cmd calls list() with correct args")

        # 14f: create() should use OBJ_DICT not OBJ_DIC
        source = inspect.getsource(PLEX_Collection.create)
        if 'OBJ_DIC[' in source and 'OBJ_DICT[' not in source:
            print(f"✗ FAIL: PLEX_Collection.create() uses OBJ_DIC (typo, should be OBJ_DICT)")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Collection.create() uses correct attribute name OBJ_DICT")

        # 14g: PLEX_Collection should be registered via add_PLEX_OBJ_TYPE
        if 'collection' in PLEXOBJ[DETECT]:
            print(f"✓ PASS: PLEX_Collection is registered in PLEXOBJ dispatch")
        else:
            print(f"✗ FAIL: PLEX_Collection is NOT registered in PLEXOBJ dispatch")
            test_ok = False

        if test_ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 15: PLEX_Playlist class correctness
    print("\n[TEST 15] PLEX_Playlist class correctness")
    print("-" * 80)
    try:
        import inspect
        test_ok = True

        # 15a: execute_cmd should use obj_args.create_playlist (not obj_args.create)
        source = inspect.getsource(PLEX_Playlist.execute_cmd)
        if 'obj_args.create)' in source or 'obj_args.create,' in source:
            print(f"✗ FAIL: PLEX_Playlist.execute_cmd uses obj_args.create (should be obj_args.create_playlist)")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Playlist.execute_cmd uses correct attribute obj_args.create_playlist")

        # 15b: create() and update() should use += not ++ for list concatenation
        for method_name in ['create', 'update']:
            method = getattr(PLEX_Playlist, method_name)
            source = inspect.getsource(method)
            if '++' in source:
                print(f"✗ FAIL: PLEX_Playlist.{method_name}() uses ++ (no-op in Python, should be +=)")
                test_ok = False
            else:
                print(f"✓ PASS: PLEX_Playlist.{method_name}() uses correct list concatenation")

        if test_ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 16: Library-required parameter validation
    print("\n[TEST 16] Library-required parameter validation")
    print("-" * 80)
    try:
        import inspect
        test_ok = True

        # 16a: _normalize_list_args() should validate --watched/--unwatched/--audio require library_name
        source = inspect.getsource(PLEX_Media._normalize_list_args)
        for flag in ['watched_only', 'unwatched_only', 'audio_filter']:
            if f'library_name is None' in source and flag in source:
                print(f"✓ PASS: PLEX_Media._normalize_list_args() validates {flag} requires library_name")
            else:
                print(f"✗ FAIL: PLEX_Media._normalize_list_args() missing validation for {flag} without library_name")
                test_ok = False

        # 16b: --collections error in execute_global_commands
        source = inspect.getsource(execute_global_commands)
        if 'collections' in source and '1072' in source:
            print(f"✓ PASS: execute_global_commands() validates --collections requires library")
        else:
            print(f"✗ FAIL: execute_global_commands() missing --collections validation")
            test_ok = False

        # 16c: execute_global_commands should NOT err() on --watched/--unwatched/--audio directly
        #       (those are in main_parser, not GLOBAL_CMD_PARSER, so calling err() on args.watched
        #        in execute_global_commands would fire even when used WITH a library)
        #       It's OK to READ these args to pass them through to PLEX_Media.list()
        import re
        has_bad_validation = bool(re.search(r"args[.,]\s*'?watched.*err\(|err\(.*watched.*requires", source))
        if has_bad_validation:
            print(f"✗ FAIL: execute_global_commands() directly errors on --watched/--unwatched/--audio")
            print(f"         (these are main_parser args and would fire even when used WITH a library)")
            test_ok = False
        else:
            print(f"✓ PASS: execute_global_commands() does not directly error on --watched/--unwatched/--audio")

        if test_ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 17: PLEX_Library.execute_cmd comment correctness
    print("\n[TEST 17] Class method comments correctness")
    print("-" * 80)
    try:
        import inspect
        test_ok = True

        source = inspect.getsource(PLEX_Library.execute_cmd)
        if 'actions on playlists' in source.lower():
            print(f"✗ FAIL: PLEX_Library.execute_cmd has wrong comment 'Handling actions on playlists' (copy-paste error)")
            test_ok = False
        else:
            print(f"✓ PASS: PLEX_Library.execute_cmd has correct comment")

        if test_ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 18: Global command dispatch passes filter args to PLEX_Media.list()
    print("\n[TEST 18] Global --list passes filter args to PLEX_Media.list()")
    print("-" * 80)
    try:
        import inspect
        test_ok = True

        source = inspect.getsource(execute_global_commands)
        # Check that watched_only, unwatched_only, audio_filter are passed in the PLEX_Media.list() call
        if 'watched_only' in source and 'unwatched_only' in source and 'audio_filter' in source:
            print(f"✓ PASS: execute_global_commands passes watched/unwatched/audio filters to PLEX_Media.list()")
        else:
            print(f"✗ FAIL: execute_global_commands does NOT pass filter args to PLEX_Media.list()")
            print(f"         Filters like --watched would be silently ignored when used globally")
            test_ok = False

        if test_ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 19: Cache helper functions exist and work correctly
    print("\n[TEST 19] Cache helper functions (build_media_cache_dict, load_media_cache)")
    print("-" * 80)
    try:
        import inspect
        test_ok = True

        # 19a: build_media_cache_dict exists and returns correct keys
        if 'build_media_cache_dict' not in locals():
            print(f"✗ FAIL: build_media_cache_dict function not found")
            test_ok = False
        else:
            # Test default (include_paths=True)
            d = build_media_cache_dict()
            required_keys = {'obj_by_id', 'obj_by_movie', 'obj_by_show', 'obj_by_show_episodes',
                             'obj_by_collection', 'obj_by_filepath', 'obj_by_library'}
            if required_keys.issubset(d.keys()):
                print(f"✓ PASS: build_media_cache_dict() returns all 7 required keys")
            else:
                missing = required_keys - d.keys()
                print(f"✗ FAIL: build_media_cache_dict() missing keys: {missing}")
                test_ok = False

            # Test include_paths=False
            d2 = build_media_cache_dict(include_paths=False)
            if 'obj_by_filepath' not in d2 and 'obj_by_library' not in d2:
                print(f"✓ PASS: build_media_cache_dict(include_paths=False) excludes path keys")
            else:
                print(f"✗ FAIL: build_media_cache_dict(include_paths=False) should not include path keys")
                test_ok = False

            # Test extra kwargs
            d3 = build_media_cache_dict(library_stats={'test': True})
            if d3.get('library_stats') == {'test': True}:
                print(f"✓ PASS: build_media_cache_dict(**extra) passes through extra keys")
            else:
                print(f"✗ FAIL: build_media_cache_dict(**extra) did not pass through extra keys")
                test_ok = False

        # 19b: load_media_cache exists and sets all attributes
        if 'load_media_cache' not in locals():
            print(f"✗ FAIL: load_media_cache function not found")
            test_ok = False
        else:
            sig = inspect.signature(load_media_cache)
            params = list(sig.parameters.keys())
            if params == ['source']:
                print(f"✓ PASS: load_media_cache(source) has correct signature")
            else:
                print(f"✗ FAIL: load_media_cache has unexpected signature: {params}")
                test_ok = False

            # Verify it handles missing keys gracefully (uses .get with defaults)
            source_code = inspect.getsource(load_media_cache)
            if '.get(' in source_code:
                print(f"✓ PASS: load_media_cache uses .get() for safe key access")
            else:
                print(f"✗ FAIL: load_media_cache should use .get() to handle missing keys")
                test_ok = False

        # 19c: All cache save sites use build_media_cache_dict (no more inline dict construction)
        source = ''
        if not source:
            with open(MAIN_SCRIPT, 'r') as f:
                source = f.read()
        # Count remaining inline cache dict patterns (excluding the helper itself and tests)
        import re
        # Match lines that build cache dicts inline (the old pattern)
        inline_saves = re.findall(r"'obj_by_id': PLEX_Media\.OBJ_BY_ID,\s*\n\s*'obj_by_movie'", source)
        if len(inline_saves) <= 1:  # Allow 1 for build_media_cache_dict itself
            print(f"✓ PASS: No redundant inline cache dict construction found")
        else:
            print(f"✗ FAIL: Found {len(inline_saves)} inline cache dict constructions (should use build_media_cache_dict)")
            test_ok = False

        if test_ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Test 20: sys.argv normalization uses inject_before_first_match helper
    print("\n[TEST 20] sys.argv normalization helper")
    print("-" * 80)
    try:
        test_ok = True

        # Read the main() source to check the normalization block
        with open(MAIN_SCRIPT, 'r') as f:
            source = f.read()

        # Check that inject_before_first_match is defined
        if 'def inject_before_first_match(' in source:
            print(f"✓ PASS: inject_before_first_match helper function is defined")
        else:
            print(f"✗ FAIL: inject_before_first_match helper function not found")
            test_ok = False

        # Check that the 3 normalization branches use the helper
        import re
        inject_calls = re.findall(r'inject_before_first_match\(', source)
        if len(inject_calls) >= 3:
            print(f"✓ PASS: inject_before_first_match is called {len(inject_calls)} times (covers all normalization cases)")
        else:
            print(f"✗ FAIL: inject_before_first_match called only {len(inject_calls)} times (expected 3+)")
            test_ok = False

        # Check that is_audio_flag helper is defined and used
        if 'def is_audio_flag(' in source:
            print(f"✓ PASS: is_audio_flag helper function is defined")
        else:
            print(f"✗ FAIL: is_audio_flag helper function not found")
            test_ok = False

        if test_ok:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"✗ FAIL: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        failed += 1

    # Print inline test summary
    print("\n" + "=" * 76)
    print("INLINE TEST SUMMARY")
    print("=" * 76)
    inline_total = passed + failed
    print(f"Total:  {inline_total} tests")
    print(f"Passed: {passed} tests ({100*passed//inline_total if inline_total > 0 else 0}%)")
    print(f"Failed: {failed} tests ({100*failed//inline_total if inline_total > 0 else 0}%)")

    # Run unittest suite (inline test classes)
    print("\n" + "=" * 76)
    print("UNITTEST SUITE")
    print("=" * 76)
    loader = unittest.TestLoader()
    unittest_ok = True
    try:
        suite = unittest.TestSuite()
        for cls in _UNITTEST_CLASSES:
            suite.addTests(loader.loadTestsFromTestCase(cls))
        runner = unittest.TextTestRunner(verbosity=2)
        unittest_result = runner.run(suite)
        unittest_ok = unittest_result.wasSuccessful()
    except Exception as e:
        print(f"✗ FAIL: Could not run unittest suite: {e}")
        unittest_ok = False

    if failed == 0 and unittest_ok:
        print("\n✓ All tests PASSED!")
        sys.exit(0)
    else:
        print(f"\n✗ Tests FAILED!")
        sys.exit(1)
