"""Structure-aware Markdown chunker with breadcrumb support."""

import re
import hashlib
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import yaml
import tiktoken


@dataclass
class ChunkMetadata:
    """Metadata for a single chunk."""
    chunk_id: str
    content: str
    heading: str
    header_path: List[str]
    method_name: str
    doc_type: str  # api, methodology, schema, deprecated
    source: str
    token_count: int
    has_code: bool
    has_table: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MarkdownChunker:
    """
    Structure-aware Markdown chunker for API documentation.

    Key features:
    - Chunks by header hierarchy (#, ##, ###)
    - Keeps methods with their parameters together
    - Protects code blocks and tables from splitting
    - Adds breadcrumb prefixes to content
    - Extracts method_name and doc_type metadata
    """

    def __init__(
        self,
        target_chunk_size: int = 450,
        max_chunk_size: int = 800,
        min_chunk_size: int = 100,
        overlap_size: int = 60,
        encoding_name: str = "cl100k_base"
    ):
        self.target_chunk_size = target_chunk_size
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_size = overlap_size
        self.tokenizer = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))

    def extract_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
        """Extract YAML frontmatter if present."""
        frontmatter = {}

        # Check for YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    content = parts[2].strip()
                except yaml.YAMLError:
                    pass

        return frontmatter, content

    def extract_code_blocks(self, content: str) -> Tuple[str, List[str]]:
        """
        Extract code blocks and replace with placeholders.
        This prevents code blocks from being split during chunking.
        """
        code_blocks = []
        placeholder_pattern = "<<<CODE_BLOCK_{}>>>"

        def replace_code_block(match):
            code_blocks.append(match.group(0))
            return placeholder_pattern.format(len(code_blocks) - 1)

        # Match fenced code blocks (```...```)
        pattern = r'```[\s\S]*?```'
        content_without_code = re.sub(pattern, replace_code_block, content)

        return content_without_code, code_blocks

    def restore_code_blocks(self, content: str, code_blocks: List[str]) -> str:
        """Restore code blocks from placeholders."""
        for i, block in enumerate(code_blocks):
            placeholder = f"<<<CODE_BLOCK_{i}>>>"
            content = content.replace(placeholder, block)
        return content

    def parse_headers(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse markdown headers and create sections.
        Returns list of sections with header info and content.
        """
        lines = content.split("\n")
        sections = []
        current_section = None

        for i, line in enumerate(lines):
            # Match markdown headers
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if header_match:
                # Save previous section
                if current_section:
                    sections.append(current_section)

                # Start new section
                level = len(header_match.group(1))
                title = header_match.group(2).strip()

                current_section = {
                    'level': level,
                    'title': title,
                    'content_lines': [],
                    'start_line': i
                }
            elif current_section:
                current_section['content_lines'].append(line)

        # Add last section
        if current_section:
            sections.append(current_section)

        return sections

    def build_header_hierarchy(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build header hierarchy and compute header paths.
        Each section gets a full breadcrumb path.
        """
        hierarchy = []
        header_stack = []  # Stack of (level, title)

        for section in sections:
            level = section['level']
            title = section['title']

            # Pop headers of same or higher level
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()

            # Add current header
            header_stack.append((level, title))

            # Build header path
            header_path = [h[1] for h in header_stack]

            section['header_path'] = header_path
            hierarchy.append(section)

        return hierarchy

    def extract_method_name(self, header_path: List[str], content: str) -> str:
        """
        Extract method name from header path or content.
        Looks for method-level headers (often level 2 or 3).
        """
        method_name = ""

        # Common method keywords
        method_keywords = [
            'cellpose', 'threshold', 'weka', 'rnascope', 'detectpin',
            'run_segmentation', 'analyze_particles', 'bindSegmentRoi'
        ]

        # Check header path
        for header in reversed(header_path):
            header_lower = header.lower()
            for keyword in method_keywords:
                if keyword in header_lower:
                    method_name = keyword
                    break
            if method_name:
                break

        # Also check in content for method references
        if not method_name:
            content_lower = content.lower()
            for keyword in method_keywords:
                if keyword in content_lower:
                    method_name = keyword
                    break

        return method_name

    def has_code_blocks(self, content: str) -> bool:
        """Check if content contains code blocks."""
        return bool(re.search(r'```[\s\S]*?```', content))

    def has_tables(self, content: str) -> bool:
        """Check if content contains markdown tables."""
        lines = content.split('\n')
        for line in lines:
            if '|' in line and line.strip().startswith('|'):
                return True
        return False

    def create_breadcrumb_prefix(self, header_path: List[str]) -> str:
        """Create breadcrumb prefix from header path."""
        if not header_path:
            return ""
        return " > ".join(header_path) + "\n\n"

    def split_long_section(
        self,
        content: str,
        header_path: List[str],
        code_blocks: List[str]
    ) -> List[str]:
        """
        Split a long section into smaller chunks while preserving structure.
        Used when a single section exceeds max_chunk_size.
        """
        chunks = []
        breadcrumb = self.create_breadcrumb_prefix(header_path)

        # Restore code blocks for proper splitting
        content = self.restore_code_blocks(content, code_blocks)

        paragraphs = content.split('\n\n')
        current_chunk = ""

        for para in paragraphs:
            test_chunk = current_chunk + ("\n\n" if current_chunk else "") + para
            test_with_breadcrumb = breadcrumb + test_chunk

            if self.count_tokens(test_with_breadcrumb) > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunks.append(breadcrumb + current_chunk)

                # Start new chunk with overlap
                words = current_chunk.split()
                overlap_text = " ".join(words[-self.overlap_size:]) if len(words) > self.overlap_size else ""
                current_chunk = overlap_text + "\n\n" + para if overlap_text else para
            else:
                current_chunk = test_chunk

        # Add remaining chunk
        if current_chunk:
            chunks.append(breadcrumb + current_chunk)

        return chunks

    def infer_doc_type(self, file_path: str, frontmatter: Dict[str, Any]) -> str:
        """
        Infer document type from frontmatter or file path.
        Returns: api, methodology, schema, or deprecated
        """
        # Check frontmatter first
        if 'doc_type' in frontmatter:
            return frontmatter['doc_type']

        # Check file path
        path_lower = file_path.lower()
        if 'deprecated' in path_lower:
            return 'deprecated'
        elif 'methodology' in path_lower or 'guide' in path_lower:
            return 'methodology'
        elif 'schema' in path_lower:
            return 'schema'
        else:
            return 'api'  # Default

    def create_chunk_id(self, source: str, header_path: List[str], index: int) -> str:
        """
        Create deterministic chunk ID.
        Format: {source_path}#{header_slug}#{index}
        """
        # Create slug from header path
        header_slug = "_".join(
            re.sub(r'[^\w\s-]', '', h).replace(' ', '_')
            for h in header_path
        )[:100]  # Limit length

        # Create short hash of source path for uniqueness
        source_hash = hashlib.md5(source.encode()).hexdigest()[:8]

        return f"{source_hash}#{header_slug}#{index}"

    def chunk_document(self, file_path: str, content: str) -> List[ChunkMetadata]:
        """
        Chunk a single markdown document.
        Main entry point for chunking.
        """
        # Extract frontmatter
        frontmatter, content = self.extract_frontmatter(content)

        # Infer doc_type
        doc_type = self.infer_doc_type(file_path, frontmatter)

        # Extract and protect code blocks
        content_no_code, code_blocks = self.extract_code_blocks(content)

        # Parse headers
        sections = self.parse_headers(content_no_code)

        # Build hierarchy
        sections = self.build_header_hierarchy(sections)

        # Create chunks
        chunks = []
        source = str(Path(file_path).name)  # Use relative path

        for section_idx, section in enumerate(sections):
            header_path = section['header_path']
            content_text = '\n'.join(section['content_lines']).strip()

            # Restore code blocks
            content_text = self.restore_code_blocks(content_text, code_blocks)

            # Create breadcrumb prefix
            breadcrumb = self.create_breadcrumb_prefix(header_path)
            full_content = breadcrumb + content_text

            token_count = self.count_tokens(full_content)

            # Check if section needs splitting
            if token_count > self.max_chunk_size:
                # Split into multiple chunks
                split_chunks = self.split_long_section(content_text, header_path, code_blocks)

                for split_idx, chunk_text in enumerate(split_chunks):
                    chunk_id = self.create_chunk_id(source, header_path, section_idx * 100 + split_idx)

                    chunks.append(ChunkMetadata(
                        chunk_id=chunk_id,
                        content=chunk_text,
                        heading=section['title'],
                        header_path=header_path,
                        method_name=self.extract_method_name(header_path, chunk_text),
                        doc_type=doc_type,
                        source=source,
                        token_count=self.count_tokens(chunk_text),
                        has_code=self.has_code_blocks(chunk_text),
                        has_table=self.has_tables(chunk_text)
                    ))
            else:
                # Single chunk for this section
                chunk_id = self.create_chunk_id(source, header_path, section_idx)

                chunks.append(ChunkMetadata(
                    chunk_id=chunk_id,
                    content=full_content,
                    heading=section['title'],
                    header_path=header_path,
                    method_name=self.extract_method_name(header_path, content_text),
                    doc_type=doc_type,
                    source=source,
                    token_count=token_count,
                    has_code=self.has_code_blocks(content_text),
                    has_table=self.has_tables(content_text)
                ))

        # Merge very short chunks with similar header paths
        chunks = self._merge_short_chunks(chunks)

        return chunks

    def _merge_short_chunks(self, chunks: List[ChunkMetadata]) -> List[ChunkMetadata]:
        """Merge consecutive short chunks with compatible header paths."""
        if not chunks:
            return chunks

        merged = [chunks[0]]

        for chunk in chunks[1:]:
            last_chunk = merged[-1]

            # Check if we should merge
            should_merge = (
                last_chunk.token_count < self.min_chunk_size and
                chunk.token_count < self.min_chunk_size and
                len(last_chunk.header_path) == len(chunk.header_path) and
                last_chunk.header_path[:-1] == chunk.header_path[:-1]  # Same parent
            )

            if should_merge:
                # Merge chunks
                merged_content = last_chunk.content + "\n\n" + chunk.content
                merged[-1] = ChunkMetadata(
                    chunk_id=last_chunk.chunk_id,
                    content=merged_content,
                    heading=last_chunk.heading + " + " + chunk.heading,
                    header_path=last_chunk.header_path,
                    method_name=last_chunk.method_name or chunk.method_name,
                    doc_type=last_chunk.doc_type,
                    source=last_chunk.source,
                    token_count=self.count_tokens(merged_content),
                    has_code=last_chunk.has_code or chunk.has_code,
                    has_table=last_chunk.has_table or chunk.has_table
                )
            else:
                merged.append(chunk)

        return merged
