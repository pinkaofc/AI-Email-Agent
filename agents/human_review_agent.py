import re
from utils.logger import get_logger

logger = get_logger(__name__)

# Patterns that commonly indicate operational details or tracking IDs
SUSPICIOUS_PATTERNS = [
    r"\bSC-[A-Z0-9]{4,}\b",       # actual order IDs
    r"\btracking number\b",       # avoid hallucinating a number
    r"\bAWB\b",                   # airway bill numbers
    r"\bETA\b",                   # exact ETA
    r"\border id\b",              # specific identifiers
    r"\bclient address\b",        # PII
    r"\bphone\b",                 # PII
]



def _find_suspicious_snippets(text: str):
    snippets = []
    for p in SUSPICIOUS_PATTERNS:
        for m in re.finditer(p, text, re.IGNORECASE):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            snippets.append(text[start:end].strip())
    return list(dict.fromkeys(snippets))  # preserve order, unique


def review_email(email: dict, response: str) -> str:
    """
    Interactive human review helper.

    Shows the generated response, highlights suspicious operational details,
    and allows the human to accept, edit, or reject the response.

    Returns the final response text to be sent (must be non-empty).
    """
    print("\n--- Generated Response ---\n")
    print(response)
    print("\n---------------------------\n")

    suspicious = _find_suspicious_snippets(response)
    if suspicious:
        print("WARNING: The AI output contains potential operational details or identifiers.")
        print("Please review these carefully — they might be fabricated or sensitive.\n")
        for i, s in enumerate(suspicious, start=1):
            print(f"{i}. ...{s}...")
        print("\nIf any snippet above looks incorrect or fabricated, choose to edit the response.\n")

    while True:
        user_input = input("Options: (a)ccept / (e)dit / (r)eject and replace: ").strip().lower()
        if user_input in ("a", "accept"):
            logger.info("[HumanReview] Reviewer accepted the AI response.")
            final = response.strip()
            if not final:
                print("Error: final response is empty. Please edit the response.")
                continue
            return final

        if user_input in ("e", "edit"):
            print("\nEnter the corrected response. Finish by pressing Enter on a blank line.")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            modified = "\n".join(lines).strip()
            if not modified:
                print("Edited response is empty — please re-edit or choose reject.")
                continue
            logger.info("[HumanReview] Reviewer edited the AI response.")
            return modified

        if user_input in ("r", "replace", "reject"):
            print("\nEnter the replacement response. Finish by pressing Enter on a blank line.")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            replacement = "\n".join(lines).strip()
            if not replacement:
                print("Replacement response is empty — cannot accept. Try again.")
                continue
            logger.info("[HumanReview] Reviewer replaced the AI response.")
            return replacement

        print("Unrecognized option. Please type 'a' (accept), 'e' (edit), or 'r' (reject).")
