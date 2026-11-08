# Estimating with CLike — a worked enterprise example

How a senior software architect and a senior software engineer estimate an enterprise integration
the classic way, how the same work is planned with CLike, and where the difference comes from. The
CLike side rests on measured pilots; the classic side on the work breakdown and staffing such a
project needs. Use the method, not only the numbers: run the same comparison on your own scenario
(section 6) before quoting a factor.

## 1. The scenario

Five services exchange business events on an event broker (Kafka) and persist the data they own in
a relational database:

- each service consumes one or more topics, applies its rules, writes its own tables and publishes
  the resulting events;
- message schemas are versioned and shared; consumers are idempotent; failures go to a dead-letter
  topic with the reason;
- an end-to-end flow crosses the five services; the solution runs on a container platform with
  observability, secured broker access (TLS/SASL) and database migrations;
- quality bar: unit, contract and integration tests per service, an end-to-end test of the flow,
  every error path tested (timeouts, malformed messages, duplicates, restarts, conflicts).

## 2. Classic estimate

### 2.1 Work breakdown (senior engineer, development only)

| Work package | Person-days |
|---|---|
| Foundations: topics and partitions, message schemas, broker and database configuration, migrations, local environment | 3–4 |
| Five services (consumer/producer, business rules, persistence, unit and contract tests): 2.5–3.5 each | 13–17 |
| Error paths: idempotency, retries with backoff, dead-letter topic, malformed messages, consumer restart, ordering per key | 3–5 |
| End-to-end integration with a real broker, observability, security, deployment | 3–5 |
| **Development total** | **22–30** |

A team that quotes "20 days" for this is quoting the optimistic end of development alone.

### 2.2 Staffing for the whole scenario (architect view)

Analysis, testing and operations are part of the scenario, not overhead on top of it.

| Role | People | Effort (person-days) |
|---|---|---|
| Architect / tech lead — topic contracts, schemas, delivery semantics, reviews | 1 | 8–10 |
| Backend developers — the five services, persistence, tests | 2–3 | 22–30 |
| QA / test automation — test plan, integration and end-to-end tests, error paths | 1 | 8–12 |
| DevOps / platform (part-time) — broker, database, CI/CD, environments, observability | 1 | 6–8 |
| Business analyst / project manager (part-time) — requirements, coordination, release | 1 | 4–6 |
| DBA and security (on call) — data model, TLS/SASL, reviews | on call | 2–4 |
| **Total** | **6–8 people** | **50–70 person-days, 5–7 calendar weeks** |

## 3. Planning the same scenario with CLike

### 3.1 Units of work (capacity profiles)

With a coding agent as KIT executor the plan uses the C2 profile (vertical slices) and one C3 epic:

| Unit | Profile | Content |
|---|---|---|
| Foundation | C2 | topics, schemas, migrations, shared seams (service registration by convention, one migration per unit), local environment |
| Service 1 … Service 5 | C2 × 5 | one vertical slice per service: consumer, rules, persistence, producer, tests |
| End-to-end flow | C3 | the cross-service flow as an epic with features (happy flow, failure flows, replay), proved end to end |

Seven units instead of the 15–25 small requirements a layer-by-layer split would produce.

### 3.2 Completeness comes with the plan

The journey catalog puts the scenarios that usually surface late into the SPEC, each included or
excluded with a reason, owned by a unit and blocking at eval until a test that names it passes:

- async jobs: accepted and queued, retry with backoff, timeout, idempotent resubmit, resume after a
  restart, failed message surfaced to the operator;
- integration: broker or dependency down, timeout, rate limit, malformed or unexpected payload,
  expired credentials, retries without duplicate side effects;
- data lifecycle: validation, duplicates, concurrent update conflicts, not found;
- API contract (where services expose one): readable 4xx bodies, 401/403/404/409, versioning.

### 3.3 Measured basis (pilots on a real product)

