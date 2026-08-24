import asyncio
import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from openai import AsyncOpenAI

from shared.config import settings
from shared.logger import setup_logger
from shared.unresolved_queue import get_queue_stats, get_unresolved_cases, clear_unresolved_cases
from ui.service_manager import ServiceManager
from harness.replay import replay_all_pending_cases
from harness.runner import run_evaluation_benchmark
from rag.retriever import HybridKnowledgeRetriever, DocumentChunk

logger = setup_logger("rag-engine")

# ==========================================
# 🛠️ Agentic Tool Definitions for RAG
# ==========================================
RAG_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_services",
            "description": "Starts one or more swarm microservices ('triage', 'resolution', 'saboteur', or 'all').",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "enum": ["all", "triage", "resolution", "saboteur"],
                        "description": "Which service to start, or 'all' to start the entire swarm."
                    }
                },
                "required": ["service_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_services",
            "description": "Stops one or more swarm microservices ('triage', 'resolution', 'saboteur', or 'all').",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "enum": ["all", "triage", "resolution", "saboteur"],
                        "description": "Which service to stop, or 'all' to stop all services."
                    }
                },
                "required": ["service_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_services",
            "description": "Restarts one or more swarm microservices ('triage', 'resolution', 'saboteur', or 'all').",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "enum": ["all", "triage", "resolution", "saboteur"],
                        "description": "Which service to restart, or 'all'."
                    }
                },
                "required": ["service_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replay_unresolved_cases",
            "description": "Triggers the re-triage and resolution replay pipeline for all pending incidents in the Dead-Letter Queue once required services are online.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "flush_queue",
            "description": "Flushes/clears either 'resolved' cases or 'all' cases from the Dead-Letter Queue backlog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["resolved", "all"],
                        "description": "Whether to flush 'resolved' cases or 'all' cases."
                    }
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "flush_telemetry_records",
            "description": "Clears and resets past benchmark telemetry evaluation reports on disk.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_benchmark_evaluation",
            "description": "Launches an automated evaluation benchmark suite with N test scenarios across the swarm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario_count": {
                        "type": "integer",
                        "description": "Number of scenarios to run (e.g. 10, 20, 25, 50). Default is 20.",
                        "default": 20
                    }
                }
            }
        }
    }
]


