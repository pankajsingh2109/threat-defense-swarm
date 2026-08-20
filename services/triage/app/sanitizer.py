import re
from shared.schemas.events import SanitizedInput

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions",
    r"disregard\s+(previous|prior|all)\s+rules",
    r"output\s+system\s+compromised",
    r"system\s+compromised",
    r"you\s+are\s+now\s+a",
    r"new\s+instruction",
    r"override\s+system",
    r"jailbreak",
    r"admin\s+mode",
]

def sanitize_input(raw_text: str) -> SanitizedInput:
    """
    Sanitizes incoming raw text by placing it inside explicit data boundaries
    and evaluating heuristic indicators of prompt injection.
    """
    flagged = False
    flag_reason = None

    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, raw_text, re.IGNORECASE):
            flagged = True
            flag_reason = f"Imperative prompt injection phrase detected matching pattern: '{pattern}'"
            break

    # Boundary framing
    framed_text = f"<data>\n{raw_text.strip()}\n</data>"

    return SanitizedInput(
        raw_text=framed_text,
        injection_flagged=flagged,
        flag_reason=flag_reason
    )
