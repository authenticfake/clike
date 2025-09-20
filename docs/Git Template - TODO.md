file .github/pull_request_template.md

# PR Title
_A short, action-oriented title (imperative)._

## Purpose / Scope
- Link to issue / ticket: <!-- e.g., #123 -->
- Summary in 1–2 sentences: what is changing and why.

## Phase (Harper)
Select the primary phase this PR targets:
- [ ] SPEC (G0)
- [ ] PLAN (G1)
- [ ] KIT (implementation)
- [ ] BUILD (tests/integration)

> Mixed changes are allowed, but each gate below must still pass.

## Linked Documents (permalinks)
- IDEA:  `[docs/harper/IDEA.md](./docs/harper/IDEA.md)` (if relevant)
- SPEC:  `[docs/harper/SPEC.md](./docs/harper/SPEC.md)`
- PLAN:  `[docs/harper/PLAN.md](./docs/harper/PLAN.md)`
- Other refs: …

## Change Summary
- Bullet points of key changes (files, modules, behaviors)

## Acceptance Criteria Mapping (from SPEC)
- AC-1 → covered by …
- AC-2 → covered by …
- KPIs / NFR notes (perf/sec/obs): …

## Test Evidence
- Unit tests: pass/fail, coverage %
- Integration/E2E: pass/fail (brief)
- Manual smoke (if any): steps & result
- Artifacts: attach or reference CI artifacts (reports, coverage, SARIF)

## Risks & Mitigations
- Risk: …
- Mitigation: …

## Checklist — Gates & Hygiene
- [ ] **G0 SPEC Gate** (if SPEC changed): goals/NFR/AC/risk present and consistent
- [ ] **G1 PLAN Gate** (if PLAN changed): tasks/owners/deps/milestones coherent
- [ ] **G2 Quality**: lint/type/security checks green
- [ ] **EDD Tests**: unit/integration thresholds met
- [ ] **Codeowners** approvals collected
- [ ] Docs updated (README / CHANGELOG / API)
- [ ] Backward compatibility considered (migration notes if needed)

