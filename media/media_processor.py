"""
Media processing for video downloads, transcription, and frame extraction
"""

import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

import whisper

from config import (AUDIO_CLIPS_PATH, AUDIO_FILE_NAME, FFMPEG_PATH,
                    FRAMES_DIR_NAME, YT_DLP_PATH)
from utils.logging import log_upgrade

# --- Process-safe transcription function ---

_whisper_model = None

def transcribe_audio_process(audio_path_str: str) -> str:
    """
    Function to be run in a separate process for audio transcription.
    Loads the model once per process and transcribes the audio.
    """
    global _whisper_model
    if _whisper_model is None:
        log_upgrade("Loading Whisper model in new process...")
        _whisper_model = whisper.load_model("tiny")
        log_upgrade("Whisper model loaded.")

    audio_path = Path(audio_path_str)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path_str}")

    log_upgrade(f"Transcribing {audio_path_str}...")
    # Use fp16=False for CPU-based transcription for better compatibility
    result = _whisper_model.transcribe(str(audio_path), fp16=False)
    log_upgrade(f"Transcription complete for {audio_path_str}.")
    return result["text"]


class MediaProcessor:
    """Handles video downloads, audio extraction, and transcription"""

    def _run_subprocess(self, cmd: list, progress_callback: Optional[Callable], cancel_event: Optional[threading.Event]) -> bool:
        """Helper to run a subprocess, stream output, and handle cancellation."""
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            for line in iter(process.stdout.readline, ''):
                if cancel_event and cancel_event.is_set():
                    process.terminate()
                    log_upgrade(f"Process cancelled: {' '.join(cmd)}")
                    return False

                if progress_callback:
                    progress_callback({'line': line.strip()})

            process.wait()
            return process.returncode == 0

        except Exception as e:
            log_upgrade(f"Subprocess error: {e}")
            if progress_callback:
                progress_callback({'error': str(e)})
            return False

    def download_video(self, video_id: str, url: str, output_path: Path,
                      progress_callback: Optional[Callable] = None,
                      cancel_event: Optional[threading.Event] = None) -> bool:
        """Download video using yt-dlp with progress reporting."""
        output_path.mkdir(parents=True, exist_ok=True)
        output_template = str(output_path / f"{video_id}_%(title)s.%(ext)s")

        cmd = [
            YT_DLP_PATH,
            '--no-mtime',
            '-o', output_template,
            '--progress',
            url
        ]

        if progress_callback:
            progress_callback({'status': 'Starting download...'})

        return self._run_subprocess(cmd, progress_callback, cancel_event)

    def download_video_for_processing(self, video_id: str, url: str,
                                    output_path: Path,
                                    progress_callback: Optional[Callable] = None,
                                    cancel_event: Optional[threading.Event] = None) -> Optional[Path]:
        """Download video in MP4 format for processing"""
        video_file = output_path / f"{video_id}.mp4"
        cmd = [
            YT_DLP_PATH,
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
            '--no-mtime',
            '-o', str(video_file),
            '--progress',
            url
        ]

        if progress_callback:
            progress_callback({'status': 'Downloading video for processing...'})

        if self._run_subprocess(cmd, progress_callback, cancel_event) and video_file.exists():
            return video_file
        return None

    def extract_keyframes(self, video_path: Path, output_dir: Path,
                         fps: int = 2,
                         progress_callback: Optional[Callable] = None,
                         cancel_event: Optional[threading.Event] = None) -> bool:
        """Extract keyframes from video using ffmpeg"""
        output_dir.mkdir(parents=True, exist_ok=True)
        frame_pattern = str(output_dir / '%04d.jpg')
        cmd = [
            FFMPEG_PATH,
            '-y',
            '-i', str(video_path),
            '-vf', f"fps={fps}",
            frame_pattern
        ]

        if progress_callback:
            progress_callback({'status': 'Extracting keyframes...'})

        return self._run_subprocess(cmd, progress_callback, cancel_event)

    def extract_audio(self, video_path: Path, audio_path: Path,
                      progress_callback: Optional[Callable] = None,
                      cancel_event: Optional[threading.Event] = None) -> bool:
        """Extract audio from video using ffmpeg"""
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            FFMPEG_PATH,
            '-y',
            '-i', str(video_path),
            '-vn',
            '-ac', '1',
            '-ar', '16000',
            str(audio_path)
        ]

        if progress_callback:
            progress_callback({'status': 'Extracting audio...'})

        return self._run_subprocess(cmd, progress_callback, cancel_event)

    def download_audio_only(self, video_id: str, url: str,
                           output_path: Path,
                           progress_callback: Optional[Callable] = None,
                           cancel_event: Optional[threading.Event] = None) -> Optional[Path]:
        """Download audio only using yt-dlp"""
        output_path.mkdir(parents=True, exist_ok=True)
        audio_file_base = output_path / f"{video_id}_audio"
        audio_file_wav = output_path / f"{video_id}_audio.wav"

        cmd = [
            YT_DLP_PATH,
            '-x',
            '--audio-format', 'wav',
            '--audio-quality', '0',
            '--no-mtime',
            '-o', f"{audio_file_base}.%(ext)s",
            '--progress',
            url
        ]

        if progress_callback:
            progress_callback({'status': 'Starting audio download...'})

        if self._run_subprocess(cmd, progress_callback, cancel_event) and audio_file_wav.exists():
            return audio_file_wav
        return None

    def transcribe_audio(self, *args, **kwargs):
        """This method is deprecated. Use the top-level 'transcribe_audio_process' function."""
        raise DeprecationWarning("Use 'transcribe_audio_process' for transcription in a separate process.")

    def process_video_for_analysis(self, video_id: str, url: str,
                                  base_output_path: Path,
                                  progress_callback: Optional[Callable] = None,
                                  cancel_event: Optional[threading.Event] = None) -> dict:
        """Complete video processing pipeline for analysis. Runs sequentially."""
        results = {'success': False}
        output_dir = base_output_path / video_id
        output_dir.mkdir(parents=True, exist_ok=True)

        video_path = self.download_video_for_processing(video_id, url, output_dir, progress_callback, cancel_event)
        if not video_path:
            return results
        results['video_path'] = video_path

        if cancel_event and cancel_event.is_set(): return results

        frames_dir = output_dir / FRAMES_DIR_NAME
        if self.extract_keyframes(video_path, frames_dir, progress_callback=progress_callback, cancel_event=cancel_event):
            results['frames_dir'] = frames_dir
        else:
            if progress_callback: progress_callback({'error': 'Frame extraction failed.'})
            return results

        if cancel_event and cancel_event.is_set(): return results

        audio_path = output_dir / AUDIO_FILE_NAME
        if self.extract_audio(video_path, audio_path, progress_callback=progress_callback, cancel_event=cancel_event):
            results['audio_path'] = audio_path
        else:
            if progress_callback: progress_callback({'error': 'Audio extraction failed.'})
            return results

        results['success'] = True
        return results

    def create_safe_filename(self, text: str, max_length: int = 50) -> str:
        """Create safe filename from text"""
        safe_name = re.sub(r'[^\w\s-]', '_', text)
        safe_name = re.sub(r'\s+', ' ', safe_name).strip()
        return safe_name[:max_length].rstrip() or 'video'

    def get_output_path(self, query: str, video_title: str = "") -> Path:
        """Generate output path based on query and video title"""
        from config import CLIPHUSTLE_BASE_PATH
        safe_query = self.create_safe_filename(query, 30)
        base_path = CLIPHUSTLE_BASE_PATH / safe_query
        if video_title:
            safe_title = self.create_safe_filename(video_title, 20)
            return base_path / safe_title
        return base_path
