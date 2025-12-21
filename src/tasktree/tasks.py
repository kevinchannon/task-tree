"""Task execution coordination."""

from pathlib import Path
from typing import Dict, List, Optional

from .executor import TaskExecutor
from .graph import resolve_dependencies
from .parser import TaskDefinition
from .state import StateManager


def execute_task(
    task_name: str,
    tasks: Dict[str, TaskDefinition],
    project_root: Path,
    state_manager: StateManager,
    args: Optional[Dict[str, str]] = None
) -> int:
    """
    Execute a single task with dependency resolution and incremental execution.

    Args:
        task_name: Name of the task to execute
        tasks: All available tasks
        project_root: Project root directory
        state_manager: State manager instance
        args: Task arguments

    Returns:
        Exit code (0 for success)
    """
    if task_name not in tasks:
        raise ValueError(f"Task '{task_name}' not found")

    executor = TaskExecutor(project_root, state_manager)

    # Get execution order for this task and its dependencies
    task_deps = _get_task_and_dependencies(task_name, tasks)
    execution_order = resolve_dependencies({name: tasks[name].definition for name in task_deps})

    # Execute tasks in order
    for current_task_name in execution_order:
        if current_task_name not in task_deps:
            continue

        task_def = tasks[current_task_name]

        # Check if task needs to run
        status = executor.check_task_status(task_def, args if current_task_name == task_name else None)

        if status.will_run:
            print(f"Running task '{current_task_name}'...")
            exit_code = executor.execute_task(task_def, args if current_task_name == task_name else None)
            if exit_code != 0:
                return exit_code
        else:
            print(f"Skipping task '{current_task_name}' ({status.reason})")

    return 0


def execute_tasks(
    task_names: List[str],
    tasks: Dict[str, TaskDefinition],
    project_root: Path,
    state_manager: StateManager,
    args_list: Optional[List[Dict[str, str]]] = None
) -> int:
    """
    Execute multiple tasks.

    Args:
        task_names: Names of tasks to execute
        tasks: All available tasks
        project_root: Project root directory
        state_manager: State manager instance
        args_list: List of argument dictionaries for each task

    Returns:
        Exit code (0 for success)
    """
    if args_list is None:
        args_list = [{}] * len(task_names)

    if len(args_list) != len(task_names):
        raise ValueError("Number of argument sets must match number of tasks")

    for task_name, args in zip(task_names, args_list):
        exit_code = execute_task(task_name, tasks, project_root, state_manager, args)
        if exit_code != 0:
            return exit_code

    return 0


def _get_task_and_dependencies(task_name: str, tasks: Dict[str, TaskDefinition]) -> List[str]:
    """Get a task and all its dependencies."""
    result = []
    visited = set()

    def visit(name):
        if name in visited:
            return
        visited.add(name)

        if name not in tasks:
            raise ValueError(f"Task '{name}' not found")

        # Add dependencies first
        task_def = tasks[name]
        for dep in task_def.deps:
            visit(dep)

        # Then add this task
        result.append(name)

    visit(task_name)
    return result
