# CLAUDE.md

This file provides guidance to AI assistants (Claude and others) working in this repository.

## Repository Overview

**Repo:** `zubirsaleh/claude`
**Status:** Initial setup — no source files yet.

Update this section as the project takes shape: describe what the product does, its primary users, and the problem it solves.

## Project Structure

```
claude/
├── CLAUDE.md          # This file
```

Update this tree as directories and files are added.

## Development Setup

Document the steps needed to get a local development environment running:

```bash
# Example — replace with actual commands
git clone https://github.com/zubirsaleh/claude.git
cd claude
# install dependencies, e.g.:
# npm install  /  pip install -r requirements.txt  /  bundle install
```

### Prerequisites

List required tools and versions here (Node, Python, Docker, etc.).

## Common Commands

| Task | Command |
|------|---------|
| Install deps | `<command>` |
| Run dev server | `<command>` |
| Run tests | `<command>` |
| Lint / type-check | `<command>` |
| Build for production | `<command>` |

Fill in the right-hand column once the project has a build system.

## Git Workflow

- **Primary branch:** `main`
- **Feature branches:** `<area>/<short-description>` (e.g. `auth/oauth-login`)
- **AI task branches:** `claude/<task-slug>` (auto-created by Claude Code on the web)
- Commit messages should be imperative, present-tense, ≤ 72 chars: `Add user authentication flow`
- Open a pull request for every change; do not push directly to `main`.

## Code Conventions

Fill this section in once the stack is decided. Typical things to document:

- **Language / framework version** in use
- **Formatting tool** (Prettier, Black, gofmt, etc.) and whether it runs automatically
- **Linter** (ESLint, Ruff, golangci-lint, etc.) and any rule overrides
- **Naming conventions** (camelCase vs snake_case, file naming, etc.)
- **Test file location and naming** (`*.test.ts` next to source, or `tests/` directory, etc.)
- **Import ordering** rules if enforced

## Testing

Describe the test strategy:

- Unit tests: `<framework>` — run with `<command>`
- Integration tests: `<framework>` — run with `<command>`
- E2E tests: `<framework>` — run with `<command>`

All new features should include tests. PRs must not reduce overall coverage.

## Environment Variables

List required environment variables and where to get them:

| Variable | Description | Required |
|----------|-------------|----------|
| `EXAMPLE_API_KEY` | API key for Example service | Yes |

Never commit real secrets. Use `.env.local` (gitignored) for local values.

## AI Assistant Guidelines

Guidelines specifically for Claude Code and other AI assistants:

- **Read this file first** before making any changes.
- **Prefer editing existing files** over creating new ones.
- **No unnecessary comments** — only add a comment when the *why* is non-obvious.
- **No speculative abstractions** — implement exactly what is asked; don't design for hypothetical future requirements.
- **Security first** — never introduce SQL injection, XSS, command injection, or other OWASP Top 10 vulnerabilities.
- **No hard-coded secrets** — use environment variables at system boundaries.
- **Ask before destructive git operations** — force-push, reset --hard, branch deletion, etc.
- **Commit and push** all work to the designated feature branch; do not open a PR unless explicitly asked.
- **Run tests** after any non-trivial change and confirm they pass before reporting work as done.

## Architecture Decisions

Record significant architectural choices here as the project grows. Each entry should note: *what* was decided, *why*, and *what was rejected*.

Example format:

> **2026-05-25 — Chose X over Y**
> Reason: X provides Z because … Y was rejected because …
