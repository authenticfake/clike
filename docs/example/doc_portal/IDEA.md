# IDEA — Secure Payroll & F24 Document Portal

## Vision
Provide a complete, secure, and auditable platform for ingesting, storing, searching, and self-service consulting of corporate documents — primarily payroll (payslips) and F24 models — with minimal manual effort and maximum transparency across HR, Administration, and Employees.

## Problem Statement
Payroll and F24 documents are scattered across email threads, shared drives, or legacy portals with limited self-service. Manual provisioning and ad-hoc sharing create friction, security risks, and poor traceability. We need a single system that automates ingestion, identity provisioning, secure storage, and employee self-service access — while preserving integrity and auditability of originals.

## Target Users & Context
- **Primary**: Employees (self-service consultation and secure re-download of originals).
- **Secondary**: HR & Administration staff (controlled uploads, stats, error monitoring).
- **Context**: Cloud-first (AWS), enterprise SSO or Amazon Cognito, web UI (desktop & mobile), Italian fiscal domain (codice fiscale), compliance/audit requirements.

## Value & Outcomes
- **Automation**: Reduce manual operations via auto-provisioning (Cognito) during payroll ingestion.
- **Transparency**: Real-time feedback on uploads, statuses, and searchable catalogs by month/year/fiscal code.
- **Security & Integrity**: Encrypted, versioned storage; original files always recoverable in exact form; end-to-end audit trail.
- **Employee Experience**: Self-service portal for consulting and re-downloading personal documents.
- **Operational Insight**: Upload statistics split by Payroll vs F24; visibility on errors/incomplete uploads.

## Out of Scope (Initial)
- Payroll calculation/processing, payments, or tax filing workflows.
- Advanced case management (tickets/appeals).
- External provider integrations beyond AWS services required for identity, storage, logging (extendable later).

## Core Capabilities (from stakeholder brief)
1) **Document Upload (Payroll / F24)**
- Controlled uploads with format/size validation.
- Progress bar and real-time visual state.
- Confirmation/error messages via snackbar.
- Automatic reset of selected file after upload.
- Direct backend API integration to ensure metadata coherence and secure archiving.

2) **Automatic Provisioning on Amazon Cognito (Payroll ingestion)**
- On payroll document ingestion, transparently create a **Cognito user** of type `employee` when needed.
- Link identity to **codice fiscale**; grant authenticated portal access.
- Enables future self-service consultation without HR intervention.

3) **Search & Consultation**
- Explore documents by **month**, **year**, or **codice fiscale**.
- Show empty periods as **visible but non-selectable**.
- Secure **re-download of original files** at any time.
- Real-time refreshed results; filters by document type (Payroll/F24).

4) **Upload Statistics**
- Dedicated section to monitor upload activity.
- Totals by **Payroll** vs **F24**; highlight errors/incomplete uploads.
- Manual or automatic refresh.
- **Tabbed layout** for clear, immediate reading.

5) **Secure & Traceable Storage**
- Encrypted, versioned storage (e.g., **S3** with dedicated policies).
- Originals always available for exact re-download.
- Integrity via **hash checks**; **granular permissions**.
- Full file lifecycle **traced for audit & compliance**.

6) **End-to-End Logging**
- Every operation (upload → consult) logged as **structured JSON**.
- **AWS Lambda** traces requests, responses, and context.
- Unified logging for audit, diagnostics, and usage analytics.
- Sensitive data handled with **data-minimization & security** principles.

7) **Responsive, Modern UI**
- **React + Material UI** responsive layout (desktop & mobile).
- Tabs for Payroll vs F24; consistent iconography for success/error/loading.
- Smooth transitions (e.g., **Fade**, **Collapse**) for an intuitive feel.

## User Journeys (happy path)
1. **HR Uploads Payroll**
   - HR selects payroll file(s) → sees progress bar → backend validates & stores → if employee not present, platform **provisions Cognito** account → HR gets success snackbar → stats update.
2. **Employee Self-Service**
   - Employee logs in (Cognito) → navigates to Payroll tab → filters by year/month → sees non-available months as disabled → downloads original file securely.
