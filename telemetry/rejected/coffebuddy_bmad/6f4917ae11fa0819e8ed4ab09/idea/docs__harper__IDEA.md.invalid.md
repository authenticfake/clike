````file:docs/harper/IDEA.md
# IDEA — CoffeeBuddy

## Vision

CoffeeBuddy streamlines office coffee runs inside the corporate network by letting teammates start runs, submit orders, remember preferences, assign a fair runner, and receive reminders through Slack. The immediate value is replacing ad-hoc Slack threads with a structured, reliable workflow that can be demonstrated end-to-end on approved on-prem infrastructure. The first slice should prove a Slack-initiated coffee run with order collection, runner assignment, reminders, and a final summary.

## Problem Statement

Office teammates coordinate coffee orders in informal Slack threads, where messages get buried, orders are inconsistent, reminders are manual, and runner selection can feel unfair. This causes missed orders, pickup mistakes, repeated preference typing, and avoidable coordination time during recurring coffee runs. In regulated enterprise contexts, common public-cloud workflow tools may be restricted, so the solved slice-1 condition is a fully on-prem Slack workflow that completes one coffee run reliably with structured orders and a clear runner summary.

## Target Users & Context

- Primary users: office teammates placing coffee orders and participating in coffee runs.
- Secondary users: the assigned coffee runner who needs a clean, consolidated pickup summary.
- Secondary stakeholders: office managers or team leads seeking fairness, reduced coordination overhead, and fewer repeated team interruptions.
- Platform stakeholders: enterprise IT/compliance teams responsible for internal gateways, identity, secrets, observability, and on-prem operations.
- Operating context: enterprise Slack workspace, on-prem Kubernetes, internal identity, internal gateways, and corporate-network-only processing.

## Value & Outcomes

- Reduce coordination time to under 2 minutes per coffee run.
- Provide consistent order summaries to reduce pickup mistakes.
- Make runner assignment transparent and fair across the team.
- Remember user preferences so repeat orders require less typing.
- Keep application processing and data inside approved enterprise infrastructure.

## Out of Scope

- Payments.
- Delivery logistics.
- External coffee vendor integrations.
- Public cloud deployment.
- Mobile app.
- Complex admin UI beyond what is needed for initial configuration and operations.
- Vendor menu catalog management.

## Technology Constraints

```yaml
tech_constraints:
  version: 1
  metadata:
    name: "CoffeeBuddy"
    domain: "enterprise office workflow"
  classification:
    solution_type: "slack-integrated workflow service"
    deployment_context: "on-prem kubernetes"
    data_sensitivity: "employee order preferences and workflow history"
  runtime:
    language: "python"
    platform: "kubernetes"
    public_cloud_allowed: false
  integrations:
    slack:
      required: true
      interfaces:
        - "slack.events"
        - "slack.commands"
        - "slack.interactions"
      ingress: "internal gateway/proxy"
  infrastructure:
    ingress:
      - "nginx"
      - "Kong Gateway"
    storage:
      relational: "postgres"
    messaging:
      stream: "apache.kafka"
    auth:
      protocol: "oidc"
      providers:
        - "Ory Hydra"
        - "Ory Kratos"
    secrets:
      manager: "hashicorp.vault"
    observability:
      metrics: "prometheus"
      dashboards: "grafana"
    ci:
      system: "jenkins"
  security:
    network_scope: "internal-only routes"
    secrets_required:
      - "Slack signing secret"
      - "Slack bot token"
    request_validation:
      - "Slack request signature verification"
  evaluation:
    required_checks:
      - "Slack command/event acknowledgement path"
      - "coffee run workflow happy path"
      - "runner assignment fairness evidence"
      - "reminder and final summary evidence"
      - "Slack rate-limit retry/backoff behavior"
      - "Prometheus metrics exposure"
```

## Risks & Assumptions

