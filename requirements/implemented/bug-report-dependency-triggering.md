# Bug Report: False Dependency Triggering in Incremental Execution

## Summary

Tasks are incorrectly triggered to run when their dependencies execute, even when those dependencies produce no actual changes to their outputs. This violates the principle of incremental execution and causes unnecessary rebuilds.

## Current Behaviour

The executor performs static analysis of the dependency graph before execution:

1. Topologically sorts all tasks
2. For each task in order, checks if it should run by examining:
   - Whether any dependency has `will_run=True` (static check)
   - Whether inputs have changed (dynamic check via mtime)
   - Other conditions (never run, no outputs, etc.)
3. Executes all tasks marked with `will_run=True`

The problem occurs at step 2: if a dependency is marked `will_run=True`, the current task is immediately marked to run, regardless of whether that dependency actually modified any files.

## Expected Behaviour

Tasks should run based solely on the runtime state of their inputs:

1. Topologically sort all tasks
2. For each task in execution order:
   - Check if any of its inputs (explicit or implicit) have changed
   - If inputs changed (or other valid conditions met), execute the task
   - After execution, downstream tasks check their inputs against actual file mtimes
3. A dependency that runs but produces no changes should NOT trigger downstream tasks

This matches Make's behaviour: it checks whether dependency output files are newer than the target, not whether the dependency command ran.

## Reproduction Test Case

The following test demonstrates the bug:

```python
def test_dependency_runs_but_produces_no_changes():
    """
    Test that a task whose dependency runs but produces no output changes
    does NOT trigger re-execution.
    
    Scenario:
    - Task 'build' has no inputs, declares outputs (always runs, like cargo/make)
    - Task 'build' runs but creates no new files (simulated by not touching)
    - Task 'package' depends on 'build' (implicitly gets build outputs as inputs)
    - Expected: 'package' should NOT run because build's outputs didn't change
    - Actual (bug): 'package' runs because 'build' has will_run=True
    """
    import tempfile
    import os
    from pathlib import Path
    from unittest.mock import patch
    import yaml
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        
        # Create recipe file
        recipe = {
            'build': {
                'desc': 'Simulate build tool (cargo/make) with internal dep resolution\nNo inputs - tool does its own dependency checking\nHas outputs so package can implicitly depend on them',
                'outputs': ['build-artifact.txt'],
                'cmd': 'touch build-artifact.txt',
            },
            'package': {
                'desc': 'No explicit inputs - should implicitly inherit build-artifact.txt from build',
                'deps': ['build'],
                'outputs': ['package.tar.gz'],
                'cmd': 'touch package.tar.gz',
            }
        }
        
        recipe_path = project_root / 'tasktree.yaml'
        recipe_path.write_text(yaml.dump(recipe))
        
        # First run: establish baseline
        # This creates build-artifact.txt and package.tar.gz
        from tasktree.parser import parse_recipe
        from tasktree.state import StateManager
        from tasktree.executor import Executor
        
        parsed_recipe = parse_recipe(recipe_path)
        state_manager = StateManager(project_root / '.tasktree-state')
        executor = Executor(parsed_recipe, state_manager)
        
        statuses = executor.execute_task('package')
        
        assert statuses['build'].will_run  # First run, no state
        assert statuses['package'].will_run  # First run, no state
        
        # Verify files exist
        assert (project_root / 'build-artifact.txt').exists()
        assert (project_root / 'package.tar.gz').exists()
        
        # Get actual mtime of build artifact
        build_artifact_path = project_root / 'build-artifact.txt'
        original_mtime = build_artifact_path.stat().st_mtime
        
        # Second run: build task runs (no inputs) but produces no changes
        # Simulate this by having build command do nothing
        recipe['build']['cmd'] = 'echo "checking dependencies, nothing to do"'
        recipe_path.write_text(yaml.dump(recipe))
        
        parsed_recipe = parse_recipe(recipe_path)
        executor = Executor(parsed_recipe, state_manager)
        
        # Patch os.stat to return the original mtime for build-artifact.txt
        # This simulates build running but not modifying its outputs
        original_stat = os.stat
        def patched_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if Path(path) == build_artifact_path:
                # Return stat result with original mtime
                import os
                stat_result = os.stat_result((
                    result.st_mode,
                    result.st_ino,
                    result.st_dev,
                    result.st_nlink,
                    result.st_uid,
                    result.st_gid,
                    result.st_size,
                    result.st_atime,
                    original_mtime,  # Keep original mtime
                    result.st_ctime,
                ))
                return stat_result
            return result
        
        with patch('os.stat', side_effect=patched_stat):
            with patch('pathlib.Path.stat', side_effect=lambda self: patched_stat(self)):
                statuses = executor.execute_task('package')
        
        # Build task should run (has no inputs)
        assert statuses['build'].will_run
        assert statuses['build'].reason == 'no_outputs'
        
        # BUG: Package task runs because build ran, even though build's output unchanged
        # EXPECTED: package task should NOT run (implicit inputs haven't changed)
        assert statuses['package'].will_run == False, \
            f"Package should not run when dependency produces no changes, " \
            f"but will_run={statuses['package'].will_run}, reason={statuses['package'].reason}"
```

