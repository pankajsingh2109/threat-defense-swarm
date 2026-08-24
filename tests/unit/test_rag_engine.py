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
