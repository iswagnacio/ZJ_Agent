"""S3/MinIO client for image storage."""

import logging
from typing import Optional
import os
import base64
from pathlib import Path

logger = logging.getLogger(__name__)

# boto3 is optional - only needed for S3/MinIO
try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.info("boto3 not installed - S3 storage will not be available")


class LocalFileStorage:
    """Local file storage fallback when S3 is not configured."""

    def __init__(self, storage_dir: str = "./uploads"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using local file storage at {self.storage_dir}")

    async def upload_image(
        self, session_id: str, content: bytes, content_type: str
    ) -> str:
        """Save image locally and return data URL."""
        session_dir = self.storage_dir / session_id
        session_dir.mkdir(exist_ok=True)

        image_path = session_dir / "input.png"
        with open(image_path, "wb") as f:
            f.write(content)

        # Return as data URL for vision models
        encoded = base64.b64encode(content).decode('utf-8')
        data_url = f"data:{content_type};base64,{encoded}"

        logger.info(f"Saved image locally for session {session_id}")
        return data_url

    async def delete_image(self, session_id: str):
        """Delete locally stored image."""
        session_dir = self.storage_dir / session_id
        image_path = session_dir / "input.png"

        if image_path.exists():
            image_path.unlink()
            logger.info(f"Deleted local image for session {session_id}")


class S3Client:
    """S3/MinIO client for storing uploaded images."""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ):
        self.bucket = bucket

        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

        # Ensure bucket exists
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        try:
            self.s3.head_bucket(Bucket=self.bucket)
            logger.info(f"Bucket '{self.bucket}' exists")
        except ClientError:
            try:
                self.s3.create_bucket(Bucket=self.bucket)
                logger.info(f"Created bucket '{self.bucket}'")
            except Exception as e:
                logger.error(f"Failed to create bucket: {e}")

    async def upload_image(
        self, session_id: str, content: bytes, content_type: str
    ) -> str:
        """Upload image and return presigned URL."""

        key = f"images/{session_id}/input.png"

        try:
            self.s3.put_object(
                Bucket=self.bucket, Key=key, Body=content, ContentType=content_type
            )

            # Generate presigned URL (7 days)
            url = self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=604800,
            )

            logger.info(f"Uploaded image for session {session_id}")
            return url

        except Exception as e:
            logger.error(f"Failed to upload image: {e}")
            raise

    async def delete_image(self, session_id: str):
        """Delete image for a session."""
        key = f"images/{session_id}/input.png"

        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            logger.info(f"Deleted image for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to delete image: {e}")
