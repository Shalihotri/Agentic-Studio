#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.config import get_settings
from app.connectors.gmail import GmailClient

def main():
    settings = get_settings()
    gmail = GmailClient(settings)
    try:
        # This will trigger the OAuth flow
        creds = gmail._get_credentials()
        print("Authentication successful!")
        print(f"Token saved to {settings.gmail_token_file}")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())