- Business assumption: Slack Enterprise usage is approved internally for this workflow.
- Business risk: users may reject automatic runner assignment unless opt-outs and fairness explanations are clear.
- Technical assumption: Slack events can be securely proxied to on-prem services through internal gateway routes.
- Technical risk: Slack rate limits or delivery failures may delay notifications; buffering, idempotency, and retry/backoff are needed.
- Delivery risk: validating the Slack-to-on-prem ingress path may be the first blocking dependency.
- UX assumption: teammates will use structured Slack modals or interactive messages instead of free-form thread replies if the flow is fast.
- Data assumption: coffee preferences and runner history can be stored internally with appropriate minimization and retention controls.
- Compliance assumption: employee coffee preferences and Slack identifiers are acceptable to store on approved on-prem infrastructure.
- Dependency risk: enterprise identity, secrets, gateway, Kafka, Postgres, and observability services must be available or stubbed for the first demonstrable slice.

## Success Metrics

- Weekly active coffee runs per active user.
- Time from first `/coffee` action to order confirmation, target under 2 minutes.
- Percentage of coffee runs that produce a complete final runner summary.
- Critical workflow error rate for Slack command handling, order submission, reminders, and summary generation.
- Runner assignment distribution across eligible participants.
- Missed or late order rate after reminders.
- Slack API failure and rate-limit event rate.
- Pilot satisfaction from participating teammates and runner stakeholders.
- Acceptance criteria: a slice-1 pilot can start a run in Slack, collect at least one structured order, assign or confirm a runner, send a reminder, post a final summary, persist the run, and expose basic operational metrics.
````

````file:docs/harper/bmad/idea/BRIEF.md
# BMAD Idea Brief — CoffeeBuddy

## One-line concept

CoffeeBuddy is an on-prem Slack workflow service that coordinates office coffee runs, remembers simple preferences, assigns a fair runner, sends reminders, and posts a reliable order summary.

## Business opportunity

- Reduce recurring team coordination waste caused by ad-hoc Slack threads.
- Prove that small internal automations can be delivered within enterprise on-prem constraints.
- Create a low-risk employee-experience pilot with measurable adoption, task success, and operational safety.
- Demonstrate reuse of internal standards: Kubernetes, internal gateway routing, OIDC, Postgres, Kafka, Vault, Prometheus, and Grafana.

## Target users and stakeholders

- Teammates placing orders: want a fast way to submit or reuse coffee preferences.
- Coffee runner: wants one clean pickup list instead of reading a messy thread.
- Office managers/team leads: want fair rotation and fewer interruptions.
- IT/compliance stakeholders: want internal-only processing, approved identity/secrets patterns, and observability.

## Core user promise

CoffeeBuddy lets a team complete a coffee run through Slack with less coordination time, fewer missed orders, clearer runner responsibility, and no dependency on public-cloud workflow hosting.

## First demonstrable slice

A narrow but complete slice should show:

1. A teammate starts a coffee run from Slack.
2. Teammates submit structured orders.
3. CoffeeBuddy confirms received orders.
4. A reminder is sent before cutoff.
5. The run locks at cutoff.
6. A fair runner is assigned or confirmed.
7. A final consolidated summary is posted.
8. Run/order/preference history is persisted internally.
9. Basic metrics are exposed for operational review.

## Strategic fit

CoffeeBuddy is a practical internal workflow product because the problem is frequent, bounded, easy to pilot, and measurable. It also tests the enterprise delivery path without introducing sensitive business transactions, payments, or external vendor dependencies.

## MVP focus

### Must prove

- Slack-native workflow initiation and interaction.
- Structured order capture.
- Preference memory.
- Fair runner assignment.
- Reminder and cutoff behavior.
- Final summary generation.
- On-prem deployment compatibility.
- Operational observability.

### Should defer

- Payments.
- Delivery logistics.
- Vendor menu integrations.
- Complex admin console.
- Public-cloud deployment.
- Mobile app.
- Calendar integration.

