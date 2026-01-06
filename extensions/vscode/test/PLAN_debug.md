# PLAN — voicesurveyagent

## Plan Snapshot

- **Counts:** total=24 / open=4 / in_progress=20 / done=0 / deferred=0
- **Progress:** 0% complete
- **Checklist:**
  - [x] SPEC aligned
  - [x] Prior REQ reconciled
  - [x] Dependencies mapped
  - [x] KIT-readiness per REQ confirmed

## Tracks & Scope Boundaries

- **Tracks:**
  - `App` — Core application logic: authentication, campaign management, contact handling, call orchestration, dialogue, events, email, dashboard
  - `Infra` — Database migrations, Redis setup, SQS configuration, EKS deployment, observability stack
  - `Data` — Schema migrations, seed data, retention jobs

- **Out of scope / Deferred:**
  - Inbound call flows, IVR menus, call transfers
  - Multi-tenant isolation
  - Advanced analytics beyond basic metrics
  - Multiple concurrent telephony providers
  - More than 3 survey questions
  - Sentiment analysis or topic modeling

## Module/Package & Namespace Plan (per KIT)

### Track=App Slices

| Slice | Root Namespace | Responsibilities |
|-------|----------------|------------------|
| `auth` | `app.auth` | OIDC integration, JWT validation, RBAC middleware |
| `campaigns` | `app.campaigns` | Campaign CRUD, validation, lifecycle state machine |
| `contacts` | `app.contacts` | Contact management, CSV import, exclusion lists |
| `calls` | `app.calls` | Call scheduling, attempt tracking, retry logic |
| `telephony` | `app.telephony` | Provider adapter interface, webhook handlers |
| `dialogue` | `app.dialogue` | LLM orchestration, consent flow, Q&A flow |
| `events` | `app.events` | Event publishing, SQS integration |
| `email` | `app.email` | Email worker, template rendering |
| `dashboard` | `app.dashboard` | Stats aggregation, export generation |
| `admin` | `app.admin` | Provider config, system settings |

### Track=Infra Modules

| Module | Purpose |
|--------|---------|
| `infra.db` | Postgres RDS setup, connection pooling |
| `infra.cache` | Redis cluster configuration |
| `infra.queue` | SQS queues and DLQ setup |
| `infra.observability` | CloudWatch, Prometheus, OpenTelemetry |
| `infra.secrets` | AWS Secrets Manager integration |
| `infra.eks` | Kubernetes manifests, Helm charts |

### Track=Data Modules

| Module | Purpose |
|--------|---------|
| `data.migrations` | Alembic migrations for all entities |
| `data.retention` | Scheduled jobs for data cleanup |

## REQ-IDs Table

