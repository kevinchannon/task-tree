"""Unit tests for environment definition tracking."""

import unittest
from dataclasses import field
from pathlib import Path

from tasktree.executor import Executor
from tasktree.hasher import hash_environment_definition
from tasktree.parser import Environment, Recipe, Task
from tasktree.state import StateManager, TaskState


class TestHashEnvironmentDefinition(unittest.TestCase):
    """Test environment definition hashing."""

    def test_hash_environment_definition_deterministic(self):
        """Test that hashing same environment twice produces same hash."""
        env = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
            preamble="set -e",
        )

        hash1 = hash_environment_definition(env)
        hash2 = hash_environment_definition(env)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)  # 16-character hash

    def test_hash_environment_definition_shell_change(self):
        """Test that changing shell produces different hash."""
        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
        )
        env2 = Environment(
            name="test",
            shell="/bin/zsh",
            args=["-c"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_args_change(self):
        """Test that changing args produces different hash."""
        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
        )
        env2 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-e", "-c"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_preamble_change(self):
        """Test that changing preamble produces different hash."""
        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
            preamble="",
        )
        env2 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
            preamble="set -e",
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_docker_fields(self):
        """Test that changing Docker fields produces different hash."""
        env1 = Environment(
            name="test",
            dockerfile="Dockerfile",
            context=".",
        )
        env2 = Environment(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            volumes=["./src:/app/src"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_args_order_independent(self):
        """Test that args order doesn't matter (they're sorted)."""
        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-e", "-c"],
        )
        env2 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c", "-e"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertEqual(hash1, hash2)


class TestCheckEnvironmentChanged(unittest.TestCase):
    """Test environment change detection in executor."""

    def setUp(self):
        """Set up test environment."""
        self.project_root = Path("/tmp/test")
        self.env = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
        )
        self.recipe = Recipe(
            tasks={},
            project_root=self.project_root,
            environments={"test": self.env},
        )
        self.state_manager = StateManager(self.project_root)
        self.executor = Executor(self.recipe, self.state_manager)

    def test_check_environment_changed_no_env(self):
        """Test that platform default (no env) returns False."""
        task = Task(name="test", cmd="echo test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_environment_changed(task, cached_state, "")

        self.assertFalse(result)

    def test_check_environment_changed_first_run(self):
        """Test that missing cached hash returns True."""
        task = Task(name="test", cmd="echo test", env="test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_environment_changed(task, cached_state, "test")

        self.assertTrue(result)

    def test_check_environment_changed_unchanged(self):
        """Test that matching hash returns False."""
        task = Task(name="test", cmd="echo test", env="test")

        # Compute hash and store in cached state
        env_hash = hash_environment_definition(self.env)
        cached_state = TaskState(
            last_run=123.0, input_state={f"_env_hash_test": env_hash}
        )

        result = self.executor._check_environment_changed(task, cached_state, "test")

        self.assertFalse(result)

    def test_check_environment_changed_shell_modified(self):
        """Test that modified shell is detected."""
        task = Task(name="test", cmd="echo test", env="test")

        # Store old hash
        old_env = Environment(name="test", shell="/bin/bash", args=["-c"])
        old_hash = hash_environment_definition(old_env)
        cached_state = TaskState(
            last_run=123.0, input_state={f"_env_hash_test": old_hash}
        )

        # Recipe now has modified environment
        # (self.env has same shell, but let's modify the recipe)
        self.recipe.environments["test"] = Environment(
            name="test", shell="/bin/zsh", args=["-c"]
        )

        result = self.executor._check_environment_changed(task, cached_state, "test")

        self.assertTrue(result)

    def test_check_environment_changed_deleted_env(self):
        """Test that deleted environment returns True."""
        task = Task(name="test", cmd="echo test", env="test")
        cached_state = TaskState(
            last_run=123.0, input_state={f"_env_hash_test": "somehash"}
        )

        # Delete environment from recipe
        self.recipe.environments = {}

        result = self.executor._check_environment_changed(task, cached_state, "test")

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
