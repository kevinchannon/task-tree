"""Command-line interface for tasktree."""

import sys
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from .executor import TaskExecutor, TaskStatus
from .graph import resolve_dependencies, validate_dependencies
from .hasher import hash_task_definition
from .parser import TaskDefinition, TaskParser
from .state import StateManager

app = typer.Typer()
console = Console()


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path.cwd()


def load_tasks() -> Dict[str, TaskDefinition]:
    """Load and parse task definitions."""
    project_root = get_project_root()
    parser = TaskParser(project_root)

    try:
        tasks = parser.parse_config()
        parser.validate_task_definitions(tasks)
        validate_dependencies({name: task.definition for name, task in tasks.items()})
        return tasks
    except Exception as e:
        console.print(f"[red]Error loading tasks:[/red] {e}")
        raise typer.Exit(1)


def setup_state_manager() -> StateManager:
    """Set up the state manager."""
    project_root = get_project_root()
    state_manager = StateManager(project_root)
    state_manager.load()

    # Prune invalid state entries
    valid_hashes = {hash_task_definition(task.definition) for task in load_tasks().values()}
    removed = state_manager.prune_invalid_entries(valid_hashes)
    if removed:
        state_manager.save()

    return state_manager


@app.command()
def list():
    """List all available tasks."""
    show_task_list()


@app.command()
def show(task_name: str):
    """Show task definition."""
    show_task_definition(task_name)


@app.command()
def tree(task_name: str):
    """Show dependency tree."""
    show_dependency_tree(task_name)


@app.command()
def dry_run(task_name: str):
    """Show execution plan."""
    show_execution_plan(task_name)


@app.command()
def init():
    """Create a sample tasktree.yaml."""
    create_sample_config()


@app.callback()
def main(ctx: typer.Context):
    """Task Tree (tt) - Intelligent task automation tool."""
    # If no command provided, show brief help
    if not ctx.invoked_subcommand:
        show_brief_help()


def create_sample_config():
    """Create a sample tasktree.yaml file."""
    config_file = get_project_root() / "tasktree.yaml"

    if config_file.exists():
        console.print(f"[yellow]tasktree.yaml already exists at {config_file}[/yellow]")
        return

    sample_config = """# Task Tree Configuration
# See https://tasktree.dev for full documentation

build:
  desc: Compile the application
  outputs: [target/release/app]
  cmd: cargo build --release

test:
  desc: Run tests
  deps: [build]
  cmd: cargo test

deploy:
  desc: Deploy to production
  deps: [build]
  args: [environment:str=prod, version:str]
  cmd: |
    echo "Deploying {{version}} to {{environment}}"
    # Add your deployment commands here
"""

    config_file.write_text(sample_config)
    console.print(f"[green]Created sample tasktree.yaml at {config_file}[/green]")


def show_brief_help():
    """Show brief help information."""
    console.print("[bold]Task Tree (tt)[/bold] - Intelligent task automation")
    console.print()
    console.print("Available tasks:")
    tasks = load_tasks()
    if tasks:
        for name in sorted(tasks.keys())[:5]:  # Show first 5 tasks
            task = tasks[name]
            desc = task.desc or "No description"
            console.print(f"  [cyan]{name}[/cyan] - {desc}")
        if len(tasks) > 5:
            console.print(f"  ... and {len(tasks) - 5} more tasks")
    else:
        console.print("  No tasks defined")
    console.print()
    console.print("Use [bold]tt --list[/bold] to see all tasks, or [bold]tt <task-name>[/bold] to run a task")


