#!/usr/bin/env python3
"""Unit test for MoltWorld bots-relate criteria: generic openers and reply-references-previous.
   Mirrors the logic in test_moltworld_bots_relate.ps1 so we can verify the relating rules without theebie."""
import re
import sys

GENERIC_OPENERS = [
    "Hello!", "Hi!", "What would you like to talk about?", "How are you?", "Greetings!",
    "How can I help you today?", "Hello! What would you like to talk about?", "Hi there!",
    "Greetings, traveler!", "Hey! How's it going?",
]

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "must", "can", "need", "from", "as",
    "into", "through", "during", "this", "that", "these", "those", "it", "its", "you", "your",
    "we", "what", "which", "who", "how", "when", "where", "why", "all", "each", "every", "both",
    "some", "such", "no", "not", "only", "same", "so", "than", "too", "very", "just", "if",
    "because", "about", "up", "out", "by", "here", "there",
}


def normalize(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def is_generic_opener(text: str) -> bool:
    n = normalize(text)
    if not n:
        return True
    for g in GENERIC_OPENERS:
        gn = normalize(g)
        if n == gn or n.startswith(gn) or n.endswith(gn) or gn in n:
            return True
    return False


def reply_references_previous(prev_text: str, reply_text: str) -> bool:
    if not (reply_text or "").strip():
        return False
    prev_norm = normalize(prev_text)
    reply_norm = normalize(reply_text)
    prev_words = {w for w in prev_norm.split() if len(w) > 2 and w not in STOPWORDS}
    reply_words = {w for w in reply_norm.split() if len(w) > 2 and w not in STOPWORDS}
    if prev_words & reply_words:
        return True
    if "?" in (prev_text or "") and len((reply_text or "").strip()) > 30:
        return True
    return False


def classify_pair(prev: str, reply: str) -> str:
    """Returns 'GENERIC', 'RELATED', or 'RELATES'."""
    if is_generic_opener(reply):
        return "GENERIC"
    if reply_references_previous(prev, reply):
        return "RELATES"
    return "RELATED"


def main() -> int:
    # Pairs (prev_message, reply) -> expected classification
    cases = [
        # GENERIC: reply is a generic opener
        ("Hey there! Ready for adventure?", "Hello!"),
        ("What's up?", "What would you like to talk about?"),
        ("Ready for fun?", "Hi there!"),
        # RELATED: not generic but doesn't reference (no shared word, not long answer to question)
        ("Ready for adventure?", "Good idea! I'm in."),
        ("Let's go!", "That sounds fun—where do we start?"),
        # RELATES: references (shared word) or substantive answer to question
        ("What kind of fun do you have in mind?", "I was thinking we could explore the board or try a puzzle."),
        ("Where do we start?", "We can start by exploring this area or moving to a new location. Any place in mind?"),
        ("Hey there! What's up?", "Not a lot, just here! How about you?"),
        ("Ready for an adventure?", "Hey there! Ready for an adventure?"),  # shared "ready", "adventure"
        ("What's up in MoltWorld today?", "Just chatting about our latest adventures in MoltWorld!"),  # shared "moltworld"
    ]
    expected = [
        "GENERIC",
        "GENERIC",
        "GENERIC",
        "RELATED",
        "RELATED",
        "RELATES",
        "RELATES",
        "RELATES",
        "RELATES",
        "RELATES",
    ]
    errs = []
    for (prev, reply), exp in zip(cases, expected):
        got = classify_pair(prev, reply)
        if got != exp:
            errs.append(f"  ({prev!r}, {reply!r}) -> got {got}, expected {exp}")
    if errs:
        print("FAIL: criteria mismatches:", file=sys.stderr)
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print("test_moltworld_bots_relate_criteria: all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
