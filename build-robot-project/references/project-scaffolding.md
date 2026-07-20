# Project Scaffolding

## Contents

- [Inspect Before Creating](#inspect-before-creating)
- [Select Files by Need](#select-files-by-need)
- [Suggested Artifact Map](#suggested-artifact-map)
- [Use Templates Selectively](#use-templates-selectively)
- [Begin the First Phase](#begin-the-first-phase)
- [Make the Next Action Obvious](#make-the-next-action-obvious)
- [Keep the Scaffold Honest](#keep-the-scaffold-honest)

## Inspect Before Creating

Determine whether the target is empty, an early planning folder, or an established project. Inspect existing documentation, source code, build tools, naming conventions, repository state, and local instructions.

If the project is not empty:

- preserve existing structure and terminology;
- avoid overwriting or renaming files;
- identify overlapping documents and merge only with clear authority;
- report conflicts and ask before a material restructure;
- keep unrelated changes untouched.

Do not create or modify files until the available evidence establishes, at minimum:

- the intended robot behavior or learning goal;
- operating environment and nearby people, animals, or hazards;
- project purpose and definition of finished;
- enough safety-relevant experience, inventory, budget, workspace, and privacy information to choose the first phase.

When these facts are missing, ask the next small interview batch and leave the project unchanged. Do not infer a sensor project, actuator project, companion app, simulation, or programming language from existing source files.

Honor explicit read-only, interview-only, research-only, or planning-only requests. Produce the permitted result without files or implementation and ask for separate authorization before changing scope.

## Select Files by Need

Create only artifacts that support the confirmed robot and selected roadmap. Possible artifacts include:

- project overview and confirmed requirements;
- architecture and subsystem boundaries;
- phased roadmap;
- hardware inventory and identification queue;
- sourcing research and compatibility matrix;
- software, firmware, electronics, and mechanical plans;
- safety and privacy plans;
- testing and acceptance strategy;
- learning path;
- decision and assumption logs;
- an exact next-step walkthrough;
- implementation code and tests for the selected first phase.

Do not force a web app, backend, mobile app, AI service, firmware folder, CAD folder, or a particular language/controller into every project.

## Suggested Artifact Map

Use this map only when each file is justified:

| Need | Possible artifact |
| --- | --- |
| Shared intent and scope | `docs/project-brief.md` |
| System boundaries | `docs/architecture.md` |
| Phase order and gates | `docs/roadmap.md` |
| Owned and unknown parts | `hardware/inventory.md` |
| Compatibility evidence | `hardware/compatibility.md` |
| Retailer research | `hardware/sourcing.md` |
| Physical hazards and approvals | `docs/safety-plan.md` |
| Media, cloud, and retention decisions | `docs/privacy-plan.md` |
| Observable completion evidence | `docs/testing-plan.md` |
| First actionable instruction | `docs/next-step.md` |

Use existing names when the project already has equivalent files.

## Use Templates Selectively

Copy and adapt only helpful templates from `assets/templates/`. Replace prompts with confirmed facts, explicit assumptions, or `Unresolved` labels. Delete irrelevant sections instead of leaving empty boilerplate.

Keep these distinctions visible:

- confirmed requirement versus assumption;
- owned exact part versus reported unknown part;
- compatible versus conditional versus unverified;
- accepted phase versus planned phase;
- safe automatic work versus approval-gated action.

## Begin the First Phase

Let the roadmap choose the starting phase. Implement the smallest coherent slice that produces evidence. Examples:

- a mock command contract and rejection tests;
- a simple simulation or state machine;
- a cardboard or CAD dimension study;
- a sensor logging experiment plan;
- non-uploaded firmware plus compile instructions;
- an exact low-energy wiring walkthrough;
- a compatibility research matrix that blocks unsafe purchasing.

Do not implement an example merely to make progress. The chosen slice must trace to the confirmed brief and roadmap.

Do not cross purchasing, power, movement, privacy, dangerous-tool, or unresolved-compatibility gates automatically.

## Make the Next Action Obvious

Create or identify one canonical next-action file or section. It must say:

- what the user will accomplish;
- required parts and tools;
- prerequisites and approvals;
- exact ordered steps;
- expected evidence after key steps;
- stop conditions and recovery;
- acceptance checklist;
- what remains forbidden afterward.

Do not hide the next hands-on step inside a history, status, or acceptance recap.

## Keep the Scaffold Honest

- Do not create empty directories or placeholder files.
- Do not claim code ran, hardware moved, sourcing was current, or compatibility was verified without evidence.
- Do not create agent-specific instruction files unless the active environment requires them, the user requests them, or their scope and benefit are explicit.
- Keep secrets, tokens, private URLs, personal data, and machine-specific absolute paths out of tracked files.
- Explain how to continue in the project's existing workflow.
