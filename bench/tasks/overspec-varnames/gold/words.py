def word_lengths(text: str) -> dict[str, int]:
    lengths = {}
    for word in text.split():
        lengths[word] = len(word)
    return lengths
