# IDEA — VibeRadio

## Vision
VibeRadio is an internal, company-only “micro-audio radio” that turns team updates, product news, shoutouts, and tips into short, snackable audio clips. Instead of long emails and heavy all-hands meetings, people can follow personalized playlists while they work, staying aligned with what matters without losing focus.

The experience should feel as playful and lightweight as a Silicon Valley startup app (channels, jingles, recurring shows, memes), while respecting the constraints of enterprise environments (on-prem deployment, data residency, compliance).

## Problem Statement
In many organizations, communication happens through long emails, large townhall meetings, and scattered Slack messages. This creates multiple issues:

- Important updates get lost in noisy channels or long threads.
- People cannot consume information at their own pace or in their preferred format.
- Leadership updates feel distant and formal, instead of frequent, authentic, and conversational.
- Large meetings are expensive and often not inclusive for distributed and hybrid teams.

Short-form internal podcasts and voice messages are emerging as a more natural medium, but typical solutions rely on public cloud services, external platforms, or ad-hoc usage of consumer tools. Regulated enterprises cannot simply push internal content to external SaaS or give up control over identity, access control, and data storage.

VibeRadio should provide a Slack-native, event-driven way to record, publish, and consume internal micro-audio content that is:

- Easy enough for any employee to use.
- Fun and engaging, encouraging recurring contributions.
- Secure, searchable, and manageable by enterprise IT and compliance teams.
- Deployable initially as a simple app and database, with a path to a scalable, on-prem architecture.

## Target Users & Context
- Primary users:
  - Team leads and managers who want to broadcast short updates to their teams.
  - Product managers and tech leads who want to share product changes, incident reviews, or roadmap highlights.
  - Internal communities (guilds, chapters, ERGs) that want recurring “shows”.
- Secondary users:
  - Employees who want a low-friction way to stay informed without attending many meetings.
  - Internal communications / HR teams who want to run recurring series (e.g., “New joiner spotlight”, “Policy explained in 60 seconds”).

Context:
- Slack enterprise workspace is the main entry point for interaction (recording, discovering, and playing content).
- Optional web UI for richer discovery, search, and playlists.
- Minimal deployment: one backend service, a relational database for metadata, and a simple object store for audio files.
- Optional enterprise deployment: on-prem Kubernetes, API gateway, centralized identity (OIDC), Kafka for events, and enterprise observability.

## Value & Outcomes
- Reduce the number and duration of synchronous all-hands and status meetings by offloading updates to micro-audio.
- Increase reach and engagement with leadership and team updates, as people can listen when it best fits their schedule.
- Create a fun, human communication layer with recurring shows, internal memes, and shoutouts that strengthen culture.
- Provide a central, searchable repository of internal audio content, respecting access control and data residency requirements.
- Offer a clear evolution path from a small pilot to an enterprise-scale platform without rewriting the core product concept.

## Out of Scope
- Public podcast publishing or external distribution of audio content.
- Advanced audio processing such as automatic transcription, translation, or AI voice cloning (these can be future extensions).
- Serving as a full replacement for the company intranet or all existing communication tools.
- Complex rights management for music or copyrighted content; VibeRadio is focused on internal spoken-word content and simple sounds or jingles.

## Technology Constraints
```yaml
tech_constraints:
  version: 1.0.0
  profiles:
    - name: minimal
      description: Minimal profile to support end-to-end VibeRadio in a small pilot.
      runtime: python
      platform: container
      api:
        - slack.events
        - rest
      storage:
        - postgres        # metadata: shows, episodes, playlists, permissions
        - object_store    # audio files (e.g., S3-compatible or filesystem)
      messaging: []
      auth: []
      observability: []
    - name: enterprise_onprem_optional
      description: Optional enterprise-grade profile for large-scale, regulated environments.
      runtime: python
      platform: kubernetes
      ingress: nginx
      api:
        - slack.events
        - rest
        - web.ui
      storage:
        - postgres
        - object_store
      messaging:
        - kafka
      auth:
        - oidc
      observability:
        - prometheus
        - grafana
  capabilities:
    - type: db.relational
      vendor: postgres
      params:
        ha: false          # minimal pilot
    - type: db.relational
      vendor: postgres
      params:
        ha: true           # optional enterprise
    - type: object.store
      vendor: s3_compatible
      params:
        encryption_at_rest: true
    - type: mq.stream
      vendor: apache.kafka
      params:
        partitions: 6
        optional: true
    - type: api.gateway
      vendor: Kong Gateway
      params:
        routes: internal-only
        optional: true
    - type: idp
      vendor: Ory Hydra
      params:
        oidc: true
        optional: true
    - type: secrets.manager
      vendor: hashicorp.vault
      params:
        optional: true
```

The minimal profile should be enough for a full end-to-end experience: record in Slack, store audio, publish episodes, and listen via Slack and a basic web endpoint. The enterprise profile simply adds reliability, scalability, and governance components without changing the core product behavior.

## Risks & Assumptions

Assumptions:
- Slack enterprise is already adopted and used as the primary chat and collaboration tool.
- Basic object storage is available internally (or via a restricted cloud account) for hosting audio files.
- Employees are allowed and willing to record short internal audio clips and share them with colleagues.

Risks:
- Some employees may be uncomfortable recording their voice or being recorded; VibeRadio must make participation voluntary and give fine-grained control over audience and visibility.
- Audio-only content can be less accessible for people with hearing impairments; mitigated by planning for transcription support or text summaries as a near-term extension.
- Storage and retention policies for audio may be unclear; mitigated by aligning with legal/compliance early and encoding retention rules into the platform (automatic expiry, archiving, and deletion).
- Slack and audio storage limits could become a bottleneck if the platform grows quickly; mitigated by retaining only recent content by default and archiving older episodes to cold storage as necessary.

## Success Metrics (early)
- Number of active shows (recurring audio series) created and maintained over time.
- Percentage of employees who listen to at least one episode per week in the pilot groups.
- Reduction in duration or frequency of specific status meetings converted to VibeRadio episodes.
- Qualitative feedback from internal comms and team leads about clarity, reach, and cultural impact.

## Sources & Inspiration
- Public podcast and short-form audio platforms, adapted for internal, private, enterprise-only usage.
- The rise of async communication patterns in distributed teams (voice notes, asynchronous standups, internal podcasts).
- Existing standards and patterns from the Clike / Harper methodology for structuring IDEA → SPEC → PLAN → KIT in an evolvable, testable way.
