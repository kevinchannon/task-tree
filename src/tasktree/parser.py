"""YAML parsing and task definition handling for tasktree."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


class TaskDefinition:
    """Represents a parsed task definition."""

    def __init__(self, name: str, definition: Dict[str, Any], source_file: Optional[Path] = None):
        self.name = name
        self.definition = definition
        self.source_file = source_file

    @property
    def cmd(self) -> str:
        """Get the command to execute."""
        return self.definition.get("cmd", "")

    @property
    def deps(self) -> List[str]:
        """Get task dependencies."""
        return self.definition.get("deps", [])

    @property
    def inputs(self) -> List[str]:
        """Get input file patterns."""
        return self.definition.get("inputs", [])

    @property
    def outputs(self) -> List[str]:
        """Get output file patterns."""
        return self.definition.get("outputs", [])

    @property
    def working_dir(self) -> Optional[str]:
        """Get working directory."""
        return self.definition.get("working_dir")

    @property
    def args(self) -> List[str]:
        """Get argument definitions."""
        return self.definition.get("args", [])

    @property
    def desc(self) -> Optional[str]:
        """Get task description."""
        return self.definition.get("desc")


class TaskParser:
    """Parses tasktree YAML files and handles imports."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def find_config_file(self) -> Optional[Path]:
        """Find the tasktree configuration file."""
        candidates = ["tasktree.yaml", "tt.yaml"]
        for candidate in candidates:
            config_file = self.project_root / candidate
            if config_file.exists():
                return config_file
        return None

    def parse_config(self, config_file: Optional[Path] = None) -> Dict[str, TaskDefinition]:
        """
        Parse the tasktree configuration file and all imports.

        Returns:
            Dictionary of task_name -> TaskDefinition
        """
        if config_file is None:
            config_file = self.find_config_file()

        if config_file is None:
            raise FileNotFoundError("No tasktree.yaml or tt.yaml found in project root")

        # Parse the main config file
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f) or {}

        # Process imports first
        imported_tasks = self._process_imports(data.get("import", []), config_file.parent)

        # Process local tasks
        local_tasks = self._process_tasks(data, config_file.parent)

        # Merge imported and local tasks
        all_tasks = {**imported_tasks, **local_tasks}

        return all_tasks

    def _process_imports(self, imports: List[Dict], base_dir: Path) -> Dict[str, TaskDefinition]:
        """Process imported task files with namespacing."""
        imported_tasks = {}

        for import_def in imports:
            file_path = import_def.get("file")
            namespace = import_def.get("as")

            if not file_path or not namespace:
                raise ValueError(f"Import definition must have 'file' and 'as' fields: {import_def}")

            # Resolve the import file path
            import_file = (base_dir / file_path).resolve()

            if not import_file.exists():
                raise FileNotFoundError(f"Imported file not found: {import_file}")

            # Parse the imported file
            with open(import_file, 'r') as f:
                import_data = yaml.safe_load(f) or {}

            # Process tasks with namespace prefix
            namespaced_tasks = self._process_tasks(
                import_data,
                import_file.parent,
                namespace=namespace,
                source_file=import_file
            )

            # Check for conflicts
            conflicts = set(imported_tasks.keys()) & set(namespaced_tasks.keys())
            if conflicts:
                raise ValueError(f"Task name conflicts in imports: {conflicts}")

            imported_tasks.update(namespaced_tasks)

        return imported_tasks

    def _process_tasks(
        self,
        data: Dict,
        base_dir: Path,
        namespace: str = "",
        source_file: Optional[Path] = None
    ) -> Dict[str, TaskDefinition]:
        """Process tasks from a YAML data structure."""
        tasks = {}

        for key, value in data.items():
            # Skip special keys like "import"
            if key == "import":
                continue

            # Skip non-dict values (they're not task definitions)
            if not isinstance(value, dict):
                continue

            # Apply namespace prefix
            task_name = f"{namespace}.{key}" if namespace else key

            # Set default working directory if not specified
            if "working_dir" not in value:
                # Make working directory relative to project root
                try:
                    relative_dir = base_dir.relative_to(self.project_root)
                    value["working_dir"] = str(relative_dir) if str(relative_dir) != "." else ""
                except ValueError:
                    # If we can't make it relative, use empty string (project root)
                    value["working_dir"] = ""

            # Rewrite relative paths in inputs/outputs to be relative to project root
            value = self._rewrite_paths(value, base_dir)

            # Create TaskDefinition
            task_def = TaskDefinition(task_name, value, source_file)
            tasks[task_name] = task_def

        return tasks

    def _rewrite_paths(self, task_def: Dict, base_dir: Path) -> Dict:
        """Rewrite relative paths in inputs/outputs to be relative to project root."""
        result = task_def.copy()

        # Helper function to rewrite a path
        def rewrite_path(path_str: str) -> str:
            path = Path(path_str)
            if not path.is_absolute():
                # Make path relative to project root
                try:
                    return str((base_dir / path).relative_to(self.project_root))
                except ValueError:
                    # If we can't make it relative, keep the original
                    return path_str
            return path_str

        # Rewrite inputs
        if "inputs" in result:
            result["inputs"] = [rewrite_path(p) for p in result["inputs"]]

        # Rewrite outputs
        if "outputs" in result:
            result["outputs"] = [rewrite_path(p) for p in result["outputs"]]

        return result

    def validate_task_definitions(self, tasks: Dict[str, TaskDefinition]) -> None:
        """Validate task definitions for required fields and correctness."""
        errors = []

        for task_name, task_def in tasks.items():
            # Check required cmd field
            if not task_def.cmd:
                errors.append(f"Task '{task_name}' is missing required 'cmd' field")

            # Validate argument definitions
            for arg_def in task_def.args:
                if not self._is_valid_arg_definition(arg_def):
                    errors.append(f"Task '{task_name}' has invalid argument definition: '{arg_def}'")

        if errors:
            raise ValueError("Task definition validation errors:\n" + "\n".join(errors))

    def _is_valid_arg_definition(self, arg_def: str) -> bool:
        """Check if an argument definition is valid."""
        # Format: name:type=default (type and default are optional)
        parts = arg_def.split(":")

        if len(parts) > 3:
            return False

        # Name part must be present and valid identifier
        name = parts[0].strip()
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            return False

        # If type is specified, check it's valid
        if len(parts) >= 2:
            type_part = parts[1].strip()
            # Basic check - could be enhanced
            if not type_part:
                return False

        # If default is specified, it should be non-empty
        if len(parts) == 3:
            default_part = parts[2].strip()
            if not default_part:
                return False

        return True