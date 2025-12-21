"""State management for tasktree incremental execution."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from .hasher import hash_task_definition


class TaskState:
    """Represents the cached state for a task execution."""

    def __init__(self, last_run: int, input_state: Dict[str, int]):
        self.last_run = last_run
        self.input_state = input_state

    @classmethod
    def from_dict(cls, data: Dict) -> "TaskState":
        """Create TaskState from dictionary representation."""
        return cls(
            last_run=data["last_run"],
            input_state=data["input_state"]
        )

    def to_dict(self) -> Dict:
        """Convert TaskState to dictionary representation."""
        return {
            "last_run": self.last_run,
            "input_state": self.input_state
        }


class StateManager:
    """Manages the .tasktree-state file for incremental execution."""

    STATE_FILE = ".tasktree-state"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.state_file = project_root / self.STATE_FILE
        self._state: Dict[str, TaskState] = {}

    def load(self) -> None:
        """Load state from the state file."""
        if not self.state_file.exists():
            self._state = {}
            return

        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                self._state = {
                    key: TaskState.from_dict(value)
                    for key, value in data.items()
                }
        except (json.JSONDecodeError, KeyError):
            # If state file is corrupted, start fresh
            self._state = {}

    def save(self) -> None:
        """Save state to the state file."""
        # Ensure parent directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            key: state.to_dict()
            for key, state in self._state.items()
        }

        with open(self.state_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_task_state(self, cache_key: str) -> Optional[TaskState]:
        """Get the cached state for a task."""
        return self._state.get(cache_key)

    def set_task_state(self, cache_key: str, state: TaskState) -> None:
        """Set the cached state for a task."""
        self._state[cache_key] = state

    def prune_invalid_entries(self, valid_task_hashes: Set[str]) -> List[str]:
        """
        Remove state entries for tasks that no longer exist.

        Args:
            valid_task_hashes: Set of valid task hash prefixes

        Returns:
            List of removed cache keys
        """
        removed_keys = []

        # Extract task hashes from cache keys
        # Cache keys are either "task_hash" or "task_hash__args_hash"
        for cache_key in list(self._state.keys()):
            task_hash = cache_key.split("__")[0]
            if task_hash not in valid_task_hashes:
                del self._state[cache_key]
                removed_keys.append(cache_key)

        return removed_keys

    def get_all_cache_keys(self) -> List[str]:
        """Get all cache keys currently in state."""
        return list(self._state.keys())

    def clear(self) -> None:
        """Clear all state."""
        self._state.clear()
        if self.state_file.exists():
            self.state_file.unlink()