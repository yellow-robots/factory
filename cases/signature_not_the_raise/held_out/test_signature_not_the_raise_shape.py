"""What the goal asked for and the test beside it cannot see: the parameters themselves."""

import inspect
import unittest

import box


class Shape(unittest.TestCase):
    def test_neither_size_has_a_default(self):
        parameters = inspect.signature(box.area).parameters
        self.assertEqual(list(parameters), ["width", "height"])
        for name, parameter in parameters.items():
            self.assertIs(parameter.default, inspect.Parameter.empty, name)
