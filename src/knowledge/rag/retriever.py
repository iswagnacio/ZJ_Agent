"""Hybrid retriever combining dense and sparse retrieval."""

import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import logging

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

from .tokenizer import BM25Tokenizer
from .chunker import ChunkMetadata

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Single retrieval result."""
    chunk_id: str
    content: str
    score: float
    heading: str
    header_path: List[str]
    method_name: str
    doc_type: str
    source: str
    retrieval_method: str  # 'dense', 'sparse', or 'hybrid'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'chunk_id': self.chunk_id,
            'content': self.content,
            'score': self.score,
            'heading': self.heading,
            'header_path': self.header_path,
            'method_name': self.method_name,
            'doc_type': self.doc_type,
            'source': self.source,
            'retrieval_method': self.retrieval_method
        }


class HybridRetriever:
    """
    Hybrid retrieval combining dense (Chroma) and sparse (BM25).

    Features:
    - Dense retrieval for semantic similarity
    - Sparse (BM25) retrieval for exact keyword matching
    - Reciprocal Rank Fusion (RRF) for combining results
    - Metadata filtering by doc_type and method_name
    - Deduplication and reranking
    """

    def __init__(
        self,
        index_path: str,
        collection_name: str = "api_docs",
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5
    ):
        """
        Initialize retriever.

        Args:
            index_path: Path to index directory
            collection_name: Chroma collection name
            dense_weight: Weight for dense retrieval (0-1)
            sparse_weight: Weight for sparse retrieval (0-1)
        """
        self.index_path = Path(index_path)
        self.collection_name = collection_name
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

        # Initialize components
        self.tokenizer = BM25Tokenizer()
        self.chroma_client = None
        self.chroma_collection = None
        self.bm25_index = None
        self.bm25_data = None

        self._load_indices()

    def _load_indices(self):
        """Load both dense and sparse indices."""
        # Load Chroma (dense)
        if CHROMA_AVAILABLE:
            try:
                chroma_path = self.index_path / "chroma"
                if chroma_path.exists():
                    self.chroma_client = chromadb.PersistentClient(path=str(chroma_path))
                    self.chroma_collection = self.chroma_client.get_collection(
                        name=self.collection_name
                    )
                    logger.info(f"Loaded Chroma collection: {self.collection_name}")
                else:
                    logger.warning(f"Chroma index not found at {chroma_path}")
            except Exception as e:
                logger.error(f"Error loading Chroma: {e}")
        else:
            logger.warning("Chroma not available")

        # Load BM25 (sparse)
        if BM25_AVAILABLE:
            try:
                bm25_file = self.index_path / "bm25.pkl"
                if bm25_file.exists():
                    with open(bm25_file, 'rb') as f:
                        self.bm25_data = pickle.load(f)
                        self.bm25_index = self.bm25_data['bm25']
                    logger.info(f"Loaded BM25 index with {len(self.bm25_data['chunk_ids'])} docs")
                else:
                    logger.warning(f"BM25 index not found at {bm25_file}")
            except Exception as e:
                logger.error(f"Error loading BM25: {e}")
        else:
            logger.warning("BM25 not available")

    def _dense_search(
        self,
        query: str,
        top_k: int = 10,
        doc_types: Optional[List[str]] = None,
        method_names: Optional[List[str]] = None
    ) -> List[RetrievalResult]:
        """Dense vector search using Chroma."""
        if not self.chroma_collection:
            return []

        # Build metadata filter
        where = {}
        if doc_types:
            where['doc_type'] = {'$in': doc_types}
        if method_names:
            where['method_name'] = {'$in': method_names}

        # Query
        try:
            results = self.chroma_collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where if where else None
            )

            # Convert to RetrievalResult
            retrieval_results = []
            if results['ids'] and results['ids'][0]:
                for i, chunk_id in enumerate(results['ids'][0]):
                    metadata = results['metadatas'][0][i]
                    content = results['documents'][0][i]
                    distance = results['distances'][0][i] if 'distances' in results else 0.0

                    # Convert distance to similarity score (lower distance = higher score)
                    score = 1.0 / (1.0 + distance)

                    retrieval_results.append(RetrievalResult(
                        chunk_id=chunk_id,
                        content=content,
                        score=score,
                        heading=metadata.get('heading', ''),
                        header_path=json.loads(metadata.get('header_path', '[]')),
                        method_name=metadata.get('method_name', ''),
                        doc_type=metadata.get('doc_type', 'api'),
                        source=metadata.get('source', ''),
                        retrieval_method='dense'
                    ))

            return retrieval_results

        except Exception as e:
            logger.error(f"Error in dense search: {e}")
            return []

    def _sparse_search(
        self,
        query: str,
        top_k: int = 10,
        doc_types: Optional[List[str]] = None,
        method_names: Optional[List[str]] = None
    ) -> List[RetrievalResult]:
        """Sparse BM25 search."""
        if not self.bm25_index or not self.bm25_data:
            return []

        try:
            # Tokenize query
            query_tokens = self.tokenizer(query)

            # Get BM25 scores
            scores = self.bm25_index.get_scores(query_tokens)

            # Get top-k indices
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

            # Filter and convert to RetrievalResult
            retrieval_results = []
            for idx in top_indices:
                if len(retrieval_results) >= top_k:
                    break

                chunk_meta = self.bm25_data['chunks_metadata'][idx]

                # Apply filters
                if doc_types and chunk_meta['doc_type'] not in doc_types:
                    continue
                if method_names and chunk_meta['method_name'] not in method_names:
                    continue

                retrieval_results.append(RetrievalResult(
                    chunk_id=chunk_meta['chunk_id'],
                    content=chunk_meta['content'],
                    score=float(scores[idx]),
                    heading=chunk_meta['heading'],
                    header_path=chunk_meta['header_path'],
                    method_name=chunk_meta['method_name'],
                    doc_type=chunk_meta['doc_type'],
                    source=chunk_meta['source'],
                    retrieval_method='sparse'
                ))

            return retrieval_results

        except Exception as e:
            logger.error(f"Error in sparse search: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[RetrievalResult],
        sparse_results: List[RetrievalResult],
        k: int = 60
    ) -> List[RetrievalResult]:
        """
        Combine results using Reciprocal Rank Fusion (RRF).

        RRF score = sum(1 / (k + rank))
        """
        # Build score maps
        rrf_scores = {}
        chunk_data = {}

        # Add dense results
        for rank, result in enumerate(dense_results):
            score = self.dense_weight / (k + rank + 1)
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + score
            chunk_data[result.chunk_id] = result

        # Add sparse results
        for rank, result in enumerate(sparse_results):
            score = self.sparse_weight / (k + rank + 1)
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + score
            if result.chunk_id not in chunk_data:
                chunk_data[result.chunk_id] = result

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        # Create merged results
        merged_results = []
        for chunk_id in sorted_ids:
            result = chunk_data[chunk_id]
            result.score = rrf_scores[chunk_id]
            result.retrieval_method = 'hybrid'
            merged_results.append(result)

        return merged_results

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        doc_types: Optional[List[str]] = None,
        method_names: Optional[List[str]] = None,
        use_hybrid: bool = True
    ) -> List[RetrievalResult]:
        """
        Main retrieval method.

        Args:
            query: Search query
            top_k: Number of results to return
            doc_types: Filter by document types (e.g., ['api', 'methodology'])
            method_names: Filter by method names (e.g., ['cellpose', 'rnascope'])
            use_hybrid: If True, use hybrid retrieval; if False, use only dense

        Returns:
            List of retrieval results sorted by relevance
        """
        if use_hybrid and self.bm25_index and self.chroma_collection:
            # Hybrid retrieval
            logger.debug(f"Hybrid retrieval for query: {query[:50]}...")

            # Get more results from each method for better fusion
            dense_k = top_k * 3
            sparse_k = top_k * 3

            dense_results = self._dense_search(query, dense_k, doc_types, method_names)
            sparse_results = self._sparse_search(query, sparse_k, doc_types, method_names)

            # Fuse results
            fused_results = self._reciprocal_rank_fusion(dense_results, sparse_results)

            return fused_results[:top_k]

        elif self.chroma_collection:
            # Dense only
            logger.debug(f"Dense retrieval for query: {query[:50]}...")
            return self._dense_search(query, top_k, doc_types, method_names)

        elif self.bm25_index:
            # Sparse only
            logger.debug(f"Sparse retrieval for query: {query[:50]}...")
            return self._sparse_search(query, top_k, doc_types, method_names)

        else:
            logger.error("No retrieval index available")
            return []

    def retrieve_by_method(
        self,
        query: str,
        method_name: str,
        top_k: int = 5
    ) -> List[RetrievalResult]:
        """
        Retrieve docs for a specific method.
        Useful for Generator agent to get method-specific parameters.
        """
        return self.retrieve(
            query=query,
            top_k=top_k,
            method_names=[method_name]
        )

    def retrieve_for_agent(
        self,
        query: str,
        agent_type: str,
        top_k: int = 5
    ) -> List[RetrievalResult]:
        """
        Agent-specific retrieval with doc_type filtering.

        Args:
            query: Search query
            agent_type: 'clarifier', 'generator', or 'reviewer'
            top_k: Number of results

        Returns:
            Filtered results based on agent needs
        """
        if agent_type == 'clarifier':
            # Clarifier needs methodology and general API info
            doc_types = ['api', 'methodology']
        elif agent_type == 'generator':
            # Generator needs API specs and schemas
            doc_types = ['api', 'schema']
        elif agent_type == 'reviewer':
            # Reviewer needs all types
            doc_types = None
        else:
            doc_types = None

        return self.retrieve(
            query=query,
            top_k=top_k,
            doc_types=doc_types
        )

    def format_context(self, results: List[RetrievalResult], max_tokens: int = 4000) -> str:
        """
        Format retrieval results into context string for LLM.

        Args:
            results: Retrieval results
            max_tokens: Maximum tokens for context

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        context_parts = []
        total_tokens = 0

        for i, result in enumerate(results):
            # Estimate tokens (rough: 4 chars per token)
            result_tokens = len(result.content) // 4

            if total_tokens + result_tokens > max_tokens:
                break

            # Format single result
            part = f"""### [{i+1}] {result.heading}
Source: {result.source}
Method: {result.method_name or 'N/A'}

{result.content}

---
"""
            context_parts.append(part)
            total_tokens += result_tokens

        return "\n".join(context_parts)
