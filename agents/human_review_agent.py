# utils/human_review.py

import re
from utils.logger import get_logger

logger = get_logger(__name__)

# ----------------------------------------------------------------------
# Suspicious patterns for detecting fabricated or sensitive details
# (same patterns used across response_agent, summarization_agent, supervisor)
# ----------------------------------------------------------------------
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",       # fabricated order IDs
    r"\btracking number\b",
    r"\bAWB\b",
    r"\bETA\b",
    r"\border id\b",
    r"\bclient address\b",
    r"\bphone\b",
]


def _find_suspicious_snippets(text: str):
    """
    Returns localized text snippets around suspicious operational patterns.
    Helpful for human reviewers to see exactly what looks unsafe.
    """
    snippets = []
    for pattern in SUSPICIOUS_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            snippet = text[start:end].strip()
            snippets.append(snippet)

    # Remove duplicates while preserving order
    return list(dict.fromkeys(snippets))


# ----------------------------------------------------------------------
# Interactive review tool — for LOCAL USE ONLY (NOT API)
# ----------------------------------------------------------------------
def review_email(email: dict, response: str) -> str:
    """
    CLI-based human review helper.
    Displays the generated AI response in the terminal
    and allows the reviewer to:
        - ACCEPT
        - EDIT
        - REPLACE

    Returns a final safe response string.
    """

    print("\n\n=======================================")
    print("           GENERATED RESPONSE          ")
    print("=======================================\n")
    print(response)
    print("\n---------------------------------------\n")

    suspicious = _find_suspicious_snippets(response)

    # ------------------------------------------------------
    # Highlight potential hallucinations / sensitive leaks
    # ------------------------------------------------------
    if suspicious:
        print("  WARNING: Suspicious or sensitive details detected!\n")
        for i, snippet in enumerate(suspicious, start=1):
            print(f" {i}. ...{snippet}...")
        print("\nReview is highly recommended before sending.\n")

    # ------------------------------------------------------
    # Interactive feedback loop (Accept/Edit/Reject)
    # ------------------------------------------------------
    while True:
        choice = input("(a)ccept / (e)dit / (r)eject → ").strip().lower()

        # ACCEPT
        if choice in ("a", "accept"):
            final = response.strip()
            if not final:
                print("Cannot accept an empty response. Please edit instead.")
                continue

            logger.info("[HumanReview] Reviewer accepted the AI response.")
            return final

        # EDIT
        if choice in ("e", "edit"):
            print("\nEnter your corrected response (blank line to finish):\n")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)

            edited = "\n".join(lines).strip()
            if not edited:
                print("Edited response cannot be empty. Try again.")
                continue

            logger.info("[HumanReview] Reviewer edited the AI response.")
            return edited

        # REJECT / REPLACE
        if choice in ("r", "reject", "replace"):
            print("\nEnter replacement response (blank line to finish):\n")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)

            replacement = "\n".join(lines).strip()
            if not replacement:
                print("Replacement cannot be empty. Try again.")
                continue

            logger.info("[HumanReview] Reviewer replaced the AI response entirely.")
            return replacement

        print("Invalid choice. Please enter 'a', 'e', or 'r'.")
