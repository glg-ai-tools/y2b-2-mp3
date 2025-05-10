#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube MP3 Batch Tool
Modes:
  1) Single video
  2) Playlist
  3) Batch file input
"""

import os
import re
import json
import subprocess
import logging
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from pydub import AudioSegment

# --- Configuration ---
DOWNLOAD_FOLDER = os.path.expanduser("~/Downloads/youtube_mp3s")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
DEFAULT_CLIP_LENGTH = 60  # seconds

# --- Utilities ---
def is_youtube_url(url):
    return bool(re.match(r'^https?://(www\.)?(youtube\.com|youtu\.be)/', url))

def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (' ', '.', '_')).rstrip()

def run_ytdlp(cmd):
    """Run yt-dlp command, raise on failure, return stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result.stdout.strip()

# --- Core Functions ---
def download_mp3(url):
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--print", "%(filepath)s",
        "-o", os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s"),
        url
    ]
    return run_ytdlp(cmd)

def trim_and_tag(mp3_path, title, artist, clip_length):
    audio = AudioSegment.from_file(mp3_path)
    trimmed = audio[:clip_length * 1000]
    trimmed.export(mp3_path, format="mp3")
    meta = MP3(mp3_path, ID3=EasyID3)
    meta["title"] = title
    meta["artist"] = artist
    meta["album"] = "YouTube Batch"
    meta.save()
    logging.info(f"✅ Trimmed & tagged: {mp3_path}")

def fetch_metadata(url):
    try:
        out = run_ytdlp(["yt-dlp", "--get-title", "--get-uploader", url])
        lines = out.splitlines()
        return (lines[0], lines[1] if len(lines) > 1 else "Unknown Artist")
    except Exception:
        return ("Unknown Title", "Unknown Artist")

def process_video(url, clip_length):
    if not is_youtube_url(url):
        logging.warning(f"Skipping invalid URL: {url}")
        return
    clean = url.split("?")[0]
    logging.info(f"Processing video: {clean}")
    title, artist = fetch_metadata(clean)
    try:
        mp3_path = download_mp3(clean)
        if os.path.exists(mp3_path):
            trim_and_tag(mp3_path, title, artist, clip_length)
        else:
            logging.error(f"MP3 not found at expected path: {mp3_path}")
    except Exception as e:
        logging.error(f"Failed video {clean}: {e}")

def process_playlist(url, clip_length):
    if not is_youtube_url(url):
        logging.warning(f"Skipping invalid playlist URL: {url}")
        return
    logging.info(f"Fetching playlist: {url}")
    try:
        data = run_ytdlp(["yt-dlp", "--flat-playlist", "--dump-single-json", url])
        pl = json.loads(data)
        entries = pl.get("entries", [])
        logging.info(f"Playlist '{pl.get('title','')}' has {len(entries)} videos")
        for entry in entries:
            vurl = f"https://www.youtube.com/watch?v={entry['id']}"
            process_video(vurl, clip_length)
    except Exception as e:
        logging.error(f"Failed playlist {url}: {e}")

def batch_from_file(path, clip_length):
    try:
        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        logging.error(f"Batch file not found: {path}")
        return
    for url in lines:
        if "playlist" in url or "list=" in url:
            process_playlist(url, clip_length)
        else:
            process_video(url, clip_length)

# --- Main CLI ---
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("🎵 YouTube MP3 Batch Tool (yt-dlp)")
    try:
        clip_length = int(input(f"Clip length in seconds (default {DEFAULT_CLIP_LENGTH}): ").strip())
    except ValueError:
        clip_length = DEFAULT_CLIP_LENGTH
    mode = input("Mode [1] Single video  [2] Playlist  [3] Batch file: ").strip()
    if mode == "1":
        url = input("Enter YouTube video URL: ").strip()
        process_video(url, clip_length)
    elif mode == "2":
        url = input("Enter YouTube playlist URL: ").strip()
        process_playlist(url, clip_length)
    elif mode == "3":
        path = input("Enter path to text file with URLs: ").strip()
        batch_from_file(path, clip_length)
    else:
        print("Invalid mode, exiting.")

if __name__ == "__main__":
    main()
