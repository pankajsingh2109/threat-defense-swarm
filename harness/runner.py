import asyncio
import time
from typing import Dict, Any, List
from httpx import AsyncClient, ASGITransport
from shared.config import settings
from shared.logger import setup_logger
from shared.schemas.events import RawStreamItem
from shared.utilities.http import set_override_clients
from services.triage.app.main import app as triage_app
from services.resolution.app.main import app as resolution_app
from services.saboteur.app.injector import chaos_injector
from harness.scenarios.library import generate_benchmark_scenarios
from harness.evaluators import generate_evaluation_report

logger = setup_logger("harness-runner")

async def run_evaluation_benchmark(run_count: int = 100, seed: int = 12345) -> Dict[str, Any]:
    """Executes full automated evaluation benchmark across N scenarios."""
    logger.info(f"Starting evaluation benchmark run (count={run_count}, seed={seed})")
    
    # Reset saboteur seed
    chaos_injector.reset_seed(seed)
    
    scenarios = generate_benchmark_scenarios(count=run_count, seed=seed)
    results: List[Dict[str, Any]] = []

    triage_transport = ASGITransport(app=triage_app)
    resolution_transport = ASGITransport(app=resolution_app)

    async with AsyncClient(transport=triage_transport, base_url="http://localhost:8001") as triage_client:
        async with AsyncClient(transport=resolution_transport, base_url="http://localhost:8002") as res_client:
            set_override_clients(triage_client=triage_client, resolution_client=res_client)
            try:
                for scenario in scenarios:
                    start_t = time.time()

                    # Optionally inject prompt chaos into raw text via Saboteur
                    if chaos_injector.should_inject_prompt():
                        scenario.raw_text = chaos_injector.inject_prompt(scenario.raw_text)

                    # Submit to Triage /ingest endpoint
                    resp = await triage_client.post("/ingest", json=scenario.model_dump())
                    latency_ms = (time.time() - start_t) * 1000

                    if resp.status_code == 200:
                        data = resp.json()
                        actual_verdict = data.get("verdict", "unknown")
                        
                        # Evaluate scenario success: verdict matches expected or handled gracefully
                        is_success = (actual_verdict == scenario.expected_verdict) or (
                            scenario.expected_verdict == "insufficient_context" and actual_verdict in ["insufficient_context", "unresolved"]
                        ) or (
                            actual_verdict in ["block_ip", "quarantine", "monitor"] and scenario.expected_verdict in ["block_ip", "quarantine"]
                        )

                        run_record = {
                            "run_id": scenario.run_id,
                            "threat_id": data.get("threat_id", "unknown"),
                            "verdict": actual_verdict,
                            "expected_verdict": scenario.expected_verdict,
                            "success": is_success,
                            "latency_ms": round(latency_ms, 2),
                            "chaos_events": data.get("chaos_events", []),
                            "clarification_attempts": data.get("clarification_attempts", 0),
                            "investigation_iterations": data.get("investigation_iterations", 0)
                        }
                    else:
                        run_record = {
                            "run_id": scenario.run_id,
                            "threat_id": "error",
                            "verdict": "error",
                            "expected_verdict": scenario.expected_verdict,
                            "success": False,
                            "latency_ms": round(latency_ms, 2),
                            "chaos_events": ["http_error"],
                            "clarification_attempts": 0,
                            "investigation_iterations": 0
                        }

                    results.append(run_record)
            finally:
                set_override_clients(triage_client=None, resolution_client=None)

    report = generate_evaluation_report(results, output_dir="reports")
    logger.info(f"Evaluation benchmark completed. Overall success rate: {report['metrics']['success_rate_pct']}%")
    return report

if __name__ == "__main__":
    asyncio.run(run_evaluation_benchmark(settings.run_count, settings.chaos_seed))
