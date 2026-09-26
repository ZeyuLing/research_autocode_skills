# Changelog

All notable changes to PaperJury are documented in this file.

## [0.7.0] - 2026-09-26

- Freeze substantive reviewer profiles before a round; job titles alone no
  longer satisfy panel diversity. Keep cards private to their assigned roles.
- Add an unscored evidence pass followed by rubric-based scoring in the same
  isolated reviewer context. Bind assessments by hash and preserve their findings.
- Require scores to cite decisive factors and explain adjacent allowed choices
  and confidence, without assigning desired ratings or reviewer strictness.
- Add panel diagnostics that distinguish identical numbers from copied reasoning;
  equal scores remain valid and never cause variance-targeted reruns.
- Clarify default conference versus legacy courtroom routing in guides/workflows.
- New packet preparation requires `--panel`; old packets remain readable through
  the legacy `reviewer-prompt` path.

## [0.5.0] - 2026-06-05

### Added

- **Claude Code plugin packaging.** PaperJury can now be installed as a Claude Code
  plugin from a self-hosted marketplace, alongside the existing clone-as-skill install.
  - `.claude-plugin/plugin.json` — plugin manifest. Declares the skill at the repo
    root (`"skills": ["./"]`, root-as-skill) so `SKILL.md` does not move and the
    plain-skill install keeps working.
  - `.claude-plugin/marketplace.json` — self-hosted marketplace listing this one
    plugin (`source: "./"`).
  - Install: `/plugin marketplace add u7079256/paperjury` then
    `/plugin install paperjury@u7079256`.

### Notes

- This change is additive and non-breaking: `SKILL.md` stays at the repo root and is
  still auto-discovered as a plain skill, so the existing `~/.claude/skills/paperjury`
  install (clone-as-skill) is unaffected.
- The plugin manifest version tracks the skill engine version in `SKILL.md` frontmatter.
- This is the first tracked changelog entry; it documents the packaging change shipped
  on top of the existing 0.5.0 engine, not the full engine history.
