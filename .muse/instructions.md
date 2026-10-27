# Muse Code instructions (whole team)

Same rules as Claude Code. Read before writing code:

1. `CLAUDE.md` (repo root): source of truth, architecture laws, model roles, fallback protocols.
2. `plan/<your-name>.md`: your build order, handoff dates and interfaces.
3. `backend/CLAUDE.md` for backend code style; `.claude/skills/crucible-code/SKILL.md` for file templates.
4. The nested `CLAUDE.md` of the area you're working in, if it has one. Project Defense + Runner:
   `backend/crucible/defense/CLAUDE.md`. It points to `docs/defense/DEFENSE_AGENT_SPEC.txt` and to
   `docs/defense/MEMORY.md`, the working memory Claude Code and Muse Code share for that area (claim
   files there and sign entries `[muse]`).
