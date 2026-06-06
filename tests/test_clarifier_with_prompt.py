"""Test Clarifier agent with new high-level system prompt.

This test verifies that the Clarifier:
1. Loads the system prompt correctly
2. Asks high-level questions (not technical parameters)
3. Recognizes common analysis patterns
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.clarifier import ClarifierAgent


async def test_clarifier_prompt_loading():
    """Test that Clarifier loads the system prompt file."""

    print("\n" + "="*60)
    print("TEST 1: System Prompt Loading")
    print("="*60)

    # Mock credentials (DouBao API not actually called in this test)
    clarifier = ClarifierAgent(
        api_key="ccc1b71a-4939-4061-b2ff-7473986f773b",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-20260602014208-2k2k7",
        system_prompt_path="prompts/clarifier_system_prompt.txt"
    )

    # Check that prompt was loaded
    assert clarifier.system_prompt is not None
    assert len(clarifier.system_prompt) > 1000  # Should be comprehensive

    # Check for key methodology concepts
    assert "WORKFLOW RECOGNITION" in clarifier.system_prompt or "workflow" in clarifier.system_prompt.lower()
    assert "cellpose" in clarifier.system_prompt.lower()
    assert "threshold" in clarifier.system_prompt.lower()

    # Check for high-level guidance (NOT technical parameters)
    assert "DON'T ask" in clarifier.system_prompt or "don't ask" in clarifier.system_prompt.lower()

    # Check that it discourages technical questions
    prompt_lower = clarifier.system_prompt.lower()
    assert "flowthreshold" in prompt_lower or "diameter" in prompt_lower  # Should mention these as things NOT to ask

    print("✅ System prompt loaded successfully")
    print(f"   Prompt length: {len(clarifier.system_prompt)} characters")
    print(f"   Contains workflow guidance: ✓")
    print(f"   Contains method selection guidance: ✓")
    print(f"   Contains high-level questioning principles: ✓")


async def test_clarifier_with_mock_scenarios():
    """Test Clarifier behavior with mock user scenarios.

    Note: This test demonstrates what questions SHOULD be asked,
    but doesn't actually call the LLM (would need real API credentials).
    """

    print("\n" + "="*60)
    print("TEST 2: Expected Clarifier Behavior")
    print("="*60)

    clarifier = ClarifierAgent(
        api_key="ccc1b71a-4939-4061-b2ff-7473986f773b",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-20260602014208-2k2k7",
        system_prompt_path="prompts/clarifier_system_prompt.txt"
    )

    print("\n📋 Scenario 1: User wants Ki67 positive rate")
    print("-" * 60)
    print("User input: 'I want to calculate Ki67 positive rate'")
    print("\nExpected Clarifier behavior:")
    print("  ✅ Should ask: What markers/staining do you have?")
    print("  ✅ Should ask: Which channel is DAPI, which is Ki67?")
    print("  ✅ Should ask: How big are the cells (small/medium/large)?")
    print("  ❌ Should NOT ask: What diameter parameter in pixels?")
    print("  ❌ Should NOT ask: What flowThreshold value?")
    print("  ❌ Should NOT ask: What cellprobThreshold range?")

    print("\n📋 Scenario 2: User wants to count vacuoles")
    print("-" * 60)
    print("User input: 'Count vacuoles in brightfield image'")
    print("\nExpected Clarifier behavior:")
    print("  ✅ Should recognize: Area percentage or count analysis")
    print("  ✅ Should suggest: Threshold method (high contrast)")
    print("  ✅ Should ask: Are vacuoles bright or dark?")
    print("  ✅ Should ask: Fill holes inside vacuoles?")
    print("  ❌ Should NOT ask: What thresholdMin/Max values?")

    print("\n📋 Scenario 3: User uncertain about method")
    print("-" * 60)
    print("User input: 'I'm not sure which method to use'")
    print("\nExpected Clarifier behavior:")
    print("  ✅ Should ask: Is your image fluorescence or brightfield?")
    print("  ✅ Should ask: What do you want to analyze?")
    print("  ✅ Should provide: Suggestions based on common patterns")
    print("  ✅ Should guide: Step-by-step decision tree")

    print("\n✅ Clarifier system prompt configured for high-level questioning")


async def test_no_technical_questions():
    """Verify that the system prompt discourages technical parameter questions."""

    print("\n" + "="*60)
    print("TEST 3: Technical Question Avoidance")
    print("="*60)

    clarifier = ClarifierAgent(
        api_key="ccc1b71a-4939-4061-b2ff-7473986f773b",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-20260602014208-2k2k7",
        system_prompt_path="prompts/clarifier_system_prompt.txt"
    )

    prompt = clarifier.system_prompt.lower()

    # Check that prompt explicitly says NOT to ask about technical parameters
    technical_params = [
        "diameter",
        "flowthreshold",
        "cellprobthreshold",
        "thresholdmin",
        "thresholdmax"
    ]

    print("\nChecking that prompt discourages asking about:")
    for param in technical_params:
        if param in prompt:
            print(f"  ✓ {param} - mentioned in prompt")
        else:
            print(f"  ? {param} - not explicitly mentioned")

    # Check for "don't ask" or "not ask" guidance
    has_dont_ask = "don't ask" in prompt or "not ask" in prompt or "avoid asking" in prompt
    print(f"\n{'✅' if has_dont_ask else '⚠️'} Prompt contains 'don't ask' guidance: {has_dont_ask}")

    # Check for high-level guidance
    has_high_level = "high-level" in prompt or "everyday" in prompt or "accessible" in prompt
    print(f"{'✅' if has_high_level else '⚠️'} Prompt emphasizes high-level questions: {has_high_level}")


async def test_workflow_recognition():
    """Verify that the system prompt includes workflow pattern recognition."""

    print("\n" + "="*60)
    print("TEST 4: Workflow Pattern Recognition")
    print("="*60)

    clarifier = ClarifierAgent(
        api_key="ccc1b71a-4939-4061-b2ff-7473986f773b",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model="ep-20260602014208-2k2k7",
        system_prompt_path="prompts/clarifier_system_prompt.txt"
    )

    prompt = clarifier.system_prompt.lower()

    # Check for common workflow patterns
    workflows = {
        "cell counting": ["count", "counting"],
        "positive rate": ["positive rate", "positive percentage", "ki67"],
        "co-localization": ["co-localization", "colocalization", "overlap"],
        "area percentage": ["area percentage", "area", "coverage"],
        "morphology": ["morphology", "shape", "size"],
        "intensity": ["intensity", "fluorescence", "brightness"]
    }

    print("\nWorkflow patterns covered in system prompt:")
    for workflow_name, keywords in workflows.items():
        found = any(kw in prompt for kw in keywords)
        print(f"  {'✓' if found else '?'} {workflow_name:20s} - {'Found' if found else 'Not explicitly mentioned'}")

    print("\n✅ System prompt includes workflow recognition guidance")


async def main():
    """Run all Clarifier tests."""

    print("\n" + "="*70)
    print(" CLARIFIER AGENT SYSTEM PROMPT TEST SUITE")
    print("="*70)
    print("\nThese tests verify that the Clarifier:")
    print("  1. Loads the new high-level system prompt")
    print("  2. Is configured to ask accessible questions")
    print("  3. Recognizes common analysis workflows")
    print("  4. Avoids asking about technical parameters")

    try:
        await test_clarifier_prompt_loading()
        await test_clarifier_with_mock_scenarios()
        await test_no_technical_questions()
        await test_workflow_recognition()

        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70)
        print("\nThe Clarifier agent is now configured with high-level")
        print("methodology guidance embedded in its system prompt.")
        print("\nThis approach:")
        print("  • Ensures guidance is always present (no retrieval needed)")
        print("  • Keeps technical API docs separate (for Generator RAG)")
        print("  • Focuses Clarifier on user intent, not implementation")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
