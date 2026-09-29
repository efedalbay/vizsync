# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

**vizsync** is an open-source Python CLI. Given a narration recording and the numbered script it was read from, it reports where each script paragraph starts and ends in the audio. It also writes YouTube chapter lists, editor markers, and chart timing for [vizreel](https://github.com/efedalbay/vizreel).

Read these before making changes. They are the source of truth:

| File | Contains |
|---|---|
| `docs/SPEC.md` | Script format, commands, output files |
| `docs/ARCHITECTURE.md` | Stack, layout, data flow, the aligner, testing strategy |
| `docs/ROADMAP.md` | Milestones and their acceptance criteria |

## Working with Efe

- Efe is the maintainer. Talk to him in **Turkish**. Code, comments, docstrings, commit messages, docs and the README are in **English**.
- Efe develops on **Windows** with PowerShell. Give commands that work there.
- Keep chat replies short and plain. Efe often reads them while busy: say what you did, what you need from him, and stop.
- When you make a non-obvious design decision, explain the reason in one or two sentences in chat. Do not put these explanations in code comments.
- Work on **one milestone at a time**, in `docs/ROADMAP.md` order. At the start of a milestone, post a short plan (files to create or change, tests to add) and wait for Efe's approval before writing code. Approving the plan also approves the branch, pull request and merge for it (see Git).
- At the end of a milestone, list each acceptance criterion and whether it is met, with evidence (test output, command output). Then add a numbered **"Senin yapacağın"** section (see below).
- Add every check that has to run on Efe's computer (real-model tests, hand checks) to `scripts/check-local.ps1` in the same milestone.

### The "Senin yapacağın" section

Written in Turkish at the end of every milestone. It lists everything Efe has to do himself, in order, with no limit on the number of items. Only list what only he can do: never list a step Claude can do.

Every item has four parts:

1. **Where:** PowerShell, GitHub, DaVinci Resolve, and so on.
2. **What to do:** the exact command to paste, or the exact place to click.
3. **What he should see** when everything is right.
4. **If he sees something else:** what to send back to Claude (which output, which file, which screenshot).

This section is the exception to "keep chat replies short": it must be complete.

## Model routing

The default model for this project is Sonnet 5.5 at high effort. Most work is well-scoped and fits it.

For the hard algorithmic parts, delegate to the **`algorithm-expert`** subagent (defined in `.claude/agents/algorithm-expert.md`, runs on Opus):

- The aligner and paragraph boundary refinement (`src/vizsync/match/`, milestone M2).
- Any bug where two straightforward attempts have already failed.

Do not use it for boilerplate, CLI wiring, file writers or docs. Give it full context in the prompt (the relevant docs sections, the failing test or case, the files involved). It returns a design or a patch plus tests; you integrate the result and run the whole test suite yourself.

If the subagent is not available in the current environment, do the work yourself and tell Efe, so he can switch the model by hand if he wants.

## Commands

```powershell
uv sync                                   # install dependencies (including dev)
uv run vizsync --help
uv run vizsync check examples/northwind-script.md
uv run pytest -m "not slow"               # fast unit tests
uv run pytest -m slow                     # real-model tests (needs a model download)
uv run ruff check . ; uv run ruff format .
uv run mypy src
```

## Rules

### Architecture
- Follow `docs/ARCHITECTURE.md`. The speech model is only ever used through the `Transcriber` interface.
- `cli.py` contains no business logic. It parses arguments, calls the library, and prints results.
- Matching logic (`match/`) is pure functions on plain data. No file access, no model, no printing.
- Use `pathlib.Path` for every path. Expand wildcards yourself; do not rely on the shell.
- Expected failures raise a `VizsyncError` subclass with a message a user can act on, naming the file and line.
- Never invent times for a paragraph that was not found. Report it as `missing`.

### Spec
- `docs/SPEC.md`, the models and the tests change together, in the same commit. Never change one without the others.
- Examples and test data use the fictional company "Northwind" and made-up numbers. No real companies, real figures or real people.

### Dependencies
- The approved list is in `docs/ARCHITECTURE.md`. Do not add anything else without asking Efe first. Say what it does and why the standard library or existing dependencies are not enough.

### Tests
- Every pure function has unit tests. Write the tests for the aligner before the implementation.
- Unit tests never need audio or a model.
- Tests marked `@pytest.mark.slow` use the real model and the fixture clip. The cloud environment may not be able to download models: if it cannot, skip them there and say so. Never fake a passing slow test.
- Tests must pass on Windows.

### Style
- Python 3.11+, type hints on all public functions, ruff for lint and format.
- Small, focused functions. Prefer clear names over comments.
- Docstrings on public classes and functions (Google style, short).

### Git
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`.
- **No AI attribution.** Never add `Co-Authored-By` trailers, "Generated with Claude Code" lines or any similar attribution to commit messages, pull requests, code or docs. Efe is the sole author.
- One logical change per commit. Commit at the end of each approved step, not in the middle of broken work.
- Never commit audio recordings other than the approved fixture, model files, or output folders.
- The approved milestone plan is the scope of the workflow below. Work outside it (another milestone, a changed plan) needs new approval first.

**Branch, pull request, merge.** Once Efe has approved a milestone plan, Claude does the following without asking again:

1. Create a branch for the milestone, commit on it, push it and open a pull request against `main`. Never push to `main` directly.
2. Wait for CI. When every job is green on the head commit, squash-merge the pull request and delete the branch. The squash commit title is a conventional commit with no attribution.
3. If CI is red, fix it on the same branch and push. Never skip, disable or weaken a test to get green. If `main` moved and the branch conflicts, merge `main` into the branch.
4. After opening a pull request, read its description back and remove any attribution line the platform added.

**Still needs Efe's explicit go-ahead every time:** publishing to PyPI, creating tags or releases, and changing CI secrets.

## Definition of done (every change)

1. `uv run ruff check .` clean.
2. `uv run mypy src` clean.
3. `uv run pytest -m "not slow"` green; slow tests green if audio or model code changed (or explicitly reported as not runnable here).
4. Docs updated if behavior or the spec changed.
