# Task
match statements - check if they can be seen as partial, and implement it like coverage.py if they can

# Context
- the project is documented in README.md
- use `uv` to manage python dependencies
- to test this project, there's a folder coverage-stats-example with example code.


# Constraints
- Must not break existing tests unless tests become obsolete, in which case they need to be changed (preferably) or removed (if they can't be reconciled with the new code changes)
- Add additional tests for this task

# Procedure
1. create a plan before executing
2. save it as a file to task/current-plan.md
3. ask the user to review the plan
4. wait until the user confirms
5. re-read the plan file (because the user might have done changes)
6. execute the plan
7. test the implementation
8. finish only after the execution is done, tests pass and the mypy linter finishes successfully
9. do not lie that tests are passing or that the linter is successful