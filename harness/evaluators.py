import json
import os
import math
from typing import List, Dict, Any

def calculate_percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return d0 + d1

def generate_evaluation_report(run_results: List[Dict[str, Any]], output_dir: str = "reports") -> Dict[str, Any]:
    """Calculates overall harness evaluation metrics and writes JSON and Markdown report files."""
    os.makedirs(output_dir, exist_ok=True)
    
    total_runs = len(run_results)
    successful_runs = sum(1 for r in run_results if r.get("success", False))
    failed_runs = total_runs - successful_runs
    success_rate = (successful_runs / total_runs) * 100.0 if total_runs > 0 else 0.0
    failure_rate = 100.0 - success_rate

    latencies = [r["latency_ms"] for r in run_results if "latency_ms" in r]
    mean_latency = sum(latencies) / len(latencies) if latencies else 0.0
    p50_latency = calculate_percentile(latencies, 50)
    p95_latency = calculate_percentile(latencies, 95)
    p99_latency = calculate_percentile(latencies, 99)

    # Chaos conditions tracking
    prompt_injection_runs = [r for r in run_results if "prompt_injection" in json.dumps(r.get("chaos_events", []))]
    prompt_defense_success = sum(1 for r in prompt_injection_runs if r.get("success", False))
    prompt_defense_rate = (prompt_defense_success / len(prompt_injection_runs) * 100.0) if prompt_injection_runs else 100.0

    tool_503_runs = [r for r in run_results if "tool_503" in json.dumps(r.get("chaos_events", []))]
    tool_503_success = sum(1 for r in tool_503_runs if r.get("success", False))
    tool_503_recovery_rate = (tool_503_success / len(tool_503_runs) * 100.0) if tool_503_runs else 100.0

    clarification_runs = [r for r in run_results if r.get("clarification_attempts", 0) > 0]
    clarification_success = sum(1 for r in clarification_runs if r.get("success", False))
    clarification_success_rate = (clarification_success / len(clarification_runs) * 100.0) if clarification_runs else 100.0

    unresolved_count = sum(1 for r in run_results if r.get("verdict") in ["insufficient_context", "unresolved"])
    unresolved_rate = (unresolved_count / total_runs * 100.0) if total_runs > 0 else 0.0

    report_summary = {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "metrics": {
            "success_rate_pct": round(success_rate, 2),
            "failure_rate_pct": round(failure_rate, 2),
            "mean_latency_ms": round(mean_latency, 2),
            "p50_latency_ms": round(p50_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "p99_latency_ms": round(p99_latency, 2),
            "prompt_injection_defense_rate_pct": round(prompt_defense_rate, 2),
            "tool_503_recovery_rate_pct": round(tool_503_recovery_rate, 2),
            "clarification_success_rate_pct": round(clarification_success_rate, 2),
            "unresolved_rate_pct": round(unresolved_rate, 2)
        },
        "runs": run_results
    }

    # Save JSON report
    json_path = os.path.join(output_dir, "latest_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_summary, f, indent=2)

    # Generate Markdown report
    md_content = f"""# Threat Defense Swarm — Automated Evaluation Report

**Total Benchmark Runs**: {total_runs}  
**Overall Success Rate**: {success_rate:.2f}%  
**Failure Rate**: {failure_rate:.2f}%  

---

## Performance Latency Summary
- **Mean Latency**: {mean_latency:.2f} ms
- **P50 Latency**: {p50_latency:.2f} ms
- **P95 Latency**: {p95_latency:.2f} ms
- **P99 Latency**: {p99_latency:.2f} ms

---

## Resilience & Chaos Metrics
| Metric | Rate (%) |
| :--- | :--- |
| **Prompt Injection Defense Rate** | `{prompt_defense_rate:.2f}%` |
| **Tool 503 Recovery Rate** | `{tool_503_recovery_rate:.2f}%` |
| **Clarification Success Rate** | `{clarification_success_rate:.2f}%` |
| **Unresolved / Insufficient Context Rate** | `{unresolved_rate:.2f}%` |

---

## Sample Run Detail Log (First 10 Runs)
| Run ID | Threat ID | Verdict | Expected | Latency (ms) | Success |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in run_results[:10]:
        md_content += f"| `{r.get('run_id')}` | `{r.get('threat_id')}` | `{r.get('verdict')}` | `{r.get('expected_verdict')}` | `{r.get('latency_ms', 0):.1f}` | `{'PASS' if r.get('success') else 'FAIL'}` |\n"

    md_path = os.path.join(output_dir, "latest_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return report_summary
