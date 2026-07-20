# Roadmap Selection

## Contents

- [Choose the Safest Useful Proof](#choose-the-safest-useful-proof)
- [Candidate Starting Phases](#candidate-starting-phases)
- [Scenario Guidance](#scenario-guidance)
- [Build the Roadmap](#build-the-roadmap)
- [Begin the Selected Phase](#begin-the-selected-phase)

## Choose the Safest Useful Proof

Let the roadmap, not a fixed template, choose the starting phase. Select the smallest phase that can disprove a major assumption, teach a required skill, or demonstrate the core experience without crossing an avoidable safety or privacy boundary.

Do not select a phase until the robot's intended behavior or learning goal, operating environment, project purpose, definition of finished, and enough safety-relevant user/inventory constraints are known. Ask rather than inventing a generic proof when those facts are absent.

Score candidate phases against:

- energy, force, speed, heat, stored energy, and tool risk;
- uncertainty in power, polarity, current, mechanics, or compatibility;
- user experience in the weakest relevant discipline;
- reversibility and cost;
- privacy and sensitive-data exposure;
- ability to test deterministically;
- dependence on unavailable hardware or research;
- value of the evidence produced.

Prefer lower-risk evidence when two phases answer the same question.

## Candidate Starting Phases

- requirements and simulation;
- software-only interaction prototype;
- mock robot interface or protocol;
- CAD study or cardboard mechanical mockup;
- sensor-only bench experiment;
- LED or button electronics lab;
- single-servo no-load lab after power compatibility is verified;
- motor-driver bench test without a mobile chassis;
- small stationary desk prototype.

Do not force software first. A cardboard reach study, sensor measurement, or low-energy electronics lesson may be the better proof.

## Scenario Guidance

| Situation | Sensible first phase |
| --- | --- |
| Beginner, no hardware, low-cost desk robot | Confirm scope, create a mock interaction or paper/cardboard study, and research a minimal compatible starter set. |
| Experienced developer with known environmental sensors | Verify exact inventory, then begin a sensor-only bench or mock telemetry phase. |
| Robotic arm with uncertain motors or supply | Stop at identification, load/torque estimates, power research, and a no-power mechanical study. |
| Walking AI robot requested as version one | Preserve the long-term goal but start with simulation, stability analysis, or a stationary expressive prototype. |
| Camera, microphone, cloud AI, and autonomy requested | Start with disabled-by-default settings, mock data, retention decisions, and deterministic command boundaries. |
| Non-empty project | Integrate the smallest phase into existing conventions; do not replace the structure automatically. |

## Build the Roadmap

For every phase record:

- **Goal:** the question or capability proven.
- **Prerequisites:** knowledge, inventory, decisions, and verified compatibility.
- **Scope:** concrete outputs.
- **Non-goals:** attractive work explicitly deferred.
- **Acceptance:** observable evidence required to finish.
- **Safety/privacy gates:** approvals and stop conditions.
- **Budget:** phase limit and uncertain cost.
- **Exit evidence:** measurements, test output, photos, or review notes.

For a learning-purpose project, also record:

- **Competency:** what the learner should understand or perform independently.
- **Prerequisite concept:** knowledge required before the guided exercise.
- **Mastery evidence:** an explanation, reconstruction, measurement, or independent task rather than passive completion.
- **Misconception and remediation:** a likely mistake, teaching response, and retry condition.

Keep advanced features out of earlier phases until their prerequisites pass. Examples include multi-actuator systems, floor movement, walking, high-current motors, battery packs, mains power, always-listening microphones, camera autonomy, and cloud retention.

## Begin the Selected Phase

Begin immediately when work is reversible and does not cross a mandatory gate. Appropriate work includes:

- creating project documents and architecture boundaries;
- implementing mocks, simulations, schemas, and unit tests;
- writing firmware that will not be uploaded yet;
- creating a detailed wiring or mechanical plan;
- preparing a sourcing matrix or verification checklist.

If the selected phase reaches a gate, finish the safe preparation and stop at the exact boundary. State the evidence or confirmation needed next.

Do not mark a physical phase complete from a compile, document, simulation, retailer page, or unobserved assumption. Require the phase's acceptance evidence.