## Deployment portability reasoning

The canonical IDEA constrains CoffeeBuddy to on-prem Kubernetes and internal-only routes. The first slice should avoid coupling business logic to a single gateway implementation beyond documented ingress behavior, because the attached context names both NGINX and Kong Gateway. Infrastructure-specific implementation details should be finalized in SPEC/PLAN with evidence from enterprise standards.

## /spec handoff readiness

SPEC should convert this idea into testable requirements for:

- Slack command/event/interactivity flows.
- Coffee run lifecycle states.
- Order submission and editing rules.
- Preference storage and retrieval.
- Runner eligibility and fairness rules.
- Reminder and cutoff behavior.
- Final summary format.
- Security controls for Slack secrets and signatures.
- Internal auth requirements for admin/API access.
- Persistence model for users, runs, orders, preferences, runner history, and audit events.
- Metrics and acceptance evidence.

## Open handoff cautions

- Do not expand into a broad office concierge system.
- Do not create public-cloud assumptions.
- Do not treat BMAD companion content as canonical when it conflicts with `docs/harper/IDEA.md`.
- Validate the Slack-to-on-prem ingress path before overbuilding downstream features.
````

````file:docs/harper/bmad/idea/PRFAQ_NOTES.md
# PRFAQ Notes — CoffeeBuddy

## Draft press-release angle

CoffeeBuddy makes the office coffee run effortless and fair by turning chaotic Slack threads into a simple, auditable workflow that runs entirely inside the enterprise environment.

## Customer promise

- Start a coffee run in seconds.
- Submit or update an order without searching a thread.
- Reuse a usual order.
- Know who is picking up and why they were selected.
- Receive a reminder before cutoff.
- See one final source-of-truth summary.
- Keep workflow processing inside corporate infrastructure.

## Why now

Teams already coordinate in Slack, but manual threads are noisy, inconsistent, and easy to miss. Enterprise teams also need small automations to respect internal identity, gateway, secrets, and observability standards rather than defaulting to public SaaS backends.

## FAQ

### Who is CoffeeBuddy for?

Office teammates who coordinate recurring coffee runs in Slack, plus the runner who needs a clean pickup summary and team leads who want lower coordination overhead.

### What problem does it solve?

It replaces informal Slack-thread coordination with a structured workflow for starting a run, collecting orders, reminding participants, assigning a fair runner, and posting a final summary.

### Why not keep using Slack threads?

Threads are flexible but unreliable for this workflow. Orders get buried, formats vary, people forget cutoff times, and runner selection is often manual or unfair.

### Why does this need to run on-prem?

The attached IDEA states the target context is regulated enterprise use where public cloud services are restricted. CoffeeBuddy must keep application data and processing inside approved corporate infrastructure.

### What is the first slice?

A Slack-initiated coffee run that collects structured orders, remembers a preference, sends a reminder, assigns or confirms a fair runner, posts a final summary, persists data, and exposes basic metrics.

### What is not included?

Payments, delivery logistics, external coffee vendor integrations, public cloud deployment, mobile app, vendor menu catalog, and complex admin UI.

### How is fairness handled?

The initial fairness model should be transparent and simple, such as selecting from eligible participants based on recent runner history while allowing opt-outs when supported by SPEC.

### What could cause adoption failure?

The Slack flow may be too slow, the form may be too rigid, users may dislike automatic runner assignment, or reminders may be noisy. The MVP should optimize for a fast “usual order” path and clear explanations.

### What could cause delivery failure?

The biggest early risk is proving the Slack-to-on-prem ingress path with signature validation, secrets management, internal routing, and reliable acknowledgement behavior.

## Press-release challenge questions

- Can a first-time user complete an order without training?
- Does the runner receive enough information to act without reading prior Slack messages?
- Is the runner assignment explainable in one sentence?
- Does the workflow still work when Slack rate limits or retries occur?
- Is all sensitive configuration stored outside code?
- Can IT observe the health of the workflow through approved metrics?
- Can the pilot prove value without payments, menus, or delivery integrations?

