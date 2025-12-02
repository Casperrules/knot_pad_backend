import boto3
from botocore.exceptions import ClientError
from config import get_settings
import uuid
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class S3Storage:
    def __init__(self):
        if settings.use_s3:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region
            )
            self.bucket_name = settings.s3_bucket_name
        else:
            self.s3_client = None
            self.bucket_name = None
    
    def upload_file(self, file_content: bytes, filename: str, content_type: str, folder: str = "images") -> str:
        """
        Upload file to S3 bucket (private)
        Returns the S3 key (filename) for later retrieval
        """
        if not settings.use_s3:
            raise ValueError("S3 storage is not enabled")
        
        try:
            # Generate unique filename
            file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'jpg'
            unique_filename = f"{folder}/{uuid.uuid4()}.{file_extension}"
            
            # Upload to S3 (private - no ACL)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=unique_filename,
                Body=file_content,
                ContentType=content_type,
                # NO ACL - bucket remains private
            )
            
            # Return S3 key (not a URL)
            return unique_filename
        
        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            raise Exception(f"Failed to upload file to S3: {str(e)}")
    
    def get_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """
        Generate a pre-signed URL for secure file access
        Default expiration: 1 hour (3600 seconds)
        """
        if not settings.use_s3:
            raise ValueError("S3 storage is not enabled")
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Error generating pre-signed URL: {e}")
            raise Exception(f"Failed to generate pre-signed URL: {str(e)}")
    
    def delete_file(self, s3_key: str) -> bool:
        """
        Delete file from S3 bucket using S3 key
        """
        if not settings.use_s3:
            return False
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
        
        except ClientError as e:
            logger.error(f"Error deleting from S3: {e}")
            return False
    
    def file_exists(self, s3_key: str) -> bool:
        """
        Check if file exists in S3 bucket using S3 key
        """
        if not settings.use_s3:
            return False
        
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False


# Singleton instance
s3_storage = S3Storage()
