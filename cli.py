#!/usr/bin/env python3
"""
Anime AI Autoposter - CLI Runner
"""

import os
import sys

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.batch_processor import process_videos
from utils.logging import setup_logging, log_upgrade

def main():
    """Main CLI entry point"""
    setup_logging()
    log_upgrade("--- Anime AI Autoposter CLI Initialized ---")

    # Run the processor. By default, the CLI will use the watermark.
    # Future enhancement could be to use command-line arguments to control this.
    process_videos(use_watermark=True)

    log_upgrade("--- Processing complete. ---")


if __name__ == '__main__':
    main()
