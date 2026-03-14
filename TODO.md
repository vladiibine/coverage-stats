1. asserts - we also want to see the number of asserts executed while tests were run (so incidental coverate, incidental asserts, direct coverage, direct asserts)
2. add % incidental coverage, % direct coverage, indirect asserts/#lines, direct asserts/#lines
2. if possible, don't generate the html file, but hook into the html generation that coverage.py does
3. show how this can be used as a pytest/coverage plugin