3. **Admin Reviews Stats**
   - Admin opens “Statistics” → sees totals Payroll/F24, errors, incomplete uploads → triggers manual refresh or waits for auto-update.

## Information Model (high level)
- **Document**: id, type {PAYROLL,F24}, employeeFiscalCode, period {year,month}, originalFilename, mimeType, size, storageKey, storageVersionId, integrityHash, createdAt, createdBy, tags[].
- **Employee**: id, fiscalCode, email (optional), fullName (optional), cognitoUserId, status.
- **Events/Logs**: operation (UPLOAD/CONSULT/ERROR), actor (HR/EMPLOYEE/SYSTEM), timestamp, requestId, docId (optional), metadata, outcome.

## Non-Functional Requirements
- **Security**: at-rest (S3/KMS) & in-transit (TLS) encryption; least-privilege IAM; private buckets; signed URLs; audit immutability.
- **Observability**: structured logs, metrics (uploads count, errors, latency), traces for ingestion pipeline.
- **Scalability**: serverless ingestion (Lambda/API Gateway/SQS) and horizontally scalable UI/API.
- **Reliability**: versioned storage; retries/backoff on transient failures; idempotent ingestion.
- **Compliance**: GDPR (data minimization, purpose limitation); auditability; retention/lifecycle policies.

## Technology Constraints (initial)

```yaml
tech_constraints:
  version: 1.0.0
  profile: aws
  frontend:
    framework: react
    ui: material-ui
  backend:
    runtime: nodejs|python  # to confirm at SPEC
    api:
      - aws.api-gateway
      - rest
    functions:
      - aws.lambda
    messaging:
      - aws.sqs            # optional for buffering + retries
  auth:
    idp: amazon-cognito
    identity_link: fiscal_code
    portal_access: employee
  storage:
    documents:
      service: aws.s3
      encryption: kms
      versioning: enabled
      object_lock: optional
    metadata:
      service: dynamodb|rds  # to confirm at SPEC
  logging_observability:
    logs: cloudwatch-logs (json-structured)
    metrics: cloudwatch-metrics
    tracing: xray (optional)
  security:
    iam: least-privilege
    network: private endpoints where possible
    download: pre-signed-urls
  ui/ux:
    layout: tabs (Payroll, F24)
    feedback: snackbar, progress, disabled-states
    effects: fade, collapse
```

## Risks & Assumptions

* **Assumption**: HR can supply canonical **codice fiscale** to link employees at ingestion time.
* **Risk**: Mis-mapped identities (wrong fiscal code) → **Mitigation**: pre-validation and reconciliation view for HR.
* **Risk**: PII exposure via logs → **Mitigation**: strict redaction & minimization; field-level encryption where needed.
* **Risk**: Large batch uploads cause throttling → **Mitigation**: SQS buffering + exponential backoff; per-file idempotency keys.
* **Risk**: Employees without email → **Mitigation**: alternate contact bootstrap (temporary codes / HR-assisted activation).

## Success Metrics (early)

* **T₁**: % of payroll ingestions that **auto-provision** Cognito successfully.
* **T₂**: Median **upload-to-available** latency (P50/P95).
* **T₃**: % of employees using **self-service** monthly (MAU/eligible).
* **T₄**: **Zero** integrity mismatches between stored hash and download.
* **T₅**: **Error rate** on uploads (target < 1%) and **retry success** rate.

## Open Questions (to resolve in SPEC)

* Which backend runtime (Node.js vs Python) and DB (DynamoDB vs RDS) do we standardize on?
* Exact validation rules per document type (mime/size, naming convention).
* Retention, legal hold, and object lock requirements by document class.
* Employee activation UX (email vs HR-assisted enrollment; localization/i18n).
* Required reporting exports (CSV, dashboard) beyond the Stats tab.
* Access from mobile devices and MDM constraints (if any).

## Sources & Inspiration

* Internal domain brief and stakeholder requirements (HR/Administration).
* AWS reference architectures for secure serverless document ingestion and Cognito user management.
