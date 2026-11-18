# Stage Report: stage_0_foundation (stage_0_foundation_f5b9635)

## 1. Summary
This report documents verified performance for **stage_0_foundation** in the Audio Token Pipeline (`atp`). All values are dynamically queried from `catalog.duckdb`, `reports/coverage.json`, and git metadata.
- **Overall Stage Status:** **PASS**
- **Sources Registered:** 18 files (354.070 s / 0.0984 h)
- **Total Project Test Coverage:** 85.41%

## 2. Environment
- **Machine:** arm64
- **CPU Topology:** Apple M4 (10 cores: 4P + 6E)
- **Platform:** macOS-15.4.1-arm64-arm-64bit
- **RAM:** 16.0 GB
- **Python Version:** 3.11.16
- **Device Used:** cpu
- **Git Commit:** `f5b96352f7ee79679efa8cc2363238ad230eb04b`
- **Config Hash:** `29265ee9e189fa8c`
- **Run ID:** `stage_0_foundation_f5b9635`
- **Start Time (UTC):** `2026-11-18T20:41:09Z`
- **End Time (UTC):** `2026-11-18T20:41:09Z`
- **CI Workflow:** [ci.yml](.github/workflows/ci.yml)
- **CI Actions Run URL:** [https://github.com/Shyam-SN/audio-token-pipeline/actions/runs/44389941085](https://github.com/Shyam-SN/audio-token-pipeline/actions/runs/44389941085)

## 3. Inputs
- **Dataset / Split:** `smoke_test` / `fixtures`
- **Total Evaluated Files:** 19
- **Total Decoded Hours:** 0.0984 h

## 4. Outputs

## 5. Metrics Table
| Metric | Value | Unit | Measurement Method | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Sources Registered | 18 | files | DuckDB sources count | >= 1 | **PASS** |
| Total Test Coverage | 85.41 | % | pytest-cov JSON report | >= 85.0 | **PASS** |

## 6. Performance & Multi-Core Scaling

## 7. Quality Evidence

## 8. Exact Commands to Reproduce
```bash
uv run atp segment --workers 6
uv run atp report stage_0_foundation
```
