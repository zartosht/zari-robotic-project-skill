# Beginner Hardware Guidance

## Calibrate the Teaching Level

Use first-time-touching-the-parts instructions when the user is new to electronics, power, fabrication, or robotics. Keep software explanations compact for experienced programmers, but do not shorten safety-critical physical instructions.

Teach one new risk-bearing concept at a time. Prefer preassembled modules, reversible connections, low energy, no soldering, and no movement until the user demonstrates the required understanding.

## Define Terms at First Use

Explain as needed:

- **Voltage:** electrical potential difference that pushes charge through a circuit.
- **Current:** the flow of electric charge; components and wires have current limits.
- **GND (ground):** the shared electrical reference and return path, not automatically earth ground.
- **Signal:** information carried by a voltage or pulse; a signal pin is not an actuator power source.
- **Resistor:** a component that limits current or sets a voltage relationship.
- **Series:** components connected in one current path.
- **Anode and cathode:** direction-sensitive LED terminals; identify their physical markings.
- **Polarity:** which terminal is positive and which is negative.
- **Common ground:** two powered systems sharing the same electrical reference where required for signals.

Explain which parts are direction-sensitive and which can safely be flipped.

## Structure Every Physical Lab

Include:

1. a single bounded goal;
2. exact parts and quantities;
3. exact tools;
4. what each part does;
5. prerequisites and approval gates;
6. the disconnected-power starting state;
7. exact pins, connectors, wire colors, and endpoints;
8. an ordered wiring or assembly table;
9. what should be visible, felt, heard, or measured after important steps;
10. a pre-power inspection;
11. explicit permission before power or movement;
12. stop conditions;
13. common mistakes and safe recovery;
14. an acceptance checklist;
15. what not to add next.

State when USB, external power, batteries, and chargers must be disconnected. Never ask the user to change wiring while powered.

For multimeter use, name the exact lead jacks and mode before every measurement. Use resistance or continuity only after verifying the circuit is unpowered and discharged. Never place a meter configured for current measurement directly across a supply. Avoid novice current measurements unless a fused series setup, expected range, lead placement, and qualified supervision are fully documented.

## Describe Breadboards Exactly

Before using a breadboard, explain:

- side power rails versus middle terminal strips;
- that `+` and `-` are labels, not powered sources;
- that rails are separate from controller `5V`, `3.3V`, and `GND` until wired;
- the center gap and separate connected groups on each side;
- possible split power rails that are not connected across the full board.

Name complete connected groups, such as `A10-E10` and `F10-J10`. Never say only “put it in row 10.” State whether a hole is a power rail or a middle strip and which side of the center gap to use.

When breadboard labels differ, explain the electrical relationship the user must preserve instead of treating example coordinates as magic.

## Give Observable Checkpoints

After every consequential step, say what confirms success. Examples:

- a continuity measurement within an expected range;
- a status LED state;
- a stable serial value;
- no heat or odor after a short, supervised interval;
- a mechanism moving freely by hand while unpowered;
- a single bounded no-load movement followed by a stop.

Do not continue when the observation differs. Give a power-off recovery path before troubleshooting wiring.

## Use Learning Gates

Before higher-risk phases, confirm the user can explain the relevant concept in their own words. Possible checks include:

- why an actuator signal pin cannot supply actuator power;
- why peak or stall current matters;
- why a shared signal may need common ground;
- how to remove power immediately;
- what motion, heat, or sound means the test must stop;
- which data a camera or microphone would retain or transmit.

Teach the unclear concept and re-check it. Do not use a quiz as ceremony when the evidence is already clear.

## Avoid Ambiguous Instructions

Do not write:

- “wire it normally”;
- “connect power” without naming voltage, source, polarity, and endpoint;
- “use a suitable resistor/driver/supply” without a verified selection method;
- “test the motor” without no-load state, bounds, stop method, and approval;
- “plug it in and see”;
- “the red wire is always positive” without checking the actual part.

If labels, colors, pinouts, or ratings are uncertain, stop and request evidence.
