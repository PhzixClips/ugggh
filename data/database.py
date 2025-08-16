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
