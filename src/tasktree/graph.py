"""Dependency resolution using topological sorting."""

from graphlib import TopologicalSorter
from pathlib import Path

from tasktree.parser import Recipe, Task


class CycleError(Exception):
    """Raised when a dependency cycle is detected."""

    pass


class TaskNotFoundError(Exception):
    """Raised when a task dependency doesn't exist."""

    pass


def resolve_execution_order(recipe: Recipe, target_task: str) -> list[str]:
    """Resolve execution order for a task and its dependencies.

    Args:
        recipe: Parsed recipe containing all tasks
        target_task: Name of the task to execute

    Returns:
        List of task names in execution order (dependencies first)

    Raises:
        TaskNotFoundError: If target task or any dependency doesn't exist
        CycleError: If a dependency cycle is detected
    """
    if target_task not in recipe.tasks:
        raise TaskNotFoundError(f"Task not found: {target_task}")

    # Build dependency graph
    graph: dict[str, set[str]] = {}

    def build_graph(task_name: str) -> None:
        """Recursively build dependency graph."""
        if task_name in graph:
            # Already processed
            return

        task = recipe.tasks.get(task_name)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {task_name}")

        # Add task to graph with its dependencies
        graph[task_name] = set(task.deps)

        # Recursively process dependencies
        for dep in task.deps:
            build_graph(dep)

    # Build graph starting from target task
    build_graph(target_task)

    # Use TopologicalSorter to resolve execution order
    try:
        sorter = TopologicalSorter(graph)
        return list(sorter.static_order())
    except ValueError as e:
        raise CycleError(f"Dependency cycle detected: {e}")


def get_implicit_inputs(recipe: Recipe, task: Task) -> list[str]:
    """Get implicit inputs for a task based on its dependencies.

    Tasks automatically inherit inputs from dependencies:
    1. All outputs from dependency tasks become implicit inputs
    2. All inputs from dependency tasks that don't declare outputs are inherited
    3. If task uses a Docker environment, Docker artifacts become implicit inputs:
       - Dockerfile
       - .dockerignore (if present)
       - Special markers for context directory and base image digests

    Args:
        recipe: Parsed recipe containing all tasks
        task: Task to get implicit inputs for

    Returns:
        List of glob patterns for implicit inputs, including Docker-specific markers
    """
    implicit_inputs = []

    # Inherit from dependencies
    for dep_name in task.deps:
        dep_task = recipe.tasks.get(dep_name)
        if dep_task is None:
            continue

        # If dependency has outputs, inherit them
        if dep_task.outputs:
            implicit_inputs.extend(dep_task.outputs)
        # If dependency has no outputs, inherit its inputs
        elif dep_task.inputs:
            implicit_inputs.extend(dep_task.inputs)

    # Add Docker-specific implicit inputs if task uses Docker environment
    env_name = task.env or recipe.default_env
    if env_name:
        env = recipe.get_environment(env_name)
        if env and env.dockerfile:
            # Add Dockerfile as input
            implicit_inputs.append(env.dockerfile)

            # Add .dockerignore if it exists in context directory
            context_path = recipe.project_root / env.context
            dockerignore_path = context_path / ".dockerignore"
            if dockerignore_path.exists():
                relative_dockerignore = str(
                    dockerignore_path.relative_to(recipe.project_root)
                )
                implicit_inputs.append(relative_dockerignore)

            # Add special markers for context directory and digest tracking
            # These are tracked differently in state management (not file paths)
            # The executor will handle these specially
            implicit_inputs.append(f"_docker_context_{env.context}")
            implicit_inputs.append(f"_docker_dockerfile_{env.dockerfile}")

    return implicit_inputs


def build_dependency_tree(recipe: Recipe, target_task: str) -> dict:
    """Build a tree structure representing dependencies for visualization.

    Note: This builds a true tree representation where shared dependencies may
    appear multiple times. Each dependency is shown in the context of its parent,
    allowing the full dependency path to be visible from any node.

    Args:
        recipe: Parsed recipe containing all tasks
        target_task: Name of the task to build tree for

    Returns:
        Nested dictionary representing the dependency tree
    """
    if target_task not in recipe.tasks:
        raise TaskNotFoundError(f"Task not found: {target_task}")

    current_path = set()  # Track current recursion path for cycle detection

    def build_tree(task_name: str) -> dict:
        """Recursively build dependency tree."""
        task = recipe.tasks.get(task_name)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {task_name}")

        # Detect cycles in current recursion path
        if task_name in current_path:
            return {"name": task_name, "deps": [], "cycle": True}

        current_path.add(task_name)

        tree = {
            "name": task_name,
            "deps": [build_tree(dep) for dep in task.deps],
        }

        current_path.remove(task_name)

        return tree

    return build_tree(target_task)
