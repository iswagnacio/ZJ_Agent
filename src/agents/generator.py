"""Agent 2: Workplan Generator

Creates structured workplan JSON based on requirements.
Enhanced with RAG retrieval for API documentation.
"""

from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Import RAG retriever
try:
    from ..knowledge.rag import HybridRetriever
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logger.warning("RAG module not available, running without knowledge retrieval")


class GeneratorAgent:
    """
    Agent 2: Workplan Generator

    Creates structured workplan JSON that specifies which APIs to call
    for microscopy image analysis.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt_path: Optional[str] = None,
        enable_rag: bool = True,
        kb_index_path: Optional[str] = None
    ):
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

        # Initialize RAG retriever
        self.retriever = None
        if enable_rag and RAG_AVAILABLE:
            # Determine index path
            if kb_index_path:
                index_path = Path(kb_index_path)
            else:
                # Default: kb_index in project root
                index_path = Path(__file__).parent.parent.parent / "kb_index"

            if index_path.exists():
                try:
                    self.retriever = HybridRetriever(
                        index_path=str(index_path),
                        dense_weight=0.5,
                        sparse_weight=0.5
                    )
                    logger.info(f"✅ RAG retriever initialized from {index_path}")
                except Exception as e:
                    logger.error(f"Failed to initialize RAG retriever: {e}")
            else:
                logger.warning(f"KB index not found at {index_path}, RAG disabled")
        elif not RAG_AVAILABLE:
            logger.warning("RAG dependencies not installed, running without knowledge retrieval")

    def _get_basic_prompt(self) -> str:
        """Fallback basic prompt if main prompt file not found."""
        return """You are a workplan generator for microscopy image analysis.

Generate structured JSON workplan that specifies which APIs to call for image analysis.

