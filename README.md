# python-mcp

A Model Context Protocol (MCP) server for Python code-quality checks with token-efficient output.

## Overview

python-mcp gives LLMs direct access to linting, formatting, type checking, security, dependency, test-collection, dead-code, and spelling checks. Tool output is parsed structurally and reduced to compact diagnostics before it reaches the model.

## Features

- **ruff_check** - Lint files, glob patterns, or everything; `changed_only` checks just the files touched in git
- **ruff_format** - Verify formatting without modifying files
- **ty_check** - Type-check with concise output and an optional `error`/`warning` severity filter
- **vulture_check** - Find unused code and other dead-code candidates
- **bandit_check** - Find common Python security problems
- **deptry_check** - Find missing, unused, obsolete, and misplaced dependencies
- **pytest_collect** - Verify that tests can be collected without executing them
- **codespell_check** - Find likely spelling mistakes in source and documentation
- **pydoclint_check** - Check docstrings against function signatures
- **Structured parsing** - ruff JSON and ty GitLab code-quality output avoid fragile parsing of human-readable text
- **Adaptive aggregation** - large result sets include rule/file rollups before flat diagnostics, reducing repeated context
- **changed_only** - Check only staged, unstaged, and untracked Python files (`*.py`, `*.pyi`)

## How It Works

python-mcp implements the [Model Context Protocol](https://modelcontextprotocol.io) to expose nine read-only tools. All tools return a `CheckResult` with token-efficient `output` text and the underlying `exit_code`.

### Tools

- `ruff_check(paths?, changed_only?)` - Run ruff linting
- `ruff_format(paths?, changed_only?)` - Run `ruff format --check`
- `ty_check(paths?, level?, changed_only?)` - Run `ty check --output-format concise`, filtering by `all` / `error` / `warning`
- `vulture_check(paths?, changed_only?)` - Run vulture dead-code analysis
- `bandit_check(paths?, changed_only?)` - Run Bandit security analysis
- `deptry_check(paths?, changed_only?)` - Run deptry dependency analysis
- `pytest_collect(paths?, changed_only?)` - Collect tests without running them
- `codespell_check(paths?, changed_only?)` - Run codespell spelling analysis
- `pydoclint_check(paths?, changed_only?)` - Run pydoclint docstring analysis

### Output Processing

| Command | Input format | Output |
|---|---|---|
| `ruff check` | JSON | Compact grouped output; large runs get rule/file rollups |
| `ruff format --check` | Concise text | One line per unformatted file |
| `ty check` | GitLab JSON | Compact grouped output; severity filter applied |
| `vulture` | Concise text | Compact grouped dead-code findings |
| `bandit` | JSON | Compact grouped security findings |
| `deptry` | ANSI-free text | Compact grouped dependency findings |
| `pytest --collect-only` | Concise text | Collected test IDs or collection errors |
| `codespell` | Concise text | Compact spelling findings with suggestions |
| `pydoclint` | Concise text | Compact docstring-signature violations |

Small and medium result sets use the plugin-compatible grouped layout because it has lower overhead. Large result sets switch to an rtk-like layout with `Top rules`, `Top files`, and flat diagnostic lines. This addresses rtk's large-result advantage without adding an external runtime dependency.

## Usage

To start the server:

```bash
uvx python-mcp
```

Or from a checkout:

```bash
uv run python-mcp
```

Configure an MCP client to launch the server in the project directory to check, e.g. for opencode:

```json
{
  "mcp": {
    "python-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["python-mcp"]
    }
  }
}
```

The server checks the project in its working directory. To target another directory, set `PYTHON_MCP_PROJECT_DIR`.

### Agent Skill

Install the bundled `python-mcp` skill in a project when the agent client
discovers skills from `.agents/skills`:

```bash
uvx python-mcp skill install python-mcp --target .
```

The skill directs agents to the server's nine read-only tools:
`ruff_check`, `ruff_format`, `ty_check`, `vulture_check`, `bandit_check`,
`deptry_check`, `pytest_collect`, `codespell_check`, and `pydoclint_check`.
It does not describe uv package
or environment management.

### Configuration

Environment variables, all optional:

- `PYTHON_MCP_LOG_LEVEL` - Logging level, default `INFO`
- `PYTHON_MCP_PROJECT_DIR` - Project directory to check, default: server working directory
- `PYTHON_MCP_COMMAND_PREFIX` - Prefix for native ruff/ty/vulture invocations, default `uv run`; set to empty to use binaries from `PATH`
- `PYTHON_MCP_COMMAND_TIMEOUT` - Optional command timeout in seconds

## Development

This project is built with [FastMCP](https://github.com/PrefectHQ/fastmcp) and [uv](https://github.com/astral-sh/uv).

```bash
uv sync --extra dev
uv run ruff check
uv run ty check
uv run pytest
```
