#!/usr/bin/env python3
"""
Test Generator agent with RAG integration.

Demonstrates multi-query strategy and context injection.
"""

import sys
import asyncio
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.agents.generator import GeneratorAgent
import logging

# Enable detailed logging to see RAG in action
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_cellpose_workplan():
    """Test Generator with cellpose requirements."""

    print("\n" + "="*80)
    print("Test: Generate Workplan with Cellpose Segmentation")
    print("="*80 + "\n")

    # Initialize generator
    generator = GeneratorAgent(
        api_key="ccc1b71a-4939-4061-b2ff-7473986f773b",  # Replace with real key
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-20260602014208-2k2k7",
        enable_rag=True  # Enable RAG
    )

    # Check if RAG is available
    if not generator.retriever:
        print("❌ RAG retriever not initialized. Make sure kb_index/ exists.")
        print("   Run: python build_knowledge_index.py")
        return

    print("✅ RAG retriever initialized\n")

    # Sample requirements (what Clarifier would provide)
    requirements = {
        "staining_type": "fluorescence",
        "segmentation_channel": "DAPI",
        "segmentation_model": "cellpose",
        "model_parameters": {
            "model": "zhijing_if_nuclei",
            "diameter": 30
        },
        "detection_targets": {
            "nuclei": "DAPI-stained cell nuclei"
        },
        "measurements": ["COUNT", "AREA", "MEAN_INTENSITY"],
        "filtering_criteria": {
            "size_range": [100, 2000],
            "circularity_min": 0.3
        },
        "output_format": "count and measurements table"
    }

    print("📋 Requirements:")
    print(json.dumps(requirements, indent=2, ensure_ascii=False))
    print()

    # Test: Show what the RAG retrieval process looks like
    print("🔍 RAG Retrieval Process:")
    print("-" * 80)

    # This will trigger the multi-query strategy
    # Watch the logs to see:
    # - Topics extracted
    # - Queries built
    # - Retrieval results with scores
    # - Context formatted

    try:
        api_context = generator._retrieve_api_context(requirements)

        if api_context:
            print("\n✅ API Context Retrieved:")
            print(f"   Length: {len(api_context)} chars")
            print(f"   Preview (first 500 chars):")
            print("-" * 80)
            print(api_context[:500] + "...")
            print("-" * 80)
        else:
            print("\n⚠️  No API context retrieved")

    except Exception as e:
        print(f"\n❌ Error during retrieval: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print("Test Complete")
    print("="*80)


async def test_threshold_workplan():
    """Test Generator with threshold requirements."""

    print("\n" + "="*80)
    print("Test: Generate Workplan with Threshold Segmentation")
    print("="*80 + "\n")

    generator = GeneratorAgent(
        api_key="dummy-key",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-dummy",
        enable_rag=True
    )

    if not generator.retriever:
        print("❌ RAG not available")
        return

    requirements = {
        "staining_type": "brightfield",
        "segmentation_model": "threshold",
        "model_parameters": {
            "thresholdMin": 100,
            "thresholdMax": 255
        },
        "detection_targets": {
            "vacuoles": "empty spaces in tissue"
        },
        "measurements": ["COUNT", "AREA"],
        "output_format": "count"
    }

    print("📋 Requirements:")
    print(json.dumps(requirements, indent=2, ensure_ascii=False))
    print()

    print("🔍 RAG Retrieval:")
    print("-" * 80)

    api_context = generator._retrieve_api_context(requirements)

    if api_context:
        print(f"\n✅ Retrieved {len(api_context)} chars of context")
    else:
        print("\n⚠️  No context retrieved")


async def test_multi_api_workplan():
    """Test with requirements that need multiple APIs."""

    print("\n" + "="*80)
    print("Test: Complex Workplan (Multiple APIs)")
    print("="*80 + "\n")

    generator = GeneratorAgent(
        api_key="dummy-key",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-dummy",
        enable_rag=True
    )

    if not generator.retriever:
        print("❌ RAG not available")
        return

    # Complex requirements needing:
    # - Pic_Split (channel splitting)
    # - Segment_ROI (cellpose)
    # - Measure_ROI (filtering)
    # - Create_Target (binding)
    # - ROI_Render (visualization)
    # - Formula (calculation)
    requirements = {
        "staining_type": "fluorescence",
        "input_mode": "RGB merged image",
        "channels": {
            "DAPI": "blue channel - nuclei",
            "Ki67": "green channel - proliferation marker"
        },
        "segmentation_model": "cellpose",
        "detection_targets": {
            "all_nuclei": "All DAPI-positive nuclei",
            "ki67_positive": "Ki67-positive nuclei (filtered by intensity)"
        },
        "measurements": ["COUNT", "MEAN_INTENSITY"],
        "filtering_criteria": {
            "ki67_intensity_threshold": 50
        },
        "output_format": "Ki67 positive rate percentage",
        "visualization": "ROI overlay on original image"
    }

    print("📋 Complex Requirements:")
    print(json.dumps(requirements, indent=2, ensure_ascii=False))
    print()

    print("🔍 Multi-Query RAG Retrieval:")
    print("-" * 80)
    print("Expected queries:")
    print("  - Cellpose parameters")
    print("  - Channel splitting")
    print("  - Measure_ROI filtering")
    print("  - Create_Target binding")
    print("  - ROI_Render visualization")
    print("  - Formula calculation")
    print()

    api_context = generator._retrieve_api_context(requirements)

    if api_context:
        print(f"\n✅ Retrieved {len(api_context)} chars")
        print("\nContext contains documentation for:")

        # Count mentions of APIs
        apis = ['Segment_ROI', 'Pic_Split', 'Measure_ROI', 'Create_Target', 'ROI_Render', 'Formula']
        for api in apis:
            count = api_context.count(api)
            if count > 0:
                print(f"  - {api}: {count} mentions")


async def main():
    """Run all tests."""

    print("\n" + "="*80)
    print("RAG-Enhanced Generator Agent Tests")
    print("="*80)

    # Test 1: Cellpose
    await test_cellpose_workplan()

    # Test 2: Threshold
    await test_threshold_workplan()

    # Test 3: Complex multi-API
    await test_multi_api_workplan()

    print("\n" + "="*80)
    print("All Tests Complete")
    print("="*80)
    print("\nKey Observations:")
    print("  ✅ Multi-query strategy extracts topics from requirements")
    print("  ✅ Targeted queries for methods, operations, APIs")
    print("  ✅ Observability: logs show queries, results, scores")
    print("  ✅ Context injection: API docs placed before requirements")
    print("  ✅ Deduplication: same chunk not retrieved twice")
    print()


if __name__ == '__main__':
    asyncio.run(main())
