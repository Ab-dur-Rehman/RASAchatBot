# =============================================================================
# KNOWLEDGE BASE API
# =============================================================================
# API endpoints for Knowledge Base management with ChromaDB integration
# =============================================================================

import os
import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncpg
import aiofiles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])
security = HTTPBearer(auto_error=False)

# Configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/knowledge_base/data"))
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "chromadb")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8000"))
DEFAULT_COLLECTION = os.getenv("KB_COLLECTION", "website_content")

# Supported file types
SUPPORTED_FILE_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown", 
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".json": "application/json",
    ".csv": "text/csv",
}


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

db_pool: Optional[asyncpg.Pool] = None


async def get_db():
    """Dependency for database connection."""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "chatbot"),
            user=os.getenv("DB_USER", "rasa"),
            password=os.getenv("DB_PASSWORD", "rasa_password"),
            min_size=2,
            max_size=10
        )
    async with db_pool.acquire() as conn:
        yield conn


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin token (simplified for development)."""
    if credentials is None:
        return {"user_id": 0, "email": "anonymous", "role": "viewer"}
    return {"user_id": 1, "email": "admin@example.com", "role": "admin"}


# =============================================================================
# CHROMADB CLIENT
# =============================================================================

class ChromaDBClient:
    """ChromaDB client for vector operations."""
    
    def __init__(self):
        self._client = None
        self._embedding_function = None
    
    def get_client(self):
        """Get or create ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings
                
                self._client = chromadb.HttpClient(
                    host=CHROMADB_HOST,
                    port=CHROMADB_PORT,
                    settings=Settings(anonymized_telemetry=False)
                )
                logger.info(f"Connected to ChromaDB at {CHROMADB_HOST}:{CHROMADB_PORT}")
            except Exception as e:
                logger.error(f"Failed to connect to ChromaDB: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"ChromaDB not available: {str(e)}"
                )
        return self._client
    
    def get_embedding_function(self):
        """Get embedding function."""
        if self._embedding_function is None:
            try:
                from chromadb.utils import embedding_functions
                model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
                self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=model
                )
            except Exception as e:
                logger.error(f"Failed to initialize embeddings: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Embedding model not available: {str(e)}"
                )
        return self._embedding_function
    
    def get_collection(self, name: str = DEFAULT_COLLECTION):
        """Get or create a collection."""
        client = self.get_client()
        embedding_fn = self.get_embedding_function()
        return client.get_or_create_collection(
            name=name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"}
        )


chroma_client = ChromaDBClient()


# =============================================================================
# DOCUMENT PROCESSING
# =============================================================================

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into chunks with overlap."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Try to break at sentence boundary
        if end < len(text):
            last_period = chunk.rfind('. ')
            last_newline = chunk.rfind('\n')
            break_point = max(last_period, last_newline)
            if break_point > chunk_size // 2:
                chunk = chunk[:break_point + 1]
                end = start + break_point + 1
        
        chunks.append(chunk.strip())
        start = end - overlap
    
    return [c for c in chunks if c]


async def process_text_file(file_path: Path) -> str:
    """Read text from a file."""
    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return await f.read()


async def process_markdown_file(file_path: Path) -> str:
    """Process markdown file."""
    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    # Simple markdown cleanup
    import re
    # Remove code blocks but keep content
    content = re.sub(r'```[\s\S]*?```', '', content)
    # Remove inline code
    content = re.sub(r'`[^`]+`', '', content)
    # Remove markdown links but keep text
    content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)
    # Remove headers markers
    content = re.sub(r'^#+\s*', '', content, flags=re.MULTILINE)
    return content


async def process_html_file(file_path: Path) -> str:
    """Extract text from HTML file."""
    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        # Remove scripts and styles
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        return soup.get_text(separator='\n', strip=True)
    except ImportError:
        # Fallback: simple regex-based extraction
        import re
        content = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', content)
        content = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', content)
        content = re.sub(r'<[^>]+>', ' ', content)
        return ' '.join(content.split())


async def process_pdf_file(file_path: Path) -> str:
    """Extract text from PDF file."""
    try:
        import PyPDF2
        text_parts = []
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text())
        return '\n'.join(text_parts)
    except ImportError:
        logger.warning("PyPDF2 not installed, skipping PDF processing")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF processing not available. Install PyPDF2."
        )


async def process_file(file_path: Path, file_type: str) -> str:
    """Process file based on type."""
    processors = {
        ".txt": process_text_file,
        ".md": process_markdown_file,
        ".html": process_html_file,
        ".pdf": process_pdf_file,
        ".json": process_text_file,
        ".csv": process_text_file,
    }
    
    processor = processors.get(file_type, process_text_file)
    return await processor(file_path)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("/stats")
