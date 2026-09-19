"""A size left out must not quietly answer."""

import unittest

import box


class Area(unittest.TestCase):
    def test_area_multiplies_the_two_sizes(self):
        self.assertEqual(box.area(3, 4), 12)

    def test_a_size_left_out_is_a_type_error(self):
        with self.assertRaises(TypeError):
            box.area()
        with self.assertRaises(TypeError):
            box.area(3)