---
_Reviewer notes:_  
- Verify alignment to IDEA/SPEC/PLAN.  
- Check security, privacy, licensing and telemetry boundaries as applicable.
- ---
Workflow unico con detect-phase → phase-gates → edd-gates → artifact-report.
È resiliente: gestisce assenza di tool/progetti (salta in modo pulito).
.github/workflows/ci-gates.yml
name: CI Gates (Harper)

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    branches: [ main, release/* ]
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: write
  security-events: write

concurrency:
  group: ci-gates-${{ github.ref }}-${{ github.event.pull_request.number || github.sha }}
  cancel-in-progress: true

jobs:
  detect-phase:
    name: Detect phase & tech stack
    runs-on: ubuntu-latest
    outputs:
      phase: ${{ steps.detect.outputs.phase }}
      changed_spec: ${{ steps.detect.outputs.changed_spec }}
      changed_plan: ${{ steps.detect.outputs.changed_plan }}
      changed_code: ${{ steps.detect.outputs.changed_code }}
      has_python: ${{ steps.detect.outputs.has_python }}
      has_node_ext: ${{ steps.detect.outputs.has_node_ext }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Compute changes & phase
        id: detect
        shell: bash
        run: |
          set -euo pipefail
          BASE="${{ github.event.pull_request.base.sha }}"
          HEAD="${{ github.event.pull_request.head.sha }}"
          # Ensure base exists locally
          git fetch origin "${{ github.event.pull_request.base.ref }}" --depth=1 || true
          CHANGED="$(git diff --name-only "$BASE...$HEAD" || true)"
          echo "Changed files:"
          echo "$CHANGED"

          changed_spec="false"
          changed_plan="false"
          changed_code="false"
          if echo "$CHANGED" | grep -qE '^docs/harper/SPEC\.md$'; then changed_spec="true"; fi
          if echo "$CHANGED" | grep -qE '^docs/harper/PLAN\.md$'; then changed_plan="true"; fi
          if echo "$CHANGED" | grep -qE '^(src/|orchestrator/|gateway/|extensions/|configs/|package\.json|pyproject\.toml|requirements\.txt)'; then changed_code="true"; fi

          # Phase selection priority: code → plan → spec → unknown
          phase="unknown"
          if [ "$changed_code" = "true" ]; then phase="kit"; fi
          if [ "$changed_plan" = "true" ] && [ "$phase" = "unknown" ]; then phase="plan"; fi
          if [ "$changed_spec" = "true" ] && [ "$phase" = "unknown" ]; then phase="spec"; fi

          # Tech stack detection
          has_python="false"
          if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -d "orchestrator" ] || [ -d "gateway" ]; then has_python="true"; fi
          has_node_ext="false"
          if [ -f "extensions/vscode/package.json" ]; then has_node_ext="true"; fi

          {
            echo "phase=$phase"
            echo "changed_spec=$changed_spec"
            echo "changed_plan=$changed_plan"
            echo "changed_code=$changed_code"
            echo "has_python=$has_python"
            echo "has_node_ext=$has_node_ext"
          } >> "$GITHUB_OUTPUT"

          echo "Phase: $phase"
          echo "has_python=$has_python, has_node_ext=$has_node_ext"

  phase-gates:
    name: Phase gates (SPEC/PLAN validation)
    needs: detect-phase
    runs-on: ubuntu-latest
    if: needs.detect-phase.outputs.phase != 'unknown'
    steps:
      - uses: actions/checkout@v4

      # -------- SPEC Gate (G0) --------
      - name: Validate SPEC.md structure (G0)
        if: needs.detect-phase.outputs.changed_spec == 'true'
        shell: bash
        run: |
          set -euo pipefail
          test -f docs/harper/SPEC.md
          # Minimal structure checks (extend as needed)
          grep -q '^# SPEC' docs/harper/SPEC.md
          grep -q '^## Goals' docs/harper/SPEC.md
          grep -q '^## Functional Requirements' docs/harper/SPEC.md
          grep -q '^## Non-Functional Requirements' docs/harper/SPEC.md
          grep -q '^## Acceptance Criteria' docs/harper/SPEC.md
          echo "SPEC.md basic structure OK."

      # -------- PLAN Gate (G1) --------
      - name: Validate PLAN.md structure (G1)
        if: needs.detect-phase.outputs.changed_plan == 'true'
        shell: bash
        run: |
          set -euo pipefail
          test -f docs/harper/PLAN.md
          grep -q -E '^# PLAN|^#\s*Plan' docs/harper/PLAN.md
          grep -q -E '^##\s*Milestones|^##\s*Work Breakdown' docs/harper/PLAN.md
          grep -q -E '^##\s*Acceptance|^##\s*Test Strategy' docs/harper/PLAN.md
          echo "PLAN.md basic structure OK."

  edd-gates:
    name: EDD gates (quality & security)
    needs: detect-phase
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # ---------- Python lane ----------
      - name: Setup Python
        if: needs.detect-phase.outputs.has_python == 'true'
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Python deps (best-effort)
        if: needs.detect-phase.outputs.has_python == 'true'
        shell: bash
        run: |
          set -e
          python -m pip install --upgrade pip
          pip install ruff mypy pytest || true
          if [ -f orchestrator/requirements.txt ]; then pip install -r orchestrator/requirements.txt || true; fi
          if [ -f gateway/requirements.txt ]; then pip install -r gateway/requirements.txt || true; fi
      - name: Ruff (lint)
        if: needs.detect-phase.outputs.has_python == 'true'
        run: ruff check .
      - name: MyPy (types)
        if: needs.detect-phase.outputs.has_python == 'true' && (hashFiles('mypy.ini') != '' || hashFiles('pyproject.toml') != '')
        run: mypy .
      - name: Pytests (if tests present)
        if: needs.detect-phase.outputs.has_python == 'true'
        shell: bash
        run: |
          if ls -1 **/tests/**/*.py **/tests/*.py 2>/dev/null | grep -q .; then
            pytest -q --maxfail=1 --disable-warnings
          else
            echo "No python tests found – skipping."
          fi

      # ---------- Node lane (VSCode extension) ----------
      - name: Setup Node
        if: needs.detect-phase.outputs.has_node_ext == 'true'
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install & Lint (extension)
        if: needs.detect-phase.outputs.has_node_ext == 'true'
        working-directory: extensions/vscode
        shell: bash
        run: |
          npm ci
          npm run lint --if-present
      - name: Tests (extension)
        if: needs.detect-phase.outputs.has_node_ext == 'true'
        working-directory: extensions/vscode
        run: npm test --if-present

      # ---------- Secrets & Security ----------
      - name: Gitleaks (secrets scan)
        uses: zricethezav/gitleaks-action@v2
        with:
          args: --no-git -v
      - name: Semgrep (default rules)
        uses: returntocorp/semgrep-action@v1
        with:
          publishToken: ${{ secrets.SEMGREP_APP_TOKEN }}
          generateSarif: true
          uploadSarif: false
        continue-on-error: true
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: semgrep.sarif
        if: always()

  artifact-report:
    name: Artifact & PR summary
    needs: [detect-phase, phase-gates, edd-gates]
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Summarize
        uses: actions/github-script@v7
        with:
          script: |
            const phase = "${{ needs.detect-phase.outputs.phase }}";
            const verdict = (arr) => arr.every(j => j.result === 'success') ? '✅ All green' :
                                      arr.some(j => j.result === 'failure') ? '❌ Failures' : '⚠️ Mixed';
            const jobs = [${{ toJson(needs) }}];
            const flat = Object.values(jobs[0] || {});
            const status = verdict(flat);
            const body = [
              `**CI Gates Summary**`,
              ``,
              `Phase detected: \`${phase}\``,
              `Overall: ${status}`,
              ``,
              `Artifacts:`,
              `- Semgrep SARIF (Code Scanning tab)`,
              `- Default Actions logs (build, tests, lint)`,
              ``,
              `_This comment is auto-generated by CI Gates (Harper)._`
            ].join('\n');
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body
            });