| ID | Title | Acceptance | DependsOn | Track | Status |
|---|---|---|---|---|---|
| REQ-001 | Database schema and migrations | All entities from SPEC data model have corresponding Alembic migrations<br/>Migrations are idempotent and can be run multiple times without error<br/>Foreign key columns have appropriate indexes for query performance<br/>Enum types are created for all status and type fields<br/>UUID primary keys use PostgreSQL native UUID type |  | Infra | in_progress |
| REQ-002 | OIDC authentication integration | OIDC authorization code flow implemented with configurable IdP endpoints<br/>JWT tokens validated on every API request via middleware<br/>User record created or updated on first login with OIDC subject mapping<br/>Session tokens have configurable expiration with refresh capability<br/>Invalid or expired tokens return 401 with appropriate error message | REQ-001 | App | in_progress |
| REQ-003 | RBAC authorization middleware | Role extracted from JWT claims or user database record<br/>Route decorators enforce minimum required role<br/>Admin endpoints restricted to admin role only<br/>Campaign modification restricted to campaign_manager and admin<br/>Denied access attempts logged with user ID, endpoint, and timestamp | REQ-002 | App | in_progress |
| REQ-004 | Campaign CRUD API | POST /api/campaigns creates campaign in draft status<br/>GET /api/campaigns returns paginated list with status filter<br/>GET /api/campaigns/{id} returns full campaign details<br/>PUT /api/campaigns/{id} validates field changes against current status<br/>Status transitions follow state machine: draft→scheduled→running→paused→completed | REQ-003 | App | in_progress |
| REQ-005 | Campaign validation service | Activation blocked if campaign has zero contacts<br/>Activation blocked if any of 3 questions is empty<br/>Activation blocked if retry policy invalid (attempts < 1 or > 5)<br/>Activation blocked if time window invalid (start >= end)<br/>Successful validation transitions status to running or scheduled | REQ-004 | App | in_progress |
| REQ-006 | Contact CSV upload and parsing | POST /api/campaigns/{id}/contacts/upload accepts multipart CSV<br/>Phone numbers validated against E.164 format<br/>Invalid rows collected with line number and error reason<br/>Valid rows create Contact records in pending state<br/>At least 95% of valid rows accepted when file has mixed validity | REQ-004 | App | in_progress |
| REQ-007 | Exclusion list management | POST /api/exclusions/import accepts CSV of phone numbers<br/>Contacts matching exclusion list marked as excluded state<br/>Excluded contacts never returned by scheduler queries<br/>Manual exclusion addition via API supported<br/>Exclusion removal requires admin role | REQ-006 | App | in_progress |
| REQ-008 | Call scheduler service | Scheduler runs as background task every 60 seconds<br/>Selects contacts with state pending or not_reached<br/>Filters by attempts_count < campaign.max_attempts<br/>Filters by current time within allowed_call_start/end window<br/>Creates CallAttempt record before initiating call | REQ-007 | App | in_progress |
| REQ-009 | Telephony provider adapter interface | TelephonyProvider interface defines initiate_call method<br/>Interface defines parse_webhook_event method<br/>Concrete adapter implements Twilio-compatible API<br/>Adapter configurable via ProviderConfig entity<br/>Adapter is injectable for testing with mock provider | REQ-001 | App | in_progress |
| REQ-010 | Telephony webhook handler | POST /webhooks/telephony/events receives provider callbacks<br/>Events parsed into domain CallEvent objects<br/>call.answered triggers dialogue start<br/>call.no_answer updates attempt outcome and contact state<br/>Duplicate events handled idempotently via call_id | REQ-009 | App | in_progress |
| REQ-011 | LLM gateway integration | LLMGateway interface defines chat_completion method<br/>Gateway supports configurable provider (OpenAI, Anthropic)<br/>System prompt includes survey context and constraints<br/>Timeout handling with configurable duration<br/>Gateway errors logged with correlation ID | REQ-001 | App | in_progress |
| REQ-012 | Dialogue orchestrator consent flow | Intro script played immediately on call.answered<br/>Consent question asked after intro<br/>Positive consent proceeds to first question<br/>Negative consent triggers call termination within 10 seconds<br/>survey.refused event published on refusal | REQ-010, REQ-011 | App | in_progress |
| REQ-013 | Dialogue orchestrator Q&A flow | Questions asked sequentially after consent<br/>Each question text from campaign configuration<br/>Answer captured and stored in draft state<br/>Repeat request detected and question re-asked once<br/>All 3 answers captured before completion flow | REQ-012 | App | in_progress |
| REQ-014 | Survey response persistence | SurveyResponse created with all 3 answers<br/>Response linked to successful CallAttempt<br/>Contact state updated to completed<br/>Timestamps recorded for completion<br/>Transaction ensures atomicity of all updates | REQ-013 | App | in_progress |
| REQ-015 | Event publisher service | EventPublisher interface defines publish method<br/>SQS adapter implements publish to configured queue<br/>Event schema includes event_type, campaign_id, contact_id, call_id<br/>Message deduplication via call_id<br/>Failed publishes retried with exponential backoff | REQ-014 | App | in_progress |
| REQ-016 | Email worker service | Email worker polls SQS queue continuously<br/>survey.completed triggers completed email if template configured<br/>Template variables substituted from event payload<br/>EmailNotification record created with status<br/>Failed sends retried up to 3 times with backoff | REQ-015 | App | in_progress |
| REQ-017 | Campaign dashboard stats API | GET /api/campaigns/{id}/stats returns aggregate metrics<br/>Metrics include total, completed, refused, not_reached counts<br/>Time-series data for calls per hour/day<br/>Stats cached with 60-second TTL<br/>Response time under 500ms for campaigns with 10k contacts | REQ-014 | App | in_progress |
| REQ-018 | Campaign CSV export | GET /api/campaigns/{id}/export initiates export job<br/>Export includes campaign_id, contact_id, external_contact_id<br/>Async job stores CSV in S3 with signed URL<br/>Download URL returned with expiration<br/>Export respects RBAC (campaign_manager or admin only) | REQ-017 | App | in_progress |
| REQ-019 | Admin configuration API | GET /api/admin/config returns current configuration<br/>PUT /api/admin/config updates provider settings<br/>Telephony provider credentials stored in Secrets Manager<br/>Config changes logged in audit trail<br/>Admin role required for all config endpoints | REQ-003 | App | in_progress |
| REQ-020 | Call detail view API | GET /api/calls/{call_id} returns call details<br/>Response includes outcome, attempt_number, timestamps<br/>Transcript snippet included if stored<br/>Access restricted to campaign_manager and admin<br/>404 returned for non-existent call_id | REQ-014 | App | open |
| REQ-021 | Observability instrumentation | All log entries in structured JSON format<br/>Correlation ID propagated across HTTP, telephony, LLM calls<br/>Prometheus metrics endpoint at /metrics<br/>OpenTelemetry traces for API requests<br/>Log level configurable via environment variable | REQ-001 | Infra | open |
| REQ-022 | Data retention jobs | Retention job runs daily as scheduled task<br/>Recordings older than retention_days deleted from storage<br/>Deletion logged with count and timestamp<br/>Job handles partial failures gracefully<br/>GDPR deletion requests processed within 72 hours | REQ-019 | Infra | open |
| REQ-023 | Frontend campaign management UI | Campaign list page shows all campaigns with status badges<br/>CSV upload component with drag-drop and progress indicator<br/>Activate button enabled only when validation passes<br/>Form validation matches backend rules<br/>Responsive design for desktop and tablet | REQ-004, REQ-006 | App | open |
| REQ-024 | Frontend dashboard and export UI | Dashboard shows completion/refusal/not_reached percentages<br/>Time-series chart for call activity<br/>Export button triggers async job<br/>Stats refresh automatically every 60 seconds<br/>Error states with retry options | REQ-017, REQ-018 | App | open |



