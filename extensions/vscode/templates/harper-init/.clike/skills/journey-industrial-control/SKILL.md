---
name: journey-industrial-control
description: Use when software commands or supervises machines, lines or plants (PLC, SCADA, HMI, edge, robotics), to enumerate and prove the control scenarios (interlocks, alarms, emergency stop, communication loss, bad sensors, manual mode, safe restart) on a simulator.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["backend", "industrial", "plc-scada", "python", "typescript", "dotnet", "java"]
domains: ["industrial", "manufacturing", "energy", "utilities", "automotive", "logistics"]
runtime_profiles: ["local", "cloud", "local-cloud", "on-prem", "hybrid", "air-gapped", "edge"]
gate_required: true
scenario_prefix: IND
scenarios:
  - IND-01 | required | Interlock prevents unsafe command | If an operator or system issues a command while an interlock condition is active, then the system shall refuse the command, keep the equipment in its current safe state and show which interlock blocked it.
  - IND-02 | required | Fault and alarm lifecycle | When a fault condition occurs, the system shall raise an alarm with priority, timestamp and text, require acknowledgement, and clear it only when the condition is gone and acknowledged according to the alarm philosophy.
  - IND-03 | required | Emergency stop | When an emergency stop is triggered, the system shall bring the controlled equipment to the defined safe state, block restart until the stop is reset deliberately, and record the event.
  - IND-04 | required | Communication loss with field device | If communication with a field device or controller is lost, then the system shall drive affected outputs to their defined safe state, raise a communication alarm and mark values as not current.
  - IND-05 | required | Sensor out of range or stale | If a sensor value is out of range, has bad quality or has not updated within its expected period, then the system shall not use it for control decisions, raise an alarm and show the value as invalid.
  - IND-06 | required | Manual override and return to auto | When an authorized operator switches to manual and back to automatic, the system shall perform a bumpless transfer, show the active mode clearly and log both transitions.
  - IND-07 | required | Safe start after power loss | When power or the controller is restored after a loss, the system shall start in a defined safe state and not resume motion or dosing without an explicit operator start.
  - IND-08 | required | Operator authorization for critical commands | If a user without the required authorization level issues a critical command (setpoint change, start, override, bypass), then the system shall reject it and log the attempt with the user identity.
  - IND-09 | required | Simulator-based verification | When control logic is verified, the system shall be exercised against a simulator or simulated I/O covering these scenarios, with no connection to a real plant in automated tests.
  - IND-10 | conditional | [Interlock bypass allowed] Bypass with authorization and expiry | When an authorized user bypasses an interlock, the system shall require a reason, show the bypass prominently, log it and remove it automatically at expiry.
  - IND-11 | conditional | [Setpoints or recipes editable] Setpoint limits | If an entered setpoint or recipe value is outside engineering limits, then the system shall reject it with the allowed range and keep the active value.
obligations:
  - Enumerate every IND scenario in SPEC and include it or exclude it with a written reason
  - Map each included scenario ID to a REQ in plan.json and to an acceptance item prefixed with the ID
  - Prove each included scenario with one blocking check against a simulator recorded in docs/ACCEPTANCE.json
  - Define the safe state of every controlled output explicitly in SPEC
  - Keep certified safety functions in the certified safety system; software scenarios prove monitoring and reaction, not certification
eval_checks:
  - scenario-coverage
  - simulator-evidence-present
  - safe-state-asserted
gate_implications:
  - block-if-included-scenario-unproven
  - block-if-tests-touch-real-plant
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
  - Simulator or simulated I/O configuration used by the checks
  - Exclusion reasons in SPEC for every scenario not included
---

# Journey: Industrial Control

## Intent

Control software is judged by what happens when things go wrong: a blocked interlock, a lost link, a frozen sensor, a power cut, an unauthorized command. This skill makes each of these an explicit scenario with a defined safe state and simulator proof. It complements industrial-safety-simulator with traceable scenario IDs.

## Use when

- Use cases or REQs mention PLC, SCADA, HMI, DCS, controller, machine, line, cell, robot, conveyor, pump, valve, motor, drive, alarm, interlock, setpoint, recipe, OPC UA, Modbus, Profinet, EtherNet/IP, MQTT telemetry, edge gateway, digital twin.
- Software writes to actuators or supervises equipment state.

## Do not use when

The REQ commands or monitors no physical process, device or field bus (office software, pure analytics on historical data).

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; include each `required` one or exclude it with a reason; define safe states per output.
- **PLAN**: assign each included scenario ID to one owning REQ in plan.json `scenarios`; add acceptance items prefixed with the ID (for example `IND-04: on OPC UA link loss for 2 s, the pump output goes to OFF and alarm COMM_P101 is raised`).
- **KIT**: one blocking check per included scenario against a simulator, recorded in docs/ACCEPTANCE.json with the scenario ID.
- **EVAL / GATE**: an included scenario without a passing blocking check blocks promotion; any test that needs a real plant blocks promotion.

## Valid exclusions

- Read-only monitoring with no write path to equipment: IND-01, IND-03, IND-06, IND-07 excluded; IND-02, IND-04, IND-05 remain.
- Emergency stop wholly in a certified hardwired safety system: IND-03 reduced to "software detects and displays the stop and blocks its own commands", still tested.
- No manual mode exists: IND-06 excluded with that reason.
- Not a valid reason: "tested on site during commissioning" as the only evidence.

## Proof per scenario

- Run logic against simulated I/O or a protocol simulator (OPC UA, Modbus) with scripted fault injection: link drop, frozen value, out-of-range value, power cycle.
- Assert output states (the defined safe state), alarm entries (ID, priority, text, ack state) and HMI-visible text.
- Use cycle-stepped or virtual time; assert reaction within the stated time budget.
- Authorization: issue critical commands as insufficient and sufficient levels; assert rejection and the audit entry.
- Restart: simulate power loss mid-operation; assert safe start and no automatic resume.

## Forbidden

- Happy-path sequences only.
- Automated tests connected to real equipment or a production network.
- Mocking the interlock or alarm logic in the test that claims to prove it.
- Undefined or implicit safe states.
- Claiming safety certification from software tests.
- Alarms that clear without acknowledgement when the philosophy requires it.

## References

- references/test-idioms.md
