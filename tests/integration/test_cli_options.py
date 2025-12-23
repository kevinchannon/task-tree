"""Integration tests for CLI options vs user task names."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestCLIOptionsNoClash(unittest.TestCase):
    """Test that CLI options (--show, --tree, etc.) don't clash with user task names."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_user_tasks_with_builtin_names(self):
        """Test that user can create tasks named 'show', 'tree', 'init', etc.

        This verifies that built-in options (--show, --tree, --init) don't prevent
        users from creating tasks with those names.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml with tasks named after built-in options
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
show:
  desc: User task named 'show'
  cmd: echo "Running user's show task"

tree:
  desc: User task named 'tree'
  cmd: echo "Running user's tree task"

init:
  desc: User task named 'init'
  cmd: echo "Running user's init task"

list:
  desc: User task named 'list'
  cmd: echo "Running user's list task"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test 1: User tasks can be executed
                result = self.runner.invoke(app, ["show"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'show' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["tree"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'tree' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["init"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'init' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["list"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'list' completed successfully", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_builtin_options_still_work(self):
        """Test that built-in options still work when user has tasks with same names."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml with tasks named after built-in options
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
show:
  desc: User task named 'show'
  cmd: echo "Running user's show task"

build:
  desc: Build task
  outputs: [output.txt]
  cmd: echo "building" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test that --show (built-in option) still works
                result = self.runner.invoke(app, ["--show", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build:", result.stdout)
                self.assertIn("desc: Build task", result.stdout)
                # Should NOT execute the user's "show" task
                self.assertNotIn("Running user's show task", result.stdout)

                # Test that --list (built-in option) still works
                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Available Tasks", result.stdout)
                self.assertIn("show", result.stdout)
                self.assertIn("build", result.stdout)

                # Test that --tree (built-in option) still works
                result = self.runner.invoke(app, ["--tree", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build", result.stdout)
                # Should NOT execute the user's "show" task
                self.assertNotIn("Running user's show task", result.stdout)
            finally:
                os.chdir(original_cwd)

            # Test that --init creates a new file (in a subdir to not conflict)
            init_dir = project_root / "subdir"
            init_dir.mkdir()
            original_cwd = os.getcwd()
            try:
                os.chdir(init_dir)
                result = self.runner.invoke(app, ["--init"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((init_dir / "tasktree.yaml").exists())
                self.assertIn("Created", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_double_dash_required_for_options(self):
        """Test that single-word options don't work - must use double-dash."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  cmd: echo "building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Single word "show" should be treated as a task name (and fail)
                result = self.runner.invoke(app, ["show", "build"], env=self.env)
                # This should fail because "show" task doesn't exist
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("Task not found: show", result.stdout)

                # But --show should work
                result = self.runner.invoke(app, ["--show", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build:", result.stdout)
            finally:
                os.chdir(original_cwd)


    def test_help_option_works(self):
        """Test that --help and -h options work correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  cmd: echo "building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test --help
                result = self.runner.invoke(app, ["--help"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Strip ANSI codes for reliable assertions
                output = strip_ansi_codes(result.stdout)

                self.assertIn("Task Tree", output)
                self.assertIn("Usage:", output)
                # Typer formats it with a box, so just check for "Options"
                self.assertIn("Options", output)
                self.assertIn("--help", output)
                self.assertIn("--version", output)
                self.assertIn("--list", output)
                self.assertIn("--show", output)
                self.assertIn("--tree", output)
                self.assertIn("--dry-run", output)
                self.assertIn("--init", output)
                self.assertIn("--clean", output)
            finally:
                os.chdir(original_cwd)


class TestForceOption(unittest.TestCase):
    """Test the --force/-f option forces re-run of all tasks."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_force_option_reruns_fresh_tasks(self):
        """Test --force causes fresh tasks to re-run."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input and recipe
            input_file = project_root / "input.txt"
            input_file.write_text("initial")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  inputs: [input.txt]
  outputs: [output.txt]
  cmd: cat input.txt > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - task executes
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "output.txt").exists())
                output_time_1 = (project_root / "output.txt").stat().st_mtime

                # Second run - task skips (fresh)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_2 = (project_root / "output.txt").stat().st_mtime
                self.assertEqual(output_time_1, output_time_2)  # Not modified

                # Third run with --force - task executes even though fresh
                import time
                time.sleep(0.01)  # Ensure mtime can change
                result = self.runner.invoke(app, ["--force", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_3 = (project_root / "output.txt").stat().st_mtime
                self.assertGreater(output_time_3, output_time_2)  # Was modified

            finally:
                os.chdir(original_cwd)

    def test_force_short_flag_works(self):
        """Test -f short flag works as alias for --force."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  outputs: [output.txt]
  cmd: echo "built" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run once
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_1 = (project_root / "output.txt").stat().st_mtime

                # Run with -f (short flag)
                import time
                time.sleep(0.01)
                result = self.runner.invoke(app, ["-f", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_2 = (project_root / "output.txt").stat().st_mtime
                self.assertGreater(output_time_2, output_time_1)

            finally:
                os.chdir(original_cwd)

    def test_force_reruns_dependencies(self):
        """Test --force re-runs all dependencies in chain."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
lint:
  outputs: [lint.log]
  cmd: echo "linting" > lint.log

build:
  deps: [lint]
  outputs: [build.log]
  cmd: echo "building" > build.log

test:
  deps: [build]
  outputs: [test.log]
  cmd: echo "testing" > test.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - all execute
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                lint_time_1 = (project_root / "lint.log").stat().st_mtime
                build_time_1 = (project_root / "build.log").stat().st_mtime
                test_time_1 = (project_root / "test.log").stat().st_mtime

                # Second run - all skip (fresh)
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                lint_time_2 = (project_root / "lint.log").stat().st_mtime
                build_time_2 = (project_root / "build.log").stat().st_mtime
                test_time_2 = (project_root / "test.log").stat().st_mtime
                self.assertEqual(lint_time_1, lint_time_2)
                self.assertEqual(build_time_1, build_time_2)
                self.assertEqual(test_time_1, test_time_2)

                # Third run with --force - all re-execute
                import time
                time.sleep(0.01)
                result = self.runner.invoke(app, ["--force", "test"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                lint_time_3 = (project_root / "lint.log").stat().st_mtime
                build_time_3 = (project_root / "build.log").stat().st_mtime
                test_time_3 = (project_root / "test.log").stat().st_mtime
                self.assertGreater(lint_time_3, lint_time_2)
                self.assertGreater(build_time_3, build_time_2)
                self.assertGreater(test_time_3, test_time_2)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