### Acceptance — REQ-001

- All entities from SPEC data model have corresponding Alembic migrations
- Migrations are idempotent and can be run multiple times without error
- Foreign key columns have appropriate indexes for query performance
- Enum types are created for all status and type fields
- UUID primary keys use PostgreSQL native UUID type
- Timestamp columns default to UTC timezone
- Migration rollback scripts exist and are tested

### Acceptance — REQ-002

- OIDC authorization code flow implemented with configurable IdP endpoints
- JWT tokens validated on every API request via middleware
- User record created or updated on first login with OIDC subject mapping
- Session tokens have configurable expiration with refresh capability
- Invalid or expired tokens return 401 with appropriate error message
- Login endpoint returns user profile with role information

### Acceptance — REQ-003

- Role extracted from JWT claims or user database record
- Route decorators enforce minimum required role
- Admin endpoints restricted to admin role only
- Campaign modification restricted to campaign_manager and admin
- Viewer role has read-only access to campaigns and stats
- Denied access attempts logged with user ID, endpoint, and timestamp
- RBAC rules configurable without code changes

### Acceptance — REQ-004

- POST /api/campaigns creates campaign in draft status
- GET /api/campaigns returns paginated list with status filter
- GET /api/campaigns/{id} returns full campaign details
- PUT /api/campaigns/{id} validates field changes against current status
- DELETE /api/campaigns/{id} performs soft delete (status to cancelled)
- Status transitions follow state machine: draft→scheduled→running→paused→completed
- Invalid status transitions return 400 with explanation

### Acceptance — REQ-005

- Activation blocked if campaign has zero contacts
- Activation blocked if any of 3 questions is empty
- Activation blocked if retry policy invalid (attempts < 1 or > 5)
- Activation blocked if time window invalid (start >= end)
- Validation errors returned as structured list with field names
- Validation runs synchronously on activation request
- Successful validation transitions status to running or scheduled

### Acceptance — REQ-006

- POST /api/campaigns/{id}/contacts/upload accepts multipart CSV
- CSV parsed with configurable delimiter and encoding
- Phone numbers validated against E.164 format
- Email addresses validated with RFC-compliant regex
- Invalid rows collected with line number and error reason
- Valid rows create Contact records in pending state
- Response includes accepted count, rejected count, and error details
- At least 95% of valid rows accepted when file has mixed validity

### Acceptance — REQ-007

- POST /api/exclusions/import accepts CSV of phone numbers
- Exclusion entries stored with source and timestamp
- Contacts matching exclusion list marked as excluded state
- Excluded contacts never returned by scheduler queries
- Manual exclusion addition via API supported
- Exclusion removal requires admin role
- Exclusion check runs on contact creation and periodically

### Acceptance — REQ-008

- Scheduler runs as background task every 60 seconds
- Selects contacts with state pending or not_reached
- Filters by attempts_count < campaign.max_attempts
- Filters by current time within allowed_call_start/end window
- Respects max_concurrent_calls from provider config
- Creates CallAttempt record before initiating call
- Updates contact state to in_progress during call
- Handles scheduler failures gracefully with retry

### Acceptance — REQ-009

