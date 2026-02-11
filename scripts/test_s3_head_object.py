#!/usr/bin/env python
"""
Test script to verify S3 HeadObject operation works with current credentials.

Usage:
    python scripts/test_s3_head_object.py <s3-key>

Example:
    python scripts/test_s3_head_object.py frames/1234567890/test.jpg
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "handout_generator.settings")

import django

django.setup()

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from django.conf import settings


async def test_head_object(s3_key: str, debug: bool = False):
    """Test HeadObject operation on a specific S3 key."""

    # Get S3 config from Django settings
    bucket_name = settings.S3_BUCKET_NAME
    region = settings.S3_REGION
    endpoint_url = settings.S3_ENDPOINT_URL or None
    access_key = settings.S3_ACCESS_KEY_ID
    secret_key = settings.S3_SECRET_ACCESS_KEY
    use_path_style = settings.S3_USE_PATH_STYLE

    print("=" * 60)
    print("S3 Configuration Test")
    print("=" * 60)
    print(f"Bucket: {bucket_name}")
    print(f"Region: {region}")
    print(f"Endpoint: {endpoint_url or 'default AWS'}")
    print(f"Access Key: {access_key[:10]}..." if access_key else "Access Key: NOT SET")
    print(f"Path Style: {use_path_style}")
    print(f"Testing key: {s3_key}")
    print("=" * 60)
    print()

    if not bucket_name:
        print("❌ ERROR: S3_BUCKET_NAME not configured")
        return False

    if not access_key or not secret_key:
        print("❌ ERROR: S3 credentials not configured")
        return False

    # Create boto3 config
    boto_config = BotoConfig(
        s3={"addressing_style": "path" if use_path_style else "auto"},
        signature_version="s3v4",
        max_pool_connections=50,
        connect_timeout=5,
        read_timeout=60,
    )

    session = aioboto3.Session()

    async with session.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=boto_config,
    ) as s3:
        # Test 1: HeadObject
        print("Test 1: HeadObject operation")
        print("-" * 60)
        try:
            response = await s3.head_object(Bucket=bucket_name, Key=s3_key)
            print("✅ SUCCESS: HeadObject returned metadata")
            print(f"   Content-Length: {response.get('ContentLength', 'unknown')} bytes")
            print(f"   Content-Type: {response.get('ContentType', 'unknown')}")
            print(f"   Last-Modified: {response.get('LastModified', 'unknown')}")
            print(f"   ETag: {response.get('ETag', 'unknown')}")
            print()
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", "Unknown")
            print(f"❌ FAILED: {error_code} - {error_msg}")

            if debug:
                print("\nDebug: full error response")
                print("-" * 60)
                print(e.response)

            if error_code == "403":
                print("\n⚠️  403 Forbidden - Permission Issues:")
                print("   - Check IAM policy includes 's3:GetObject' and 's3:HeadObject'")
                print("   - Verify bucket policy doesn't deny access")
                print("   - Confirm credentials have read permissions")
            elif error_code == "404":
                print("\n⚠️  404 Not Found - Object doesn't exist:")
                print(f"   - Key '{s3_key}' not found in bucket '{bucket_name}'")
                print("   - Check the key path is correct")

            print()
            return False

        # Test 2: GetObject (just headers)
        print("Test 2: GetObject operation (headers only)")
        print("-" * 60)
        try:
            response = await s3.get_object(Bucket=bucket_name, Key=s3_key, Range="bytes=0-0")
            print("✅ SUCCESS: GetObject returned data")
            print(f"   Can read object content")
            print()
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", "Unknown")
            print(f"❌ FAILED: {error_code} - {error_msg}")

            if debug:
                print("\nDebug: full error response")
                print("-" * 60)
                print(e.response)

            if error_code == "403":
                print("\n⚠️  403 Forbidden - Read permission missing:")
                print("   - IAM policy needs 's3:GetObject' permission")

            print()
            return False

        # Test 3: List some objects in the same prefix
        print("Test 3: ListObjectsV2 (check nearby objects)")
        print("-" * 60)
        try:
            # Get prefix from key (e.g., "frames/123/" from "frames/123/file.jpg")
            prefix = "/".join(s3_key.split("/")[:-1]) + "/"
            response = await s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, MaxKeys=5)

            if "Contents" in response:
                print(
                    f"✅ SUCCESS: Found {len(response['Contents'])} objects with prefix '{prefix}':"
                )
                for obj in response["Contents"][:5]:
                    print(f"   - {obj['Key']} ({obj['Size']} bytes)")
            else:
                print(f"⚠️  No objects found with prefix '{prefix}'")
            print()
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", "Unknown")
            print(f"❌ FAILED: {error_code} - {error_msg}")
            if debug:
                print("\nDebug: full error response")
                print("-" * 60)
                print(e.response)
            print()

    print("=" * 60)
    print("All tests passed! ✅")
    print("=" * 60)
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test S3 HeadObject access.")
    parser.add_argument("s3_key", help="S3 key to test (e.g., frames/123/file.jpg)")
    parser.add_argument(
        "-n",
        "--repeat",
        type=int,
        default=1,
        help="Number of times to repeat the test",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable botocore debug logging and print full error responses",
    )
    args = parser.parse_args()

    if args.repeat < 1:
        print("Repeat count must be at least 1")
        sys.exit(1)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        for logger_name in ("botocore", "aiobotocore", "aiohttp"):
            logging.getLogger(logger_name).setLevel(logging.DEBUG)

    for idx in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"\nRun {idx}/{args.repeat}")
            print("-" * 60)
        success = asyncio.run(test_head_object(args.s3_key, debug=args.debug))
        if not success:
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