| Pilot | Scope | Effective time | Result |
|---|---|---|---|
| Vertical slice (C2) | API + console + persistence, 15 acceptance criteria and 17 journey scenarios, ~4k lines of source and ~2k of tests | ~1 h 15 min (agent ~54 min, eval ~22 min) | gate passed, every scenario proved by a test that names it, regression of the promoted requirements green |
| Epic (C3) | the equivalent of 4 requirements of the original plan (two APIs and two consoles), 26 journey scenarios, ~5.7k lines of source | ~1.5 h | gate passed, 26/26 scenarios traced; the original project needed 10 evals and 12 gates over more than a day of calendar for the same scope |

### 3.4 Projection

Two availability models: people work 5 days × 8 hours (40 hours a week), the coding agent works
around the clock, 7 days a week (168 hours), driven by `/autopilot`. Agent hours therefore run at
night and over the weekend; the critical path is made of the human gates — SPEC and plan approval,
pull request reviews, decisions — not of the generation.

| Item | Effort | When |
|---|---|---|
| Agent work and evals: 7 units × 1.5–2.5 h | 12–18 machine hours | overnight, outside working hours |
| Human work: SPEC and plan (topic contracts, data ownership, delivery semantics), reviews, decisions | 1.5–2 person-days | working hours |
| Environment and integration with the real broker | ~1 person-day | working hours |

A realistic timeline:

| Day | People (working hours) | Agent (around the clock) |
|---|---|---|
| Day 1 | SPEC with the journey scenarios, plan with the seven units, approval | night: foundation and the five service slices |
| Day 2 | review of the six units, real broker and database wired in the eval environment | night: the end-to-end epic, repairs from the review |
| Day 3 | review of the epic, integration on the target environment, sign-off | — |
| **Calendar** | **~3 working days, one product engineer leading** | |

Staffing with CLike:

| Role | People | Effort (person-days) |
|---|---|---|
| Product engineer / tech lead driving CLike — SPEC, plan, decisions, reviews | 1 | 4–5 |
| DevOps / platform (part-time) — real broker and database, deployment | 1 | ~2 |
| Architect or security reviewer | on call | ~1 |
| **Total** | **2–3 people** | **6–8 person-days, ~3 working days of calendar** |

QA and test automation are largely absorbed: CLike writes the tests, proves every journey scenario
and blocks a unit until they pass; the review stays human.

## 4. The factor

| | Classic | With CLike | Factor |
|---|---|---|---|
| Total effort (people) | 50–70 person-days | 6–8 person-days | **~7–9×** |
| People involved | 6–8 | 2–3 | ~3× |
| Calendar (working days of 8 hours) | 25–35 (5–7 weeks) | ~3 | **~8–12×** |
| Building and verifying well-specified requirements | 3–5 person-days per slice | ~½ day of review per slice (generation runs unattended) | up to ~10× |

The agent's 12–18 machine hours are not person effort: they run while people are off. The
calendar gain comes from that and from the smaller number of human gates; the effort gain from the
work CLike absorbs (coding, tests, error scenarios, repair).

How to state it without overselling: *on building and verifying well-specified requirements CLike
turns up to ten person-days into one, with every error scenario proved by a test; across the whole
scenario — analysis, decisions, integration and operations included — the factor is about seven to
nine on effort and eight to twelve on calendar, because the agent works around the clock while
people keep their working hours.*

## 5. What can stretch the estimate

- **The broker in the eval sandbox.** The sandbox runs no containers: the real broker is provided
  from outside (`provision: external` in `docker/eval.env`) or the tests use an in-process broker or
  a fake. Decide it in the SPEC; leaving it open costs days of repairs.
- **Non-functional requirements** — throughput, exactly-once, ordering per key — need architecture
  decisions written in the SPEC; the model implements what is decided, it does not decide it.
- **Shared composition files.** A unit that rewrites a promoted entrypoint or manifest breaks every
  earlier unit; the shared seams of the plan and the eval guard on promoted files prevent it.
- **Executor variance.** Agents differ in how many repair cycles they need; measure on your stack and
  use the one that converges best.

## 6. Validate it on your scenario

1. Before starting, the team writes the classic estimate (work breakdown and staffing, sections
   2.1–2.2) and keeps it unchanged.
2. Run the scenario with CLike; the telemetry portal (`/harper/aggregate`, `per_req`) records time,
   tokens and cost per unit; record the human hours separately.
3. Compare effort, people and calendar as in section 4, and keep the comparison with the project.