- TelephonyProvider interface defines initiate_call method
- Interface defines parse_webhook_event method
- Concrete adapter implements Twilio-compatible API
- Adapter configurable via ProviderConfig entity
- Call initiation includes callback URL and metadata
- Provider errors wrapped in domain exceptions
- Adapter is injectable for testing with mock provider

### Acceptance — REQ-010

- POST /webhooks/telephony/events receives provider callbacks
- Webhook signature validated if provider supports it
- Events parsed into domain CallEvent objects
- call.answered triggers dialogue start
- call.no_answer updates attempt outcome and contact state
- call.busy updates attempt outcome and contact state
- call.failed logs error and updates attempt outcome
- Duplicate events handled idempotently via call_id

### Acceptance — REQ-011

- LLMGateway interface defines chat_completion method
- Gateway supports configurable provider (OpenAI, Anthropic)
- System prompt includes survey context and constraints
- Response parsed for next utterance and control signals
- Timeout handling with configurable duration
- Rate limiting respected with backoff
- Gateway errors logged with correlation ID

### Acceptance — REQ-012

- Intro script played immediately on call.answered
- Consent question asked after intro
- LLM interprets response for consent intent
- Positive consent proceeds to first question
- Negative consent triggers call termination within 10 seconds
- Refusal updates CallAttempt outcome to refused
- Refusal updates Contact state to refused
- survey.refused event published on refusal

### Acceptance — REQ-013

- Questions asked sequentially after consent
- Each question text from campaign configuration
- LLM generates natural language question delivery
- Answer captured and stored in draft state
- Repeat request detected and question re-asked once
- Confusion or unclear answer prompts clarification
- All 3 answers captured before completion flow
- Answer confidence scores calculated if available

### Acceptance — REQ-014

- SurveyResponse created with all 3 answers
- Response linked to successful CallAttempt
- Contact state updated to completed
- CallAttempt outcome updated to completed
- Timestamps recorded for completion
- Confidence scores stored per answer
- Transaction ensures atomicity of all updates

### Acceptance — REQ-015

- EventPublisher interface defines publish method
- SQS adapter implements publish to configured queue
- Event schema includes event_type, campaign_id, contact_id, call_id
- survey.completed includes answers array
- survey.refused includes attempt count
- survey.not_reached includes total attempts
- Message deduplication via call_id
- Failed publishes retried with exponential backoff

### Acceptance — REQ-016

- Email worker polls SQS queue continuously
- survey.completed triggers completed email if template configured
- survey.refused triggers refused email if template configured
- survey.not_reached triggers not_reached email if template configured
- Template variables substituted from event payload
- Email sent via configured SMTP or API provider
- EmailNotification record created with status
- Failed sends retried up to 3 times with backoff

### Acceptance — REQ-017

- GET /api/campaigns/{id}/stats returns aggregate metrics
- Metrics include total, completed, refused, not_reached counts
- Metrics include completion rate percentage
- Time-series data for calls per hour/day
- Average call duration calculated
- P95 latency reported if available
- Stats cached with 60-second TTL
- Response time under 500ms for campaigns with 10k contacts

### Acceptance — REQ-018

- GET /api/campaigns/{id}/export initiates export job
- Export includes campaign_id, contact_id, external_contact_id
- Export includes phone_number, outcome, attempt_count
- Export includes timestamps and 3 answers for completed
- Export excludes raw transcripts and full PII
- Async job stores CSV in S3 with signed URL
- Download URL returned with expiration
- Export respects RBAC (campaign_manager or admin only)

### Acceptance — REQ-019

- GET /api/admin/config returns current configuration
- PUT /api/admin/config updates provider settings
- Telephony provider credentials stored in Secrets Manager
- LLM provider and model configurable
- Retention days configurable for recordings and transcripts
- Email provider settings configurable
- Config changes logged in audit trail
- Admin role required for all config endpoints

### Acceptance — REQ-020

- GET /api/calls/{call_id} returns call details
- Response includes outcome, attempt_number, timestamps
- Response includes provider_call_id and error codes if any
- Transcript snippet included if stored
- Recording URL included if available and not expired
- Access restricted to campaign_manager and admin
- Call must belong to accessible campaign
- 404 returned for non-existent call_id

### Acceptance — REQ-021

- All log entries in structured JSON format
- Correlation ID propagated across HTTP, telephony, LLM calls
- Prometheus metrics endpoint at /metrics
- Metrics include call_attempts_total, survey_completions_total
- Metrics include provider_errors_total, llm_latency_histogram
- OpenTelemetry traces for API requests
- Traces span across async operations
- Log level configurable via environment variable

### Acceptance — REQ-022

