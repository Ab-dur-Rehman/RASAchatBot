# =============================================================================
# KNOWLEDGE BASE CLIENT
# =============================================================================
# Client for vector store retrieval using ChromaDB
# =============================================================================

import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KnowledgeBaseClient:
    """
    Client for knowledge base retrieval using ChromaDB.
    
    Features:
    - Semantic search using embeddings
    - Collection management
    - Result filtering and ranking
    """
    
    def __init__(self):
        self.chroma_host = os.getenv("CHROMA_HOST", "chromadb")
        self.chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
        self.collection_name = os.getenv("KB_COLLECTION", "website_content")
        
        # Lazy initialization of ChromaDB client
        self._client = None
        self._collection = None
        self._embedding_function = None
    
    def _get_client(self):
        """Lazy initialization of ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings
                
                self._client = chromadb.HttpClient(
                    host=self.chroma_host,
                    port=self.chroma_port,
                    settings=Settings(
                        anonymized_telemetry=False
                    )
                )
                
                logger.info(f"Connected to ChromaDB at {self.chroma_host}:{self.chroma_port}")
                
            except ImportError:
                logger.error("chromadb package not installed")
                raise
            except Exception as e:
                logger.error(f"Failed to connect to ChromaDB: {e}")
                raise
        
        return self._client
    
    def _get_embedding_function(self):
        """Get embedding function for semantic search."""
        if self._embedding_function is None:
            try:
                from chromadb.utils import embedding_functions
                
                # Use sentence-transformers for embeddings
                # Can be switched to OpenAI embeddings if preferred
                embedding_model = os.getenv(
                    "EMBEDDING_MODEL",
                    "all-MiniLM-L6-v2"
                )
                
                self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=embedding_model
                )
                
                logger.info(f"Using embedding model: {embedding_model}")
                
            except Exception as e:
                logger.error(f"Failed to initialize embedding function: {e}")
                raise
        
        return self._embedding_function
    
    def _get_collection(self, collection_name: Optional[str] = None):
        """Get or create a collection."""
        name = collection_name or self.collection_name
        
        if self._collection is None or collection_name:
            try:
                client = self._get_client()
                embedding_fn = self._get_embedding_function()
                
                self._collection = client.get_or_create_collection(
                    name=name,
                    embedding_function=embedding_fn,
                    metadata={"hnsw:space": "cosine"}
                )
                
            except Exception as e:
                logger.error(f"Failed to get collection: {e}")
                raise
        
        return self._collection
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.5,
        collection_name: Optional[str] = None,
        filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Search the knowledge base for relevant content.
        
        Args:
            query: Search query text
            top_k: Maximum number of results to return
            min_score: Minimum similarity score threshold
            collection_name: Specific collection to search (optional)
            filters: Metadata filters (optional)
        
        Returns:
            List of result dictionaries with 'content', 'source', 'score'
        """
        try:
            collection = self._get_collection(collection_name)
            
            # Build query parameters
            query_params = {
                "query_texts": [query],
                "n_results": top_k * 2,  # Get more results for filtering
            }
            
            if filters:
                query_params["where"] = filters
            
            # Execute search
            results = collection.query(**query_params)
            
            # Process results
            processed_results = []
            
            if results and results.get("documents"):
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]
                
                for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
                    # Convert distance to similarity score
                    # ChromaDB uses L2 distance, convert to similarity
                    score = 1 - (distance / 2)  # Normalize to 0-1 range
                    
                    if score >= min_score:
                        processed_results.append({
                            "content": doc,
                            "source": metadata.get("source", "Unknown"),
                            "page": metadata.get("page", ""),
                            "score": round(score, 3),
                            "metadata": metadata
                        })
            
            # Sort by score and limit to top_k
            processed_results.sort(key=lambda x: x["score"], reverse=True)
            return processed_results[:top_k]
            
        except Exception as e:
            logger.exception(f"Knowledge base search error: {e}")
            return []
    
    async def search_multiple_collections(
        self,
        query: str,
        collections: List[str],
        top_k: int = 5,
        min_score: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search across multiple collections.
        
        Args:
            query: Search query text
            collections: List of collection names to search
            top_k: Maximum total results
            min_score: Minimum similarity score
        
        Returns:
            Combined and ranked results from all collections
        """
        all_results = []
        
        for collection_name in collections:
            try:
                results = await self.search(
                    query=query,
                    top_k=top_k,
                    min_score=min_score,
                    collection_name=collection_name
                )
                
                # Tag results with collection name
                for result in results:
                    result["collection"] = collection_name
                
                all_results.extend(results)
                
            except Exception as e:
                logger.warning(f"Error searching collection {collection_name}: {e}")
        
        # Sort all results by score
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]
    
    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        collection_name: Optional[str] = None
    ) -> bool:
        """
        Add documents to the knowledge base.
        
        Args:
            documents: List of document dicts with 'id', 'content', 'metadata'
            collection_name: Target collection (optional)
        
        Returns:
            True if successful
        """
        try:
            collection = self._get_collection(collection_name)
            
            ids = [doc["id"] for doc in documents]
            contents = [doc["content"] for doc in documents]
            metadatas = [doc.get("metadata", {}) for doc in documents]
            
            collection.add(
                ids=ids,
                documents=contents,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(documents)} documents to collection")
            return True
            
        except Exception as e:
            logger.exception(f"Error adding documents: {e}")
            return False
    
    async def delete_documents(
        self,
        ids: List[str],
        collection_name: Optional[str] = None
    ) -> bool:
        """
        Delete documents from the knowledge base.
        
        Args:
            ids: List of document IDs to delete
            collection_name: Target collection (optional)
        
        Returns:
            True if successful
        """
        try:
            collection = self._get_collection(collection_name)
            collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} documents from collection")
            return True
            
        except Exception as e:
            logger.exception(f"Error deleting documents: {e}")
            return False
    
    async def get_collection_stats(
        self,
        collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about a collection.
        
        Returns:
            Dict with collection statistics
        """
        try:
            collection = self._get_collection(collection_name)
            count = collection.count()
            
            return {
                "name": collection.name,
                "document_count": count,
                "metadata": collection.metadata
            }
            
        except Exception as e:
            logger.exception(f"Error getting collection stats: {e}")
            return {}
