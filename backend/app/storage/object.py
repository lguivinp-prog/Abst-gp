import io
import hashlib
from typing import BinaryIO, Dict, Any, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None

from .base import DocumentStorage
from app.core.config import settings

class ObjectStorageAdapter(DocumentStorage):
    def __init__(self):
        if boto3 is None:
            raise ImportError("boto3 is required to use ObjectStorageAdapter")
            
        self.bucket_name = settings.S3_BUCKET_NAME
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name="us-east-1"
        )
        
    def _get_s3_key(self, tenant_id: str, document_id: str) -> str:
        # Avoid leading slashes
        return f"{tenant_id}/{document_id}"

    def put(self, tenant_id: str, document_id: str, file_stream: BinaryIO, expected_checksum: Optional[str] = None) -> str:
        key = self._get_s3_key(tenant_id, document_id)
        
        # Calculate checksum while reading
        hasher = hashlib.sha256()
        
        if hasattr(file_stream, 'seek') and hasattr(file_stream, 'tell'):
            try:
                if file_stream.tell() != 0:
                    file_stream.seek(0)
            except Exception:
                pass
                
        # We need to compute the SHA-256 before uploading to validate it
        # and to attach it as metadata. We spool to memory (or temp file for large files).
        # Since we must maintain SHA-256 authority, let's read the stream.
        content = file_stream.read()
        hasher.update(content)
        actual_checksum = hasher.hexdigest()
        
        if expected_checksum and actual_checksum != expected_checksum:
            raise ValueError(f"Checksum mismatch. Expected {expected_checksum}, got {actual_checksum}")
            
        # Rewind if possible, else use the read content
        if hasattr(file_stream, 'seek'):
            try:
                file_stream.seek(0)
            except Exception:
                file_stream = io.BytesIO(content)
        else:
            file_stream = io.BytesIO(content)
            
        # Upload with metadata
        self.s3_client.upload_fileobj(
            file_stream, 
            self.bucket_name, 
            key,
            ExtraArgs={
                "Metadata": {
                    "sha256_checksum": actual_checksum
                }
            }
        )
        
        # URI will simply be the key for Object Storage
        return key

    def get(self, uri: str) -> BinaryIO:
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=uri)
            # return the streaming body
            # boto3 StreamingBody has a .read() method which is duck-typed as BinaryIO
            return response['Body']
        except ClientError as e:
            if e.response['Error']['Code'] in ('NoSuchKey', '404'):
                raise FileNotFoundError(f"Document not found at {uri}")
            raise

    def delete(self, uri: str) -> bool:
        if not self.exists(uri):
            return False
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=uri)
        return True

    def exists(self, uri: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=uri)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] in ('NoSuchKey', '404'):
                return False
            raise

    def checksum(self, uri: str) -> str:
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=uri)
            metadata = response.get('Metadata', {})
            
            # Prefer our explicit sha256 checksum in metadata
            if 'sha256_checksum' in metadata:
                return metadata['sha256_checksum']
                
            # If not in metadata, we must download and calculate to remain the authority
            stream = self.get(uri)
            hasher = hashlib.sha256()
            try:
                while chunk := stream.read(8192):
                    hasher.update(chunk)
            finally:
                if hasattr(stream, 'close'):
                    stream.close()
            return hasher.hexdigest()
            
        except ClientError as e:
            if e.response['Error']['Code'] in ('NoSuchKey', '404'):
                raise FileNotFoundError(f"Document not found at {uri}")
            raise

    def metadata(self, uri: str) -> Dict[str, Any]:
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=uri)
            return {
                "size_bytes": response.get('ContentLength', 0),
                "created_at": response.get('LastModified', 0).timestamp() if response.get('LastModified') else 0,
                "modified_at": response.get('LastModified', 0).timestamp() if response.get('LastModified') else 0,
                "content_type": response.get('ContentType'),
                "sha256_checksum": response.get('Metadata', {}).get('sha256_checksum')
            }
        except ClientError as e:
            if e.response['Error']['Code'] in ('NoSuchKey', '404'):
                raise FileNotFoundError(f"Document not found at {uri}")
            raise

    def generate_presigned_url(self, uri: str, expiration: int = 3600) -> str:
        try:
            return self.s3_client.generate_presigned_url(
                'put_object',
                Params={'Bucket': self.bucket_name, 'Key': uri},
                ExpiresIn=expiration
            )
        except ClientError as e:
            raise RuntimeError(f"Error generating presigned URL: {e}")
