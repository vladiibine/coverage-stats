TEST
  * test that it works with coverage
  * test that it works with xdist
  * test that it works with both

CORE
  * [v] instead of "lines", we need "statements", like coverage does it
  * [v] add "number of incidental/deliberate tests that ran on this line of code"  
  * generate the reports via a new command, after the tests have finished running, not as part of the test run (like coverage does it)

REPORTING:
  * See the exact tests that covered (incidentally & deliberately) every line
  * in the html report, there are too many lines columns; Add checkboxes, which enable one or multiple columns
  * in the html index, add all stats (statements, #deliberate, %deliberate, #/%incidental, )
  * total coverage
  * json/csv reporting: do they also display partial lines? They should!
  * [v] match statements - check if they can be seen as partial, and implement it like coverage.py if they can
  * [v] check with statement; claude wasn't able to figure it out. I imagine the case where the `__enter__` fires an exception could be treated as partial, but let's check how coverage does it 
  * [v] check skipped for/while branches
  * [v] add num of incidental/deliberate tests that were run for each line of code
  * [v] make the positioning of the table headers stick at the top of the page
  * [v] exclude some lines (comments, def/class lines, docstrings)
  * [v] show stats for the entire file in the individual file view
  * [v] check skipped if branches
  * [v] count class/def lines as executed if they were actually run; count them as skipped if they were not run (like if present in functions that were not called during the tests) 
  * [v] count total and executed statements like coverage.py does it (the total and missing statements count should be identical)
  * [v] have a default folder, and we only track the coverage there
  * [v] summary per folder, in index.html

Non-functional requirements:
  * [v] check that performance is not seriously degraded
  * [v] the example project, move it 
  * [v] the small project - turn it into a larger one, with lots of lines, files and tests (can be copy-pasted)