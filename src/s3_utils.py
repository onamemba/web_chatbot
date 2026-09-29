"""
S3 utilities for storing and retrieving company policy documents.

This is what lets the project genuinely claim "cloud-hosted data" -
source documents live in AWS S3, not just on your local disk.
"""

import os
import boto3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")


def get_s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


def create_bucket_if_not_exists():
    """Create the S3 bucket if it doesn't already exist. Safe to call repeatedly."""
    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"Bucket '{BUCKET_NAME}' already exists.")
    except Exception:
        print(f"Creating bucket '{BUCKET_NAME}'...")
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET_NAME)
        else:
            s3.create_bucket(
                Bucket=BUCKET_NAME,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
            )
        print("Bucket created.")


def upload_docs_to_s3(local_dir: str, s3_prefix: str = "hr-policy/data/"):
    """Upload every file in local_dir to the S3 bucket under s3_prefix."""
    s3 = get_s3_client()
    local_path = Path(local_dir)
    uploaded = []

    for file_path in local_path.glob("*"):
        if file_path.is_file():
            s3_key = f"{s3_prefix}{file_path.name}"
            s3.upload_file(str(file_path), BUCKET_NAME, s3_key)
            uploaded.append(s3_key)
            print(f"Uploaded: {file_path.name} -> s3://{BUCKET_NAME}/{s3_key}")

    return uploaded


def download_docs_from_s3(s3_prefix: str = "chr-policy/data/", local_dir: str = "data_from_s3"):
    """Download all documents under s3_prefix from S3 into local_dir."""
    s3 = get_s3_client()
    Path(local_dir).mkdir(exist_ok=True)

    paginator = s3.get_paginator("list_objects_v2")
    downloaded = []

    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.split("/")[-1]
            if not filename:
                continue
            local_file = Path(local_dir) / filename
            s3.download_file(BUCKET_NAME, key, str(local_file))
            downloaded.append(str(local_file))
            print(f"Downloaded: {key} -> {local_file}")

    return downloaded


if __name__ == "__main__":
    # Quick manual test: upload the sample docs, then list what's in the bucket.
    create_bucket_if_not_exists()
    upload_docs_to_s3("data")
    print("\nDone. Documents are now hosted in S3.")
