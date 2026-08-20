# Threat Defense Swarm — Automated Evaluation Report

**Total Benchmark Runs**: 10  
**Overall Success Rate**: 90.00%  
**Failure Rate**: 10.00%  

---

## Performance Latency Summary
- **Mean Latency**: 10292.01 ms
- **P50 Latency**: 10852.51 ms
- **P95 Latency**: 18406.90 ms
- **P99 Latency**: 19842.24 ms

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
| `run_0001` | `threat-d694c729` | `allow` | `allow` | `10807.3` | `PASS` |
| `run_0002` | `threat-f6c12dc6` | `block_ip` | `block_ip` | `20201.1` | `PASS` |
| `run_0003` | `threat-e95755b6` | `insufficient_context` | `insufficient_context` | `10897.7` | `PASS` |
| `run_0004` | `threat-ab463104` | `block_ip` | `block_ip` | `16214.0` | `PASS` |
| `run_0005` | `threat-67bc8674` | `insufficient_context` | `insufficient_context` | `1427.3` | `PASS` |
| `run_0006` | `threat-dcb6fe45` | `allow` | `insufficient_context` | `7285.5` | `FAIL` |
| `run_0007` | `threat-bd1ae547` | `block_ip` | `block_ip` | `13912.0` | `PASS` |
| `run_0008` | `threat-ea52b9e6` | `allow` | `allow` | `4174.9` | `PASS` |
| `run_0009` | `threat-c27fb508` | `allow` | `allow` | `4152.4` | `PASS` |
| `run_0010` | `threat-92765397` | `block_ip` | `block_ip` | `13848.0` | `PASS` |
