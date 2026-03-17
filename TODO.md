TEST
  * test that it works with coverage
  * test that it works with xdist
  * test that it works with both

CORE
  * instead of "lines", we need "statements", like coverage does it
  * add "number of incidental/deliberate tests that ran on this line of code"  

REPORTING:
  * in the html report, there are too many lines columns; Add checkboxes, which enable one or multiple columns
  * [v] exclude some lines (comments, def/class lines, docstrings)
  * [v] show stats for the entire file in the individual file view
  * [v] check skipped if branches
  * check skipped for/while branches
  * [v] count class/def lines as executed if they were actually run; count them as skipped if they were not run (like if present in functions that were not called during the tests) 
  * [v] count total and executed statements like coverage.py does it (the total and missing statements count should be identical)
  * have a default folder, and we only track the coverage there
  * generate the reports via a new command, after the tests have finished running, not as part of the test run (like coverage does it)

Non-functional requirements:
  * check that performance is not seriously degraded
  * the example project, move it 