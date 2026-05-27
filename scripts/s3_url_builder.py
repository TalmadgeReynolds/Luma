#!/usr/bin/env python3
"""
S3 URL builder — generates properly formatted CDN URLs for metadata.json

Handles URL encoding (spaces → %20) automatically so you don't have to.

Usage:
    python scripts/s3_url_builder.py 20260521 GMT20260521-170000_Recording_2560x1440.mp4

Output:
    https://luma-webinars-730335545672-us-east-1-an.s3.us-east-1.amazonaws.com/Luma%20Webinars/20260521%20Luma%20Webinar/GMT20260521-170000_Recording_2560x1440.mp4

Copy the output directly into your metadata.json video_url field.
"""
import sys
import urllib.parse

S3_BUCKET = "luma-webinars-730335545672-us-east-1-an"
S3_REGION = "us-east-1"
CDN_BASE = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com"


def build_s3_url(date_yyyymmdd: str, filename: str) -> str:
    """Build S3 CDN URL with proper encoding."""
    folder = f"Luma Webinars/{date_yyyymmdd} Luma Webinar"
    key = f"{folder}/{filename}"

    # URL-encode spaces and special characters (but not slashes)
    encoded_key = urllib.parse.quote(key, safe="/")

    return f"{CDN_BASE}/{encoded_key}"


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <YYYYMMDD> <filename>")
        print(f"Example: {sys.argv[0]} 20260521 GMT20260521-170000_Recording_2560x1440.mp4")
        sys.exit(1)

    date_str = sys.argv[1]
    filename = sys.argv[2]

    # Validate date format
    if len(date_str) != 8 or not date_str.isdigit():
        print(f"Error: Date must be YYYYMMDD (got '{date_str}')")
        sys.exit(1)

    url = build_s3_url(date_str, filename)
    print(url)


if __name__ == "__main__":
    main()
