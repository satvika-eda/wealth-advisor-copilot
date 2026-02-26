"""Document chunking with metadata preservation for optimal retrieval."""
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import tiktoken

from app.config import get_settings

settings = get_settings()


class ChunkingStrategy(Enum):
    """Chunking strategies for different document types."""
    FIXED_SIZE = "fixed_size"
    SECTION_BASED = "section_based"
    SEMANTIC = "semantic"


@dataclass
class Chunk:
    """A chunk of text with metadata for retrieval."""
    content: str
    chunk_index: int
    token_count: int
    metadata: Dict[str, Any]
    # Metadata includes:
    # - heading_path: List[str] (breadcrumb of headings)
    # - page: int (for PDFs)
    # - section: str
    # - source_anchor: str (for citations)
    # - company: str
    # - filing_date: str


class Chunker:
    """Document chunker with support for multiple strategies."""
    
    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
        strategy: ChunkingStrategy = ChunkingStrategy.SECTION_BASED,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def chunk_document(
        self,
        content: str,
        sections: List[Dict[str, Any]],
        doc_metadata: Dict[str, Any],
    ) -> List[Chunk]:
        """
        Chunk a document based on the configured strategy.
        
        Args:
            content: Full document content
            sections: Parsed sections with headings
            doc_metadata: Document-level metadata (company, filing_type, etc.)
        
        Returns:
            List of Chunk objects
        """
        if self.strategy == ChunkingStrategy.SECTION_BASED and sections:
            return self._chunk_by_sections(sections, doc_metadata)
        else:
            return self._chunk_fixed_size(content, doc_metadata)
    
    def _chunk_by_sections(
        self,
        sections: List[Dict[str, Any]],
        doc_metadata: Dict[str, Any],
    ) -> List[Chunk]:
        """Chunk by document sections, splitting large sections."""
        chunks = []
        chunk_index = 0
        heading_path = []
        
        for section in sections:
            heading = section.get("heading", "")
            content = section.get("content", "")
            level = section.get("level", 1)
            page = section.get("page")
            
            if not content or not content.strip():
                continue
            
            # Update heading path based on level
            if level <= len(heading_path):
                heading_path = heading_path[:level-1]
            heading_path.append(heading)
            
            # Check if section needs splitting
            section_tokens = self.count_tokens(content)
            
            if section_tokens <= self.chunk_size:
                # Section fits in one chunk
                chunks.append(Chunk(
                    content=content.strip(),
                    chunk_index=chunk_index,
                    token_count=section_tokens,
                    metadata={
                        **doc_metadata,
                        "heading_path": heading_path.copy(),
                        "section": heading,
                        "page": page,
                        "source_anchor": self._create_source_anchor(heading_path, page),
                    }
                ))
                chunk_index += 1
            else:
                # Split large section
                sub_chunks = self._split_large_section(content, heading_path, page, doc_metadata)
                for sub_chunk in sub_chunks:
                    sub_chunk.chunk_index = chunk_index
                    chunks.append(sub_chunk)
                    chunk_index += 1
        
        return chunks
    
    def _split_large_section(
        self,
        content: str,
        heading_path: List[str],
        page: Optional[int],
        doc_metadata: Dict[str, Any],
    ) -> List[Chunk]:
        """Split a large section into smaller chunks with overlap."""
        chunks = []
        
        # Split by paragraphs first
        paragraphs = re.split(r'\n\s*\n', content)
        
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_tokens = self.count_tokens(para)
            
            if current_tokens + para_tokens <= self.chunk_size:
                current_chunk.append(para)
                current_tokens += para_tokens
            else:
                # Save current chunk
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append(Chunk(
                        content=chunk_text,
                        chunk_index=0,  # Will be set by caller
                        token_count=current_tokens,
                        metadata={
                            **doc_metadata,
                            "heading_path": heading_path.copy(),
                            "section": heading_path[-1] if heading_path else "",
                            "page": page,
                            "source_anchor": self._create_source_anchor(heading_path, page),
                            "is_split": True,
                        }
                    ))
                
                # Start new chunk with overlap
                overlap_tokens = 0
                overlap_paras = []
                
                # Add paragraphs from end of current chunk for overlap
                for p in reversed(current_chunk):
                    p_tokens = self.count_tokens(p)
                    if overlap_tokens + p_tokens <= self.chunk_overlap:
                        overlap_paras.insert(0, p)
                        overlap_tokens += p_tokens
                    else:
                        break
                
                current_chunk = overlap_paras + [para]
                current_tokens = overlap_tokens + para_tokens
        
        # Add final chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(Chunk(
                content=chunk_text,
                chunk_index=0,
                token_count=self.count_tokens(chunk_text),
                metadata={
                    **doc_metadata,
                    "heading_path": heading_path.copy(),
                    "section": heading_path[-1] if heading_path else "",
                    "page": page,
                    "source_anchor": self._create_source_anchor(heading_path, page),
                    "is_split": True,
                }
            ))
        
        return chunks
    
    def _chunk_fixed_size(
        self,
        content: str,
        doc_metadata: Dict[str, Any],
    ) -> List[Chunk]:
        """Simple fixed-size chunking with overlap."""
        chunks = []
        
        # Tokenize content
        tokens = self.tokenizer.encode(content)
        
        start = 0
        chunk_index = 0
        
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            chunks.append(Chunk(
                content=chunk_text,
                chunk_index=chunk_index,
                token_count=len(chunk_tokens),
                metadata={
                    **doc_metadata,
                    "heading_path": [],
                    "section": f"Chunk {chunk_index + 1}",
                    "source_anchor": f"chunk-{chunk_index + 1}",
                }
            ))
            
            # Move start with overlap
            start = end - self.chunk_overlap if end < len(tokens) else end
            chunk_index += 1
        
        return chunks
    
    def _create_source_anchor(self, heading_path: List[str], page: Optional[int]) -> str:
        """Create a citation-friendly source anchor."""
        parts = []
        
        if heading_path:
            # Clean headings for anchor
            clean_path = [re.sub(r'[^\w\s-]', '', h).strip().replace(' ', '-').lower() 
                         for h in heading_path]
            parts.append('/'.join(clean_path))
        
        if page:
            parts.append(f"p{page}")
        
        return '-'.join(parts) if parts else "content"
