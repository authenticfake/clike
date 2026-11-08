# CLike overlay — superpowers

How the vendored skills apply inside CLike. The upstream files stay as pinned (VENDORED.json); this
overlay is CLike's and comes first. Where the upstream text and this overlay differ, the overlay
wins.

## test-driven-development

### All executors

- The whole KIT is generated and runs headless: there is no human partner to ask; the "generated
  code" exception does not apply — every behaviour of the REQ gets its test.
- Tests first, complete source second: write the tests of every acceptance criterion and owned
  scenario, then the implementation that makes all of them pass. "Minimal code" means no code beyond
  the REQ; it never means leaving an acceptance criterion or scenario out.
- For each test, name the production change that would make it fail (a wrong message, a missing
  check, an off-by-one limit). A test that no plausible defect can fail proves nothing.
- Put the scenario id in the name or title of the test that proves it, one or two ids per test (see
  eval-contract-writer); a comment listing ids proves nothing.

### Cloud — one generation call

- You cannot run anything. Do not write "watch it fail", run logs or pass claims: the eval runs the
  tests and its result is the red/green signal.
- Emit the test files before the source files, and in `docs/KIT_<REQ-ID>.md` a table
  scenario or criterion → test → assertion → the defect it catches.

### Coding agent

- During the KIT: red-green per behaviour — write the test, run it, see it fail for the expected
  reason, implement, run it green, then run the REQ's whole suite.
- During an /eval repair the tests and `ci/` are locked: the failing eval check is the red. Repair
  the source; never delete working code to "start over" — read the failure, fix the cause, re-run.
- A test that is itself wrong is corrected without weakening its assertions (the eval governance
  reviews it).

## verification-before-completion

### All executors

- "Done" for a REQ means every criterion in `docs/ACCEPTANCE.json` is `done` with the blocking
  checks that verify it — the line-by-line checklist of the upstream skill is that file.
- Never report a result you did not observe.

### Cloud — one generation call

- You verify nothing at run time: mark checks "to be run by the eval", and set an ACCEPTANCE.json
  criterion `done` only when its tests and blocking case are in this KIT.

### Coding agent

- Before saying a REQ, a feature or a fix is done: run the checks of `ci/LTC.json` you touched and
  report the commands and their results.
