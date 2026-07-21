# Adaptive Discovery Interview

## Contents

- [Purpose](#purpose)
- [Interview Order](#interview-order)
- [Project Vision](#project-vision)
- [Experience Profile](#experience-profile)
- [Existing Hardware and Resources](#existing-hardware-and-resources)
- [Constraints and Preferences](#constraints-and-preferences)
- [Batch Examples](#batch-examples)
- [Requirements Confirmation](#requirements-confirmation)

## Purpose

Discover enough evidence to choose a project-specific architecture and first phase without overwhelming the user. Ask one to three related questions at a time and reuse everything already answered in conversation, files, inventory, images, labels, or datasheets.

## Interview Order

Use this order as a decision guide, not a fixed questionnaire:

1. Establish the robot's purpose and form.
2. Identify the user, operating environment, and definition of finished.
3. Assess experience by discipline.
4. Inventory owned hardware, tools, fabrication access, and computer environment.
5. Establish budget, location, schedule, workspace, and retailer preferences.
6. Identify privacy, connectivity, power, movement, and autonomy constraints.
7. Resolve contradictions and high-impact unknowns.

Skip topics that cannot affect the current decision. Revisit them only when a later phase makes them relevant.

## Project Vision

Discover:

- what the robot should do and who will use it;
- the problem, experience, artwork, research question, product intent, or learning goal;
- whether it is stationary, desk-scale, wearable, wheeled, walking, flying, underwater, arm-based, soft, or another form;
- the operating environment, including people, pets, water, dust, stairs, public spaces, temperature, and lighting;
- desired size, weight, appearance, materials, portability, noise, and interaction methods;
- essential, optional, and aspirational features;
- expected reliability and acceptable failure behavior;
- what a finished result means to the user.

Ask for measurable examples when words such as small, fast, autonomous, cheap, safe, or reliable would materially affect the design.

## Experience Profile

Assess these areas separately:

- general programming and preferred languages;
- web, backend, mobile, AI, and computer vision;
- electronics and breadboards;
- reading wiring diagrams;
- microcontrollers and single-board computers;
- sensors, motors, servos, and motor drivers;
- power supplies, batteries, voltage, and current;
- soldering and multimeter use;
- CAD, mechanical design, 3D printing, and fabrication;
- robotics debugging and safety.

Never infer electronics, power, mechanical, or safety experience from software experience.

Adapt the plan from the weakest safety-relevant area:

| Evidence | Adaptation |
| --- | --- |
| First-time electronics user | Use preassembled modules, avoid soldering where possible, teach one concept per lab, and add frequent inspection gates. |
| Software expert but hardware beginner | Keep software explanations compact while retaining full wiring, power, and mechanical teaching. |
| Experienced hardware builder | Use concise terminology but still require ratings, compatibility evidence, and physical safety gates. |
| Unknown experience | Start conservatively and ask one focused experience question before physical work. |

## Existing Hardware and Resources

Ask what the user owns or can access only when relevant:

- computer and operating system;
- microcontrollers and single-board computers;
- motors, servos, drivers, sensors, cameras, microphones, displays, speakers, and radios;
- breadboards, wires, resistors, LEDs, buttons, connectors, and protection components;
- regulated power supplies, batteries, and chargers;
- multimeter, soldering equipment, and hand tools;
- 3D printer, laser cutter, CNC machine, workshop, materials, and fasteners.

Request exact model numbers, photos, labels, connector colors, datasheets, dimensions, and voltage/current ratings when compatibility depends on them.

Classify inventory as:

- **Confirmed owned:** exact identity and relevant ratings are known.
- **Reported, not identified:** the user says it exists but details are insufficient.
- **Needed:** required by an approved roadmap phase.
- **Optional:** useful but not required.
- **Incompatible or unsafe:** evidence shows it should not be used in the planned configuration.
- **Replacement candidate:** a safer or more compatible alternative needs research.

Never silently promote uncertain hardware into confirmed inventory.

## Constraints and Preferences

Discover when relevant:

- country, city, currency, total budget, and per-phase budget;
- timeline and delivery restrictions;
- preferred retailers and whether used parts are acceptable;
- workspace size, ventilation, noise, tools, and supervision;
- size, weight, materials, portability, and appearance;
- internet availability and offline requirements;
- privacy, data retention, camera, microphone, location, and cloud-AI preferences;
- autonomous movement, battery operation, and expected runtime;
- preferred technology and learning goals;
- manual subsystem construction versus ready-made modules.

If the builder or operator may be a minor, record the responsible adult and require that adult's supervision and approval before battery, tool, power, actuator, or movement gates.

Always ask for preferred hardware retailers before sourcing. If the user names none, record Robotistan as the default research source. If Robotistan cannot ship to the user or lacks a compatible part, explain the limitation and ask before changing the primary retailer.

## Batch Examples

Start with vision:

1. What should the robot do in its first useful version?
2. Where will it operate, and who or what will be nearby?
3. Is this mainly a learning project, prototype, artwork, research platform, or intended product?

Then ask a focused experience batch:

1. How comfortable are you with programming?
2. Separately, have you used a breadboard, multimeter, motor, or servo before?

Explain why a question matters when a beginner may not know. Example: ask about pets or children because reachable moving parts require different guarding and force limits.

## Requirements Confirmation

Summarize:

- confirmed decisions;
- assumptions;
- open questions;
- deferred ideas;
- contradictions or safety concerns;
- the proposed first proof and why it is low risk.

Ask for confirmation only when an incorrect assumption would materially change cost, architecture, safety, privacy, purchasing, or the roadmap's first phase. Do not ask the user to re-confirm every answer.
