#!/usr/bin/env python3
"""
Server-side video metadata collection script

Runs on Plex server to collect MKV/MP4/AVI metadata for ALL video files.
Outputs JSON file with container durations for integration into local cache.

Usage:
    ./collect_video_metadata.py --file-list /path/to/files.txt --output metadata.json

File list format (one path per line):
    /Volumes/2/watch.v/movies.fr/Movie (2023)/movie.mkv
    /Volumes/2/watch.v/movies.en/Another Movie (2024)/movie.mkv
"""

import sys
import json
import struct
import subprocess
from datetime import datetime
from pathlib import Path

def get_mkv_header_duration(filepath):
    """Read duration from MKV file header

    Returns:
        Duration in minutes (float) or None if unable to read
    """
    try:
        # Read first 4096 bytes of file
        with open(filepath, 'rb') as f:
            header_data = f.read(4096)

        # Search for duration element in MKV header
        # MKV duration is stored as a float64 in milliseconds
        # The EBML ID for Duration is 0x4489 (2 bytes: 0x44, 0x89)
        duration_id = b'\x44\x89'
        pos = header_data.find(duration_id)

        if pos == -1:
            return None

        # Skip ID (2 bytes) and size byte(s)
        pos += 2  # Skip ID
        size_byte = header_data[pos]
        pos += 1  # Skip size byte

        # If size indicates 8 bytes (0x88), read the float64 value
        if size_byte == 0x88 and pos + 8 <= len(header_data):
            # Read 8 bytes as big-endian float64
            duration_ms = struct.unpack('>d', header_data[pos:pos+8])[0]
            duration_min = duration_ms / 1000.0 / 60.0  # Convert ms to minutes
            return duration_min
        else:
            return None

    except Exception as e:
        return None

def get_mp4_duration(filepath):
    """Read duration from MP4 file using ffprobe

    Returns:
        Duration in minutes (float) or None if unable to read
    """
    try:
        # Try full path first (for SSH sessions where PATH may not include /usr/local/bin)
        ffprobe_cmd = '/usr/local/bin/ffprobe'
        result = subprocess.run(
            [ffprobe_cmd, '-v', 'error', '-show_entries',
             'format=duration', '-of',
             'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            duration_sec = float(result.stdout.strip())
            return duration_sec / 60.0
        return None
    except Exception:
        return None

def get_video_metadata(filepath):
    """Get metadata for a video file

    Returns:
        dict with metadata or None if unable to read
    """
    path = Path(filepath)
    if not path.exists():
        return None

    filesize = path.stat().st_size
    ext = path.suffix.lower()

    container_duration = None

    if ext == '.mkv':
        container_duration = get_mkv_header_duration(filepath)
    elif ext in ['.mp4', '.m4v']:
        container_duration = get_mp4_duration(filepath)
    elif ext == '.avi':
        # AVI duration can also be read via ffprobe
        container_duration = get_mp4_duration(filepath)

    if container_duration is None:
        return None

    return {
        'container_duration': container_duration,
        'filesize': filesize,
        'scanned_at': datetime.now().isoformat(),
        'file_type': ext[1:]  # Remove leading dot
    }

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Collect video file metadata')
    parser.add_argument('--file-list', required=True, help='Text file with one filepath per line')
    parser.add_argument('--output', required=True, help='Output JSON file')
    parser.add_argument('--progress', type=int, default=100, help='Show progress every N files')

    args = parser.parse_args()

    # Read file list
    with open(args.file_list, 'r') as f:
        filepaths = [line.strip() for line in f if line.strip()]

    print(f"Collecting metadata for {len(filepaths)} files...")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    metadata = {}
    processed = 0
    errors = 0

    for filepath in filepaths:
        try:
            file_meta = get_video_metadata(filepath)
            if file_meta:
                metadata[filepath] = file_meta
            else:
                errors += 1
        except Exception as e:
            errors += 1

        processed += 1
        if processed % args.progress == 0:
            print(f"  Progress: {processed}/{len(filepaths)} ({100*processed/len(filepaths):.1f}%) - {len(metadata)} successful, {errors} errors")

    # Write output
    with open(args.output, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total processed: {processed}")
    print(f"Successful: {len(metadata)}")
    print(f"Errors: {errors}")
    print(f"Output written to: {args.output}")

if __name__ == '__main__':
    main()
