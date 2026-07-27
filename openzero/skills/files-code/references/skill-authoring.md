# Skill authoring

Build an OpenZero skill as a concise, reviewable package:

1. Choose a short lowercase hyphenated id and write a trigger-rich description.
2. Put only essential procedure in `SKILL.md`; keep frontmatter to `name` and `description`.
3. Move conditional detail into one-level `references/` files linked directly from `SKILL.md`.
4. Declare typed tool schemas without executable placeholder values.
5. Separate read-only, task-scoped, and fresh-confirmation capabilities.
6. Set finite step, tool-call, time, and output budgets.
7. Declare evidence-based completion and honest stop conditions.
8. Add the id to `catalog.json`, run `skills/validate_catalog.py`, and add focused tests.

Do not copy private system prompts or proprietary skill packages. Write clean-room procedures for OpenZero's actual tools and verify every declared capability exists.
