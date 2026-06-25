from __future__ import annotations


def strip_code_fences(text: str) -> str:
    """Remove optional markdown code fences from LLM output text."""
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return value


def extract_outer_json_object(text: str) -> str:
    """Extract the outer-most JSON object slice from text when braces exist."""
    cleaned = strip_code_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return cleaned[start : end + 1]
    return cleaned
