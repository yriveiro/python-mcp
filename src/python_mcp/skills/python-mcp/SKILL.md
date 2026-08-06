---
name: python-mcp
description: Use when the python-mcp MCP server is available to run ruff_check, ruff_format, or ty_check on a Python project. Prefer its compact read-only diagnostics for linting, format verification, and type checking.
license: MIT
compatibility: Requires the python-mcp MCP server connected to the agent.
metadata:
  audience: python-developers
  author: Yago Riveiro
  version: "1.0.0"
---

# python-mcp Skill

`python-mcp` exposes compact, read-only quality checks for Python projects. It
does not manage dependencies or environments, and it does not modify source
files.

## Tools

| Need | Tool | Arguments |
| --- | --- | --- |
| Lint Python code | `ruff_check` | `paths?: list[str]`, `changed_only?: bool` |
| Verify formatting | `ruff_format` | `paths?: list[str]`, `changed_only?: bool` |
| Type check | `ty_check` | `paths?: list[str]`, `level?: "all"|"error"|"warning"`, `changed_only?: bool` |

Use these MCP tools instead of shelling out to `ruff` or `ty` when they are in
the tool context. Their output is structured and intentionally compact.

## Fast Feedback

After changing Python code:

1. Run `ruff_check(changed_only=true)`.
2. Run `ruff_format(changed_only=true)`.
3. Run `ty_check(level="error", changed_only=true)`.
4. Fix the reported files and rerun the affected check until it passes.

Use `ty_check(level="all")` when warnings are relevant to the task. A filtered
result can contain zero displayed diagnostics while the underlying command still
has a nonzero `exit_code`, so always inspect the exit code.

## Full Verification

Before finishing a change, run the checks across the project:

1. `ruff_check()`
2. `ruff_format()`
3. `ty_check(level="error")`

`ruff_format` only reports files that need formatting. Apply formatting through
the project's authorized editing workflow, then rerun `ruff_format` to verify
it.

## Target Selection

- Omit `paths` to check the whole project.
- Pass files, directories, or glob patterns, such as
  `paths=["src/**/*.py", "tests"]`, to narrow a check.
- Use `changed_only=true` for staged, unstaged, and untracked Python files in
  the current Git repository. It takes precedence over `paths`; do not combine
  the two when a scoped check is intended.
- When no modified Python files exist, a changed-only check succeeds with
  `No modified Python files found.`

## Results

Each tool returns compact `output`, the underlying `exit_code`, and an `issues`
count. Ruff lint results also report `fixable`; type-check results report
`warnings`. `saved_tokens` and `savings_percent` estimate the output reduction.

Treat a nonzero `exit_code` as a failed check even when a severity filter hides
some diagnostics. Report the tool, scope, and remaining findings concisely.
