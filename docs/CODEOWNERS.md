# CODEOWNERS — Governance for Harper approach (SPEC/PLAN/KIT/BUILD) and platform
# Replace @your-org/... with your actual GitHub teams or users.

# SPEC / PLAN (G0 / G1 gates)
/docs/harper/IDEA.md                        @your-org/product-owners
/docs/harper/SPEC.md                        @your-org/product-owners @your-org/system-architects
/docs/harper/PLAN.md                        @your-org/system-architects

# Runtime code & pipelines (KIT/BUILD)
/orchestrator/**                            @your-org/platform-engineering
/gateway/**                                 @your-org/platform-engineering
/src/**                                     @your-org/swe-core @your-org/qa-leads
/extensions/**                              @your-org/swe-core

# Platform, CI/CD, security
/.github/**                                 @your-org/devops @your-org/secops
/configs/**                                 @your-org/devops

# Default fallback owners (catch-all)
*                                           @your-org/swe-core
