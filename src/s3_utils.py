"""Download source documents from S3. (Keep your existing version if you have one.)"""

from pathlib import Path

import boto3

from config import AWS_REGION, S3_BUCKET_NAME

SUPPORTED = (".md", ".txt", ".pdf")


def download_docs_from_s3(s3_prefix: str = "", local_dir: str = "data_from_s3") -> int:
    if not S3_BUCKET_NAME:
        raise ValueError("S3_BUCKET_NAME is not set in .env")

    out = Path(local_dir)
    out.mkdir(parents=True, exist_ok=True)

    s3 = boto3.client("s3", region_name=AWS_REGION)
    paginator = s3.get_paginator("list_objects_v2")
    count = 0

    for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or not key.lower().endswith(SUPPORTED):
                continue
            s3.download_file(S3_BUCKET_NAME, key, str(out / Path(key).name))
            count += 1

    print(f"Downloaded {count} file(s) from s3://{S3_BUCKET_NAME}/{s3_prefix}")
    return count
