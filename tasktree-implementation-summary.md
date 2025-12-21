# Task Tree (`tt`) - Implementation Summary for Claude Code

## Project Overview

Task Tree is a Python 3.11+ command-line task automation tool that provides intelligent incremental execution for development workflows. It fills the gap between simple task runners (Just) and full build systems (Make).

**Invocation**: `tt <task-name> [args...]`

**Config files**: `tasktree.yaml` or `tt.yaml` (YAML format)

**State file**: `.tasktree-state` (JSON format, single file, auto-pruned)

---

## Core Architecture

### Module Structure

```
tasktree/
  __init__.py
  cli.py         # Typer-based CLI with dynamic command generation
  parser.py      # Parse recipe YAML, handle imports
  graph.py       # Dependency resolution via graphlib.TopologicalSorter
  state.py       # State file management, pruning
  executor.py    # Task execution, staleness detection
  hasher.py      # Task and argument hashing
  types.py       # Custom Click/Typer parameter types for validation
```

### Key Dependencies

- **PyYAML** - Recipe file parsing
- **Typer** - CLI framework (prefer over Click for dynamic command generation)
- **Pygments** or **Rich** - Syntax highlighting for `--show`
- **colorama** - Terminal colours (cross-platform)
- Standard library: `graphlib.TopologicalSorter`, `pathlib`, `subprocess`, `json`, `hashlib`

---

## Task Definition Schema

```yaml
task-name:
  desc: string              # Optional, human-readable description
  deps: [task1, task2]      # Optional, task dependencies
  inputs: [glob/patterns]   # Optional, explicit input files
  outputs: [glob/patterns]  # Optional, output files
  working_dir: path/        # Optional, defaults to config file's directory
  args: [name:type=default] # Optional, typed parameters
  cmd: string | multiline   # Required, command to execute
```

### Argument Type System

Format: `name:type=default` (type and default both optional)

**Supported types**:
- `str` (default if unspecified)
- `int`, `float`, `bool`
- `path` - Uses `pathlib.Path`
- `datetime` - Uses Click's DateTime
- `url` - String with basic validation
- `hostname` - String with hostname format validation
- `email` - String with email format validation
- `ip` - Either IPv4 or IPv6 (uses `ipaddress.ip_address()`)
- `ipv4` - IPv4 only (uses `ipaddress.IPv4Address`)
- `ipv6` - IPv6 only (uses `ipaddress.IPv6Address`)

**Future/deferred**: `choice{a,b,c}` and `list{type}` were discussed but deferred for complexity reasons. Start with primitives.

Argument substitution uses `{{arg_name}}` in commands.

---

## State Management

### State File Structure

```json
{
  "e4d3a1f2": {
    "last_run": 1734567890,
    "input_state": {
      "src/main.rs": 1734567880,
      "Cargo.toml": 1734560000
    }
  },
  "e4d3a1f2__a3f5c2b1": {
    "last_run": 1734567920,
    "input_state": {...}
  }
}
```

### Cache Key Format

- **Non-parameterised tasks**: `task_hash` (8-char hex)
- **Parameterised tasks**: `task_hash__args_hash`

The two-part scheme is **required** for proper pruning—with a single hash, you cannot determine which cached entries are still valid without knowing what arguments were used.

### Task Hash Includes

- `cmd` - The command to execute
- `outputs` - Declared output files
- `working_dir` - Execution directory
- `args` - Parameter definitions (names and types)

### Task Hash Excludes

- `deps` - Only affects scheduling order
- `inputs` - Tracked separately via timestamps
- `desc` - Documentation only

### Pruning Algorithm

Run **before** each execution:
1. Compute hashes for all tasks in current recipe file
2. Load `.tasktree-state`
3. For each state entry, extract task_hash prefix
4. Remove entries whose task_hash doesn't match any current task
5. Execute tasks as needed
6. Write updated state back

### File Change Detection

**Use path + mtime only**. Do NOT use inodes—the complexity doesn't justify the marginal benefit. If a file is renamed, the task reruns (conservative and correct).

```python
input_state = {
    "src/main.rs": 1734567880,  # mtime as integer
    "src/lib.rs": 1734567850
}
```

---

## Dependency Resolution

### Implicit Input Inheritance

Tasks automatically inherit inputs from dependencies:
1. All `outputs` from dependency tasks become implicit inputs
2. All `inputs` from dependency tasks that don't declare `outputs` are inherited

### When Tasks Run

A task executes if ANY of these conditions are met:
1. Task definition hash differs from cached state
2. Any explicit `inputs` have newer mtime than `last_run`
3. Any implicit inputs (from deps) have changed
4. No cached state exists for this task+args combination
5. Task has no inputs AND no outputs (always runs)
6. Different arguments than any cached execution

### Execution Order

Use `graphlib.TopologicalSorter` to determine execution order. Process dependencies before dependents.

---

## File Imports / Composition

### Syntax

```yaml
import:
  - file: common/build.yaml
    as: build
  - file: deployment/tasks.yaml
    as: deploy

my-task:
  deps: [build.compile, deploy.setup]
  cmd: ...
```

### Import Resolution (Parse-Time)

Imported files are resolved and merged into a unified in-memory representation:

