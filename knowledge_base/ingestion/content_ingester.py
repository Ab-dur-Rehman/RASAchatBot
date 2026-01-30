# =============================================================================
# CONTENT INGESTION SYSTEM
# =============================================================================
# Scripts for ingesting website content into the vector store
# =============================================================================

import os
import re
import logging
import hashlib
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class ContentChunk:
    """Represents a chunk of content for the knowledge base."""
    id: str
    content: str
    source: str
    page: str
    chunk_index: int
    metadata: Dict[str, Any]


class ContentIngester:
    """
    Ingests content from various sources into the vector store.
    
    Supported sources:
    - HTML files
    - Text files
    - Markdown files
    - Web scraping (URLs)
    """
    
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 100
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        
        # Initialize knowledge base client
        from rasa.actions.utils.knowledge_base import KnowledgeBaseClient
        self.kb_client = KnowledgeBaseClient()
    
    # =========================================================================
    # FILE INGESTION
    # =========================================================================
    
    async def ingest_directory(
        self,
        directory: str,
        collection_name: str = "website_content",
        file_patterns: List[str] = None
    ) -> Dict[str, Any]:
        """
        Ingest all files from a directory.
        
        Args:
            directory: Path to directory
            collection_name: Target collection name
            file_patterns: File patterns to match (e.g., ['*.html', '*.md'])
        
        Returns:
            Ingestion statistics
        """
        if file_patterns is None:
            file_patterns = ['*.html', '*.htm', '*.txt', '*.md']
        
        stats = {
            "files_processed": 0,
            "chunks_created": 0,
            "errors": []
        }
        
        directory_path = Path(directory)
        
        for pattern in file_patterns:
            for file_path in directory_path.glob(f"**/{pattern}"):
                try:
                    result = await self.ingest_file(
                        str(file_path),
                        collection_name=collection_name
                    )
                    stats["files_processed"] += 1
                    stats["chunks_created"] += result.get("chunks", 0)
                    
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    stats["errors"].append({
                        "file": str(file_path),
                        "error": str(e)
                    })
        
        logger.info(f"Ingested {stats['files_processed']} files, "
                   f"created {stats['chunks_created']} chunks")
        
        return stats
    
    async def ingest_file(
        self,
        file_path: str,
        collection_name: str = "website_content",
        source_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingest a single file.
        
        Args:
            file_path: Path to file
            collection_name: Target collection
            source_name: Custom source name (defaults to filename)
        
        Returns:
            Ingestion result
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        source = source_name or path.stem
        
        # Read and parse file based on extension
        content = self._read_file(path)
        
        # Clean content
        content = self._clean_content(content, path.suffix)
        
        if not content or len(content) < self.min_chunk_size:
            logger.warning(f"File {file_path} has insufficient content")
            return {"chunks": 0}
        
        # Create chunks
        chunks = self._create_chunks(
            content=content,
            source=source,
            page=str(path)
        )
        
        # Add to knowledge base
        documents = [
            {
                "id": chunk.id,
                "content": chunk.content,
                "metadata": {
                    "source": chunk.source,
                    "page": chunk.page,
                    "chunk_index": chunk.chunk_index,
                    **chunk.metadata
                }
            }
            for chunk in chunks
        ]
        
        await self.kb_client.add_documents(documents, collection_name)
        
        return {"chunks": len(chunks)}
    
    def _read_file(self, path: Path) -> str:
        """Read file content."""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    
    def _clean_content(self, content: str, extension: str) -> str:
        """Clean content based on file type."""
        if extension.lower() in ['.html', '.htm']:
            return self._clean_html(content)
        elif extension.lower() == '.md':
            return self._clean_markdown(content)
        else:
            return self._clean_text(content)
    
    def _clean_html(self, html: str) -> str:
        """Extract and clean text from HTML."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script, style, and nav elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                element.decompose()
            
            # Get text
            text = soup.get_text(separator='\n')
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            text = '\n'.join(line for line in lines if line)
            
            return text
            
        except ImportError:
            logger.warning("beautifulsoup4 not installed, using basic HTML cleaning")
            # Basic HTML tag removal
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text)
            return text.strip()
    
    def _clean_markdown(self, markdown: str) -> str:
        """Clean markdown content."""
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '', markdown)
        text = re.sub(r'`[^`]+`', '', text)
        
        # Remove images
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        
        # Convert links to text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove headers markers but keep text
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # Remove emphasis markers
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        
        # Clean whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    def _clean_text(self, text: str) -> str:
        """Clean plain text."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove non-printable characters
        text = re.sub(r'[^\x20-\x7E\n]', '', text)
        return text.strip()
    
    # =========================================================================
    # CHUNKING
    # =========================================================================
    
    def _create_chunks(
        self,
        content: str,
        source: str,
        page: str
    ) -> List[ContentChunk]:
        """
        Split content into chunks for embedding.
        
        Uses a sliding window approach with overlap.
        """
        chunks = []
        
        # Split into sentences first for better chunk boundaries
        sentences = self._split_into_sentences(content)
        
        current_chunk = []
        current_length = 0
        chunk_index = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            
            # If adding this sentence exceeds chunk size, save current chunk
            if current_length + sentence_length > self.chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                
                if len(chunk_text) >= self.min_chunk_size:
                    chunk_id = self._generate_chunk_id(source, page, chunk_index)
                    chunks.append(ContentChunk(
                        id=chunk_id,
                        content=chunk_text,
                        source=source,
                        page=page,
                        chunk_index=chunk_index,
                        metadata={
                            "char_count": len(chunk_text),
                            "word_count": len(chunk_text.split())
                        }
                    ))
                    chunk_index += 1
                
                # Keep some sentences for overlap
                overlap_sentences = []
                overlap_length = 0
                for s in reversed(current_chunk):
                    if overlap_length + len(s) <= self.chunk_overlap:
                        overlap_sentences.insert(0, s)
                        overlap_length += len(s)
                    else:
                        break
                
                current_chunk = overlap_sentences
                current_length = overlap_length
            
            current_chunk.append(sentence)
            current_length += sentence_length
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) >= self.min_chunk_size:
                chunk_id = self._generate_chunk_id(source, page, chunk_index)
                chunks.append(ContentChunk(
                    id=chunk_id,
                    content=chunk_text,
                    source=source,
                    page=page,
                    chunk_index=chunk_index,
                    metadata={
                        "char_count": len(chunk_text),
                        "word_count": len(chunk_text.split())
                    }
                ))
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Simple sentence splitting
        # Can be enhanced with NLTK or spaCy for better accuracy
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _generate_chunk_id(self, source: str, page: str, index: int) -> str:
        """Generate unique chunk ID."""
        content = f"{source}:{page}:{index}"
        return hashlib.md5(content.encode()).hexdigest()
    
    # =========================================================================
    # WEB SCRAPING
    # =========================================================================
    
    async def ingest_urls(
        self,
        urls: List[str],
        collection_name: str = "website_content"
    ) -> Dict[str, Any]:
        """
        Ingest content from URLs.
        
        Args:
            urls: List of URLs to scrape
            collection_name: Target collection
        
        Returns:
            Ingestion statistics
        """
        stats = {
            "urls_processed": 0,
            "chunks_created": 0,
            "errors": []
        }
        
        try:
            import aiohttp
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("aiohttp and beautifulsoup4 required for URL ingestion")
            return {"error": "Missing dependencies"}
        
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=30) as response:
                        if response.status == 200:
                            html = await response.text()
                            
                            # Parse HTML
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Get page title
                            title = soup.title.string if soup.title else url
                            
                            # Extract text
                            for element in soup(['script', 'style', 'nav', 'footer']):
                                element.decompose()
                            
                            text = soup.get_text(separator='\n')
                            text = self._clean_text(text)
                            
                            if len(text) >= self.min_chunk_size:
                                # Create chunks
                                chunks = self._create_chunks(
                                    content=text,
                                    source=title,
                                    page=url
                                )
                                
                                # Add to knowledge base
                                documents = [
                                    {
                                        "id": chunk.id,
                                        "content": chunk.content,
                                        "metadata": {
                                            "source": chunk.source,
                                            "page": chunk.page,
                                            "url": url,
                                            "chunk_index": chunk.chunk_index
                                        }
                                    }
                                    for chunk in chunks
                                ]
                                
                                await self.kb_client.add_documents(documents, collection_name)
                                
                                stats["urls_processed"] += 1
                                stats["chunks_created"] += len(chunks)
                        else:
                            stats["errors"].append({
                                "url": url,
                                "error": f"HTTP {response.status}"
                            })
                            
                except Exception as e:
                    logger.error(f"Error fetching {url}: {e}")
                    stats["errors"].append({"url": url, "error": str(e)})
        
        return stats


# =============================================================================
# CLI INTERFACE
# =============================================================================

async def main():
    """CLI for content ingestion."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest content into knowledge base")
    parser.add_argument("--directory", "-d", help="Directory to ingest")
    parser.add_argument("--urls", "-u", nargs="+", help="URLs to ingest")
    parser.add_argument("--collection", "-c", default="website_content",
                       help="Collection name")
    parser.add_argument("--chunk-size", type=int, default=500,
                       help="Chunk size in characters")
    
    args = parser.parse_args()
    
    ingester = ContentIngester(chunk_size=args.chunk_size)
    
    if args.directory:
        result = await ingester.ingest_directory(args.directory, args.collection)
        print(f"Ingested directory: {result}")
    
    if args.urls:
        result = await ingester.ingest_urls(args.urls, args.collection)
        print(f"Ingested URLs: {result}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
