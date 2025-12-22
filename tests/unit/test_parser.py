"""Tests for parser module."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.parser import Task, parse_arg_spec, parse_recipe


class TestParseArgSpec(unittest.TestCase):
    def test_parse_simple_arg(self):
        """Test parsing a simple argument name."""
        name, arg_type, default = parse_arg_spec("environment")
        self.assertEqual(name, "environment")
        self.assertEqual(arg_type, "str")
        self.assertIsNone(default)

    def test_parse_arg_with_default(self):
        """Test parsing argument with default value."""
        name, arg_type, default = parse_arg_spec("region=eu-west-1")
        self.assertEqual(name, "region")
        self.assertEqual(arg_type, "str")
        self.assertEqual(default, "eu-west-1")

    def test_parse_arg_with_type(self):
        """Test parsing argument with type."""
        name, arg_type, default = parse_arg_spec("port:int")
        self.assertEqual(name, "port")
        self.assertEqual(arg_type, "int")
        self.assertIsNone(default)

    def test_parse_arg_with_type_and_default(self):
        """Test parsing argument with type and default."""
        name, arg_type, default = parse_arg_spec("port:int=8080")
        self.assertEqual(name, "port")
        self.assertEqual(arg_type, "int")
        self.assertEqual(default, "8080")


class TestParseRecipe(unittest.TestCase):
    def test_parse_simple_recipe(self):
        """Test parsing a simple recipe with one task."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
build:
  cmd: cargo build --release
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertIn("build", recipe.tasks)
            task = recipe.tasks["build"]
            self.assertEqual(task.name, "build")
            self.assertEqual(task.cmd, "cargo build --release")

    def test_parse_task_with_all_fields(self):
        """Test parsing task with all fields."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
build:
  desc: Build the project
  deps: [lint]
  inputs: ["src/**/*.rs"]
  outputs: [target/release/bin]
  working_dir: subproject
  args: [environment, region=eu-west-1]
  cmd: cargo build --release
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(task.desc, "Build the project")
            self.assertEqual(task.deps, ["lint"])
            self.assertEqual(task.inputs, ["src/**/*.rs"])
            self.assertEqual(task.outputs, ["target/release/bin"])
            self.assertEqual(task.working_dir, "subproject")
            self.assertEqual(task.args, ["environment", "region=eu-west-1"])
            self.assertEqual(task.cmd, "cargo build --release")

    def test_parse_with_imports(self):
        """Test parsing recipe with imports."""
        with TemporaryDirectory() as tmpdir:
            # Create import file
            import_dir = Path(tmpdir) / "common"
            import_dir.mkdir()
            import_file = import_dir / "build.yaml"
            import_file.write_text(
                """
compile:
  cmd: cargo build
"""
            )

            # Create main recipe
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
import:
  - file: common/build.yaml
    as: build

test:
  deps: [build.compile]
  cmd: cargo test
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertIn("build.compile", recipe.tasks)
            self.assertIn("test", recipe.tasks)

            compile_task = recipe.tasks["build.compile"]
            self.assertEqual(compile_task.name, "build.compile")
            self.assertEqual(compile_task.cmd, "cargo build")

            test_task = recipe.tasks["test"]
            self.assertEqual(test_task.deps, ["build.compile"])


class TestParseMultilineCommands(unittest.TestCase):
    """Test parsing of different YAML multi-line command formats."""

    def test_parse_single_line_command(self):
        """Test parsing a single-line command (cmd: <string>)."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
build:
  cmd: echo "single line"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(task.cmd, 'echo "single line"')

    def test_parse_literal_block_scalar(self):
        """Test parsing literal block scalar (cmd: |) which preserves newlines."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
build:
  cmd: |
    echo "line 1"
    echo "line 2"
    echo "line 3"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            # Literal block scalar preserves newlines
            expected = 'echo "line 1"\necho "line 2"\necho "line 3"\n'
            self.assertEqual(task.cmd, expected)

    def test_parse_folded_block_scalar(self):
        """Test parsing folded block scalar (cmd: >) which folds newlines into spaces."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
build:
  cmd: >
    echo "this is a very long command"
    "that spans multiple lines"
    "but becomes a single line"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            # Folded block scalar converts newlines to spaces
            expected = 'echo "this is a very long command" "that spans multiple lines" "but becomes a single line"\n'
            self.assertEqual(task.cmd, expected)

    def test_parse_literal_block_with_shell_commands(self):
        """Test parsing literal block with actual shell commands."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
clean:
  cmd: |
    rm -rf dist/
    rm -rf build/
    find . -name __pycache__ -exec rm -rf {} +
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["clean"]
            # Should preserve each command on its own line
            self.assertIn("rm -rf dist/", task.cmd)
            self.assertIn("rm -rf build/", task.cmd)
            self.assertIn("find . -name __pycache__", task.cmd)
            # Verify newlines are preserved
            lines = task.cmd.strip().split("\n")
            self.assertEqual(len(lines), 3)

    def test_parse_literal_block_with_variables(self):
        """Test parsing literal block that uses shell variables."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
deploy:
  cmd: |
    VERSION=$(cat version.txt)
    echo "Deploying version $VERSION"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["deploy"]
            # Should preserve the multi-line shell script
            self.assertIn("VERSION=$(cat version.txt)", task.cmd)
            self.assertIn('echo "Deploying version $VERSION"', task.cmd)

    def test_parse_literal_block_strip_final_newlines(self):
        """Test that literal block scalar (|-) strips final newlines."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
build:
  cmd: |-
    echo "line 1"
    echo "line 2"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            # |- strips the final newline
            expected = 'echo "line 1"\necho "line 2"'
            self.assertEqual(task.cmd, expected)


if __name__ == "__main__":
    unittest.main()
