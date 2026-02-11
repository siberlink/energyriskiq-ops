import os
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

ERIQ_DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ERIQ")

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200

_knowledge_cache = {}


def load_knowledge_base() -> List[dict]:
    global _knowledge_cache
    if _knowledge_cache:
        return list(_knowledge_cache.values())

    docs = []
    if not os.path.isdir(ERIQ_DOCS_DIR):
        logger.warning(f"ERIQ docs directory not found: {ERIQ_DOCS_DIR}")
        return docs

    for filename in sorted(os.listdir(ERIQ_DOCS_DIR)):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(ERIQ_DOCS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            chunks = _chunk_document(content, filename)
            for chunk in chunks:
                doc_id = f"{filename}:{chunk['section']}"
                entry = {
                    "id": doc_id,
                    "source": filename,
                    "section": chunk["section"],
                    "content": chunk["content"],
                    "keywords": chunk["keywords"],
                }
                _knowledge_cache[doc_id] = entry
                docs.append(entry)
            logger.info(f"Loaded {len(chunks)} chunks from {filename}")
        except Exception as e:
            logger.error(f"Failed to load {filename}: {e}")

    logger.info(f"Knowledge base loaded: {len(docs)} total chunks from {len(os.listdir(ERIQ_DOCS_DIR))} files")
    return docs


def _chunk_document(content: str, filename: str) -> List[dict]:
    chunks = []
    lines = content.split("\n")
    current_section = filename.replace(".md", "").replace("-", " ").title()
    current_content = []
    current_keywords = set()

    for line in lines:
        if line.startswith("## ") or line.startswith("# "):
            if current_content:
                text = "\n".join(current_content)
                if len(text.strip()) > 50:
                    sub_chunks = _split_long_text(text, current_section, current_keywords)
                    chunks.extend(sub_chunks)
            current_section = line.lstrip("#").strip()
            current_content = [line]
            current_keywords = _extract_keywords(line)
        elif line.startswith("### "):
            current_keywords.update(_extract_keywords(line))
            current_content.append(line)
        else:
            current_content.append(line)

    if current_content:
        text = "\n".join(current_content)
        if len(text.strip()) > 50:
            sub_chunks = _split_long_text(text, current_section, current_keywords)
            chunks.extend(sub_chunks)

    return chunks


def _split_long_text(text: str, section: str, keywords: set) -> List[dict]:
    if len(text) <= CHUNK_SIZE:
        return [{
            "section": section,
            "content": text.strip(),
            "keywords": list(keywords),
        }]

    chunks = []
    start = 0
    part = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            break_at = text.rfind("\n", start, end)
            if break_at > start + CHUNK_SIZE // 2:
                end = break_at

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "section": f"{section} (part {part + 1})" if part > 0 else section,
                "content": chunk_text,
                "keywords": list(keywords),
            })
        start = max(start + 1, end - CHUNK_OVERLAP)
        part += 1

    return chunks


def _extract_keywords(text: str) -> set:
    important_terms = {
        "geri", "eeri", "egsi", "egsi-m", "egsi-s", "index", "risk", "band",
        "pillar", "component", "alert", "severity", "region", "asset", "brent",
        "ttf", "vix", "eurusd", "storage", "regime", "momentum", "trend",
        "divergence", "correlation", "beta", "volatility", "contagion",
        "escalation", "spike", "critical", "severe", "elevated", "moderate",
        "low", "normal", "high", "methodology", "formula", "weight",
        "interpretation", "classification", "geopolitical", "supply",
        "demand", "infrastructure", "sanctions", "opec", "pipeline",
        "lng", "refinery", "conflict", "election", "tariff", "embargo",
    }
    words = set(text.lower().replace("#", "").replace("*", "").split())
    return words & important_terms


def retrieve_relevant_docs(query: str, top_k: int = 5) -> List[dict]:
    if not _knowledge_cache:
        load_knowledge_base()

    query_lower = query.lower()
    query_words = set(query_lower.split())
    query_keywords = _extract_keywords(query_lower)

    scored = []
    for doc in _knowledge_cache.values():
        score = 0.0

        doc_keywords = set(doc.get("keywords", []))
        keyword_overlap = len(query_keywords & doc_keywords)
        score += keyword_overlap * 3.0

        content_lower = doc["content"].lower()
        for word in query_words:
            if len(word) > 3 and word in content_lower:
                score += 1.0

        for term in ["geri", "eeri", "egsi", "egsi-m", "egsi-s"]:
            if term in query_lower and term in content_lower:
                score += 5.0

        if any(w in query_lower for w in ["what is", "how does", "explain", "define", "meaning"]):
            if "methodology" in doc["source"] or "taxonomy" in doc["source"]:
                score += 2.0

        if any(w in query_lower for w in ["interpret", "analyze", "why", "pattern", "divergence"]):
            if "interpretation" in doc["source"] or "playbook" in doc["source"]:
                score += 2.0

        if any(w in query_lower for w in ["asset", "brent", "ttf", "vix", "storage", "eurusd"]):
            if "asset" in doc["source"]:
                score += 3.0

        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]


def format_knowledge_for_prompt(docs: List[dict]) -> str:
    if not docs:
        return ""

    parts = ["=== ERIQ KNOWLEDGE BASE (Reference Documents) ==="]
    for i, doc in enumerate(docs, 1):
        parts.append(f"\n--- Source: {doc['source']} | Section: {doc['section']} ---")
        content = doc["content"]
        if len(content) > 1200:
            content = content[:1200] + "..."
        parts.append(content)

    return "\n".join(parts)
