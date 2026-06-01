# Future TEA

TEA is a future roadmap item. It is not implemented in the current BMAD-aware methodology profile integration.

The governing principle is simple: TEA can recommend. CLike decides.

Future TEA support may provide structured recommendations for reasoning, evidence, traceability, assumptions, risks, and tradeoffs across Harper phases. It may help explain why a requirement is ready, why a repair is likely, or which evidence supports a planning decision.

TEA must remain advisory. It must not become a hidden gate override, an alternate EvalRunner, a promotion path, or a way to mutate canonical artifacts outside CLike governance.

## Possible Direction

Future TEA support may help with:

- traceable decisions
- explicit assumptions
- evidence-backed acceptance criteria
- risk and tradeoff records
- stronger audit links between generated artifacts and source context
- recommended follow-up questions
- advisory repair reasoning after eval

## Current Boundary

Current CLike behavior remains:

- Harper phases are CLike-governed
- EvalRunner is authoritative for eval
- gate is CLike-only
- BMAD roles provide methodology guidance only
- no TEA runtime is implemented

Any future TEA work must preserve canonical eval/gate authority and must not add a parallel Harper pipeline.
