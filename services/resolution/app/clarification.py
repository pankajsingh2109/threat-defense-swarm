import httpx
from typing import Optional, Tuple
from shared.config import settings
from shared.logger import setup_logger
from shared.schemas.a2a import A2AContext, ClarificationRequest, ClarificationResponse, MessageType
from shared.schemas.events import TerminalResult, Verdict

logger = setup_logger("resolution-clarification")
MAX_CLARIFICATION_ATTEMPTS = 2

async def handle_clarification_loop(
    context: A2AContext,
    run_id: Optional[str] = None
) -> Tuple[A2AContext, int, bool]:
    """
    Executes bounded clarification loop (max 2 attempts) with Service 1 if context is incomplete.
    Returns (updated_context, attempts_made, is_resolved).
    """
    attempts = 0

    # Check if vital information is missing
    if context.source_ip:
        return context, 0, True

    logger.info(f"Context missing source_ip for threat: {context.threat_id}. Initiating clarification loop.")

    for attempt in range(1, MAX_CLARIFICATION_ATTEMPTS + 1):
        attempts = attempt
        logger.info(f"Clarification attempt {attempt}/{MAX_CLARIFICATION_ATTEMPTS} for threat: {context.threat_id}")

        req = ClarificationRequest(
            message_type=MessageType.CLARIFICATION_REQUEST,
            threat_id=context.threat_id,
            clarification_needed=["source_ip"]
        )

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(f"{settings.triage_url}/a2a/clarify", json=req.model_dump())
                if resp.status_code == 200:
                    clar_resp = ClarificationResponse(**resp.json())
                    if "source_ip" in clar_resp.provided_data and clar_resp.provided_data["source_ip"]:
                        context.source_ip = clar_resp.provided_data["source_ip"]
                        logger.info(f"Clarification successful on attempt {attempt}: IP={context.source_ip}")
                        return context, attempts, True
        except Exception as e:
            logger.warning(f"Clarification request failed on attempt {attempt}: {e}")

    logger.warning(f"Clarification loop exhausted ({MAX_CLARIFICATION_ATTEMPTS} attempts) for threat: {context.threat_id}")
    return context, attempts, False