def detect_operational_actions(query: str) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Robust intent detector that extracts operational actions from natural language commands.
    Returns a sequence of (tool_name, tool_args) to execute.
    """
    q = query.lower().strip()
    actions: List[Tuple[str, Dict[str, Any]]] = []

    # 1. Start Services
    if re.search(r"\b(start|up|boot|launch|turn on|bring up)\b", q) and not re.search(r"\b(benchmark|eval|test)\b", q):
        if re.search(r"\b(all|swarm|system|everything)\b", q) or ("service" in q and "2" not in q and "1" not in q and "3" not in q):
            actions.append(("start_services", {"service_name": "all"}))
        elif "service 1" in q or "triage" in q:
            actions.append(("start_services", {"service_name": "triage"}))
        elif "service 2" in q or "resolution" in q:
            actions.append(("start_services", {"service_name": "resolution"}))
        elif "service 3" in q or "saboteur" in q:
            actions.append(("start_services", {"service_name": "saboteur"}))
        else:
            actions.append(("start_services", {"service_name": "all"}))

    # 2. Stop Services
    if re.search(r"\b(stop|kill|shut down|shutdown|turn off|down)\b", q):
        if re.search(r"\b(all|swarm|system|everything)\b", q):
            actions.append(("stop_services", {"service_name": "all"}))
        elif "service 1" in q or "triage" in q:
            actions.append(("stop_services", {"service_name": "triage"}))
        elif "service 2" in q or "resolution" in q:
            actions.append(("stop_services", {"service_name": "resolution"}))
        elif "service 3" in q or "saboteur" in q:
            actions.append(("stop_services", {"service_name": "saboteur"}))

    # 3. Restart Services
    if re.search(r"\b(restart|reboot|cycle)\b", q):
        if re.search(r"\b(all|swarm|system)\b", q) or "service" in q:
            actions.append(("restart_services", {"service_name": "all"}))
        elif "service 1" in q or "triage" in q:
            actions.append(("restart_services", {"service_name": "triage"}))
        elif "service 2" in q or "resolution" in q:
            actions.append(("restart_services", {"service_name": "resolution"}))
        elif "service 3" in q or "saboteur" in q:
            actions.append(("restart_services", {"service_name": "saboteur"}))

    # 4. Replay Unresolved Backlog
    if re.search(r"\b(replay|resolve|re-triage|reprocess|process pending|clear backlog)\b", q):
        actions.append(("replay_unresolved_cases", {}))

    # 5. Flush Queue
    if re.search(r"\b(flush|purge|clear|empty)\b", q) and re.search(r"\b(queue|backlog|cases)\b", q) and not re.search(r"\b(replay)\b", q):
        target = "all" if re.search(r"\b(all|entire|everything)\b", q) else "resolved"
        actions.append(("flush_queue", {"target": target}))

    # 6. Flush Telemetry / Reports
    if re.search(r"\b(flush|purge|clear|reset)\b", q) and re.search(r"\b(telemetry|report|reports|benchmark data)\b", q):
        actions.append(("flush_telemetry_records", {}))

    # 7. Run Benchmark Evaluation
    if re.search(r"\b(run|launch|execute)\b", q) and re.search(r"\b(benchmark|eval|evaluation|suite)\b", q):
        # Extract scenario count if specified
        count_match = re.search(r"\b(\d+)\s*(scenarios|runs|count)?\b", q)
        count = int(count_match.group(1)) if count_match else 20
        actions.append(("run_benchmark_evaluation", {"scenario_count": count}))

    return actions


class SwarmRAGEngine:
    """Agentic Retrieval-Augmented Generation (RAG) incident intelligence and operational action engine."""

    def __init__(self, reports_dir: str = "reports", queue_path: str = "data/unresolved_cases.json"):
        self.retriever = HybridKnowledgeRetriever(reports_dir=reports_dir, queue_path=queue_path)
        self.client: Optional[AsyncOpenAI] = None
        if settings.openai_api_key and settings.openai_api_key != "your_key_here":
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a requested operational action tool."""
        logger.info(f"Agentic Tool Execution: {name}({args})")

        if name == "start_services":
            svc = args.get("service_name", "all")
            if svc == "all":
                res = ServiceManager.start_all_services()
                await asyncio.sleep(0.5)
                return {"status": "success", "message": "Started all 3 swarm microservices (Triage: 8001, Resolution: 8002, Saboteur: 8003).", "details": res}
            else:
                res = ServiceManager.start_service(svc)
                await asyncio.sleep(0.5)
                return {"status": "success", "message": f"Started {svc} service on its designated port.", "details": res}

        elif name == "stop_services":
            svc = args.get("service_name", "all")
            if svc == "all":
                for k in ["triage", "resolution", "saboteur"]:
                    ServiceManager.stop_service(k)
                return {"status": "success", "message": "Stopped all swarm microservices."}
            else:
                res = ServiceManager.stop_service(svc)
                return {"status": "success", "message": f"Stopped {svc} service.", "details": res}

        elif name == "restart_services":
            svc = args.get("service_name", "all")
            if svc == "all":
                for k in ["triage", "resolution", "saboteur"]:
                    ServiceManager.restart_service(k)
                await asyncio.sleep(0.5)
                return {"status": "success", "message": "Restarted all swarm microservices."}
            else:
                res = ServiceManager.restart_service(svc)
                await asyncio.sleep(0.5)
                return {"status": "success", "message": f"Restarted {svc} service.", "details": res}

        elif name == "replay_unresolved_cases":
            summary = await replay_all_pending_cases(use_inprocess_fallback=False)
            self.retriever.refresh()
            return {"status": "success", "summary": summary}

        elif name == "flush_queue":
            target = args.get("target", "resolved")
            cleared = clear_unresolved_cases(status="resolved" if target == "resolved" else None)
            self.retriever.refresh()
            return {"status": "success", "message": f"Flushed {cleared} cases from Dead-Letter Queue ({target})."}

        elif name == "flush_telemetry_records":
            rep_json = Path("reports/latest_report.json")
            rep_md = Path("reports/latest_report.md")
            if rep_json.exists():
                rep_json.unlink(missing_ok=True)
            if rep_md.exists():
                rep_md.unlink(missing_ok=True)
            self.retriever.refresh()
            return {"status": "success", "message": "Flushed telemetry evaluation records from disk."}

        elif name == "run_benchmark_evaluation":
            count = args.get("scenario_count", 20)
            report = await run_evaluation_benchmark(run_count=count, seed=settings.chaos_seed)
            self.retriever.refresh()
            return {
                "status": "success",
                "total_runs": report.get("total_runs"),
                "success_rate_pct": report.get("metrics", {}).get("success_rate_pct"),
                "p50_latency_ms": report.get("metrics", {}).get("p50_latency_ms")
            }

        return {"status": "error", "message": f"Unknown tool: {name}"}

    async def answer_query(self, query: str, top_k: int = 6) -> Dict[str, Any]:
        """
        Processes user query with hybrid retrieval and Agentic Tool Calling.
        Can execute actions (starting services, replaying cases, running benchmarks) and synthesize findings.
        """
        start_t = time.time()
        actions_executed: List[Dict[str, Any]] = []

        # 1. Proactive Operational Intent Detection
        detected_actions = detect_operational_actions(query)

        # If operational actions were detected, execute them directly first!
        if detected_actions:
            action_reports = []
            for tool_name, tool_args in detected_actions:
                tool_res = await self.execute_tool(tool_name, tool_args)
                actions_executed.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "result": tool_res
                })
                if tool_name == "start_services":
                    action_reports.append(f"⚡ **Started Microservices:** `{tool_args.get('service_name', 'all').upper()}` (All services initiated).")
                elif tool_name == "stop_services":
                    action_reports.append(f"⏹️ **Stopped Microservices:** `{tool_args.get('service_name', 'all').upper()}`.")
                elif tool_name == "restart_services":
                    action_reports.append(f"🔄 **Restarted Microservices:** `{tool_args.get('service_name', 'all').upper()}`.")
                elif tool_name == "replay_unresolved_cases":
                    rep_sum = tool_res.get("summary", {})
                    action_reports.append(f"🔄 **Replay Engine Executed:** {rep_sum.get('message', 'Replayed pending cases')}.")
                elif tool_name == "flush_queue":
                    action_reports.append(f"🧹 **Queue Flushed:** {tool_res.get('message')}.")
                elif tool_name == "flush_telemetry_records":
                    action_reports.append("🗑️ **Telemetry Flushed:** Evaluation reports cleared from disk.")
                elif tool_name == "run_benchmark_evaluation":
                    action_reports.append(f"🏆 **Benchmark Completed:** {tool_res.get('total_runs')} runs evaluated | Success Rate: `{tool_res.get('success_rate_pct')}%`.")

            # Fetch updated system state
            fresh_services = ServiceManager.get_all_statuses()
            fresh_stats = get_queue_stats()

            s1_badge = "🟢 ONLINE" if fresh_services["triage"]["healthy"] else "🔴 OFFLINE"
            s2_badge = "🟢 ONLINE" if fresh_services["resolution"]["healthy"] else "🔴 OFFLINE"
            s3_badge = "🟢 ONLINE" if fresh_services["saboteur"]["healthy"] else "🔴 OFFLINE"

            response_lines = [
                "### 🤖 Swarm Operational Action Executed\n",
                "\n".join(action_reports),
                "\n#### 🛰️ Updated System & Service Posture:",
                f"- **Service 1 (Triage Agent):** `{s1_badge}` (Port {fresh_services['triage']['port']})",
                f"- **Service 2 (Resolution Agent):** `{s2_badge}` (Port {fresh_services['resolution']['port']})",
                f"- **Service 3 (Saboteur Chaos):** `{s3_badge}` (Port {fresh_services['saboteur']['port']})",
                f"- **Dead-Letter Queue:** `{fresh_stats['pending_cases']}` pending backlog cases (`{fresh_stats['resolved_cases']}` resolved).",
                "\n*All operational actions and verdicts are synchronized in real-time with the Control Room and Executive SOC Dashboard.*"
            ]

            latency_ms = round((time.time() - start_t) * 1000, 2)
            return {
                "query": query,
                "answer": "\n".join(response_lines),
                "actions_executed": actions_executed,
                "sources": [],
                "system_status": {
                    "services": fresh_services,
                    "queue_stats": fresh_stats
                },
                "latency_ms": latency_ms
            }

        # 2. Informational Q&A: Retrieve relevant chunks
        relevant_chunks: List[DocumentChunk] = self.retriever.retrieve(query, top_k=top_k)

        # 3. Get live real-time system state
        service_statuses = ServiceManager.get_all_statuses()
        queue_stats = get_queue_stats()
        pending_cases = get_unresolved_cases(status="pending")

        system_state_text = (
            f"CURRENT LIVE SYSTEM STATUS:\n"
            f"- Service 1 (Triage): {service_statuses['triage']['status']}\n"
            f"- Service 2 (Resolution): {service_statuses['resolution']['status']}\n"
            f"- Service 3 (Saboteur): {service_statuses['saboteur']['status']}\n"
            f"- Unresolved Queue: {queue_stats['pending_cases']} pending cases waiting for replay "
            f"({queue_stats['resolved_cases']} already resolved out of {queue_stats['total_cases']} total).\n"
        )
        if queue_stats["pending_cases"] > 0:
            system_state_text += f"- Pending Threat IDs waiting for replay: {', '.join([c['threat_id'] for c in pending_cases[:5]])}\n"

        retrieved_context_text = "\n\n---\n\n".join([
            f"Source [{c.doc_id}] ({c.title}):\n{c.content}"
            for c in relevant_chunks
        ])

        system_prompt = (
            "You are the Threat Defense Swarm Incident Intelligence Assistant. "
            "Your role is to provide accurate, concise, and structured cybersecurity incident analysis to human operators.\n\n"
            "Instructions:\n"
            "1. Always consult the provided LIVE SYSTEM STATUS and RETRIEVED KNOWLEDGE CONTEXT.\n"
            "2. Cite exact metrics (P50/P95 latency, success rate %, prompt injection defense rate) when asked about benchmark results.\n"
            "3. If asked about unresolved or incomplete cases, explain why they failed (e.g. Service 2 downtime), list queued threat IDs, "
            "and note that you can start services and replay them whenever instructed.\n"
            "4. Format cleanly in GitHub Markdown with bold entity names and bullet points."
        )

        user_prompt = (
            f"{system_state_text}\n\n"
            f"RETRIEVED KNOWLEDGE CONTEXT:\n"
            f"{retrieved_context_text}\n\n"
            f"USER QUESTION: {query}"
        )

        if self.client:
            try:
                response = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=800
                )
                answer_text = response.choices[0].message.content or "No response generated."
            except Exception as e:
                logger.warning(f"OpenAI API call failed in RAG engine: {e}. Using deterministic synthesis.")
                answer_text = self._deterministic_synthesis(query, system_state_text, relevant_chunks, queue_stats, pending_cases)
        else:
            answer_text = self._deterministic_synthesis(query, system_state_text, relevant_chunks, queue_stats, pending_cases)

        latency_ms = round((time.time() - start_t) * 1000, 2)

        return {
            "query": query,
            "answer": answer_text,
            "actions_executed": actions_executed,
            "sources": [c.to_dict() for c in relevant_chunks],
            "system_status": {
                "services": service_statuses,
                "queue_stats": queue_stats
            },
            "latency_ms": latency_ms
        }

    def _deterministic_synthesis(
        self,
        query: str,
        system_state: str,
        chunks: List[DocumentChunk],
        queue_stats: Dict[str, Any],
        pending_cases: List[Dict[str, Any]]
    ) -> str:
        """Deterministic context synthesis for informational queries when LLM is offline."""
        q_lower = query.lower()

        # Unresolved cases inquiry
        if any(k in q_lower for k in ["unresolved", "incomplete", "service 2", "down", "pending", "queue"]):
            lines = [
                "### 🔍 Unresolved & Incomplete Incident Summary",
                f"- **Pending Unresolved Cases in Queue:** `{queue_stats['pending_cases']}`",
                f"- **Resolved Cases (Post-Replay):** `{queue_stats['resolved_cases']}`",
                f"- **Total Queued Cases:** `{queue_stats['total_cases']}`\n",
                "#### 🛡️ Resilience Architecture:",
                "When **Service 2 (Resolution Agent)** is offline, Service 1 (Triage Agent) performs **3 exponential backoff retries**. "
                "Upon exhausting retries, it produces an **`unresolved`** verdict with `success: false` and safely routes the incident into the "
                "**Dead-Letter Queue (`data/unresolved_cases.json`)**.\n"
            ]
            if pending_cases:
                lines.append("#### 📋 Current Pending Cases Waiting for Replay:")
                for c in pending_cases[:5]:
                    lines.append(f"- **{c.get('threat_id')}** (`{c.get('run_id')}`): Intent `{c.get('intent_category')}` — Reason: *{c.get('failure_reason')}*")
                lines.append("\n> 💡 **Action Item:** You can tell me **'Start all services and replay unresolved cases'** to resolve them automatically!")
            else:
                lines.append("✅ **All cases are currently resolved.** There are no pending cases in the backlog.")
            return "\n".join(lines)

        # Benchmark Metrics inquiry
        if any(k in q_lower for k in ["metric", "result", "success rate", "performance", "p50", "p95", "latency", "benchmark"]):
            report_chunk = next((c for c in chunks if c.doc_type == "report_metric"), None)
            if report_chunk:
                return (
                    "### 📊 Benchmark Performance & Evaluation Results\n\n"
                    f"{report_chunk.content}\n\n"
                    f"#### 🛰️ Live Service State:\n"
                    f"{system_state}"
                )

        # General inquiry
        return (
            "### 🤖 Swarm Intelligence Report\n\n"
            f"**Query:** *{query}*\n\n"
            f"**Live System Status:**\n{system_state}\n\n"
            "**Retrieved Knowledge Evidence:**\n"
            + "\n".join([f"- **{c.title}** ({c.doc_type}):\n  {c.content[:200]}..." for c in chunks[:3]])
        )