- Retention job runs daily as scheduled task
- Recordings older than retention_days deleted from storage
- Transcripts older than retention_days anonymized or deleted
- Deletion logged with count and timestamp
- Retention period read from ProviderConfig
- Job handles partial failures gracefully
- Manual trigger available via admin API
- GDPR deletion requests processed within 72 hours

### Acceptance — REQ-023

- Campaign list page shows all campaigns with status badges
- Campaign detail page shows configuration and contact stats
- CSV upload component with drag-drop and progress indicator
- Upload validation errors displayed inline
- Activate button enabled only when validation passes
- Pause/Resume buttons for running campaigns
- Form validation matches backend rules
- Responsive design for desktop and tablet

### Acceptance — REQ-024

- Dashboard shows completion/refusal/not_reached percentages
- Time-series chart for call activity
- Contact table with pagination and outcome filter
- Export button triggers async job
- Download link appears when export ready
- Stats refresh automatically every 60 seconds
- Loading states for all async operations
- Error states with retry options

## Dependency Graph (textual)

```
REQ-001 -> []
REQ-002 -> [REQ-001]
REQ-003 -> [REQ-002]
REQ-004 -> [REQ-003]
REQ-005 -> [REQ-004]
REQ-006 -> [REQ-004]
REQ-007 -> [REQ-006]
REQ-008 -> [REQ-007]
REQ-009 -> [REQ-001]
REQ-010 -> [REQ-009]
REQ-011 -> [REQ-001]
REQ-012 -> [REQ-010, REQ-011]
REQ-013 -> [REQ-012]
REQ-014 -> [REQ-013]
REQ-015 -> [REQ-014]
REQ-016 -> [REQ-015]
REQ-017 -> [REQ-014]
REQ-018 -> [REQ-017]
REQ-019 -> [REQ-003]
REQ-020 -> [REQ-014]
REQ-021 -> [REQ-001]
REQ-022 -> [REQ-019]
REQ-023 -> [REQ-004, REQ-006]
REQ-024 -> [REQ-017, REQ-018]
```

## Iteration Strategy

### Batch 1 — Foundation (S)
- REQ-001: Database schema and migrations
- REQ-021: Observability instrumentation
- Estimated: 2-3 days
- Confidence: High (±0 batches)

### Batch 2 — Authentication & Authorization (S)
- REQ-002: OIDC authentication integration
- REQ-003: RBAC authorization middleware
- Estimated: 2-3 days
- Confidence: High (±0 batches)

### Batch 3 — Campaign Core (M)
- REQ-004: Campaign CRUD API
- REQ-005: Campaign validation service
- REQ-019: Admin configuration API
- Estimated: 3-4 days
- Confidence: Medium (±1 batch)

### Batch 4 — Contact Management (M)
- REQ-006: Contact CSV upload and parsing
- REQ-007: Exclusion list management
- Estimated: 3-4 days
- Confidence: Medium (±1 batch)

### Batch 5 — Telephony Integration (M)
- REQ-009: Telephony provider adapter interface
- REQ-010: Telephony webhook handler
- REQ-008: Call scheduler service
- Estimated: 4-5 days
- Confidence: Medium (±1 batch)

### Batch 6 — Dialogue & LLM (L)
- REQ-011: LLM gateway integration
- REQ-012: Dialogue orchestrator consent flow
- REQ-013: Dialogue orchestrator Q&A flow
- REQ-014: Survey response persistence
- Estimated: 5-7 days
- Confidence: Low (±2 batches)

### Batch 7 — Events & Email (M)
- REQ-015: Event publisher service
- REQ-016: Email worker service
- Estimated: 3-4 days
- Confidence: Medium (±1 batch)

### Batch 8 — Dashboard & Export (M)
- REQ-017: Campaign dashboard stats API
- REQ-018: Campaign CSV export
- REQ-020: Call detail view API
- REQ-022: Data retention jobs
- Estimated: 4-5 days
- Confidence: Medium (±1 batch)

### Batch 9 — Frontend (L)
- REQ-023: Frontend campaign management UI
- REQ-024: Frontend dashboard and export UI
- Estimated: 5-7 days
- Confidence: Low (±2 batches)

## Test Strategy

### Per REQ Testing

