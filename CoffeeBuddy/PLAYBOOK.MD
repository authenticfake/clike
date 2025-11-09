# Harper PLAYBOOK — CoffeeBuddy (On-Prem)

## Phases
1) **SPEC** from IDEA (iterate until approved)  
2) **PLAN** from SPEC (traceability 100%, test hooks ready)  
3) **KIT** implement REQs in short cycles (code + tests + docs)  
4) **Finalize** package + SBOM + license checks

## Commands (chat)
/init CoffeeBuddy [path] — scaffold project  
/spec — generate SPEC from IDEA & context (writes to `SPEC.generated.md`, then promote to `SPEC.md`)  
/plan — generate PLAN from SPEC  
/kit — scaffold + incremental build cycles  
/build — apply micro-diffs and re-run tests

### Evals & Gates
/eval spec | plan | kit | finalize — run eval profile  
/gate spec | plan | kit | finalize — enforce gates  

## On-Prem Expectations
- SPEC contains **Technology Constraints** for on-prem: Kubernetes + NGINX ingress, WSO2 APIM, Keycloak (OIDC), Kafka, PostgreSQL, Vault, Prometheus/Grafana.
- PLAN declares **Coverage: 100%** and test hooks (Unit/Functional/Integration/Security/UAT) and **Environment Profiles** (onprem).
- KIT runs lint/type/tests/security aligned to the chosen stack (e.g., Java 17 build, contract tests against Slack proxy).
- PRs require green checks (SPEC/PLAN/KIT Gates) prior to merging.

## Quick checklist before `/kit`
- SPEC approved and promoted to `SPEC.md`;
- PLAN approved with traceability and test hooks.  
- On-prem dev env configured: kube context, Keycloak realm, WSO2 route, Vault policy, Kafka/Postgres connectivity.