Output ONLY valid JSON. No markdown, no explanations.
"""

    def _extract_api_topics(self, requirements: dict) -> Dict[str, List[str]]:
        """
        Extract API topics from requirements for targeted retrieval.

        Returns dict with categories: methods, operations, measurements, etc.
        """
        topics = {
            'methods': [],
            'operations': [],
            'apis': [],
            'parameters': []
        }

        req_str = json.dumps(requirements, ensure_ascii=False).lower()

        # Extract segmentation methods
        method_keywords = {
            'cellpose': ['cellpose', '细胞分割', 'cell segmentation', 'deep learning'],
            'threshold': ['threshold', '阈值', '阈值分割', 'binary', '二值'],
            'weka': ['weka', 'trainable', '可训练']
        }

        for method, keywords in method_keywords.items():
            if any(kw in req_str for kw in keywords):
                topics['methods'].append(method)

        # Extract operations
        if 'channel' in req_str or '通道' in req_str or 'split' in req_str:
            topics['operations'].append('channel_split')

        if 'deconvolution' in req_str or '反卷积' in req_str or '色彩分离' in req_str:
            topics['operations'].append('color_deconvolution')

        if 'target' in req_str or '目标' in req_str or 'binding' in req_str:
            topics['apis'].append('Create_Target')

        if 'measure' in req_str or '测量' in req_str or 'filter' in req_str or '筛选' in req_str:
            topics['apis'].append('Measure_ROI')

        if 'render' in req_str or '渲染' in req_str or 'visualization' in req_str:
            topics['apis'].append('ROI_Render')

        if 'formula' in req_str or '公式' in req_str or 'calculation' in req_str or '计算' in req_str:
            topics['apis'].append('Formula')

        return topics

    def _build_targeted_queries(self, requirements: dict, topics: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """
        Build multiple targeted queries based on extracted topics.

        Following the multi-query strategy:
        - Method-specific queries for parameters
        - Operation-specific queries
        - API-specific queries for fields
        """
        queries = []

        # Query 1: Method-specific parameters
        for method in topics['methods']:
            queries.append({
                'query': f"{method} 参数 parameters diameter threshold",
                'method_name': method,
                'description': f'{method} method parameters',
                'priority': 'high'
            })

        # Query 2: Channel/deconvolution operations
        if 'channel_split' in topics['operations']:
            queries.append({
                'query': "通道分割 channel split RGB splitMethod channelMapping",
                'description': 'Channel splitting operations',
                'priority': 'high'
            })

        if 'color_deconvolution' in topics['operations']:
            queries.append({
                'query': "色彩反卷积 color deconvolution H&E DAB staining vector",
                'description': 'Color deconvolution',
                'priority': 'high'
            })

        # Query 3: API-specific fields
        for api in topics['apis']:
            if api == 'Create_Target':
                queries.append({
                    'query': "Create_Target bindSegmentRoi targetName parameters",
                    'description': 'Create_Target API fields',
                    'priority': 'medium'
                })
            elif api == 'Measure_ROI':
                queries.append({
                    'query': "Measure_ROI filterRules featureNames measurementType",
                    'description': 'Measure_ROI API fields',
                    'priority': 'medium'
                })
            elif api == 'ROI_Render':
                queries.append({
                    'query': "ROI rendering roiRenderParams contourColor renderMaskOverlay",
                    'description': 'ROI rendering parameters',
                    'priority': 'medium'
                })
            elif api == 'Formula':
                queries.append({
                    'query': "Formula API reportFields expression calculation",
                    'description': 'Formula API fields',
                    'priority': 'medium'
                })

        # Query 4: General context from requirements
        if requirements:
            general_query = self._build_general_query(requirements)
            if general_query:
                queries.append({
                    'query': general_query,
                    'description': 'General requirements context',
                    'priority': 'low'
                })

        return queries

    def _build_general_query(self, requirements: dict) -> str:
        """Build a general query from requirements."""
        query_parts = []

        # Extract key terms
        if 'staining_type' in requirements:
            query_parts.append(requirements['staining_type'])

        if 'segmentation_model' in requirements:
            query_parts.append(requirements['segmentation_model'])

        if 'detection_targets' in requirements:
            targets = requirements['detection_targets']
            if isinstance(targets, dict):
                query_parts.extend(str(v) for v in list(targets.values())[:3])

        if 'measurements' in requirements:
            meas = requirements['measurements']
            if isinstance(meas, list):
                query_parts.extend(meas[:3])

        return " ".join(query_parts) if query_parts else ""

    def _retrieve_api_context(self, requirements: dict) -> str:
        """
        Retrieve API documentation using multi-query strategy.

        Returns formatted context string for injection into prompt.
        """
        if not self.retriever:
            logger.info("No retriever available, skipping context retrieval")
            return ""

        logger.info("🔍 Starting multi-query API context retrieval")

        # Step 1: Extract topics
        topics = self._extract_api_topics(requirements)
        logger.info(f"📋 Extracted topics: {topics}")

        # Step 2: Build targeted queries
        queries = self._build_targeted_queries(requirements, topics)
        logger.info(f"📝 Built {len(queries)} targeted queries")

        # Step 3: Execute queries and collect results
        all_results = []
        seen_chunks = set()  # Deduplicate by chunk_id

        for query_info in queries:
            query = query_info['query']
            description = query_info.get('description', 'N/A')
            priority = query_info.get('priority', 'medium')

            # Determine top_k based on priority
            top_k = {'high': 5, 'medium': 3, 'low': 2}.get(priority, 3)

            logger.info(f"  🔎 Query [{priority}]: {query[:60]}... ({description})")

            # Execute retrieval
            if 'method_name' in query_info:
                # Method-specific retrieval
                results = self.retriever.retrieve_by_method(
                    query=query,
                    method_name=query_info['method_name'],
                    top_k=top_k
                )
            else:
                # General retrieval with doc_type filter for Generator
                results = self.retriever.retrieve_for_agent(
                    query=query,
                    agent_type='generator',
                    top_k=top_k
                )

            # Log results with observability
            for i, result in enumerate(results[:3], 1):
                if result.chunk_id not in seen_chunks:
                    all_results.append(result)
                    seen_chunks.add(result.chunk_id)
                    logger.info(
                        f"    [{i}] {result.source} - {result.heading[:40]}... "
                        f"(score: {result.score:.4f}, method: {result.method_name or 'N/A'})"
                    )

        logger.info(f"✅ Retrieved {len(all_results)} unique chunks total")

        # Step 4: Format context
        if not all_results:
            return ""

        # Sort by score (higher first)
        all_results.sort(key=lambda x: x.score, reverse=True)

        # Take top chunks within token budget (4000 tokens ≈ 16000 chars)
        context = self.retriever.format_context(all_results, max_tokens=4000)

        logger.info(f"📄 Formatted context: {len(context)} chars")

        return context

    async def generate_workplan(
        self, requirements: dict, feedback: Optional[dict] = None
    ) -> dict:
        """Generate workplan from requirements with RAG-enhanced context."""

        logger.info("🚀 Generating workplan")

        # Retrieve API context if available
        api_context = ""
        if self.retriever:
            try:
                api_context = self._retrieve_api_context(requirements)
            except Exception as e:
                logger.error(f"Error during API context retrieval: {e}", exc_info=True)
                api_context = ""

        # Build context with injected API documentation
        context = self._build_context(requirements, feedback, api_context)

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
        self, requirements: dict, feedback: Optional[dict], api_context: str = ""
    ) -> str:
        """
        Build context for workplan generation with proper injection order.

        Order (following implementation plan):
        1. Task instructions
        2. API documentation context (if available)
        3. Requirements
        4. Feedback (if any)
        5. Output format instructions
        """

        parts = []

        # Part 1: Inject API documentation context FIRST (after system prompt, before requirements)
        if api_context:
            parts.append("## Retrieved API Documentation")
            parts.append("")
            parts.append("以下是从知识库检索到的相关API文档，**必须严格按照这些文档中的参数名、类型、枚举值生成工作计划**。")
            parts.append("")
            parts.append(api_context)
            parts.append("")
            parts.append("=" * 80)
            parts.append("")

        # Part 2: Requirements
        parts.append("## User Requirements")
        parts.append("")
        parts.append("Generate a complete workplan for the following requirements:")
        parts.append("")
        parts.append(json.dumps(requirements, indent=2, ensure_ascii=False))
        parts.append("")

        # Part 3: Feedback (if any)
        if feedback:
            parts.append("## Reviewer Feedback")
            parts.append("")
            parts.append("Previous workplan was rejected with the following issues:")
            parts.append("")
            parts.append(json.dumps(feedback, indent=2, ensure_ascii=False))
            parts.append("")
            parts.append("Please address these issues in the new workplan.")
            parts.append("")

        # Part 4: Output instructions
        parts.append("## Output Instructions")
        parts.append("")
        if api_context:
            parts.append("**CRITICAL**: Use EXACT parameter names, types, and enum values from the API documentation above.")
            parts.append("")
        parts.append("Output ONLY the complete workplan JSON.")
        parts.append("Do NOT include markdown code blocks.")
        parts.append("Do NOT include explanations.")
        parts.append("Output ONLY valid JSON.")

        return "\n".join(parts)

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
