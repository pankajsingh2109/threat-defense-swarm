# Threat Defense Swarm — Automated Evaluation Report

**Total Benchmark Runs**: 10  
**Overall Success Rate**: 90.00%  
**Failure Rate**: 10.00%  

---

## Performance Latency Summary
- **Mean Latency**: 6496.26 ms
- **P50 Latency**: 5798.78 ms
- **P95 Latency**: 13187.27 ms
- **P99 Latency**: 15144.57 ms

---

## Resilience & Chaos Metrics
| Metric | Rate (%) |
| :--- | :--- |
| **Prompt Injection Defense Rate** | `100.00%` |
| **Tool 503 Recovery Rate** | `100.00%` |
| **Clarification Success Rate** | `100.00%` |
| **Unresolved / Insufficient Context Rate** | `20.00%` |

---

## Sample Run Detail Log (First 10 Runs)
| Run ID | Threat ID | Verdict | Expected | Latency (ms) | Success |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `run_0001` | `threat-33c15b94` | `allow` | `allow` | `5814.8` | `PASS` |
| `run_0002` | `threat-450a55e2` | `block_ip` | `block_ip` | `15633.9` | `PASS` |
| `run_0003` | `threat-5b45d503` | `insufficient_context` | `insufficient_context` | `1213.0` | `PASS` |
| `run_0004` | `threat-85437b99` | `block_ip` | `block_ip` | `9241.4` | `PASS` |
| `run_0005` | `threat-5818673f` | `insufficient_context` | `insufficient_context` | `3508.6` | `PASS` |
| `run_0006` | `threat-b28ea282` | `allow` | `insufficient_context` | `5782.8` | `FAIL` |
| `run_0007` | `threat-1351304a` | `block_ip` | `block_ip` | `7106.9` | `PASS` |
| `run_0008` | `threat-6b032852` | `allow` | `allow` | `3442.8` | `PASS` |
| `run_0009` | `threat-5f14644a` | `allow` | `allow` | `3021.6` | `PASS` |
| `run_0010` | `threat-d58d4237` | `block_ip` | `block_ip` | `10197.0` | `PASS` |
