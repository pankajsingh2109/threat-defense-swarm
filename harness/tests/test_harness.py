import pytest
import os
from harness.scenarios.library import generate_benchmark_scenarios
from harness.evaluators import generate_evaluation_report, calculate_percentile
from harness.runner import run_evaluation_benchmark

def test_scenario_generation():
    scenarios = generate_benchmark_scenarios(count=100, seed=12345)
    assert len(scenarios) == 100
    assert scenarios[0].run_id == "run_0001"
    assert scenarios[99].run_id == "run_0100"

def test_percentile_calculation():
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    p50 = calculate_percentile(vals, 50)
    assert p50 == 30.0

@pytest.mark.asyncio
async def test_harness_execution():
    report = await run_evaluation_benchmark(run_count=10, seed=999)
    assert report["total_runs"] == 10
    assert "metrics" in report
    assert os.path.exists("reports/latest_report.json")
    assert os.path.exists("reports/latest_report.md")
