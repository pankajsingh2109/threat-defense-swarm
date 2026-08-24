import json
import math
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from shared.config import settings
from shared.logger import setup_logger
from shared.unresolved_queue import get_unresolved_cases, get_queue_stats

logger = setup_logger("rag-retriever")


class DocumentChunk:
    def __init__(self, doc_id: str, title: str, content: str, metadata: Dict[str, Any], doc_type: str):
        self.doc_id = doc_id
        self.title = title
        self.content = content
        self.metadata = metadata
        self.doc_type = doc_type  # 'report_metric', 'run_case', 'unresolved_case', 'architecture'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata,
            "doc_type": self.doc_type
        }


class HybridKnowledgeRetriever:
    """Indexes reports, runs, dead-letter queue, and architecture docs for hybrid retrieval."""

    def __init__(self, reports_dir: str = "reports", queue_path: str = "data/unresolved_cases.json"):
        self.reports_dir = Path(reports_dir)
        self.queue_path = Path(queue_path)
        self.chunks: List[DocumentChunk] = []
        self._build_index()

    def refresh(self):
        """Rebuilds the in-memory knowledge index from disk."""
        self._build_index()

    def _build_index(self):
        self.chunks = []
        self._index_architecture_docs()
        self._index_evaluation_report()
        self._index_unresolved_queue()
        logger.info(f"RAG Knowledge Index built with {len(self.chunks)} chunks.")

    def _index_architecture_docs(self):
        arch_content = (
            "Threat Defense Swarm Architecture Overview:\n"
            "- Service 1 (Triage Agent, port 8001): Ingests raw telemetry, applies <data> tag sanitization, "
            "evaluates prompt injection flags, classifies intent (Threat vs Noise), and compresses context.\n"
            "- Service 2 (Resolution Agent, port 8002): Receives A2A envelope, executes bounded clarification loop "
            "(max 2 attempts), bounded investigation loop (max 3 iterations) calling IP reputation, auth frequency, "
            "and geo lookup tools, then issues structured verdicts (block_ip, quarantine, monitor, allow, unresolved).\n"
            "- Service 3 (Saboteur Chaos, port 8003): Injects adversarial prompt overrides, drops transit packets, "
            "and simulates HTTP 503 errors on mock tools.\n"
            "- Resilience & Downtime Policy: When Service 2 is offline, Service 1 retries 3 times with exponential backoff. "
            "Upon failure, it outputs verdict 'unresolved' and archives the incident into the Dead-Letter Queue (data/unresolved_cases.json) "
            "so it can be replayed when Service 2 comes back online."
        )
        self.chunks.append(DocumentChunk(
            doc_id="doc_arch_overview",
            title="System Architecture & Service 2 Resilience",
            content=arch_content,
            metadata={"category": "architecture"},
            doc_type="architecture"
        ))

    def _index_evaluation_report(self):
        json_path = self.reports_dir / "latest_report.json"
        if not json_path.exists():
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 1. Summary Metrics Chunk
            metrics = data.get("metrics", {})
            metrics_summary = (
                f"Evaluation Benchmark Summary Metrics:\n"
                f"- Total Runs: {data.get('total_runs', 0)}\n"
                f"- Successful Runs: {data.get('successful_runs', 0)}\n"
                f"- Failed Runs: {data.get('failed_runs', 0)}\n"
                f"- Success Rate: {metrics.get('success_rate_pct', 0.0)}%\n"
                f"- Failure Rate: {metrics.get('failure_rate_pct', 0.0)}%\n"
                f"- Mean Latency: {metrics.get('mean_latency_ms', 0.0)} ms\n"
                f"- P50 Latency: {metrics.get('p50_latency_ms', 0.0)} ms\n"
                f"- P95 Latency: {metrics.get('p95_latency_ms', 0.0)} ms\n"
                f"- P99 Latency: {metrics.get('p99_latency_ms', 0.0)} ms\n"
                f"- Prompt Injection Defense Rate: {metrics.get('prompt_injection_defense_rate_pct', 0.0)}%\n"
                f"- Tool 503 Recovery Rate: {metrics.get('tool_503_recovery_rate_pct', 0.0)}%\n"
                f"- Clarification Success Rate: {metrics.get('clarification_success_rate_pct', 0.0)}%\n"
                f"- Unresolved Rate: {metrics.get('unresolved_rate_pct', 0.0)}%"
            )
            self.chunks.append(DocumentChunk(
                doc_id="doc_benchmark_metrics",
                title="Latest Benchmark Metrics & Performance Report",
                content=metrics_summary,
                metadata={"total_runs": data.get("total_runs")},
                doc_type="report_metric"
            ))

            # 2. Individual Runs Chunks
            for run in data.get("runs", []):
                run_id = run.get("run_id", "unknown")
                threat_id = run.get("threat_id", "unknown")
                verdict = run.get("verdict", "unknown")
                success = run.get("success", False)
                reason = run.get("reason", "N/A")
                raw_text = run.get("raw_text", "")
                chaos_evs = ", ".join(run.get("chaos_events", [])) or "None"

                run_text = (
                    f"Run ID: {run_id} | Threat ID: {threat_id}\n"
                    f"Source: {run.get('source')} | Raw Input: \"{raw_text}\"\n"
                    f"Intent: {run.get('intent')} (Category: {run.get('intent_category')}, Confidence: {run.get('intent_confidence')})\n"
                    f"Sanitization Flagged: {run.get('sanitization_flagged')} (Reason: {run.get('flag_reason')})\n"
                    f"Verdict: {verdict} (Expected: {run.get('expected_verdict')}) | Success: {success}\n"
                    f"Reason: {reason}\n"
                    f"Latency: {run.get('latency_ms')} ms | Chaos Events: {chaos_evs}\n"
                    f"Clarification Attempts: {run.get('clarification_attempts')} | Investigation Iterations: {run.get('investigation_iterations')}"
                )

                self.chunks.append(DocumentChunk(
                    doc_id=f"run_{run_id}",
                    title=f"Evaluation Run {run_id} ({verdict})",
                    content=run_text,
                    metadata={
                        "run_id": run_id,
                        "threat_id": threat_id,
                        "verdict": verdict,
                        "success": success,
                        "category": run.get("intent_category")
                    },
                    doc_type="run_case"
                ))
        except Exception as e:
            logger.warning(f"Error indexing evaluation report: {e}")

    def _index_unresolved_queue(self):
        try:
            cases = get_unresolved_cases(queue_path=self.queue_path)
            stats = get_queue_stats(queue_path=self.queue_path)

            queue_summary = (
                f"Dead-Letter Unresolved Queue Summary:\n"
                f"- Total Unresolved Logged: {stats['total_cases']}\n"
                f"- Pending Replay (Service 2 Downtime backlog): {stats['pending_cases']}\n"
                f"- Resolved After Replay: {stats['resolved_cases']}\n"
                f"- Replay Ready: {'Yes, pending cases present' if stats['pending_cases'] > 0 else 'No pending cases'}"
            )
            self.chunks.append(DocumentChunk(
                doc_id="doc_queue_summary",
                title="Dead-Letter Unresolved Queue Summary",
                content=queue_summary,
                metadata={"pending": stats["pending_cases"]},
                doc_type="unresolved_case"
            ))

            for case in cases:
                threat_id = case.get("threat_id", "unknown")
                status = case.get("status", "pending")
                raw_text = case.get("raw_text", "")
                failure_reason = case.get("failure_reason", "Service 2 unreachable")
                res_verdict = case.get("resolved_verdict", "N/A")
                res_reason = case.get("resolved_reason", "N/A")

                case_text = (
                    f"Unresolved Queue Case — Threat ID: {threat_id} | Status: {status.upper()}\n"
                    f"Run ID: {case.get('run_id')} | Created At: {case.get('created_at')}\n"
                    f"Raw Telemetry: \"{raw_text}\"\n"
                    f"Intent: {case.get('intent')} ({case.get('intent_category')})\n"
                    f"Original Failure Reason: {failure_reason}\n"
                    f"Resolved Verdict: {res_verdict} (Reason: {res_reason})\n"
                    f"Resolved At: {case.get('resolved_at', 'Pending')}"
                )

                self.chunks.append(DocumentChunk(
                    doc_id=f"queue_{threat_id}",
                    title=f"Unresolved Queue Item {threat_id} [{status}]",
                    content=case_text,
                    metadata={
                        "threat_id": threat_id,
                        "status": status,
                        "resolved_verdict": res_verdict
                    },
                    doc_type="unresolved_case"
                ))
        except Exception as e:
            logger.warning(f"Error indexing unresolved queue: {e}")

    def retrieve(self, query: str, top_k: int = 5) -> List[DocumentChunk]:
        """
        Hybrid retrieval combining exact keyword / entity match (threat ID, run ID, status)
        with token BM25/TF-IDF similarity scoring.
        """
        self.refresh()
        if not self.chunks:
            return []

        query_lower = query.lower()
        scored_chunks: List[Tuple[float, DocumentChunk]] = []

        # Extract specific entities from query
        threat_match = re.search(r"threat-[0-9a-fA-F]+", query)
        run_match = re.search(r"run_[0-9]+", query_lower)
        is_asking_unresolved = any(k in query_lower for k in ["unresolved", "incomplete", "service 2 down", "offline", "pending", "queue", "failed"])
        is_asking_metrics = any(k in query_lower for k in ["success rate", "metrics", "p50", "p95", "p99", "latency", "benchmark", "overall", "performance"])

        query_tokens = set(re.findall(r"\w+", query_lower))

        for chunk in self.chunks:
            score = 0.0
            content_lower = chunk.content.lower()

            # Exact entity boosts
            if threat_match and threat_match.group(0).lower() in content_lower:
                score += 50.0
            if run_match and run_match.group(0).lower() in content_lower:
                score += 50.0

            # Intent-based boosts
            if is_asking_unresolved and chunk.doc_type == "unresolved_case":
                score += 20.0
            if is_asking_metrics and chunk.doc_type == "report_metric":
                score += 25.0

            # Specific verdict queries
            if "block_ip" in query_lower and "verdict: block_ip" in content_lower:
                score += 10.0
            if "prompt injection" in query_lower and "prompt_injection" in content_lower:
                score += 15.0

            # Token overlap & term frequency
            content_tokens = re.findall(r"\w+", content_lower)
            if content_tokens:
                matches = sum(1 for token in query_tokens if token in content_tokens)
                overlap_ratio = matches / len(query_tokens) if query_tokens else 0
                score += overlap_ratio * 10.0

            scored_chunks.append((score, chunk))

        # Sort by score descending
        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        top_results = [chunk for score, chunk in scored_chunks[:top_k] if score > 0.0]
        # Fallback to top chunks if no score
        if not top_results:
            top_results = [chunk for _, chunk in scored_chunks[:top_k]]

        return top_results
