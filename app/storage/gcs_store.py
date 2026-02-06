"""
Cloud Storage integration for document management.
"""

from typing import Optional
from google.cloud import storage
from datetime import datetime
from app.logging_config import get_logger


logger = get_logger(__name__)


class GCSDocumentStore:
    """
    Cloud Storage integration for document storage and management.
    Stores uploaded documents for audit trail and reprocessing.
    """
    
    def __init__(self, project_id: str, bucket_name: str):
        try:
            self.client = storage.Client(project=project_id)
            self.bucket = self.client.bucket(bucket_name)
            
            # Create bucket if it doesn't exist
            if not self.bucket.exists():
                self.bucket = self.client.create_bucket(
                    bucket_name,
                    location="us-central1"
                )
                logger.info(f"Created GCS bucket: {bucket_name}")
            else:
                logger.info(f"Using existing GCS bucket: {bucket_name}")
                
        except Exception as e:
            logger.error(f"Failed to initialize GCS", error=e)
            self.bucket = None
    
    def upload_document(
        self, 
        filename: str, 
        content: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict = None
    ) -> Optional[str]:
        """
        Upload document to Cloud Storage.
        
        Args:
            filename: Original filename
            content: File content as bytes
            content_type: MIME type
            metadata: Optional metadata
        
        Returns:
            GCS URI or None
        """
        if not self.bucket:
            return None
        
        try:
            # Generate unique path with timestamp
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            blob_name = f"documents/{timestamp}_{filename}"
            
            blob = self.bucket.blob(blob_name)
            blob.content_type = content_type
            
            # Set metadata
            if metadata:
                blob.metadata = metadata
            
            # Upload
            blob.upload_from_string(content, content_type=content_type)
            
            gcs_uri = f"gs://{self.bucket.name}/{blob_name}"
            logger.info(f"Uploaded document", filename=filename, gcs_uri=gcs_uri)
            
            return gcs_uri
            
        except Exception as e:
            logger.error(f"Failed to upload document {filename}", error=e)
            return None
    

    

    

    

