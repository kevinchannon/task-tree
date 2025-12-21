"""Dependency resolution and topological sorting for tasks."""

from graphlib import TopologicalSorter
from typing import Dict, List, Set


def resolve_dependencies(tasks: Dict[str, Dict]) -> List[str]:
    """
    Resolve task dependencies and return execution order.

    Args:
        tasks: Dictionary of task_name -> task_definition

    Returns:
        List of task names in execution order

    Raises:
        ValueError: If there are circular dependencies
    """
    # Build the dependency graph
    graph = {}
    for task_name, task_def in tasks.items():
        deps = task_def.get("deps", [])
        graph[task_name] = set(deps)

    # Use TopologicalSorter to resolve dependencies
    try:
        sorter = TopologicalSorter(graph)
        return list(sorter.static_order())
    except Exception as e:
        raise ValueError(f"Dependency resolution failed: {e}")


def get_task_dependencies(task_name: str, tasks: Dict[str, Dict]) -> Set[str]:
    """
    Get all direct and transitive dependencies of a task.

    Args:
        task_name: Name of the task
        tasks: Dictionary of all tasks

    Returns:
        Set of all dependency task names
    """
    if task_name not in tasks:
        return set()

    dependencies = set()
    to_visit = [task_name]
    visited = set()

    while to_visit:
        current = to_visit.pop()
        if current in visited:
            continue

        visited.add(current)

        if current != task_name:  # Don't include the task itself
            dependencies.add(current)

        # Add dependencies to visit list
        task_def = tasks.get(current, {})
        deps = task_def.get("deps", [])
        to_visit.extend(deps)

    return dependencies


def validate_dependencies(tasks: Dict[str, Dict]) -> None:
    """
    Validate that all task dependencies exist.

    Args:
        tasks: Dictionary of task_name -> task_definition

    Raises:
        ValueError: If any dependency references a non-existent task
    """
    missing_deps = []

    for task_name, task_def in tasks.items():
        deps = task_def.get("deps", [])
        for dep in deps:
            if dep not in tasks:
                missing_deps.append(f"Task '{task_name}' depends on '{dep}' which does not exist")

    if missing_deps:
        raise ValueError("Missing task dependencies:\n" + "\n".join(missing_deps))