## PRFAQ acceptance signal

A successful pilot should produce repeat team usage, order confirmations in under 2 minutes from the initiating action, fewer missed orders, a clear runner summary, and positive feedback from both participants and assigned runners.
````

````file:docs/harper/bmad/idea/ASSUMPTIONS.md
# BMAD Assumptions — CoffeeBuddy

## Source assumptions

- The attached `IDEA.md` is the primary source of truth for product intent.
- Companion artifacts are advisory context and do not override the canonical IDEA.
- A local repository snapshot was analyzed; GitHub remote verification was not available in this run.
- Repository evidence shows documentation and CLike capability context only; no existing application entry point was detected.
- No external market research, competitor scan, stakeholder interview transcript, or production incident history was attached.

## Business assumptions

- Slack is the primary collaboration surface for the target teams.
- Coffee runs are frequent enough to justify a small internal workflow service.
- Users value fairness and reduced coordination time more than broad feature depth.
- A narrow pilot can validate value before expanding admin, menu, or integration capabilities.
- Office managers or team leads can sponsor adoption inside selected channels.

## User and UX assumptions

- Users will accept structured Slack modals or interactive messages if they are faster than thread replies.
- “Use my usual” or saved preferences will materially reduce repeated typing.
- Runner fairness must be understandable to avoid distrust.
- A reminder before cutoff is useful, but excessive notifications could reduce adoption.
- A final summary should be easy for the runner to act on without additional clarification.

## Technical assumptions

- Slack events, slash commands, and interactions can be routed to on-prem services through approved gateway/ingress paths.
- Slack request signatures can be verified by the receiving service.
- Slack tokens and signing secrets can be stored in Vault or an approved secrets manager.
- Postgres is the preferred relational store for workflow state, preferences, and history.
- Kafka is available or intended for buffering events, reminders, notifications, and retryable workflows.
- Prometheus and Grafana are available or intended for metrics and dashboards.
- OIDC is relevant for internal admin/API access, not necessarily for every Slack interaction.
- Python runtime is supported by the attached technology constraints.
- Jenkins is an available CI system per attached constraints.

## Delivery assumptions

- The first implementation step should validate the Slack-to-on-prem path before building deeper workflow features.
- One active coffee run per channel is a reasonable default until product research proves otherwise.
- Initial configuration may be file-based or internal-API-based; a rich admin UI is not required for slice-1.
- Fair runner assignment can start with a simple, deterministic, explainable algorithm.
- Preference and runner history data retention requirements need confirmation before production rollout.

## Data and compliance assumptions

- Coffee preferences, Slack IDs, channel IDs, and runner history are internal employee data and should be minimized.
- Retention controls may be required even though the data is low-risk compared with regulated business records.
- Public-cloud processing is excluded for the first slice.
- Internal-only routes are required for application APIs.
- Audit events may be useful for enterprise review, especially assignment changes and admin actions.

## Dependency assumptions

- Enterprise Slack workspace administration can configure commands, bot scopes, event subscriptions, and interactivity endpoints.
- Gateway owners can expose the required Slack-facing routes while keeping application services internal.
- Identity/secrets/observability teams can provide or approve the referenced platform services.
- The delivery team can access a test Slack workspace or equivalent enterprise sandbox.

## Assumption validation priorities

1. Confirm Slack-to-on-prem ingress feasibility and response-time constraints.
2. Confirm approved Slack scopes, commands, events, and interaction patterns.
3. Confirm retention requirements for preferences, orders, and runner history.
4. Confirm runner eligibility and opt-out expectations.
5. Confirm whether OIDC mapping is required for all users or only admin/API users.
6. Confirm operational SLOs and metrics thresholds for the pilot.

## Canonical conflict rule

If this assumptions file conflicts with `docs/harper/IDEA.md`, the canonical IDEA wins.
````

