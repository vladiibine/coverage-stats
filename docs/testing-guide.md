# Unit tests
Examples of where tests should live, for the given code
```python
# file: mymodule/mydubmodule/myfile.py
def foo(a, b):
    ...

class MyClass:
    def __init__(self):
        ...
    
    def method1(self):
        ...

# file: test_mymodue/test_mydubmodule/test_myfile/test_functions.py
class TestFoo:
    def test_happy_case(self):
        ...
    
    def test_edge_case(self):
        ...

# file: test_mymodule/test_mysubmodule/test_myfile/test_my_class.py
# this file contains all the tests for MyClass: One test-class per MyClass method
class TestInit:  # tests for MyClass.__init__
    def test_happy_case(self):
        ...

    ...

class TestMethod1:  # tests for MyClass.method1
    ...

```