# Validation

## Contents

- [Validate the Scaffold](#validate-the-scaffold)
- [Validate Requirements and Architecture](#validate-requirements-and-architecture)
- [Validate Hardware Evidence](#validate-hardware-evidence)
- [Validate Software and Firmware](#validate-software-and-firmware)
- [Validate Safety and Privacy](#validate-safety-and-privacy)
- [Validate the First Phase](#validate-the-first-phase)
- [Use Independent Review When Available](#use-independent-review-when-available)
- [Report the Result](#report-the-result)

## Validate the Scaffold

Confirm:

- every created file serves the selected project;
- existing work and conventions are preserved;
- confirmed facts, assumptions, open questions, and deferred ideas remain distinct;
- the roadmap selected the first phase;
- the next action is easy to find and executable at the user's experience level;
- no empty placeholders, credentials, private data, or machine-specific paths remain.

## Validate Requirements and Architecture

Trace essential requirements to a phase, output, and acceptance criterion. Check that subsystem boundaries match the actual robot rather than a preferred stack.

For AI-controlled systems, verify that proposed intent cannot bypass deterministic validation or firmware safety enforcement.

## Validate Hardware Evidence

For every recommended or connected part, verify:

- exact identity and revision;
- source date and direct evidence URL;
- voltage, current, logic, polarity, connector, and driver requirements;
- mechanical fit and load assumptions;
- included and missing accessories;
- compatibility verdict and unresolved blockers.

Do not accept a retailer listing as proof of system compatibility. Do not accept physical connector fit as electrical compatibility.

## Validate Software and Firmware

Run proportionate checks such as:

- schema and unit tests;
- rejection tests for malformed, stale, unauthorized, and out-of-range commands;
- watchdog, safe-start, disconnect, and fault-state tests;
- for hazardous motion, independent-supervisor, controller-hang, stalled-loop, stale-sensor, driver-enable fail-safe, brownout, and reboot-without-resume tests;
- simulation or mock end-to-end tests;
- firmware compilation for the exact board target;
- static checks for secrets and accidental agent-specific assumptions.

A firmware compile proves only that the source compiled for the selected target. It does not prove wiring, power, timing under load, mechanical safety, or physical movement.

Keep hardware-in-the-loop tests opt-in, clearly labeled, and gated. Never make a routine test command move hardware unexpectedly.

## Validate Safety and Privacy

Check:

- all mandatory approval gates are explicit;
- stop conditions and recovery steps exist;
- power and current assumptions are evidence-backed;
- physical movement has bounded speed, force, range, duration, and a stop method;
- motion capable of injury or material property damage has an independent reachable, latching physical stop or power/enable cut-off, a defined coast/brake/hold state, manual reset, deliberate re-arm, and no automatic restart;
- batteries and dangerous tools receive appropriate warnings and supervision requirements;
- cameras, microphones, cloud processing, location, autonomy, and retention default to disabled or privacy-preserving behavior;
- credentials stay outside tracked files.

## Validate the First Phase

Use observable acceptance evidence. Depending on the phase, this may be:

- passing automated tests;
- a reproducible simulation trace;
- a measured dimension or load estimate;
- a reviewed wiring plan with all ratings resolved;
- a sensor reading under documented conditions;
- a single approved physical test with recorded stop behavior.

Do not mark the phase complete when required evidence is missing. Record the exact blocker and the next safe action.

## Use Independent Review When Available

Give isolated reviewers the raw project artifacts and scenario, not the expected answer or prior diagnosis. Ask them to check safety, portability, sourcing evidence, beginner clarity, and whether the roadmap starts sensibly. Fix substantive findings and rerun affected checks.

## Report the Result

Use:

### What Changed

List changed files and their purpose.

### How It Works

Explain the main flow and abstractions.

### Why This Shape

Explain project-specific choices, tradeoffs, and deferred work.

### How To Verify

List commands, automated tests, manual checks, and the evidence actually observed.

### Follow-Up Risks

List unresolved assumptions, sourcing volatility, hardware-dependent gaps, and approval gates.

### Safety Impact

Include for firmware, electronics, movement, sensors, power, batteries, autonomy, cameras, microphones, networking, privacy, or credentials. State what remains disabled and which actions still require approval.
