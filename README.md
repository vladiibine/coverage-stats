# coverage-stats

A pytest plugin that tracks deliberate vs incidental line coverage per test.

## Install

```bash
pip install coverage-stats
```

## Usage

```bash
pytest --coverage-stats
```

Mark which lines a test deliberately covers using the `covers` decorator:

```python
from coverage_stats import covers

@covers("mymodule.MyClass.my_method")
def test_my_method():
    ...
```
