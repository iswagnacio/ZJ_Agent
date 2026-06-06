#!/usr/bin/env python3
"""
Test RAG system with actual methods from API docs.

Real methods: threshold, cellpose, weka
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.knowledge.rag import HybridRetriever


def main():
    """Test with real API methods."""

    retriever = HybridRetriever(index_path="kb_index")

    print("\n" + "="*80)
    print("Testing RAG with Real API Methods")
    print("="*80)

    # Test 1: Cellpose parameters
    print("\n📋 Test 1: Cellpose Parameters")
    print("-"*80)
    results = retriever.retrieve_by_method(
        query="diameter flowThreshold cellprobThreshold parameters",
        method_name="cellpose",
        top_k=3
    )
    print(f"Found {len(results)} results for cellpose:")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.heading} (score: {r.score:.4f})")
        print(f"      {r.content[:150]}...\n")

    # Test 2: Threshold parameters
    print("\n📋 Test 2: Threshold Parameters")
    print("-"*80)
    results = retriever.retrieve_by_method(
        query="thresholdMin thresholdMax binary parameters",
        method_name="threshold",
        top_k=3
    )
    print(f"Found {len(results)} results for threshold:")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.heading} (score: {r.score:.4f})")
        print(f"      {r.content[:150]}...\n")

    # Test 3: Weka parameters
    print("\n📋 Test 3: Weka Parameters")
    print("-"*80)
    results = retriever.retrieve_by_method(
        query="classifier parameters",
        method_name="weka",
        top_k=2
    )
    print(f"Found {len(results)} results for weka:")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.heading} (score: {r.score:.4f})")
        print(f"      {r.content[:150]}...\n")

    # Test 4: ROI rendering (cross-API)
    print("\n📋 Test 4: ROI Rendering Parameters (Cross-API)")
    print("-"*80)
    results = retriever.retrieve(
        query="ROI rendering contourColor contourWidthPixels renderMaskOverlay",
        top_k=5
    )
    print(f"Found {len(results)} results for ROI rendering:")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.source} - {r.heading} (score: {r.score:.4f})")

    # Test 5: Semantic query in Chinese
    print("\n📋 Test 5: Semantic Chinese Query")
    print("-"*80)
    results = retriever.retrieve(
        query="如何使用 cellpose 进行细胞分割",
        top_k=3
    )
    print(f"Found {len(results)} results:")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.heading} (score: {r.score:.4f}, method: {r.method_name or 'N/A'})")

    # Test 6: Format context for Generator
    print("\n📋 Test 6: Format Context for Generator Agent")
    print("-"*80)
    results = retriever.retrieve_for_agent(
        query="cellpose segmentation parameters model diameter",
        agent_type="generator",
        top_k=3
    )
    context = retriever.format_context(results, max_tokens=2000)
    print(f"Context generated ({len(context)} chars):")
    print(context[:500] + "...\n")

    print("\n✅ All tests completed successfully!\n")


if __name__ == '__main__':
    main()