| REQ | Unit Tests | Integration Tests | E2E Tests |
|-----|------------|-------------------|-----------|
| REQ-001 | Migration scripts | DB connection, schema validation | — |
| REQ-002 | JWT parsing, token validation | OIDC flow with mock IdP | Login flow |
| REQ-003 | Role extraction, permission checks | Protected endpoint access | — |
| REQ-004 | Campaign model validation | API CRUD operations | — |
| REQ-005 | Validation rules | Activation flow | — |
| REQ-006 | CSV parsing, row validation | Upload endpoint | — |
| REQ-007 | Exclusion matching | Import and query | — |
| REQ-008 | Scheduling logic, time windows | Scheduler with mock provider | — |
| REQ-009 | Adapter interface | Provider API calls | — |
| REQ-010 | Event parsing | Webhook processing | — |
| REQ-011 | Prompt construction | LLM API calls | — |
| REQ-012 | Consent detection | Full consent flow | — |
| REQ-013 | Q&A state machine | Full dialogue | — |
| REQ-014 | Response persistence | Transaction integrity | — |
| REQ-015 | Event serialization | SQS publishing | — |
| REQ-016 | Template rendering | Email sending | — |
| REQ-017 | Aggregation queries | Stats API | — |
| REQ-018 | CSV generation | Export flow | — |
| REQ-019 | Config validation | Config API | — |
| REQ-020 | Call data retrieval | Detail API | — |
| REQ-021 | Log formatting | Metrics endpoint | — |
| REQ-022 | Retention logic | Cleanup job | — |
| REQ-023 | Component rendering | Form submission | Campaign creation |
| REQ-024 | Chart rendering | Data loading | Export download |

### Per Batch Validation

- **Batch 1**: Schema matches SPEC data model, migrations reversible
- **Batch 2**: Full auth flow works with test IdP
- **Batch 3**: Campaign lifecycle state machine correct
- **Batch 4**: CSV with 1000 rows processes in <30s
- **Batch 5**: Mock calls scheduled and tracked correctly
- **Batch 6**: Full dialogue flow with mock LLM completes
- **Batch 7**: Events published and emails sent
- **Batch 8**: Stats accurate, export complete
- **Batch 9**: UI functional for all workflows

## KIT Readiness (per REQ)

### REQ-001
- **Path**: `/runs/kit/REQ-001/src/data/migrations/`
- **Primary module**: `data.migrations`
- **Shared modules**: None (foundation)
- **Creates new modules**: Yes — `data.migrations`
- **Scaffolds**: Alembic configuration, initial migration
- **Commands**: `alembic upgrade head`, `alembic downgrade -1`
- **Expected**: All migrations apply cleanly
- **KIT-functional**: yes

### REQ-002
- **Path**: `/runs/kit/REQ-002/src/app/auth/`
- **Primary module**: `app.auth`
- **Shared modules**: `data.migrations` (User model)
- **Creates new modules**: Yes — `app.auth`
- **Scaffolds**: OIDC client, JWT middleware
- **Commands**: `pytest tests/auth/`
- **Expected**: Auth tests pass
- **KIT-functional**: yes

### REQ-003
- **Path**: `/runs/kit/REQ-003/src/app/auth/`
- **Primary module**: `app.auth.rbac`
- **Shared modules**: `app.auth` (extends)
- **Creates new modules**: No — extends `app.auth`
- **Scaffolds**: RBAC decorators, permission checks
- **Commands**: `pytest tests/auth/test_rbac.py`
- **Expected**: RBAC tests pass
- **KIT-functional**: yes

### REQ-004
- **Path**: `/runs/kit/REQ-004/src/app/campaigns/`
- **Primary module**: `app.campaigns`
- **Shared modules**: `app.auth.rbac`, `data.migrations`
- **Creates new modules**: Yes — `app.campaigns`
- **Scaffolds**: Campaign router, service, repository
- **Commands**: `pytest tests/campaigns/`
- **Expected**: CRUD tests pass
- **KIT-functional**: yes
- **API documentation**: `/runs/kit/REQ-004/test/api/campaigns.json`

### REQ-005
- **Path**: `/runs/kit/REQ-005/src/app/campaigns/`
- **Primary module**: `app.campaigns.validation`
- **Shared modules**: `app.campaigns` (extends)
- **Creates new modules**: No — extends `app.campaigns`
- **Scaffolds**: Validation service
- **Commands**: `pytest tests/campaigns/test_validation.py`
- **Expected**: Validation tests pass
- **KIT-functional**: yes

### REQ-006
- **Path**: `/runs/kit/REQ-006/src/app/contacts/`
- **Primary module**: `app.contacts`
- **Shared modules**: `app.campaigns`, `data.migrations`
- **Creates new modules**: Yes — `app.contacts`
- **Scaffolds**: CSV parser, contact router
- **Commands**: `pytest tests/contacts/`
- **Expected**: Upload tests pass
- **KIT-functional**: yes
- **API documentation**: `/runs/kit/REQ-006/test/api/contacts.json`

