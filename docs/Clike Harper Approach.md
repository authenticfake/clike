## CLike Harper Approach
###Sintesi operativa (IT)

* **`runs/` a cosa serve**
  È l’area **ephemeral ma versionata** per *telemetria di fase* e *stato iterativo* per ogni `runId`. Qui non mettiamo il codice “prod”, ma **report, indici REQ-ID, esiti test, gate decisions**. Serve a:

  * rendere **replicabile** ogni ciclo (`kit.report.json`, `eval.summary.json`, `gate.decisions.json`);
  * mantenere storico dei batch e sapere “cosa è stato fatto / cosa resta” senza dover parsare i diff git;
  * permettere a `/eval` e `/gate` di ragionare su **REQ-ID** e non su “file sparsi”.

* **`KIT.md` e `README` per ogni iterazione**

  * Ogni `/kit` produce:

    * `docs/harper/KIT.md` **append-only** (log delle iterazioni, mapping REQ-ID → artefatti/test);
    * un **`README` specifico** nella root o nel modulo toccato (scelta sensata in base al repo), che contenga:

      * prerequisiti (tooling locale/CI, env vars, on-prem proxy, ecc.);
      * come **eseguire i test** (comandi chiari);
      * cosa **è in scope** in questa iterazione, cosa **out of scope**;
      * dipendenze e come mockarle;
      * cosa aspettarsi dagli **esiti di /eval**.
  * In `KIT.md` aggiungiamo una sezione **“Product Owner Notes”** (o “User Notes”) dove l’utente può scrivere feedback/scope change. Al prossimo `/plan` (o `/kit --rescope`) aggiorniamo il `plan.json` / `PLAN.md` di conseguenza.

* **`/eval` cosa fa (in concreto)**
  Esegue la **suite tecnica** coerente con lo stack (esempi):

  * test automatici (pytest/jest…);
  * lint (ruff/eslint);
  * type-check (mypy/pyright/tsc);
  * format check (black/prettier in check-mode);
  * *(opz)* sicurezza e supply-chain (bandit/trivy/snyk) secondo profilo **startup vs enterprise**, **cloud vs on-prem**;
  * build/check packaging (ad es. `mvn -q -DskipTests` o `docker build --target test`).
    Output: `runs/<runId>/eval.summary.json` indicizzato per **REQ-ID** + summary aggregati.
    **Scoping**: per default valuta i REQ toccati dall’ultimo `/kit`. Con `--all` valuta tutto.

* **Relazione `/kit` → `/eval` → `/gate` (REQ-ID-centrica)**

  * `/kit` lavora su **uno o più REQ-ID** (default: prossimo “open”, rispettando dipendenze).
  * `/eval` valida i REQ toccati (o `--all`).
  * `/gate` decide promozione: se **tutti verdi** nel batch corrente → segna “done” quei REQ in `plan.json`/`PLAN.md`.
    → **Sblocca** automaticamente il **prossimo REQ-ID** per il ciclo `/kit` successivo (smart advance).
  * Se falliscono, resta sul branch di lavoro e non promuove.

* **Git (stesse regole di /plan, con attenzione a e2e)**

  * Branch: `harper/<phase>/<runId>`.
  * Commit messaggi standard (includere `runId`, `model`, `profile`).
  * **/kit**: commit solo degli **artefatti del/i REQ target** + `runs/*` e doc.
    PR opzionale (config), gate blocca merge se `/eval` non è verde.