---
name: journey-ml-reproducibility
description: Use when a REQ trains, evaluates or serves a machine-learning model or a data pipeline with quality metrics, to prove runs are reproducible, metrics gate the change, data is validated and pinned, and inference rejects bad input.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "data", "ai-native", "backend"]
domains: ["ai-native", "enterprise", "industrial", "startup"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid"]
gate_required: true
scenario_prefix: MLR
scenarios:
  - MLR-01 | required | Reproducible run | When training or evaluation runs twice with the same seed, configuration and dataset version, the system shall produce the same metrics within the stated tolerance.
  - MLR-02 | required | Metric threshold gates the change | If a model's metric on the evaluation set is below its threshold or worse than the baseline by more than the allowed margin, then the evaluation check shall fail.
  - MLR-03 | required | Dataset pinned and validated | If the dataset does not match its recorded version (hash) or violates its schema (missing columns, types, ranges, label set), then the system shall refuse to train or evaluate and name the problem.
  - MLR-04 | required | Inference input validated | If an inference request has missing features, wrong types or out-of-range values, then the system shall reject it with a readable error instead of predicting.
  - MLR-05 | conditional | [Training and serving share feature code] Training and serving parity | When the same raw input goes through the training and the serving feature path, the system shall produce identical features.
  - MLR-06 | conditional | [Model in production] Drift signalled | If the distribution of live inputs moves beyond the stated threshold from the training data, then the system shall raise a drift signal.
obligations:
  - Record seed, configuration, dataset hash, code version and metrics in a run manifest (for example docs/REPRO.json)
  - Keep blocking checks on a small deterministic fixture dataset; full-scale evaluation is a non-blocking case
  - Prove each included scenario with a blocking check recorded in docs/ACCEPTANCE.json
eval_checks:
  - scenario-coverage
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-quality-claimed-without-metric
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - The run manifest and the thresholds
---

# Journey: ML Reproducibility

## Intent

A model is only as trustworthy as the run that produced it. A metric printed in a notebook proves
nothing if the run cannot be repeated, the data changed underneath, or the serving code computes
features differently. Each risk is a tested scenario on a small fixture that runs in the sandbox.

## Use when

Training, fine-tuning, feature engineering, offline evaluation, batch or online inference, data
quality pipelines with metrics.

## Do not use when

Prompt-based features without training or metrics of their own (use journey-ai-guardrails).

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; state metrics, thresholds, baseline and tolerance
  before implementation.
- **PLAN**: the REQ that creates the training/evaluation path owns MLR-01..03; the serving REQ owns
  MLR-04/05.
- **KIT**: blocking checks run on the fixture dataset, CPU only, seeded; GPU or full-data runs are
  `blocking: false` with `environment_requirements`.

## Valid exclusions

- Batch scoring only, no online serving: MLR-05/06 may be excluded with that reason.
- Not valid: "the metric was checked manually".

## Proof per scenario

- MLR-01: run the pipeline twice on the fixture with the same seed; assert metrics equal within tolerance.
- MLR-02: a model stub or a degraded fixture below the threshold makes the evaluation check fail.
- MLR-03: alter one row or drop a column of the fixture; assert the refusal names the problem.
- MLR-04: inference with a missing feature and an out-of-range value; assert the error body.

## Forbidden

- Absolute local data paths, private or production data in fixtures.
- Improvement claims without baseline and metric; thresholds only in prose.
- Blocking checks that need a GPU, the full dataset or the network.
- Notebook-only logic: extract it into a module and test it.

## References

- references/test-idioms.md