## Root Cause Analysis

The issue is in the execution planning phase. The code attempts to determine which tasks will run before any tasks execute. This creates a dependency on static analysis of the dependency graph rather than dynamic checking of actual file states.

The specific problematic logic:
- Checking `if any(status.will_run for status in dep_statuses.values())` 
- This happens before the dependency actually runs
- Therefore, it cannot know what the dependency will actually do to files

## Algorithmic Changes Required

The execution algorithm needs to shift from "plan then execute" to "check and execute incrementally":

**Current approach:**
```
for each task in topo order:
    if dependency.will_run:
        mark this task to run
    elif inputs changed:
        mark this task to run
    
for each task marked to run:
    execute task
```

**Required approach:**
```
for each task in topo order:
    if inputs changed (checking actual file mtimes):
        execute task
        update state
    else:
        skip task
```

The key differences:
1. No separate planning phase that checks `dep_statuses`
2. Each task checks only the current runtime state of its inputs
3. Execution happens immediately when needed, not in a separate loop
4. State updates happen immediately after execution

## Implementation Considerations

- The `TaskStatus` dataclass and planning phase may need significant restructuring
- The `check_task_status` method should not receive or examine `dep_statuses`
- Input checking should always use current file system state, never cached planning decisions
- The execution order still requires topological sorting (dependencies run before dependents)
- Edge cases to preserve:
  - Tasks with no inputs/outputs still run every time
  - `--force` flag behaviour
  - Missing outputs trigger re-execution
  - First-run (no cached state) behaviour

## Test Validation

The test case should pass after the fix:
- First run: both tasks execute (establishing baseline)
- Second run: build runs (no inputs/outputs), package skips (inputs unchanged)
- The test explicitly verifies build-artifact.txt mtime is unchanged
- The test asserts package task does NOT run

## Related Code Locations

- `src/tasktree/executor.py`: `Executor.execute_task()` method
- `src/tasktree/executor.py`: `Executor.check_task_status()` method
- Focus on the dependency triggering logic and execution flow

## Additional Context

This bug fundamentally conflicts with the tool's purpose: intelligent incremental execution. Build tools like cargo, make, and cmake have sophisticated internal dependency tracking. When tt wraps these tools, it should respect their decisions about whether work is needed, not override them with static graph analysis.

The current implementation would cause spurious rebuilds in common workflows:
- `cargo build` (checks Rust dependencies, may do nothing)
- `make` (checks C/C++ timestamps, may do nothing)  
- `cmake --build` (checks build graph, may do nothing)

These tools are designed to be incremental. Forcing downstream tasks to run when these tools decide nothing changed defeats the purpose of incremental builds.
