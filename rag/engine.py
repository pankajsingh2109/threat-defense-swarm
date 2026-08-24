import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
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
                return {"status": "success", "message": "Started all 3 swarm microservices.", "details": res}
            else:
                res = ServiceManager.start_service(svc)
                await asyncio.sleep(0.5)
                return {"status": "success", "message": f"Started {svc} service.", "details": res}

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
            return {"status": "success", "message": f"Flushed {cleared} cases from queue ({target})."}

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

        # 1. Retrieve relevant chunks
        relevant_chunks: List[DocumentChunk] = self.retriever.retrieve(query, top_k=top_k)

        # 2. Get live real-time system state
        service_statuses = ServiceManager.get_all_statuses()
        queue_stats = get_queue_stats()
        pending_cases = get_unresolved_cases(status="pending")

        # 3. Build live system state context block
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

        # 4. Assemble Knowledge Context Block
        retrieved_context_text = "\n\n---\n\n".join([
            f"Source [{c.doc_id}] ({c.title}):\n{c.content}"
            for c in relevant_chunks
        ])

        system_prompt = (
            "You are the Threat Defense Swarm Agentic Incident Intelligence Assistant. "
            "You have full operational capabilities to both analyze incidents and execute actions on behalf of the security operator.\n\n"
            "Capabilities & Tools:\n"
            "- You can start, stop, or restart microservices (`start_services`, `stop_services`, `restart_services`).\n"
            "- You can trigger replay of unresolved backlog incidents (`replay_unresolved_cases`).\n"
            "- You can flush queues or telemetry (`flush_queue`, `flush_telemetry_records`).\n"
            "- You can launch automated benchmark evaluation suites (`run_benchmark_evaluation`).\n"
            "- You can answer questions using the provided live system telemetry and retrieved knowledge.\n\n"
            "Instructions:\n"
            "1. If the user commands an operational action (e.g. 'start all services and replay unresolved cases', 'flush the queue'), "
            "CALL the appropriate tool(s) to execute the request in real time.\n"
            "2. After executing tools, synthesize a clear summary of what actions were performed and what outcomes were achieved.\n"
            "3. If the user asks an informational question, consult the retrieved context and live system status to give a structured, cited answer.\n"
            "4. Format responses cleanly with GitHub Markdown, bold key entities, and bullet points."
        )

        user_prompt = (
            f"{system_state_text}\n\n"
            f"RETRIEVED KNOWLEDGE CONTEXT:\n"
            f"{retrieved_context_text}\n\n"
            f"USER QUERY/COMMAND: {query}"
        )

        if self.client:
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]

                # Step 1: Initial call with tools
                response = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    tools=RAG_TOOLS,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=800
                )

                msg = response.choices[0].message

                # Step 2: Handle Tool Calls
                if msg.tool_calls:
                    messages.append(msg)
                    for tool_call in msg.tool_calls:
                        func_name = tool_call.function.name
                        try:
                            func_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                        except Exception:
                            func_args = {}

                        tool_res = await self.execute_tool(func_name, func_args)
                        actions_executed.append({
                            "tool": func_name,
                            "arguments": func_args,
                            "result": tool_res
                        })

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": json.dumps(tool_res)
                        })

                    # Step 3: Get final synthesized response from LLM
                    final_response = await self.client.chat.completions.create(
                        model=settings.openai_model,
                        messages=messages,
                        temperature=0.2,
                        max_tokens=800
                    )
                    answer_text = final_response.choices[0].message.content or "Action executed successfully."
                else:
                    answer_text = msg.content or "No response generated."

            except Exception as e:
                logger.warning(f"OpenAI API call failed in RAG engine: {e}. Checking deterministic actions.")
                answer_text, actions_executed = await self._deterministic_action_and_synthesis(
                    query, system_state_text, relevant_chunks, queue_stats, pending_cases
                )
        else:
            answer_text, actions_executed = await self._deterministic_action_and_synthesis(
                query, system_state_text, relevant_chunks, queue_stats, pending_cases
            )

        latency_ms = round((time.time() - start_t) * 1000, 2)

        return {
            "query": query,
            "answer": answer_text,
            "actions_executed": actions_executed,
            "sources": [c.to_dict() for c in relevant_chunks],
            "system_status": {
                "services": ServiceManager.get_all_statuses(),
                "queue_stats": get_queue_stats()
            },
            "latency_ms": latency_ms
        }

    async def _deterministic_action_and_synthesis(
        self,
        query: str,
        system_state: str,
        chunks: List[DocumentChunk],
        queue_stats: Dict[str, Any],
        pending_cases: List[Dict[str, Any]]
    ) -> (str, List[Dict[str, Any]]):
        """Deterministic action execution and context synthesis when LLM is offline."""
        q_lower = query.lower()
        actions: List[Dict[str, Any]] = []
        action_notes: List[str] = []

        # Action: Start all services
        if "start" in q_lower or "up" in q_lower:
            if "service" in q_lower or "all" in q_lower or "swarm" in q_lower:
                res = await self.execute_tool("start_services", {"service_name": "all"})
                actions.append({"tool": "start_services", "result": res})
                action_notes.append("⚡ **Action Executed:** Started all 3 swarm microservices.")

        # Action: Replay unresolved cases
        if "replay" in q_lower or "resolve" in q_lower:
            res = await self.execute_tool("replay_unresolved_cases", {})
            actions.append({"tool": "replay_unresolved_cases", "result": res})
            rep_msg = res.get("summary", {}).get("message", "Replayed pending backlog cases.")
            action_notes.append(f"🔄 **Action Executed:** Replay Engine executed $\\rightarrow$ {rep_msg}")

        # Action: Flush queue
        if "flush" in q_lower and "queue" in q_lower:
            target = "all" if "all" in q_lower or "entire" in q_lower else "resolved"
            res = await self.execute_tool("flush_queue", {"target": target})
            actions.append({"tool": "flush_queue", "result": res})
            action_notes.append(f"🧹 **Action Executed:** {res.get('message')}")

        if action_notes:
            fresh_stats = get_queue_stats()
            fresh_services = ServiceManager.get_all_statuses()
            resp_lines = [
                "### 🤖 Swarm Operational Action Completed\n",
                "\n".join(action_notes),
                "\n#### 🛰️ Updated System Posture:",
                f"- **Service 1 (Triage):** `{fresh_services['triage']['status']}`",
                f"- **Service 2 (Resolution):** `{fresh_services['resolution']['status']}`",
                f"- **Pending Queue Backlog:** `{fresh_stats['pending_cases']}` cases remaining (`{fresh_stats['resolved_cases']}` resolved).",
                "\n*All changes and resolved verdicts have been synchronized with `latest_report.json` and the Executive SOC Dashboard.*"
            ]
            return "\n".join(resp_lines), actions

        # Q&A Synthesis
        if any(k in q_lower for k in ["unresolved", "incomplete", "service 2", "down", "pending", "queue"]):
            lines = [
                "### 🔍 Unresolved & Incomplete Incident Summary",
                f"- **Pending Unresolved Cases in Queue:** `{queue_stats['pending_cases']}`",
                f"- **Resolved Cases (Post-Replay):** `{queue_stats['resolved_cases']}`",
                f"- **Total Queued Cases:** `{queue_stats['total_cases']}`\n",
                "#### 🛡️ Resilience Architecture:",
                "When **Service 2 (Resolution Agent)** is offline, Service 1 (Triage Agent) catches network timeouts and "
                "safely routes the incident to the **Dead-Letter Queue (`data/unresolved_cases.json`)** with an `unresolved` verdict.\n"
            ]
            if pending_cases:
                lines.append("#### 📋 Current Pending Cases:")
                for c in pending_cases[:5]:
                    lines.append(f"- **{c.get('threat_id')}**: {c.get('failure_reason')}")
            else:
                lines.append("✅ **All cases are currently resolved.**")
            return "\n".join(lines), actions

        if any(k in q_lower for k in ["metric", "result", "success rate", "performance", "p50", "p95", "latency", "benchmark"]):
            report_chunk = next((c for c in chunks if c.doc_type == "report_metric"), None)
            if report_chunk:
                return f"### 📊 Benchmark Performance\n\n{report_chunk.content}", actions

        return (
            "### 🤖 Swarm Intelligence Report\n\n"
            f"**Query:** *{query}*\n\n"
            f"**Live System Status:**\n{system_state}\n\n"
            "**Retrieved Context:**\n"
            + "\n".join([f"- **{c.title}**: {c.content[:200]}..." for c in chunks[:3]]),
            actions
        )
