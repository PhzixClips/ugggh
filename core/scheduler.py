"""
Manages the APScheduler instance for scheduling video posts.
"""

import os
import sys
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.database import DatabaseManager
from api.youtube_client import YouTubeAPIClient
from utils.logging import log_upgrade

class SchedulerManager:
    """A singleton class to manage the APScheduler."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SchedulerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'scheduler'):  # Avoid re-initialization
            self.db_manager = DatabaseManager()
            self.youtube_client = YouTubeAPIClient()
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            self._load_pending_jobs()
            log_upgrade("SchedulerManager initialized and pending jobs loaded.")

    def _execute_post(self, post_id: int):
        """
        The actual job function that gets executed by the scheduler.
        """
        log_upgrade(f"Scheduler executing post ID: {post_id}")
        # Mark as processing
        self.db_manager.update_scheduled_post_status(post_id, 'processing')

        # Retrieve job details from DB
        # Note: get_scheduled_posts returns a list of rows. We need to find our specific post.
        # A get_post_by_id method would be better, but we can filter for now.
        posts = self.db_manager.get_scheduled_posts()
        post_details = next((p for p in posts if p['id'] == post_id), None)

        if not post_details:
            log_upgrade(f"Could not find post details for ID {post_id}. Aborting job.")
            self.db_manager.update_scheduled_post_status(post_id, 'failed')
            return

        try:
            log_upgrade(f"Uploading video: {post_details['video_filepath']}")

            upload_response = self.youtube_client.upload_video(
                file_path=post_details['video_filepath'],
                title=post_details['title'],
                description=post_details['description'],
                tags=post_details['tags'].split(','),
                category_id='1', # Film & Animation
                privacy_status='private'
            )

            if upload_response and 'id' in upload_response:
                youtube_video_id = upload_response['id']
                log_upgrade(f"Successfully uploaded post ID {post_id}. YouTube ID: {youtube_video_id}")
                self.db_manager.update_scheduled_post_status(post_id, 'success', youtube_video_id)
            else:
                log_upgrade(f"Failed to upload post ID {post_id}.")
                self.db_manager.update_scheduled_post_status(post_id, 'failed')

        except Exception as e:
            log_upgrade(f"An error occurred during scheduled upload for post ID {post_id}: {e}")
            self.db_manager.update_scheduled_post_status(post_id, 'failed')

    def add_job(self, video_filepath: str, title: str, description: str, tags: str, scheduled_time: datetime):
        """
        Adds a job to the database and the scheduler.
        """
        # 1. Add to database to get a persistent ID
        post_id = self.db_manager.add_scheduled_post(video_filepath, title, description, tags, scheduled_time)

        if post_id == -1:
            log_upgrade("Failed to save scheduled post to the database.")
            return None

        # 2. Add to the actual scheduler
        try:
            self.scheduler.add_job(
                self._execute_post,
                trigger=DateTrigger(run_date=scheduled_time),
                args=[post_id],
                id=str(post_id),  # Job ID must be a string
                name=f"Post '{title[:20]}...'",
                misfire_grace_time=3600, # If missed, run up to 1 hour late
                replace_existing=True
            )
            log_upgrade(f"Successfully scheduled job for post ID: {post_id} at {scheduled_time}")
            return post_id
        except Exception as e:
            log_upgrade(f"Failed to add job to APScheduler: {e}")
            # Clean up the record we just added to the DB
            # (Requires a delete method in DatabaseManager, for now we leave it as pending)
            return None

    def _load_pending_jobs(self):
        """
        Loads all 'pending' jobs from the database and adds them to the scheduler.
        This ensures persistence across application restarts.
        """
        log_upgrade("Loading pending jobs from database...")
        pending_posts = self.db_manager.get_scheduled_posts(status='pending')
        now = datetime.now()

        for post in pending_posts:
            scheduled_time = post['scheduled_time']
            if scheduled_time < now:
                # The scheduled time is in the past. Mark it as failed.
                log_upgrade(f"Found pending job (ID: {post['id']}) with past schedule time. Marking as failed.")
                self.db_manager.update_scheduled_post_status(post['id'], 'failed')
                continue

            self.scheduler.add_job(
                self._execute_post,
                trigger=DateTrigger(run_date=scheduled_time),
                args=[post['id']],
                id=str(post['id']),
                name=f"Post '{post['title'][:20]}...'",
                misfire_grace_time=3600,
                replace_existing=True
            )
            log_upgrade(f"Loaded pending job ID: {post['id']} for {scheduled_time}")

    def shutdown(self):
        """Shuts down the scheduler."""
        self.scheduler.shutdown()
        log_upgrade("Scheduler has been shut down.")
