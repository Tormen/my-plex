"""One-time script: normalize genres in existing cache to canonical English names.

Run once after updating my-plex.py with _normalize_genres().
Future --update-cache runs will store normalized genres automatically.
"""
import pickle, shutil, os

CACHE_FILE = os.path.expanduser('~/.my-plex/cache.pkl')

# Map inline — must match my-plex.py _GENRE_NORM exactly
_GENRE_NORM = {
    'comedy': 'Comedy', 'komödie': 'Comedy', 'komedie': 'Comedy',
    'comédie': 'Comedy', 'comedie': 'Comedy',
    'drama': 'Drama', 'drame': 'Drama',
    'action': 'Action',
    'adventure': 'Adventure', 'abenteuer': 'Adventure', 'aventure': 'Adventure',
    'animation': 'Animation',
    'horror': 'Horror', 'horreur': 'Horror',
    'thriller': 'Thriller',
    'romance': 'Romance', 'liebesfilm': 'Romance', 'romantik': 'Romance',
    'documentary': 'Documentary', 'dokumentarfilm': 'Documentary', 'documentaire': 'Documentary',
    'crime': 'Crime', 'krimi': 'Crime',
    'mystery': 'Mystery', 'mystère': 'Mystery', 'mystere': 'Mystery',
    'family': 'Family', 'familie': 'Family', 'familial': 'Family',
    'history': 'History', 'historie': 'History', 'histoire': 'History',
    'biography': 'Biography', 'biographie': 'Biography',
    'science fiction': 'Science Fiction', 'sci-fi': 'Science Fiction',
    'science-fiction': 'Science Fiction',
    'fantasy': 'Fantasy', 'fantastique': 'Fantasy',
    'music': 'Music', 'musik': 'Music', 'musique': 'Music', 'musical': 'Music',
    'sport': 'Sport', 'sports': 'Sport',
    'war': 'War', 'krieg': 'War', 'guerre': 'War',
    'western': 'Western',
    'suspense': 'Suspense',
    'tv movie': 'TV Movie', 'tv-film': 'TV Movie', 'téléfilm': 'TV Movie',
    'children': 'Children', 'kinder': 'Children',
    'short': 'Short',
    'kids': 'Kids',
    'news': 'News',
}

def _norm(genres):
    return [_GENRE_NORM.get(str(g).lower(), str(g)) for g in (genres or [])]

print(f"Loading cache: {CACHE_FILE}")
with open(CACHE_FILE, 'rb') as f:
    data = pickle.load(f)

objs = data.get('obj_by_id', {})
changed = 0
for obj in objs.values():
    if not isinstance(obj, dict):
        continue
    raw = obj.get('genres')
    if not raw:
        continue
    normalized = _norm(raw)
    if normalized != raw:
        obj['genres'] = normalized
        changed += 1

print(f"Normalized genres in {changed} objects.")

backup = CACHE_FILE + '.bak-genres'
shutil.copy2(CACHE_FILE, backup)
print(f"Backup saved: {backup}")

with open(CACHE_FILE, 'wb') as f:
    pickle.dump(data, f)
print("Cache updated.")
