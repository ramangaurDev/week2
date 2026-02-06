"""
Firestore integration for persistent chunk storage (production-grade).
"""

from typing import Dict
from google.cloud import firestore
from app.logging_config import get_logger


logger = get_logger(__name__)


class FirestoreChunkStore:
    """
    Production-grade chunk storage using Firestore.
    Replaces in-memory storage for production deployments.
    """
    
    def __init__(self, project_id: str, collection_name: str = "rag_chunks"):
        try:
            self.db = firestore.Client(project=project_id)
            self.collection = self.db.collection(collection_name)
            logger.info(f"Firestore initialized", collection=collection_name)
        except Exception as e:
            logger.error(f"Failed to initialize Firestore", error=e)
            self.db = None
            self.collection = None
    
    def store_chunk(self, chunk_id: str, chunk_data: Dict) -> bool:
        """
        Store a single chunk in Firestore.
        
        Args:
            chunk_id: Unique chunk identifier
            chunk_data: Chunk data including text, metadata, vector
        
        Returns:
            Success status
        """
        if not self.collection:
            return False
        
        try:
            doc_data = {
                "chunk_id": chunk_id,
                "text": chunk_data.get("text", ""),
                "metadata": chunk_data.get("metadata", {}),
                "vector": chunk_data.get("vector", []),
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            
            self.collection.document(chunk_id).set(doc_data, merge=True)
            return True
            
        except Exception as e:
            logger.error(f"Failed to store chunk {chunk_id}", error=e)
            return False
    
    def batch_store_chunks(self, chunks: Dict[str, Dict]) -> int:
        """
        Store multiple chunks in batch.
        
        Args:
            chunks: Dictionary of chunk_id -> chunk_data
        
        Returns:
            Number of successfully stored chunks
        """
        if not self.db:
            return 0
        
        try:
            batch = self.db.batch()
            count = 0
            
            for chunk_id, chunk_data in chunks.items():
                doc_ref = self.collection.document(chunk_id)
                doc_data = {
                    "chunk_id": chunk_id,
                    "text": chunk_data.get("text", ""),
                    "metadata": chunk_data.get("metadata", {}),
                    "vector": chunk_data.get("vector", []),
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP
                }
                batch.set(doc_ref, doc_data, merge=True)
                count += 1
                
                # Firestore batch limit is 500
                if count % 500 == 0:
                    batch.commit()
                    batch = self.db.batch()
            
            if count % 500 != 0:
                batch.commit()
            
            logger.info(f"Batch stored {count} chunks")
            return count
            
        except Exception as e:
            logger.error(f"Batch store failed", error=e)
            return 0
    

    

    

    

    
    def count_chunks(self) -> int:
        """Count total chunks in store."""
        if not self.collection:
            return 0
        
        try:
            # Get aggregate count
            query = self.collection.count()
            result = query.get()
            return result[0][0].value
        except Exception as e:
            logger.warning(f"Count failed, using manual count", error=str(e))
            # Fallback to manual count
            try:
                docs = self.collection.stream()
                return sum(1 for _ in docs)
            except:
                return 0
