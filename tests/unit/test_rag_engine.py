import pytest
from rag.retriever import HybridKnowledgeRetriever
from rag.engine import SwarmRAGEngine

@pytest.mark.asyncio
async def test_rag_retriever_indexing():
    retriever = HybridKnowledgeRetriever()
    assert len(retriever.chunks) > 0

    # Query metrics
    metrics_results = retriever.retrieve("What is the success rate and latency metrics?", top_k=3)
    assert len(metrics_results) > 0
    assert any(c.doc_type in ["report_metric", "architecture"] for c in metrics_results)

    # Query unresolved cases
    unresolved_results = retriever.retrieve("Show unresolved cases during Service 2 downtime", top_k=3)
    assert len(unresolved_results) > 0


@pytest.mark.asyncio
async def test_rag_engine_query():
    engine = SwarmRAGEngine()
    res = await engine.answer_query("What is the system policy when Service 2 is offline?")

    assert "answer" in res
    assert len(res["answer"]) > 10
    assert "sources" in res
    assert "system_status" in res


@pytest.mark.asyncio
async def test_rag_engine_tool_execution():
    engine = SwarmRAGEngine()
    
    # Test flush_queue tool execution
    flush_res = await engine.execute_tool("flush_queue", {"target": "resolved"})
    assert flush_res["status"] == "success"

    # Test tool dispatch in query
    action_res = await engine.answer_query("Flush all resolved cases from queue")
    assert "answer" in action_res
