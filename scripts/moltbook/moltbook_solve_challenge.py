#!/usr/bin/env python3
"""Parse Moltbook post-creation challenge text and return the numeric answer (2 decimal places).
Used so queue/cron posts can be verified automatically and published.
Challenge text is often obfuscated (e.g. ThIrTtY TwO = 32). We normalize and extract numbers."""
import re
import sys

# Word to digit for compound numbers (lowercase, no spaces)
WORD_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def normalize(s: str) -> str:
    """Lowercase, remove non-alphanumeric; collapse repeated letters (thirtty->thirty, foour->four)."""
    s = re.sub(r"[^a-z0-9\s]", "", s.lower())
    # Collapse duplicate consecutive letters so obfuscation like ThIrTtY -> thirtty -> thirty
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def extract_numbers(text: str) -> list[float]:
    """Extract all numbers from obfuscated challenge text (words or digits)."""
    norm = normalize(text)
    tokens = norm.split()
    numbers = []
    i = 0
    while i < len(tokens):
        # Try digit
        if tokens[i].isdigit():
            numbers.append(float(tokens[i]))
            i += 1
            continue
        # Try single word number
        if tokens[i] in WORD_NUMS:
            val = WORD_NUMS[tokens[i]]
            # Compound e.g. "thirty two"
            if i + 1 < len(tokens) and tokens[i + 1] in WORD_NUMS:
                next_val = WORD_NUMS[tokens[i + 1]]
                if val >= 20 and next_val < 10:  # thirty two = 32
                    numbers.append(float(val + next_val))
                    i += 2
                    continue
            numbers.append(float(val))
            i += 1
            continue
        # Concatenated word like "thirtytwo" (whole-word only; avoid "four" in "force")
        for word, num in WORD_NUMS.items():
            if tokens[i] == word:
                numbers.append(float(num))
                i += 1
                break
            if tokens[i].startswith(word) and len(tokens[i]) > len(word):
                rest = tokens[i][len(word):]
                if rest in WORD_NUMS:
                    numbers.append(float(num + WORD_NUMS[rest]))
                    i += 1
                    break
        else:
            i += 1
    return numbers


def solve_challenge(text: str) -> str | None:
    """Return answer as 'XXX.00' or None if we can't parse."""
    numbers = extract_numbers(text)
    if not numbers:
        return None
    norm = normalize(text)
    # "doubling" / "multiplied by" -> first number * 2 * rest (e.g. 32 doubling multiplied by 4 = 256)
    if "doubl" in norm:
        result = numbers[0] * 2.0
        for n in numbers[1:]:
            result *= n
        return f"{result:.2f}"
    if "multipl" in norm:
        result = numbers[0]
        for n in numbers[1:]:
            result *= n
        return f"{result:.2f}"
    if "increas" in norm or "add" in norm or "plus" in norm:
        return f"{sum(numbers):.2f}"
    if len(numbers) >= 2:
        return f"{numbers[0] * numbers[1]:.2f}"
    return f"{numbers[0]:.2f}"


def main():
    if len(sys.argv) < 2:
        # Read from stdin (e.g. echo "$challenge" | python moltbook_solve_challenge.py)
        text = sys.stdin.read().strip()
    else:
        text = " ".join(sys.argv[1:])
    if not text:
        sys.exit(1)
    answer = solve_challenge(text)
    if answer is None:
        sys.exit(1)
    print(answer)


if __name__ == "__main__":
    main()
