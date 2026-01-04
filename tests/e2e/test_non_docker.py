"""E2E tests for non-Docker execution."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import run_tasktree_cli


class TestNonDockerExecution(unittest.TestCase):
    """Test basic task execution without Docker."""

    def test_simple_parameterized_task(self):
        """Test a simple recipe with parameterized arguments works as expected."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parameterized task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  deploy:
    args:
      - foo
      - environment: { type: str, choices: ["dev", "staging", "prod"], default: "dev" }
    outputs: [deploy.log]
    cmd: |
      echo "environment={{ arg.environment }}" > deploy.log
      echo "foo was {{ arg.foo }}"
""")

            # Execute: tt deploy 42
            result = run_tasktree_cli(["deploy", "42"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify output file was created
            output_file = project_root / "deploy.log"
            self.assertTrue(output_file.exists(), "deploy.log was not created")

            # Verify output file content
            log_content = output_file.read_text().strip()
            self.assertEqual(
                log_content,
                "environment=dev",
                f"Expected 'environment=dev' but got: {log_content}"
            )

            # Verify terminal output contains expected text
            self.assertIn("foo was 42", result.stdout,
                         f"Expected 'foo was 42' in stdout but got: {result.stdout}")

    def test_parameterized_task_with_custom_environment(self):
        """Test parameterized task with non-default environment choice."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parameterized task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  deploy:
    args:
      - foo
      - environment: { type: str, choices: ["dev", "staging", "prod"], default: "dev" }
    outputs: [deploy.log]
    cmd: |
      echo "environment={{ arg.environment }}" > deploy.log
      echo "foo was {{ arg.foo }}"
""")

            # Execute: tt deploy 42 environment=prod
            result = run_tasktree_cli(["deploy", "42", "environment=prod"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify output file content
            output_file = project_root / "deploy.log"
            self.assertTrue(output_file.exists(), "deploy.log was not created")

            log_content = output_file.read_text().strip()
            self.assertEqual(
                log_content,
                "environment=prod",
                f"Expected 'environment=prod' but got: {log_content}"
            )

            # Verify terminal output
            self.assertIn("foo was 42", result.stdout,
                         f"Expected 'foo was 42' in stdout but got: {result.stdout}")


if __name__ == "__main__":
    unittest.main()