### REQ-007
- **Path**: `/runs/kit/REQ-007/src/app/contacts/`
- **Primary module**: `app.contacts.exclusions`
- **Shared modules**: `app.contacts` (extends)
- **Creates new modules**: No — extends `app.contacts`
- **Scaffolds**: Exclusion service, import handler
- **Commands**: `pytest tests/contacts/test_exclusions.py`
- **Expected**: Exclusion tests pass
- **KIT-functional**: yes

### REQ-008
- **Path**: `/runs/kit/REQ-008/src/app/calls/`
- **Primary module**: `app.calls.scheduler`
- **Shared modules**: `app.contacts`, `app.campaigns`
- **Creates new modules**: Yes — `app.calls`
- **Scaffolds**: Scheduler service, background task
- **Commands**: `pytest tests/calls/test_scheduler.py`
- **Expected**: Scheduling tests pass
- **KIT-functional**: yes

### REQ-009
- **Path**: `/runs/kit/REQ-009/src/app/telephony/`
- **Primary module**: `app.telephony`
- **Shared modules**: `data.migrations`
- **Creates new modules**: Yes — `app.telephony`
- **Scaffolds**: Provider interface, Twilio adapter
- **Commands**: `pytest tests/telephony/`
- **Expected**: Adapter tests pass
- **KIT-functional**: yes

### REQ-010
- **Path**: `/runs/kit/REQ-010/src/app/telephony/`
- **Primary module**: `app.telephony.webhooks`
- **Shared modules**: `app.telephony`, `app.calls`
- **Creates new modules**: No — extends `app.telephony`
- **Scaffolds**: Webhook router, event handlers
- **Commands**: `pytest tests/telephony/test_webhooks.py`
- **Expected**: Webhook tests pass
- **KIT-functional**: yes

### REQ-011
- **Path**: `/runs/kit/REQ-011/src/app/dialogue/`
- **Primary module**: `app.dialogue.llm`
- **Shared modules**: None
- **Creates new modules**: Yes — `app.dialogue`
- **Scaffolds**: LLM gateway, prompt templates
- **Commands**: `pytest tests/dialogue/test_llm.py`
- **Expected**: LLM integration tests pass
- **KIT-functional**: yes

### REQ-012
- **Path**: `/runs/kit/REQ-012/src/app/dialogue/`
- **Primary module**: `app.dialogue.consent`
- **Shared modules**: `app.dialogue.llm`, `app.telephony`
- **Creates new modules**: No — extends `app.dialogue`
- **Scaffolds**: Consent flow handler
- **Commands**: `pytest tests/dialogue/test_consent.py`
- **Expected**: Consent flow tests pass
- **KIT-functional**: yes

### REQ-013
- **Path**: `/runs/kit/REQ-013/src/app/dialogue/`
- **Primary module**: `app.dialogue.qa`
- **Shared modules**: `app.dialogue.consent`, `app.dialogue.llm`
- **Creates new modules**: No — extends `app.dialogue`
- **Scaffolds**: Q&A flow handler
- **Commands**: `pytest tests/dialogue/test_qa.py`
- **Expected**: Q&A flow tests pass
- **KIT-functional**: yes

### REQ-014
- **Path**: `/runs/kit/REQ-014/src/app/dialogue/`
- **Primary module**: `app.dialogue.persistence`
- **Shared modules**: `app.dialogue.qa`, `data.migrations`
- **Creates new modules**: No — extends `app.dialogue`
- **Scaffolds**: Response persistence service
- **Commands**: `pytest tests/dialogue/test_persistence.py`
- **Expected**: Persistence tests pass
- **KIT-functional**: yes

### REQ-015
- **Path**: `/runs/kit/REQ-015/src/app/events/`
- **Primary module**: `app.events`
- **Shared modules**: `app.dialogue.persistence`
- **Creates new modules**: Yes — `app.events`
- **Scaffolds**: Event publisher, SQS adapter
- **Commands**: `pytest tests/events/`
- **Expected**: Event publishing tests pass
- **KIT-functional**: yes

### REQ-016
- **Path**: `/runs/kit/REQ-016/src/app/email/`
- **Primary module**: `app.email`
- **Shared modules**: `app.events`, `data.migrations`
- **Creates new modules**: Yes — `app.email`
- **Scaffolds**: Email worker, template renderer
- **Commands**: `pytest tests/email/`
- **Expected**: Email worker tests pass
- **KIT-functional**: yes

