* coverage.py (cov) uses sys.settrace alone on python < 3.12
* cov uses both sys.settrace AND sys.monitoring on 3.12 <= python < 3.14
* cov uses sys.monitoring on py >= 3.14
* coverage.py's sys.settrace usage is self-healing (we can't call it, we must deactivate it OR if we inject, we must not inject data 2 times)