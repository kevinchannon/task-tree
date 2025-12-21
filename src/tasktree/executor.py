"""Task execution and staleness detection logic."""

import glob
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from .graph import get_task_dependencies
from .hasher import hash_arguments, make_cache_key
from .parser import TaskDefinition
from .state import StateManager, TaskState


@dataclass
class TaskStatus:
    """Status information for a task."""

    task_name: str
    will_run: bool
    reason: str
    changed_files: Optional[List[str]] = None
    last_run: Optional[int] = None

    def __post_init__(self):
        if self.changed_files is None:
            self.changed_files = []


class TaskExecutor:
    """Handles task execution and staleness detection."""

    def __init__(self, project_root: Path, state_manager: StateManager):
        self.project_root = project_root
        self.state_manager = state_manager

    def check_task_status(
        self,
        task_def: TaskDefinition,
        args: Optional[Dict[str, str]] = None,
        dep_statuses: Optional[Dict[str, TaskStatus]] = None
    ) -> TaskStatus:
        """
        Check if a task needs to run based on its definition and current state.

        Args:
            task_def: The task definition
            args: Task arguments (if any)
            dep_statuses: Status of dependency tasks

        Returns:
            TaskStatus indicating whether the task will run and why
        """
        if dep_statuses is None:
            dep_statuses = {}

        # Generate cache key
        task_hash = self._get_task_hash(task_def)
        args_hash = hash_arguments(args) if args else ""
        cache_key = make_cache_key(task_hash, args_hash)

        # Get cached state
        cached_state = self.state_manager.get_task_state(cache_key)

        # Check various conditions that would require running the task

        # 1. Task has never been run
        if cached_state is None:
            return TaskStatus(
                task_name=task_def.name,
                will_run=True,
                reason="never_run"
            )

        # 2. Task definition has changed
        if self._task_definition_changed(task_def, cached_state):
            return TaskStatus(
                task_name=task_def.name,
                will_run=True,
                reason="definition_changed"
            )

        # 3. Explicit inputs have changed
        input_changes = self._get_input_changes(task_def, cached_state)
        if input_changes:
            return TaskStatus(
                task_name=task_def.name,
                will_run=True,
                reason="inputs_changed",
                changed_files=input_changes
            )

        # 4. Outputs don't exist
        if task_def.outputs:
            for output_pattern in task_def.outputs:
                output_path = self.project_root / output_pattern
                if not output_path.exists():
                    return TaskStatus(
                        task_name=task_def.name,
                        will_run=True,
                        reason="outputs_missing",
                        changed_files=[output_pattern]
                    )

        # 4. Any dependency has run
        for dep_name, dep_status in dep_statuses.items():
            if dep_status.will_run:
                return TaskStatus(
                    task_name=task_def.name,
                    will_run=True,
                    reason="dependency_triggered"
                )

        # 5. Task has no inputs or outputs (always runs)
        if not task_def.inputs and not task_def.outputs:
            return TaskStatus(
                task_name=task_def.name,
                will_run=True,
                reason="no_outputs"
            )

        # Task is fresh
        return TaskStatus(
            task_name=task_def.name,
            will_run=False,
            reason="fresh",
            last_run=cached_state.last_run
        )

    def execute_task(
        self,
        task_def: TaskDefinition,
        args: Optional[Dict[str, str]] = None
    ) -> int:
        """
        Execute a task and update its state.

        Args:
            task_def: The task definition to execute
            args: Task arguments

        Returns:
            Exit code from the command
        """
        # Prepare the command
        cmd = self._prepare_command(task_def.cmd, args)

        # Set working directory
        if task_def.working_dir and task_def.working_dir.strip():
            working_dir = self.project_root / task_def.working_dir
        else:
            working_dir = self.project_root

        # Execute the command
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=working_dir,
                capture_output=False  # Let output go to stdout/stderr
            )
        except Exception as e:
            print(f"Error executing task '{task_def.name}': {e}")
            return 1

        # Update state if command succeeded
        if result.returncode == 0:
            self._update_task_state(task_def, args)

        return result.returncode

    def _get_task_hash(self, task_def: TaskDefinition) -> str:
        """Get the hash for a task definition."""
        from .hasher import hash_task_definition
        return hash_task_definition(task_def.definition)

    def _task_definition_changed(self, task_def: TaskDefinition, cached_state: TaskState) -> bool:
        """Check if task definition has changed since last run."""
        # For now, we'll assume definition changes are detected by hash comparison
        # This would be checked during state pruning
        return False

    def _get_input_changes(self, task_def: TaskDefinition, cached_state: TaskState) -> List[str]:
        """Get list of input files that have changed since last run."""
        changed_files = []

        # Get all input files (explicit + implicit from dependencies)
        all_inputs = self._get_all_input_files(task_def)

        for input_file in all_inputs:
            input_path = self.project_root / input_file

            # Check if file exists
            if not input_path.exists():
                # File was deleted - consider it changed
                changed_files.append(input_file)
                continue

            # Get current mtime
            current_mtime = int(input_path.stat().st_mtime)

            # Check if mtime has changed
            cached_mtime = cached_state.input_state.get(input_file)
            if cached_mtime is None or current_mtime > cached_mtime:
                changed_files.append(input_file)

        return changed_files

    def _get_output_changes(self, task_def: TaskDefinition, cached_state: TaskState) -> List[str]:
        """Check if outputs are missing or stale."""
        missing_outputs = []

        for output_pattern in task_def.outputs:
            # For now, treat output patterns as literal files
            # TODO: Implement glob expansion for outputs
            output_path = self.project_root / output_pattern

            if not output_path.exists():
                missing_outputs.append(output_pattern)
            else:
                # Check if output is older than last run
                output_mtime = int(output_path.stat().st_mtime)
                if output_mtime < cached_state.last_run:
                    missing_outputs.append(output_pattern)

        return missing_outputs

    def _get_all_input_files(self, task_def: TaskDefinition) -> Set[str]:
        """Get all input files for a task (explicit + implicit)."""
        # For now, just return explicit inputs
        # In a full implementation, this would also include outputs from dependencies
        inputs = set()

        # Add explicit inputs
        for pattern in task_def.inputs:
            matches = glob.glob(str(self.project_root / pattern))
            inputs.update(str(Path(p).relative_to(self.project_root)) for p in matches)

        return inputs

    def _prepare_command(self, cmd: str, args: Optional[Dict[str, str]]) -> str:
        """Prepare command string with argument substitution."""
        if not args:
            return cmd

        # Substitute {{arg_name}} placeholders
        result = cmd
        for arg_name, arg_value in args.items():
            placeholder = "{{" + arg_name + "}}"
            result = result.replace(placeholder, str(arg_value))

        return result

    def _update_task_state(self, task_def: TaskDefinition, args: Optional[Dict[str, str]]) -> None:
        """Update the cached state for a task after successful execution."""
        # Generate cache key
        task_hash = self._get_task_hash(task_def)
        args_hash = hash_arguments(args) if args else ""
        cache_key = make_cache_key(task_hash, args_hash)

        # Get current timestamp
        now = int(time.time())

        # Build input state
        input_state = {}
        all_inputs = self._get_all_input_files(task_def)

        for input_file in all_inputs:
            input_path = self.project_root / input_file
            if input_path.exists():
                input_state[input_file] = int(input_path.stat().st_mtime)

        # Update state
        state = TaskState(last_run=now, input_state=input_state)
        self.state_manager.set_task_state(cache_key, state)
        self.state_manager.save()