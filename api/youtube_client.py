"""
YouTube API client for handling all API interactions
"""

import os
import pickle
import requests
import itertools
from datetime import datetime, timezone
import isodate
from typing import Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import API_KEY_LIST, MAX_API_CALLS
from utils.logging import log_upgrade

# --- YouTube Uploading Constants ---
CLIENT_SECRET_FILE = 'client_secret.json'
API_NAME = 'youtube'
API_VERSION = 'v3'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
TOKEN_PICKLE_FILE = 'token.pickle'

class YouTubeAPIClient:
    def __init__(self):
        self.api_keys = itertools.cycle(API_KEY_LIST)
        self.api_call_count = 0
        self.search_cancelled = False

    def reset_tracking(self):
        """Reset API call tracking"""
        self.api_call_count = 0
        self.search_cancelled = False

    def cancel_search(self):
        """Cancel ongoing search operations"""
        self.search_cancelled = True

    def _get_next_key(self) -> str:
        """Get next API key from rotation"""
        return next(self.api_keys)

    def _make_request(self, url: str, params: Dict) -> Dict:
        """Make API request with fallback key rotation"""
        if self.search_cancelled:
            raise Exception('Search cancelled by user')

        if self.api_call_count >= MAX_API_CALLS:
            raise Exception(f'API call limit reached ({MAX_API_CALLS} calls)')

        for _ in range(len(API_KEY_LIST)):
            params['key'] = self._get_next_key()
            try:
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                self.api_call_count += 1

                if 'error' not in data:
                    return data

            except Exception as e:
                log_upgrade(f"API request error: {e}")
                continue

        raise Exception('All API keys exhausted or network error')

    def search_videos(self, query: str, max_results: int = 50,
                     published_after: Optional[datetime] = None,
                     next_page_token: Optional[str] = None) -> Tuple[List[str], Optional[str]]:
        """Search for videos and return video IDs and next page token"""
        search_url = 'https://www.googleapis.com/youtube/v3/search'

        params = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'maxResults': min(50, max_results),
            'videoDuration': 'any',
            'safeSearch': 'moderate'
        }

        if published_after:
            params['publishedAfter'] = published_after.replace(
                tzinfo=timezone.utc
            ).isoformat().replace('+00:00', 'Z')

        if next_page_token:
            params['pageToken'] = next_page_token

        data = self._make_request(search_url, params)

        video_ids = [
            item['id']['videoId']
            for item in data.get('items', [])
            if item.get('id', {}).get('videoId')
        ]

        return video_ids, data.get('nextPageToken')

    def get_video_details(self, video_ids: List[str]) -> Dict[str, Dict]:
        """Get detailed information for videos"""
        if not video_ids:
            return {}

        video_url = 'https://www.googleapis.com/youtube/v3/videos'

        params = {
            'part': 'snippet,statistics,contentDetails',
            'id': ','.join(video_ids)
        }

        data = self._make_request(video_url, params)

        return {
            video['id']: video
            for video in data.get('items', [])
        }

    def get_suggestions(self, query: str) -> List[str]:
        """Get search suggestions from Google"""
        try:
            response = requests.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "ds": "yt", "q": query},
                timeout=5
            )
            data = response.json()
            suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []
            return list(dict.fromkeys([query] + suggestions))
        except Exception as e:
            log_upgrade(f"Error getting suggestions: {e}")
            return [query]

    def get_authenticated_service(self):
        """
        Handles OAuth 2.0 flow and returns an authenticated YouTube service object.
        """
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        if os.path.exists(TOKEN_PICKLE_FILE):
            with open(TOKEN_PICKLE_FILE, 'rb') as token:
                creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CLIENT_SECRET_FILE):
                    raise FileNotFoundError(
                        "Could not find client_secret.json. "
                        "Please follow the instructions to set up OAuth 2.0 credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(TOKEN_PICKLE_FILE, 'wb') as token:
                pickle.dump(creds, token)

        return build(API_NAME, API_VERSION, credentials=creds)

    def upload_video(self, file_path: str, title: str, description: str, category_id: str, tags: List[str], privacy_status: str = 'private'):
        """
        Uploads a video to YouTube.

        Args:
            file_path: Path to the video file.
            title: The title of the video.
            description: The description of the video.
            category_id: The category ID for the video (e.g., '22' for People & Blogs).
            tags: A list of tags for the video.
            privacy_status: The privacy status of the video ('public', 'private', 'unlisted').

        Returns:
            The response from the YouTube API after uploading the video.
        """
        try:
            youtube = self.get_authenticated_service()

            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags,
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': privacy_status
                }
            }

            media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

            request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    log_upgrade(f"Uploaded {int(status.progress() * 100)}%.")

            log_upgrade(f"Upload successful! Video ID: {response.get('id')}")
            return response

        except Exception as e:
            log_upgrade(f"An error occurred during video upload: {e}")
            return None