1. Parse imported YAML
2. For each task in imported file:
   - Prefix task name with namespace (`compile` → `build.compile`)
   - Set `working_dir` to imported file's parent directory (if not already set)
   - Rewrite paths in `inputs`/`outputs` relative to root project
   - Rewrite internal dependency references (`deps: [test]` → `deps: [build.test]`)
3. Merge into root task dictionary

### Import Rules

- Imported files must be **self-contained**—they cannot depend on tasks in the root file
- Dependencies are unidirectional: root can depend on imports, not vice versa
- Transitive imports: initially disallow for simplicity
- After parsing, there's no distinction between local and imported tasks—everything has explicit `working_dir` and fully qualified names

---

## CLI Commands

### Core Commands

```bash
tt <task-name> [args...]    # Execute task
tt --list                   # Brief summary of available tasks
tt --help                   # Show help
tt --init                   # Create blank tasktree.yml with commented examples
```

### Debugging Commands

```bash
tt --show <task>           # Display task definition with syntax highlighting
tt --tree <task>           # Visual dependency tree with freshness colours
tt --dry-run <task>        # Show execution plan with reasons
```

### Bare `tt` Behaviour

Display brief summary showing available task names with hint to use `--list` for details. Don't dump everything—keep it concise for quick orientation.

### `--tree` Output

```
foo
├─ build (fresh)
│  └─ lint (fresh)
└─ package (stale: inputs changed)
   └─ build (fresh)
```

**Colour scheme**:
- **Green**: Fresh, won't run
- **Red**: Stale, will run (inputs changed, definition changed, never run)
- **Yellow/Amber**: Will run because dependency is running (even though own inputs fresh)

### `--dry-run` Output

```
Execution plan for 'deploy server1':

Will execute (3 tasks):
  1. package
     - inputs changed: src/config.rs (modified 2m ago)
  2. deploy-binaries server1
     - dependency changed: package
  3. deploy server1
     - no outputs (always runs)

Will skip (2 tasks):
  - build (fresh, last run 5m ago)
  - lint (fresh, last run 5m ago)
```

### `--show` Output

Display raw task definition with YAML syntax highlighting. For imported tasks, indicate source file:

```
Task: compile (from build/tasks.yml, referenced as build.compile)

compile:
  desc: Compile the project
  cmd: cargo build --release
```

---

## CLI Implementation with Typer

Dynamic command generation from YAML task definitions is **worth the complexity** for proper `--help` and argument handling.

### Approach

Use `exec()` to dynamically create Typer commands at runtime based on parsed task definitions. Keep the dynamic generation isolated in one function with clear comments.

```python
# Pseudocode for dynamic command creation
for task_name, task_def in tasks.items():
    params = parse_args(task_def.get('args', []))
    # Generate function with proper signature
    # Add to Typer app
```

### Custom Click Types

For validated types (hostname, email, ip, etc.), create custom Click parameter types:

```python
class IPv4Type(click.ParamType):
    name = "ipv4"
    
    def convert(self, value, param, ctx):
        try:
            IPv4Address(value)
            return value
        except ValueError:
            self.fail(f"{value} is not a valid IPv4 address", param, ctx)
```

---

## Staleness Detection Logic

Factor out for reuse between execution, `--tree`, and `--dry-run`:

```python
@dataclass
class TaskStatus:
    task_name: str
    will_run: bool
    reason: str  # "fresh", "inputs_changed", "definition_changed",
                 # "never_run", "dependency_triggered", "no_outputs"
    changed_files: list[str] = field(default_factory=list)
    last_run: Optional[datetime] = None

def check_task_status(
    task: Task,
    state: State,
    dep_statuses: dict[str, TaskStatus]
) -> TaskStatus:
    # Implement staleness logic here
    # Return status without executing
    ...
```

---

## Execution Environments (Future)

Discussed but not in initial scope:

- **local** - Default shell (implemented)
- **compose** - Docker/Podman Compose for declarative volume/port/env config
- **remote** - SSH to another machine

The compose approach is preferred over raw `docker run` because it's declarative and handles volumes/ports/env elegantly. Use the Compose Specification (open standard, works with docker-compose, podman-compose, nerdctl).

---

## Design Principles

1. **Conservative over clever**: When faced with complex optimisations (like inode tracking), prefer simple reliable approaches even if they occasionally trigger unnecessary reruns.

2. **Declarative and readable**: The YAML should be self-documenting. `--show` displays raw definitions, not processed versions.

3. **Separation of concerns**: `--tree` for structure, `--dry-run` for execution plan—don't combine into one overloaded interface.

4. **Unidirectional dependencies**: Imported files cannot depend on the root file.

5. **Explicit working directories**: Every task has an explicit `working_dir` after parsing (defaults to config file's parent directory).

---

## Distribution

- Distribute via **PyPI**
- Recommend installation via **pipx** (avoids dependency conflicts)
- Both pip and pipx read from the same PyPI package—no special packaging needed

---

## What NOT to Implement

- Complex inode tracking for file moves
- Content hashing (mtime is sufficient for v1)
- Transitive imports (keep initial version simple)
- Cross-project dependencies
- Distributed/remote builds (beyond simple SSH)
- Language-specific build logic (delegate to Cargo, CMake, etc.)
