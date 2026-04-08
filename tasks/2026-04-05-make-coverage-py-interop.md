# Intro

This doc contains the main idea to make coverage-stats interoperable with coverage.py

# Claude output

How coverage-stats infers branches

It doesn't track arcs at all. Instead, _analyze_branches does a post-hoc AST analysis combined with execution counts:

  - True branch taken: body_count > 0 (first line of body was executed)
  - False branch taken (no else): if_count > body_count — the header line executed more times than the body, meaning some executions skipped the body

This is a count-comparison heuristic, not direct arc tracking. It's clever and largely correct.

Can this feed coverage.py?

Coverage.py's add_arcs() expects explicit (from_line, to_line) pairs for every arc that was actually traversed. Coverage-stats knows which branch was taken, but not always the exact destination line:

  - True branch: destination is body[0].lineno — already known from the AST. ✅ Can construct (header_line, body[0].lineno).
  - False branch with else/elif: destination is orelse[0].lineno — also known from the AST. ✅ Can construct (header_line, orelse[0].lineno).
  - False branch without else: destination is the first line after the entire if/while/for block. ❌ Coverage-stats currently has no mechanism to determine this line.

That last case is the gap. Coverage-stats detects that the false branch was taken (if_count > body_count) but doesn't know the destination. Coverage.py computes this from bytecode;
coverage-stats would need additional AST traversal — specifically, finding the next sibling statement after the block in the AST.

What additional data would be needed

Nothing new needs to be collected at trace time. The line execution counts already contain everything needed. What's missing is a second AST pass that, for each branchable node without an
else, walks up to the parent node's body list and identifies the next sibling statement's lineno. That gives the to_line for false arcs, completing the arc pair for add_arcs().

So: fully achievable with purely static analysis additions to the existing _analyze_branches logic, no changes to the tracer required.

# Plan
* in py<3.12 
  * then if coverage-stats is active
    * then if coverage.py is active
      * then here we mustn't re-install it
      * else here we use the approach that calls other tracing functions, if any were already set
    * else ...so we're installed, but not started. what happens here?
  * else use sys.monitoring

1. if py<3.12 
  1.1. then if coverage-stats is active (--coverage-stats)
    1.1.1. then if coverage.py is active
      1.1.1.1. then here we mustn't re-install it, we just replace it. we'll feed it data at the end. we also need to parse the ast, to get branch info
      1.1.1.2. else here we use the approach that calls other tracing functions, if any were already set. no ast parsing.
    1.1.2. else ...so we're installed, but not started. what happens here?
  1.2. else use sys.monitoring


if py<3.12 :
    if coverage-stats is active (--coverage-stats):
        if coverage.py is active
            ...here we mustn't re-install it, we just replace it. we'll feed it data at the end. we also need to parse the ast, to get branch info
        else: 
            ...here we use the approach that calls other tracing functions, if any were already set. no ast parsing.
    else:  # what happens here?
        ...ensure the plugin does nothing (returns quickly from every hook)
else:
    ...use sys.monitoring