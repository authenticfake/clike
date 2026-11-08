# Test idioms: ML reproducibility

Small seeded fixtures, CPU only, metrics computed and asserted by code.

## Python

- Seed everything in one helper (`random`, `numpy`, the framework's seed and deterministic flags); MLR-01 runs `train(cfg, seed=7)` twice and `pytest.approx(rel=tol)` on the metrics.
- Dataset checks: schema validation (pandera, a pydantic row model, or explicit dtype/range checks) and a sha256 of the fixture compared with the manifest.
- Metrics with scikit-learn on fixture predictions; the threshold lives in the test or the config the test reads.
- Serving: FastAPI `TestClient` on the inference endpoint with invalid payloads; parity test feeding the same raw rows through the training transform and the serving transform.
- Drift: compute a population-stability or KS statistic on a shifted fixture and assert the signal.
