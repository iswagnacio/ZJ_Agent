"""Agent 1: Requirement Clarifier

Extracts complete requirements through conversational dialogue.
"""

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json
import logging

logger = logging.getLogger(__name__)


class ClarifierAgent:
    """
    Agent 1: Requirement Clarifier

    Analyzes microscope images and engages in dialogue with users
    to extract complete, unambiguous requirements.
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=0.3,
        )

        self.system_prompt = """
You are an expert microscopy image analysis consultant.
Your job is to understand the user's analysis needs by:
1. Analyzing the microscope image they provide
2. Asking specific, targeted questions to clarify ambiguities
3. Building a complete requirement specification

Common things to clarify:
- What does each color/channel represent? (e.g., DAPI=nuclei, GFP=protein)
- What objects need to be detected? (cells, nuclei, regions, structures)
- What measurements are needed? (count, area, intensity, ratio, colocalization)
- Are there spatial relationships? (colocalization, inside/outside, distance)
- Should border objects be excluded?
- Are there size constraints? (min/max cell size, diameter)
- What is the final output format? (metrics, visualizations)

IMPORTANT:
- Ask questions ONE topic at a time. Don't overwhelm the user.
- Be specific and reference what you see in the image.
- When you have all necessary information, respond with JSON:
  {"status": "complete", "requirements": {...}}
- When you need more information, respond with JSON:
  {"status": "need_clarification", "questions": ["your question here"]}
"""

    async def analyze_initial_input(
        self, image_url: str, description: str
    ) -> Dict[str, Any]:
        """Analyze the initial image and description."""

        logger.info("Analyzing initial input")

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(
                content=[
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {
                        "type": "text",
                        "text": f"User description: {description}\n\nAnalyze this microscope image and ask your first clarifying questions. Output JSON only.",
                    },
                ]
            ),
        ]

        response = await self.llm.ainvoke(messages)
        return self._parse_response(response.content)

    async def process_user_response(
        self, conversation_history: list, user_response: str
    ) -> Dict[str, Any]:
        """Process user's response to clarification questions."""

        logger.info(f"Processing user response: {user_response[:50]}...")

        # Build conversation context
        messages = [SystemMessage(content=self.system_prompt)]

        for turn in conversation_history:
            if "agent_message" in turn:
                messages.append(HumanMessage(content=f"Agent: {turn['agent_message']}"))
            if "user_response" in turn:
                messages.append(HumanMessage(content=f"User: {turn['user_response']}"))

        # Add latest response
        messages.append(
            HumanMessage(
                content=f"User: {user_response}\n\nContinue clarification or output completion JSON if you have all information. Output JSON only."
            )
        )

        response = await self.llm.ainvoke(messages)
        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse agent response."""
        try:
            # Try to parse as JSON
            content = content.strip()

            # Remove markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            if content.startswith("{"):
                parsed = json.loads(content)
                logger.info(f"Parsed response: {parsed.get('status')}")
                return parsed

            # Otherwise, treat as questions
            return {"status": "need_clarification", "questions": [content]}

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}, treating as question")
            return {"status": "need_clarification", "questions": [content]}

    def extract_requirements(self, conversation_history: list) -> dict:
        """Extract structured requirements from conversation."""

        logger.info("Extracting requirements from conversation")

        # Basic extraction - in production, you'd use LLM to structure this
        requirements = {
            "experiment_type": "Microscopy Analysis",
            "image_modality": "unknown",
            "channels": {},
            "analysis_goal": "Image analysis",
            "target_objects": {},
            "output_requirements": {"metrics": []},
            "special_considerations": [],
        }

        # Extract from conversation (simplified)
        for turn in conversation_history:
            user_resp = turn.get("user_response", "").lower()

            # Detect modality
            if "fluorescence" in user_resp or "dapi" in user_resp:
                requirements["image_modality"] = "fluorescence"
            elif "brightfield" in user_resp or "ihc" in user_resp or "dab" in user_resp:
                requirements["image_modality"] = "brightfield"

            # Detect channels
            if "dapi" in user_resp:
                requirements["channels"]["ch0"] = "DAPI (nuclei)"
            if "ki67" in user_resp or "gfp" in user_resp:
                requirements["channels"]["ch1"] = "Ki67 or GFP"

            # Detect goal
            if "count" in user_resp:
                requirements["analysis_goal"] = "Cell counting"
            if "positive" in user_resp:
                requirements["analysis_goal"] = "Positive cell detection"

        return requirements
