#!/usr/bin/env python3
"""
Example REST API client for the workplan generator web service.

This demonstrates how to integrate with the API from a Python client.
Your frontend application should make similar HTTP requests.

Usage:
    python test_client.py path/to/image.png "Count cells"

This is NOT the primary usage method - it's just an example integration.
The primary interface is the REST API at http://localhost:8000
"""

import requests
import sys
import time
from pathlib import Path


def test_workplan_generation(image_path: str, description: str):
    """Test the complete workplan generation flow."""

    base_url = "http://localhost:8000"

    print("=" * 60)
    print("Workplan Generator - Test Client")
    print("=" * 60)

    # Check health
    print("\n1. Checking API health...")
    try:
        response = requests.get(f"{base_url}/health")
        response.raise_for_status()
        print("   ✓ API is healthy")
    except Exception as e:
        print(f"   ✗ API not accessible: {e}")
        print("   Make sure the server is running: uvicorn src.api.main:app --reload")
        return

    # Create session
    print(f"\n2. Creating session...")
    print(f"   Image: {image_path}")
    print(f"   Description: {description}")

    try:
        with open(image_path, "rb") as f:
            response = requests.post(
                f"{base_url}/sessions",
                files={"image": f},
                data={"description": description},
            )
        response.raise_for_status()
        data = response.json()
        session_id = data["session_id"]
        print(f"   ✓ Session created: {session_id}")
    except Exception as e:
        print(f"   ✗ Failed to create session: {e}")
        return

    # Clarification loop
    print("\n3. Clarification phase...")
    clarification_count = 0

    while True:
        try:
            response = requests.get(f"{base_url}/sessions/{session_id}")
            response.raise_for_status()
            status = response.json()

            state = status["state"]
            print(f"   State: {state}")

            if state == "clarification":
                clarification_count += 1
                questions = status.get("questions", [])

                if questions:
                    print(f"\n   Question {clarification_count}:")
                    print(f"   {questions[0]}")
                    print()

                    # Get user input
                    answer = input("   Your answer: ").strip()

                    if not answer:
                        print("   (Skipping - no answer provided)")
                        continue

                    # Submit response
                    response = requests.post(
                        f"{base_url}/sessions/{session_id}/respond",
                        json={"response": answer},
                    )
                    response.raise_for_status()

            elif state == "generating":
                print("   Generating workplan...")
                time.sleep(2)

            elif state == "reviewing":
                print("   Reviewing workplan...")
                time.sleep(2)

            elif state == "user_review":
                print("\n4. Review phase...")
                print("   Workplan ready for review!")

                review = status.get("review", {})
                if review:
                    print(f"\n   Review Score: {review.get('overall_score', 'N/A')}")
                    print(
                        f"   Critical Issues: {len(review.get('critical_issues', []))}"
                    )
                    print(f"   Warnings: {len(review.get('warnings', []))}")

                # Ask user decision
                print("\n   Options:")
                print("   1) Accept workplan")
                print("   2) Restart from generator (Agent 2)")
                print("   3) Restart from clarifier (Agent 1)")

                choice = input("\n   Your choice (1/2/3): ").strip()

                action_map = {
                    "1": "accept",
                    "2": "restart_agent2",
                    "3": "restart_agent1",
                }

                action = action_map.get(choice, "accept")

                response = requests.post(
                    f"{base_url}/sessions/{session_id}/decision",
                    json={"action": action},
                )
                response.raise_for_status()

                if action == "accept":
                    break

            elif state == "completed":
                print("\n5. Completed!")
                break

            elif state == "error":
                print(f"   ✗ Error: {status.get('message')}")
                return

            else:
                print(f"   State: {state}")
                time.sleep(2)

        except KeyboardInterrupt:
            print("\n\n   Interrupted by user")
            return
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return

    # Download workplan
    print("\n6. Downloading workplan...")
    try:
        response = requests.get(f"{base_url}/sessions/{session_id}/workplan")
        response.raise_for_status()
        workplan = response.json()

        # Save to file
        output_file = f"workplan_{session_id[:8]}.json"
        import json

        with open(output_file, "w") as f:
            json.dump(workplan, f, indent=2)

        print(f"   ✓ Workplan saved to: {output_file}")
        print(f"\n   Experiment: {workplan.get('experimentName', 'N/A')}")
        print(f"   Jobs: {len(workplan.get('jobs', []))}")

    except Exception as e:
        print(f"   ✗ Failed to download: {e}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_client.py <image_path> <description>")
        print('Example: python test_client.py image.png "Count Ki67 positive cells"')
        sys.exit(1)

    image_path = sys.argv[1]
    description = sys.argv[2]

    if not Path(image_path).exists():
        print(f"Error: Image file not found: {image_path}")
        sys.exit(1)

    test_workplan_generation(image_path, description)
