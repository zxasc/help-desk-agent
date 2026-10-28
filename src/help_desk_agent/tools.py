import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from help_desk_agent.core import Tool

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
POLICIES_DIR = DATA_DIR / "policies"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "much",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "will",
    "with",
    "you",
    "your",
}

# Prefix length used to match word forms, e.g. "cancel" ~ "cancelled" ~ "cancellation"
STEM_LENGTH = 5


@dataclass(frozen=True, kw_only=True)
class PolicySection:
    source: str
    heading: str
    text: str


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS]


def _matches(query_word: str, words: set[str]) -> bool:
    if len(query_word) < 3:
        return query_word in words  # "e", "14": prefixes would match almost anything
    stem = query_word[:STEM_LENGTH]
    # Second check covers short base forms: "opening" ~ "open", "rented" ~ "rent"
    return any(
        w.startswith(stem) or (len(w) >= 4 and query_word.startswith(w)) for w in words
    )


def load_policy_sections(policies_dir: Path = POLICIES_DIR) -> list[PolicySection]:
    """Split every policy file into its `##` sections."""
    sections = []
    for path in sorted(policies_dir.glob("*.md")):
        for chunk in re.split(r"^(?=## )", path.read_text(), flags=re.MULTILINE):
            lines = chunk.strip().splitlines()
            if not lines or not lines[0].startswith("## "):
                continue  # document title and intro
            sections.append(
                PolicySection(
                    source=path.name,
                    heading=lines[0].removeprefix("## ").strip(),
                    text="\n".join(lines[1:]).strip(),
                )
            )
    return sections


def search_policies(query: str, top_k: int = 3) -> dict[str, Any]:
    """Find the policy sections that share the most words with the query."""
    query_words = set(_tokenize(query))
    scored = []
    for section in load_policy_sections():
        heading_words = set(_tokenize(section.heading))
        body_words = set(_tokenize(section.text))
        # A match in the heading counts double: headings say what a section is about
        score = sum(
            2 * _matches(w, heading_words) + _matches(w, body_words)
            for w in query_words
        )
        if score > 0:
            scored.append((score, section))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        {"source": s.source, "heading": s.heading, "text": s.text}
        for _, s in scored[:top_k]
    ]
    if not results:
        return {"query": query, "results": [], "message": "No matching policy found."}
    return {"query": query, "results": results}


TOOLS = {
    tool.name: tool
    for tool in (
        Tool(
            name="search_policies",
            description="Search the CityWheels policy documents (prices, opening hours, "
            "cancellations, refunds, FAQ, staff contact) and return the most relevant sections.",
            func=search_policies,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or the customer's question.",
                    }
                },
                "required": ["query"],
            },
        ),
    )
}
