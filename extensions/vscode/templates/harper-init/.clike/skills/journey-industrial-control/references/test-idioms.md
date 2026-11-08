# Test idioms: industrial control

Every check runs against simulated I/O or a protocol simulator, with scripted faults and virtual time.

## PLC / SCADA (IEC 61131-3)

- The eval sandbox has no vendor runtime: the blocking check runs the logic on a portable Structured Text runner or a simulator model of the function blocks (or the supervisory code against a protocol simulator); the IDE test (TcUnit, CODESYS Test Manager) is a non-blocking case with `environment_requirements` naming the runtime.
- Test names carry the scenario id with underscores (`IND_04_CommLossSafeState`): hyphens are not valid in IEC 61131-3 identifiers.
- Unit tests in the controller environment: TcUnit (TwinCAT), CODESYS Test Manager or equivalent; one test suite per function block.
- Simulated I/O: map inputs to test variables; force interlock inputs, frozen values, out-of-range analogs; step cycles and assert outputs.
- Alarms: assert alarm raised, priority, text, acknowledge, clear-after-normal according to the alarm philosophy (for example ISA-18.2 states).
- Emergency stop and power loss: simulate the input drop and a cold/warm restart; assert outputs at safe state and start inhibit until reset.
- Mode changes: manual/auto transitions with bumpless transfer asserted on the controller output.
- Virtual commissioning or a digital twin for sequence-level journeys when available.

## Protocol simulators

- OPC UA: a local simulation server (for example open62541-based or a vendor-neutral simulator) to publish values, set bad quality, stop updating (stale) and drop sessions.
- Modbus: a simulator slave to return exceptions, timeouts and wrong values.
- MQTT: a local broker; publish retained stale values, disconnect the publisher, assert last-will handling.

## Python (supervisory, edge, gateways)

- pytest with an OPC UA client against a local simulation server or an in-process fake device; `freezegun` or an injected clock for staleness windows.
- Assert safe-state writes, alarm records and that stale or bad-quality values are excluded from control decisions.

## TypeScript (HMI, web SCADA)

- vitest + Testing Library for screen states: comm loss banner, invalid value marker, interlock reason text, mode indicator.
- Playwright journeys against the HMI with a simulator backend: issue a blocked command and assert the interlock message; log in at an insufficient level and assert rejection.

## .NET

- xUnit with an OPC UA client against a simulator; `FakeTimeProvider` for timeouts and staleness.
- HMI journeys with Playwright .NET or UI automation for desktop HMIs.

## Java

- JUnit 5 with a simulator client (for example Eclipse Milo against a local server); Awaitility with bounded waits for reaction time budgets.

## Backend services

- Command APIs tested for authorization level, interlock rejection message and audit entry (actor, command, value, result).
- Never point automated tests at real controller addresses; configuration for tests uses simulator endpoints only.
