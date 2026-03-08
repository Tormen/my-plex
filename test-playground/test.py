import os
import pickle
from plexapi.server import PlexServer
from datetime import datetime
from pathlib import Path

# Replace with your Plex server URL and token
PLEX_URL = 'https://192-168-192-252.37042a2a68964c6597fc54267ed7a413.plex.direct:32400'
PLEX_TOKEN = '-BfszsiY4sVQ16fsa7yv'
CACHE_FILE = os.path.join(Path.home(), '.plex_media_cache.pkl')

def load_cache():
    # Load the previous cache from file if it exists
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'rb') as f:
            return pickle.load(f)
    return {'media_paths': {}, 'library_timestamps': {}}

def save_cache(media_paths, library_timestamps):
    # Save the current cache to file
    with open(CACHE_FILE, 'wb') as f:
        pickle.dump({'media_paths': media_paths, 'library_timestamps': library_timestamps}, f)

def check_library_updates():
    # Connect to the Plex server and check each library's updatedAt timestamp
    plex = PlexServer(PLEX_URL, PLEX_TOKEN)
    current_library_timestamps = {}

    # Collect current timestamps for each library
    for library in plex.library.sections():
        current_library_timestamps[library.title] = library.updatedAt
    
    return current_library_timestamps

def get_movie_library_paths(library):
    # Retrieve MediaPart IDs and file paths for a Movie library
    media_paths = {}
    for item in library.all():
        for media in item.media:
            for part in media.parts:
                media_paths[part.id] = part.file
    return media_paths

def get_show_library_paths(library):
    # Retrieve MediaPart IDs and file paths for a Show library (includes seasons and episodes)
    media_paths = {}
    for show in library.all():
        for season in show.seasons():
            for episode in season.episodes():
                for media in episode.media:
                    for part in media.parts:
                        media_paths[part.id] = part.file
    return media_paths

def cache_media_paths():
    # Load the previous cache
    cache = load_cache()
    old_media_paths = cache['media_paths']
    old_library_timestamps = cache['library_timestamps']
    
    # Get the current library timestamps
    current_library_timestamps = check_library_updates()
    
    # Track any changes to the libraries
    updated_media_paths = old_media_paths.copy()  # Start with existing media paths

    for library_name, current_timestamp in current_library_timestamps.items():
        old_timestamp = old_library_timestamps.get(library_name)

        # If the library has been updated since the last run
        if current_timestamp != old_timestamp:
            print(f"Library '{library_name}' has changed since last run. Updating cache for this library...")

            # Fetch the library section and update only this library's media paths
            plex = PlexServer(PLEX_URL, PLEX_TOKEN)
            library = plex.library.section(library_name)

            # Differentiate between Movie and Show libraries
            if library.type == 'movie':
                updated_media_paths.update(get_movie_library_paths(library))
            elif library.type == 'show':
                updated_media_paths.update(get_show_library_paths(library))

    # Save the updated cache with the current timestamps
    save_cache(updated_media_paths, current_library_timestamps)
    
    return updated_media_paths

# Example usage
print(f"CACHE_FILE='{CACHE_FILE}'")
media_paths = cache_media_paths()
for media_id, filepath in media_paths.items():
    print(f"MediaPart ID: {media_id}, Filepath: {filepath}")
