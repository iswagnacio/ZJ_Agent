#!/usr/bin/env python3
"""
Knowledge base indexing pipeline.

Builds both dense (Chroma) and sparse (BM25) indices from API documentation.

Usage:
    python build_knowledge_index.py [--force-rebuild] [--validate-only]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.knowledge.rag import KnowledgeIndexer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Build knowledge base indices')
    parser.add_argument(
        '--kb-path',
        type=str,
        default='../api_docs',
        help='Path to knowledge base (markdown files)'
    )
    parser.add_argument(
        '--output-path',
        type=str,
        default='kb_index',
        help='Path to output indices'
    )
    parser.add_argument(
        '--force-rebuild',
        action='store_true',
        help='Force rebuild even if indices exist'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate existing indices'
    )
    parser.add_argument(
        '--embedding-model',
        type=str,
        default='text-embedding-3-small',
        help='OpenAI embedding model name'
    )

    args = parser.parse_args()

    # Resolve paths
    kb_path = Path(args.kb_path)
    if not kb_path.is_absolute():
        kb_path = (Path(__file__).parent / kb_path).resolve()

    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = (Path(__file__).parent / output_path).resolve()

    logger.info(f"Knowledge base path: {kb_path}")
    logger.info(f"Output path: {output_path}")

    # Validate KB path exists
    if not kb_path.exists():
        logger.error(f"Knowledge base path does not exist: {kb_path}")
        sys.exit(1)

    # Initialize indexer
    indexer = KnowledgeIndexer(
        knowledge_base_path=str(kb_path),
        index_output_path=str(output_path),
        embedding_model=args.embedding_model
    )

    if args.validate_only:
        # Validate only
        logger.info("Running validation only...")
        stats = indexer.validate_index()

        print("\n=== Validation Results ===")
        print(f"Total chunks: {stats.get('total_chunks', 0)}")
        print(f"Avg tokens: {stats.get('avg_tokens', 0):.1f}")
        print(f"Max tokens: {stats.get('max_tokens', 0)}")
        print(f"Min tokens: {stats.get('min_tokens', 0)}")
        print(f"\nDoc type distribution: {stats.get('doc_type_distribution', {})}")
        print(f"Method name coverage: {stats.get('method_name_coverage', 0):.1%}")

        if stats.get('issues'):
            print("\n⚠️  Issues found:")
            for issue in stats['issues']:
                print(f"  - {issue}")
            sys.exit(1)
        else:
            print("\n✅ All validation checks passed!")
            sys.exit(0)

    else:
        # Build indices
        logger.info("Building knowledge base indices...")

        result = indexer.build_all(force_rebuild=args.force_rebuild)

        if result.get('success'):
            print("\n=== Indexing Complete ===")
            print(f"✅ Successfully indexed {result['num_files']} files")
            print(f"✅ Created {result['num_chunks']} chunks")
            print(f"\nOutput directory: {output_path}")
            print(f"  - chunks.jsonl: Ground truth chunks")
            print(f"  - chroma/: Dense vector index")
            print(f"  - bm25.pkl: Sparse BM25 index")
            print(f"  - manifest.json: Build metadata")

            # Run validation
            print("\nRunning validation...")
            stats = indexer.validate_index()

            if stats.get('valid'):
                print("✅ Validation passed!")
            else:
                print("⚠️  Validation warnings:")
                for issue in stats.get('issues', []):
                    print(f"  - {issue}")

            sys.exit(0)
        else:
            logger.error("Indexing failed!")
            sys.exit(1)


if __name__ == '__main__':
    main()
