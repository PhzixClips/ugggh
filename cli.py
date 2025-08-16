#!/usr/bin/env python3
"""
Anime AI Autoposter - CLI Runner
"""

import os
import time
from pathlib import Path
import sys

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from data.database import DatabaseManager
from media.media_processor import MediaProcessor
from api.youtube_client import YouTubeAPIClient
from utils.logging import setup_logging, log_upgrade

# --- Directory Constants ---
VIDEOS_DIR = Path('videos')
INBOX_DIR = VIDEOS_DIR / 'inbox'
PROCESSED_DIR = VIDEOS_DIR / 'processed'
OUTBOX_DIR = VIDEOS_DIR / 'outbox'
SUPPORTED_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv']

def process_videos():
    """
    The main processing loop for finding, preprocessing, and uploading videos.
    """
    db_manager = DatabaseManager()
    media_processor = MediaProcessor()
    youtube_client = YouTubeAPIClient()

    log_upgrade("Scanning for new videos in inbox...")

    video_files = [f for f in INBOX_DIR.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]

    if not video_files:
        log_upgrade("No new videos found.")
        return

    for video_path in video_files:
        try:
            log_upgrade(f"Processing video: {video_path.name}")

            # 1. Check if already processed
            if db_manager.is_video_uploaded(str(video_path.resolve())):
                log_upgrade(f"Skipping '{video_path.name}', already uploaded.")
                continue

            # 2. Preprocess the video
            processed_video_path = OUTBOX_DIR / f"processed_{video_path.name}"
            log_upgrade(f"Preprocessing '{video_path.name}'...")
            success = media_processor.preprocess_video(video_path, processed_video_path)

            if not success:
                log_upgrade(f"Failed to preprocess '{video_path.name}'. Skipping.")
                db_manager.log_upload(
                    source_filepath=str(video_path.resolve()),
                    platform='youtube',
                    status='preprocess_failed',
                    details='FFmpeg preprocessing failed.'
                )
                continue

            # 3. Upload to YouTube
            log_upgrade(f"Uploading '{processed_video_path.name}' to YouTube...")
            title = video_path.stem  # Use the filename (without extension) as the title
            description = f"AI-generated anime clip: {title}.\n#ai #anime #aianimation"
            tags = ['ai', 'anime', 'animation', 'shorts']
            category_id = '1' # Film & Animation

            upload_response = youtube_client.upload_video(
                file_path=str(processed_video_path),
                title=title,
                description=description,
                tags=tags,
                category_id=category_id,
                privacy_status='private' # Change to 'public' for live uploads
            )

            # 4. Log and cleanup
            if upload_response and 'id' in upload_response:
                video_id = upload_response['id']
                log_upgrade(f"Successfully uploaded '{video_path.name}' to YouTube with ID: {video_id}")
                db_manager.log_upload(
                    source_filepath=str(video_path.resolve()),
                    platform='youtube',
                    status='success',
                    video_id_on_platform=video_id
                )
                # Move original video to processed directory
                video_path.rename(PROCESSED_DIR / video_path.name)
                log_upgrade(f"Moved '{video_path.name}' to processed folder.")
            else:
                log_upgrade(f"Failed to upload '{video_path.name}'.")
                db_manager.log_upload(
                    source_filepath=str(video_path.resolve()),
                    platform='youtube',
                    status='upload_failed',
                    details='The upload process did not return a valid video ID.'
                )

            # Clean up the processed file from the outbox
            if processed_video_path.exists():
                processed_video_path.unlink()

        except Exception as e:
            log_upgrade(f"An unexpected error occurred while processing '{video_path.name}': {e}")
            # Log this as a generic failure
            db_manager.log_upload(
                source_filepath=str(video_path.resolve()),
                platform='youtube',
                status='error',
                details=str(e)
            )
            continue


def main():
    """Main CLI entry point"""
    setup_logging()
    log_upgrade("--- Anime AI Autoposter CLI Initialized ---")

    # Ensure directories exist
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

    # For now, we will run once. The plan mentions a scheduler for later.
    process_videos()

    log_upgrade("--- Processing complete. ---")


if __name__ == '__main__':
    main()
