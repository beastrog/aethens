def format_counts(text: str) -> str:
    counts: dict[str, int] = {}
    for word in text.split():
        w = word.lower()
        counts[w] = counts.get(w, 0) + 1
    return "\n".join(f"{w}: {n}" for w, n in counts.items())
