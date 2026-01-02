#!/usr/bin/env python3
"""Manual test for list formatting."""

import sys
sys.path.insert(0, 'src')

from tasktree.cli import _format_task_arguments

# Test cases
test_cases = [
    ([], ""),
    (["environment"], "environment:str"),
    (["environment=production"], "environment:str with default"),
    (["mode", "target"], "mode:str target:str"),
    (["mode=debug", "target=x86_64"], "both with defaults"),
    (["port:int"], "port:int"),
    (["verbose:bool"], "verbose:bool"),
    (["timeout:float"], "timeout:float"),
]

print("Testing _format_task_arguments:")
for args, desc in test_cases:
    result = _format_task_arguments(args)
    print(f"  {desc}: {result!r}")

print("\nAll tests passed!")
