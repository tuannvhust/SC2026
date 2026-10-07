import re
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    _HAS_LANGCHAIN = True
except ImportError:
    _HAS_LANGCHAIN = False


class SimpleSplitter:
    """Fallback line-based splitter with character-bounded overlap."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        if not text.strip():
            return []

        lines = text.split("\n")
        chunks: List[str] = []
        cur_lines: List[str] = []
        cur_len = 0

        for line in lines:
            line_len = len(line) + 1  # includes '\n'
            
            if cur_len + line_len > self.chunk_size and cur_lines:
                chunks.append("\n".join(cur_lines).strip())
                
                # Retain tail lines fitting within chunk_overlap length
                overlap_lines: List[str] = []
                overlap_len = 0
                for prev_line in reversed(cur_lines):
                    p_len = len(prev_line) + 1
                    if overlap_len + p_len > self.chunk_overlap:
                        break
                    overlap_lines.insert(0, prev_line)
                    overlap_len += p_len
                
                cur_lines = overlap_lines
                cur_len = overlap_len

            cur_lines.append(line)
            cur_len += line_len

        if cur_lines and "\n".join(cur_lines).strip():
            chunks.append("\n".join(cur_lines).strip())

        return chunks


class MarkdownChunker:
    """Chunks markdown documents for vector indexing with deterministic chunk IDs."""

    def __init__(self, max_chars: int = 800, overlap: int = 50):
        self.max_chars = max_chars
        self.overlap = overlap
        
        if _HAS_LANGCHAIN:
            self.splitter = RecursiveCharacterTextSplitter(
                chunk_size=max_chars,
                chunk_overlap=overlap,
                separators=["\n\n", "\n", " "],
            )
        else:
            self.splitter = SimpleSplitter(chunk_size=max_chars, chunk_overlap=overlap)

    @staticmethod
    def _clean(text: str) -> str:
        """Strip HTML elements and markdown formatting while maintaining structure."""
        cleaned = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"[`*_~]+", "", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert section heading into URL-friendly slug."""
        slug = re.sub(r"[^\w]+", "-", text.strip().lower())
        return slug.strip("-") or "section"

    @staticmethod
    def _section_id(heading: Optional[str]) -> Optional[str]:
        if not heading:
            return None
        match = re.search(r"\[([A-Z][A-Z0-9]*-\d+)\]", heading)
        return match.group(1) if match else None

    @staticmethod
    def _deterministic_id(file_stem: str, heading: Optional[str], index: int) -> str:
        """Generate stable identifier for Qdrant indexing consistency."""
        if heading:
            code = MarkdownChunker._section_id(heading)
            if code:
                return code if index == 0 else f"{code}_chunk{index}"
            return f"{file_stem}_{MarkdownChunker._slugify(heading)}_chunk{index}"
        return f"{file_stem}_chunk{index}"

    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        """Split document by ATX markdown headings (# Heading)."""
        pattern = re.compile(r"(^\s*#+\s.*$)", re.MULTILINE)
        matches = list(pattern.finditer(text))
        
        if not matches:
            return [{"heading": None, "content": text}]

        sections: List[Dict[str, Any]] = []
        
        # Capture preamble text before the first heading
        if matches[0].start() > 0:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                sections.append({"heading": None, "content": preamble})

        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append({
                "heading": match.group(0).strip(),
                "content": text[start:end],
            })
            
        return sections

    def chunk(self, raw_text: str, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Clean, section, split, and enrich text chunks with metadata."""
        cleaned = self._clean(raw_text)
        sections = self._extract_sections(cleaned)
        file_stem = Path(meta.get("source_path", "unknown")).stem
        chunks: List[Dict[str, Any]] = []

        for sec in sections:
            heading = sec["heading"]
            sub_chunks = self.splitter.split_text(sec["content"])

            for idx, chunk_text in enumerate(sub_chunks):
                if not chunk_text.strip():
                    continue
                
                chunk_id = self._deterministic_id(file_stem, heading, idx)
                section_id = self._section_id(heading)
                text = "\n".join(
                    part for part in (heading, chunk_text.strip()) if part
                )
                chunks.append({
                    "id": chunk_id,
                    "text": text,
                    "meta": {
                        **meta,
                        "heading": heading,
                        "chunk_index": idx,
                        "chunk_id": section_id or chunk_id,
                    },
                })

        return chunks