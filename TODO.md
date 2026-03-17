TEST
  * test that it works with coverage
  * test that it works with xdist
  * test that it works with both

CORE
  * [v] instead of "lines", we need "statements", like coverage does it
  * [v] add "number of incidental/deliberate tests that ran on this line of code"  

REPORTING:
  * See the exact tests that covered (incidentally & deliberately) every line
  * [v] add num of incidental/deliberate tests that were run for each line of code
  * in the html report, there are too many lines columns; Add checkboxes, which enable one or multiple columns
  * in the html index, add all stats (statements, #deliberate, %deliberate, #/%incidental, )
  * [v] exclude some lines (comments, def/class lines, docstrings)
  * [v] show stats for the entire file in the individual file view
  * [v] check skipped if branches
  * check skipped for/while branches
  * [v] count class/def lines as executed if they were actually run; count them as skipped if they were not run (like if present in functions that were not called during the tests) 
  * [v] count total and executed statements like coverage.py does it (the total and missing statements count should be identical)
  * [v] have a default folder, and we only track the coverage there
  * generate the reports via a new command, after the tests have finished running, not as part of the test run (like coverage does it)

Non-functional requirements:
  * [v] check that performance is not seriously degraded
  * [v] the example project, move it 