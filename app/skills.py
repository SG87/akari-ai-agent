"""
Skill loader — reads skill markdown files and assembles system prompts.

Skills are stored in the `skills/` directory as markdown files with optional
YAML frontmatter (stripped before injection into the system prompt).
"""

import re
from pathlib import Path
from functools import lru_cache

# Resolve skills directory relative to project root
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from the beginning of a file."""
    pattern = r"^---\s*\n.*?\n---\s*\n"
    return re.sub(pattern, "", content, count=1, flags=re.DOTALL).strip()


@lru_cache(maxsize=32)
def load_skill(name: str) -> str:
    """Load a single skill file by name (without .md extension).

    Returns the markdown body with YAML frontmatter stripped.
    Raises FileNotFoundError if the skill does not exist.
    """
    path = _SKILLS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill '{name}' not found at {path}")
    raw = path.read_text(encoding="utf-8")
    return _strip_frontmatter(raw)


def list_available_skills() -> list[str]:
    """Return the names of all available skill files (without .md)."""
    if not _SKILLS_DIR.exists():
        return []
    return sorted(p.stem for p in _SKILLS_DIR.glob("*.md"))


def build_system_prompt(skill_names: list[str]) -> str:
    """Assemble a system prompt from multiple skill files.

    `scout-core` is always included first (if not already in the list).
    Each skill is separated by a horizontal rule for clarity.
    """
    # Ensure scout-core is always first
    ordered: list[str] = []
    if "scout-core" not in skill_names:
        ordered.append("scout-core")
    for name in skill_names:
        if name not in ordered:
            ordered.append(name)

    sections: list[str] = []
    for name in ordered:
        try:
            sections.append(load_skill(name))
        except FileNotFoundError:
            sections.append(f"<!-- Skill '{name}' not found — skipped -->")

    return "\n\n---\n\n".join(sections)
