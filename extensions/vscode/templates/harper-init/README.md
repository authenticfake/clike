# ${project.name} — Harper Vibe Coding (CLike)

## What is Harper
Harper is an outcome-driven, AI-native workflow: IDEA → SPEC → PLAN → KIT → BUILD → FINALIZE.
- Human = orchestrator/validator. AI = executor.
- Core docs live in \`docs/harper/\` and are **always** part of the model context.

## How to use CLike in VS Code
- Open the **CLike Chat** panel. Use \`/help\` to see commands.
- Modes: *harper* (planning/generation), *coding* (implementation), *free* (Q&A).
- Commands:
  - \`/spec\`: generate/update SPEC from IDEA.
  - \`/plan\`: generate/update PLAN from SPEC.
  - \`/kit\`, \`/build\`: implement & test in short loops.
  - \`/finalize\`: final gates & report.
  - \`/eval <spec|plan|kit|finalize>\`: Performs an eval of spec/plan/kit/finalize.
  - \`/gate <spec|plan|kit|finalize>\`: Performs a gate of spec/plan|kit|finalize. 
  - \`/syncConstraints [path]\`: Syncs Technology Constraints from IDEA/SPEC, regenerates canonical JSON.
  - \`/planUpdate [REQ-ID] [runs/.../eval/kit.report.json]\`: Checks off the PLAN item after a passing KIT eval.
  - \`/rag <query>\`: Searches the RAG (shows top results) (cross).
  - \`/rag list\`: Shows current attached files (inline+RAG) (cross).
  - \`/rag +<N>\`: Adds RAG result #N from the last search to the attached files (cross).
  - \`/ragIndex [glob]\`: Manually indexes into the RAG. Examples: /ragIndex docs.
  - \`/ragSearch <query>\`: Searches the RAG and shows the best results in the Texts panel.

## Project layout
\`\`\`
docs/harper/
  PLAYBOOK.md   # how to fill IDEA/SPEC, gates & commands
  IDEA.md       # business/tech idea (human+assistant)
  SPEC.md       # system specification (human+assistant)
runs/           # manifests, diffs, test logs
.clike/         # project config & policy
\`\`\`

## GitHub workflow (recommended)
1. \`git init\`; first commit (bootstrap).
2. Create a repo on GitHub, then:
   \`git remote add origin <your-repo-url>\`
   \`git push -u origin main\`
3. SPEC approved (Gate G0) → tag/annotate.
4. PLAN approved (Gate G1) → feature branches, PRs, CI checks.
5. KIT/BUILD cycles → PR with tests and quality gates.
6. FINALIZE → tag release (e.g., \`v0.1.0\`) + FINAL_REPORT.md.

## Next steps
Init ${project.name} gith repository
1. git init
2. git add .
3. git commit -m "chore(init): bootstrap Harper workspace from CLike template"
4. git branch -M main
5. git remote add origin <git@github.com:org/repo.git>
6. git push -u origin main
Start ${project.name} harper approach
7. Open \`docs/harper/IDEA.md\` and complete it.
8. Run \`/spec\` to generate \`SPEC.md\`.
9. Review SPEC, then run \`/plan\`.
10. Start \`/kit\` /\`/build\` cycles, verify gates, iterate.

> Attachments in CLike are **supportive** only. Core docs from \`docs/harper/\` are **always** included in context.