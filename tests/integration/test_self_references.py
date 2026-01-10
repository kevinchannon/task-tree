"""Integration tests for self-reference templates."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


class TestBasicSelfReferences(unittest.TestCase):
    """Test basic self-reference functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_basic_self_input_reference(self):
        """Test simple {{ self.inputs.src }} in command."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "input.txt"
            src_file.write_text("Hello World")

            # Create recipe with self-reference to input
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  process:
    inputs:
      - src: input.txt
    outputs: [output.txt]
    cmd: cat {{ self.inputs.src }} > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created with correct content
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Hello World")
            finally:
                os.chdir(original_cwd)

    def test_basic_self_output_reference(self):
        """Test simple {{ self.outputs.dest }} in command."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with self-reference to output
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  generate:
    outputs:
      - dest: result.txt
    cmd: echo "Generated content" > {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["generate"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created with correct content
                output_file = project_root / "result.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "Generated content")
            finally:
                os.chdir(original_cwd)

    def test_mixed_self_references(self):
        """Test both inputs and outputs in same command."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "data.txt"
            src_file.write_text("Original Data")

            # Create recipe with both input and output self-references
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  transform:
    inputs:
      - source: data.txt
    outputs:
      - target: processed.txt
    cmd: cat {{ self.inputs.source }} | tr '[:lower:]' '[:upper:]' > {{ self.outputs.target }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["transform"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file has transformed content
                output_file = project_root / "processed.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "ORIGINAL DATA")
            finally:
                os.chdir(original_cwd)

    def test_self_references_with_glob_patterns(self):
        """Test that glob patterns are substituted verbatim."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "file1.txt").write_text("File 1")
            (project_root / "file2.txt").write_text("File 2")

            # Create recipe with glob pattern in input
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  concat:
    inputs:
      - sources: "*.txt"
    outputs:
      - combined: all.txt
    cmd: cat {{ self.inputs.sources }} > {{ self.outputs.combined }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["concat"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file contains both files' content
                output_file = project_root / "all.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                content = output_file.read_text()
                self.assertIn("File 1", content)
                self.assertIn("File 2", content)
            finally:
                os.chdir(original_cwd)

    def test_anonymous_inputs_still_work(self):
        """Test backward compatibility - anonymous inputs work without self-references."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "input.txt").write_text("Anonymous Input")

            # Create recipe with anonymous input (no self-reference)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  copy:
    inputs: [input.txt]
    outputs: [output.txt]
    cmd: cp input.txt output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["copy"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Anonymous Input")
            finally:
                os.chdir(original_cwd)

    def test_anonymous_outputs_still_work(self):
        """Test backward compatibility - anonymous outputs work without self-references."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with anonymous output (no self-reference)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [build.log]
    cmd: echo "Build complete" > build.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created
                output_file = project_root / "build.log"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "Build complete")
            finally:
                os.chdir(original_cwd)

    def test_mixed_named_and_anonymous(self):
        """Test both named and anonymous inputs/outputs in same task."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "named.txt").write_text("Named")
            (project_root / "anon.txt").write_text("Anonymous")

            # Create recipe with mixed inputs/outputs
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  process:
    inputs:
      - config: named.txt
      - anon.txt
    outputs:
      - result: output.txt
      - debug.log
    cmd: |
      cat {{ self.inputs.config }} anon.txt > {{ self.outputs.result }}
      echo "Processed" > debug.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify both output files were created
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                content = output_file.read_text()
                self.assertIn("Named", content)
                self.assertIn("Anonymous", content)

                debug_file = project_root / "debug.log"
                self.assertTrue(debug_file.exists(), "Debug file should exist")
                self.assertEqual(debug_file.read_text().strip(), "Processed")
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
