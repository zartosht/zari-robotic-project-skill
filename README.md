# Zari Robot Project Builder

Zari Robot Project Builder is a portable Agent Skill that interviews, plans, sources, scaffolds, and safely starts physical robotics projects.

The repository contains one skill, `build-robot-project`, built against the open [Agent Skills specification](https://agentskills.io/specification). Its core workflow is agent-neutral; client-specific installation notes and optional OpenAI UI metadata stay outside the portable instructions.

> [!WARNING]
> This project provides planning and educational guidance, not professional electrical, battery, mechanical, medical, aviation, marine, or functional-safety certification. Review component documentation, local law, and the actual physical setup. Use qualified supervision for mains voltage, high current, custom battery packs, dangerous tools, flight, pressure systems, or any hazard beyond your competence.

## What It Does

- Inspects an empty or early-stage project without overwriting existing work.
- Conducts an adaptive interview in small batches.
- Assesses software, electronics, power, fabrication, and robotics experience separately.
- Records confirmed requirements, assumptions, open questions, and deferred ideas.
- Classifies owned, uncertain, needed, optional, incompatible, and replacement hardware.
- Researches current parts from the user's preferred retailers.
- Uses Robotistan as the default research source when no retailer is supplied.
- Builds a compatibility matrix before treating a part as a purchase candidate.
- Chooses a low-risk, phased roadmap for the actual robot and user.
- Creates only the project files that the roadmap needs.
- Begins the roadmap-selected first phase up to mandatory safety, privacy, and purchasing gates.
- Produces exact beginner instructions when the user is new to physical hardware.
- Honors explicit read-only, interview-only, research-only, and planning-only scope without creating files or starting implementation.

## What It Does Not Do

- It does not impose Arduino, Raspberry Pi, TypeScript, Python, AI, voice, cameras, wheels, walking, cloud services, or a fixed folder layout.
- It does not order hardware, reserve stock, add products to carts, or claim a purchase occurred.
- It does not present unverified hardware as compatible.
- It does not power circuits, upload movement-capable firmware, or authorize physical motion on its own.
- It does not connect AI output directly to motors, servos, or other actuators.
- It does not guarantee automatic discovery in agents that do not natively support Agent Skills.

## How the Adaptive Interview Works

The skill starts from available evidence: the conversation, project files, inventory, photos, labels, and datasheets. It then asks one to three related questions at a time rather than presenting a giant questionnaire.

The interview covers only decisions that can affect the project:

1. Purpose, user, environment, form, and definition of finished.
2. Experience in programming, electronics, power, mechanical work, and safety.
3. Owned hardware, tools, fabrication access, and uncertain parts.
4. Budget, schedule, location, workspace, and preferred retailers.
5. Privacy, connectivity, battery, movement, autonomy, camera, microphone, and cloud preferences.

Afterward it separates confirmed decisions, assumptions, open questions, deferred ideas, contradictions, and safety concerns. It asks for confirmation only when a wrong interpretation would materially alter cost, architecture, safety, privacy, purchasing, or the first phase.

## Supported Project Types

The workflow can adapt to stationary robots, desk robots, robotic arms, wheeled platforms, wearables, walking concepts, flying or underwater research projects, sensor platforms, interactive artworks, learning labs, AI-enabled robots, and other physical robotic systems.

Higher-risk projects still begin with lower-risk evidence. A walking robot might start with stability simulation or a stationary mechanism; a robotic arm with unknown motors might start with part identification, torque estimates, and a no-power mechanical study.

## Example Generated Roadmap

For a beginner who wants a low-cost desk companion and owns no hardware, the skill might produce:

1. **Phase 1 — Requirements and mock interaction:** confirm behavior, create a text-only mock, and define safe command boundaries.
2. **Phase 2 — Low-energy electronics learning:** identify a compatible controller kit, then complete an LED/button lab after purchasing and power approvals.
3. **Phase 3 — Single unloaded actuator:** verify servo and supply compatibility, write bounded firmware, then pause before upload and first movement.
4. **Phase 4 — Stationary expressive prototype:** use a cardboard or foam-board body with guarded, limited motion.
5. **Phase 5 — Optional privacy-sensitive features:** add push-to-talk or a camera only after explicit privacy choices and visible indicators.

The sequence is an example, not a universal blueprint. The roadmap determines the starting phase.

## Example Generated Scaffold

The skill may create a project-specific structure such as:

```text
desk-companion/
├── README.md
├── docs/
│   ├── project-brief.md
│   ├── architecture.md
│   ├── roadmap.md
│   ├── safety-plan.md
│   ├── privacy-plan.md
│   └── next-step.md
├── hardware/
│   ├── inventory.md
│   ├── compatibility.md
│   └── sourcing.md
└── simulation/
    ├── mock_robot.py
    └── test_mock_robot.py
```

Another robot may need CAD files and no software, or firmware and no web app. The skill preserves existing conventions in non-empty projects.

## Repository Layout

```text
zari-robotic-project-skill/
├── build-robot-project/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   └── assets/templates/
├── scripts/validate_repository.py
├── tests/
├── .github/workflows/validate.yml
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

The portable core is `build-robot-project/SKILL.md`, `references/`, and `assets/`. `agents/openai.yaml` is optional OpenAI-specific UI metadata and is not required by the core.

## Quick Start

The proposed public URL is `https://github.com/zartosht/zari-robotic-project-skill`. It will not work until the owner explicitly authorizes publication.

From this checkout, point a supported agent at `build-robot-project/SKILL.md`, or link/copy the whole `build-robot-project` directory into the client-specific location below. Review the skill before enabling it; skills may read files, research the web, and create project files when invoked.

After publication:

```bash
git clone https://github.com/zartosht/zari-robotic-project-skill.git
cd zari-robotic-project-skill
```

## Compatibility Matrix

Support labels describe documented client behavior, not a guarantee that every version, account, editor, or managed environment enables the feature.

| Client | Support status | Discovery or installation | Invocation | Last verified |
| --- | --- | --- | --- | --- |
| OpenAI Codex CLI, IDE, and desktop app | Officially documented native | Repository or user `.agents/skills/` location | Mention `$build-robot-project` where skill mentions are supported, or ask a matching request | 2026-07-20 |
| Claude Code | Officially documented native | Project `.claude/skills/` or user `~/.claude/skills/` | `/build-robot-project` or a matching request | 2026-07-20 |
| Gemini CLI | Officially documented native | `gemini skills install`, `gemini skills link`, `.gemini/skills/`, or `.agents/skills/` | Ask a matching request and approve activation | 2026-07-20 |
| GitHub Copilot in VS Code / Agent mode | Officially documented native | Project `.github/skills/`, `.claude/skills/`, or `.agents/skills/`; user equivalents are also documented | `/build-robot-project` or a matching request | 2026-07-20 |
| Other agents that can read `SKILL.md` | Manual compatibility | Give the agent the skill directory or file explicitly | Tell it to read and follow `SKILL.md` | 2026-07-20 |

Official sources checked:

- [Open Agent Skills specification](https://agentskills.io/specification)
- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code: Extend Claude with skills](https://code.claude.com/docs/en/skills)
- [Gemini CLI: Managing Agent Skills](https://geminicli.com/docs/cli/using-agent-skills/)
- [VS Code: Use Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)

### OpenAI Codex

Codex officially documents repository-scoped and user-scoped skills under `.agents/skills`. To install for one project from a local clone:

```bash
mkdir -p /path/to/robot-project/.agents/skills
test ! -e /path/to/robot-project/.agents/skills/build-robot-project &&
  cp -R build-robot-project /path/to/robot-project/.agents/skills/ &&
cp LICENSE /path/to/robot-project/.agents/skills/build-robot-project/LICENSE
```

For a user-scoped installation:

```bash
mkdir -p "$HOME/.agents/skills"
test ! -e "$HOME/.agents/skills/build-robot-project" &&
  cp -R build-robot-project "$HOME/.agents/skills/" &&
cp LICENSE "$HOME/.agents/skills/build-robot-project/LICENSE"
```

The chained copy sequence stops if the destination exists. Review differences and remove or rename the old copy yourself before replacing it. Codex detects skill changes automatically in current documentation; restart if the skill does not appear.

Invoke with a matching request or, where supported:

```text
$build-robot-project Help me start a desk robot in this empty folder.
```

### Claude Code

Claude Code officially documents project skills under `.claude/skills/` and personal skills under `~/.claude/skills/`.

```bash
mkdir -p /path/to/robot-project/.claude/skills
test ! -e /path/to/robot-project/.claude/skills/build-robot-project &&
  cp -R build-robot-project /path/to/robot-project/.claude/skills/ &&
cp LICENSE /path/to/robot-project/.claude/skills/build-robot-project/LICENSE
```

Or install for the current user:

```bash
mkdir -p "$HOME/.claude/skills"
test ! -e "$HOME/.claude/skills/build-robot-project" &&
  cp -R build-robot-project "$HOME/.claude/skills/" &&
cp LICENSE "$HOME/.claude/skills/build-robot-project/LICENSE"
```

Invoke explicitly:

```text
/build-robot-project Help me plan a robotic arm.
```

Claude Code also documents automatic matching from the skill description.

### Gemini CLI

For local development, Gemini CLI officially documents linking a skill directory:

```bash
gemini skills link ./build-robot-project
gemini skills list
```

After publication, its documented remote-install form is:

```bash
gemini skills install https://github.com/zartosht/zari-robotic-project-skill --path build-robot-project
```

Gemini CLI also discovers `.gemini/skills/` and `.agents/skills/` at workspace or user scope. Use `/skills reload` after changes. Current Gemini CLI behavior asks for consent when activating a skill.

The current Gemini CLI documentation warns that some unpaid tiers are transitioning to Antigravity CLI. This compatibility row applies where Gemini CLI and its documented Agent Skills commands remain available.

### GitHub Copilot in VS Code / Agent Mode

VS Code officially documents shared project skills under `.github/skills/`, `.claude/skills/`, or `.agents/skills/`. For a repository-local copy:

```bash
mkdir -p /path/to/robot-project/.github/skills
test ! -e /path/to/robot-project/.github/skills/build-robot-project &&
  cp -R build-robot-project /path/to/robot-project/.github/skills/ &&
cp LICENSE /path/to/robot-project/.github/skills/build-robot-project/LICENSE
```

Open Chat, run `/skills` to inspect configured skills, and invoke:

```text
/build-robot-project Help me build a wheeled environmental monitor.
```

Availability can depend on the installed VS Code and GitHub Copilot versions, account, policy, and workspace trust.

### Windows PowerShell Copy

Use the client-specific destination from the sections above:

```powershell
$Source = Resolve-Path ".\build-robot-project"
$Destination = "$HOME\.agents\skills\build-robot-project"
if (Test-Path $Destination) { throw "Destination already exists: $Destination" }
New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
Copy-Item -Recurse -Path $Source -Destination $Destination
Copy-Item -Path (Join-Path (Split-Path $Source) "LICENSE") -Destination (Join-Path $Destination "LICENSE")
```

### Other Agents

For a client without documented Agent Skills discovery, explicitly instruct it:

```text
Read /path/to/zari-robotic-project-skill/build-robot-project/SKILL.md and follow it to interview me, scaffold this project, and begin the roadmap-selected first phase. Treat linked references as part of the skill and stop at its mandatory approval gates.
```

This is manual compatibility. Automatic discovery, progressive loading, approval behavior, and bundled-resource handling are not guaranteed.

## Invocation Examples

- “Help me start a robotics project.”
- “I want to build a robot from scratch.”
- “Set up this empty folder for my robot idea.”
- “Help me plan and build a personal AI robot.”
- “Help me build a robotic arm.”
- “I want to build a wheeled robot.”
- “Create a robotics learning project for me.”
- “Use the build-robot-project skill.”

The description intentionally avoids triggering for robotics news, company research, casual mentions, or unrelated software bots.

## Example User Session

```text
User: Help me build a small robot arm.

Agent: What should the arm manipulate, where will it operate, and is this mainly
a learning project or a prototype for a specific task?

User: A learning project on my desk. It should move foam blocks.

Agent: How comfortable are you with programming? Separately, have you wired a
breadboard, used a multimeter, or controlled a motor or servo before?

User: I am a web developer but new to electronics.

Agent: I will keep software explanations compact and teach electronics from first
principles. What hardware and tools do you already own, and which retailers do
you prefer?

User: No parts yet and no retailer preference.

Agent: I have recorded Robotistan as the default research source. I will first
create a no-power reach/load study and compatibility research plan. Purchasing,
power, firmware upload, and movement will remain approval-gated.
```

## Robotistan Default and Live Research

The skill always asks for preferred retailers. If none is supplied, it records Robotistan as the default research source. Robotistan is a research source, not a guarantee of compatibility, stock, shipping, or value.

For each recommended part, the skill seeks a current retailer page and manufacturer evidence, then records date, model, revision, price, currency, stock, shipping, voltage, current, logic level, connector, dimensions, load/torque/range, drivers, power, mounting, and missing accessories.

Claims are labeled as confirmed specifications, manufacturer claims, retailer claims, inferences, or unresolved questions. Hardware with an unresolved safety-critical field is marked `Unverified - do not buy or connect yet`.

## Safety and Approval Model

Explicit confirmation is required before purchasing, applying power to new wiring, connecting batteries or actuators to power, uploading movement-capable firmware, first movement, increasing motion energy, autonomous or floor movement, cameras, always-listening microphones, sensitive-data transmission, dangerous tools, mains voltage, high-current work, custom battery packs, or unresolved electrical compatibility.

AI may propose intent only. A deterministic validator must convert approved intent into bounded commands, and firmware must independently enforce limits, freshness, watchdog stops, fault stops, safe startup, and emergency stopping. Any motion capable of injury or material property damage requires a reachable, latching physical stop or non-network power/enable cut-off independent of the app and primary control process.

Camera and microphone features default to disabled, local-first processing where practical, visible activity indicators, and no raw recording retention.

## Updating

For a symlinked or linked development install, update the source checkout:

```bash
git pull --ff-only
```

For a copied install, pull the source, compare the existing destination, then replace it only after review. The project intentionally does not provide an overwrite installer because supported clients have different native locations and update behavior; explicit copy/link commands are easier to audit and reverse.

Gemini CLI users can uninstall and reinstall after reviewing changes:

```bash
gemini skills uninstall build-robot-project
gemini skills install https://github.com/zartosht/zari-robotic-project-skill --path build-robot-project
```

Use release tags after releases exist. Do not assume the default branch is a stable release.

## Uninstalling

Remove only the exact skill directory you installed. Inspect the path first:

```bash
ls -ld "$HOME/.agents/skills/build-robot-project"
rm -r "$HOME/.agents/skills/build-robot-project"
```

For Claude Code, substitute `"$HOME/.claude/skills/build-robot-project"`. For a project install, use that project's exact `.agents/skills/`, `.claude/skills/`, or `.github/skills/` path.

For Gemini CLI:

```bash
gemini skills uninstall build-robot-project
```

## Troubleshooting

### The skill is not discovered

- Confirm the directory is named `build-robot-project` and contains `SKILL.md` directly.
- Confirm `SKILL.md` begins with YAML frontmatter and contains `name` and `description`.
- Confirm the client-specific location from the official documentation.
- Check workspace trust and organization policy.
- Reload skills or restart the client when documented.
- Fall back to explicitly asking the agent to read `build-robot-project/SKILL.md`.

### The skill triggers too often

Confirm the installed copy uses the repository's narrow description. Disable implicit invocation through the client's supported settings when available and invoke explicitly.

### The interview repeats questions

Point the agent to the existing project brief or inventory and tell it to treat those answers as current evidence. Report a reproducible case if it still ignores confirmed information.

### Hardware research is incomplete

Web access may be unavailable, a retailer may block automated access, or a datasheet may omit critical ratings. The correct fallback is an unresolved research target, not a guessed compatibility claim.

### The first phase stops early

The skill intentionally stops at purchasing, power, movement, privacy, and unresolved-compatibility gates. Review the exact configuration and provide explicit confirmation only when you are ready.

## Validation

Run the repository's deterministic checks:

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -v
```

Run the standard Agent Skills validator when `skills-ref` is installed:

```bash
skills-ref validate ./build-robot-project
```

The GitHub Actions workflow runs repository checks, unit tests, the standard validator, and Gitleaks secret scanning. See [tests/forward-tests.md](tests/forward-tests.md) for behavior scenarios, [tests/forward-test-report.md](tests/forward-test-report.md) for the latest independent results, and [tests/adversarial-review-report.md](tests/adversarial-review-report.md) for second-pass findings and dispositions.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Safety, sourcing, and compatibility changes need evidence and adversarial review. Do not add client-specific tool instructions to the portable core.

## Security and Robotics-Safety Reporting

Read [SECURITY.md](SECURITY.md) for private reporting guidance covering software vulnerabilities, privacy leaks, unsafe robotics instructions, actuator-control bypasses, power hazards, and supply-chain concerns.

## License

Licensed under the [Apache License 2.0](LICENSE), including an explicit patent grant.

## Project Status and Limitations

Status: owner-review candidate; not yet published or released.

- The format and client documentation were checked on 2026-07-20.
- Native support labels are documentation-backed; cross-client hands-on execution can still vary by version, policy, and environment.
- Live sourcing depends on web access and accessible product pages.
- Prices, stock, shipping, and product revisions can change after research.
- The skill cannot inspect physical wiring, measure current, or certify a machine from text alone.
- Beginner guidance reduces ambiguity but does not replace qualified supervision.
- No public GitHub repository, release, package, or installer should be assumed to exist until publication is explicitly authorized.
- GitHub private vulnerability reporting must be enabled and its advisory URL verified before the repository is made public.
- The standard validator source is commit-pinned in CI; its Python transitive dependencies are still resolved from the package index at workflow time.
