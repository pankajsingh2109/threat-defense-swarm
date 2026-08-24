import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from shared.logger import setup_logger

logger = setup_logger("unresolved-queue")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "unresolved_cases.json"
_lock = threading.Lock()


def _ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def add_unresolved_case(
    run_id: str,
    threat_id: str,
    raw_text: str,
    source: str = "system_log",
    sanitization_flagged: bool = False,
    flag_reason: Optional[str] = None,
    intent: str = "threat",
    intent_category: str = "unknown",
    intent_confidence: float = 0.0,
    failure_reason: str = "Service 2 (Resolution Agent) offline or unreachable",
    queue_path: Path = DEFAULT_QUEUE_PATH
) -> Dict[str, Any]:
    """Adds a new unresolved incident to the persistent Dead-Letter Queue."""
    with _lock:
        _ensure_dir(queue_path)
        try:
            with open(queue_path, "r", encoding="utf-8") as f:
                cases: List[Dict[str, Any]] = json.load(f)
        except Exception:
            cases = []

        # Check if already exists in pending state
        for c in cases:
            if c.get("threat_id") == threat_id and c.get("status") == "pending":
                logger.info(f"Case {threat_id} already queued in pending state.")
                return c

        case_entry = {
            "case_id": f"queue-{threat_id}",
            "run_id": run_id,
            "threat_id": threat_id,
            "source": source,
            "raw_text": raw_text,
            "sanitization_flagged": sanitization_flagged,
            "flag_reason": flag_reason,
            "intent": intent,
            "intent_category": intent_category,
            "intent_confidence": intent_confidence,
            "failure_reason": failure_reason,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
            "resolved_verdict": None,
            "resolved_reason": None,
            "replay_attempts": 0
        }

        cases.append(case_entry)
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(cases, f, indent=2)

        logger.info(f"Recorded unresolved case {threat_id} to queue (Status: pending).")
        return case_entry


def get_unresolved_cases(
    status: Optional[str] = None,
    queue_path: Path = DEFAULT_QUEUE_PATH
) -> List[Dict[str, Any]]:
    """Retrieves all unresolved cases, optionally filtered by status ('pending', 'resolved')."""
    with _lock:
        _ensure_dir(queue_path)
        try:
            with open(queue_path, "r", encoding="utf-8") as f:
                cases = json.load(f)
        except Exception:
            cases = []

        if status:
            return [c for c in cases if c.get("status") == status]
        return cases


def get_case_by_id(case_id: str, queue_path: Path = DEFAULT_QUEUE_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves a single case entry by case_id or threat_id."""
    cases = get_unresolved_cases(queue_path=queue_path)
    for c in cases:
        if c.get("case_id") == case_id or c.get("threat_id") == case_id:
            return c
    return None


def mark_case_resolved(
    threat_id: str,
    verdict: str,
    reason: str,
    details: Optional[Dict[str, Any]] = None,
    queue_path: Path = DEFAULT_QUEUE_PATH
) -> bool:
    """Updates a pending case entry to resolved status with final verdict."""
    with _lock:
        _ensure_dir(queue_path)
        try:
            with open(queue_path, "r", encoding="utf-8") as f:
                cases = json.load(f)
        except Exception:
            return False

        updated = False
        for c in cases:
            if (c.get("threat_id") == threat_id or c.get("case_id") == threat_id) and c.get("status") == "pending":
                c["status"] = "resolved"
                c["resolved_verdict"] = verdict
                c["resolved_reason"] = reason
                c["resolved_at"] = datetime.now(timezone.utc).isoformat()
                c["replay_attempts"] = c.get("replay_attempts", 0) + 1
                if details:
                    c["resolution_details"] = details
                updated = True
                break

        if updated:
            with open(queue_path, "w", encoding="utf-8") as f:
                json.dump(cases, f, indent=2)
            logger.info(f"Marked case {threat_id} as RESOLVED (Verdict: {verdict}).")
            return True
        return False


def get_queue_stats(queue_path: Path = DEFAULT_QUEUE_PATH) -> Dict[str, Any]:
    """Returns aggregated stats of the unresolved queue."""
    cases = get_unresolved_cases(queue_path=queue_path)
    pending_count = sum(1 for c in cases if c.get("status") == "pending")
    resolved_count = sum(1 for c in cases if c.get("status") == "resolved")
    return {
        "total_cases": len(cases),
        "pending_cases": pending_count,
        "resolved_cases": resolved_count,
        "service_2_down_backlog": pending_count > 0
    }


def clear_unresolved_cases(
    status: Optional[str] = None,
    queue_path: Path = DEFAULT_QUEUE_PATH
) -> int:
    """
    Clears cases from the Dead-Letter Queue.
    If status is provided (e.g. 'resolved'), only cases with that status are cleared.
    If status is None, clears all cases. Returns count of cleared cases.
    """
    with _lock:
        _ensure_dir(queue_path)
        try:
            with open(queue_path, "r", encoding="utf-8") as f:
                cases = json.load(f)
        except Exception:
            cases = []

        initial_len = len(cases)
        if status:
            remaining = [c for c in cases if c.get("status") != status]
        else:
            remaining = []

        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(remaining, f, indent=2)

        cleared_count = initial_len - len(remaining)
        logger.info(f"Cleared {cleared_count} cases from unresolved queue (Filter: {status or 'ALL'}).")
        return cleared_count
