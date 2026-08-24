import json
import time
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from shared.config import settings
from shared.logger import setup_logger
from shared.unresolved_queue import get_queue_stats, get_unresolved_cases
from ui.service_manager import ServiceManager
from rag.retriever import HybridKnowledgeRetriever, DocumentChunk

logger = setup_logger("rag-engine")


class SwarmRAGEngine:
    """Retrieval-Augmented Generation (RAG) incident intelligence engine."""

    def __init__(self, reports_dir: str = "reports", queue_path: str = "data/unresolved_cases.json"):
        self.retriever = HybridKnowledgeRetriever(reports_dir=reports_dir, queue_path=queue_path)
        self.client: Optional[AsyncOpenAI] = None
        if settings.openai_api_key and settings.openai_api_key != "your_key_here":
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def answer_query(self, query: str, top_k: int = 6) -> Dict[str, Any]:
        """
        Retrieves relevant incident context, inspects live service states & unresolved queue,
        and generates a cited response.
        """
        start_t = time.time()
        
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

        # 5. Generate Response via LLM (or deterministic fallback)
        if self.client:
            try:
                system_prompt = (
                    "You are the Threat Defense Swarm Incident Intelligence Assistant. "
                    "Your role is to provide accurate, concise, and structured cybersecurity incident analysis "
                    "to human security analysts and operators.\n\n"
                    "Instructions:\n"
                    "1. Always consult the provided LIVE SYSTEM STATUS and RETRIEVED KNOWLEDGE CONTEXT.\n"
                    "2. If the user asks about results or metrics, cite exact benchmark numbers (P50/P95 latency, success rate, prompt defense rate).\n"
                    "3. If the user asks about unresolved or incomplete cases, explain why they failed (e.g. Service 2 downtime/communication failure), "
                    "show which threat IDs are currently queued, and note that they will be automatically/manually re-triaged once Service 2 is back up.\n"
                    "4. If the user asks about specific runs or threats, detail the raw input, classification, verdict, and investigation reasoning.\n"
                    "5. Format output cleanly in GitHub Markdown with bullet points, bold tags, and markdown tables where appropriate.\n"
                    "6. List the cited sources/threat IDs at the end."
                )

                user_prompt = (
                    f"{system_state_text}\n\n"
                    f"RETRIEVED KNOWLEDGE CONTEXT:\n"
                    f"{retrieved_context_text}\n\n"
                    f"USER QUESTION: {query}"
                )

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
        """Deterministic context synthesis when LLM is offline."""
        q_lower = query.lower()

        # Case 1: Asking about unresolved cases / Service 2 downtime
        if any(k in q_lower for k in ["unresolved", "incomplete", "service 2", "down", "pending", "queue"]):
            pending_count = queue_stats["pending_cases"]
            resolved_count = queue_stats["resolved_cases"]
            lines = [
                "### 🔍 Unresolved & Incomplete Incident Summary",
                f"- **Pending Unresolved Cases in Queue:** `{pending_count}`",
                f"- **Resolved Cases (Post-Replay):** `{resolved_count}`",
                f"- **Total Queued Cases:** `{queue_stats['total_cases']}`\n",
                "#### 🛡️ System Response to Service 2 Downtime:",
                "When **Service 2 (Resolution Agent)** is offline, Service 1 (Triage Agent) performs **3 exponential backoff retries**. "
                "Upon exhausting retries, it produces an **`unresolved`** verdict with `success: false` and safely routes the incident into the "
                "**Dead-Letter Queue (`data/unresolved_cases.json`)**.\n"
            ]

            if pending_cases:
                lines.append("#### 📋 Current Pending Cases Waiting for Replay:")
                for c in pending_cases[:5]:
                    lines.append(f"- **{c.get('threat_id')}** (`{c.get('run_id')}`): Intent `{c.get('intent_category')}` — Reason: *{c.get('failure_reason')}*")
                lines.append("\n> 💡 **Action Item:** Once Service 2 is online, navigate to the **Unresolved Cases & Replay** tab in the UI and click **'Replay Pending Cases'** to resolve them.")
            else:
                lines.append("✅ **All cases are currently resolved.** There are no pending cases in the backlog.")

            return "\n".join(lines)

        # Case 2: Asking about metrics / benchmark results
        if any(k in q_lower for k in ["metric", "result", "success rate", "performance", "p50", "p95", "latency", "benchmark"]):
            report_chunk = next((c for c in chunks if c.doc_type == "report_metric"), None)
            if report_chunk:
                return (
                    "### 📊 Swarm Benchmark Results & Performance\n\n"
                    f"{report_chunk.content}\n\n"
                    f"#### 🛰️ Live Service State:\n"
                    f"{system_state}"
                )

        # Case 3: Specific run / threat lookup
        run_chunk = next((c for c in chunks if c.doc_type == "run_case"), None)
        if run_chunk:
            return (
                f"### 🛡️ Incident Analysis — {run_chunk.title}\n\n"
                f"{run_chunk.content}\n\n"
                f"**Retrieved Context Summary:**\n"
                + "\n".join([f"- **{c.title}**: {c.content[:150]}..." for c in chunks[:3]])
            )

        # General synthesis
        return (
            "### 🤖 Swarm Intelligence Report\n\n"
            f"**Query:** *{query}*\n\n"
            f"**Live System Status:**\n{system_state}\n\n"
            "**Retrieved Evidence:**\n"
            + "\n".join([f"- **{c.title}** ({c.doc_type}):\n  {c.content[:200]}..." for c in chunks[:3]])
        )
