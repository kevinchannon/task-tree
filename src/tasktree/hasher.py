"""Task and argument hashing utilities for incremental execution."""

import hashlib
import json
from typing import Any, Dict, List, Optional


def hash_task_definition(task_def: Dict[str, Any]) -> str:
    """
    Generate a hash for a task definition.

    The hash includes:
    - cmd: The command to execute
    - outputs: Declared output files
    - working_dir: Execution directory
    - args: Parameter definitions (names and types)

    The hash excludes:
    - deps: Only affects scheduling order
    - inputs: Tracked separately via timestamps
    - desc: Documentation only
    """
    # Extract the components that affect task execution
    hash_components = {
        "cmd": task_def.get("cmd", ""),
        "outputs": sorted(task_def.get("outputs", [])),
        "working_dir": task_def.get("working_dir", ""),
        "args": sorted(task_def.get("args", [])),
    }

    # Convert to JSON string for consistent hashing
    hash_string = json.dumps(hash_components, sort_keys=True)

    # Generate SHA256 hash and return first 8 characters
    return hashlib.sha256(hash_string.encode()).hexdigest()[:8]


def hash_arguments(args: Optional[Dict[str, Any]]) -> str:
    """
    Generate a hash for task arguments.

    Args:
        args: Dictionary of argument name -> value mappings

    Returns:
        8-character hex hash of the arguments
    """
    if not args:
        return ""

    # Sort arguments by name for consistent hashing
    sorted_args = {k: str(v) for k, v in sorted(args.items())}

    # Convert to JSON string
    hash_string = json.dumps(sorted_args, sort_keys=True)

    # Generate hash
    return hashlib.sha256(hash_string.encode()).hexdigest()[:8]


def make_cache_key(task_hash: str, args_hash: str = "") -> str:
    """
    Generate a cache key for state storage.

    Format:
    - Non-parameterised tasks: task_hash (8-char hex)
    - Parameterised tasks: task_hash__args_hash

    Args:
        task_hash: 8-character task definition hash
        args_hash: 8-character arguments hash (empty for non-parameterised tasks)

    Returns:
        Cache key string
    """
    if args_hash:
        return f"{task_hash}__{args_hash}"
    return task_hash