### REQ-017
- **Path**: `/runs/kit/REQ-017/src/app/dashboard/`
- **Primary module**: `app.dashboard`
- **Shared modules**: `app.campaigns`, `app.contacts`, `app.calls`
- **Creates new modules**: Yes — `app.dashboard`
- **Scaffolds**: Stats service, aggregation queries
- **Commands**: `pytest tests/dashboard/`
- **Expected**: Stats API tests pass
- **KIT-functional**: yes
- **API documentation**: `/runs/kit/REQ-017/test/api/stats.json`

### REQ-018
- **Path**: `/runs/kit/REQ-018/src/app/dashboard/`
- **Primary module**: `app.dashboard.export`
- **Shared modules**: `app.dashboard` (extends)
- **Creates new modules**: No — extends `app.dashboard`
- **Scaffolds**: Export service, CSV generator
- **Commands**: `pytest tests/dashboard/test_export.py`
- **Expected**: Export tests pass
- **KIT-functional**: yes

### REQ-019
- **Path**: `/runs/kit/REQ-019/src/app/admin/`
- **Primary module**: `app.admin`
- **Shared modules**: `app.auth.rbac`, `data.migrations`
- **Creates new modules**: Yes — `app.admin`
- **Scaffolds**: Config router, secrets integration
- **Commands**: `pytest tests/admin/`
- **Expected**: Admin API tests pass
- **KIT-functional**: yes
- **API documentation**: `/runs/kit/REQ-019/test/api/admin.json`

### REQ-020
- **Path**: `/runs/kit/REQ-020/src/app/calls/`
- **Primary module**: `app.calls.detail`
- **Shared modules**: `app.calls` (extends)
- **Creates new modules**: No — extends `app.calls`
- **Scaffolds**: Call detail router
- **Commands**: `pytest tests/calls/test_detail.py`
- **Expected**: Detail API tests pass
- **KIT-functional**: yes
- **API documentation**: `/runs/kit/REQ-020/test/api/calls.json`

### REQ-021
- **Path**: `/runs/kit/REQ-021/src/infra/observability/`
- **Primary module**: `infra.observability`
- **Shared modules**: None
- **Creates new modules**: Yes — `infra.observability`
- **Scaffolds**: Logging config, metrics endpoint, tracing setup
- **Commands**: `pytest tests/infra/test_observability.py`
- **Expected**: Observability tests pass
- **KIT-functional**: yes

### REQ-022
- **Path**: `/runs/kit/REQ-022/src/infra/retention/`
- **Primary module**: `infra.retention`
- **Shared modules**: `app.admin`, `data.migrations`
- **Creates new modules**: Yes — `infra.retention`
- **Scaffolds**: Retention job, cleanup service
- **Commands**: `pytest tests/infra/test_retention.py`
- **Expected**: Retention tests pass
- **KIT-functional**: yes

### REQ-023
- **Path**: `/runs/kit/REQ-023/src/frontend/campaigns/`
- **Primary module**: `frontend.campaigns`
- **Shared modules**: None (frontend)
- **Creates new modules**: Yes — `frontend.campaigns`
- **Scaffolds**: Campaign pages, components
- **Commands**: `npm test -- --testPathPattern=campaigns`
- **Expected**: Frontend campaign tests pass
- **KIT-functional**: yes

### REQ-024
- **Path**: `/runs/kit/REQ-024/src/frontend/dashboard/`
- **Primary module**: `frontend.dashboard`
- **Shared modules**: `frontend.campaigns` (shared components)
- **Creates new modules**: Yes — `frontend.dashboard`
- **Scaffolds**: Dashboard pages, chart components
- **Commands**: `npm test -- --testPathPattern=dashboard`
- **Expected**: Frontend dashboard tests pass
- **KIT-functional**: yes

## Notes

### Assumptions
- Single telephony provider (Twilio-compatible) for slice-1
- LLM provider supports streaming for low-latency responses
- OIDC IdP is pre-configured and accessible
- AWS infrastructure (EKS, RDS, SQS) is provisioned separately
- Email service (SES or SMTP) is available

### Risks & Mitigations
- **Risk**: Telephony provider latency exceeds 1.5s P95
  - **Mitigation**: Implement provider timeout handling, monitor latency metrics, prepare adapter swap
- **Risk**: LLM response quality varies for consent detection
  - **Mitigation**: Use structured prompts, implement fallback detection logic, log edge cases
- **Risk**: CSV upload with large files causes timeouts
  - **Mitigation**: Implement chunked processing, async job for large files
- **Risk**: Concurrent call limits exceeded
  - **Mitigation**: Redis-based distributed locking, rate limiting in scheduler

### Open Questions
- Exact OIDC IdP configuration and claims structure
- Telephony provider selection (Twilio vs alternatives)
- LLM model selection for production (GPT-4 vs Claude)
- Recording storage location and access patterns

`PLAN_END`