async def get_knowledge_base_stats(
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Get knowledge base statistics."""
    try:
        client = chroma_client.get_client()
        collections = client.list_collections()
        
        total_chunks = 0
        collection_info = []
        
        for col in collections:
            count = col.count()
            total_chunks += count
            collection_info.append({
                "name": col.name,
                "count": count
            })
        
        return {
            "total_collections": len(collections),
            "total_chunks": total_chunks,
            "collections": collection_info,
            "chromadb_status": "connected"
        }
    except Exception as e:
        return {
            "total_collections": 0,
            "total_chunks": 0,
            "collections": [],
            "chromadb_status": f"error: {str(e)}"
        }


@router.get("/documents")
async def list_documents(
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """List all documents in the knowledge base."""
    rows = await conn.fetch("""
        SELECT id, name, source_type, location, collection_name,
               enabled, last_ingested, document_count, chunk_count, metadata
        FROM content_sources
        ORDER BY created_at DESC
    """)
    
    documents = [dict(row) for row in rows]
    return {"documents": documents, "total": len(documents)}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form(DEFAULT_COLLECTION),
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Upload and process a document."""
    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}. Supported: {list(SUPPORTED_FILE_TYPES.keys())}"
        )
    
    # Create upload directory if needed
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate unique ID and save file
    doc_id = str(uuid.uuid4())[:8]
    safe_filename = f"{doc_id}_{file.filename.replace(' ', '_')}"
    file_path = UPLOAD_DIR / safe_filename
    
    try:
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Process document
        text_content = await process_file(file_path, file_ext)
        
        if not text_content or len(text_content.strip()) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document appears to be empty or could not be processed"
            )
        
        # Chunk the content
        chunks = chunk_text(text_content)
        
        # Add to ChromaDB
        chroma_collection = chroma_client.get_collection(collection)
        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source": file.filename,
                "doc_id": doc_id,
                "chunk_index": i,
                "file_type": file_ext
            }
            for i in range(len(chunks))
        ]
        
        chroma_collection.add(
            ids=chunk_ids,
            documents=chunks,
            metadatas=metadatas
        )
        
        # Save metadata to database
        await conn.execute("""
            INSERT INTO content_sources (id, name, source_type, location, collection_name,
                                        document_count, chunk_count, last_ingested, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8)
            ON CONFLICT (id) DO UPDATE SET
                document_count = $6,
                chunk_count = $7,
                last_ingested = NOW()
        """, doc_id, file.filename, 'file', str(file_path), collection,
             1, len(chunks), {"file_type": file_ext, "size_bytes": len(content)})
        
        return {
            "success": True,
            "document_id": doc_id,
            "filename": file.filename,
            "chunks_created": len(chunks),
            "collection": collection,
            "content_preview": text_content[:200] + "..." if len(text_content) > 200 else text_content
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        # Cleanup file on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing document: {str(e)}"
        )


@router.post("/import-url")
async def import_from_url(
    url: str = Form(...),
    collection: str = Form(DEFAULT_COLLECTION),
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Import content from a URL."""
    import httpx
    
    try:
        # Fetch URL content
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            content = response.text
        
        # Process HTML content
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # Get title
            title = soup.title.string if soup.title else url
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                tag.decompose()
            
            # Get main content
            main_content = soup.find('main') or soup.find('article') or soup.find('body')
            text_content = main_content.get_text(separator='\n', strip=True) if main_content else soup.get_text()
            
        except ImportError:
            # Fallback
            import re
            text_content = re.sub(r'<[^>]+>', ' ', content)
            text_content = ' '.join(text_content.split())
            title = url
        
        if not text_content or len(text_content.strip()) < 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract meaningful content from URL"
            )
        
        # Chunk and add to ChromaDB
        doc_id = str(uuid.uuid4())[:8]
        chunks = chunk_text(text_content)
        
        chroma_collection = chroma_client.get_collection(collection)
        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source": url,
                "title": title,
                "doc_id": doc_id,
                "chunk_index": i,
                "source_type": "url"
            }
            for i in range(len(chunks))
        ]
        
        chroma_collection.add(
            ids=chunk_ids,
            documents=chunks,
            metadatas=metadatas
        )
        
        # Save to database
        await conn.execute("""
            INSERT INTO content_sources (id, name, source_type, location, collection_name,
                                        document_count, chunk_count, last_ingested, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8)
            ON CONFLICT (id) DO UPDATE SET
                document_count = $6,
                chunk_count = $7,
                last_ingested = NOW()
        """, doc_id, title[:255], 'url', url, collection,
             1, len(chunks), {"title": title})
        
        return {
            "success": True,
            "document_id": doc_id,
            "title": title,
            "url": url,
            "chunks_created": len(chunks),
            "collection": collection
        }
        
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch URL: {str(e)}"
        )


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Delete a document from the knowledge base."""
    # Get document info
    row = await conn.fetchrow(
        "SELECT collection_name, location, source_type FROM content_sources WHERE id = $1",
        doc_id
    )
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    try:
        # Delete from ChromaDB
        collection = chroma_client.get_collection(row['collection_name'])
        # Get all chunk IDs for this document
        results = collection.get(where={"doc_id": doc_id})
        if results['ids']:
            collection.delete(ids=results['ids'])
        
        # Delete file if it's a local file
        if row['source_type'] == 'file':
            file_path = Path(row['location'])
            if file_path.exists():
                file_path.unlink()
        
        # Delete from database
        await conn.execute("DELETE FROM content_sources WHERE id = $1", doc_id)
        
        return {"success": True, "deleted_id": doc_id}
        
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting document: {str(e)}"
        )


@router.post("/search")
async def search_knowledge_base(
    query: str = Form(...),
    collection: str = Form(DEFAULT_COLLECTION),
    top_k: int = Form(5),
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Search the knowledge base."""
    try:
        chroma_collection = chroma_client.get_collection(collection)
        
        results = chroma_collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        # Format results
        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results.get('distances') else 0
                
                formatted_results.append({
                    "content": doc,
                    "source": metadata.get('source', 'Unknown'),
                    "score": 1 - distance,  # Convert distance to similarity
                    "metadata": metadata
                })
        
        return {
            "query": query,
            "results": formatted_results,
            "collection": collection
        }
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/collections")
async def list_collections(
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """List all collections."""
    try:
        client = chroma_client.get_client()
        collections = client.list_collections()
        
        return {
            "collections": [
                {"name": col.name, "count": col.count()}
                for col in collections
            ]
        }
    except Exception as e:
        return {"collections": [], "error": str(e)}


@router.post("/collections")
async def create_collection(
    name: str = Form(...),
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Create a new collection."""
    try:
        collection = chroma_client.get_collection(name)
        return {"success": True, "collection": name, "count": collection.count()}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create collection: {str(e)}"
        )
