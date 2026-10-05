# IDEA — ShortLink

## Vision
A small internal URL shortener with a web page to create links and a redirect endpoint.

## Problem Statement
The team shares long internal URLs (dashboards, runbooks) in chat and documents; they are hard to read and to type.

## Target Users & Context
Up to 50 employees on the internal network; links are created from a browser.

## Value & Outcomes
Short, memorable links; one place to see which links exist and how often they are used.

## Out of Scope
Authentication, custom domains, link expiry, analytics beyond a click counter.

## Technology Constraints
```yaml
tech_constraints:
  backend:
    runtime: python
    version: "3.12"
    framework: fastapi
    storage: sqlite
  frontend:
    kind: static web page
    language: javascript
    framework: none
```

## Risks & Assumptions
Single instance; SQLite is enough for the expected volume; short codes are 6 characters.

## Success Metrics
A link can be created from the web page in under 10 seconds; the redirect answers in under 50 ms locally.
