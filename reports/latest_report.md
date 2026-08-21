# Threat Defense Swarm — Automated Evaluation Report

**Total Benchmark Runs**: 10  
**Overall Success Rate**: 80.00%  
**Failure Rate**: 20.00%  

---

## Performance Latency Summary
- **Mean Latency**: 14488.48 ms
- **P50 Latency**: 11684.51 ms
- **P95 Latency**: 39419.15 ms
- **P99 Latency**: 44611.64 ms

---

## Resilience & Chaos Metrics
| Metric | Rate (%) |
| :--- | :--- |
| **Prompt Injection Defense Rate** | `100.00%` |
| **Tool 503 Recovery Rate** | `100.00%` |
| **Clarification Success Rate** | `100.00%` |
| **Unresolved / Insufficient Context Rate** | `30.00%` |

---

## Sample Run Detail Log (First 10 Runs)
| Run ID | Threat ID | Verdict | Expected | Latency (ms) | Success |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `run_0001` | `threat-6c7f1ed5` | `block_ip` | `block_ip` | `9733.1` | `PASS` |
| `run_0002` | `threat-70893b95` | `insufficient_context` | `allow` | `45909.8` | `FAIL` |
| `run_0003` | `threat-fa827399` | `insufficient_context` | `insufficient_context` | `2187.0` | `PASS` |
| `run_0004` | `threat-724c1eac` | `allow` | `insufficient_context` | `2583.7` | `FAIL` |
| `run_0005` | `threat-c9775fe5` | `quarantine` | `quarantine` | `17702.4` | `PASS` |
| `run_0006` | `threat-b513b9df` | `allow` | `allow` | `3036.1` | `PASS` |
| `run_0007` | `threat-ecd06ad9` | `insufficient_context` | `insufficient_context` | `4142.1` | `PASS` |
| `run_0008` | `threat-4228ce4c` | `block_ip` | `quarantine` | `31486.2` | `PASS` |
| `run_0009` | `threat-629b32b1` | `allow` | `allow` | `14468.5` | `PASS` |
| `run_0010` | `threat-396c26a3` | `block_ip` | `block_ip` | `13636.0` | `PASS` |
