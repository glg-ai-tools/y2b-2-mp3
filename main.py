#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube MP3 Batch Tool
Modes:
 1) Single video
 2) Playlist
 3) Batch file

Dependencies:
  • yt-dlp      (pip install yt-dlp)
  • pydub       (pip install pydub)
  • mutagen     (pip install mutagen)
  • ffmpeg must be installed and on your PATH
"""

import os
import re
import json
import subprocess
import logging
import glob
import time
import tempfile
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from pydub import AudioSegment
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Configuration
DOWNLOAD_FOLDER  = os.path.expanduser("~/Downloads/youtube_mp3s")
DEFAULT_CLIP_LEN = 60  # seconds
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Helpers
def sanitize_url(raw: str) -> str:
    """Sanitize a YouTube URL by keeping only necessary query parameters."""
    p = urlparse(raw)
    params = {}
    if 'v' in parse_qs(p.query):   
        params['v'] = parse_qs(p.query)['v'][0]
    if 'list' in parse_qs(p.query): 
        params['list'] = parse_qs(p.query)['list'][0]
    return urlunparse(p._replace(query=urlencode(params)))

def is_youtube_url(url: str) -> bool:
    return bool(re.match(r'^https?://(www\.)?(youtube\.com|youtu\.be)/', url))

def run_ytdlp(cmd: list) -> str:
    logging.info(f"Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logging.error(f"yt-dlp error: {proc.stderr.strip()}")
        return None
    output = proc.stdout.strip().splitlines()
    if not output:
        return None
    filepath = output[-1]
    if filepath.upper() == 'NA':
        logging.error("yt-dlp returned 'NA' for filepath.")
        return None
    return filepath

# Core
def download_mp3(url: str, output_folder: str) -> str:
    """
    Download the audio stream of a YouTube URL as MP3.
    Returns the full path to the downloaded file.
    """
    with tempfile.TemporaryDirectory() as temp_folder:
        template = os.path.join(temp_folder, "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", template,
            url
        ]
        logging.info(f"Running: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logging.error(f"yt-dlp error: {proc.stderr.strip()}")
            return None

        # Find the downloaded file in the temporary folder
        candidates = glob.glob(os.path.join(temp_folder, "*.mp3"))
        if not candidates:
            logging.error("No MP3 found after download.")
            return None

        # Move the file to the output folder
        latest = max(candidates, key=os.path.getmtime)
        final_path = os.path.join(output_folder, os.path.basename(latest))
        os.rename(latest, final_path)
        logging.info(f"Downloaded MP3: {final_path}")
        return final_path

def trim_and_tag(path: str, title: str, artist: str, length: int):
    audio = AudioSegment.from_file(path)
    clipped = audio[: length * 1000]
    clipped.export(path, format="mp3")
    tags = MP3(path, ID3=EasyID3)
    tags["title"] = title
    tags["artist"] = artist
    tags["album"] = "YouTube Batch"
    tags.save()
    logging.info(f"Trimmed & tagged: {path}")

def fetch_metadata(url: str) -> (str, str):
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", "--get-uploader", url],
            capture_output=True, text=True, check=True
        ).stdout.splitlines()
        title = result[0] if result else "Unknown Title"
        artist = result[1] if len(result) > 1 else "Unknown Artist"
    except Exception:
        logging.warning("Metadata fetch failed; using defaults.")
        title, artist = f"Video_{int(time.time())}", "Unknown Artist"  # Use timestamp for uniqueness
    return title, artist

def process_video(raw_url: str, length: int):
    url = sanitize_url(raw_url)
    if not is_youtube_url(url):
        logging.warning(f"Skipping invalid URL: {url}")
        return
    title, artist = fetch_metadata(url)
    logging.info(f"Downloading: '{title}' by {artist}")
    mp3_path = download_mp3(url, DOWNLOAD_FOLDER)
    if not mp3_path or not os.path.exists(mp3_path):
        logging.error(f"Failed to download MP3 for: {url}")
        return
    try:
        trim_and_tag(mp3_path, title, artist, length)
    except Exception as e:
        logging.error(f"Error trimming/tagging {mp3_path}: {e}")

def process_playlist(raw_url: str, length: int):
    url = sanitize_url(raw_url)
    if not is_youtube_url(url):
        logging.warning(f"Skipping invalid playlist URL: {url}")
        return
    try:
        data = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--dump-single-json", url],
            capture_output=True, text=True, check=True
        ).stdout
        pl = json.loads(data)
        entries = pl.get("entries", [])
        logging.info(f"Playlist '{pl.get('title','')}' contains {len(entries)} videos")
        for e in entries:
            try:
                vid = f"https://www.youtube.com/watch?v={e['id']}"
                process_video(vid, length)
            except Exception as e:
                logging.error(f"Error processing video {e['id']}: {e}")
    except Exception as e:
        logging.error(f"Error processing playlist {url}: {e}")

def batch_from_file(file_path: str, length: int):
    if not os.path.isfile(file_path):
        logging.error(f"Batch file not found: {file_path}")
        return
    with open(file_path, "r") as f:
        for line in f:
            link = line.strip()
            if not link:
                continue
            if not is_youtube_url(link):
                logging.warning(f"Skipping invalid URL: {link}")
                continue
            if 'list=' in link:
                process_playlist(link, length)
            else:
                process_video(link, length)

# Main CLI
def main():
    print("YouTube MP3 Batch Tool")
    try:
        clip_len = int(input(f"Clip length seconds (default {DEFAULT_CLIP_LEN}): ").strip())
        if clip_len <= 0:
            raise ValueError("Clip length must be positive.")
    except ValueError:
        clip_len = DEFAULT_CLIP_LEN
        logging.info(f"Using default clip length: {clip_len}s")

    while True:
        mode = input("Mode [1] Video  [2] Playlist  [3] Batch-file [4] Exit: ").strip()
        if mode == '1':
            process_video(input("Video URL: ").strip(), clip_len)
        elif mode == '2':
            process_playlist(input("Playlist URL: ").strip(), clip_len)
        elif mode == '3':
            batch_from_file(input("Path to URL list: ").strip(), clip_len)
        elif mode == '4':
            print("Exiting. Goodbye!")
            break
        else:
            print("Invalid mode. Please try again.")

if __name__ == '__main__':
    main()