from collections import Counter


def format_counts(text: str) -> str:
    c = Counter(w.lower() for w in text.split())
    lines = [f"{word}: {n}" for word, n in sorted(c.items())]
    return "\n".join(lines)
