"""Knowledge indexer for building dense and sparse indices."""

import json
import pickle
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

from .chunker import MarkdownChunker, ChunkMetadata
from .tokenizer import BM25Tokenizer

logger = logging.getLogger(__name__)


class KnowledgeIndexer:
    """
    Builds and manages knowledge base indices.

    Creates:
    1. chunks.jsonl - ground truth chunks
    2. chroma/ - dense vector index
    3. bm25.pkl - sparse BM25 index
    4. manifest.json - build metadata
    """

    def __init__(
        self,
        knowledge_base_path: str,
        index_output_path: str,
        embedding_model: str = "text-embedding-3-small",
        collection_name: str = "api_docs"
    ):
        """
        Initialize indexer.

        Args:
            knowledge_base_path: Path to markdown files
            index_output_path: Path to store indices
            embedding_model: OpenAI embedding model name
            collection_name: Chroma collection name
        """
        self.kb_path = Path(knowledge_base_path)
        self.output_path = Path(index_output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)

        self.embedding_model = embedding_model
        self.collection_name = collection_name

        # Initialize components
        self.chunker = MarkdownChunker()
        self.tokenizer = BM25Tokenizer()

        # Validate dependencies
        if not CHROMA_AVAILABLE:
            logger.warning("chromadb not installed, dense indexing disabled")
        if not BM25_AVAILABLE:
            logger.warning("rank-bm25 not installed, BM25 indexing disabled")

    def discover_documents(self) -> List[Path]:
        """Discover all markdown files in knowledge base."""
        md_files = list(self.kb_path.rglob("*.md"))
        logger.info(f"Discovered {len(md_files)} markdown files")
        return md_files

    def compute_file_hash(self, file_path: Path) -> str:
        """Compute MD5 hash of file content."""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def chunk_all_documents(self, file_paths: List[Path]) -> List[ChunkMetadata]:
        """Chunk all documents and return list of chunks."""
        all_chunks = []

        for file_path in file_paths:
            logger.info(f"Chunking {file_path.name}...")

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Get relative path from kb_path
                rel_path = file_path.relative_to(self.kb_path)

                chunks = self.chunker.chunk_document(str(rel_path), content)
                all_chunks.extend(chunks)

                logger.info(f"  -> {len(chunks)} chunks created")

            except Exception as e:
                logger.error(f"Error chunking {file_path}: {e}")
                continue

        logger.info(f"Total chunks created: {len(all_chunks)}")
        return all_chunks

    def save_chunks_jsonl(self, chunks: List[ChunkMetadata]) -> Path:
        """Save chunks to jsonl file (ground truth)."""
        output_file = self.output_path / "chunks.jsonl"

        with open(output_file, 'w', encoding='utf-8') as f:
            for chunk in chunks:
                f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + '\n')

        logger.info(f"Saved {len(chunks)} chunks to {output_file}")
        return output_file

    def load_chunks_jsonl(self) -> List[ChunkMetadata]:
        """Load chunks from jsonl file."""
        chunks_file = self.output_path / "chunks.jsonl"

        if not chunks_file.exists():
            logger.warning(f"Chunks file not found: {chunks_file}")
            return []

        chunks = []
        with open(chunks_file, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                chunks.append(ChunkMetadata(**data))

        logger.info(f"Loaded {len(chunks)} chunks from {chunks_file}")
        return chunks

    def build_dense_index(self, chunks: List[ChunkMetadata]) -> Optional[chromadb.Collection]:
        """Build Chroma dense vector index."""
        if not CHROMA_AVAILABLE:
            logger.warning("Skipping dense index - chromadb not available")
            return None

        logger.info("Building dense vector index with Chroma...")

        # Initialize Chroma client
        chroma_path = self.output_path / "chroma"
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection
        try:
            client.delete_collection(name=self.collection_name)
        except:
            pass

        collection = client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )

        # Prepare data for batch insert
        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = [
            {
                'heading': chunk.heading,
                'header_path': json.dumps(chunk.header_path),
                'method_name': chunk.method_name,
                'doc_type': chunk.doc_type,
                'source': chunk.source,
                'token_count': chunk.token_count,
                'has_code': chunk.has_code,
                'has_table': chunk.has_table
            }
            for chunk in chunks
        ]

        # Add to collection in batches
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            end_idx = min(i + batch_size, len(chunks))
            batch_ids = ids[i:end_idx]
            batch_docs = documents[i:end_idx]
            batch_meta = metadatas[i:end_idx]

            collection.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta
            )

            logger.info(f"  Indexed {end_idx}/{len(chunks)} chunks")

        logger.info(f"Dense index built: {len(chunks)} chunks")
        return collection

    def build_bm25_index(self, chunks: List[ChunkMetadata]) -> Optional[Dict[str, Any]]:
        """Build BM25 sparse index."""
        if not BM25_AVAILABLE:
            logger.warning("Skipping BM25 index - rank-bm25 not available")
            return None

        logger.info("Building BM25 sparse index...")

        # Tokenize all documents
        corpus = [chunk.content for chunk in chunks]
        tokenized_corpus = [self.tokenizer(doc) for doc in corpus]

        # Build BM25 index
        bm25 = BM25Okapi(tokenized_corpus)

        # Save BM25 state + metadata
        bm25_data = {
            'bm25': bm25,
            'chunk_ids': [chunk.chunk_id for chunk in chunks],
            'tokenized_corpus': tokenized_corpus,
            'chunks_metadata': [chunk.to_dict() for chunk in chunks]
        }

        output_file = self.output_path / "bm25.pkl"
        with open(output_file, 'wb') as f:
            pickle.dump(bm25_data, f)

        logger.info(f"BM25 index saved to {output_file}")
        return bm25_data

    def build_manifest(self, file_paths: List[Path], chunks: List[ChunkMetadata]) -> Dict[str, Any]:
        """Create build manifest with metadata."""
        file_hashes = {
            str(fp.relative_to(self.kb_path)): self.compute_file_hash(fp)
            for fp in file_paths
        }

        manifest = {
            'build_time': datetime.now().isoformat(),
            'embedding_model': self.embedding_model,
            'num_source_files': len(file_paths),
            'num_chunks': len(chunks),
            'file_hashes': file_hashes,
            'doc_type_distribution': self._get_doc_type_dist(chunks),
            'avg_chunk_tokens': sum(c.token_count for c in chunks) / len(chunks) if chunks else 0,
            'chunker_config': {
                'target_chunk_size': self.chunker.target_chunk_size,
                'max_chunk_size': self.chunker.max_chunk_size,
                'min_chunk_size': self.chunker.min_chunk_size,
                'overlap_size': self.chunker.overlap_size
            }
        }

        output_file = self.output_path / "manifest.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(f"Manifest saved to {output_file}")
        return manifest

    def _get_doc_type_dist(self, chunks: List[ChunkMetadata]) -> Dict[str, int]:
        """Get distribution of doc_types."""
        dist = {}
        for chunk in chunks:
            dist[chunk.doc_type] = dist.get(chunk.doc_type, 0) + 1
        return dist

    def build_all(self, force_rebuild: bool = False) -> Dict[str, Any]:
        """
        Build all indices: chunking + dense + sparse.

        Args:
            force_rebuild: If True, rebuild even if indices exist

        Returns:
            Build statistics
        """
        logger.info("Starting knowledge base indexing...")

        # Step 1: Discover documents
        file_paths = self.discover_documents()
        if not file_paths:
            logger.error("No markdown files found!")
            return {}

        # Step 2: Chunk all documents
        chunks = self.chunk_all_documents(file_paths)
        if not chunks:
            logger.error("No chunks created!")
            return {}

        # Step 3: Save chunks.jsonl (ground truth)
        self.save_chunks_jsonl(chunks)

        # Step 4: Build dense index
        if CHROMA_AVAILABLE:
            self.build_dense_index(chunks)
        else:
            logger.warning("Chroma not available, skipping dense index")

        # Step 5: Build BM25 index
        if BM25_AVAILABLE:
            self.build_bm25_index(chunks)
        else:
            logger.warning("BM25 not available, skipping sparse index")

        # Step 6: Create manifest
        manifest = self.build_manifest(file_paths, chunks)

        logger.info("Indexing complete!")

        # Return stats
        return {
            'success': True,
            'num_files': len(file_paths),
            'num_chunks': len(chunks),
            'manifest': manifest
        }

    def validate_index(self) -> Dict[str, Any]:
        """
        Validate built indices.

        Returns validation report with:
        - Chunk count and size distribution
        - Doc type distribution
        - Method name coverage
        - Sanity checks (no empty chunks, no oversized chunks)
        """
        logger.info("Validating indices...")

        chunks = self.load_chunks_jsonl()
        if not chunks:
            return {'valid': False, 'error': 'No chunks found'}

        # Basic stats
        stats = {
            'total_chunks': len(chunks),
            'avg_tokens': sum(c.token_count for c in chunks) / len(chunks),
            'max_tokens': max(c.token_count for c in chunks),
            'min_tokens': min(c.token_count for c in chunks),
        }

        # Doc type distribution
        doc_types = {}
        for chunk in chunks:
            doc_types[chunk.doc_type] = doc_types.get(chunk.doc_type, 0) + 1
        stats['doc_type_distribution'] = doc_types

        # Method name coverage
        with_method = sum(1 for c in chunks if c.method_name)
        stats['method_name_coverage'] = with_method / len(chunks)

        # Sanity checks
        issues = []

        # Check for empty chunks
        empty_chunks = [c for c in chunks if not c.content.strip()]
        if empty_chunks:
            issues.append(f"Found {len(empty_chunks)} empty chunks")

        # Check for oversized chunks
        oversized = [c for c in chunks if c.token_count > self.chunker.max_chunk_size * 1.2]
        if oversized:
            issues.append(f"Found {len(oversized)} oversized chunks (>20% over max)")

        # Check for duplicate IDs
        chunk_ids = [c.chunk_id for c in chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            issues.append("Found duplicate chunk IDs")

        stats['issues'] = issues
        stats['valid'] = len(issues) == 0

        logger.info(f"Validation complete: {'PASS' if stats['valid'] else 'FAIL'}")
        if issues:
            for issue in issues:
                logger.warning(f"  - {issue}")

        return stats
