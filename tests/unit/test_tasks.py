import unittest
from unittest.mock import patch, call, MagicMock
from pathlib import Path

from tasktree import tasks
from tasktree.parser import TaskDefinition

class Tests(unittest.TestCase):
    @patch("subprocess.run")
    def test_loads_single_task(self, subproc_run_spy):
        # Create a mock task definition
        task_def = TaskDefinition(
            name="hello",
            definition={"cmd": "echo hello"}
        )

        # Mock state manager
        mock_state_manager = MagicMock()

        # Execute the task
        tasks.execute_task(
            "hello",
            {"hello": task_def},
            Path("/tmp"),
            mock_state_manager
        )

        # Check that subprocess.run was called correctly
        subproc_run_spy.assert_called_once_with(
            "echo hello",
            shell=True,
            cwd=Path("/tmp"),
            capture_output=False
        )



if __name__ == '__main__':
    unittest.main()
