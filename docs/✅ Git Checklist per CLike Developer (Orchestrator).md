##CLike GIT life cycle

# ✅ Git Checklist per CLike Developer (Orchestrator)

### 1. Dopo `/init`

* `git init` (se non già repo)
* `git add .`
* `git commit -m "init: scaffold Harper workspace"`
* `git push origin feat/<project>-bootstrap`

### 2. Ogni volta che generi SPEC

* Esegui `/spec` in chat/palette.
* Subito dopo:

  * `git diff docs/harper/SPEC.md` → rivedi cosa è cambiato.
  * `git add docs/harper/SPEC.md`
  * `git commit -m "spec: update after iteration <N>"`
* Se lo SPEC non è ancora maturo, tieni il branch aperto (`feat/<project>-spec`) e non aprire PR.

### 3. Validazione SPEC

* Quando `/eval spec` → **PASS**, apri PR verso `main`.
* PR template deve includere:

  * Gate status (PASS)
  * Checklist delle sezioni SPEC
* Merge solo se CI è verde.

### 4. Ogni volta che generi PLAN

* Esegui `/plan`.
* `git diff docs/harper/PLAN.md` → controlla traceability (Coverage: 100%).
* `git commit -m "plan: initial PLAN generated"`
* Itera con `/eval plan` finché PASS.
* PR: merge solo se Plan Gate è verde.

### 5. Durante KIT

* Ogni micro-step produce codice + test.
* Dopo `/kit` o `/build`:

  * `git add .`
  * `git commit -m "kit: implement REQ-xxx"`
* Dopo `/eval kit` PASS:

  * `/planUpdate REQ-xxx runs/<ts>/eval/kit.report.json`
  * `git add docs/harper/PLAN.md`
  * `git commit -m "plan: update progress REQ-xxx"`

### 6. Finalize

* `/finalize` → run ultimi eval.
* `git add .`
* `git commit -m "finalize: package release vX.Y.Z"`
* `git tag vX.Y.Z`
* `git push origin main --tags`

### 7. Best practices

* Usa sempre **branch dedicati** per ogni fase (`feat/<project>-spec`, `feat/<project>-plan`, `feat/<project>-kit`).
* Ogni PR deve avere i **Required Checks** (eval/gates verdi).
* Non forzare merge: governance Git è il guardrail.
* Fai commit granulari e messaggi chiari: SPEC updates, PLAN updates, KIT implementations.

---

# 📌 Sintesi della chat

1. **Abbiamo definito il ciclo Harper in CLike**: IDEA → SPEC → PLAN → KIT → Finalize, con eval/gates a ogni step.
2. **Abbiamo discusso i documenti seed** (`IDEA.md`, `SPEC.md`, `PLAYBOOK.md`) e preparato template `/init` con placeholder `${project.name}`.
3. **Abbiamo generato un esempio completo**: progetto **CoffeeBuddy** in due varianti:

   * **Cloud (AWS/serverless)**
   * **On-Prem (Kubernetes, Keycloak, WSO2, Kafka, Vault, Jenkins)**
     Entrambe con SPEC/IDEA/PLAYBOOK completi, validi per i Gates.
4. **Abbiamo risolto dubbi su SPEC.generated.md vs SPEC.md**:

   * Deciso di rimanere con `SPEC.md` diretto (sovrascrive ma tutto versionato in Git).
   * Governance via Git + Gates impedisce problemi reali.
5. **Abbiamo parlato dell’Orchestrator**: nuovo nome per l’utente “super-user” di CLike. È lui che valida SPEC/PLAN e orchestra l’AI.
6. **Abbiamo definito la checklist Git completa** per l’orchestrator: commit, branch, PR, merge only with Gates PASS.
7. **Prossimo step**: iniziare i **test su CoffeeBuddy (On-Prem)** partendo da `IDEA.md`:

   * `/spec` → genera SPEC.md, iterazioni fino a PASS.
   * `/eval spec` → validazione.
   * Poi passare a PLAN.


