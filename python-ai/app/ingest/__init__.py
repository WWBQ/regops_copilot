"""文档入库：解析、清洗、校验、幂等写入。"""

from app.ingest.chunker import TextChunk, chunk_page_blocks
from app.ingest.cleaner import CleanStats, clean_page_blocks
from app.ingest.embeddings import (
    EMBEDDING_DIM,
    embed_text,
    embed_texts,
    get_embedding_model,
    vector_to_pg_literal,
)
from app.ingest.models import PageBlock, TableBlock, TableCellBlock
from app.ingest.parser import ParseError, content_hash, parse_pdf

__all__ = [
    "CleanStats",
    "EMBEDDING_DIM",
    "PageBlock",
    "ParseError",
    "TableBlock",
    "TableCellBlock",
    "TextChunk",
    "chunk_page_blocks",
    "clean_page_blocks",
    "content_hash",
    "embed_text",
    "embed_texts",
    "get_embedding_model",
    "parse_pdf",
    "vector_to_pg_literal",
]
