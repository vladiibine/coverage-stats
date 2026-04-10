TEST
  * [v] The coverage-stats-example project is set up to run with coverage.py and xdist! Just run `nox` (it runs as a pre-commit hook)

DOCS:
  * architecture docs
  * in-report docs (html)
  * cli docs
  * README docs (with pictures)
  * Coverage-stats options should be documented as a group, like coverage.py options are

CORE
  * [v] instead of "lines", we need "statements", like coverage does it
  * [v] add "number of incidental/deliberate tests that ran on this line of code"  
  * generate the reports via a new command, after the tests have finished running, not as part of the test run (like coverage does it)
  * [v] assert_counter.py -> the assert incrementing logic there seems to belong more in the LineProfiler. Move it there if possible, or at least allow the user to parametrize it
  * [v] Test library via itself! See how well it’s intentionally covered
  * [v] add tests invoking the library together with coverage.py / xdist / both
  * [v] html and report_data duplicate calculations -> refactor!
  * [v] document the columns (in README, on the index page and on individual report pages)
  * option to show all tests that ran on a certain line/file/folder
  * code comment to turn off counting of inc/deliberate asserts/test/executions
  *  !!! the Tracing and Reporting coordinators can't actually be subclassed in a 100% useful way. They already register hooks, so their hooks will get called. What can be done is for the hooks to call user-code. Therefore, we should refactor them, 

REPORTING:
  * ordering or html columns
  * (optional) resizing of columns
  * See the exact tests that covered (incidentally & deliberately) every line
  * index should show # inc/del tests
  * [v] color file report pages
  * [v] coloring of stats (from red-ish to green-ish) 
    * [] the colors of folders, make them - % are comparable, # are not, and folders should be added to a comparison bucket different from that of files 
  * [v] in the html index, add all stats (# statements, #/% deliberate, #/% incidental, # asserts, #asserts/#lines)
  * [v] in the html report, there are too many lines columns; Add checkboxes, which enable one or multiple columns
  * [v] json/csv reporting: do they also display partial lines? They should!
  * [v] total coverage
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
  * [v] split HtmlReporter - getting too big. Idea: HtmlIndexReporter + HtmlFileReporter (exposed as attrs on HtmlReporter, so user can customize just 1 class, so we don't get too many customization options). Also split the calculation part from the HTML part
    * [v] also idea: Maybe for the entire customization process we can provide just 1 option: CoverageStatsConfig, with get_<feature>_class() for customizing feature X.
    * SO:
      * adjust the --coverage-stats-report-builder
      * [v] adjust the protocol file  
      * [v] split it in 2 classes (well 3, with the caller)
      * [v] The HTML report builder is not at all configurable, just the thing the creates the data for it. Fix!
      * [v] report builder - there are module level functions in the modules, but they're used only in tests; move them into the test files!
  * clone some open source projects, run its tests, check the coverage for it 
  * publish on pypi
  * [v] make it extensible (allow plugging into the stats collection)
  * [v] plugging into the HTML generation
    * so the CoverageStatsPlugin, on session finish calls the reporter directly
  * [v]allow creating other reporters
    * [v]so the CoverageStatsPlugin, on session finish calls the reporter directly
  * [v] add tox, to test on all supported python versions
    * !used `nox` instead of tox. Should be ok. nox is better integrated with `uv`.
  * [v] check that performance is not seriously degraded
  * [v] the example project, move it 
  * [v] the small project - turn it into a larger one, with lots of lines, files and tests (can be copy-pasted)
