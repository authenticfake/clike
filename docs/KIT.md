# KIT

## Deliverables
- `src/` – production code
- `tests/` – unit tests (pytest)
- `README.md` – quickstart
- `requirements.txt` – tooling & deps

## How to Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
```

## How to Test & Validate
```bash
ruff check .
ruff format .
mypy src
pytest -q
pytest --cov=src --cov-report=term-missing
```

## Rollout Checklist
- [ ] README includes usage & troubleshooting
- [ ] Lint/type/test PASS locally
- [ ] Example data (if needed)
- [ ] CI workflow configured
- [ ] License/NOTICE updated
