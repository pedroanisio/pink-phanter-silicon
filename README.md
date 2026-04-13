# Codebase Refactor Tool

A three-phase codebase reorganization tool that scans directory trees, detects structural smells, proposes refactor plans, and executes them — moving files, rewriting imports, patching documentation, and cleaning up empty directories.

Supports Python, JavaScript/TypeScript, and Markdown files.

## Installation

Requires Python 3.10+.

```bash
uv venv && uv pip install pyyaml
```

For development:

```bash
uv pip install pyyaml pytest pytest-cov
```

## Usage

The tool has two commands: **scan** and **execute**. The workflow is always scan first, review the plan, then execute.

### Scan

Walk a directory, build a dependency graph, detect structural smells, and output a YAML refactor plan:

```bash
python -m codebase_refactor scan ./my-project
```

Options:

| Flag | Description | Default |
|------|-------------|---------|
| `--ignore PATTERN` | Glob pattern to exclude (repeatable) | none |
| `--out FILE` | Write plan to file instead of stdout | stdout |
| `--check-invariants` | Enable runtime invariant assertions | off |
| `-v, --verbose` | Print log to stderr | off |

Example with ignore patterns:

```bash
python -m codebase_refactor scan ./my-project \
  --ignore "*.pyc" \
  --ignore "__pycache__" \
  --ignore "node_modules" \
  --out plan.yaml
```

### Review the plan

The scan produces a YAML file listing proposed file moves. Review and edit it before executing:

```yaml
version: '1.0'
root: /path/to/my-project
delete_empty: true
created_at: '2026-04-12T20:30:00+00:00'
moves:
- source: src/deeply/nested/utils/helpers.py
  destination: src/utils/helpers.py
  lang: python
```

Remove moves you disagree with, add your own, or adjust destinations. The plan is the handoff artifact between scan and execute — no state is shared otherwise.

### Execute

Apply an approved plan:

```bash
python -m codebase_refactor execute ./my-project --plan plan.yaml
```

Always dry-run first:

```bash
python -m codebase_refactor execute ./my-project --plan plan.yaml --dry-run
```

Options:

| Flag | Description | Default |
|------|-------------|---------|
| `--plan FILE` | Path to YAML plan (required) | — |
| `--dry-run` | Simulate without filesystem changes | off |
| `--backup-dir NAME` | Backup directory name | `.refactor-backup` |
| `--check-invariants` | Enable runtime invariant assertions | off |
| `-v, --verbose` | Print log to stderr | off |

The execute pipeline:

1. **Validates** the plan (sources exist, no duplicate destinations, no collisions, lang annotations match)
2. **Backs up** all files that will be moved or have imports rewritten
3. **Creates** destination directories
4. **Moves** files (uses staging for swap-safe cycle handling)
5. **Rewrites** import statements in all source files
6. **Patches** path references in Markdown documentation
7. **Cleans** empty directories left behind (if `delete_empty: true`)
8. **Reports** results as JSON to stdout

Exit codes: `0` success, `1` plan failure, `2` internal error.

## What it detects

The scan phase identifies structural smells:

- **Circular dependencies** — cycles in the import graph
- **God modules** — files imported by more than 10 others
- **Orphan files** — non-test files with no importers and no imports
- **Deep nesting** — files more than 5 directory levels deep

## Import rewriting

| Language | Strategy | Limitations |
|----------|----------|-------------|
| Python | `ast` module — parses and rewrites `import` / `from ... import` statements | Does not preserve comments or formatting within rewritten lines |
| JavaScript / TypeScript | Regex-based — covers `import/export ... from`, `require()`, `import()` | Misses computed `require()` and template literal imports |
| Markdown | Boundary-safe regex — longest-path-first substitution | Only matches paths at word-like boundaries |

## Development

Run tests:

```bash
python -m pytest codebase_refactor/tests/ -v
```

Run tests with coverage:

```bash
python -m pytest codebase_refactor/tests/ --cov=codebase_refactor --cov-report=term-missing
```

Current coverage: 92% across 149 tests.

### Project structure

```
codebase_refactor/
├── __init__.py
├── __main__.py              # python -m codebase_refactor
├── cli.py                   # argparse entry point
├── engine.py                # state machine — phase transitions + rule dispatch
├── models.py                # dataclasses and enums
├── extern/
│   ├── filesystem.py        # directory walking, file I/O, hashing
│   ├── imports.py           # extract, resolve, and rewrite imports
│   ├── doc_patch.py         # patch path references in Markdown
│   ├── plan.py              # YAML serialization, validation
│   ├── cycles.py            # move-cycle detection (DFS)
│   ├── preflight.py         # pre-mutation safety checks
│   ├── graph.py             # dependency graph + smell detection
│   └── reporting.py         # JSON report generation
└── tests/
    ├── test_models.py
    ├── test_filesystem.py
    ├── test_imports.py
    ├── test_plan.py
    ├── test_cycles.py
    ├── test_preflight.py
    ├── test_doc_patch.py
    ├── test_graph.py
    ├── test_reporting.py
    ├── test_engine.py
    └── test_cli.py
```

### Architecture

The engine is a priority-ordered rule-based state machine. Each rule is a `(name, guard, action)` triple. On each step, the first rule whose guard passes fires. The engine loops until the phase reaches `DONE` or `FAILED`.

All filesystem and analysis operations are in the `extern/` package. The engine never touches the filesystem directly — it delegates to extern functions, which accept a `dry_run` flag and skip mutations when set.

Eight invariants from the BSL spec are enforced at runtime when `--check-invariants` is passed:

1. Backup completes before any mutation (or dry-run mode is active)
2. FAILED state always has an error message
3. Files moved never exceeds plan size
4. Scan command never enters execute phases
5. Execute command never enters scan phases
6. Scan completion always produces plan YAML
7. Execute completion always produces a JSON report
8. Validation errors only exist in FAILED or VALIDATING state

## Spec

This tool is implemented from a formal BSL (Behavioral Specification Language) spec. See:

- `codebase_refactor_v2.md` — the BSL spec defining all rules, states, invariants, and extern contracts
- `implementation_plan.md` — the Python implementation plan derived from the spec

## License

Not yet specified.
