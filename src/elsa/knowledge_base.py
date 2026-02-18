import os
import logging
from typing import List

logger = logging.getLogger(__name__)

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")
ERIQ_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ERIQ")

CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200

_elsa_knowledge_cache = {}


def load_elsa_knowledge_base() -> List[dict]:
    global _elsa_knowledge_cache
    if _elsa_knowledge_cache:
        return list(_elsa_knowledge_cache.values())

    docs = []

    for dir_path, label in [(DOCS_DIR, "docs"), (ERIQ_DIR, "ERIQ")]:
        if not os.path.isdir(dir_path):
            logger.warning(f"ELSA knowledge dir not found: {dir_path}")
            continue
        for filename in sorted(os.listdir(dir_path)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(dir_path, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                chunks = _chunk_document(content, filename, label)
                for chunk in chunks:
                    doc_id = f"{label}/{filename}:{chunk['section']}"
                    entry = {
                        "id": doc_id,
                        "source": f"{label}/{filename}",
                        "section": chunk["section"],
                        "content": chunk["content"],
                        "keywords": chunk["keywords"],
                    }
                    _elsa_knowledge_cache[doc_id] = entry
                    docs.append(entry)
            except Exception as e:
                logger.error(f"ELSA failed to load {filepath}: {e}")

    logger.info(f"ELSA knowledge base loaded: {len(docs)} chunks from docs/ and ERIQ/")
    return docs


def _chunk_document(content: str, filename: str, label: str) -> List[dict]:
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
        return [{"section": section, "content": text.strip(), "keywords": list(keywords)}]

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
    marketing_terms = {
        "geri", "eeri", "egsi", "index", "risk", "alert", "user", "plan",
        "subscription", "free", "personal", "trader", "pro", "enterprise",
        "marketing", "seo", "growth", "conversion", "retention", "churn",
        "pricing", "revenue", "stripe", "billing", "signup", "onboarding",
        "email", "telegram", "digest", "dashboard", "feature", "tier",
        "trial", "offer", "campaign", "content", "analytics", "engagement",
        "methodology", "intelligence", "briefing", "premium", "upgrade",
        "brent", "ttf", "vix", "storage", "geopolitical", "energy",
    }
    words = set(text.lower().replace("#", "").replace("*", "").split())
    return words & marketing_terms


def retrieve_relevant_elsa_docs(query: str, top_k: int = 6) -> List[dict]:
    if not _elsa_knowledge_cache:
        load_elsa_knowledge_base()

    query_lower = query.lower()
    query_words = set(query_lower.split())
    query_keywords = _extract_keywords(query_lower)

    scored = []
    for doc in _elsa_knowledge_cache.values():
        score = 0.0
        doc_keywords = set(doc.get("keywords", []))
        keyword_overlap = len(query_keywords & doc_keywords)
        score += keyword_overlap * 3.0

        content_lower = doc["content"].lower()
        for word in query_words:
            if len(word) > 3 and word in content_lower:
                score += 1.0

        for term in ["marketing", "seo", "growth", "conversion", "pricing", "revenue", "plan", "user"]:
            if term in query_lower and term in content_lower:
                score += 3.0

        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]


def format_elsa_knowledge(docs: List[dict]) -> str:
    if not docs:
        return ""

    parts = ["=== ELSA KNOWLEDGE BASE (Product & Documentation) ==="]
    for doc in docs:
        parts.append(f"\n--- Source: {doc['source']} | Section: {doc['section']} ---")
        content = doc["content"]
        if len(content) > 1500:
            content = content[:1500] + "..."
        parts.append(content)

    return "\n".join(parts)
