"""Agent 2: Workplan Generator

Creates structured workplan JSON based on requirements.
"""

from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json
import logging
import os

logger = logging.getLogger(__name__)


class GeneratorAgent:
    """
    Agent 2: Workplan Generator

    Creates structured workplan JSON that specifies which APIs to call
    for microscopy image analysis.
    """

    def __init__(self, api_key: str, base_url: str, model: str, system_prompt_path: Optional[str] = None):
        self.llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=0.1,  # Lower temp for structured output
        )

        # Load the comprehensive system prompt
        if system_prompt_path and os.path.exists(system_prompt_path):
            with open(system_prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
            logger.info(f"Loaded system prompt from {system_prompt_path}")
        else:
            logger.warning("System prompt file not found, using basic prompt")
            self.system_prompt = self._get_basic_prompt()

    def _get_basic_prompt(self) -> str:
        """Fallback basic prompt if main prompt file not found."""
        return """
You are a workplan generator for microscopy image analysis.

Generate a JSON workplan with the following structure:
{
  "experimentName": "string",
  "inputMode": "single_rgb_merged_image",
  "analysisGoal": "string",
  "imageInference": {
    "imageModality": "fluorescence|brightfield|brightfield_ihc",
    "experimentType": "cellular_analysis",
    "reasoning": ["reason1", "reason2"]
  },
  "workplanSceneType": "target_based_analysis",
  "channels": [
    {
      "channelId": "ch0",
      "channelName": "DAPI",
      "semanticRole": "nuclei_marker"
    }
  ],
  "targets": [
    {
      "targetName": "all_nuclei",
      "targetType": "total_roi",
      "description": "All nuclei detected"
    }
  ],
  "jobs": [
    {
      "jobId": "job_00",
      "jobName": "Split channels",
      "jobType": "pic_split",
      "stepDescript": "Split RGB channels",
      "inputs": {},
      "outputs": {},
      "picSplitPlan": {
        "splitMethod": "rgb_split",
        "channelMapping": {}
      }
    },
    {
      "jobId": "job_99",
      "jobName": "Calculate results",
      "jobType": "formula",
      "stepDescript": "Calculate final metrics",
      "inputs": {},
      "outputs": {},
      "formulaPlan": {
        "expression": "target.COUNT",
        "reportFields": [
          {
            "fieldName": "count",
            "displayName": "细胞数",
            "unit": "个",
            "description": "Total cell count"
          }
        ]
      }
    }
  ]
}

Output ONLY valid JSON. No markdown, no explanations.
"""

    async def generate_workplan(
        self, requirements: dict, feedback: Optional[dict] = None
    ) -> dict:
        """Generate workplan from requirements."""

        logger.info("Generating workplan")

        # Build context
        context = self._build_context(requirements, feedback)

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=context),
        ]

        # Generate workplan
        response = await self.llm.ainvoke(messages)

        # Parse JSON
        workplan = self._parse_workplan(response.content)

        logger.info(f"Generated workplan with {len(workplan.get('jobs', []))} jobs")

        return workplan

    def _build_context(
        self, requirements: dict, feedback: Optional[dict]
    ) -> str:
        """Build context for workplan generation."""

        context = f"""
Generate a complete workplan for the following requirements:

{json.dumps(requirements, indent=2)}
"""

        if feedback:
            context += f"""

Previous workplan was rejected with the following issues:
{json.dumps(feedback, indent=2)}

Please address these issues in the new workplan.
"""

        context += """

Output ONLY the complete workplan JSON.
Do NOT include markdown code blocks.
Do NOT include explanations.
Output ONLY valid JSON.
"""

        return context

    def _parse_workplan(self, content: str) -> dict:
        """Parse and validate workplan JSON."""

        # Remove markdown if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        try:
            workplan = json.loads(content)
            logger.info("Successfully parsed workplan JSON")
            return workplan
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse workplan JSON: {e}")
            logger.error(f"Content: {content[:200]}...")
            raise ValueError(f"Failed to parse workplan JSON: {e}")
