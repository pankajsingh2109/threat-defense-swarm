import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from httpx import AsyncClient, ASGITransport

from shared.config import settings
from shared.logger import setup_logger
from shared.schemas.events import RawStreamItem, Verdict
from shared.unresolved_queue import get_unresolved_cases, mark_case_resolved, get_queue_stats
from shared.utilities.http import set_override_clients, get_resolution_client
from services.triage.app.main import app as triage_app
from services.resolution.app.main import app as resolution_app
from harness.evaluators import generate_evaluation_report

logger = setup_logger("replay-engine")


async def is_service_healthy(url: str, timeout: float = 1.0) -> bool:
    """Probes a service's /health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{url}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def replay_single_case(
    case: Dict[str, Any],
    triage_client: Optional[AsyncClient] = None
) -> Dict[str, Any]:
    """Replays a single unresolved case through the triage & resolution pipeline."""
    threat_id = case.get("threat_id")
    raw_text = case.get("raw_text", "")
    source = case.get("source", "replay_stream")
    run_id = case.get("run_id", f"replay_{threat_id}")

    item = RawStreamItem(
        source=source,
        raw_text=raw_text,
        run_id=run_id
    )

    start_t = time.time()
    try:
        if triage_client is not None:
            resp = await triage_client.post("/ingest", json=item.model_dump())
            result = resp.json()
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{settings.triage_url}/ingest", json=item.model_dump())
                result = resp.json()

        verdict = result.get("verdict", Verdict.UNRESOLVED.value)
        reason = result.get("reason", "Replayed successfully")
        success = result.get("success", False)

        if verdict != Verdict.UNRESOLVED.value:
            # Successfully resolved!
            mark_case_resolved(
                threat_id=threat_id,
                verdict=verdict,
                reason=reason,
                details=result
            )
            logger.info(f"Successfully replayed and resolved case {threat_id} -> Verdict: {verdict}")
            return {
                "threat_id": threat_id,
                "status": "resolved",
                "verdict": verdict,
                "reason": reason,
                "latency_ms": round((time.time() - start_t) * 1000, 2),
                "details": result
            }
        else:
            logger.warning(f"Replay for case {threat_id} remained UNRESOLVED.")
            return {
                "threat_id": threat_id,
                "status": "pending",
                "verdict": verdict,
                "reason": reason,
                "latency_ms": round((time.time() - start_t) * 1000, 2),
                "details": result
            }
    except Exception as e:
        logger.error(f"Replay failed for case {threat_id}: {e}")
        return {
            "threat_id": threat_id,
            "status": "failed",
            "verdict": Verdict.UNRESOLVED.value,
            "reason": str(e),
            "latency_ms": round((time.time() - start_t) * 1000, 2)
        }


async def replay_all_pending_cases(
    use_inprocess_fallback: bool = True
) -> Dict[str, Any]:
    """
    Finds all pending unresolved cases in Dead-Letter Queue and re-processes them.
    If services are running via HTTP, uses HTTP clients; otherwise falls back to in-process ASGI transports.
    """
    pending_cases = get_unresolved_cases(status="pending")
    if not pending_cases:
        return {
            "total_pending": 0,
            "replayed": 0,
            "resolved": 0,
            "still_pending": 0,
            "results": [],
            "message": "No pending unresolved cases in queue."
        }

    # Check if external HTTP services are running
    s1_healthy = await is_service_healthy(settings.triage_url)
    s2_healthy = await is_service_healthy(settings.resolution_url)

    results = []
    if s1_healthy and s2_healthy:
        logger.info(f"Replaying {len(pending_cases)} pending cases via live HTTP microservices...")
        tasks = [replay_single_case(case, triage_client=None) for case in pending_cases]
        results = await asyncio.gather(*tasks)
    elif use_inprocess_fallback:
        logger.info(f"Replaying {len(pending_cases)} pending cases via in-process ASGI transports...")
        triage_transport = ASGITransport(app=triage_app)
        resolution_transport = ASGITransport(app=resolution_app)
        async with AsyncClient(transport=triage_transport, base_url="http://localhost:8001") as triage_client:
            async with AsyncClient(transport=resolution_transport, base_url="http://localhost:8002") as res_client:
                set_override_clients(triage_client=triage_client, resolution_client=res_client)
                try:
                    tasks = [replay_single_case(case, triage_client=triage_client) for case in pending_cases]
                    results = await asyncio.gather(*tasks)
                finally:
                    set_override_clients(triage_client=None, resolution_client=None)
    else:
        return {
            "total_pending": len(pending_cases),
            "replayed": 0,
            "resolved": 0,
            "still_pending": len(pending_cases),
            "results": [],
            "message": "Services are offline. Start Service 1 and Service 2 before replaying."
        }

    resolved_count = sum(1 for r in results if r.get("status") == "resolved")
    still_pending = len(pending_cases) - resolved_count

    # Refresh latest report if exists
    _update_reports_post_replay(results)

    return {
        "total_pending": len(pending_cases),
        "replayed": len(results),
        "resolved": resolved_count,
        "still_pending": still_pending,
        "results": results,
        "message": f"Replayed {len(results)} cases: {resolved_count} resolved, {still_pending} pending."
    }


def _update_reports_post_replay(replay_results: List[Dict[str, Any]]):
    """Updates latest_report.json and latest_report.md with replayed verdicts."""
    report_file = Path("reports/latest_report.json")
    if not report_file.exists():
        return

    try:
        with open(report_file, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        runs = report_data.get("runs", [])
        replayed_map = {r["threat_id"]: r for r in replay_results if r.get("status") == "resolved"}

        updated = False
        for run in runs:
            t_id = run.get("threat_id")
            if t_id in replayed_map:
                res_info = replayed_map[t_id]
                run["verdict"] = res_info["verdict"]
                run["reason"] = f"[REPLAY RESOLVED] {res_info['reason']}"
                run["success"] = True
                updated = True

        if updated:
            # Re-generate structured report
            generate_evaluation_report(runs, output_dir="reports")
            logger.info("Evaluation report successfully updated following replay.")
    except Exception as e:
        logger.warning(f"Could not update evaluation report after replay: {e}")
