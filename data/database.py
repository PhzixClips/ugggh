import sqlite3
from pathlib import Path
from datetime import datetime

DB_FILE = Path(__file__).parent / 'autoposter.db'

class DatabaseManager:
    """Manages the SQLite database for the autoposter."""

    def __init__(self, db_file: Path = DB_FILE):
        """
        Initializes the DatabaseManager.

        Args:
            db_file: The path to the SQLite database file.
        """
        self.db_file = db_file
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Establishes a connection to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
            self.conn.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            raise

    def _create_tables(self):
        """Creates the necessary database tables if they don't already exist."""
        if not self.conn:
            return

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_filepath TEXT NOT NULL UNIQUE,
                    platform TEXT NOT NULL,
                    video_id_on_platform TEXT,
                    upload_timestamp TIMESTAMP NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_filepath TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    tags TEXT,
                    scheduled_time TIMESTAMP NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    youtube_video_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error creating tables: {e}")

    def log_upload(self, source_filepath: str, platform: str, status: str, video_id: str = None, details: str = None) -> int:
        """
        Logs a video upload attempt in the database.

        Args:
            source_filepath: The absolute path to the source video file.
            platform: The platform the video was uploaded to (e.g., 'youtube').
            status: The status of the upload ('success', 'failure').
            video_id: The ID of the video on the platform after a successful upload.
            details: Any additional details, such as error messages.

        Returns:
            The ID of the newly created log entry.
        """
        if not self.conn:
            return -1

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO uploads (source_filepath, platform, video_id_on_platform, upload_timestamp, status, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (str(source_filepath), platform, video_id, datetime.now(), status, details))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Error logging upload: {e}")
            return -1

    def is_video_uploaded(self, source_filepath: str) -> bool:
        """
        Checks if a video has already been successfully uploaded.

        Args:
            source_filepath: The absolute path to the source video file.

        Returns:
            True if the video has a 'success' status in the log, False otherwise.
        """
        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 1 FROM uploads WHERE source_filepath = ? AND status = 'success'
            """, (str(source_filepath),))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            print(f"Error checking upload status: {e}")
            return False

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def add_scheduled_post(self, video_filepath: str, title: str, description: str, tags: str, scheduled_time: datetime) -> int:
        """Adds a new post to the schedule."""
        if not self.conn:
            return -1
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO scheduled_posts (video_filepath, title, description, tags, scheduled_time)
                VALUES (?, ?, ?, ?, ?)
            """, (video_filepath, title, description, tags, scheduled_time))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Error adding scheduled post: {e}")
            return -1

    def get_scheduled_posts(self, status: str = None):
        """
        Retrieves scheduled posts from the database.

        Args:
            status: Optional filter to get posts with a specific status (e.g., 'pending').

        Returns:
            A list of rows representing the scheduled posts.
        """
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            query = "SELECT * FROM scheduled_posts"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
            query += " ORDER BY scheduled_time ASC"

            cursor.execute(query, params)
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting scheduled posts: {e}")
            return []

    def update_scheduled_post_status(self, post_id: int, status: str, youtube_video_id: str = None):
        """Updates the status of a scheduled post."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE scheduled_posts
                SET status = ?, youtube_video_id = ?
                WHERE id = ?
            """, (status, youtube_video_id, post_id))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error updating scheduled post status: {e}")
            return False
