# Security and Robotics-Safety Policy

## Supported Versions

Until the first tagged release, only the current default branch is supported. After releases begin, supported versions will be documented here.

## Report Privately

Use GitHub private vulnerability reporting when the repository is published:

`https://github.com/zartosht/zari-robotic-project-skill/security/advisories/new`

The owner must enable private vulnerability reporting and verify this URL before making the repository public. Publication is blocked until that check succeeds.

If private reporting is unavailable after publication, do not publish sensitive details. Open a minimal issue asking the maintainer to establish a monitored private contact channel, without including exploit steps, personal data, credentials, or dangerous physical instructions.

Include:

- the affected file, version, or commit;
- impact and realistic preconditions;
- a minimal reproduction when safe;
- whether physical hardware, power, movement, privacy, or credentials are involved;
- a proposed mitigation if known.

## In Scope

- instruction injection or unsafe trust of project content;
- credential, personal-data, audio, video, or location exposure;
- actuator commands bypassing deterministic validation;
- missing watchdog, fault-stop, safe-start, or emergency-stop boundaries;
- dangerous voltage, current, polarity, power, battery, or charging guidance;
- shopping or compatibility claims that could cause hardware damage or injury;
- destructive installation or update behavior;
- repository scripts or workflows with command-injection or supply-chain risk;
- false compatibility claims that bypass client security or approval behavior.

## Safety Response

For an immediate physical hazard, disconnect power using the safest available method, keep people and animals away, and follow the component or facility emergency guidance. Do not continue testing to collect a better reproduction.

Maintainers will prioritize credible risks involving unintended movement, heat, fire, battery damage, mains voltage, privacy leaks, or credentials. Do not send live secrets or sensitive recordings.

## Not a Safety Certification

This repository is educational workflow guidance. Security review, issue triage, or a merged fix does not certify a robot, circuit, battery system, tool process, or regulated product.