````file:docs/harper/bmad/idea/RESEARCH_QUESTIONS.md
# BMAD Research Questions — CoffeeBuddy

## User and workflow research

- Which Slack interaction should be primary for slice-1: slash command, channel shortcut, message shortcut, modal, or interactive message?
- What is the most common coffee-run pattern: one runner collecting many orders, rotating runner, volunteer runner, or manager-assigned runner?
- Should the runner be selected from all channel members, only participants, or a configured eligible pool?
- Should users be able to opt out of runner eligibility for a specific run?
- Should the assigned runner be able to reassign themselves?
- Should CoffeeBuddy allow multiple simultaneous runs in one channel?
- Should a run require manual confirmation before locking, or should cutoff locking be automatic?
- Should final summaries be posted publicly in the channel, privately to the runner, or both?
- Should reminders be sent to the whole channel, only non-responders, or participants via DM?
- What minimum order fields are needed for slice-1: drink, size, milk, sugar, notes, pickup location, or cutoff time?

## Slack UX research

- Is `/coffee start` the desired primary command?
- Should users submit orders via modal, button-driven “usual order,” structured text, or a combination?
- What Slack bot scopes are required and approved?
- What events and interaction payloads must be supported for the MVP?
- What acknowledgement latency is required for commands and interactions in the target Slack environment?
- How should CoffeeBuddy communicate failed submissions, late orders, or locked runs?
- What message format makes the runner summary easiest to act on?
- Should CoffeeBuddy support editing or canceling an order before cutoff in slice-1?

## Fairness and policy research

- What fairness algorithm will users perceive as legitimate?
- Should fairness use recent history, all-time history, weighted participation, or manual rotation?
- How should vacations, meetings, remote work, or temporary unavailability affect eligibility?
- Should runner history be visible to users?
- Should managers or admins be able to override assignments?
- What audit trail is required for runner assignment and reassignment?

## Enterprise technology research

- Which gateway is authoritative for Slack-facing routes in the target environment: NGINX, Kong Gateway, or both?
- Are public Slack endpoints allowed to reach an internal gateway, and under what network controls?
- What TLS, DNS, firewall, and proxy requirements apply?
- Are Slack request payloads allowed to be persisted for debugging, or only normalized event records?
- What retention period applies to orders, preferences, runner history, and audit events?
- Are Slack user IDs sufficient for participants, or must users be mapped to OIDC identities?
- Which secrets manager path and rotation policy should be used for Slack tokens and signing secrets?
- Which Kafka topics, retention settings, and partitioning strategy are approved?
- Which Postgres HA and backup requirements apply?
- What Prometheus metrics and Grafana dashboards are required for operational acceptance?
- What Jenkins pipeline requirements apply to build, test, scan, and deploy?

## Pilot success research

- What team size is ideal for a first pilot?
- How many weekly runs are needed to prove adoption?
- What baseline coordination time should be measured before launch?
- What target reduction in missed orders or pickup mistakes is realistic?
- How should pilot satisfaction be collected from participants and runners?
- What usage threshold justifies further investment?
- What failure threshold should stop or redesign the pilot?

## SPEC handoff questions

- Define exact coffee run lifecycle states and allowed transitions.
- Define required order fields and validation rules.
- Define preference create/update/delete behavior.
- Define runner eligibility and fairness acceptance tests.
- Define reminder timing and retry behavior.
- Define final summary content and visibility.
- Define idempotency requirements for Slack retries.
- Define security requirements for signature verification and secrets.
- Define persistence entities and retention policies.
- Define metrics required for EVAL/GATE evidence.

## Highest-priority unknowns

1. Slack-to-on-prem ingress feasibility.
2. Required Slack interaction pattern and scopes.
3. Runner eligibility/opt-out rules.
4. Data retention and identity mapping requirements.
5. Pilot success thresholds and baseline measurements.
````