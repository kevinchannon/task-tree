"""Regression test for false dependency triggering bug.

This test verifies that tasks only run when their inputs actually change,
not just because a dependency ran.
"""

import tempfile
import time
from pathlib import Path

import yaml

from tasktree.executor import Executor
from tasktree.parser import parse_recipe
from tasktree.state import StateManager


def test_dependency_runs_but_produces_no_changes():
    """Test that a task whose dependency runs but produces no output changes
    does NOT trigger re-execution.

    Scenario:
    - Task 'build' has no inputs, declares outputs (always runs, like cargo/make)
    - Task 'build' runs but produces no new changes (second run does nothing)
    - Task 'package' depends on 'build' (implicitly gets build outputs as inputs)
    - Expected: 'package' should NOT run because build's outputs didn't change
    - Bug (if present): 'package' runs because 'build' has will_run=True
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create recipe file
        recipe = {
            "tasks": {
                "build": {
                    "desc": "Simulate build tool (cargo/make) with internal dep resolution",
                    "outputs": ["build-artifact.txt"],
                    "cmd": "touch build-artifact.txt",
                },
                "package": {
                    "desc": "Package depends on build outputs",
                    "deps": ["build"],
                    "outputs": ["package.tar.gz"],
                    "cmd": "touch package.tar.gz",
                },
            }
        }

        recipe_path = project_root / "tasktree.yaml"
        recipe_path.write_text(yaml.dump(recipe))

        # First run: establish baseline
        # This creates build-artifact.txt and package.tar.gz
        parsed_recipe = parse_recipe(recipe_path)
        state_manager = StateManager(project_root)
        executor = Executor(parsed_recipe, state_manager)

        statuses = executor.execute_task("package")

        assert statuses["build"].will_run  # First run, no state
        assert statuses["package"].will_run  # First run, no state

        # Verify files exist
        assert (project_root / "build-artifact.txt").exists()
        assert (project_root / "package.tar.gz").exists()

        # Record the mtime of build artifact
        build_artifact_path = project_root / "build-artifact.txt"
        original_mtime = build_artifact_path.stat().st_mtime

        # Small delay to ensure time resolution
        time.sleep(0.01)

        # Second run: build task runs (no inputs) but produces no changes
        # Change build command to do nothing (simulates cargo/make finding nothing to do)
        recipe["tasks"]["build"]["cmd"] = 'echo "checking dependencies, nothing to do"'
        recipe_path.write_text(yaml.dump(recipe))

        parsed_recipe = parse_recipe(recipe_path)
        executor = Executor(parsed_recipe, state_manager)

        statuses = executor.execute_task("package")

        # Build task should run (changed command = new task definition = "never_run")
        # OR if command hadn't changed, would be "no_outputs" (has outputs but no inputs)
        assert statuses["build"].will_run
        assert statuses["build"].reason in ["no_outputs", "never_run"]

        # Verify build-artifact.txt mtime unchanged
        # (build command didn't touch it)
        current_mtime = build_artifact_path.stat().st_mtime
        assert (
            current_mtime == original_mtime
        ), f"Build artifact mtime changed unexpectedly: {original_mtime} -> {current_mtime}"

        # BUG FIX VERIFICATION: Package task should NOT run
        # because build's implicit output (build-artifact.txt) has unchanged mtime
        # This is the CORE assertion that verifies the bug is fixed
        assert (
            statuses["package"].will_run == False
        ), f"Package should not run when dependency produces no changes, but will_run={statuses['package'].will_run}, reason={statuses['package'].reason}"

        assert (
            statuses["package"].reason == "fresh"
        ), f"Package should be fresh, but reason={statuses['package'].reason}"


def test_dependency_actually_changes_outputs():
    """Test that tasks DO run when dependency outputs actually change.

    This is the positive test case - ensure we didn't break normal behavior.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create recipe
        recipe = {
            "tasks": {
                "generate": {
                    "desc": "Generate a file",
                    "outputs": ["config.json"],
                    "cmd": "echo '{}' > config.json",
                },
                "build": {
                    "desc": "Build using generated file",
                    "deps": ["generate"],
                    "outputs": ["app"],
                    "cmd": "touch app",
                },
            }
        }

        recipe_path = project_root / "tasktree.yaml"
        recipe_path.write_text(yaml.dump(recipe))

        # First run: establish baseline
        parsed_recipe = parse_recipe(recipe_path)
        state_manager = StateManager(project_root)
        executor = Executor(parsed_recipe, state_manager)

        statuses = executor.execute_task("build")

        assert statuses["generate"].will_run
        assert statuses["build"].will_run

        # Small delay
        time.sleep(0.01)

        # Second run: modify generate command so it changes its output
        recipe["tasks"]["generate"]["cmd"] = 'echo \'{"version": 2}\' > config.json'
        recipe_path.write_text(yaml.dump(recipe))

        parsed_recipe = parse_recipe(recipe_path)
        executor = Executor(parsed_recipe, state_manager)

        statuses = executor.execute_task("build")

        # Generate runs (changed command = new definition = "never_run")
        # OR if command hadn't changed, would be "no_outputs" (has outputs but no inputs)
        assert statuses["generate"].will_run
        assert statuses["generate"].reason in ["no_outputs", "never_run"]

        # Build SHOULD run because generate's output changed
        assert (
            statuses["build"].will_run
        ), "Build should run when dependency output changes"
        # Reason could be "inputs_changed" or "never_run" (if generate's definition change
        # cascades to make build's implicit inputs appear as first-time)
        assert statuses["build"].reason in [
            "inputs_changed",
            "never_run",
        ], f"Build should run, got reason={statuses['build'].reason}"
