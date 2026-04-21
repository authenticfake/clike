# Skill: ML Experiment Reproducibility

## Intent

Ensure ML, data science, model evaluation, and experiment requirements are reproducible, measurable, and traceable.

This skill separates product code from experiments and prevents unverifiable model-quality claims.

## Use when

Use this skill when a REQ touches ML models, datasets, training, fine-tuning, feature engineering, evaluation metrics, model comparison, notebooks, pipelines, data quality, experiment tracking, or batch inference.

## Do not use when

Do not use this skill for generic LLM prompt/RAG work unless the REQ includes ML datasets, model metrics, training, offline evaluation, or experiment comparison.

## Signals

- The REQ mentions ML, model training, fine-tuning, dataset, feature, label, metric, accuracy, precision, recall, F1, ROC, drift, experiment, notebook, inference, pipeline, validation split, baseline, or model registry.
- Acceptance criteria include measurable model quality.
- Generated files include notebooks, data loaders, evaluation scripts, model wrappers, or dataset fixtures.

## Required behavior

- Define datasets, fixtures, or sample data boundaries explicitly.
- Define metrics and thresholds before implementation.
- Keep training/experiment code separate from production inference code when practical.
- Make evaluation commands reproducible.
- Record assumptions about data availability, privacy, sampling, and labels.
- Include deterministic smoke tests for data loading and metric computation.
- Avoid requiring large datasets or GPUs for local blocking checks unless explicitly required.

## Forbidden behavior

- Do not claim model improvement without baseline and metric evidence.
- Do not hardcode local absolute dataset paths.
- Do not put private or production data into generated fixtures.
- Do not make local tests depend on GPU availability unless the REQ explicitly requires it.
- Do not mix notebook-only exploration with production code without extraction into testable modules.
- Do not hide data quality gaps behind successful code execution.

## Evidence required

- Evaluation command or script with documented inputs.
- Metric definitions and thresholds.
- Small deterministic fixture or synthetic dataset when real data is unavailable.
- Tests for metric computation, data validation, or inference wrapper behavior.
- HOWTO explaining local smoke evaluation and optional full evaluation.
- Notes describing baseline, limitations, and data assumptions.

## Repair guidance

- If metrics are missing, add a minimal evaluation script and documented thresholds.
- If data paths are hardcoded, move them to configuration.
- If only a notebook exists, extract reusable logic into a module and test it.
- If full data is unavailable, create a small representative fixture and mark full evaluation as external/non-blocking.
- If model quality is unknown, downgrade claims and document the required next evaluation.

## Gate implications

Gate should block promotion when:
- Model quality is part of acceptance criteria but no metric evidence exists.
- Evaluation cannot be reproduced.
- Tests require unavailable private data or hardware.
- Generated code uses hardcoded local data paths.
- Production inference behavior is untested.

Gate may allow non-blocking warnings when:
- Full-scale evaluation requires external infrastructure but local smoke evaluation passes.
- Drift monitoring is documented as future work outside the current REQ scope.

## Examples

- A classifier REQ includes fixture data, metric computation tests, baseline threshold, and HOWTO eval commands.
- A batch inference REQ separates loader, predictor, and writer with deterministic unit tests.
- A data quality REQ defines validation rules and failure examples.

## Non-examples

- A notebook that prints a high accuracy score without data or command reproducibility.
- A model wrapper that requires a production dataset to import.
- A fine-tuning REQ with no baseline, no metrics, and no eval script.
