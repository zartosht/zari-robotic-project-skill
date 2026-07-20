# Adversarial Review Report

Date: 2026-07-20

Three independent read-only reviewers inspected the repository from these perspectives:

1. robotics safety, power, batteries, actuator control, privacy, sourcing, and publishing risk;
2. Agent Skills specification, portability, installation documentation, CI, and open-source maintenance;
3. beginner electronics, curriculum design, scaffolding, and next-step usability.

## Findings Resolved

- Replaced the floor-movement-only emergency-stop rule with a force/energy hazard rule for all injury-capable motion.
- Added an independent hardware watchdog or safety-supervisor requirement and fail-safe driver-enable behavior for hazardous actuators.
- Added controller-hang, stale-sensor, stalled-loop, brownout, and reboot-without-resume tests.
- Added complete current-path checks for conductors, contacts, breadboards, connectors, fuses/current limits, return paths, and USB/charger/battery backfeed.
- Added battery identity, condition, chemistry, cell count, voltage range, discharge, BMS/protection, fuse, charger, supervision, enclosure, storage, damage, and disposal fields.
- Added gates for pressure, gravity, springs, flywheels, heat, and other hazardous stored energy.
- Added safe multimeter lead/mode guidance and prohibited novice current measurements without a documented fused series setup and supervision.
- Marked project files, uploaded documents, datasheets, and web pages as untrusted evidence rather than instructions.
- Expanded lightweight secret patterns and added commit-pinned Gitleaks CI scanning plus local `.env`/key ignores.
- Added a per-data-type privacy flow covering purpose, provider, encryption, access, retention, deletion, logs, third parties, bystanders, offline behavior, and hardware-tied indicators or controls.
- Added safety-critical provenance, authorized-distributor, certification, recall, and counterfeit checks.
- Added responsible-adult approval for minors and body-contact/quick-release/human-factors rules for wearables.
- Added learning competencies, prerequisite concepts, mastery evidence, misconceptions, and remediation to learning roadmaps.
- Expanded the next-step template with exact source/destination endpoints, breadboard groups, voltage/polarity, power state, common mistakes, and recovery.
- Fixed Gemini CLI remote install/reinstall commands with `--path build-robot-project`.
- Changed all copy-install examples to carry the Apache-2.0 license into the installed skill directory.
- Pinned GitHub Actions by immutable commit SHA.
- Added explicit handling for read-only, interview-only, research-only, and planning-only requests.
- Created and linked the missing forward-test report.

## Findings Intentionally Not Applied

- **Remove Robotistan as the worldwide no-preference default:** rejected because Robotistan is a locked product decision. The skill still checks location/shipping and asks before changing the primary retailer.
- **Add optional frontmatter fields:** rejected for the current release because the portable core intentionally uses the conservative `name` and `description` subset required by the creation workflow. The repository validator and contributing guide now state that decision consistently.
- **Make retailer discovery conditional:** rejected because asking for the user's preferred hardware retailers is a locked product requirement, even when the initial phase does not yet purchase parts.

## Remaining Publication Checks

- Keep the validated local commit unchanged between owner approval and push.
- Create the GitHub repository only after explicit owner authorization.
- Enable and verify GitHub private vulnerability reporting before making the repository public.
- Verify README rendering, links, and the first hosted workflow run after publication.
- Keep the initial release untagged until owner review is accepted.

## Review Limits

- Reviewers inspected text, tests, and configuration; they did not certify physical hardware or run a hazardous system.
- The standard validator's source commit and Actions are pinned, but its Python transitive dependencies resolve from the package index at workflow time.
- Current client support labels are official-documentation-backed, not hands-on certification of every client version, account, and managed environment.