def show_task_list():
    """Show a detailed list of all tasks."""
    tasks = load_tasks()

    if not tasks:
        console.print("[yellow]No tasks defined[/yellow]")
        return

    table = Table(title="Available Tasks")
    table.add_column("Task", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Dependencies", style="yellow")

    for name in sorted(tasks.keys()):
        task = tasks[name]
        desc = task.desc or ""
        deps = ", ".join(task.deps) if task.deps else ""
        table.add_row(name, desc, deps)

    console.print(table)


def show_task_definition(task_name: str):
    """Show the definition of a specific task."""
    tasks = load_tasks()

    if task_name not in tasks:
        console.print(f"[red]Task '{task_name}' not found[/red]")
        return

    task = tasks[task_name]

    console.print(f"[bold]Task:[/bold] {task_name}")
    if task.source_file:
        console.print(f"[dim]From: {task.source_file}[/dim]")
    console.print()

    # Display the raw YAML definition
    import yaml
    console.print(yaml.dump(task.definition, default_flow_style=False))


def show_dependency_tree(task_name: str):
    """Show dependency tree for a task."""
    tasks = load_tasks()

    if task_name not in tasks:
        console.print(f"[red]Task '{task_name}' not found[/red]")
        return

    # Build dependency tree
    tree = Tree(f"[bold]{task_name}[/bold]")

    def add_dependencies(node, task_name, visited=None):
        if visited is None:
            visited = set()
        if task_name in visited:
            return
        visited.add(task_name)

        task = tasks.get(task_name)
        if not task:
            return

        for dep in task.deps:
            dep_node = node.add(f"[cyan]{dep}[/cyan]")
            add_dependencies(dep_node, dep, visited.copy())

    add_dependencies(tree, task_name)
    console.print(tree)


def show_execution_plan(task_name: str):
    """Show execution plan for a task."""
    tasks = load_tasks()
    state_manager = setup_state_manager()
    executor = TaskExecutor(get_project_root(), state_manager)

    if task_name not in tasks:
        console.print(f"[red]Task '{task_name}' not found[/red]")
        return

    # Get execution order
    execution_order = resolve_dependencies({name: task.definition for name, task in tasks.items()})

    # Filter to tasks that would actually run
    relevant_tasks = set()
    to_check = [task_name]

    while to_check:
        current = to_check.pop()
        if current in relevant_tasks:
            continue
        relevant_tasks.add(current)

        task = tasks[current]
        to_check.extend(task.deps)

    # Check status for each relevant task
    task_statuses = {}
    for task_name in execution_order:
        if task_name not in relevant_tasks:
            continue

        task = tasks[task_name]
        status = executor.check_task_status(task)
        task_statuses[task_name] = status

    # Display execution plan
    console.print(f"[bold]Execution plan for '{task_name}':[/bold]")
    console.print()

    will_execute = [status for status in task_statuses.values() if status.will_run]
    will_skip = [status for status in task_statuses.values() if not status.will_run]

    if will_execute:
        console.print(f"[red]Will execute ({len(will_execute)} tasks):[/red]")
        for status in will_execute:
            console.print(f"  • {status.task_name}")
            console.print(f"    [dim]- {status.reason}[/dim]")
            if status.changed_files:
                for changed_file in status.changed_files:
                    console.print(f"    [dim]- {changed_file} changed[/dim]")
        console.print()

    if will_skip:
        console.print(f"[green]Will skip ({len(will_skip)} tasks):[/green]")
        for status in will_skip:
            reason = f"fresh (last run {status.last_run} ago)" if status.last_run else "fresh"
            console.print(f"  • {status.task_name} [dim]({reason})[/dim]")


def create_dynamic_commands():
    """Create dynamic Typer commands from task definitions."""
    tasks = load_tasks()

    for task_name, task_def in tasks.items():
        # Parse arguments
        args_info = parse_task_args(task_def.args)

        # Create the command function dynamically
        def create_command_func(task_name=task_name, task_def=task_def, args_info=args_info):
            def command_func(**kwargs):
                return execute_task_command(task_name, task_def, args_info, kwargs)
            return command_func

        # Add the command to the app
        command_func = create_command_func()

        # Set function name and docstring
        command_func.__name__ = f"cmd_{task_name.replace('-', '_').replace('.', '_')}"
        command_func.__doc__ = task_def.desc or f"Execute task '{task_name}'"

        # Add parameters to the function
        import inspect
        sig = inspect.signature(command_func)

        # Build new signature with parameters
        params = []
        for arg_name, arg_info in args_info.items():
            param = inspect.Parameter(
                arg_name,
                inspect.Parameter.KEYWORD_ONLY,
                default=arg_info["default"],
                annotation=arg_info["type"]
            )
            params.append(param)

        new_sig = sig.replace(parameters=params)
        command_func.__signature__ = new_sig

        # Register the command
        app.command(name=task_name)(command_func)


def parse_task_args(args_defs: List[str]) -> Dict:
    """Parse task argument definitions."""
    from .types import get_param_type

    args_info = {}

    for arg_def in args_defs:
        # Parse name:type=default format
        parts = arg_def.split(":")
        name = parts[0].strip()

        type_name = "str"  # default
        default = ...  # no default

        if len(parts) >= 2:
            type_part = parts[1].strip()
            if "=" in type_part:
                type_name, default_str = type_part.split("=", 1)
                type_name = type_name.strip()
                default = parse_default_value(default_str.strip(), type_name)
            else:
                type_name = type_part

        if len(parts) == 3:
            default = parse_default_value(parts[2].strip(), type_name)

        args_info[name] = {
            "type": get_param_type(type_name),
            "default": default
        }

    return args_info


def parse_default_value(value_str: str, type_name: str):
    """Parse a default value string based on type."""
    if type_name == "str":
        return value_str
    elif type_name == "int":
        return int(value_str)
    elif type_name == "float":
        return float(value_str)
    elif type_name == "bool":
        return value_str.lower() in ("true", "yes", "1", "on")
    else:
        # For other types, keep as string
        return value_str


def execute_task_command(task_name: str, task_def: TaskDefinition, args_info: Dict, kwargs: Dict):
    """Execute a task command with given arguments."""
    # Load state and executor
    state_manager = setup_state_manager()
    executor = TaskExecutor(get_project_root(), state_manager)

    # Filter out arguments that weren't provided (use defaults)
    provided_args = {k: v for k, v in kwargs.items() if k in args_info}

    # Execute the task
    exit_code = executor.execute_task(task_def, provided_args)

    if exit_code != 0:
        console.print(f"[red]Task '{task_name}' failed with exit code {exit_code}[/red]")
        raise typer.Exit(exit_code)
    else:
        console.print(f"[green]Task '{task_name}' completed successfully[/green]")


# Initialize dynamic commands
try:
    create_dynamic_commands()
except Exception as e:
    # If task loading fails, continue with basic commands
    pass


if __name__ == "__main__":
    app()