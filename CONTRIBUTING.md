# Contributing

Thank you for improving Zari Robot Project Builder. Contributions should keep the skill portable, conservative around physical risk, and useful to beginners without forcing a particular robot or technology stack.

## Before You Start

1. Read `build-robot-project/SKILL.md` and every reference affected by your change.
2. Check the current open Agent Skills specification.
3. Open an issue before a large workflow, safety-policy, compatibility, or repository-layout change.
4. Do not include credentials, private product links, personal data, or unlicensed third-party content.

## Design Rules

- Keep `SKILL.md` imperative, under 500 lines, and under the recommended 5,000-token budget.
- Keep only `name` and `description` in portable frontmatter. This repository intentionally enforces that conservative subset; changing it requires an explicit maintainer decision and matching validator update.
- Put detailed guidance in directly linked references.
- Keep client-specific paths, syntax, and metadata out of the portable core.
- Do not assume Arduino, Raspberry Pi, TypeScript, Python, web apps, voice, AI, cameras, wheels, or walking.
- Treat hardware lists as research until current compatibility evidence exists.
- Preserve all purchasing, power, movement, battery, privacy, tool, and autonomy gates.
- Prefer exact beginner instructions and observable stop conditions over shorthand.

## Development

Run:

```bash
python3 scripts/validate_repository.py
python3 -m unittest discover -s tests -v
skills-ref validate ./build-robot-project
gitleaks git .
```

If `skills-ref` is unavailable, disclose that in the pull request and rely on GitHub Actions for the standard validation pass.

For behavior changes, update the relevant scenario in `tests/forward-tests.md` and run an isolated forward test without giving the test agent the expected answer. Record material results in `tests/forward-test-report.md`.

## Pull Request Checklist

- [ ] The portable core remains agent-neutral.
- [ ] Trigger wording activates for project-start requests and avoids casual robot mentions.
- [ ] Relative links resolve and no empty placeholders remain.
- [ ] Safety, privacy, sourcing, and compatibility claims are evidence-backed.
- [ ] New scripts are necessary, non-destructive, documented, reversible, and tested.
- [ ] Documentation commands match current official client documentation.
- [ ] Validation and unit tests pass.
- [ ] An adversarial review considered actuator safety, power, batteries, privacy, sourcing, portability, and publishing risk.

## Review Expectations

Maintainers may request a smaller change, additional official sources, a forward test, or a safety review. A passing structural validator is necessary but does not establish that behavioral instructions are safe or effective.

By contributing, you agree that your contribution is licensed under Apache-2.0.
